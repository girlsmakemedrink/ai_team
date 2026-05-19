"""Unit tests for BaseAgent default helpers."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, ClassVar
from uuid import uuid4

import pytest

from agents._base import BaseAgent
from core.llm.base import LLMResponse, TokensUsage
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


# === iter-3 Phase 4: per-message LLM metrics stamped on metadata["llm"] ===


class _StubLLMResponseClient:
    """Returns a fixed LLMResponse from .invoke; ignores all kwargs."""

    def __init__(self, response: LLMResponse) -> None:
        self._response = response

    async def invoke(self, **kwargs: Any) -> LLMResponse:
        del kwargs
        return self._response

    async def reset_session(self, session_id: str) -> None:
        del session_id


class _EchoingAgent(BaseAgent):
    """Returns a single TASK_REPORT(DONE) for every incoming TASK_ASSIGNMENT."""

    role: ClassVar[AgentId] = AgentId.BACKEND_DEVELOPER
    system_prompt_path: ClassVar[Path] = Path("/dev/null")

    def build_outputs(self, response: LLMResponse, incoming: AgentMessage) -> list[AgentMessage]:
        del response
        if not isinstance(incoming.payload, TaskAssignmentPayload):
            return []
        return [
            AgentMessage(
                correlation_id=incoming.correlation_id,
                sender=self.role,
                recipient=AgentId.TEAM_LEAD,
                message_type=MessageType.TASK_REPORT,
                priority=Priority.P3,
                payload=TaskReportPayload(
                    task_id=incoming.payload.task_id,
                    status=TaskStatus.DONE,
                    progress_pct=100,
                    summary="ok",
                ),
                metadata={"existing_key": "preserved"},
            )
        ]


def _make_assignment() -> AgentMessage:
    return AgentMessage(
        correlation_id=uuid4(),
        sender=AgentId.TEAM_LEAD,
        recipient=AgentId.BACKEND_DEVELOPER,
        message_type=MessageType.TASK_ASSIGNMENT,
        priority=Priority.P2,
        payload=TaskAssignmentPayload(
            task_id=uuid4(),
            title="t",
            description="d",
        ),
    )


def _make_response(*, validated: bool = True) -> LLMResponse:
    return LLMResponse(
        text="",
        structured={"ok": True},
        session_id="s",
        tokens=TokensUsage(input=123, output=456, cached_input=78, model="claude-sonnet-4-6"),
        cost_estimate_cents=42,
        duration_ms=999,
        validated_against_schema=validated,
    )


def test_handle_stamps_llm_metrics_on_metadata(tmp_path: Path) -> None:
    _EchoingAgent.system_prompt_path = tmp_path / "p.md"
    _EchoingAgent.system_prompt_path.write_text("# Role: Backend Developer\nstub")

    response = _make_response()
    agent = _EchoingAgent(llm=_StubLLMResponseClient(response))

    outputs = asyncio.run(agent.handle(_make_assignment()))
    assert len(outputs) == 1
    out = outputs[0]

    llm_meta = out.metadata.get("llm")
    assert isinstance(llm_meta, dict), f"metadata['llm'] missing or wrong type: {out.metadata}"
    assert llm_meta["tokens_in"] == 123
    assert llm_meta["tokens_out"] == 456
    assert llm_meta["cached_input"] == 78
    assert llm_meta["cost_cents"] == 42
    assert llm_meta["duration_ms"] == 999
    assert llm_meta["model"] == "claude-sonnet-4-6"
    assert llm_meta["validated_against_schema"] is True


def test_handle_preserves_existing_metadata_when_stamping(tmp_path: Path) -> None:
    _EchoingAgent.system_prompt_path = tmp_path / "p.md"
    _EchoingAgent.system_prompt_path.write_text("# Role: Backend Developer\nstub")

    agent = _EchoingAgent(llm=_StubLLMResponseClient(_make_response()))
    outputs = asyncio.run(agent.handle(_make_assignment()))
    assert outputs[0].metadata.get("existing_key") == "preserved"


def test_handle_records_validated_false_when_schema_failed(tmp_path: Path) -> None:
    _EchoingAgent.system_prompt_path = tmp_path / "p.md"
    _EchoingAgent.system_prompt_path.write_text("# Role: Backend Developer\nstub")

    agent = _EchoingAgent(llm=_StubLLMResponseClient(_make_response(validated=False)))
    outputs = asyncio.run(agent.handle(_make_assignment()))
    llm_meta = outputs[0].metadata.get("llm")
    assert isinstance(llm_meta, dict)
    assert llm_meta["validated_against_schema"] is False
