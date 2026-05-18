"""team_feed publisher and subscriber. See ADR-007."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import structlog
from redis.asyncio import Redis

from core.messaging.schemas import AgentMessage, MessageType
from core.security.redaction import redact_for_feed

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

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


class FeedPublisher:
    def __init__(self, redis: Redis[bytes]) -> None:
        self._redis = redis

    @classmethod
    def from_url(cls, url: str) -> FeedPublisher:
        return cls(Redis.from_url(url, decode_responses=False))

    async def publish(
        self, msg: AgentMessage, *, include_noise: bool = False
    ) -> dict[str, Any] | None:
        if msg.message_type in NOISE_TYPES and not include_noise:
            return None
        event = make_feed_event(msg)
        await self._redis.publish(CHANNEL, json.dumps(event))
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
