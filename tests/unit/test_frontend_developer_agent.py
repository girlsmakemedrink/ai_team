"""Tests for FrontendDeveloperAgent — Sonnet, UI code under apps/web,apps/cli."""

from __future__ import annotations

import json
from uuid import uuid4

import pytest

from agents.frontend_developer import FrontendDeveloperAgent
from core.llm.base import LLMResponse, TokensUsage
from core.messaging.schemas import (
    AgentId,
    AgentMessage,
    MessageType,
    Priority,
    TaskAssignmentPayload,
    TaskReportPayload,
)


class _StubLLM:
    def __init__(self, response: LLMResponse) -> None:
        self._response = response

    async def invoke(self, **kwargs: object) -> LLMResponse:
        return self._response

    async def reset_session(self, session_id: str) -> None:
        return None


def _frontend_response(
    *,
    validation_step: str = "Ran `make test-unit`, 250 passed.",
    pr_url: str = "https://github.com/x/y/pull/11",
) -> LLMResponse:
    structured = {
        "target_files": ["apps/cli/main.py"],
        "changes": "Added a `--watch-since <ts>` flag to `ai-team watch`.",
        "rationale": "See docs/design/feed-keymap.md. Backend already filters server-side.",
        "validation_step": validation_step,
        "pr_url": pr_url,
        "branch": "agent/frontend/watch-since",
    }
    return LLMResponse(
        text=json.dumps(structured),
        structured=structured,
        tools_used=[],
        session_id="fe-sess",
        tokens=TokensUsage(input=70, output=130, model="claude-sonnet-4-6"),
        cost_estimate_cents=4,
        duration_ms=1300,
        validated_against_schema=True,
        raw={},
    )


def _task() -> AgentMessage:
    return AgentMessage(
        correlation_id=uuid4(),
        sender=AgentId.TEAM_LEAD,
        recipient=AgentId.FRONTEND_DEVELOPER,
        message_type=MessageType.TASK_ASSIGNMENT,
        priority=Priority.P3,
        payload=TaskAssignmentPayload(
            task_id=uuid4(),
            title="Wire --watch-since flag in the CLI",
            description="See docs/design/feed-keymap.md.",
        ),
    )


def test_role_and_tier() -> None:
    assert FrontendDeveloperAgent.role == AgentId.FRONTEND_DEVELOPER
    assert FrontendDeveloperAgent.model_tier == "sonnet"


def test_mcp_env_scopes_to_apps_web_and_cli() -> None:
    """Per ADR-004 Frontend row — apps/web + apps/cli for ai_team itself."""
    prefixes = FrontendDeveloperAgent.mcp_env["AI_TEAM_PATH_PREFIXES"]
    assert "apps/web" in prefixes
    assert "apps/cli" in prefixes


def test_allowed_tools_no_raw_bash_write() -> None:
    forbidden = {"Bash", "Write", "Edit", "MultiEdit"}
    assert not (set(FrontendDeveloperAgent.allowed_tools) & forbidden)


def test_schema_pins_branch_pattern() -> None:
    """Branch must match agent/frontend/<slug> to prevent role drift."""
    from agents.frontend_developer.agent import FRONTEND_REPORT_SCHEMA

    branch_schema = FRONTEND_REPORT_SCHEMA["properties"]["branch"]  # type: ignore[index]
    assert "agent/frontend/" in branch_schema["pattern"]  # type: ignore[index]


@pytest.mark.asyncio
async def test_handle_reports_done_with_pr_url() -> None:
    agent = FrontendDeveloperAgent(llm=_StubLLM(_frontend_response()))
    outputs = await agent.handle(_task())

    payload = outputs[0].payload
    assert isinstance(payload, TaskReportPayload)
    assert payload.status.value == "done"
    assert "pull/11" in payload.summary
    assert "Validation" in payload.summary
    assert payload.artifacts == ["apps/cli/main.py"]


@pytest.mark.asyncio
async def test_handle_marks_blocked_when_validation_says_blocked() -> None:
    """Frontend must escalate to TL when the ask requires Backend territory."""
    response = _frontend_response(
        validation_step="blocked: requires Backend (new API endpoint in apps/api/main.py)"
    )
    agent = FrontendDeveloperAgent(llm=_StubLLM(response))
    outputs = await agent.handle(_task())

    payload = outputs[0].payload
    assert isinstance(payload, TaskReportPayload)
    assert payload.status.value == "blocked"
    assert "requires Backend" in payload.summary


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
    agent = FrontendDeveloperAgent(llm=_StubLLM(bad))
    payload = (await agent.handle(_task()))[0].payload
    assert isinstance(payload, TaskReportPayload)
    assert payload.status.value == "failed"


@pytest.mark.asyncio
async def test_handle_skips_non_task_assignment() -> None:
    agent = FrontendDeveloperAgent(llm=_StubLLM(_frontend_response()))
    other = AgentMessage(
        correlation_id=uuid4(),
        sender=AgentId.TEAM_LEAD,
        recipient=AgentId.FRONTEND_DEVELOPER,
        message_type=MessageType.QUESTION,
        priority=Priority.P3,
        payload={"kind": "question", "question_id": str(uuid4()), "text": "hi"},
    )
    assert await agent.handle(other) == []
