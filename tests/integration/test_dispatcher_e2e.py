"""End-to-end dispatcher test: user → TL → PM → report.

Uses a `ScriptedLLM` that returns predefined `LLMResponse` based on which
agent's system prompt is invoking it. No real `claude -p` calls.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import pytest
from sqlalchemy import select

from agents._base import BaseAgent
from agents.product_manager import ProductManagerAgent
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
    TaskReportPayload,
    TaskStatus,
)
from core.persistence.models import AuditLog, FeedEvent
from core.security.hmac_signer import HMACSigner

if TYPE_CHECKING:
    from pathlib import Path

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = pytest.mark.integration

_SECRET = b"e" * 64


class ScriptedLLM:
    """Returns scripted responses based on agent role detected in system prompt."""

    def __init__(self, by_role: dict[str, LLMResponse]) -> None:
        self._by_role = by_role
        self.calls: list[str] = []

    async def invoke(self, *, system_prompt: str, **kwargs: Any) -> LLMResponse:
        # Check most-specific role marker first; the PM prompt also contains
        # the substring "Team Lead" (in "from Team Lead").
        head = system_prompt.lstrip()
        if head.startswith("# Role: Product Manager"):
            self.calls.append("product_manager")
            return self._by_role["product_manager"]
        if head.startswith("# Role: Team Lead"):
            self.calls.append("team_lead")
            return self._by_role["team_lead"]
        raise RuntimeError(f"no scripted response for prompt: {system_prompt[:80]}")

    async def reset_session(self, session_id: str) -> None:
        return None


def _tl_response() -> LLMResponse:
    return LLMResponse(
        text="",
        structured={
            "summary": "Route to PM for user stories.",
            "subtasks": [
                {
                    "id": "pm_stories",
                    "recipient": "product_manager",
                    "title": "Generate user stories",
                    "description": "Produce 3-5 stories for the test task.",
                    "priority": "P2",
                    "depends_on": [],
                }
            ],
        },
        tools_used=[],
        session_id="tl-sess",
        tokens=TokensUsage(input=10, output=20, model="claude-opus-4-7"),
        cost_estimate_cents=0,
        duration_ms=100,
        raw={},
    )


def _pm_response() -> LLMResponse:
    return LLMResponse(
        text="",
        structured={
            "summary": "3 stories drafted: signup, onboarding, retention.",
            "stories": [
                {
                    "id": "US-1",
                    "as_a": "solo founder",
                    "i_want": "sign up with a single click",
                    "so_that": "I can start using the product within seconds",
                    "acceptance_criteria": [
                        "User reaches dashboard within 5s of clicking signup",
                        "No required fields beyond email",
                    ],
                    "priority": "P2",
                }
            ],
        },
        tools_used=[],
        session_id="pm-sess",
        tokens=TokensUsage(input=10, output=30, model="claude-sonnet-4-6"),
        cost_estimate_cents=0,
        duration_ms=100,
        raw={},
    )


async def test_user_to_tl_to_pm_to_report(
    redis_url: str,
    session_factory: async_sessionmaker[AsyncSession],
    db_session: AsyncSession,
) -> None:
    bus = MessageBus.from_url(redis_url)
    feed = FeedPublisher.from_url(redis_url, db_session_factory=session_factory)
    signer = HMACSigner(_SECRET)
    audit = AuditLogWriter(session_factory, _SECRET)

    llm = ScriptedLLM({"team_lead": _tl_response(), "product_manager": _pm_response()})

    agents = {
        AgentId.TEAM_LEAD: TeamLeadAgent(llm=llm),
        AgentId.PRODUCT_MANAGER: ProductManagerAgent(llm=llm),
    }
    dispatcher = AgentDispatcher(
        bus=bus,
        feed=feed,
        audit=audit,
        signer=signer,
        agents=agents,
        iteration=1,
    )

    task = asyncio.create_task(dispatcher.run())

    correlation_id = uuid4()
    user_msg = signer.with_signature(
        AgentMessage(
            correlation_id=correlation_id,
            sender=AgentId.USER,
            recipient=AgentId.TEAM_LEAD,
            message_type=MessageType.TASK_ASSIGNMENT,
            priority=Priority.P2,
            payload=TaskAssignmentPayload(
                task_id=uuid4(),
                title="iter-1 e2e test",
                description="Validate the dispatcher loop end-to-end.",
            ),
        )
    )

    try:
        # The API would audit the user message; emulate that here.
        await audit.write_message(user_msg, iteration=1)
        await bus.publish(user_msg)

        # Wait until 3 audit rows exist for this correlation:
        # user→TL (we just wrote), TL→PM (dispatcher), PM→TL (dispatcher).
        deadline = asyncio.get_event_loop().time() + 30
        rows: list[AuditLog] = []
        while asyncio.get_event_loop().time() < deadline:
            async with session_factory() as session:
                rows = list(
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
            if len(rows) >= 3:
                break
            await asyncio.sleep(0.2)

        assert len(rows) >= 3, f"only {len(rows)} audit rows after 30s"

        # Three distinct senders.
        senders = [r.sender for r in rows[:3]]
        debug = [
            (
                r.id,
                r.sender,
                r.recipient,
                r.message_type,
                str(r.payload_json.get("message_id"))[:8] if r.payload_json else "?",
            )
            for r in rows
        ]
        expected = ["user", "team_lead", "product_manager"]
        assert senders == expected, f"senders={senders} debug={debug}"

        # Chain verification is covered by test_audit_writer (which
        # intentionally tampers with rows). Here we just check that the
        # rows we expect are present and the LLM was called as expected.
        assert llm.calls == ["team_lead", "product_manager"]

        # Feed_events captured the TL→PM and PM→TL hops. Poll briefly: feed
        # publishes happen after audit writes and may lag a few hundred ms.
        feed_deadline = asyncio.get_event_loop().time() + 10
        feed_senders: list[str] = []
        while asyncio.get_event_loop().time() < feed_deadline:
            async with session_factory() as session:
                feed_rows = list(
                    (
                        await session.execute(
                            select(FeedEvent).where(FeedEvent.correlation_id == correlation_id)
                        )
                    )
                    .scalars()
                    .all()
                )
            feed_senders = sorted(r.sender for r in feed_rows)
            if "team_lead" in feed_senders and "product_manager" in feed_senders:
                break
            await asyncio.sleep(0.2)
        assert "team_lead" in feed_senders, f"feed_senders={feed_senders}"
        assert "product_manager" in feed_senders, f"feed_senders={feed_senders}"
    finally:
        dispatcher.shutdown()
        try:
            await asyncio.wait_for(task, timeout=5)
        except (TimeoutError, asyncio.CancelledError):
            task.cancel()
        await bus.close()
        await feed.close()


# === iter-3 Phase 2D: three-stage dependency-ordered chain ===


class _StaticDoneAgent(BaseAgent):
    """Stub agent for the depends_on integration test.

    On any TASK_ASSIGNMENT, returns a TASK_REPORT(DONE) carrying the same
    task_id. The role / model_tier / system_prompt_path are all minimal
    placeholders — this agent doesn't invoke the LLM.
    """

    role: Any = AgentId.ARCHITECT  # overridden per-instance in fixture
    model_tier: Any = "sonnet"
    allowed_tools: tuple[str, ...] = ()
    system_prompt_path: Path = None  # type: ignore[assignment]

    def __init__(self, *, role: AgentId, observer: list[AgentMessage]) -> None:
        self.role = role  # type: ignore[misc]
        self._observer = observer
        self._llm = None  # not used

    def system_prompt(self) -> str:
        return f"# Role: {self.role.value}\nStub agent for tests.\n"

    async def handle(self, msg: AgentMessage) -> list[AgentMessage]:
        if msg.message_type != MessageType.TASK_ASSIGNMENT:
            return []
        if not isinstance(msg.payload, TaskAssignmentPayload):
            return []
        self._observer.append(msg)
        return [
            AgentMessage(
                correlation_id=msg.correlation_id,
                sender=self.role,
                recipient=AgentId.TEAM_LEAD,
                message_type=MessageType.TASK_REPORT,
                priority=Priority.P3,
                payload=TaskReportPayload(
                    task_id=msg.payload.task_id,
                    status=TaskStatus.DONE,
                    progress_pct=100,
                    summary=f"{self.role.value} done",
                ),
            )
        ]

    def build_outputs(
        self,
        response: LLMResponse,
        incoming: AgentMessage,
    ) -> list[AgentMessage]:
        del response, incoming  # not used by this stub; handle() builds outputs directly
        return []


def _tl_three_stage_response() -> LLMResponse:
    """TL emits a 3-stage DAG: arch → be → qa."""
    return LLMResponse(
        text="",
        structured={
            "summary": "Three-stage chain test.",
            "subtasks": [
                {
                    "id": "arch",
                    "recipient": "architect",
                    "title": "Design",
                    "description": "Write a tiny ADR.",
                    "priority": "P2",
                    "depends_on": [],
                },
                {
                    "id": "be",
                    "recipient": "backend_developer",
                    "title": "Build",
                    "description": "Implement per ADR.",
                    "priority": "P2",
                    "depends_on": ["arch"],
                },
                {
                    "id": "qa",
                    "recipient": "qa_engineer",
                    "title": "Verify",
                    "description": "Run tests.",
                    "priority": "P3",
                    "depends_on": ["be"],
                },
            ],
        },
        tools_used=[],
        session_id="tl-3stage",
        tokens=TokensUsage(input=10, output=20, model="claude-opus-4-7"),
        cost_estimate_cents=0,
        duration_ms=100,
        raw={},
    )


class _OnlyTLResponseLLM:
    """Used by TL only — stub agents in this test don't invoke the LLM."""

    def __init__(self, tl_response: LLMResponse) -> None:
        self._tl_response = tl_response
        self.calls: list[str] = []

    async def invoke(self, *, system_prompt: str, **kwargs: Any) -> LLMResponse:
        head = system_prompt.lstrip()
        if head.startswith("# Role: Team Lead"):
            self.calls.append("team_lead")
            return self._tl_response
        raise RuntimeError(f"no scripted response for prompt: {system_prompt[:80]}")

    async def reset_session(self, session_id: str) -> None:
        return None


async def test_dependency_ordered_three_stage_chain(
    redis_url: str,
    session_factory: async_sessionmaker[AsyncSession],
    db_session: AsyncSession,
) -> None:
    _ = db_session  # ensures schema-setup fixture ran before this test
    """TL emits arch → be → qa with depends_on; HoldQueue gates ordering.

    Asserts:
      - arch's TASK_ASSIGNMENT lands on the bus BEFORE be's
      - be's TASK_ASSIGNMENT lands BEFORE qa's
      - all three terminal TASK_REPORTs eventually arrive
      - HoldQueue ends empty (no held messages leak)
    """
    bus = MessageBus.from_url(redis_url)
    feed = FeedPublisher.from_url(redis_url, db_session_factory=session_factory)
    signer = HMACSigner(_SECRET)
    audit = AuditLogWriter(session_factory, _SECRET)

    llm = _OnlyTLResponseLLM(_tl_three_stage_response())
    arch_received: list[AgentMessage] = []
    be_received: list[AgentMessage] = []
    qa_received: list[AgentMessage] = []

    agents = {
        AgentId.TEAM_LEAD: TeamLeadAgent(llm=llm),
        AgentId.ARCHITECT: _StaticDoneAgent(role=AgentId.ARCHITECT, observer=arch_received),
        AgentId.BACKEND_DEVELOPER: _StaticDoneAgent(
            role=AgentId.BACKEND_DEVELOPER, observer=be_received
        ),
        AgentId.QA_ENGINEER: _StaticDoneAgent(role=AgentId.QA_ENGINEER, observer=qa_received),
    }
    dispatcher = AgentDispatcher(
        bus=bus,
        feed=feed,
        audit=audit,
        signer=signer,
        agents=agents,
        iteration=3,
    )

    task = asyncio.create_task(dispatcher.run())

    correlation_id = uuid4()
    user_msg = signer.with_signature(
        AgentMessage(
            correlation_id=correlation_id,
            sender=AgentId.USER,
            recipient=AgentId.TEAM_LEAD,
            message_type=MessageType.TASK_ASSIGNMENT,
            priority=Priority.P2,
            payload=TaskAssignmentPayload(
                task_id=uuid4(),
                title="3-stage e2e",
                description="Validate dependency ordering.",
            ),
        )
    )

    try:
        await audit.write_message(user_msg, iteration=3)
        await bus.publish(user_msg)

        # Wait for all 7 audit rows (user→TL, TL→arch/be/qa,
        # arch→TL, be→TL, qa→TL).
        deadline = asyncio.get_event_loop().time() + 30
        rows: list[AuditLog] = []
        while asyncio.get_event_loop().time() < deadline:
            async with session_factory() as session:
                rows = list(
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
            if len(rows) >= 7:
                break
            await asyncio.sleep(0.2)

        assert len(rows) >= 7, (
            f"only {len(rows)} audit rows after 30s; senders={[r.sender for r in rows]}"
        )

        # All three stub agents received exactly one assignment.
        assert len(arch_received) == 1
        assert len(be_received) == 1
        assert len(qa_received) == 1

        # Ground truth for ordering is the stubs' observer lists —
        # _StaticDoneAgent appends only when the dispatcher actually
        # delivers via the bus. HoldQueue gates that delivery, so
        # receipt order is the chain order regardless of when the
        # intent (audit row) was written.
        arch_payload = arch_received[0].payload
        be_payload = be_received[0].payload
        assert isinstance(arch_payload, TaskAssignmentPayload)
        assert isinstance(be_payload, TaskAssignmentPayload)

        # Cross-check the depends_on metadata reflects the chain.
        assert be_received[0].metadata.get("depends_on") == [str(arch_payload.task_id)]
        assert qa_received[0].metadata.get("depends_on") == [str(be_payload.task_id)]

        # Audit-row id ordering: the architect's TASK_REPORT(done) must
        # appear strictly before the backend_developer's TASK_REPORT(done).
        # If be ran in parallel with arch (no hold), be's report would
        # likely land first because the stub agents are trivially fast
        # and the TL emits all three assignments in one batch.
        def _row_id(sender: str, message_type: str) -> int:
            for r in rows:
                if r.sender == sender and r.message_type == message_type:
                    return r.id
            raise AssertionError(f"no row sender={sender} type={message_type}")

        arch_done_id = _row_id("architect", "task_report")
        be_done_id = _row_id("backend_developer", "task_report")
        qa_done_id = _row_id("qa_engineer", "task_report")
        assert arch_done_id < be_done_id < qa_done_id, (
            f"chain order broken: arch_done={arch_done_id} "
            f"be_done={be_done_id} qa_done={qa_done_id}"
        )

        # HoldQueue is empty at end (no leaks).
        held = dispatcher._hold_queue._held
        for cid, items in held.items():
            assert items == [], f"held messages remain at end of test: cid={cid} items={items}"

        assert llm.calls == ["team_lead"]
    finally:
        dispatcher.shutdown()
        try:
            await asyncio.wait_for(task, timeout=5)
        except (TimeoutError, asyncio.CancelledError):
            task.cancel()
        await bus.close()
        await feed.close()
