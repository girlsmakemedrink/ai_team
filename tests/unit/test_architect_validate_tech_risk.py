"""Architect validate-tech-risk mode: schema + render + dispatch + max_budget."""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Any
from uuid import uuid4

if TYPE_CHECKING:
    from pathlib import Path

import jsonschema  # type: ignore[import-untyped]
import pytest

from agents.architect import ArchitectAgent
from agents.architect.agent import (
    ADR_SCHEMA,
    VALIDATE_TECH_RISK_SCHEMA,
    _render_tech_risk_markdown,
)
from core.llm.base import LLMResponse, TokensUsage
from core.messaging.schemas import (
    AgentId,
    AgentMessage,
    MessageType,
    Priority,
    TaskAssignmentPayload,
    TaskReportPayload,
    TaskStatus,
)

# ---------------------------------------------------------------------------
# Shared fixture data
# ---------------------------------------------------------------------------

_GOOD_OUTPUT: dict[str, Any] = {
    "intent_completed": "validate_tech_risk",
    "components": [
        {
            "name": "Telegram Bot API ingestion",
            "complexity": 3,
            "dependency": "Telegram Bot API (3rd-party, free)",
            "scaling_limit": "30 msg/sec to different users, 1/sec per chat",
            "gotchas": ["per-chat rate limits", "message length 4096 chars"],
        },
        {
            "name": "Source curator (GitHub + RSS)",
            "complexity": 2,
            "dependency": "GitHub REST API + RSS libs",
            "scaling_limit": "GitHub 5000 req/hr authenticated",
            "gotchas": ["RSS feed flake"],
        },
        {
            "name": "LLM voice calibration",
            "complexity": 4,
            "dependency": "Claude API via owner subscription",
            "scaling_limit": "subscription quota",
            "gotchas": ["voice drift between sessions", "prompt caching invalidation"],
        },
    ],
    "risks_found": 4,
    "top_risk": "Voice calibration drift undermines the 'authentic-creator-voice' moat over time.",
    "llm_opex_at_scale": {
        "per_user_per_day_at_100": 0.50,
        "per_user_per_day_at_1000": 0.40,
        "per_user_per_day_at_10000": 0.30,
    },
    "build_window_weeks": "6-8 weeks",
    "verdict": "feasible_with_caveats",
    "summary": (
        "Telegram Bot API + Python + Claude is feasible; voice calibration is the long-tail risk."
    ),
    "artifacts": ["docs/products/telegram-tech-publisher/tech_risk.md"],
}


# ---------------------------------------------------------------------------
# Stub LLM — captures invoke() kwargs for assertion
# ---------------------------------------------------------------------------


class _StubLLM:
    """Minimal LLMClient stub that records invoke() kwargs."""

    def __init__(self, structured: dict[str, Any]) -> None:
        self._structured = structured
        self.last_kwargs: dict[str, Any] = {}

    async def invoke(self, **kwargs: object) -> LLMResponse:
        self.last_kwargs = dict(kwargs)
        return LLMResponse(
            text=json.dumps(self._structured),
            structured=self._structured,
            tools_used=[],
            session_id="stub-session",
            tokens=TokensUsage(input=100, output=200, model="claude-opus-4-7"),
            cost_estimate_cents=4,
            duration_ms=1000,
            validated_against_schema=True,
            raw={},
        )

    async def reset_session(self, session_id: str) -> None:
        return None


# ---------------------------------------------------------------------------
# Helper: build a TASK_ASSIGNMENT AgentMessage
# ---------------------------------------------------------------------------


def _make_assignment(inputs: dict[str, Any] | None, title: str = "Test task") -> AgentMessage:
    return AgentMessage(
        correlation_id=uuid4(),
        sender=AgentId.TEAM_LEAD,
        recipient=AgentId.ARCHITECT,
        message_type=MessageType.TASK_ASSIGNMENT,
        priority=Priority.P2,
        payload=TaskAssignmentPayload(
            task_id=uuid4(),
            title=title,
            description=title,
            inputs=inputs or {},
        ),
    )


# ---------------------------------------------------------------------------
# Schema tests (pure-Python, no async)
# ---------------------------------------------------------------------------


def test_schema_accepts_valid_output() -> None:
    jsonschema.validate(_GOOD_OUTPUT, VALIDATE_TECH_RISK_SCHEMA)


def test_schema_rejects_components_below_minimum() -> None:
    bad = {**_GOOD_OUTPUT, "components": _GOOD_OUTPUT["components"][:2]}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, VALIDATE_TECH_RISK_SCHEMA)


def test_schema_rejects_unknown_build_window() -> None:
    bad = {**_GOOD_OUTPUT, "build_window_weeks": "5-7 weeks"}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, VALIDATE_TECH_RISK_SCHEMA)


def test_schema_rejects_complexity_out_of_range() -> None:
    bad_components = list(_GOOD_OUTPUT["components"])
    bad_components[0] = {**bad_components[0], "complexity": 6}
    bad = {**_GOOD_OUTPUT, "components": bad_components}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, VALIDATE_TECH_RISK_SCHEMA)


def test_schema_rejects_extra_top_level_keys() -> None:
    bad = {**_GOOD_OUTPUT, "extra_field": "not allowed"}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, VALIDATE_TECH_RISK_SCHEMA)


# ---------------------------------------------------------------------------
# Render test
# ---------------------------------------------------------------------------


def test_render_includes_component_table_and_opex() -> None:
    md = _render_tech_risk_markdown(_GOOD_OUTPUT, slug="telegram-tech-publisher")
    assert "# Tech-risk register: telegram-tech-publisher" in md
    assert "Telegram Bot API ingestion" in md
    assert "## LLM opex at scale" in md
    assert "0.50" in md or "0.5" in md
    assert "feasible_with_caveats" in md
    assert "6-8 weeks" in md


# ---------------------------------------------------------------------------
# Dispatch + max_budget tests (async)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_dispatches_validate_schema_on_intent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When inputs.intent='validate_tech_risk', handle() uses
    VALIDATE_TECH_RISK_SCHEMA, passes max_budget_usd=4.50, and the agent
    writes docs/products/<slug>/tech_risk.md."""
    monkeypatch.setattr("agents.architect.agent._REPO_ROOT", tmp_path)
    monkeypatch.setattr(
        "agents.architect.agent._VALIDATE_DIR",
        tmp_path / "docs" / "products",
    )

    stub = _StubLLM(_GOOD_OUTPUT)
    agent = ArchitectAgent(llm=stub)
    incoming = _make_assignment(
        inputs={
            "intent": "validate_tech_risk",
            "slug": "telegram-tech-publisher",
            "candidate_brief": "...",
            "constraints": {"owner_profile": "solo_developer"},
        },
        title="Validate tech-risk: telegram-tech-publisher",
    )

    outputs = await agent.handle(incoming)

    # Verify schema and budget were threaded through
    assert stub.last_kwargs.get("json_schema") is VALIDATE_TECH_RISK_SCHEMA
    assert stub.last_kwargs.get("max_budget_usd") == 4.50

    # Verify file was written
    artifact_path = tmp_path / "docs" / "products" / "telegram-tech-publisher" / "tech_risk.md"
    assert artifact_path.exists()
    body = artifact_path.read_text()
    assert "feasible_with_caveats" in body

    # Single DONE task report
    reports = [m for m in outputs if m.message_type == MessageType.TASK_REPORT]
    assert len(reports) == 1
    payload = reports[0].payload
    assert isinstance(payload, TaskReportPayload)
    assert payload.status == TaskStatus.DONE
    assert payload.artifacts == ["docs/products/telegram-tech-publisher/tech_risk.md"]


@pytest.mark.asyncio
async def test_handle_no_intent_falls_through_to_adr(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pre-existing ADR-emitting flow still works when no intent is set."""
    adr_dir = tmp_path / "docs" / "adr"
    monkeypatch.setattr("agents.architect.agent._ADR_DIR", adr_dir)

    adr_structured: dict[str, Any] = {
        "title": "Design the idea-validator pipeline",
        "slug": "idea-validator-pipeline",
        "context": "Sandbox training task.",
        "decision": "Use a 7-stage pipeline.",
        "consequences": {"positive": [], "negative": [], "neutral": []},
        "alternatives": [],
        "references": [],
    }
    stub = _StubLLM(adr_structured)
    agent = ArchitectAgent(llm=stub)
    incoming = _make_assignment(inputs=None, title="Design")

    await agent.handle(incoming)

    assert stub.last_kwargs.get("json_schema") is ADR_SCHEMA
    assert "max_budget_usd" not in stub.last_kwargs


@pytest.mark.asyncio
async def test_handle_fails_on_invalid_slug(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A path-traversal or otherwise invalid slug must be rejected before the LLM is called."""
    monkeypatch.setattr("agents.architect.agent._REPO_ROOT", tmp_path)
    monkeypatch.setattr(
        "agents.architect.agent._VALIDATE_DIR",
        tmp_path / "docs" / "products",
    )

    stub = _StubLLM(_GOOD_OUTPUT)
    agent = ArchitectAgent(llm=stub)
    incoming = _make_assignment(
        inputs={
            "intent": "validate_tech_risk",
            "slug": "../escaped/slug",  # path traversal attempt
            "candidate_brief": "...",
            "constraints": {},
        },
        title="Validate tech-risk: bad slug",
    )

    outputs = await agent.handle(incoming)

    # LLM must NOT have been invoked
    assert stub.last_kwargs == {}

    reports = [m for m in outputs if m.message_type == MessageType.TASK_REPORT]
    assert len(reports) == 1
    payload = reports[0].payload
    assert isinstance(payload, TaskReportPayload)
    assert payload.status == TaskStatus.FAILED
    summary = (payload.summary or "").lower()
    assert "input_validation" in summary or "slug" in summary


# ---------------------------------------------------------------------------
# Helper: build a validate_tech_risk TASK_ASSIGNMENT for a given slug
# ---------------------------------------------------------------------------


def _validate_incoming(slug: str) -> AgentMessage:
    return _make_assignment(
        inputs={
            "intent": "validate_tech_risk",
            "slug": slug,
            "candidate_brief": "...",
            "constraints": {"owner_profile": "solo_developer"},
        },
        title=f"Validate tech-risk: {slug}",
    )


# ---------------------------------------------------------------------------
# Fix 2: env path-scope must use docs/architecture.md, not docs/architecture/
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_validate_path_scope_includes_slug_and_excludes_arch_dir(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr("agents.architect.agent._REPO_ROOT", tmp_path)
    monkeypatch.setattr("agents.architect.agent._VALIDATE_DIR", tmp_path / "docs" / "products")

    stub = _StubLLM(_GOOD_OUTPUT)
    agent = ArchitectAgent(llm=stub)
    incoming = _validate_incoming("telegram-tech-publisher")
    await agent.handle(incoming)

    env = stub.last_kwargs.get("env") or {}
    prefixes = env.get("AI_TEAM_PATH_PREFIXES", "")
    assert "docs/architecture.md" in prefixes
    assert "docs/architecture," not in prefixes  # dir prefix would be a regression
    assert "docs/products/telegram-tech-publisher" in prefixes
    assert "docs/adr" in prefixes


# ---------------------------------------------------------------------------
# Fix 3: pipe chars in component fields must be escaped in GFM table rows
# ---------------------------------------------------------------------------


def test_render_escapes_pipe_chars_in_component_fields() -> None:
    bad = {
        **_GOOD_OUTPUT,
        "components": [
            {
                "name": "Telegram|WhatsApp bridge",
                "complexity": 3,
                "dependency": "Bot API|Webhook",
                "scaling_limit": "30 msg|sec",
                "gotchas": ["watch | this"],
            },
            *_GOOD_OUTPUT["components"][:2],  # keep min items count at 3
        ],
    }
    md = _render_tech_risk_markdown(bad, slug="telegram-tech-publisher")
    # The bridge row must NOT have extra column separators
    bridge_line = next(line for line in md.splitlines() if "Telegram" in line and "|" in line)
    # GFM row: leading | + 5 field separators + trailing | = 6 unescaped pipes; the
    # 4 fields with embedded | add 4 escaped \| which should NOT increase separator count.
    unescaped_pipes = len(re.findall(r"(?<!\\)\|", bridge_line))
    assert unescaped_pipes == 6, (
        f"row should have 6 unescaped column separators, got {unescaped_pipes}: {bridge_line!r}"
    )


# ---------------------------------------------------------------------------
# Fix 1: _fail_report kind= — validate path must not say "ADR"
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_validate_fail_summary_uses_validation_kind(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr("agents.architect.agent._REPO_ROOT", tmp_path)
    monkeypatch.setattr("agents.architect.agent._VALIDATE_DIR", tmp_path / "docs" / "products")

    # Stub returns intent_completed mismatched → triggers _fail_report path
    bad_response = {**_GOOD_OUTPUT, "intent_completed": "wrong"}
    stub = _StubLLM(bad_response)
    agent = ArchitectAgent(llm=stub)
    incoming = _validate_incoming("telegram-tech-publisher")
    outputs = await agent.handle(incoming)

    reports = [m for m in outputs if m.message_type == MessageType.TASK_REPORT]
    assert len(reports) == 1
    payload = reports[0].payload
    assert isinstance(payload, TaskReportPayload)
    assert payload.status == TaskStatus.FAILED
    assert "ADR" not in payload.summary, (
        f"validate-path failure should not mention ADR, got: {payload.summary}"
    )
    assert "tech-risk" in payload.summary.lower() or "validation" in payload.summary.lower()
