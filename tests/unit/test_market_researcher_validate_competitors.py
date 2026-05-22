"""MR validate-competitors mode: schema + render + dispatch + max_budget."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any
from uuid import uuid4

if TYPE_CHECKING:
    from pathlib import Path

import jsonschema  # type: ignore[import-untyped]
import pytest

from agents.market_researcher.agent import (
    BRAINSTORM_NICHE_SCHEMA,
    VALIDATE_COMPETITORS_SCHEMA,
    MarketResearcherAgent,
    _render_competitors_markdown,
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
    "intent_completed": "validate_competitors",
    "competitors_found": 15,
    "pain_signals_found": 7,
    "distribution_feasibility": {
        "channel_estimate": "~120 CIS dev Telegram channels with 5k+ subs",
        "audience_reach_estimate": "~800k aggregate addressable subs",
        "conversion_to_paid_estimate": "0.5-1.5% based on observed Telegram bot subscriptions",
        "notes": "Owner's existing network covers ~15 channels directly.",
    },
    "verdict": "underserved",
    "summary": (
        "Niche has 3-4 partial competitors but none specifically targeting Telegram dev channels."
    ),
    "artifacts": ["docs/products/telegram-tech-publisher/competitors.md"],
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


def _make_assignment(inputs: dict[str, Any] | None, title: str = "Test task") -> AgentMessage:
    return AgentMessage(
        correlation_id=uuid4(),
        sender=AgentId.TEAM_LEAD,
        recipient=AgentId.MARKET_RESEARCHER,
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
    jsonschema.validate(_GOOD_OUTPUT, VALIDATE_COMPETITORS_SCHEMA)


def test_schema_rejects_wrong_intent_completed() -> None:
    bad = {**_GOOD_OUTPUT, "intent_completed": "market_scan"}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, VALIDATE_COMPETITORS_SCHEMA)


def test_schema_rejects_unknown_verdict() -> None:
    bad = {**_GOOD_OUTPUT, "verdict": "amazing"}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, VALIDATE_COMPETITORS_SCHEMA)


def test_schema_requires_distribution_feasibility_subfields() -> None:
    bad = {**_GOOD_OUTPUT, "distribution_feasibility": {"channel_estimate": "x"}}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, VALIDATE_COMPETITORS_SCHEMA)


def test_schema_rejects_extra_top_level_keys() -> None:
    bad = {**_GOOD_OUTPUT, "extra_field": "not allowed"}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, VALIDATE_COMPETITORS_SCHEMA)


# ---------------------------------------------------------------------------
# Render test
# ---------------------------------------------------------------------------


def test_render_competitors_markdown_includes_all_sections() -> None:
    md = _render_competitors_markdown(_GOOD_OUTPUT, slug="telegram-tech-publisher")
    assert "# Competitor scan: telegram-tech-publisher" in md
    assert "## Distribution feasibility" in md
    assert "CIS dev Telegram channels" in md
    assert "Verdict: **underserved**" in md
    assert "15" in md  # competitors_found
    assert "7" in md  # pain_signals_found


# ---------------------------------------------------------------------------
# Dispatch + max_budget tests (async)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_dispatches_validate_schema_on_intent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When inputs.intent='validate_competitors', handle() uses
    VALIDATE_COMPETITORS_SCHEMA, passes max_budget_usd=5.50, and the agent
    writes docs/products/<slug>/competitors.md."""
    monkeypatch.setattr("agents.market_researcher.agent._REPO_ROOT", tmp_path)
    monkeypatch.setattr(
        "agents.market_researcher.agent._VALIDATE_DIR",
        tmp_path / "docs" / "products",
    )

    stub = _StubLLM(_GOOD_OUTPUT)
    agent = MarketResearcherAgent(llm=stub)
    incoming = _make_assignment(
        inputs={
            "intent": "validate_competitors",
            "slug": "telegram-tech-publisher",
            "depth": "standard",
            "candidate_brief": "...",
            "target_market": "...",
            "constraints": {"owner_profile": "solo_developer"},
        },
        title="Validate competitors: telegram-tech-publisher",
    )

    outputs = await agent.handle(incoming)

    # Verify schema and budget were threaded through
    assert stub.last_kwargs.get("json_schema") is VALIDATE_COMPETITORS_SCHEMA
    assert stub.last_kwargs.get("max_budget_usd") == 5.50

    # Verify file was written
    artifact_path = tmp_path / "docs" / "products" / "telegram-tech-publisher" / "competitors.md"
    assert artifact_path.exists()
    body = artifact_path.read_text()
    assert "Verdict: **underserved**" in body

    # Single DONE task report
    reports = [m for m in outputs if m.message_type == MessageType.TASK_REPORT]
    assert len(reports) == 1
    payload = reports[0].payload
    assert isinstance(payload, TaskReportPayload)
    assert payload.status == TaskStatus.DONE


@pytest.mark.asyncio
async def test_handle_blocks_on_invalid_slug(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A path-traversal or otherwise invalid slug must be rejected before the LLM is called."""
    monkeypatch.setattr("agents.market_researcher.agent._REPO_ROOT", tmp_path)
    monkeypatch.setattr(
        "agents.market_researcher.agent._VALIDATE_DIR",
        tmp_path / "docs" / "products",
    )

    stub = _StubLLM(_GOOD_OUTPUT)
    agent = MarketResearcherAgent(llm=stub)
    incoming = _make_assignment(
        inputs={
            "intent": "validate_competitors",
            "slug": "../escaped/slug",  # path traversal attempt
            "depth": "standard",
            "candidate_brief": "...",
            "target_market": "...",
            "constraints": {},
        },
        title="Validate competitors: bad slug",
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


@pytest.mark.asyncio
async def test_handle_non_validate_intent_falls_through_to_existing_modes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pre-existing brainstorm_niche mode is unaffected by the new intent branch."""
    monkeypatch.setattr("agents.market_researcher.agent._REPO_ROOT", tmp_path)
    monkeypatch.setattr(
        "agents.market_researcher.agent._BRAINSTORM_DIR",
        tmp_path / "docs" / "products" / "_candidates",
    )

    # Minimal valid brainstorm response so build_outputs() doesn't fail
    def _cand(i: int) -> dict[str, Any]:
        return {
            "title": f"dev_tools idea {i}",
            "slug": f"dev-tools-idea-{i}",
            "one_paragraph": "x" * 30,
            "target_buyer": "y",
            "monetization": "subscription",
            "known_competitors": [{"name": "C", "positioning": "p"}],
            "scores": {
                "tam_signal": 3,
                "solo_fit": 3,
                "llm_opex_fit": 3,
                "defensibility": 3,
                "time_to_first_revenue": 3,
            },
            "composite_score": 15,
            "rationale": "r",
        }

    brainstorm_resp: dict[str, Any] = {
        "niche": "dev_tools",
        "candidates": [_cand(i) for i in range(5)],
        "researcher_top_3_slugs": [f"dev-tools-idea-{i}" for i in range(3)],
        "research_sources_used": ["https://example.com"],
    }

    stub = _StubLLM(brainstorm_resp)
    agent = MarketResearcherAgent(llm=stub)
    incoming = _make_assignment(
        inputs={"mode": "brainstorm_niche", "niche": "dev_tools", "candidates": 5},
        title="Brainstorm dev_tools",
    )

    await agent.handle(incoming)

    assert stub.last_kwargs.get("json_schema") is BRAINSTORM_NICHE_SCHEMA
    # max_budget_usd must NOT have been set for brainstorm
    assert "max_budget_usd" not in stub.last_kwargs
