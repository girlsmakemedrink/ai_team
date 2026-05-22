"""End-to-end iter-26b chain on Postgres + Redis + mocked LLM.

Asserts the full validate_product audit chain:
  1 USER→TL root
  1 TL broadcast (DAG preview)
  3 TL→agent parallel assignments (MR, Architect, PM)
  3 agent DONE reports
  1 TL→QA assignment (gated on all three)
  1 QA→TL DONE report
  1 pending_review row (QA safety-net inserts it)

Real-LLM coverage is in tests/integration/test_mr_brainstorm_one_niche_real_llm.py
(iter-26a pattern).  This file mirrors test_iter_26a_e2e_brainstorm.py exactly.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import pytest
from sqlalchemy import select

from agents.architect import ArchitectAgent
from agents.market_researcher import MarketResearcherAgent
from agents.product_manager import ProductManagerAgent
from agents.qa_engineer import QAEngineerAgent
from agents.team_lead import TeamLeadAgent
from core.audit.writer import AuditLogWriter
from core.dispatcher import AgentDispatcher
from core.llm.base import LLMResponse, TokensUsage
from core.messaging.bus import MessageBus
from core.messaging.feed import FeedPublisher
from core.messaging.schemas import (
    AgentId,
    AgentMessage,
    MessageType,
    Priority,
    TaskAssignmentPayload,
    TaskStatus,
)
from core.persistence.models import AuditLog, PendingReview, Task
from core.persistence.task_state import TaskStateReducer
from core.security.hmac_signer import HMACSigner

if TYPE_CHECKING:
    from pathlib import Path

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = pytest.mark.integration

_SECRET = b"e" * 64  # distinct from other e2e tests to avoid HMAC cross-contamination

# ---------------------------------------------------------------------------
# Scripted LLM responses
# ---------------------------------------------------------------------------

_SLUG = "telegram-tech-publisher"


def _tl_validate_response() -> LLMResponse:
    """TL decomposes 'validate_product' into 3 parallel subtasks + 1 QA gated synth."""
    return LLMResponse(
        text="",
        structured={
            "summary": (
                "Decomposing validate_product for telegram-tech-publisher into 3 parallel "
                "validation subtasks (comp, tech, rev) and one QA synthesis step gated "
                "on all three."
            ),
            "subtasks": [
                {
                    "id": "comp",
                    "recipient": "market_researcher",
                    "title": "Validate competitors",
                    "description": (
                        "Research competitor landscape for telegram-tech-publisher. "
                        "Assess market saturation and pain signals."
                    ),
                    "priority": "P2",
                    "depends_on": [],
                    "inputs": {
                        "intent": "validate_competitors",
                        "slug": _SLUG,
                        "depth": "quick",
                    },
                },
                {
                    "id": "tech",
                    "recipient": "architect",
                    "title": "Validate tech risk",
                    "description": (
                        "Assess technical feasibility and risk for telegram-tech-publisher. "
                        "Enumerate key components, gotchas, LLM opex at scale."
                    ),
                    "priority": "P2",
                    "depends_on": [],
                    "inputs": {
                        "intent": "validate_tech_risk",
                        "slug": _SLUG,
                        "depth": "quick",
                    },
                },
                {
                    "id": "rev",
                    "recipient": "product_manager",
                    "title": "Validate revenue model",
                    "description": (
                        "Model the revenue potential of telegram-tech-publisher. "
                        "Size addressable population, draft pricing tiers, unit economics."
                    ),
                    "priority": "P2",
                    "depends_on": [],
                    "inputs": {
                        "intent": "validate_revenue_model",
                        "slug": _SLUG,
                        "depth": "quick",
                    },
                },
                {
                    "id": "synth",
                    "recipient": "qa_engineer",
                    "title": "Synthesize validation",
                    "description": (
                        "Synthesize all three validation reports into a go/no-go recommendation "
                        "for telegram-tech-publisher."
                    ),
                    "priority": "P2",
                    "depends_on": ["comp", "tech", "rev"],
                    "inputs": {
                        "intent": "synthesize_validation",
                        "slug": _SLUG,
                    },
                },
            ],
        },
        tools_used=[],
        session_id="tl-validate-e2e",
        tokens=TokensUsage(input=10, output=40, model="claude-opus-4-7"),
        cost_estimate_cents=0,
        duration_ms=100,
        raw={},
    )


def _mr_validate_response() -> LLMResponse:
    """MR returns a VALIDATE_COMPETITORS_SCHEMA-valid response."""
    return LLMResponse(
        text="",
        structured={
            "intent_completed": "validate_competitors",
            "competitors_found": 4,
            "pain_signals_found": 7,
            "distribution_feasibility": {
                "channel_estimate": "Telegram channels + Product Hunt launch",
                "audience_reach_estimate": "~50k Telegram tech channel followers",
                "conversion_to_paid_estimate": "2-4% based on comparable B2C SaaS",
                "notes": (
                    "Distribution is the primary moat risk. "
                    "Paid acquisition channels are expensive for a solo founder."
                ),
            },
            "verdict": "underserved",
            "summary": (
                "The competitor landscape for telegram-tech-publisher is sparse. "
                "Existing tools focus on newsletters rather than Telegram. "
                "Strong pain signals from indie-hacker forums. Market is underserved."
            ),
            "artifacts": [f"docs/products/{_SLUG}/competitors.md"],
        },
        tools_used=[],
        session_id="mr-validate-competitors-e2e",
        tokens=TokensUsage(input=10, output=30, model="claude-sonnet-4-6"),
        cost_estimate_cents=0,
        duration_ms=100,
        raw={},
    )


def _arch_validate_response() -> LLMResponse:
    """Architect returns a VALIDATE_TECH_RISK_SCHEMA-valid response."""
    return LLMResponse(
        text="",
        structured={
            "intent_completed": "validate_tech_risk",
            "components": [
                {
                    "name": "Telegram Bot API",
                    "complexity": 2,
                    "dependency": "Telegram (third-party)",
                    "scaling_limit": "Rate-limited to 30 msg/s per bot",
                    "gotchas": ["API changes without notice", "No webhooks in restricted networks"],
                },
                {
                    "name": "LLM content generation",
                    "complexity": 3,
                    "dependency": "Anthropic Claude API",
                    "scaling_limit": "Token budget per user per day",
                    "gotchas": ["Prompt injection risk", "Variable latency"],
                },
                {
                    "name": "Postgres persistence",
                    "complexity": 2,
                    "dependency": "self-hosted",
                    "scaling_limit": "Vertical until ~10k users",
                    "gotchas": ["Backup automation required"],
                },
            ],
            "risks_found": 3,
            "top_risk": "Telegram API rate limits at scale could throttle delivery SLAs.",
            "llm_opex_at_scale": {
                "per_user_per_day_at_100": 0.05,
                "per_user_per_day_at_1000": 0.04,
                "per_user_per_day_at_10000": 0.03,
            },
            "build_window_weeks": "6-8 weeks",
            "verdict": "feasible_with_caveats",
            "summary": (
                "telegram-tech-publisher is technically feasible for a solo founder "
                "in 6-8 weeks. Main caveats: Telegram rate limits and LLM opex at scale."
            ),
            "artifacts": [f"docs/products/{_SLUG}/tech_risk.md"],
        },
        tools_used=[],
        session_id="arch-validate-tech-risk-e2e",
        tokens=TokensUsage(input=10, output=30, model="claude-opus-4-7"),
        cost_estimate_cents=0,
        duration_ms=100,
        raw={},
    )


def _pm_validate_response() -> LLMResponse:
    """PM returns a VALIDATE_REVENUE_SCHEMA-valid response."""
    return LLMResponse(
        text="",
        structured={
            "intent_completed": "validate_revenue_model",
            "buyer_persona": (
                "Solo founder or indie hacker who curates tech content for a Telegram audience "
                "and wants to save 3-5 hours/week on content production."
            ),
            "addressable_population_estimate": "~15k active Telegram tech channel owners globally",
            "pricing_tiers": [
                {
                    "name": "Starter",
                    "price_usd_monthly": 19.0,
                    "target_user": "Channel with < 500 subscribers",
                },
                {
                    "name": "Growth",
                    "price_usd_monthly": 49.0,
                    "target_user": "Channel with 500-5k subscribers",
                },
            ],
            "cac_envelope_usd": 35.0,
            "ltv_envelope_usd": 350.0,
            "time_to_first_revenue_weeks": 8,
            "time_to_1k_mrr_weeks": 20,
            "break_even_users": 30,
            "revenue_forecast": {
                "conservative_mrr_month_6": 600.0,
                "base_mrr_month_6": 1200.0,
                "optimistic_mrr_month_6": 2500.0,
            },
            "verdict": "viable_with_caveats",
            "summary": (
                "Revenue model is viable at small scale. $1k MRR reachable in ~20 weeks "
                "if content-quality bar is maintained. CAC:LTV ratio is healthy (10x). "
                "Main caveat: small addressable market caps growth ceiling."
            ),
            "artifacts": [f"docs/products/{_SLUG}/revenue.md"],
        },
        tools_used=[],
        session_id="pm-validate-revenue-e2e",
        tokens=TokensUsage(input=10, output=30, model="claude-sonnet-4-6"),
        cost_estimate_cents=0,
        duration_ms=100,
        raw={},
    )


def _qa_synth_response() -> LLMResponse:
    """QA returns a SYNTHESIZE_VALIDATION_SCHEMA-valid response."""
    return LLMResponse(
        text="",
        structured={
            "intent_completed": "synthesize_validation",
            "recommendation": "go_with_caveats",
            "confidence": 4,
            "top_risks": [
                {
                    "name": "Telegram API rate limits",
                    "severity": 3,
                    "mitigation": (
                        "Implement exponential back-off; cap concurrent deliveries per bot."
                    ),
                },
                {
                    "name": "Small addressable market",
                    "severity": 2,
                    "mitigation": "Expand to WhatsApp / Discord channels in v2.",
                },
            ],
            "fatal_flaws": [],
            "build_window": "6-8 weeks",
            "next_steps": [
                "Build Telegram bot MVP with LLM-powered content summariser",
                "Onboard 5 beta channel owners for qualitative feedback",
                "Validate $19/mo price point via Stripe checkout before full build",
            ],
            "summary": (
                "telegram-tech-publisher clears all three validation gates: "
                "underserved market (MR), feasible tech (Architect), viable unit economics (PM). "
                "Recommendation: go_with_caveats. Confidence 4/5."
            ),
            "artifacts": [f"docs/products/{_SLUG}/_validation_summary.md"],
        },
        tools_used=[],
        session_id="qa-synth-validate-e2e",
        tokens=TokensUsage(input=10, output=30, model="claude-sonnet-4-6"),
        cost_estimate_cents=0,
        duration_ms=100,
        raw={},
    )


class _ValidateScriptedLLM:
    """Scripted LLM that routes by role detected from system prompt header.

    Detection mirrors test_iter_26a_e2e_brainstorm.py: check the
    stripped prompt prefix against '# Role: <RoleName>' literals.
    For agents that handle multiple intents, also sniff the user_message
    for intent keywords (same approach as _detect_niche in iter-26a).
    """

    def __init__(self) -> None:
        self.calls: list[str] = []
        self._tl_resp = _tl_validate_response()
        self._mr_resp = _mr_validate_response()
        self._arch_resp = _arch_validate_response()
        self._pm_resp = _pm_validate_response()
        self._qa_resp = _qa_synth_response()

    async def invoke(
        self, *, system_prompt: str, user_message: str = "", **kwargs: Any
    ) -> LLMResponse:
        head = system_prompt.lstrip()
        if head.startswith("# Role: Team Lead"):
            self.calls.append("team_lead")
            return self._tl_resp
        if head.startswith("# Role: Market Researcher"):
            intent = self._detect_intent(user_message, **kwargs)
            self.calls.append(f"market_researcher:{intent}")
            return self._mr_resp
        if head.startswith("# Role: Architect"):
            intent = self._detect_intent(user_message, **kwargs)
            self.calls.append(f"architect:{intent}")
            return self._arch_resp
        if head.startswith("# Role: Product Manager"):
            intent = self._detect_intent(user_message, **kwargs)
            self.calls.append(f"product_manager:{intent}")
            return self._pm_resp
        if head.startswith("# Role: QA Engineer"):
            intent = self._detect_intent(user_message, **kwargs)
            self.calls.append(f"qa_engineer:{intent}")
            return self._qa_resp
        raise RuntimeError(f"no scripted response for prompt header: {head[:80]!r}")

    def _detect_intent(self, user_message: str, **_kwargs: Any) -> str:
        """Detect intent by scanning the user message for intent keywords."""
        for intent in (
            "validate_competitors",
            "validate_tech_risk",
            "validate_revenue_model",
            "synthesize_validation",
            "validate_product",
        ):
            if intent in user_message:
                return intent
        # Fallback — defensive
        return "unknown"

    async def reset_session(self, session_id: str) -> None:
        return None


# ---------------------------------------------------------------------------
# The test
# ---------------------------------------------------------------------------


async def test_validate_product_full_chain(
    redis_url: str,
    session_factory: async_sessionmaker[AsyncSession],
    db_session: AsyncSession,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Submit one root validate_product task.

    Asserts the full audit chain:
      1  USER→TL root
      1  TL   → broadcast (DAG preview)
      3  TL   → agent parallel assignments (MR, Architect, PM)
      3  agent → TL DONE reports
      1  TL   → QA assignment (gated on comp + tech + rev)
      1  QA   → TL DONE report
    Plus 1 pending_review row (QA safety-net inserts it since the mocked LLM
    does not invoke the MCP tool).
    """
    _ = db_session  # ensures _alembic_upgrade ran

    # Redirect file outputs to tmp_path so the test doesn't pollute
    # the actual repo's docs/products/ directory.
    monkeypatch.setattr("agents.market_researcher.agent._REPO_ROOT", tmp_path)
    monkeypatch.setattr(
        "agents.market_researcher.agent._VALIDATE_DIR",
        tmp_path / "docs" / "products",
    )
    monkeypatch.setattr("agents.architect.agent._REPO_ROOT", tmp_path)
    monkeypatch.setattr(
        "agents.architect.agent._VALIDATE_DIR",
        tmp_path / "docs" / "products",
    )
    monkeypatch.setattr("agents.product_manager.agent._REPO_ROOT", tmp_path)
    monkeypatch.setattr(
        "agents.product_manager.agent._VALIDATE_DIR",
        tmp_path / "docs" / "products",
    )
    monkeypatch.setattr("agents.qa_engineer.agent._REPO_ROOT", tmp_path)
    monkeypatch.setattr(
        "agents.qa_engineer.agent._VALIDATE_DIR",
        tmp_path / "docs" / "products",
    )

    bus = MessageBus.from_url(redis_url)
    feed = FeedPublisher.from_url(redis_url, db_session_factory=session_factory)
    signer = HMACSigner(_SECRET)
    audit = AuditLogWriter(session_factory, _SECRET)

    llm = _ValidateScriptedLLM()

    agents = {
        AgentId.TEAM_LEAD: TeamLeadAgent(llm=llm),
        AgentId.MARKET_RESEARCHER: MarketResearcherAgent(llm=llm),
        AgentId.ARCHITECT: ArchitectAgent(llm=llm),
        AgentId.PRODUCT_MANAGER: ProductManagerAgent(llm=llm),
        AgentId.QA_ENGINEER: QAEngineerAgent(llm=llm, session_factory=session_factory),
    }
    task_state = TaskStateReducer(session_factory)
    dispatcher = AgentDispatcher(
        bus=bus,
        feed=feed,
        audit=audit,
        signer=signer,
        agents=agents,
        iteration=26,
        task_state=task_state,
    )

    dispatch_task = asyncio.create_task(dispatcher.run())

    correlation_id = uuid4()
    root_task_id = uuid4()
    user_msg = signer.with_signature(
        AgentMessage(
            correlation_id=correlation_id,
            sender=AgentId.USER,
            recipient=AgentId.TEAM_LEAD,
            message_type=MessageType.TASK_ASSIGNMENT,
            priority=Priority.P2,
            payload=TaskAssignmentPayload(
                task_id=root_task_id,
                title="iter-26b e2e validate-product",
                description=(
                    "Validate telegram-tech-publisher as a candidate product. "
                    "Run competitor, tech-risk, and revenue validation in parallel, "
                    "then synthesize into a go/no-go recommendation."
                ),
                inputs={
                    "intent": "validate_product",
                    "slug": _SLUG,
                    "depth": "quick",
                    "candidate_brief": (
                        "A Telegram bot that auto-generates tech content digests "
                        "for channel owners using an LLM backend."
                    ),
                    "constraints": {
                        "solo_founder": True,
                        "max_build_weeks": 12,
                        "target_mrr_usd": 1000,
                    },
                },
            ),
        )
    )

    # Emulate the API: insert root Task row.
    async with session_factory() as session:
        session.add(
            Task(
                id=root_task_id,
                correlation_id=correlation_id,
                title="iter-26b e2e validate-product",
                description=("Validate telegram-tech-publisher as a candidate product."),
                status="in_progress",
                assigned_agent=AgentId.TEAM_LEAD.value,
                priority=Priority.P2.value,
                iteration=26,
            )
        )
        await session.commit()

    try:
        # Emulate the API: audit the user message then publish.
        await audit.write_message(user_msg, iteration=26)
        await bus.publish(user_msg)

        # ---------- Assertion 1: pending_review row appears (≤90 s) ----------
        deadline = asyncio.get_event_loop().time() + 90
        review_rows: list[PendingReview] = []
        while asyncio.get_event_loop().time() < deadline:
            async with session_factory() as session:
                review_rows = list(
                    (
                        await session.execute(
                            select(PendingReview).where(
                                PendingReview.correlation_id == correlation_id
                            )
                        )
                    )
                    .scalars()
                    .all()
                )
            if review_rows:
                break
            await asyncio.sleep(0.3)

        assert review_rows, (
            f"pending_review row never appeared for correlation_id={correlation_id} after 90s; "
            f"llm.calls={llm.calls}"
        )

        # ---------- Assertion 2: pending_review is from qa_engineer ----------
        qa_review_rows = [r for r in review_rows if r.requesting_agent == "qa_engineer"]
        assert qa_review_rows, (
            f"expected pending_review with requesting_agent='qa_engineer', "
            f"got requesting_agent values={[r.requesting_agent for r in review_rows]}; "
            f"llm.calls={llm.calls}"
        )

        # ---------- Assertion 3: audit-log shape ----------
        async with session_factory() as session:
            all_rows = list(
                (
                    await session.execute(
                        select(AuditLog)
                        .where(AuditLog.correlation_id == correlation_id)
                        .order_by(AuditLog.id)
                    )
                )
                .scalars()
                .all()
            )

        senders = [r.sender for r in all_rows]

        mr_done_rows = [
            r
            for r in all_rows
            if r.sender == AgentId.MARKET_RESEARCHER.value
            and r.message_type == MessageType.TASK_REPORT.value
        ]
        arch_done_rows = [
            r
            for r in all_rows
            if r.sender == AgentId.ARCHITECT.value
            and r.message_type == MessageType.TASK_REPORT.value
        ]
        pm_done_rows = [
            r
            for r in all_rows
            if r.sender == AgentId.PRODUCT_MANAGER.value
            and r.message_type == MessageType.TASK_REPORT.value
        ]
        qa_done_rows = [
            r
            for r in all_rows
            if r.sender == AgentId.QA_ENGINEER.value
            and r.message_type == MessageType.TASK_REPORT.value
        ]

        assert len(mr_done_rows) >= 1, (
            f"expected ≥1 market_researcher TASK_REPORT row, got {len(mr_done_rows)}; "
            f"senders={senders}"
        )
        assert len(arch_done_rows) >= 1, (
            f"expected ≥1 architect TASK_REPORT row, got {len(arch_done_rows)}; senders={senders}"
        )
        assert len(pm_done_rows) >= 1, (
            f"expected ≥1 product_manager TASK_REPORT row, got {len(pm_done_rows)}; "
            f"senders={senders}"
        )
        assert len(qa_done_rows) >= 1, (
            f"expected ≥1 qa_engineer TASK_REPORT row, got {len(qa_done_rows)}; senders={senders}"
        )

        # Each agent report must be DONE.
        for row in mr_done_rows:
            status = row.payload_json.get("payload", {}).get("status")
            assert status == TaskStatus.DONE.value, (
                f"MR report not DONE: status={status!r}; payload={row.payload_json}"
            )
        for row in arch_done_rows:
            status = row.payload_json.get("payload", {}).get("status")
            assert status == TaskStatus.DONE.value, (
                f"Architect report not DONE: status={status!r}; payload={row.payload_json}"
            )
        for row in pm_done_rows:
            status = row.payload_json.get("payload", {}).get("status")
            assert status == TaskStatus.DONE.value, (
                f"PM report not DONE: status={status!r}; payload={row.payload_json}"
            )

        qa_payload = qa_done_rows[0].payload_json.get("payload", {})
        assert qa_payload.get("status") == TaskStatus.DONE.value, (
            f"QA report not DONE: status={qa_payload.get('status')!r}; "
            f"payload={qa_done_rows[0].payload_json}"
        )

        # ---------- Assertion 4: total row count floor ----------
        # Minimum expected rows:
        #   1  user → TL (root)
        #   1  TL   → broadcast (DAG preview)
        #   3  TL   → agent assignments (MR, Architect, PM)
        #   3  agent → TL DONE reports
        #   1  TL   → QA assignment
        #   1  QA   → TL DONE report
        # = 10 rows (conservative floor)
        assert len(all_rows) >= 10, (
            f"expected ≥10 audit rows total, got {len(all_rows)}; senders={senders}"
        )

        # ---------- Assertion 5: artifact files exist ----------
        product_dir = tmp_path / "docs" / "products" / _SLUG
        assert (product_dir / "competitors.md").exists(), (
            f"competitors.md not written to {product_dir}"
        )
        assert (product_dir / "tech_risk.md").exists(), f"tech_risk.md not written to {product_dir}"
        assert (product_dir / "revenue.md").exists(), f"revenue.md not written to {product_dir}"
        summary_file = product_dir / "_validation_summary.md"
        assert summary_file.exists(), f"_validation_summary.md not written to {product_dir}"
        summary_content = summary_file.read_text()
        assert "recommendation: go_with_caveats" in summary_content, (
            f"_validation_summary.md missing 'recommendation: go_with_caveats'; "
            f"content preview: {summary_content[:400]!r}"
        )

        # ---------- Assertion 6: LLM call accounting ----------
        # 1 TL call + 1 MR + 1 Architect + 1 PM + 1 QA = 5 total.
        assert "team_lead" in llm.calls, f"TL was never called; llm.calls={llm.calls}"

        mr_calls = [c for c in llm.calls if c.startswith("market_researcher:")]
        assert len(mr_calls) >= 1, (
            f"expected ≥1 MR LLM call, got {len(mr_calls)}; llm.calls={llm.calls}"
        )
        assert any("validate_competitors" in c for c in mr_calls), (
            f"MR was not called with validate_competitors intent; llm.calls={llm.calls}"
        )

        arch_calls = [c for c in llm.calls if c.startswith("architect:")]
        assert len(arch_calls) >= 1, (
            f"expected ≥1 Architect LLM call, got {len(arch_calls)}; llm.calls={llm.calls}"
        )
        assert any("validate_tech_risk" in c for c in arch_calls), (
            f"Architect was not called with validate_tech_risk intent; llm.calls={llm.calls}"
        )

        pm_calls = [c for c in llm.calls if c.startswith("product_manager:")]
        assert len(pm_calls) >= 1, (
            f"expected ≥1 PM LLM call, got {len(pm_calls)}; llm.calls={llm.calls}"
        )
        assert any("validate_revenue_model" in c for c in pm_calls), (
            f"PM was not called with validate_revenue_model intent; llm.calls={llm.calls}"
        )

        qa_calls = [c for c in llm.calls if c.startswith("qa_engineer:")]
        assert len(qa_calls) >= 1, (
            f"expected ≥1 QA LLM call, got {len(qa_calls)}; llm.calls={llm.calls}"
        )
        assert any("synthesize_validation" in c for c in qa_calls), (
            f"QA was not called with synthesize_validation intent; llm.calls={llm.calls}"
        )

    finally:
        dispatcher.shutdown()
        try:
            await asyncio.wait_for(dispatch_task, timeout=5)
        except (TimeoutError, asyncio.CancelledError):
            dispatch_task.cancel()
        await bus.close()
        await feed.close()
