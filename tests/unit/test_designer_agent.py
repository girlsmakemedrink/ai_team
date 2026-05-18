"""Tests for DesignerAgent — Sonnet, design notes to docs/design/."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest

from agents.designer import DesignerAgent
from core.llm.base import LLMResponse, TokensUsage
from core.messaging.schemas import (
    AgentId,
    AgentMessage,
    MessageType,
    Priority,
    TaskAssignmentPayload,
    TaskReportPayload,
)

if TYPE_CHECKING:
    from pathlib import Path


class _StubLLM:
    def __init__(self, response: LLMResponse) -> None:
        self._response = response

    async def invoke(self, **kwargs: object) -> LLMResponse:
        return self._response

    async def reset_session(self, session_id: str) -> None:
        return None


def _design_response(*, slug: str = "feed-keymap") -> LLMResponse:
    structured = {
        "title": "Feed keymap",
        "slug": slug,
        "summary": "Two-key chord nav for the ai-team CLI feed.",
        "layout": "j/k → up/down, p → pause, r → resume, q → quit",
        "decisions": [
            {
                "name": "chord vs single key",
                "choice": "single key",
                "rationale": "feed is a narrow surface; no risk of conflict.",
            }
        ],
        "links": ["docs/sandbox/feed_spec.md"],
    }
    return LLMResponse(
        text=json.dumps(structured),
        structured=structured,
        tools_used=[],
        session_id="d-sess",
        tokens=TokensUsage(input=50, output=80, model="claude-sonnet-4-6"),
        cost_estimate_cents=2,
        duration_ms=500,
        validated_against_schema=True,
        raw={},
    )


def _task() -> AgentMessage:
    return AgentMessage(
        correlation_id=uuid4(),
        sender=AgentId.TEAM_LEAD,
        recipient=AgentId.DESIGNER,
        message_type=MessageType.TASK_ASSIGNMENT,
        priority=Priority.P3,
        payload=TaskAssignmentPayload(
            task_id=uuid4(),
            title="Design the feed keymap",
            description="See docs/sandbox/feed_spec.md.",
        ),
    )


def test_role_and_tier() -> None:
    assert DesignerAgent.role == AgentId.DESIGNER
    assert DesignerAgent.model_tier == "sonnet"


def test_mcp_env_scopes_to_design_dir() -> None:
    assert DesignerAgent.mcp_env["AI_TEAM_PATH_PREFIXES"] == "docs/design"


def test_allowed_tools_no_raw_bash_write() -> None:
    forbidden = {"Bash", "Write", "Edit", "MultiEdit"}
    assert not (set(DesignerAgent.allowed_tools) & forbidden)


@pytest.mark.asyncio
async def test_handle_writes_design_md_and_reports_to_tl(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    design_dir = tmp_path / "docs" / "design"
    monkeypatch.setattr("agents.designer.agent._DESIGN_DIR", design_dir)

    agent = DesignerAgent(llm=_StubLLM(_design_response()))
    outputs = await agent.handle(_task())

    assert len(outputs) == 1
    report = outputs[0]
    assert report.recipient == AgentId.TEAM_LEAD
    payload = report.payload
    assert isinstance(payload, TaskReportPayload)
    assert payload.status.value == "done"
    assert payload.artifacts == ["docs/design/feed-keymap.md"]

    written = (design_dir / "feed-keymap.md").read_text()
    assert "Design — Feed keymap" in written
    assert "j/k → up/down" in written
    assert "single key" in written
    assert "docs/sandbox/feed_spec.md" in written


@pytest.mark.asyncio
async def test_handle_rejects_invalid_slug(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("agents.designer.agent._DESIGN_DIR", tmp_path / "docs" / "design")
    agent = DesignerAgent(llm=_StubLLM(_design_response(slug="Bad Slug")))
    outputs = await agent.handle(_task())
    payload = outputs[0].payload
    assert isinstance(payload, TaskReportPayload)
    assert payload.status.value == "failed"


@pytest.mark.asyncio
async def test_handle_fails_on_missing_structured() -> None:
    bad = LLMResponse(
        text="model wandered",
        structured=None,
        tools_used=[],
        session_id="x",
        tokens=TokensUsage(input=1, output=1, model="claude-sonnet-4-6"),
        cost_estimate_cents=0,
        duration_ms=1,
        validated_against_schema=False,
        raw={},
    )
    agent = DesignerAgent(llm=_StubLLM(bad))
    outputs = await agent.handle(_task())
    payload = outputs[0].payload
    assert isinstance(payload, TaskReportPayload)
    assert payload.status.value == "failed"


@pytest.mark.asyncio
async def test_handle_skips_non_task_assignment() -> None:
    agent = DesignerAgent(llm=_StubLLM(_design_response()))
    other = AgentMessage(
        correlation_id=uuid4(),
        sender=AgentId.TEAM_LEAD,
        recipient=AgentId.DESIGNER,
        message_type=MessageType.QUESTION,
        priority=Priority.P3,
        payload={"kind": "question", "question_id": str(uuid4()), "text": "hi"},
    )
    assert await agent.handle(other) == []
