"""Smoke that testcontainers fixtures work + feed_events persistence."""
from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import uuid4

import pytest
from redis.asyncio import Redis
from sqlalchemy import select

from core.messaging.feed import FeedPublisher
from core.messaging.schemas import (
    AgentId,
    AgentMessage,
    MessageType,
    Priority,
    TaskReportPayload,
    TaskStatus,
)
from core.persistence.models import FeedEvent

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = pytest.mark.integration


def _make_msg() -> AgentMessage:
    return AgentMessage(
        correlation_id=uuid4(),
        sender=AgentId.TEAM_LEAD,
        recipient=AgentId.USER,
        message_type=MessageType.TASK_REPORT,
        priority=Priority.P3,
        payload=TaskReportPayload(
            task_id=uuid4(),
            status=TaskStatus.DONE,
            progress_pct=100,
            summary="integration smoke",
        ),
    )


async def test_pg_and_redis_containers_alive(
    pg_dsn: str, redis_url: str, db_session: AsyncSession
) -> None:
    assert "asyncpg" in pg_dsn
    assert redis_url.startswith("redis://")
    # session is connected and migrations applied → tables exist
    rows = (await db_session.execute(select(FeedEvent).limit(1))).all()
    assert rows == []  # empty but queryable


async def test_feed_publisher_persists_event(
    redis_url: str,
    session_factory: async_sessionmaker[AsyncSession],
    db_session: AsyncSession,
) -> None:
    redis = Redis.from_url(redis_url, decode_responses=False)
    publisher = FeedPublisher(redis, db_session_factory=session_factory)
    msg = _make_msg()
    event = await publisher.publish(msg)
    await publisher.close()

    assert event is not None
    assert event["sender"] == "team_lead"

    # Verify DB row written.
    rows = (
        await db_session.execute(
            select(FeedEvent).where(FeedEvent.message_id == msg.message_id)
        )
    ).scalars().all()
    assert len(rows) == 1
    assert rows[0].summary.startswith("[P3] team_lead")
    assert rows[0].redacted_payload["status"] == "done"


async def test_feed_publisher_without_db_factory_only_pubsubs(
    redis_url: str, db_session: AsyncSession
) -> None:
    redis = Redis.from_url(redis_url, decode_responses=False)
    publisher = FeedPublisher(redis)  # no db_session_factory
    msg = _make_msg()
    event = await publisher.publish(msg)
    await publisher.close()

    assert event is not None
    rows = (
        await db_session.execute(
            select(FeedEvent).where(FeedEvent.message_id == msg.message_id)
        )
    ).all()
    assert rows == []  # no DB write
