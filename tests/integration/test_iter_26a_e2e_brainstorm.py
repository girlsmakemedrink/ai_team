"""End-to-end iter-26a chain on Postgres + Redis + mocked LLM.

Asserts the full audit chain shape: 1 root → 3 MR assignments →
3 MR DONE → 1 QA assignment → 1 QA DONE → 1 pending_review row.

Real LLM coverage is in tests/integration/test_mr_brainstorm_one_niche_real_llm.py.

Template: tests/integration/test_dispatcher_e2e.py
(ScriptedLLM pattern, session-scoped testcontainers Postgres + Redis,
poll-until-done, dispatcher.shutdown() in finally.)
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import pytest
from sqlalchemy import select

from agents.market_researcher import MarketResearcherAgent
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

_SECRET = b"f" * 64  # distinct from other e2e tests to avoid HMAC cross-contamination

# ---------------------------------------------------------------------------
# Scripted LLM responses
# ---------------------------------------------------------------------------


def _tl_brainstorm_response() -> LLMResponse:
    """TL decomposes 'brainstorm_products' into 3 MR subtasks + 1 QA gated subtask."""
    return LLMResponse(
        text="",
        structured={
            "summary": (
                "Decomposing brainstorm_products into 3 parallel Market Researcher "
                "niche brainstorms (dev_tools, b2b_smb, creator_tools) and one "
                "QA ranking step gated on all three."
            ),
            "subtasks": [
                {
                    "id": "mr_dev_tools",
                    "recipient": "market_researcher",
                    "title": "Brainstorm dev_tools niche",
                    "description": (
                        "Brainstorm 5 monetizable SaaS/tool ideas in the dev_tools niche."
                    ),
                    "priority": "P2",
                    "depends_on": [],
                    "inputs": {
                        "mode": "brainstorm_niche",
                        "niche": "dev_tools",
                    },
                },
                {
                    "id": "mr_b2b_smb",
                    "recipient": "market_researcher",
                    "title": "Brainstorm b2b_smb niche",
                    "description": "Brainstorm 5 monetizable SaaS/tool ideas in the b2b_smb niche.",
                    "priority": "P2",
                    "depends_on": [],
                    "inputs": {
                        "mode": "brainstorm_niche",
                        "niche": "b2b_smb",
                    },
                },
                {
                    "id": "mr_creator_tools",
                    "recipient": "market_researcher",
                    "title": "Brainstorm creator_tools niche",
                    "description": (
                        "Brainstorm 5 monetizable SaaS/tool ideas in the creator_tools niche."
                    ),
                    "priority": "P2",
                    "depends_on": [],
                    "inputs": {
                        "mode": "brainstorm_niche",
                        "niche": "creator_tools",
                    },
                },
                {
                    "id": "qa_rank",
                    "recipient": "qa_engineer",
                    "title": "Rank brainstorm candidates",
                    "description": (
                        "Merge and rank all three niche brainstorms into a top-3 shortlist."
                    ),
                    "priority": "P2",
                    "depends_on": ["mr_dev_tools", "mr_b2b_smb", "mr_creator_tools"],
                    "inputs": {
                        "intent": "rank_brainstorm_candidates",
                    },
                },
            ],
        },
        tools_used=[],
        session_id="tl-brainstorm-e2e",
        tokens=TokensUsage(input=10, output=40, model="claude-opus-4-7"),
        cost_estimate_cents=0,
        duration_ms=100,
        raw={},
    )


def _make_candidate(niche: str, idx: int) -> dict[str, Any]:
    """Build one valid candidate dict. composite_score == sum of 5 axes (each=3 → 15)."""
    return {
        "title": f"{niche.capitalize()} Idea {idx}",
        "slug": f"{niche}-{idx}",
        "one_paragraph": f"A SaaS product in the {niche} space targeting solo founders. "
        f"This is candidate {idx}.",
        "target_buyer": "Solo founder / indie hacker",
        "monetization": "subscription",
        "known_competitors": [
            {
                "name": "CompetitorA",
                "url": "https://example.com",
                "positioning": "Enterprise focus",
            },
        ],
        "scores": {
            "tam_signal": 3,
            "solo_fit": 3,
            "llm_opex_fit": 3,
            "defensibility": 3,
            "time_to_first_revenue": 3,
        },
        "composite_score": 15,  # sum of 5 axes each=3: 5*3=15
        "rationale": f"Solid fit for {niche} niche. Moderate across all axes.",
    }


def _mr_response(niche: str) -> LLMResponse:
    """MR returns a BRAINSTORM_NICHE_SCHEMA-valid response for the given niche."""
    candidates = [_make_candidate(niche, i) for i in range(5)]
    top_3_slugs = [f"{niche}-{i}" for i in range(3)]
    return LLMResponse(
        text="",
        structured={
            "niche": niche,
            "candidates": candidates,
            "researcher_top_3_slugs": top_3_slugs,
            "research_sources_used": ["https://hn.algolia.com", "https://trends.google.com"],
        },
        tools_used=[],
        session_id=f"mr-{niche}-e2e",
        tokens=TokensUsage(input=10, output=50, model="claude-sonnet-4-6"),
        cost_estimate_cents=0,
        duration_ms=100,
        raw={},
    )


def _qa_rank_response() -> LLMResponse:
    """QA returns a RANK_BRAINSTORM_SCHEMA-valid response."""
    return LLMResponse(
        text="",
        structured={
            "intent_completed": "rank_brainstorm_candidates",
            "ranking_summary": (
                "All three niche brainstorms reviewed. dev_tools scores highest for "
                "solo-fit and TAM; b2b_smb is close second; creator_tools has highest "
                "time-to-first-revenue potential."
            ),
            "top_3_overall": ["dev_tools-0", "b2b_smb-0", "creator_tools-0"],
        },
        tools_used=[],
        session_id="qa-rank-e2e",
        tokens=TokensUsage(input=10, output=30, model="claude-sonnet-4-6"),
        cost_estimate_cents=0,
        duration_ms=100,
        raw={},
    )


class _BrainstormScriptedLLM:
    """Scripted LLM that routes by role detected from the system prompt header.

    Detection mirrors the pattern in test_dispatcher_e2e.py: check the
    stripped prompt prefix against 'Role: <RoleName>' literals. MR receives
    3 separate calls (one per niche). QA receives 1 call.
    """

    def __init__(self) -> None:
        self.calls: list[str] = []
        # Pre-load scripted responses.
        self._tl_resp = _tl_brainstorm_response()
        self._mr_responses = {
            "dev_tools": _mr_response("dev_tools"),
            "b2b_smb": _mr_response("b2b_smb"),
            "creator_tools": _mr_response("creator_tools"),
        }
        self._qa_resp = _qa_rank_response()

    async def invoke(
        self, *, system_prompt: str, user_message: str = "", **kwargs: Any
    ) -> LLMResponse:
        head = system_prompt.lstrip()
        if head.startswith("# Role: Team Lead"):
            self.calls.append("team_lead")
            return self._tl_resp
        if head.startswith("# Role: Market Researcher"):
            # Detect which niche from user_message (inputs are embedded there).
            niche = self._detect_niche(user_message, **kwargs)
            self.calls.append(f"market_researcher:{niche}")
            return self._mr_responses[niche]
        if head.startswith("# Role: QA Engineer"):
            self.calls.append("qa_engineer")
            return self._qa_resp
        raise RuntimeError(f"no scripted response for prompt header: {head[:80]!r}")

    def _detect_niche(self, user_message: str, **_kwargs: Any) -> str:
        """Detect niche by scanning the user message for niche keywords."""
        for niche in ("dev_tools", "b2b_smb", "creator_tools"):
            if niche in user_message:
                return niche
        # Fallback: scan kwargs for json_schema 'niche' enum
        # (shouldn't be needed, but defensive).
        raise RuntimeError(f"could not detect niche from user_message: {user_message[:200]!r}")

    async def reset_session(self, session_id: str) -> None:
        return None


# ---------------------------------------------------------------------------
# The test
# ---------------------------------------------------------------------------


async def test_brainstorm_products_full_chain(
    redis_url: str,
    session_factory: async_sessionmaker[AsyncSession],
    db_session: AsyncSession,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Submit one root brainstorm_products task.

    Asserts the full audit chain:
      1 USER→TL root
      1 TL broadcast (DAG preview)
      3 TL→MR assignments
      3 MR→TL DONE reports
      1 TL→QA assignment (gated on all 3 MR)
      1 QA→TL DONE report
    Plus 1 pending_review row (QA safety-net inserts it since MockLLM
    doesn't actually call the MCP tool).
    """
    _ = db_session  # ensures _alembic_upgrade ran

    # Redirect MR + QA file outputs to tmp_path so the test doesn't pollute
    # the actual repo's docs/products/ directory. Also redirect _REPO_ROOT
    # because QA's _build_rank_outputs computes paths relative to it.
    monkeypatch.setattr("agents.market_researcher.agent._REPO_ROOT", tmp_path)
    monkeypatch.setattr(
        "agents.market_researcher.agent._BRAINSTORM_DIR",
        tmp_path / "docs" / "products" / "_candidates",
    )
    monkeypatch.setattr("agents.qa_engineer.agent._REPO_ROOT", tmp_path)
    monkeypatch.setattr(
        "agents.qa_engineer.agent._RANKING_DIR",
        tmp_path / "docs" / "products" / "_candidates",
    )

    bus = MessageBus.from_url(redis_url)
    feed = FeedPublisher.from_url(redis_url, db_session_factory=session_factory)
    signer = HMACSigner(_SECRET)
    audit = AuditLogWriter(session_factory, _SECRET)

    llm = _BrainstormScriptedLLM()

    agents = {
        AgentId.TEAM_LEAD: TeamLeadAgent(llm=llm),
        AgentId.MARKET_RESEARCHER: MarketResearcherAgent(llm=llm),
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
                title="iter-26a e2e brainstorm",
                description="Brainstorm monetizable product candidates across 3 niches.",
                inputs={"intent": "brainstorm_products"},
            ),
        )
    )

    # Emulate the API: insert root Task row.
    async with session_factory() as session:
        session.add(
            Task(
                id=root_task_id,
                correlation_id=correlation_id,
                title="iter-26a e2e brainstorm",
                description="Brainstorm monetizable product candidates across 3 niches.",
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

        # ---------- Assertion 1: pending_review row appears (≤60 s) ----------
        deadline = asyncio.get_event_loop().time() + 60
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
            f"pending_review row never appeared for correlation_id={correlation_id} after 60s; "
            f"llm.calls={llm.calls}"
        )

        # ---------- Assertion 2: audit-log shape ----------
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
        qa_done_rows = [
            r
            for r in all_rows
            if r.sender == AgentId.QA_ENGINEER.value
            and r.message_type == MessageType.TASK_REPORT.value
        ]

        assert len(mr_done_rows) >= 3, (
            f"expected ≥3 market_researcher TASK_REPORT rows, got {len(mr_done_rows)}; "
            f"senders={senders}"
        )
        assert len(qa_done_rows) >= 1, (
            f"expected ≥1 qa_engineer TASK_REPORT row, got {len(qa_done_rows)}; senders={senders}"
        )

        # Each MR report must be DONE.
        for row in mr_done_rows:
            mr_status = row.payload_json.get("payload", {}).get("status")
            assert mr_status == TaskStatus.DONE.value, (
                f"MR report not DONE: status={mr_status!r}; payload={row.payload_json}"
            )

        # QA report must be DONE.
        qa_payload = qa_done_rows[0].payload_json.get("payload", {})
        assert qa_payload.get("status") == TaskStatus.DONE.value, (
            f"QA report not DONE: status={qa_payload.get('status')!r}; "
            f"payload={qa_done_rows[0].payload_json}"
        )

        # ---------- Assertion 3: total row count floor ----------
        # Minimum expected rows:
        #   1  user → TL (root)
        #   1  TL   → broadcast (DAG preview)
        #   3  TL   → MR assignments
        #   3  MR   → TL DONE reports
        #   1  TL   → QA assignment
        #   1  QA   → TL DONE report
        # = 10 rows (conservative floor = 9 per spec)
        assert len(all_rows) >= 9, (
            f"expected ≥9 audit rows total, got {len(all_rows)}; senders={senders}"
        )

        # ---------- Assertion 4: LLM call accounting ----------
        # 1 TL call + 3 MR calls (one per niche) + 1 QA call = 5 total.
        assert "team_lead" in llm.calls, f"TL was never called; llm.calls={llm.calls}"
        mr_calls = [c for c in llm.calls if c.startswith("market_researcher:")]
        assert len(mr_calls) == 3, (
            f"expected 3 MR LLM calls (one per niche), got {len(mr_calls)}; llm.calls={llm.calls}"
        )
        mr_niches_called = {c.split(":")[1] for c in mr_calls}
        assert mr_niches_called == {"dev_tools", "b2b_smb", "creator_tools"}, (
            f"MR niche calls mismatch: {mr_niches_called}"
        )
        assert "qa_engineer" in llm.calls, f"QA was never called; llm.calls={llm.calls}"

    finally:
        dispatcher.shutdown()
        try:
            await asyncio.wait_for(dispatch_task, timeout=5)
        except (TimeoutError, asyncio.CancelledError):
            dispatch_task.cancel()
        await bus.close()
        await feed.close()
