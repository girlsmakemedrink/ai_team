"""PM validate-revenue-model mode: schema + render + dispatch + max_budget."""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Any
from uuid import uuid4

if TYPE_CHECKING:
    from pathlib import Path

import jsonschema  # type: ignore[import-untyped]
import pytest

from agents.product_manager.agent import (
    USER_STORIES_SCHEMA,
    VALIDATE_REVENUE_SCHEMA,
    ProductManagerAgent,
    _render_revenue_markdown,
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
    "intent_completed": "validate_revenue_model",
    "buyer_persona": (
        "Developer-influencer running a 5k-100k-sub Telegram channel, posting 3-5x weekly,"
        " currently spending 30-60 min/day on content."
    ),
    "addressable_population_estimate": (
        "~120 active CIS dev Telegram channels with 5k+ subs; ~2k globally if expanded."
    ),
    "pricing_tiers": [
        {"name": "Free", "price_usd_monthly": 0, "target_user": "trial / <500 subs"},
        {"name": "Pro", "price_usd_monthly": 19, "target_user": "5k-50k subs"},
        {"name": "Power", "price_usd_monthly": 49, "target_user": "50k+ subs, daily volume"},
    ],
    "cac_envelope_usd": 0,
    "ltv_envelope_usd": 320,
    "time_to_first_revenue_weeks": 10,
    "time_to_1k_mrr_weeks": 24,
    "break_even_users": 35,
    "revenue_forecast": {
        "conservative_mrr_month_6": 800,
        "base_mrr_month_6": 1900,
        "optimistic_mrr_month_6": 4500,
    },
    "verdict": "viable",
    "summary": (
        "$0 CAC via owner channel + $19 Pro tier + 35-user break-even is achievable in 6 months."
    ),
    "artifacts": ["docs/products/telegram-tech-publisher/revenue.md"],
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
        recipient=AgentId.PRODUCT_MANAGER,
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
    jsonschema.validate(_GOOD_OUTPUT, VALIDATE_REVENUE_SCHEMA)


def test_schema_rejects_single_pricing_tier() -> None:
    bad = {**_GOOD_OUTPUT, "pricing_tiers": _GOOD_OUTPUT["pricing_tiers"][:1]}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, VALIDATE_REVENUE_SCHEMA)


def test_schema_rejects_zero_break_even_users() -> None:
    bad = {**_GOOD_OUTPUT, "break_even_users": 0}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, VALIDATE_REVENUE_SCHEMA)


def test_schema_rejects_unknown_verdict() -> None:
    bad = {**_GOOD_OUTPUT, "verdict": "great"}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, VALIDATE_REVENUE_SCHEMA)


def test_schema_rejects_extra_top_level_keys() -> None:
    bad = {**_GOOD_OUTPUT, "extra_field": "not allowed"}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, VALIDATE_REVENUE_SCHEMA)


# ---------------------------------------------------------------------------
# Render tests
# ---------------------------------------------------------------------------


def test_render_includes_pricing_table_and_break_even() -> None:
    md = _render_revenue_markdown(_GOOD_OUTPUT, slug="telegram-tech-publisher")
    assert "# Revenue model: telegram-tech-publisher" in md
    assert "## Pricing tiers" in md
    assert "Pro" in md and "$19" in md
    assert "Break-even" in md
    assert "35" in md
    assert "viable" in md.lower()


def test_render_escapes_pipe_chars_in_pricing_tiers() -> None:
    piped = {
        **_GOOD_OUTPUT,
        "pricing_tiers": [
            {"name": "Free|Trial", "price_usd_monthly": 0, "target_user": "devs|teams"},
            {"name": "Pro", "price_usd_monthly": 19, "target_user": "solo founders"},
        ],
    }
    md = _render_revenue_markdown(piped, slug="slug-test")
    # Each pricing-tier data row: leading | + 3 field separators + trailing | = 4 unescaped pipes.
    # The embedded | chars in "Free|Trial" and "devs|teams" must be escaped as \|.
    tier_line = next(
        line for line in md.splitlines() if "Free" in line and "|" in line and "---" not in line
    )
    unescaped = len(re.findall(r"(?<!\\)\|", tier_line))
    assert unescaped == 4, (
        f"row should have 4 unescaped column separators, got {unescaped}: {tier_line!r}"
    )


# ---------------------------------------------------------------------------
# Dispatch + max_budget tests (async)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_dispatches_validate_schema_on_intent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When inputs.intent='validate_revenue_model', handle() uses
    VALIDATE_REVENUE_SCHEMA, passes max_budget_usd=3.50, writes revenue.md,
    and the env includes both docs/backlog and docs/products/<slug>."""
    monkeypatch.setattr("agents.product_manager.agent._REPO_ROOT", tmp_path)
    monkeypatch.setattr(
        "agents.product_manager.agent._VALIDATE_DIR",
        tmp_path / "docs" / "products",
    )

    stub = _StubLLM(_GOOD_OUTPUT)
    agent = ProductManagerAgent(llm=stub)
    incoming = _make_assignment(
        inputs={
            "intent": "validate_revenue_model",
            "slug": "telegram-tech-publisher",
            "candidate_brief": "...",
            "target_market": "...",
            "constraints": {},
        },
        title="Validate revenue: telegram-tech-publisher",
    )

    outputs = await agent.handle(incoming)

    # Schema and budget threaded through
    assert stub.last_kwargs.get("json_schema") is VALIDATE_REVENUE_SCHEMA
    assert stub.last_kwargs.get("max_budget_usd") == 3.50

    # Path scope contains both docs/backlog and docs/products/<slug>
    env = stub.last_kwargs.get("env") or {}
    prefixes = env.get("AI_TEAM_PATH_PREFIXES", "")
    assert "docs/backlog" in prefixes
    assert "docs/products/telegram-tech-publisher" in prefixes

    # Artifact file was written
    artifact_path = tmp_path / "docs" / "products" / "telegram-tech-publisher" / "revenue.md"
    assert artifact_path.exists()
    body = artifact_path.read_text()
    assert "viable" in body

    # Single DONE task report
    reports = [m for m in outputs if m.message_type == MessageType.TASK_REPORT]
    assert len(reports) == 1
    payload = reports[0].payload
    assert isinstance(payload, TaskReportPayload)
    assert payload.status == TaskStatus.DONE
    assert payload.artifacts == ["docs/products/telegram-tech-publisher/revenue.md"]


@pytest.mark.asyncio
async def test_handle_fails_on_invalid_slug(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A path-traversal or otherwise invalid slug must be rejected before the LLM is called."""
    monkeypatch.setattr("agents.product_manager.agent._REPO_ROOT", tmp_path)
    monkeypatch.setattr(
        "agents.product_manager.agent._VALIDATE_DIR",
        tmp_path / "docs" / "products",
    )

    stub = _StubLLM(_GOOD_OUTPUT)
    agent = ProductManagerAgent(llm=stub)
    incoming = _make_assignment(
        inputs={
            "intent": "validate_revenue_model",
            "slug": "../escaped/slug",
            "candidate_brief": "...",
            "target_market": "...",
            "constraints": {},
        },
        title="Validate revenue: bad slug",
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
async def test_handle_no_intent_falls_through_to_user_stories(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pre-existing user-stories path is unaffected when no intent is set."""
    monkeypatch.setattr("agents.product_manager.agent._REPO_ROOT", tmp_path)
    monkeypatch.setattr(
        "agents.product_manager.agent._BACKLOG_DIR",
        tmp_path / "docs" / "backlog",
    )

    user_stories_resp: dict[str, Any] = {
        "summary": "Two stories for testing.",
        "stories": [
            {
                "id": "US-1",
                "as_a": "developer",
                "i_want": "a CLI",
                "so_that": "I can run commands",
                "acceptance_criteria": ["it works"],
                "priority": "P2",
            }
        ],
    }
    stub = _StubLLM(user_stories_resp)
    agent = ProductManagerAgent(llm=stub)
    incoming = _make_assignment(inputs=None, title="Write stories")

    await agent.handle(incoming)

    assert stub.last_kwargs.get("json_schema") is USER_STORIES_SCHEMA
    assert "max_budget_usd" not in stub.last_kwargs
