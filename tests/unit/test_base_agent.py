"""Unit tests for BaseAgent default helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import ClassVar
from uuid import uuid4

import pytest

from agents._base import BaseAgent
from core.llm.base import LLMResponse  # noqa: TC001  used in ClassVar signature
from core.llm.mock import MockLLMClient
from core.messaging.schemas import (
    AgentId,
    AgentMessage,
    MessageType,
    Priority,
    TaskAssignmentPayload,
    TaskReportPayload,
    TaskStatus,
)


class _DummyAgent(BaseAgent):
    role: ClassVar[AgentId] = AgentId.PRODUCT_MANAGER
    system_prompt_path: ClassVar[Path] = Path("/dev/null")  # overridden in fixture

    def build_outputs(self, response: LLMResponse, incoming: AgentMessage) -> list[AgentMessage]:
        return []


@pytest.fixture
def dummy_agent(tmp_path: Path) -> _DummyAgent:
    prompt_path = tmp_path / "p.md"
    prompt_path.write_text("# Test prompt")
    _DummyAgent.system_prompt_path = prompt_path
    return _DummyAgent(llm=MockLLMClient(tmp_path, strict=False))


def _make_msg() -> AgentMessage:
    return AgentMessage(
        correlation_id=uuid4(),
        sender=AgentId.USER,
        recipient=AgentId.PRODUCT_MANAGER,
        message_type=MessageType.TASK_ASSIGNMENT,
        priority=Priority.P2,
        payload=TaskAssignmentPayload(
            task_id=uuid4(),
            title="title",
            description="desc",
        ),
    )


def test_system_prompt_is_cached(dummy_agent: _DummyAgent) -> None:
    p1 = dummy_agent.system_prompt()
    p2 = dummy_agent.system_prompt()
    assert p1 == p2
    assert "Test prompt" in p1


def test_user_message_wraps_untrusted(dummy_agent: _DummyAgent) -> None:
    msg = _make_msg()
    rendered = dummy_agent._user_message_for(msg)
    assert "<UNTRUSTED_INPUT>" in rendered
    assert "</UNTRUSTED_INPUT>" in rendered
    # Payload fields appear inside the marker (JSON-encoded).
    assert "task_assignment" in rendered
    # Sanitiser inserts a zero-width space inside any literal close-tag,
    # so the inner content shouldn't terminate the marker prematurely.
    inner = rendered.split("<UNTRUSTED_INPUT>")[1].split("</UNTRUSTED_INPUT>")[0]
    assert "</UNTRUSTED_INPUT>" not in inner


def test_default_handle_calls_llm(dummy_agent: _DummyAgent) -> None:
    # MockLLMClient is lenient → returns placeholder; build_outputs returns [].
    import asyncio

    msg = _make_msg()
    out = asyncio.run(dummy_agent.handle(msg))
    assert out == []
    assert dummy_agent._llm.calls  # type: ignore[attr-defined]


def test_user_message_for_task_report_serializes() -> None:
    """Reports also encode cleanly (the JSON dump never crashes on enums)."""
    msg = AgentMessage(
        correlation_id=uuid4(),
        sender=AgentId.PRODUCT_MANAGER,
        recipient=AgentId.TEAM_LEAD,
        message_type=MessageType.TASK_REPORT,
        priority=Priority.P3,
        payload=TaskReportPayload(
            task_id=uuid4(),
            status=TaskStatus.DONE,
            progress_pct=100,
            summary="done",
        ),
    )

    class _NoOpAgent(BaseAgent):
        role: ClassVar[AgentId] = AgentId.PRODUCT_MANAGER
        system_prompt_path: ClassVar[Path] = Path("/dev/null")

        def build_outputs(
            self, response: LLMResponse, incoming: AgentMessage
        ) -> list[AgentMessage]:
            return []

    agent = _NoOpAgent(llm=MockLLMClient(Path("/tmp"), strict=False))
    rendered = agent._user_message_for(msg)
    assert "task_report" in rendered
    # The JSON inside is parseable when extracted.
    inner = rendered.split("<UNTRUSTED_INPUT>")[1].split("</UNTRUSTED_INPUT>")[0]
    assert json.loads(inner)["kind"] == "task_report"
