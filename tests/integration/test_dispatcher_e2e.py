"""End-to-end dispatcher test: user → TL → PM → report.

Uses a `ScriptedLLM` that returns predefined `LLMResponse` based on which
agent's system prompt is invoking it. No real `claude -p` calls.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar
from uuid import uuid4

import pytest
from sqlalchemy import select

from agents._base import BaseAgent
from agents.product_manager import ProductManagerAgent
from agents.team_lead import TeamLeadAgent
from core.audit.writer import AuditLogWriter
from core.dispatcher import AgentDispatcher
from core.llm.base import LLMBudgetExhaustedError, LLMResponse, TokensUsage
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
from core.persistence.models import AuditLog, FeedEvent, Task
from core.persistence.task_state import TaskStateReducer
from core.security.hmac_signer import HMACSigner

if TYPE_CHECKING:
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

        # Wait until 4 audit rows exist for this correlation:
        # user→TL (we just wrote), TL→broadcast (iter-4 DAG preview),
        # TL→PM (dispatcher), PM→TL (dispatcher).
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
            if len(rows) >= 4:
                break
            await asyncio.sleep(0.2)

        assert len(rows) >= 4, f"only {len(rows)} audit rows after 30s"

        senders = [r.sender for r in rows]
        message_types = [r.message_type for r in rows]
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
        # User submits, then TL emits two messages (DAG preview broadcast
        # + PM task_assignment), then PM reports back.
        assert senders[0] == "user", f"senders={senders} debug={debug}"
        assert senders.count("team_lead") == 2, f"senders={senders} debug={debug}"
        assert "product_manager" in senders, f"senders={senders} debug={debug}"
        # iter-4: TL must emit exactly one DAG preview broadcast alongside
        # the task assignment.
        assert message_types.count("broadcast") == 1, f"message_types={message_types} debug={debug}"

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


class _StaticDoneAgentBase(BaseAgent):
    """Stub base: returns one TASK_REPORT(DONE) per incoming TASK_ASSIGNMENT.

    Subclasses fix `role` as a ClassVar (mypy-friendly) and pass an
    observer list to capture every message the dispatcher delivered.
    """

    system_prompt_path: ClassVar[Path] = Path("/dev/null")

    def __init__(self, *, observer: list[AgentMessage]) -> None:
        # Intentionally skip BaseAgent.__init__ — the stub never calls
        # the LLM and doesn't need a system prompt loader.
        self._observer = observer
        self._cached_prompt: str | None = None

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
        del response, incoming  # stub's handle() builds outputs directly
        return []


class _StubArchitect(_StaticDoneAgentBase):
    role: ClassVar[AgentId] = AgentId.ARCHITECT


class _StubBackend(_StaticDoneAgentBase):
    role: ClassVar[AgentId] = AgentId.BACKEND_DEVELOPER


class _StubQA(_StaticDoneAgentBase):
    role: ClassVar[AgentId] = AgentId.QA_ENGINEER


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
        AgentId.ARCHITECT: _StubArchitect(observer=arch_received),
        AgentId.BACKEND_DEVELOPER: _StubBackend(observer=be_received),
        AgentId.QA_ENGINEER: _StubQA(observer=qa_received),
    }
    task_state = TaskStateReducer(session_factory)
    dispatcher = AgentDispatcher(
        bus=bus,
        feed=feed,
        audit=audit,
        signer=signer,
        agents=agents,
        iteration=3,
        task_state=task_state,
    )

    task = asyncio.create_task(dispatcher.run())

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
                title="3-stage e2e",
                description="Validate dependency ordering.",
            ),
        )
    )

    # Emulate the API: insert the root Task row when the user submits.
    async with session_factory() as session:
        session.add(
            Task(
                id=root_task_id,
                correlation_id=correlation_id,
                title="3-stage e2e",
                description="Validate dependency ordering.",
                status="in_progress",
                assigned_agent=AgentId.TEAM_LEAD.value,
                priority=Priority.P2.value,
                iteration=3,
            )
        )
        await session.commit()

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

        # Root-task rollup: three children inserted, each marked `done`,
        # parent flipped to `done`.
        async with session_factory() as session:
            children = (
                (await session.execute(select(Task).where(Task.parent_task_id == root_task_id)))
                .scalars()
                .all()
            )
            root = (await session.execute(select(Task).where(Task.id == root_task_id))).scalar_one()
        assert len(children) == 3, f"expected 3 child rows, got {len(children)}"
        child_statuses = sorted(c.status for c in children)
        assert child_statuses == ["done", "done", "done"], (
            f"unexpected child statuses: {child_statuses}"
        )
        assert root.status == "done", f"root.status={root.status!r}; expected 'done'"
    finally:
        dispatcher.shutdown()
        try:
            await asyncio.wait_for(task, timeout=5)
        except (TimeoutError, asyncio.CancelledError):
            task.cancel()
        await bus.close()
        await feed.close()


# === iter-5 Phase 1: agent handle() exception → synthesised TASK_REPORT(failed) ===


class _RaisingBackend(BaseAgent):
    """Stub Backend whose handle() always raises. Iter-5 dispatcher
    must catch the exception and emit a synthetic TASK_REPORT(failed)
    on the agent's behalf so HoldQueue / rollup see a terminal status."""

    role: ClassVar[AgentId] = AgentId.BACKEND_DEVELOPER
    system_prompt_path: ClassVar[Path] = Path("/dev/null")

    def __init__(self) -> None:
        # Intentionally skip BaseAgent.__init__ — stub never invokes the LLM.
        self._cached_prompt: str | None = None

    def system_prompt(self) -> str:
        return "# Role: Backend Developer\nStub agent for tests.\n"

    async def handle(self, msg: AgentMessage) -> list[AgentMessage]:
        del msg
        raise RuntimeError("simulated backend crash for iter-5 dispatcher test")

    def build_outputs(
        self,
        response: LLMResponse,
        incoming: AgentMessage,
    ) -> list[AgentMessage]:
        del response, incoming  # stub never reaches build_outputs
        return []


def _tl_single_be_response() -> LLMResponse:
    """TL emits a 1-subtask DAG: just be (no deps)."""
    return LLMResponse(
        text="",
        structured={
            "summary": "Single backend subtask.",
            "subtasks": [
                {
                    "id": "be",
                    "recipient": "backend_developer",
                    "title": "Build",
                    "description": "Implement something.",
                    "priority": "P2",
                    "depends_on": [],
                }
            ],
        },
        tools_used=[],
        session_id="tl-iter5",
        tokens=TokensUsage(input=10, output=20, model="claude-opus-4-7"),
        cost_estimate_cents=0,
        duration_ms=100,
        raw={},
    )


async def test_agent_handle_exception_synthesises_failed_report(
    redis_url: str,
    session_factory: async_sessionmaker[AsyncSession],
    db_session: AsyncSession,
) -> None:
    _ = db_session
    """When Backend's handle() raises, the dispatcher must synthesise a
    TASK_REPORT(failed) so the rollup + HoldQueue see a terminal status
    instead of leaving the chain hung (iter-4 demo Backend exit-1)."""
    bus = MessageBus.from_url(redis_url)
    feed = FeedPublisher.from_url(redis_url, db_session_factory=session_factory)
    signer = HMACSigner(_SECRET)
    audit = AuditLogWriter(session_factory, _SECRET)

    llm = _OnlyTLResponseLLM(_tl_single_be_response())

    agents = {
        AgentId.TEAM_LEAD: TeamLeadAgent(llm=llm),
        AgentId.BACKEND_DEVELOPER: _RaisingBackend(),
    }
    task_state = TaskStateReducer(session_factory)
    dispatcher = AgentDispatcher(
        bus=bus,
        feed=feed,
        audit=audit,
        signer=signer,
        agents=agents,
        iteration=5,
        task_state=task_state,
    )

    task = asyncio.create_task(dispatcher.run())

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
                title="iter-5 exception path",
                description="Backend will crash; dispatcher must synthesise.",
            ),
        )
    )

    async with session_factory() as session:
        session.add(
            Task(
                id=root_task_id,
                correlation_id=correlation_id,
                title="iter-5 exception path",
                description="Backend will crash; dispatcher must synthesise.",
                status="in_progress",
                assigned_agent=AgentId.TEAM_LEAD.value,
                priority=Priority.P2.value,
                iteration=5,
            )
        )
        await session.commit()

    try:
        await audit.write_message(user_msg, iteration=5)
        await bus.publish(user_msg)

        # Wait for a synthesised TASK_REPORT(failed) row from Backend.
        # Chain: user→TL, TL→broadcast (DAG preview), TL→be, be→TL (synth failed).
        deadline = asyncio.get_event_loop().time() + 15
        failed_rows: list[AuditLog] = []
        while asyncio.get_event_loop().time() < deadline:
            async with session_factory() as session:
                failed_rows = list(
                    (
                        await session.execute(
                            select(AuditLog)
                            .where(AuditLog.correlation_id == correlation_id)
                            .where(AuditLog.sender == AgentId.BACKEND_DEVELOPER.value)
                            .where(AuditLog.message_type == MessageType.TASK_REPORT.value)
                        )
                    )
                    .scalars()
                    .all()
                )
            if failed_rows:
                break
            await asyncio.sleep(0.2)

        assert failed_rows, "no synthesised TASK_REPORT(failed) from Backend after 15s"
        row = failed_rows[0]
        payload = row.payload_json.get("payload", {})
        assert payload.get("status") == TaskStatus.FAILED.value
        # Summary carries the exception type per the synthesis helper.
        assert "RuntimeError" in payload.get("summary", "")

        # Root Task rolled up to failed via derive_parent_status
        # (any-failed dominates per iter-3 rule).
        deadline = asyncio.get_event_loop().time() + 5
        root_status = "in_progress"
        while asyncio.get_event_loop().time() < deadline:
            async with session_factory() as session:
                root = (
                    await session.execute(select(Task).where(Task.id == root_task_id))
                ).scalar_one()
            root_status = root.status
            if root_status == "failed":
                break
            await asyncio.sleep(0.2)
        assert root_status == "failed", f"root rollup expected 'failed', got {root_status!r}"
    finally:
        dispatcher.shutdown()
        try:
            await asyncio.wait_for(task, timeout=5)
        except (TimeoutError, asyncio.CancelledError):
            task.cancel()
        await bus.close()
        await feed.close()


# === iter-6 Phase 2: LLMBudgetExhaustedError → BLOCKED (no cascade-drop) ===


class _BudgetExhaustedBackend(BaseAgent):
    """Stub Backend whose handle() always raises LLMBudgetExhaustedError.
    Iter-6 dispatcher must catch the distinct exception and emit a
    TASK_REPORT(status=blocked, blocked_on='budget') so the HoldQueue
    does NOT cascade-drop dependents (the failed path does)."""

    role: ClassVar[AgentId] = AgentId.BACKEND_DEVELOPER
    system_prompt_path: ClassVar[Path] = Path("/dev/null")

    def __init__(self) -> None:
        self._cached_prompt: str | None = None

    def system_prompt(self) -> str:
        return "# Role: Backend Developer\nStub agent for tests.\n"

    async def handle(self, msg: AgentMessage) -> list[AgentMessage]:
        del msg
        raise LLMBudgetExhaustedError("claude -p budget exhausted: stdout=...")

    def build_outputs(
        self,
        response: LLMResponse,
        incoming: AgentMessage,
    ) -> list[AgentMessage]:
        del response, incoming
        return []


def _tl_be_then_qa_response() -> LLMResponse:
    """TL emits be (no deps) + qa (depends_on=[be])."""
    return LLMResponse(
        text="",
        structured={
            "summary": "Backend then QA.",
            "subtasks": [
                {
                    "id": "be",
                    "recipient": "backend_developer",
                    "title": "Build",
                    "description": "Implement something.",
                    "priority": "P2",
                    "depends_on": [],
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
        session_id="tl-iter6",
        tokens=TokensUsage(input=10, output=20, model="claude-opus-4-7"),
        cost_estimate_cents=0,
        duration_ms=100,
        raw={},
    )


def _tl_arch_then_be_response() -> LLMResponse:
    """TL emits arch (no deps) + be (depends_on=[arch]). Iter-6 Phase 3
    test uses this to drive arch → FAILED so be gets dropped by
    HoldQueue and on_drop must flip be's Task row to FAILED."""
    return LLMResponse(
        text="",
        structured={
            "summary": "Arch then Backend.",
            "subtasks": [
                {
                    "id": "arch",
                    "recipient": "architect",
                    "title": "Design",
                    "description": "Tiny ADR.",
                    "priority": "P2",
                    "depends_on": [],
                },
                {
                    "id": "be",
                    "recipient": "backend_developer",
                    "title": "Build",
                    "description": "Impl per ADR.",
                    "priority": "P2",
                    "depends_on": ["arch"],
                },
            ],
        },
        tools_used=[],
        session_id="tl-iter6-drop",
        tokens=TokensUsage(input=10, output=20, model="claude-opus-4-7"),
        cost_estimate_cents=0,
        duration_ms=100,
        raw={},
    )


class _RaisingArchitect(BaseAgent):
    """Stub Architect whose handle() raises RuntimeError so the dispatcher
    synthesises TASK_REPORT(failed) → HoldQueue.mark_failed → drops the
    queued Backend assignment. Iter-6 dispatcher must walk those dropped
    messages through TaskStateReducer.on_drop so the be child Task row
    flips from in_progress to failed."""

    role: ClassVar[AgentId] = AgentId.ARCHITECT
    system_prompt_path: ClassVar[Path] = Path("/dev/null")

    def __init__(self) -> None:
        self._cached_prompt: str | None = None

    def system_prompt(self) -> str:
        return "# Role: Architect\nStub agent for tests.\n"

    async def handle(self, msg: AgentMessage) -> list[AgentMessage]:
        del msg
        raise RuntimeError("simulated architect crash for iter-6 on_drop test")

    def build_outputs(
        self,
        response: LLMResponse,
        incoming: AgentMessage,
    ) -> list[AgentMessage]:
        del response, incoming
        return []


async def test_dropped_dependent_child_task_flips_to_failed(
    redis_url: str,
    session_factory: async_sessionmaker[AsyncSession],
    db_session: AsyncSession,
) -> None:
    _ = db_session
    """Predecessor fails → HoldQueue drops dependent → dispatcher walks
    dropped messages through TaskStateReducer.on_drop → dependent child
    Task row flips from in_progress to failed → root Task rolls up.

    Pre-iter-6 bug: dropped dependents left child Task rows stuck
    in_progress indefinitely even though they would never run. See
    iter_5_demo_report.md Failure 3 + iter_6.md Phase 3."""
    bus = MessageBus.from_url(redis_url)
    feed = FeedPublisher.from_url(redis_url, db_session_factory=session_factory)
    signer = HMACSigner(_SECRET)
    audit = AuditLogWriter(session_factory, _SECRET)

    llm = _OnlyTLResponseLLM(_tl_arch_then_be_response())
    be_received: list[AgentMessage] = []

    agents = {
        AgentId.TEAM_LEAD: TeamLeadAgent(llm=llm),
        AgentId.ARCHITECT: _RaisingArchitect(),
        # Backend stub records if the bus ever delivers — should NOT happen
        # because be is dropped by HoldQueue when arch fails.
        AgentId.BACKEND_DEVELOPER: _StubBackend(observer=be_received),
    }
    task_state = TaskStateReducer(session_factory)
    dispatcher = AgentDispatcher(
        bus=bus,
        feed=feed,
        audit=audit,
        signer=signer,
        agents=agents,
        iteration=6,
        task_state=task_state,
    )

    task = asyncio.create_task(dispatcher.run())

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
                title="iter-6 on_drop path",
                description="Architect crashes; Backend dependent gets dropped.",
            ),
        )
    )

    async with session_factory() as session:
        session.add(
            Task(
                id=root_task_id,
                correlation_id=correlation_id,
                title="iter-6 on_drop path",
                description="Architect crashes; Backend dependent gets dropped.",
                status="in_progress",
                assigned_agent=AgentId.TEAM_LEAD.value,
                priority=Priority.P2.value,
                iteration=6,
            )
        )
        await session.commit()

    try:
        await audit.write_message(user_msg, iteration=6)
        await bus.publish(user_msg)

        # Wait for root Task rollup to terminate (any-failed → failed).
        deadline = asyncio.get_event_loop().time() + 15
        root_status = "in_progress"
        while asyncio.get_event_loop().time() < deadline:
            async with session_factory() as session:
                root = (
                    await session.execute(select(Task).where(Task.id == root_task_id))
                ).scalar_one()
            root_status = root.status
            if root_status == "failed":
                break
            await asyncio.sleep(0.2)
        assert root_status == "failed", f"root rollup expected 'failed', got {root_status!r}"

        # Backend was NEVER delivered (HoldQueue dropped it on arch's failure).
        assert be_received == [], (
            f"Backend must not run when its predecessor failed; "
            f"received {len(be_received)} messages"
        )

        # Child Task rows: arch=failed (real), be=failed (via on_drop).
        # Without iter-6's on_drop, be would still be in_progress here.
        async with session_factory() as session:
            children = (
                (await session.execute(select(Task).where(Task.parent_task_id == root_task_id)))
                .scalars()
                .all()
            )
        by_role = {c.assigned_agent: c for c in children}
        assert AgentId.ARCHITECT.value in by_role, f"no architect child row: {list(by_role.keys())}"
        assert AgentId.BACKEND_DEVELOPER.value in by_role, (
            f"no backend_developer child row: {list(by_role.keys())}"
        )
        assert by_role[AgentId.ARCHITECT.value].status == "failed", (
            f"arch child must be 'failed' (real synth), "
            f"got {by_role[AgentId.ARCHITECT.value].status!r}"
        )
        assert by_role[AgentId.BACKEND_DEVELOPER.value].status == "failed", (
            f"be child must be 'failed' (via on_drop); "
            f"got {by_role[AgentId.BACKEND_DEVELOPER.value].status!r}"
        )
    finally:
        dispatcher.shutdown()
        try:
            await asyncio.wait_for(task, timeout=5)
        except (TimeoutError, asyncio.CancelledError):
            task.cancel()
        await bus.close()
        await feed.close()


async def test_budget_exhausted_emits_blocked_does_not_cascade_drop(
    redis_url: str,
    session_factory: async_sessionmaker[AsyncSession],
    db_session: AsyncSession,
) -> None:
    _ = db_session
    """When Backend raises LLMBudgetExhaustedError, the synthesised report
    is BLOCKED (not failed). QA (depends_on=[be]) stays held rather than
    getting dropped; root Task stays in_progress (no terminal cascade).

    Owner can then `ai-team approve <id>` or manually retry with elevated
    budget — see iter_6.md Phase 2."""
    bus = MessageBus.from_url(redis_url)
    feed = FeedPublisher.from_url(redis_url, db_session_factory=session_factory)
    signer = HMACSigner(_SECRET)
    audit = AuditLogWriter(session_factory, _SECRET)

    llm = _OnlyTLResponseLLM(_tl_be_then_qa_response())
    qa_received: list[AgentMessage] = []

    agents = {
        AgentId.TEAM_LEAD: TeamLeadAgent(llm=llm),
        AgentId.BACKEND_DEVELOPER: _BudgetExhaustedBackend(),
        # QA stub records anything the bus delivers — we'll assert it's
        # NEVER called because the HoldQueue keeps qa held under BLOCKED.
        AgentId.QA_ENGINEER: _StubQA(observer=qa_received),
    }
    task_state = TaskStateReducer(session_factory)
    dispatcher = AgentDispatcher(
        bus=bus,
        feed=feed,
        audit=audit,
        signer=signer,
        agents=agents,
        iteration=6,
        task_state=task_state,
    )

    task = asyncio.create_task(dispatcher.run())

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
                title="iter-6 budget-blocked path",
                description="Backend will raise LLMBudgetExhaustedError.",
            ),
        )
    )

    async with session_factory() as session:
        session.add(
            Task(
                id=root_task_id,
                correlation_id=correlation_id,
                title="iter-6 budget-blocked path",
                description="Backend will raise LLMBudgetExhaustedError.",
                status="in_progress",
                assigned_agent=AgentId.TEAM_LEAD.value,
                priority=Priority.P2.value,
                iteration=6,
            )
        )
        await session.commit()

    try:
        await audit.write_message(user_msg, iteration=6)
        await bus.publish(user_msg)

        # Wait for Backend's synthesised TASK_REPORT to land.
        deadline = asyncio.get_event_loop().time() + 15
        be_report_rows: list[AuditLog] = []
        while asyncio.get_event_loop().time() < deadline:
            async with session_factory() as session:
                be_report_rows = list(
                    (
                        await session.execute(
                            select(AuditLog)
                            .where(AuditLog.correlation_id == correlation_id)
                            .where(AuditLog.sender == AgentId.BACKEND_DEVELOPER.value)
                            .where(AuditLog.message_type == MessageType.TASK_REPORT.value)
                        )
                    )
                    .scalars()
                    .all()
                )
            if be_report_rows:
                break
            await asyncio.sleep(0.2)
        assert be_report_rows, "no synthesised TASK_REPORT from Backend after 15s"

        # Status is BLOCKED (not FAILED); blocked_on='budget'; summary
        # carries the LLMBudgetExhaustedError name.
        be_payload = be_report_rows[0].payload_json.get("payload", {})
        assert be_payload.get("status") == TaskStatus.BLOCKED.value, (
            f"expected blocked, got {be_payload.get('status')!r}"
        )
        assert be_payload.get("blocked_on") == "budget", (
            f"expected blocked_on='budget', got {be_payload.get('blocked_on')!r}"
        )
        assert "LLMBudgetExhaustedError" in be_payload.get("summary", "")

        # QA was NEVER delivered (still held by HoldQueue because BLOCKED
        # is not a terminal that releases or drops).
        await asyncio.sleep(1.0)  # give dispatcher a beat to (incorrectly) release qa
        assert qa_received == [], (
            f"QA should be held under BLOCKED, but received {len(qa_received)} messages"
        )

        # Root Task stays in_progress — no cascade.
        async with session_factory() as session:
            root = (await session.execute(select(Task).where(Task.id == root_task_id))).scalar_one()
        assert root.status == "in_progress", (
            f"root must stay in_progress under BLOCKED; got {root.status!r}"
        )

        # QA's child Task row is still in_progress (not failed-by-cascade
        # — that's a FAILED path, not BLOCKED).
        async with session_factory() as session:
            children = (
                (await session.execute(select(Task).where(Task.parent_task_id == root_task_id)))
                .scalars()
                .all()
            )
        qa_children = [c for c in children if c.assigned_agent == AgentId.QA_ENGINEER.value]
        assert qa_children, "no QA child row inserted"
        assert qa_children[0].status == "in_progress", (
            f"QA child must stay in_progress under BLOCKED, got {qa_children[0].status!r}"
        )
    finally:
        dispatcher.shutdown()
        try:
            await asyncio.wait_for(task, timeout=5)
        except (TimeoutError, asyncio.CancelledError):
            task.cancel()
        await bus.close()
        await feed.close()
