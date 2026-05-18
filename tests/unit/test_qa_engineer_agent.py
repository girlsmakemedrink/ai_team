"""Tests for QAEngineerAgent — Sonnet, runs tests, reports back to TL."""

from __future__ import annotations

import json
from uuid import uuid4

import pytest

from agents.qa_engineer import QAEngineerAgent
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


def _qa_response(
    *,
    suite_passed: bool = True,
    coverage_pct: float = 87.5,
    failures: list[str] | None = None,
) -> LLMResponse:
    structured = {
        "suite_passed": suite_passed,
        "tests_run": 42,
        "tests_failed": 0 if suite_passed else len(failures or ["x"]),
        "coverage_pct": coverage_pct,
        "failures": failures or [],
        "summary": (
            "All tests pass with 87.5% coverage."
            if suite_passed
            else f"{len(failures or [])} test(s) failed"
        ),
    }
    return LLMResponse(
        text=json.dumps(structured),
        structured=structured,
        tools_used=[],
        session_id="qa-sess",
        tokens=TokensUsage(input=80, output=100, model="claude-sonnet-4-6"),
        cost_estimate_cents=4,
        duration_ms=1500,
        validated_against_schema=True,
        raw={},
    )


def _task_assignment() -> AgentMessage:
    return AgentMessage(
        correlation_id=uuid4(),
        sender=AgentId.TEAM_LEAD,
        recipient=AgentId.QA_ENGINEER,
        message_type=MessageType.TASK_ASSIGNMENT,
        priority=Priority.P2,
        payload=TaskAssignmentPayload(
            task_id=uuid4(),
            title="Run QA on idea-validator PR",
            description="Run the full test suite at HEAD and report.",
            target_repo="examples/sandbox/idea-validator",
        ),
    )


def test_role_and_model_tier() -> None:
    assert QAEngineerAgent.role == AgentId.QA_ENGINEER
    assert QAEngineerAgent.model_tier == "sonnet"


def test_allowed_tools_no_raw_bash_or_write() -> None:
    forbidden = {"Bash", "Write", "Edit", "MultiEdit"}
    overlap = set(QAEngineerAgent.allowed_tools) & forbidden
    assert not overlap


def test_mcp_env_scopes_to_tests_dir() -> None:
    """QA only writes to tests/ (regression cases). Enforced at MCP spawn."""
    assert QAEngineerAgent.mcp_env["AI_TEAM_PATH_PREFIXES"] == "tests/"


def test_allowed_tools_includes_run_shell() -> None:
    """QA's whole job is running tests — must have run_shell."""
    assert "mcp__ai_team_repo__run_shell" in QAEngineerAgent.allowed_tools


@pytest.mark.asyncio
async def test_handle_reports_done_when_suite_passes() -> None:
    agent = QAEngineerAgent(llm=_StubLLM(_qa_response()))
    outputs = await agent.handle(_task_assignment())

    assert len(outputs) == 1
    payload = outputs[0].payload
    assert isinstance(payload, TaskReportPayload)
    assert payload.status.value == "done"
    assert "87.5" in payload.summary  # coverage figure surfaced
    assert outputs[0].recipient == AgentId.TEAM_LEAD


@pytest.mark.asyncio
async def test_handle_reports_failed_when_suite_fails() -> None:
    failing = _qa_response(
        suite_passed=False,
        coverage_pct=72.0,
        failures=["test_pipeline.py::test_score_within_1_to_10"],
    )
    agent = QAEngineerAgent(llm=_StubLLM(failing))
    outputs = await agent.handle(_task_assignment())

    payload = outputs[0].payload
    assert isinstance(payload, TaskReportPayload)
    assert payload.status.value == "failed"
    assert "test_score_within_1_to_10" in payload.summary


@pytest.mark.asyncio
async def test_handle_reports_failed_on_missing_structured() -> None:
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
    agent = QAEngineerAgent(llm=_StubLLM(bad))
    outputs = await agent.handle(_task_assignment())
    payload = outputs[0].payload
    assert isinstance(payload, TaskReportPayload)
    assert payload.status.value == "failed"


@pytest.mark.asyncio
async def test_handle_skips_non_task_assignment() -> None:
    agent = QAEngineerAgent(llm=_StubLLM(_qa_response()))
    other = AgentMessage(
        correlation_id=uuid4(),
        sender=AgentId.TEAM_LEAD,
        recipient=AgentId.QA_ENGINEER,
        message_type=MessageType.QUESTION,
        priority=Priority.P3,
        payload={"kind": "question", "question_id": str(uuid4()), "text": "hi"},
    )
    assert await agent.handle(other) == []
