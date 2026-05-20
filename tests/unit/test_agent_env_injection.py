"""iter-19 Phase 1: per-message env injection in
BaseAgent + PM + TL.

Asserts every concrete agent's invocation path passes
an env dict containing AI_TEAM_AGENT_ROLE +
AI_TEAM_CORRELATION_ID + AI_TEAM_TASK_ID to
LLMClient.invoke. Defense-in-depth for the MCP
server's Context.from_env fallback when the LLM
forgets to pass these fields in tool args. See
iter_18_demo_report.md Caveat 2.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar
from uuid import uuid4

from agents._base import BaseAgent
from agents.product_manager import ProductManagerAgent
from agents.team_lead import TeamLeadAgent
from core.llm.base import LLMResponse, TokensUsage
from core.messaging.schemas import (
    AgentId,
    AgentMessage,
    MessageType,
    Priority,
    TaskAssignmentPayload,
)

if TYPE_CHECKING:
    pass


class _RecordingLLM:
    """LLMClient that records the last invoke kwargs.

    Returns a minimal valid LLMResponse so build_outputs
    doesn't crash. Captures `env` so the test can
    assert on it.
    """

    def __init__(self) -> None:
        self.last_kwargs: dict[str, Any] | None = None

    async def invoke(self, **kwargs: Any) -> LLMResponse:
        self.last_kwargs = kwargs
        return LLMResponse(
            text="",
            structured={"summary": "x", "subtasks": []},
            session_id="s",
            tokens=TokensUsage(input=0, output=0, model="claude-sonnet-4-6"),
            duration_ms=0,
        )

    async def reset_session(self, session_id: str) -> None:
        del session_id


class _DummyAgent(BaseAgent):
    role: ClassVar[AgentId] = AgentId.QA_ENGINEER
    system_prompt_path: ClassVar[Path] = Path("/dev/null")
    allowed_tools: ClassVar[tuple[str, ...]] = ("Read",)

    def build_outputs(
        self, response: LLMResponse, incoming: AgentMessage
    ) -> list[AgentMessage]:
        del response, incoming
        return []


def _make_assignment(recipient: AgentId = AgentId.QA_ENGINEER) -> AgentMessage:
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


def test_base_agent_injects_per_message_env(tmp_path: Path) -> None:
    """Default BaseAgent.handle() (via _invoke_with_retries)
    must pass an env dict carrying AI_TEAM_AGENT_ROLE,
    AI_TEAM_CORRELATION_ID, and AI_TEAM_TASK_ID."""
    prompt = tmp_path / "p.md"
    prompt.write_text("stub")
    _DummyAgent.system_prompt_path = prompt
    llm = _RecordingLLM()
    agent = _DummyAgent(llm=llm)
    msg = _make_assignment()

    asyncio.run(agent.handle(msg))

    assert llm.last_kwargs is not None
    env = llm.last_kwargs["env"]
    assert env is not None, "env was None — per-message injection not wired"
    assert env["AI_TEAM_AGENT_ROLE"] == "qa_engineer"
    assert env["AI_TEAM_CORRELATION_ID"] == str(msg.correlation_id)
    assert isinstance(msg.payload, TaskAssignmentPayload)
    assert env["AI_TEAM_TASK_ID"] == str(msg.payload.task_id)


def test_product_manager_injects_per_message_env() -> None:
    """PM has a custom handle() that bypasses
    _invoke_with_retries — it must still inject
    per-message env. Reads the real prompts/
    product_manager.md from disk; do NOT monkey-patch
    system_prompt_path because it's a ClassVar and
    leaks across tests (caught in iter-19 Phase 1)."""
    llm = _RecordingLLM()
    agent = ProductManagerAgent(llm=llm)
    msg = _make_assignment(recipient=AgentId.PRODUCT_MANAGER)

    asyncio.run(agent.handle(msg))

    assert llm.last_kwargs is not None
    env = llm.last_kwargs["env"]
    assert env is not None, "PM.handle did not pass env"
    assert env["AI_TEAM_AGENT_ROLE"] == "product_manager"
    assert env["AI_TEAM_CORRELATION_ID"] == str(msg.correlation_id)
    assert isinstance(msg.payload, TaskAssignmentPayload)
    assert env["AI_TEAM_TASK_ID"] == str(msg.payload.task_id)


def test_team_lead_injects_per_message_env() -> None:
    """TL has a custom handle() — same contract as PM.
    Reads the real prompts/team_lead.md from disk; do
    NOT monkey-patch system_prompt_path (ClassVar
    leaks across tests)."""
    llm = _RecordingLLM()
    agent = TeamLeadAgent(llm=llm)
    msg = _make_assignment(recipient=AgentId.TEAM_LEAD)

    asyncio.run(agent.handle(msg))

    assert llm.last_kwargs is not None
    env = llm.last_kwargs["env"]
    assert env is not None, "TL.handle did not pass env"
    assert env["AI_TEAM_AGENT_ROLE"] == "team_lead"
    assert env["AI_TEAM_CORRELATION_ID"] == str(msg.correlation_id)
    assert isinstance(msg.payload, TaskAssignmentPayload)
    assert env["AI_TEAM_TASK_ID"] == str(msg.payload.task_id)
