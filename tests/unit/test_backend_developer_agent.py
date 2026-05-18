"""Tests for BackendDeveloperAgent — Sonnet, code + tests + PR.

The agent's Python side is thin: it invokes claude -p with the right
system prompt, allowed_tools (MCP-only, no raw Bash/Write), and a
JSON-schema for the structured task_report. The actual code-writing,
test-running, branch-creating, and PR-opening happens *inside the LLM
turn*, via the `mcp__ai_team_repo__*` tools — those are exercised in
end-to-end demo, not here. Unit tests pin: agent identity, allowed
tools, structured-response unpacking, failure paths.
"""

from __future__ import annotations

import json
from uuid import uuid4

import pytest

from agents.backend_developer import BackendDeveloperAgent
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
        self.calls: list[dict[str, object]] = []

    async def invoke(self, **kwargs: object) -> LLMResponse:
        self.calls.append(kwargs)
        return self._response

    async def reset_session(self, session_id: str) -> None:
        return None


def _backend_response(
    *,
    pr_url: str = "https://github.com/x/y/pull/42",
    tests_passed: bool = True,
) -> LLMResponse:
    structured = {
        "branch": "agent/backend_developer/iter2-idea-validator",
        "summary": "Implemented idea-validator pipeline with tests.",
        "files_written": [
            "examples/sandbox/idea-validator/src/pipeline.py",
            "examples/sandbox/idea-validator/tests/test_pipeline.py",
        ],
        "tests_passed": tests_passed,
        "pr_url": pr_url,
    }
    return LLMResponse(
        text=json.dumps(structured),
        structured=structured,
        tools_used=[],
        session_id="be-sess",
        tokens=TokensUsage(input=100, output=200, model="claude-sonnet-4-6"),
        cost_estimate_cents=15,
        duration_ms=2000,
        validated_against_schema=True,
        raw={},
    )


def _task_assignment() -> AgentMessage:
    return AgentMessage(
        correlation_id=uuid4(),
        sender=AgentId.TEAM_LEAD,
        recipient=AgentId.BACKEND_DEVELOPER,
        message_type=MessageType.TASK_ASSIGNMENT,
        priority=Priority.P2,
        payload=TaskAssignmentPayload(
            task_id=uuid4(),
            title="Implement idea-validator pipeline",
            description="See ADR-0010 and docs/sandbox/idea_validator_spec.md.",
            target_repo="examples/sandbox/idea-validator",
        ),
    )


def test_role_and_model_tier() -> None:
    assert BackendDeveloperAgent.role == AgentId.BACKEND_DEVELOPER
    assert BackendDeveloperAgent.model_tier == "sonnet"


def test_allowed_tools_excludes_raw_bash_write_edit() -> None:
    """ADR-004: Backend gets MCP tools only; raw Bash / Write / Edit are forbidden."""
    forbidden = {"Bash", "Write", "Edit", "MultiEdit"}
    overlap = set(BackendDeveloperAgent.allowed_tools) & forbidden
    assert not overlap, f"Backend must not have raw {overlap} access"


def test_allowed_tools_includes_mcp_repo_surface() -> None:
    """Backend's whole point is having the MCP repo tools."""
    needed = {
        "mcp__ai_team_repo__create_branch",
        "mcp__ai_team_repo__write_file_in_scope",
        "mcp__ai_team_repo__run_shell",
        "mcp__ai_team_repo__open_pr",
    }
    missing = needed - set(BackendDeveloperAgent.allowed_tools)
    assert not missing, f"Backend allowlist is missing {missing}"


@pytest.mark.asyncio
async def test_handle_reports_done_with_pr_url_on_success() -> None:
    agent = BackendDeveloperAgent(llm=_StubLLM(_backend_response()))
    outputs = await agent.handle(_task_assignment())

    assert len(outputs) == 1
    report = outputs[0]
    assert report.sender == AgentId.BACKEND_DEVELOPER
    assert report.recipient == AgentId.TEAM_LEAD
    assert report.message_type == MessageType.TASK_REPORT
    payload = report.payload
    assert isinstance(payload, TaskReportPayload)
    assert payload.status.value == "done"
    assert "https://github.com/x/y/pull/42" in payload.summary
    assert payload.artifacts == [
        "examples/sandbox/idea-validator/src/pipeline.py",
        "examples/sandbox/idea-validator/tests/test_pipeline.py",
    ]


@pytest.mark.asyncio
async def test_handle_reports_failed_when_tests_did_not_pass() -> None:
    agent = BackendDeveloperAgent(llm=_StubLLM(_backend_response(tests_passed=False)))
    outputs = await agent.handle(_task_assignment())

    payload = outputs[0].payload
    assert isinstance(payload, TaskReportPayload)
    assert payload.status.value == "failed"
    assert "tests failed" in payload.summary.lower()


@pytest.mark.asyncio
async def test_handle_reports_failed_on_missing_structured_output() -> None:
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
    agent = BackendDeveloperAgent(llm=_StubLLM(bad))
    outputs = await agent.handle(_task_assignment())

    payload = outputs[0].payload
    assert isinstance(payload, TaskReportPayload)
    assert payload.status.value == "failed"


@pytest.mark.asyncio
async def test_handle_skips_non_task_assignment() -> None:
    agent = BackendDeveloperAgent(llm=_StubLLM(_backend_response()))
    other = AgentMessage(
        correlation_id=uuid4(),
        sender=AgentId.TEAM_LEAD,
        recipient=AgentId.BACKEND_DEVELOPER,
        message_type=MessageType.QUESTION,
        priority=Priority.P3,
        payload={"kind": "question", "question_id": str(uuid4()), "text": "hi"},
    )
    assert await agent.handle(other) == []
