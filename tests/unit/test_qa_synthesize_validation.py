"""QA synthesize_validation: schema + render + fatal_flaws invariant + dispatch."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any
from uuid import uuid4

if TYPE_CHECKING:
    from pathlib import Path

import jsonschema  # type: ignore[import-untyped]
import pytest

from agents.qa_engineer.agent import (
    RANK_BRAINSTORM_SCHEMA,
    SYNTHESIZE_VALIDATION_SCHEMA,
    QAEngineerAgent,
    _coerce_recommendation_for_fatal_flaws,
    _render_validation_summary_markdown,
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
    "intent_completed": "synthesize_validation",
    "recommendation": "go_with_caveats",
    "confidence": 4,
    "top_risks": [
        {
            "name": "Voice calibration drift",
            "severity": 3,
            "mitigation": "monthly recalibration script",
        },
        {
            "name": "Telegram Bot API rate limit on broadcast channels",
            "severity": 2,
            "mitigation": "per-chat queue with backoff",
        },
    ],
    "fatal_flaws": [],
    "build_window": "6-8 weeks",
    "next_steps": [
        "Draft iter-27 spec with first-sprint scope: source curator + single-channel pipeline",
        "Validate Telegram Stars vs Stripe payment flow before week 2",
        "Set up voice-calibration test harness before LLM integration",
    ],
    "summary": (
        "All three upstream reports return positive verdicts with mitigable risks;"
        " recommend go_with_caveats."
    ),
    "artifacts": ["docs/products/telegram-tech-publisher/_validation_summary.md"],
}


# ---------------------------------------------------------------------------
# Stub LLM — captures invoke() kwargs for assertion
# ---------------------------------------------------------------------------


class _StubLLM:
    """Minimal LLMClient stub that records invoke() kwargs."""

    def __init__(self, structured: dict[str, Any] | None) -> None:
        self._structured = structured
        self.last_kwargs: dict[str, Any] = {}

    async def invoke(self, **kwargs: Any) -> LLMResponse:
        self.last_kwargs = dict(kwargs)
        return LLMResponse(
            text=json.dumps(self._structured) if self._structured else "",
            structured=self._structured,
            tools_used=[],
            session_id="stub-session",
            tokens=TokensUsage(input=100, output=200, model="claude-sonnet-4-6"),
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


def _make_assignment(
    inputs: dict[str, Any] | None = None, title: str = "Test task"
) -> AgentMessage:
    return AgentMessage(
        correlation_id=uuid4(),
        sender=AgentId.TEAM_LEAD,
        recipient=AgentId.QA_ENGINEER,
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
    jsonschema.validate(_GOOD_OUTPUT, SYNTHESIZE_VALIDATION_SCHEMA)


def test_schema_accepts_recommendation_kill_with_fatal_flaws() -> None:
    bad = {
        **_GOOD_OUTPUT,
        "recommendation": "kill",
        "fatal_flaws": ["Telegram ToS prohibits commercial bots"],
        "top_risks": [],
    }
    jsonschema.validate(bad, SYNTHESIZE_VALIDATION_SCHEMA)


def test_schema_rejects_unknown_recommendation() -> None:
    bad = {**_GOOD_OUTPUT, "recommendation": "maybe"}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, SYNTHESIZE_VALIDATION_SCHEMA)


def test_schema_rejects_confidence_out_of_range() -> None:
    bad = {**_GOOD_OUTPUT, "confidence": 6}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, SYNTHESIZE_VALIDATION_SCHEMA)


# ---------------------------------------------------------------------------
# Coerce helper tests
# ---------------------------------------------------------------------------


def test_coerce_recommendation_no_change_when_no_fatal_flaws() -> None:
    out = _coerce_recommendation_for_fatal_flaws(_GOOD_OUTPUT)
    assert out["recommendation"] == "go_with_caveats"


def test_coerce_recommendation_no_change_when_already_kill() -> None:
    inp = {**_GOOD_OUTPUT, "recommendation": "kill", "fatal_flaws": ["x"]}
    out = _coerce_recommendation_for_fatal_flaws(inp)
    assert out["recommendation"] == "kill"


def test_coerce_recommendation_no_change_when_already_pivot() -> None:
    inp = {**_GOOD_OUTPUT, "recommendation": "pivot", "fatal_flaws": ["x"]}
    out = _coerce_recommendation_for_fatal_flaws(inp)
    assert out["recommendation"] == "pivot"


def test_coerce_recommendation_forces_kill_when_go_with_fatal_flaws() -> None:
    """The fatal_flaws ⇒ {kill, pivot} cross-field invariant: if the LLM
    sets recommendation=go but lists fatal_flaws, override to kill and
    record the original in metadata.
    """
    inp = {
        **_GOOD_OUTPUT,
        "recommendation": "go",
        "fatal_flaws": ["LLM hallucinates pricing in 8% of generated posts"],
    }
    out = _coerce_recommendation_for_fatal_flaws(inp)
    assert out["recommendation"] == "kill"
    assert out.get("_coerced_from") == "go"


# ---------------------------------------------------------------------------
# Render test
# ---------------------------------------------------------------------------


def test_render_validation_summary_includes_yaml_block_and_sections() -> None:
    md = _render_validation_summary_markdown(_GOOD_OUTPUT, slug="telegram-tech-publisher")
    # Top-of-file YAML block
    assert md.startswith("---\n")
    assert "recommendation: go_with_caveats" in md
    assert "confidence: 4" in md
    assert "build_window: 6-8 weeks" in md
    # Prose
    assert "# Validation summary: telegram-tech-publisher" in md
    assert "## Risk register" in md
    assert "Voice calibration drift" in md
    assert "## Next steps" in md


# ---------------------------------------------------------------------------
# Dispatch tests (async)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_dispatches_synthesize_schema_on_intent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When inputs.intent='synthesize_validation', handle() uses
    SYNTHESIZE_VALIDATION_SCHEMA, passes max_budget_usd=2.50, narrows
    env path scope to docs/products/<slug>, writes _validation_summary.md,
    and returns status DONE with non-empty summary.
    """
    monkeypatch.setattr("agents.qa_engineer.agent._REPO_ROOT", tmp_path)
    monkeypatch.setattr(
        "agents.qa_engineer.agent._VALIDATE_DIR",
        tmp_path / "docs" / "products",
    )
    # Seed upstream artifacts the synth agent reads (not strictly required
    # by Python code, but mirrors real usage).
    out_dir = tmp_path / "docs" / "products" / "telegram-tech-publisher"
    out_dir.mkdir(parents=True)
    (out_dir / "competitors.md").write_text("# Competitor scan\nverdict: underserved\n")
    (out_dir / "tech_risk.md").write_text("# Tech risk\nverdict: feasible_with_caveats\n")
    (out_dir / "revenue.md").write_text("# Revenue\nverdict: viable\n")

    stub = _StubLLM(_GOOD_OUTPUT)
    agent = QAEngineerAgent(llm=stub)
    incoming = _make_assignment(
        inputs={
            "intent": "synthesize_validation",
            "slug": "telegram-tech-publisher",
        },
        title="Synthesize validation: telegram-tech-publisher",
    )

    outputs = await agent.handle(incoming)

    # Schema and budget threaded through
    assert stub.last_kwargs.get("json_schema") is SYNTHESIZE_VALIDATION_SCHEMA
    assert stub.last_kwargs.get("max_budget_usd") == 2.50

    # Path scope includes docs/products/<slug>
    env = stub.last_kwargs.get("env") or {}
    prefixes = env.get("AI_TEAM_PATH_PREFIXES", "")
    assert "docs/products/telegram-tech-publisher" in prefixes

    # Artifact file was written
    summary_path = out_dir / "_validation_summary.md"
    assert summary_path.exists()
    body = summary_path.read_text()
    assert "recommendation: go_with_caveats" in body
    assert "## Risk register" in body

    # Single DONE task report
    reports = [m for m in outputs if m.message_type == MessageType.TASK_REPORT]
    assert len(reports) == 1
    payload = reports[0].payload
    assert isinstance(payload, TaskReportPayload)
    assert payload.status == TaskStatus.DONE
    assert payload.summary  # non-empty


@pytest.mark.asyncio
async def test_handle_coerces_fatal_flaws_to_kill(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """End-to-end: LLM returns recommendation='go' + non-empty fatal_flaws →
    artifact must contain 'recommendation: kill' and
    'recommendation_coerced_from: go'.
    """
    monkeypatch.setattr("agents.qa_engineer.agent._REPO_ROOT", tmp_path)
    monkeypatch.setattr(
        "agents.qa_engineer.agent._VALIDATE_DIR",
        tmp_path / "docs" / "products",
    )
    out_dir = tmp_path / "docs" / "products" / "telegram-tech-publisher"
    out_dir.mkdir(parents=True)

    bad_output = {
        **_GOOD_OUTPUT,
        "recommendation": "go",
        "fatal_flaws": ["Telegram ToS prohibits commercial bots in this category"],
    }
    stub = _StubLLM(bad_output)
    agent = QAEngineerAgent(llm=stub)
    incoming = _make_assignment(
        inputs={
            "intent": "synthesize_validation",
            "slug": "telegram-tech-publisher",
        },
        title="Synthesize validation: telegram-tech-publisher",
    )

    outputs = await agent.handle(incoming)

    summary_md = (out_dir / "_validation_summary.md").read_text()
    assert "recommendation: kill" in summary_md
    assert "recommendation_coerced_from: go" in summary_md

    reports = [m for m in outputs if m.message_type == MessageType.TASK_REPORT]
    assert len(reports) == 1
    payload = reports[0].payload
    assert isinstance(payload, TaskReportPayload)
    assert payload.status == TaskStatus.DONE


@pytest.mark.asyncio
async def test_handle_invalid_slug_returns_failed() -> None:
    """An invalid slug must be rejected before the LLM is called."""
    stub = _StubLLM(_GOOD_OUTPUT)
    agent = QAEngineerAgent(llm=stub)
    incoming = _make_assignment(
        inputs={
            "intent": "synthesize_validation",
            "slug": "../escaped/slug",
        },
        title="Synthesize validation: bad slug",
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
    assert "validation synthesis" in summary
    assert "slug" in summary


@pytest.mark.asyncio
async def test_handle_other_intent_falls_through_to_rank_brainstorm(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """rank_brainstorm_candidates branch still selects RANK_BRAINSTORM_SCHEMA."""
    monkeypatch.setattr("agents.qa_engineer.agent._REPO_ROOT", tmp_path)
    monkeypatch.setattr(
        "agents.qa_engineer.agent._RANKING_DIR",
        tmp_path / "docs" / "products" / "_candidates",
    )
    cands_dir = tmp_path / "docs" / "products" / "_candidates"
    cands_dir.mkdir(parents=True)

    rank_payload = {
        "intent_completed": "rank_brainstorm_candidates",
        "ranking_summary": "x",
        "top_3_overall": ["slug-a", "slug-b", "slug-c"],
    }
    stub = _StubLLM(rank_payload)
    agent = QAEngineerAgent(llm=stub)
    incoming = _make_assignment(
        inputs={"intent": "rank_brainstorm_candidates"},
        title="Rank",
    )

    await agent.handle(incoming)

    assert stub.last_kwargs.get("json_schema") is RANK_BRAINSTORM_SCHEMA
