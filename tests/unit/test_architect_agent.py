"""Tests for ArchitectAgent — Opus, emits ADR markdown to docs/adr/.

See ADR-001 (orchestrator) and ADR-006 (Opus only for TL/Architect).
The agent is tested via MockLLMClient with a structured response; the
real --json-schema path is verified by integration in the end-to-end demo.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest

from agents.architect import ArchitectAgent
from agents.architect.agent import _next_adr_number, _render_adr_markdown
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


# ----- pure-helper tests -----


def test_next_adr_number_empty_dir_starts_at_one(tmp_path: Path) -> None:
    """A pristine docs/adr/ dir should be assigned 0001."""
    assert _next_adr_number(tmp_path) == 1


def test_next_adr_number_picks_max_plus_one(tmp_path: Path) -> None:
    (tmp_path / "0001-foo.md").write_text("")
    (tmp_path / "0007-bar.md").write_text("")
    (tmp_path / "0003-baz.md").write_text("")
    assert _next_adr_number(tmp_path) == 8


def test_next_adr_number_ignores_non_adr_files(tmp_path: Path) -> None:
    (tmp_path / "0001-foo.md").write_text("")
    (tmp_path / "README.md").write_text("")
    (tmp_path / "draft-notes.txt").write_text("")
    (tmp_path / "9999-suffix-wrong-no-dash.md").write_text("")
    # The 9999-suffix-wrong-no-dash file still matches the NNNN-… pattern
    # — that IS the regex we accept; the test is here to remind future
    # maintainers that "any 4-digit-prefix file in docs/adr counts".
    assert _next_adr_number(tmp_path) == 10000


def test_next_adr_number_missing_dir_returns_one(tmp_path: Path) -> None:
    """If docs/adr/ doesn't exist yet, the next number is still 1."""
    missing = tmp_path / "does-not-exist"
    assert _next_adr_number(missing) == 1


# ----- markdown rendering tests -----


def test_render_adr_markdown_has_all_sections() -> None:
    """The rendered markdown must include every section ADR-001..009 use."""
    md = _render_adr_markdown(
        number=10,
        title="Idea-validator pipeline",
        slug="idea-validator-pipeline",
        context="Sandbox training task per ADR-009.",
        decision="Use a 7-stage Pydantic pipeline.",
        consequences={
            "positive": ["small surface", "easy to test"],
            "negative": ["LLM cost per call"],
            "neutral": ["needs idea-validator binary path"],
        },
        alternatives=[
            {"name": "monolithic script", "reason_rejected": "harder to unit test"},
        ],
        references=["ADR-009", "ADR-008"],
    )
    assert "# ADR-0010 — Idea-validator pipeline" in md
    assert "## Context" in md
    assert "## Decision" in md
    assert "## Consequences" in md
    assert "### Positive" in md and "small surface" in md
    assert "### Negative" in md and "LLM cost per call" in md
    assert "### Neutral" in md
    assert "## Alternatives considered" in md
    assert "monolithic script" in md and "harder to unit test" in md
    assert "## References" in md
    assert "ADR-009" in md and "ADR-008" in md


# ----- agent behavior tests -----


class _StubLLM:
    """Returns a single canned LLMResponse for any invoke call."""

    def __init__(self, response: LLMResponse) -> None:
        self._response = response
        self.calls: list[dict[str, object]] = []

    async def invoke(self, **kwargs: object) -> LLMResponse:
        self.calls.append(kwargs)
        return self._response

    async def reset_session(self, session_id: str) -> None:
        return None


def _adr_response(*, slug: str = "idea-validator-pipeline") -> LLMResponse:
    structured = {
        "title": "Idea-validator pipeline",
        "slug": slug,
        "context": "Sandbox training task per ADR-009.",
        "decision": "Use a 7-stage Pydantic pipeline.",
        "consequences": {
            "positive": ["small surface", "easy to test"],
            "negative": ["LLM cost per call"],
            "neutral": [],
        },
        "alternatives": [{"name": "monolithic script", "reason_rejected": "harder to unit test"}],
        "references": ["ADR-009"],
    }
    return LLMResponse(
        text=json.dumps(structured),
        structured=structured,
        tools_used=[],
        session_id="arch-sess",
        tokens=TokensUsage(input=10, output=50, model="claude-opus-4-7"),
        cost_estimate_cents=5,
        duration_ms=100,
        validated_against_schema=True,
        raw={},
    )


def _task_assignment(target_repo: str | None = None) -> AgentMessage:
    return AgentMessage(
        correlation_id=uuid4(),
        sender=AgentId.TEAM_LEAD,
        recipient=AgentId.ARCHITECT,
        message_type=MessageType.TASK_ASSIGNMENT,
        priority=Priority.P2,
        payload=TaskAssignmentPayload(
            task_id=uuid4(),
            title="Design the idea-validator pipeline",
            description="Decide the stage breakdown for the sandbox.",
            target_repo=target_repo,
        ),
    )


@pytest.mark.asyncio
async def test_handle_writes_adr_and_reports_to_team_lead(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """End-to-end behaviour: receive task_assignment, write ADR, report to TL."""
    adr_dir = tmp_path / "docs" / "adr"
    monkeypatch.setattr("agents.architect.agent._ADR_DIR", adr_dir)

    agent = ArchitectAgent(llm=_StubLLM(_adr_response()))
    msg = _task_assignment()
    outputs = await agent.handle(msg)

    assert len(outputs) == 1
    report = outputs[0]
    assert report.sender == AgentId.ARCHITECT
    assert report.recipient == AgentId.TEAM_LEAD
    assert report.message_type == MessageType.TASK_REPORT
    assert isinstance(report.payload, TaskReportPayload)
    assert report.payload.status.value == "done"
    assert report.payload.artifacts == ["docs/adr/0001-idea-validator-pipeline.md"]

    written = adr_dir / "0001-idea-validator-pipeline.md"
    assert written.exists()
    content = written.read_text()
    assert "ADR-0001 — Idea-validator pipeline" in content
    assert "Sandbox training task" in content
    assert "ADR-009" in content


@pytest.mark.asyncio
async def test_handle_picks_next_number_when_adrs_exist(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    adr_dir = tmp_path / "docs" / "adr"
    adr_dir.mkdir(parents=True)
    (adr_dir / "0009-existing.md").write_text("")
    monkeypatch.setattr("agents.architect.agent._ADR_DIR", adr_dir)

    agent = ArchitectAgent(llm=_StubLLM(_adr_response()))
    outputs = await agent.handle(_task_assignment())

    payload = outputs[0].payload
    assert isinstance(payload, TaskReportPayload)
    assert payload.artifacts == ["docs/adr/0010-idea-validator-pipeline.md"]
    assert (adr_dir / "0010-idea-validator-pipeline.md").exists()


@pytest.mark.asyncio
async def test_handle_skips_non_task_assignment(tmp_path: Path) -> None:
    agent = ArchitectAgent(llm=_StubLLM(_adr_response()))
    other = AgentMessage(
        correlation_id=uuid4(),
        sender=AgentId.TEAM_LEAD,
        recipient=AgentId.ARCHITECT,
        message_type=MessageType.QUESTION,
        priority=Priority.P3,
        payload={"kind": "question", "question_id": str(uuid4()), "text": "hi"},
    )
    assert await agent.handle(other) == []


@pytest.mark.asyncio
async def test_handle_fails_gracefully_on_missing_structured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """LLM returned no structured output → emit a failed task_report, no file written."""
    adr_dir = tmp_path / "docs" / "adr"
    monkeypatch.setattr("agents.architect.agent._ADR_DIR", adr_dir)

    bad_response = LLMResponse(
        text="model refused",
        structured=None,
        tools_used=[],
        session_id="x",
        tokens=TokensUsage(input=1, output=1, model="claude-opus-4-7"),
        cost_estimate_cents=0,
        duration_ms=1,
        validated_against_schema=False,
        raw={},
    )
    agent = ArchitectAgent(llm=_StubLLM(bad_response))
    outputs = await agent.handle(_task_assignment())

    assert len(outputs) == 1
    payload = outputs[0].payload
    assert isinstance(payload, TaskReportPayload)
    assert payload.status.value == "failed"
    assert payload.artifacts == []
    assert not adr_dir.exists() or not any(adr_dir.iterdir())


def test_allowed_tools_excludes_raw_write_edit_bash() -> None:
    """Per ADR-004: Architect writes only via mcp__ai_team_repo__write_file_in_scope.

    Raw Write/Edit/Bash must never be on the allowlist.
    """
    forbidden = {"Write", "Edit", "Bash", "MultiEdit"}
    overlap = set(ArchitectAgent.allowed_tools) & forbidden
    assert not overlap, f"Architect must not have raw {overlap} access"


def test_mcp_env_scopes_to_adr_dirs() -> None:
    """Architect's MCP server spawns with path scope limited to docs/adr/
    and docs/architecture.md per ADR-004."""
    assert ArchitectAgent.mcp_env["AI_TEAM_PATH_PREFIXES"] == "docs/adr,docs/architecture.md"
