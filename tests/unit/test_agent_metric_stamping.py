"""Pin: every agent subclass that overrides handle() stamps metadata['llm'].

Iter-4 demo report Failure 3: only TeamLeadAgent stamps per-turn LLM
metrics on its outputs; all 9 other subclasses override `handle()`
and skip the helper, so the demo's per-message SQL query returned
empty `metadata.llm` for every non-TL row. Iter-5 brings the other
subclasses to parity. This test pins it as a regression guard.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import uuid4

import pytest

from agents.architect import ArchitectAgent
from agents.backend_developer import BackendDeveloperAgent
from agents.designer import DesignerAgent
from agents.devops import DevOpsAgent
from agents.frontend_developer import FrontendDeveloperAgent
from agents.market_researcher import MarketResearcherAgent
from agents.product_manager import ProductManagerAgent
from agents.qa_engineer import QAEngineerAgent
from agents.sre_support import SRESupportAgent
from core.llm.base import LLMResponse, TokensUsage
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
    from collections.abc import Callable

    from agents._base import BaseAgent


class _StubLLM:
    """Returns a fixed LLMResponse for any invoke() call."""

    def __init__(self, response: LLMResponse) -> None:
        self._response = response

    async def invoke(self, **kwargs: Any) -> LLMResponse:
        del kwargs
        return self._response

    async def reset_session(self, session_id: str) -> None:
        return None


def _stub_response() -> LLMResponse:
    """Minimal valid LLMResponse — `structured` is irrelevant because we
    monkey-patch build_outputs to return a fixed output regardless."""
    return LLMResponse(
        text="",
        structured={"summary": "stub"},
        session_id="t",
        tokens=TokensUsage(input=7, output=42, cached_input=0, model="claude-sonnet-4-6"),
        cost_estimate_cents=3,
        duration_ms=123,
        validated_against_schema=True,
    )


def _make_output_factory(role: AgentId) -> Callable[..., list[AgentMessage]]:
    """Replace each agent's build_outputs with one that returns a single
    no-metrics output. handle() must wrap it in _stamp_metrics, otherwise
    metadata['llm'] stays absent."""

    def _factory(
        self: BaseAgent, response: LLMResponse, incoming: AgentMessage
    ) -> list[AgentMessage]:
        del self, response
        return [
            AgentMessage(
                correlation_id=incoming.correlation_id,
                sender=role,
                recipient=AgentId.TEAM_LEAD,
                message_type=MessageType.TASK_REPORT,
                priority=Priority.P3,
                payload=TaskReportPayload(
                    task_id=incoming.payload.task_id
                    if isinstance(incoming.payload, TaskAssignmentPayload)
                    else uuid4(),
                    status=TaskStatus.DONE,
                    progress_pct=100,
                    summary="stub output",
                ),
                # IMPORTANT: no 'llm' key — handle() is responsible for stamping it.
                metadata={},
            )
        ]

    return _factory


def _incoming_assignment(recipient: AgentId) -> AgentMessage:
    return AgentMessage(
        correlation_id=uuid4(),
        sender=AgentId.TEAM_LEAD,
        recipient=recipient,
        message_type=MessageType.TASK_ASSIGNMENT,
        priority=Priority.P2,
        payload=TaskAssignmentPayload(
            task_id=uuid4(),
            title="t",
            description="d",
        ),
    )


_OVERRIDING_AGENTS = [
    ProductManagerAgent,
    ArchitectAgent,
    BackendDeveloperAgent,
    DesignerAgent,
    FrontendDeveloperAgent,
    QAEngineerAgent,
    DevOpsAgent,
    SRESupportAgent,
    MarketResearcherAgent,
]


@pytest.mark.parametrize("agent_cls", _OVERRIDING_AGENTS)
@pytest.mark.asyncio
async def test_handle_stamps_llm_metrics(
    agent_cls: type[BaseAgent], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every agent that overrides handle() must wrap build_outputs in
    self._stamp_metrics(...). The dispatcher's per-message SQL query
    pulls metrics out of `metadata['llm']` on the AgentMessage envelope
    — if any agent skips the stamping, the demo report has a gap."""
    response = _stub_response()
    monkeypatch.setattr(agent_cls, "build_outputs", _make_output_factory(agent_cls.role))

    agent = agent_cls(llm=_StubLLM(response))
    incoming = _incoming_assignment(agent_cls.role)

    outputs = await agent.handle(incoming)

    assert outputs, f"{agent_cls.__name__}.handle() returned no outputs"
    for out in outputs:
        llm = out.metadata.get("llm")
        assert llm is not None, (
            f"{agent_cls.__name__} returned an output without metadata['llm'] "
            f"— handle() must wrap build_outputs in _stamp_metrics(...)"
        )
        # Spot-check the stamped fields match the response.
        assert llm.get("tokens_in") == response.tokens.input
        assert llm.get("tokens_out") == response.tokens.output
        assert llm.get("cost_cents") == response.cost_estimate_cents
        assert llm.get("duration_ms") == response.duration_ms
        assert llm.get("model") == response.tokens.model
        assert llm.get("validated_against_schema") is True
