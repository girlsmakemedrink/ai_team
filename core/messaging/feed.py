"""team_feed publisher and subscriber. See ADR-007.

Layered:
  1. Pub/Sub broadcast (Redis) — live consumers.
  2. Postgres `feed_events` table — queryable history (best-effort).

Both layers are non-blocking with respect to the caller's audit-log path.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator  # noqa: TC003  runtime async-gen annotation
from typing import TYPE_CHECKING, Any
from uuid import UUID

import structlog
from redis.asyncio import Redis

from core.messaging.schemas import AgentMessage, MessageType
from core.observability.metrics import audit_log_write_failures_total
from core.persistence.models import FeedEvent
from core.security.redaction import redact_for_feed

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

_log = structlog.get_logger(__name__)

CHANNEL: str = "team_feed"

# By default, these are filtered out of the feed (CLI `--no-internal`).
NOISE_TYPES: frozenset[MessageType] = frozenset({MessageType.HEARTBEAT})


def summarise(msg: AgentMessage) -> str:
    return (
        f"[{msg.priority.value}] "
        f"{msg.sender.value} → {msg.recipient.value}: "
        f"{msg.message_type.value}"
    )


def make_feed_event(msg: AgentMessage) -> dict[str, Any]:
    return {
        "message_id": str(msg.message_id),
        "correlation_id": str(msg.correlation_id),
        "timestamp": msg.timestamp.isoformat(),
        "sender": msg.sender.value,
        "recipient": msg.recipient.value,
        "message_type": msg.message_type.value,
        "priority": msg.priority.value,
        "summary": summarise(msg),
        "redacted_payload": redact_for_feed(msg.payload.model_dump(mode="json")),
    }


async def _persist_event(
    session_factory: async_sessionmaker[AsyncSession],
    event: dict[str, Any],
) -> None:
    """Best-effort insert into feed_events. Logs+counts failures, doesn't raise."""
    try:
        async with session_factory() as session:
            row = FeedEvent(
                message_id=UUID(event["message_id"]),
                correlation_id=UUID(event["correlation_id"]),
                sender=event["sender"],
                recipient=event["recipient"],
                message_type=event["message_type"],
                priority=event["priority"],
                summary=event["summary"],
                redacted_payload=event["redacted_payload"],
            )
            session.add(row)
            await session.commit()
    except Exception as e:
        _log.warning("feed.persist.failed", error=str(e),
                     message_id=event.get("message_id"))
        audit_log_write_failures_total.inc()


class FeedPublisher:
    """Publishes feed events on Pub/Sub and (optionally) persists to Postgres."""

    def __init__(
        self,
        redis: Redis[bytes],
        *,
        db_session_factory: async_sessionmaker[AsyncSession] | None = None,
    ) -> None:
        self._redis = redis
        self._db_session_factory = db_session_factory

    @classmethod
    def from_url(
        cls,
        url: str,
        *,
        db_session_factory: async_sessionmaker[AsyncSession] | None = None,
    ) -> FeedPublisher:
        return cls(
            Redis.from_url(url, decode_responses=False),
            db_session_factory=db_session_factory,
        )

    async def publish(
        self, msg: AgentMessage, *, include_noise: bool = False
    ) -> dict[str, Any] | None:
        if msg.message_type in NOISE_TYPES and not include_noise:
            return None
        event = make_feed_event(msg)

        # Pub/Sub first (low-latency fan-out).
        await self._redis.publish(CHANNEL, json.dumps(event))

        # Postgres sink (queryable history; best-effort).
        if self._db_session_factory is not None:
            await _persist_event(self._db_session_factory, event)

        return event

    async def close(self) -> None:
        await self._redis.aclose()  # type: ignore[attr-defined]


class FeedSubscriber:
    """Async iterator over live feed_event dicts."""

    def __init__(self, redis: Redis[bytes]) -> None:
        self._redis = redis

    @classmethod
    def from_url(cls, url: str) -> FeedSubscriber:
        return cls(Redis.from_url(url, decode_responses=False))

    async def stream(self) -> AsyncIterator[dict[str, Any]]:
        pubsub = self._redis.pubsub()
        await pubsub.subscribe(CHANNEL)
        try:
            async for raw in pubsub.listen():
                if raw["type"] != "message":
                    continue
                data = raw["data"]
                if isinstance(data, bytes):
                    data = data.decode()
                try:
                    parsed = json.loads(data)
                except json.JSONDecodeError:
                    _log.warning("feed.invalid_payload")
                    continue
                if isinstance(parsed, dict):
                    yield parsed
        finally:
            await pubsub.unsubscribe(CHANNEL)
            await pubsub.aclose()  # type: ignore[attr-defined]

    async def close(self) -> None:
        await self._redis.aclose()  # type: ignore[attr-defined]
