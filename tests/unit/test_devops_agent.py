"""Tests for DevOpsAgent — Sonnet, CI/infra patches."""

from __future__ import annotations

import json
from uuid import uuid4

import pytest

from agents.devops import DevOpsAgent
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


def _devops_response(
    *,
    validation_step: str = "Ran `make test-unit`, 222 passed.",
    pr_url: str = "https://github.com/x/y/pull/9",
) -> LLMResponse:
    structured = {
        "target_files": [".github/workflows/ci.yml"],
        "changes": "Added a nightly cron job that runs `make smoke-llm`.",
        "rationale": "Iter-2 retro action: catch substrate regressions before iter-N starts.",
        "validation_step": validation_step,
        "pr_url": pr_url,
        "branch": "agent/devops/nightly-smoke",
    }
    return LLMResponse(
        text=json.dumps(structured),
        structured=structured,
        tools_used=[],
        session_id="ops-sess",
        tokens=TokensUsage(input=70, output=120, model="claude-sonnet-4-6"),
        cost_estimate_cents=4,
        duration_ms=1200,
        validated_against_schema=True,
        raw={},
    )


def _task() -> AgentMessage:
    return AgentMessage(
        correlation_id=uuid4(),
        sender=AgentId.TEAM_LEAD,
        recipient=AgentId.DEVOPS,
        message_type=MessageType.TASK_ASSIGNMENT,
        priority=Priority.P3,
        payload=TaskAssignmentPayload(
            task_id=uuid4(),
            title="Add nightly smoke-llm CI step",
            description="See docs/iterations/iter_2_retro.md.",
        ),
    )


def test_role_and_tier() -> None:
    assert DevOpsAgent.role == AgentId.DEVOPS
    assert DevOpsAgent.model_tier == "sonnet"


def test_mcp_env_scopes_to_infra_workflows_makefile() -> None:
    """Per ADR-004 DevOps row."""
    prefixes = DevOpsAgent.mcp_env["AI_TEAM_PATH_PREFIXES"]
    for needed in ("infra", ".github/workflows", "Makefile", "docker-compose.yml", "scripts"):
        assert needed in prefixes, f"{needed!r} missing from {prefixes!r}"


def test_allowed_tools_no_raw_bash() -> None:
    forbidden = {"Bash", "Write", "Edit", "MultiEdit"}
    assert not (set(DevOpsAgent.allowed_tools) & forbidden)


@pytest.mark.asyncio
async def test_handle_reports_done_with_pr_url() -> None:
    agent = DevOpsAgent(llm=_StubLLM(_devops_response()))
    outputs = await agent.handle(_task())

    payload = outputs[0].payload
    assert isinstance(payload, TaskReportPayload)
    assert payload.status.value == "done"
    assert "pull/9" in payload.summary
    assert "Validation" in payload.summary
    assert payload.artifacts == [".github/workflows/ci.yml"]


@pytest.mark.asyncio
async def test_handle_marks_blocked_when_validation_says_blocked() -> None:
    """DevOps must escalate to TL when the ask requires Backend territory.

    Phase 4: the parsed role lands on TaskReportPayload.blocked_on so TL
    can auto-route without re-parsing summary text.
    """
    response = _devops_response(
        validation_step="blocked: requires backend_developer (agents/foo/bar.py change)"
    )
    agent = DevOpsAgent(llm=_StubLLM(response))
    outputs = await agent.handle(_task())
    payload = outputs[0].payload
    assert isinstance(payload, TaskReportPayload)
    assert payload.status.value == "blocked"
    assert "requires backend_developer" in payload.summary
    assert payload.blocked_on == "backend_developer"


@pytest.mark.asyncio
async def test_handle_blocked_with_unparseable_role_sets_blocked_on_none() -> None:
    """If the validation_step is generic 'blocked: <reason>' with no
    parseable role, blocked_on stays None and TL leaves it for the owner.
    """
    response = _devops_response(
        validation_step="blocked: docker daemon unreachable, no clear owner"
    )
    agent = DevOpsAgent(llm=_StubLLM(response))
    outputs = await agent.handle(_task())
    payload = outputs[0].payload
    assert isinstance(payload, TaskReportPayload)
    assert payload.status.value == "blocked"
    assert payload.blocked_on is None


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
    agent = DevOpsAgent(llm=_StubLLM(bad))
    payload = (await agent.handle(_task()))[0].payload
    assert isinstance(payload, TaskReportPayload)
    assert payload.status.value == "failed"


@pytest.mark.asyncio
async def test_handle_skips_non_task_assignment() -> None:
    agent = DevOpsAgent(llm=_StubLLM(_devops_response()))
    other = AgentMessage(
        correlation_id=uuid4(),
        sender=AgentId.TEAM_LEAD,
        recipient=AgentId.DEVOPS,
        message_type=MessageType.QUESTION,
        priority=Priority.P3,
        payload={"kind": "question", "question_id": str(uuid4()), "text": "hi"},
    )
    assert await agent.handle(other) == []
