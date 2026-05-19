"""Task state reducer: child rows + parent rollup. See iter-3 Phase 3.

The Team Lead's `build_outputs` stamps `metadata["parent_task_id"]` onto
every sub-task assignment it emits. The dispatcher calls this reducer:

  * `on_assignment(...)` when an outbound TASK_ASSIGNMENT carries a
    `parent_task_id` — insert a child `Task` row tied to the parent.
  * `on_report(...)` when an outbound TASK_REPORT lands — update the
    matching `Task` row's status. If every child of the same parent is
    now terminal (`done` / `failed`), flip the parent's status too.

Why this lives in `core/persistence/` rather than `core/dispatcher/`:
the reducer is a thin layer over the `tasks` table; the dispatcher's
job is routing, not bookkeeping. Keeping persistence concerns near
the model means the dispatcher imports a single `TaskStateReducer`
class and doesn't grow new SQL.

The pure-logic helpers (`is_terminal`, `derive_parent_status`) are
unit-testable without a database.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog
from sqlalchemy import select

from core.persistence.models import Task

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

_log = structlog.get_logger(__name__)


TERMINAL_STATUSES: frozenset[str] = frozenset({"done", "failed"})


def is_terminal(status: str) -> bool:
    return status in TERMINAL_STATUSES


def derive_parent_status(child_statuses: list[str]) -> str | None:
    """Decide whether a parent task should flip status given its children.

    Rules:
      - Empty list (no children) → None (don't touch the parent).
      - Any child `failed` → `failed` (failure dominates even mid-flight
        siblings; a failed dep means the root can't complete).
      - All children `done` → `done`.
      - Otherwise → None (parent stays `in_progress` or `pending`).
    """
    if not child_statuses:
        return None
    if "failed" in child_statuses:
        return "failed"
    if all(s == "done" for s in child_statuses):
        return "done"
    return None


class TaskStateReducer:
    """Insert sub-task rows + roll parent status up from child terminals.

    Failure mode: a TL decomposition that crashes after writing rows 1
    and 2 of 3 leaves orphans (parent stays in_progress forever because
    no child #3 exists). Iter-3 ships with that risk documented; iter-4
    will wrap the TL batch in a single transaction.
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def on_assignment(
        self,
        *,
        child_task_id: UUID,
        parent_task_id: UUID,
        correlation_id: UUID,
        recipient: str,
        title: str,
        description: str,
        priority: str,
        target_repo: str | None,
        iteration: int | None,
    ) -> None:
        """Insert a child Task row when TL emits a sub-task assignment."""
        async with self._session_factory() as session:
            session.add(
                Task(
                    id=child_task_id,
                    correlation_id=correlation_id,
                    title=title[:200],
                    description=description,
                    target_repo=target_repo,
                    status="in_progress",
                    assigned_agent=recipient,
                    priority=priority,
                    iteration=iteration,
                    parent_task_id=parent_task_id,
                )
            )
            await session.commit()
        _log.info(
            "task_state.child_inserted",
            child_task_id=str(child_task_id),
            parent_task_id=str(parent_task_id),
            recipient=recipient,
        )

    async def on_drop(self, task_ids: list[UUID]) -> None:
        """Flip dropped dependents' Task rows to FAILED and roll up parents.

        Called from the dispatcher when `HoldQueue.mark_failed` returns
        dropped held messages: those dependents will never run because a
        predecessor failed, so their child Task rows must terminate (not
        stay `in_progress` indefinitely). We reuse `failed` rather than
        introduce a new `dropped` status — `derive_parent_status`
        already cascades `failed` through the rollup, and the
        forensics-quality distinction between a real crash and a drop
        is on the audit_log (synth helper records both), not the tasks
        table. See iter_5_demo_report.md Failure 3 + iter_6.md
        decision #3.

        Idempotent: re-applying `failed` to an already-`failed` row is
        a no-op; non-terminal rows (a row that somehow already completed
        between the dispatcher's hold and this call) are left alone via
        the same guard that on_report uses.
        """
        if not task_ids:
            return
        async with self._session_factory() as session:
            parent_ids: set[UUID] = set()
            for task_id in task_ids:
                child = (
                    await session.execute(select(Task).where(Task.id == task_id))
                ).scalar_one_or_none()
                if child is None:
                    _log.debug("task_state.drop_no_matching_child", task_id=str(task_id))
                    continue
                if is_terminal(child.status):
                    _log.debug(
                        "task_state.drop_skipped_already_terminal",
                        task_id=str(task_id),
                        existing=child.status,
                    )
                    continue
                child.status = "failed"
                if child.parent_task_id is not None:
                    parent_ids.add(child.parent_task_id)
            await session.commit()

            # Roll up each affected parent. Mirrors on_report's
            # derive_parent_status path so a fully-dropped batch flips
            # the root to `failed` (any-failed dominates).
            for parent_id in parent_ids:
                siblings = (
                    (await session.execute(select(Task).where(Task.parent_task_id == parent_id)))
                    .scalars()
                    .all()
                )
                new_parent_status = derive_parent_status([s.status for s in siblings])
                if new_parent_status is None:
                    continue
                parent = (
                    await session.execute(select(Task).where(Task.id == parent_id))
                ).scalar_one_or_none()
                if parent is None:
                    _log.warning(
                        "task_state.parent_missing_on_drop",
                        parent_id=str(parent_id),
                    )
                    continue
                if parent.status == new_parent_status:
                    continue
                parent.status = new_parent_status
                await session.commit()
                _log.info(
                    "task_state.parent_rolled_up_on_drop",
                    parent_task_id=str(parent_id),
                    new_status=new_parent_status,
                    dropped_count=len(task_ids),
                )
        _log.info(
            "task_state.children_dropped",
            count=len(task_ids),
            task_ids=[str(t) for t in task_ids],
        )

    async def on_report(self, *, task_id: UUID, status: str) -> None:
        """Update the matching child's status; flip parent if all terminal.

        Idempotent on already-terminal children: re-applying the same
        terminal status is a no-op. Late-arriving non-terminal reports
        (e.g. an `in_progress` heartbeat after a `done`) do not regress
        a terminal child — guards against TASK_REPORT(in_progress) racing
        with a final TASK_REPORT(done).
        """
        async with self._session_factory() as session:
            child = (
                await session.execute(select(Task).where(Task.id == task_id))
            ).scalar_one_or_none()
            if child is None:
                # No matching child row — either the TL didn't stamp
                # parent_task_id (root task; iter-2 chain), or the row
                # never got inserted. Either way, nothing to roll up.
                _log.debug("task_state.report_no_matching_child", task_id=str(task_id))
                return

            if is_terminal(child.status) and not is_terminal(status):
                _log.debug(
                    "task_state.report_skipped_already_terminal",
                    task_id=str(task_id),
                    existing=child.status,
                    incoming=status,
                )
                return

            child.status = status
            await session.commit()

            parent_id = child.parent_task_id
            if parent_id is None or not is_terminal(status):
                return

            # Roll up: gather all siblings under the same parent.
            siblings = (
                (await session.execute(select(Task).where(Task.parent_task_id == parent_id)))
                .scalars()
                .all()
            )
            new_parent_status = derive_parent_status([s.status for s in siblings])
            if new_parent_status is None:
                return

            parent = (
                await session.execute(select(Task).where(Task.id == parent_id))
            ).scalar_one_or_none()
            if parent is None:
                _log.warning(
                    "task_state.parent_missing",
                    child_task_id=str(task_id),
                    parent_id=str(parent_id),
                )
                return
            if parent.status == new_parent_status:
                return
            parent.status = new_parent_status
            await session.commit()
            _log.info(
                "task_state.parent_rolled_up",
                parent_task_id=str(parent_id),
                new_status=new_parent_status,
                child_count=len(siblings),
            )
