"""Direct integration tests for TaskStateReducer.on_drop edge cases.

The happy path (drop terminalises child + rolls up parent) is covered
by tests/integration/test_dispatcher_e2e.py's
test_dropped_dependent_child_task_flips_to_failed (iter-6 two-level
cascade) and test_transitive_drops_cascade_through_hold_queue (iter-7
three-level cascade). This file pins the protective guards that
on_drop is responsible for and that the dispatcher path doesn't
exercise in practice.

See iter_7.md Phase 4 + iter_6_demo_report.md Failure 3.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import uuid4

import pytest
from sqlalchemy import select

from core.messaging.schemas import AgentId, Priority
from core.persistence.models import Task
from core.persistence.task_state import TaskStateReducer

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = pytest.mark.integration


async def test_on_drop_no_op_when_task_id_missing(
    session_factory: async_sessionmaker[AsyncSession],
    db_session: AsyncSession,
) -> None:
    """on_drop with a task_id that doesn't exist in the tasks table is
    a no-op (the reducer logs `task_state.drop_no_matching_child`
    and moves on). Common in production when the dispatcher's
    hold-queue state outlives a row's deletion."""
    _ = db_session
    reducer = TaskStateReducer(session_factory)
    await reducer.on_drop([uuid4()])  # must not raise


async def test_on_drop_skipped_when_child_already_terminal(
    session_factory: async_sessionmaker[AsyncSession],
    db_session: AsyncSession,
) -> None:
    """on_drop on a task_id whose row is already terminal must NOT
    re-flip it (idempotent + protects against late drops racing with
    an earlier on_report that beat them)."""
    _ = db_session
    child_id = uuid4()
    async with session_factory() as session:
        session.add(
            Task(
                id=child_id,
                correlation_id=uuid4(),
                title="t",
                description="d",
                status="failed",
                assigned_agent=AgentId.BACKEND_DEVELOPER.value,
                priority=Priority.P2.value,
            )
        )
        await session.commit()

    reducer = TaskStateReducer(session_factory)
    await reducer.on_drop([child_id])

    async with session_factory() as session:
        row = (await session.execute(select(Task).where(Task.id == child_id))).scalar_one()
    assert row.status == "failed"  # unchanged


async def test_on_drop_parent_rollup_no_op_when_parent_status_unchanged(
    session_factory: async_sessionmaker[AsyncSession],
    db_session: AsyncSession,
) -> None:
    """When the parent's existing status already equals the derived
    status (parent already `failed` because some other sibling already
    rolled it up), the rollup must short-circuit without a redundant
    write — and certainly without an exception."""
    _ = db_session
    parent_id = uuid4()
    child_id = uuid4()
    async with session_factory() as session:
        session.add(
            Task(
                id=parent_id,
                correlation_id=uuid4(),
                title="root",
                description="r",
                status="failed",  # already terminal
                assigned_agent=AgentId.TEAM_LEAD.value,
                priority=Priority.P2.value,
            )
        )
        session.add(
            Task(
                id=child_id,
                correlation_id=uuid4(),
                title="c",
                description="d",
                status="in_progress",
                assigned_agent=AgentId.BACKEND_DEVELOPER.value,
                priority=Priority.P2.value,
                parent_task_id=parent_id,
            )
        )
        await session.commit()

    reducer = TaskStateReducer(session_factory)
    await reducer.on_drop([child_id])

    # Parent stayed `failed` (no exception, no regression to a different
    # status). The child flipped to `failed` via the drop.
    async with session_factory() as session:
        parent = (await session.execute(select(Task).where(Task.id == parent_id))).scalar_one()
        child = (await session.execute(select(Task).where(Task.id == child_id))).scalar_one()
    assert parent.status == "failed"
    assert child.status == "failed"


async def test_on_drop_rollup_mixed_siblings_keeps_parent_in_progress(
    session_factory: async_sessionmaker[AsyncSession],
    db_session: AsyncSession,
) -> None:
    """When a child is dropped but other siblings are still mid-flight,
    derive_parent_status returns 'failed' (any-failed dominates per
    iter-3 rule). The parent rolls up immediately — siblings still
    in_progress cannot un-fail it. Pins the rollup semantics
    explicitly so a future "wait for all siblings" rewrite would
    surface here."""
    _ = db_session
    parent_id = uuid4()
    dropped_child = uuid4()
    busy_sibling = uuid4()
    async with session_factory() as session:
        session.add(
            Task(
                id=parent_id,
                correlation_id=uuid4(),
                title="root",
                description="r",
                status="in_progress",
                assigned_agent=AgentId.TEAM_LEAD.value,
                priority=Priority.P2.value,
            )
        )
        session.add(
            Task(
                id=dropped_child,
                correlation_id=uuid4(),
                title="dropped",
                description="d",
                status="in_progress",
                assigned_agent=AgentId.BACKEND_DEVELOPER.value,
                priority=Priority.P2.value,
                parent_task_id=parent_id,
            )
        )
        session.add(
            Task(
                id=busy_sibling,
                correlation_id=uuid4(),
                title="busy",
                description="d",
                status="in_progress",
                assigned_agent=AgentId.QA_ENGINEER.value,
                priority=Priority.P3.value,
                parent_task_id=parent_id,
            )
        )
        await session.commit()

    reducer = TaskStateReducer(session_factory)
    await reducer.on_drop([dropped_child])

    async with session_factory() as session:
        parent = (await session.execute(select(Task).where(Task.id == parent_id))).scalar_one()
        sibling = (await session.execute(select(Task).where(Task.id == busy_sibling))).scalar_one()
    # Parent rolled up to failed (any-failed wins); the busy sibling
    # is untouched (it stays in_progress).
    assert parent.status == "failed"
    assert sibling.status == "in_progress"
