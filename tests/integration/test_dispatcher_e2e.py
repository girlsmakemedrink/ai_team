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
)
from core.persistence.models import AuditLog, FeedEvent
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
                    "recipient": "product_manager",
                    "title": "Generate user stories",
                    "description": "Produce 3-5 stories for the test task.",
                    "priority": "P2",
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

        # Feed_events captured the TL→PM and PM→TL hops (publisher-only sinks).
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
        assert "team_lead" in feed_senders
        assert "product_manager" in feed_senders
    finally:
        dispatcher.shutdown()
        try:
            await asyncio.wait_for(task, timeout=5)
        except (TimeoutError, asyncio.CancelledError):
            task.cancel()
        await bus.close()
        await feed.close()
