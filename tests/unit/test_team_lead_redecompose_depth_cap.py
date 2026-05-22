"""TL re-decompose depth cap. iter-29c."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import uuid4

import pytest

from agents.team_lead import TeamLeadAgent
from agents.team_lead.agent import MAX_REDECOMPOSE_DEPTH
from core.messaging.schemas import (
    AgentId,
    AgentMessage,
    MessageType,
    Priority,
    TaskAssignmentPayload,
    TaskReportPayload,
    TaskStatus,
)

if TYPE_CHECKING:
    from uuid import UUID

    from core.llm.base import LLMResponse


class _StubLLM:
    async def invoke(self, **kwargs: object) -> LLMResponse:  # pragma: no cover
        raise AssertionError("TL must not call LLM in re-decompose dispatch")

    async def reset_session(self, session_id: str) -> None:
        return None


def _blocked_too_large(*, correlation_id: UUID | None = None) -> AgentMessage:
    return AgentMessage(
        correlation_id=correlation_id or uuid4(),
        sender=AgentId.BACKEND_DEVELOPER,
        recipient=AgentId.TEAM_LEAD,
        message_type=MessageType.TASK_REPORT,
        priority=Priority.P2,
        payload=TaskReportPayload(
            task_id=uuid4(),
            status=TaskStatus.BLOCKED,
            progress_pct=0,
            summary="Scope pre-flight: task too large: description 2000 chars > 1500 threshold",
            blocked_on="task_too_large",
        ),
    )


@pytest.mark.asyncio
async def test_depth_zero_re_decomposes_as_before() -> None:
    """Regression guard: first BLOCKED(task_too_large) still produces
    a TL→TL self-assignment."""
    agent = TeamLeadAgent(llm=_StubLLM())
    outputs = await agent.handle(_blocked_too_large())

    assert len(outputs) == 1
    out = outputs[0]
    assert out.message_type == MessageType.TASK_ASSIGNMENT
    assert out.recipient == AgentId.TEAM_LEAD
    assert isinstance(out.payload, TaskAssignmentPayload)


@pytest.mark.asyncio
async def test_depth_at_cap_emits_failed_report() -> None:
    """After MAX_REDECOMPOSE_DEPTH successful re-decomposes within one
    correlation, the next BLOCKED(task_too_large) emits FAILED instead
    of another self-assignment."""
    agent = TeamLeadAgent(llm=_StubLLM())
    cid = uuid4()

    # First MAX_REDECOMPOSE_DEPTH re-decomposes succeed.
    for _ in range(MAX_REDECOMPOSE_DEPTH):
        out = await agent.handle(_blocked_too_large(correlation_id=cid))
        assert out[0].message_type == MessageType.TASK_ASSIGNMENT

    # Next hit on the same correlation must trip the cap.
    outputs = await agent.handle(_blocked_too_large(correlation_id=cid))

    assert len(outputs) == 1
    cap_msg = outputs[0]
    assert cap_msg.message_type == MessageType.TASK_REPORT
    payload = cap_msg.payload
    assert isinstance(payload, TaskReportPayload)
    assert payload.status == TaskStatus.FAILED
    assert "re-decompose" in payload.summary.lower()
    assert str(MAX_REDECOMPOSE_DEPTH) in payload.summary


@pytest.mark.asyncio
async def test_cap_isolated_per_correlation() -> None:
    """Two unrelated correlations don't share the counter."""
    agent = TeamLeadAgent(llm=_StubLLM())
    c1, c2 = uuid4(), uuid4()

    # Exhaust c1's quota.
    for _ in range(MAX_REDECOMPOSE_DEPTH):
        await agent.handle(_blocked_too_large(correlation_id=c1))
    cap_hit = await agent.handle(_blocked_too_large(correlation_id=c1))
    assert cap_hit[0].message_type == MessageType.TASK_REPORT

    # c2 still gets its first re-decompose.
    out = await agent.handle(_blocked_too_large(correlation_id=c2))
    assert out[0].message_type == MessageType.TASK_ASSIGNMENT


@pytest.mark.asyncio
async def test_cap_exceeded_summary_mentions_threshold() -> None:
    agent = TeamLeadAgent(llm=_StubLLM())
    cid = uuid4()
    for _ in range(MAX_REDECOMPOSE_DEPTH):
        await agent.handle(_blocked_too_large(correlation_id=cid))
    outputs = await agent.handle(_blocked_too_large(correlation_id=cid))

    payload = outputs[0].payload
    assert isinstance(payload, TaskReportPayload)
    assert "cap" in payload.summary.lower()
    assert str(MAX_REDECOMPOSE_DEPTH) in payload.summary
