"""Tests for SRESupportAgent — Sonnet, runbooks to docs/runbooks/."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest

from agents.sre_support import SRESupportAgent
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


def _sre_response(
    *,
    slug: str = "quota-exhausted",
    kind: str = "runbook",
) -> LLMResponse:
    structured = {
        "title": "Dispatcher reports quota_exhausted",
        "slug": slug,
        "kind": kind,
        "summary": (
            "claude -p returns the quota-exhausted error; "
            "dispatcher refuses new tasks until quota rolls over."
        ),
        "steps": (
            "1. Confirm via `ai-team digest` that the dispatcher state is "
            "`quota_exhausted`.\n"
            "2. Wait for monthly quota reset (UTC start of next month).\n"
            "3. Dispatcher auto-resumes on the next message."
        ),
        "metrics": ["docs/adr/0008-llm-access-strategy.md"],
        "severity": "P2",
    }
    return LLMResponse(
        text=json.dumps(structured),
        structured=structured,
        tools_used=[],
        session_id="sre-sess",
        tokens=TokensUsage(input=60, output=110, model="claude-sonnet-4-6"),
        cost_estimate_cents=3,
        duration_ms=900,
        validated_against_schema=True,
        raw={},
    )


def _task() -> AgentMessage:
    return AgentMessage(
        correlation_id=uuid4(),
        sender=AgentId.TEAM_LEAD,
        recipient=AgentId.SRE_SUPPORT,
        message_type=MessageType.TASK_ASSIGNMENT,
        priority=Priority.P3,
        payload=TaskAssignmentPayload(
            task_id=uuid4(),
            title="Write a runbook for quota_exhausted",
            description="See docs/adr/0008-llm-access-strategy.md.",
        ),
    )


def test_role_and_tier() -> None:
    assert SRESupportAgent.role == AgentId.SRE_SUPPORT
    assert SRESupportAgent.model_tier == "sonnet"


def test_mcp_env_scopes_to_runbooks_and_monitoring() -> None:
    """Per ADR-004 SRE row."""
    prefixes = SRESupportAgent.mcp_env["AI_TEAM_PATH_PREFIXES"]
    assert "docs/runbooks" in prefixes
    assert "infra/monitoring" in prefixes


def test_allowed_tools_no_raw_bash_or_shell() -> None:
    """Iter-2c defers shell allowlist (curl/promtool/journalctl) to iter-5."""
    forbidden = {"Bash", "Write", "Edit", "MultiEdit", "mcp__ai_team_repo__run_shell"}
    assert not (set(SRESupportAgent.allowed_tools) & forbidden)


@pytest.mark.asyncio
async def test_handle_writes_runbook_md_and_reports_to_tl(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runbook_dir = tmp_path / "docs" / "runbooks"
    monkeypatch.setattr("agents.sre_support.agent._RUNBOOK_DIR", runbook_dir)
    monkeypatch.setattr(
        "agents.sre_support.agent._REPO_ROOT", tmp_path
    )  # so relative_to() works for artifact path

    agent = SRESupportAgent(llm=_StubLLM(_sre_response()))
    outputs = await agent.handle(_task())

    assert len(outputs) == 1
    report = outputs[0]
    assert report.recipient == AgentId.TEAM_LEAD
    payload = report.payload
    assert isinstance(payload, TaskReportPayload)
    assert payload.status.value == "done"
    assert payload.artifacts == ["docs/runbooks/quota-exhausted.md"]

    written = (runbook_dir / "quota-exhausted.md").read_text()
    assert "Runbook — Dispatcher reports quota_exhausted" in written
    assert "P2" in written
    assert "Wait for monthly quota reset" in written


@pytest.mark.asyncio
async def test_handle_writes_alert_to_monitoring_dir_when_kind_is_alert(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monitoring_dir = tmp_path / "infra" / "monitoring"
    monkeypatch.setattr("agents.sre_support.agent._RUNBOOK_DIR", tmp_path / "docs" / "runbooks")
    monkeypatch.setattr("agents.sre_support.agent._MONITORING_DIR", monitoring_dir)
    monkeypatch.setattr("agents.sre_support.agent._REPO_ROOT", tmp_path)

    agent = SRESupportAgent(llm=_StubLLM(_sre_response(slug="chain-tampered", kind="alert")))
    outputs = await agent.handle(_task())

    payload = outputs[0].payload
    assert isinstance(payload, TaskReportPayload)
    assert payload.status.value == "done"
    assert payload.artifacts == ["infra/monitoring/chain-tampered.md"]
    assert (monitoring_dir / "chain-tampered.md").exists()


@pytest.mark.asyncio
async def test_handle_rejects_invalid_slug(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("agents.sre_support.agent._RUNBOOK_DIR", tmp_path / "docs" / "runbooks")
    monkeypatch.setattr("agents.sre_support.agent._REPO_ROOT", tmp_path)

    agent = SRESupportAgent(llm=_StubLLM(_sre_response(slug="Bad Slug")))
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
    agent = SRESupportAgent(llm=_StubLLM(bad))
    outputs = await agent.handle(_task())
    payload = outputs[0].payload
    assert isinstance(payload, TaskReportPayload)
    assert payload.status.value == "failed"


@pytest.mark.asyncio
async def test_handle_skips_non_task_assignment() -> None:
    agent = SRESupportAgent(llm=_StubLLM(_sre_response()))
    other = AgentMessage(
        correlation_id=uuid4(),
        sender=AgentId.TEAM_LEAD,
        recipient=AgentId.SRE_SUPPORT,
        message_type=MessageType.QUESTION,
        priority=Priority.P3,
        payload={"kind": "question", "question_id": str(uuid4()), "text": "hi"},
    )
    assert await agent.handle(other) == []
