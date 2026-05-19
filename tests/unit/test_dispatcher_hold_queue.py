"""Unit tests for the HoldQueue dependency gate. See iter_3.md Phase 2C."""

from __future__ import annotations

import asyncio
from uuid import UUID, uuid4

import pytest

from core.dispatcher.hold_queue import HoldQueue
from core.messaging.schemas import (
    AgentId,
    AgentMessage,
    MessageType,
    Priority,
    TaskAssignmentPayload,
    TaskReportPayload,
    TaskStatus,
)


def _assignment(correlation_id: UUID, *, task_id: UUID | None = None) -> AgentMessage:
    return AgentMessage(
        correlation_id=correlation_id,
        sender=AgentId.TEAM_LEAD,
        recipient=AgentId.BACKEND_DEVELOPER,
        message_type=MessageType.TASK_ASSIGNMENT,
        priority=Priority.P2,
        payload=TaskAssignmentPayload(
            task_id=task_id or uuid4(),
            title="t",
            description="d",
        ),
    )


def _done_report(correlation_id: UUID, task_id: UUID) -> AgentMessage:
    return AgentMessage(
        correlation_id=correlation_id,
        sender=AgentId.BACKEND_DEVELOPER,
        recipient=AgentId.TEAM_LEAD,
        message_type=MessageType.TASK_REPORT,
        priority=Priority.P3,
        payload=TaskReportPayload(
            task_id=task_id,
            status=TaskStatus.DONE,
            progress_pct=100,
            summary="ok",
        ),
    )


@pytest.mark.asyncio
async def test_hold_returns_false_when_no_predecessors() -> None:
    q = HoldQueue()
    msg = _assignment(uuid4())
    held = await q.hold(msg, depends_on=set())
    assert held is False


@pytest.mark.asyncio
async def test_hold_returns_true_when_predecessor_missing() -> None:
    q = HoldQueue()
    cid = uuid4()
    msg = _assignment(cid)
    held = await q.hold(msg, depends_on={uuid4()})
    assert held is True


@pytest.mark.asyncio
async def test_hold_returns_false_when_predecessor_already_done() -> None:
    q = HoldQueue()
    cid = uuid4()
    pred = uuid4()
    await q.mark_done(cid, pred)
    msg = _assignment(cid)
    held = await q.hold(msg, depends_on={pred})
    assert held is False


@pytest.mark.asyncio
async def test_mark_done_releases_dependent() -> None:
    q = HoldQueue()
    cid = uuid4()
    pred = uuid4()
    held_msg = _assignment(cid)
    await q.hold(held_msg, depends_on={pred})

    released = await q.mark_done(cid, pred)

    assert len(released) == 1
    assert released[0].message_id == held_msg.message_id


@pytest.mark.asyncio
async def test_mark_done_releases_only_when_all_predecessors_done() -> None:
    q = HoldQueue()
    cid = uuid4()
    pred_a = uuid4()
    pred_b = uuid4()
    held_msg = _assignment(cid)
    await q.hold(held_msg, depends_on={pred_a, pred_b})

    released_after_a = await q.mark_done(cid, pred_a)
    assert released_after_a == []

    released_after_b = await q.mark_done(cid, pred_b)
    assert len(released_after_b) == 1
    assert released_after_b[0].message_id == held_msg.message_id


@pytest.mark.asyncio
async def test_mark_done_isolated_per_correlation() -> None:
    q = HoldQueue()
    cid_a = uuid4()
    cid_b = uuid4()
    pred = uuid4()
    msg_b = _assignment(cid_b)
    await q.hold(msg_b, depends_on={pred})

    # Same task_id done in a different correlation_id MUST NOT release msg_b.
    released = await q.mark_done(cid_a, pred)
    assert released == []


@pytest.mark.asyncio
async def test_mark_done_idempotent_on_unknown_task_id() -> None:
    q = HoldQueue()
    cid = uuid4()
    released = await q.mark_done(cid, uuid4())
    assert released == []
    # Marking the same unknown id a second time should also be a no-op.
    released = await q.mark_done(cid, uuid4())
    assert released == []


@pytest.mark.asyncio
async def test_released_messages_removed_from_held_queue() -> None:
    q = HoldQueue()
    cid = uuid4()
    pred = uuid4()
    held_msg = _assignment(cid)
    await q.hold(held_msg, depends_on={pred})

    released_first = await q.mark_done(cid, pred)
    assert len(released_first) == 1

    # Marking pred done again returns nothing — the dependent is no
    # longer in the held queue.
    released_second = await q.mark_done(cid, pred)
    assert released_second == []


@pytest.mark.asyncio
async def test_concurrent_hold_and_mark_done_race_free() -> None:
    """Many concurrent holds + one mark_done should release exactly the right set."""
    q = HoldQueue()
    cid = uuid4()
    pred = uuid4()
    msgs = [_assignment(cid) for _ in range(20)]
    # Half depend on pred, half don't (immediately publishable).
    await asyncio.gather(
        *(q.hold(m, depends_on={pred}) for m in msgs[:10]),
        *(q.hold(m, depends_on=set()) for m in msgs[10:]),
    )
    released = await q.mark_done(cid, pred)
    assert len(released) == 10
    released_ids = {r.message_id for r in released}
    expected_ids = {m.message_id for m in msgs[:10]}
    assert released_ids == expected_ids


@pytest.mark.asyncio
async def test_mark_failed_drops_held_dependents() -> None:
    q = HoldQueue()
    cid = uuid4()
    failed_pred = uuid4()
    other_pred = uuid4()

    held_on_failed = _assignment(cid)
    held_on_other = _assignment(cid)
    await q.hold(held_on_failed, depends_on={failed_pred})
    await q.hold(held_on_other, depends_on={other_pred})

    dropped = await q.mark_failed(cid, failed_pred)
    assert len(dropped) == 1
    assert dropped[0].message_id == held_on_failed.message_id

    # The other dependent is untouched; marking its real predecessor done
    # still releases it.
    released = await q.mark_done(cid, other_pred)
    assert len(released) == 1
    assert released[0].message_id == held_on_other.message_id


@pytest.mark.asyncio
async def test_done_report_payload_compat() -> None:
    """Smoke: _done_report builds a valid TASK_REPORT(DONE) we can use elsewhere."""
    cid = uuid4()
    task_id = uuid4()
    rpt = _done_report(cid, task_id)
    assert isinstance(rpt.payload, TaskReportPayload)
    assert rpt.payload.status == TaskStatus.DONE
    assert rpt.payload.task_id == task_id
