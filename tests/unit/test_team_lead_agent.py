"""Tests for TeamLeadAgent — Opus, decomposition + BLOCKED auto-routing.

The decomposition path is exercised end-to-end via the integration test
`tests/integration/test_dispatcher_e2e.py`. This file unit-tests the
new Phase-4 BLOCKED-routing branch in isolation (pure dispatch, no LLM
call needed)."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import uuid4

import pytest

from agents.team_lead import TeamLeadAgent
from agents.team_lead.agent import _AUTO_ROUTED_MARKER
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
    from core.llm.base import LLMResponse


class _StubLLM:
    """TL.handle() should never call the LLM for BLOCKED routing.
    If it does, this stub raises so the test fails loudly."""

    async def invoke(self, **kwargs: object) -> LLMResponse:  # pragma: no cover
        raise AssertionError("TL invoked LLM during BLOCKED routing")

    async def reset_session(self, session_id: str) -> None:
        return None


def _blocked_report(
    *,
    sender: AgentId = AgentId.DEVOPS,
    blocked_on: str | None = "backend_developer",
    summary: str = "DevOps blocked: blocked: requires backend_developer (agents/foo.py).",
) -> AgentMessage:
    return AgentMessage(
        correlation_id=uuid4(),
        sender=sender,
        recipient=AgentId.TEAM_LEAD,
        message_type=MessageType.TASK_REPORT,
        priority=Priority.P2,
        payload=TaskReportPayload(
            task_id=uuid4(),
            status=TaskStatus.BLOCKED,
            progress_pct=0,
            summary=summary,
            artifacts=[],
            blocked_on=blocked_on,
        ),
    )


@pytest.mark.asyncio
async def test_routes_blocked_with_explicit_blocked_on_field() -> None:
    agent = TeamLeadAgent(llm=_StubLLM())
    msg = _blocked_report(blocked_on="backend_developer")

    outputs = await agent.handle(msg)

    assert len(outputs) == 1
    out = outputs[0]
    assert out.sender == AgentId.TEAM_LEAD
    assert out.recipient == AgentId.BACKEND_DEVELOPER
    assert out.message_type == MessageType.TASK_ASSIGNMENT
    payload = out.payload
    assert isinstance(payload, TaskAssignmentPayload)
    assert payload.title.startswith("Unblock:")
    assert _AUTO_ROUTED_MARKER in payload.description
    assert "DevOps" in payload.description or "devops" in payload.description
    # Same correlation chain — auditor follows one thread.
    assert out.correlation_id == msg.correlation_id


@pytest.mark.asyncio
async def test_routes_blocked_by_parsing_summary_when_blocked_on_missing() -> None:
    agent = TeamLeadAgent(llm=_StubLLM())
    msg = _blocked_report(
        blocked_on=None,
        summary="Frontend blocked: blocked: requires backend_developer (new API endpoint).",
    )

    outputs = await agent.handle(msg)

    assert len(outputs) == 1
    assert outputs[0].recipient == AgentId.BACKEND_DEVELOPER


@pytest.mark.asyncio
async def test_does_not_loop_when_summary_already_auto_routed() -> None:
    """Anti-loop: if a BLOCKED report itself originated from a prior
    auto-route, TL refuses to route a second time."""
    agent = TeamLeadAgent(llm=_StubLLM())
    msg = _blocked_report(
        blocked_on="backend_developer",
        summary=(
            f"Backend blocked: [{_AUTO_ROUTED_MARKER} from devops] cannot "
            "complete; needs Backend territory but tools are insufficient."
        ),
    )

    outputs = await agent.handle(msg)

    assert outputs == []


@pytest.mark.asyncio
async def test_ignores_blocked_with_no_target() -> None:
    """No blocked_on field and no parseable summary → no-op. Owner
    sees the BLOCKED in the digest."""
    agent = TeamLeadAgent(llm=_StubLLM())
    msg = _blocked_report(blocked_on=None, summary="DevOps blocked: unknown reason.")

    outputs = await agent.handle(msg)

    assert outputs == []


@pytest.mark.asyncio
async def test_ignores_blocked_with_unknown_target_role() -> None:
    """`blocked_on='someone_random'` AND unparseable summary → no-op.
    Owner sees in digest. (If blocked_on doesn't resolve but the summary
    *does* mention a valid role, that's covered by the summary-parsing
    fallback above.)"""
    agent = TeamLeadAgent(llm=_StubLLM())
    msg = _blocked_report(
        blocked_on="someone_random",
        summary="DevOps blocked: tooling issue, no clear owner.",
    )

    outputs = await agent.handle(msg)

    assert outputs == []


@pytest.mark.asyncio
async def test_ignores_blocked_targeting_team_lead_itself() -> None:
    """`blocked_on='team_lead'` → no-op. Self-routing would loop."""
    agent = TeamLeadAgent(llm=_StubLLM())
    msg = _blocked_report(blocked_on="team_lead")

    outputs = await agent.handle(msg)

    assert outputs == []


@pytest.mark.asyncio
async def test_skips_non_blocked_task_reports() -> None:
    """DONE / FAILED / IN_PROGRESS reports are not re-routed."""
    agent = TeamLeadAgent(llm=_StubLLM())
    msg = AgentMessage(
        correlation_id=uuid4(),
        sender=AgentId.BACKEND_DEVELOPER,
        recipient=AgentId.TEAM_LEAD,
        message_type=MessageType.TASK_REPORT,
        priority=Priority.P2,
        payload=TaskReportPayload(
            task_id=uuid4(),
            status=TaskStatus.DONE,
            progress_pct=100,
            summary="OK",
        ),
    )

    outputs = await agent.handle(msg)

    assert outputs == []
