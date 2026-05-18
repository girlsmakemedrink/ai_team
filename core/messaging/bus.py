"""Redis Streams message bus. See ADR-001, ADR-002."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Final

import structlog
from redis.asyncio import Redis

from core.messaging.schemas import AgentId, AgentMessage

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

_log = structlog.get_logger(__name__)

STREAM_NAME_FMT: Final = "bus:msgs:{agent}"
DLQ_STREAM: Final = "bus:dlq"
CONSUMER_GROUP_FMT: Final = "cg:{agent}"


def stream_name(agent: AgentId | str) -> str:
    name = agent.value if isinstance(agent, AgentId) else agent
    return STREAM_NAME_FMT.format(agent=name)


def group_name(agent: AgentId | str) -> str:
    name = agent.value if isinstance(agent, AgentId) else agent
    return CONSUMER_GROUP_FMT.format(agent=name)


class MessageBus:
    """Producer + consumer wrapper over Redis Streams.

    One stream per recipient agent. Each agent has a single consumer
    group; instances of the same agent (rare; future scale-out) act as
    competing consumers within the group.
    """

    def __init__(self, redis: Redis[bytes]) -> None:
        self._redis = redis

    @classmethod
    def from_url(cls, url: str) -> MessageBus:
        return cls(Redis.from_url(url, decode_responses=False))

    async def ensure_streams(self, agents: list[AgentId | str]) -> None:
        for agent in agents:
            try:
                await self._redis.xgroup_create(
                    stream_name(agent), group_name(agent), id="$", mkstream=True
                )
            except Exception as e:
                if "BUSYGROUP" in str(e):
                    continue
                raise

    async def publish(self, message: AgentMessage) -> str:
        target = stream_name(message.recipient)
        payload = message.model_dump_json()
        entry_id = await self._redis.xadd(target, {"msg": payload})
        return entry_id.decode() if isinstance(entry_id, bytes) else str(entry_id)

    async def consume(
        self,
        agent: AgentId | str,
        *,
        consumer_name: str,
        block_ms: int = 5_000,
        count: int = 10,
    ) -> AsyncIterator[tuple[str, AgentMessage]]:
        """Block-read messages destined for this agent. Caller must ack().

        Invalid messages (HMAC failures, schema mismatches) are routed to
        the DLQ and acknowledged on the source stream, so a poisoned
        message can't stall the consumer.
        """
        target = stream_name(agent)
        group = group_name(agent)
        while True:
            results = await self._redis.xreadgroup(
                group, consumer_name, {target: ">"}, count=count, block=block_ms
            )
            if not results:
                continue
            for _stream, entries in results:
                for entry_id, fields in entries:
                    eid = self._decode(entry_id)
                    raw = self._extract_msg(fields)
                    msg = await self._parse_or_dlq(raw, eid=eid, stream=target, group=group)
                    if msg is not None:
                        yield eid, msg

    async def ack(self, agent: AgentId | str, entry_id: str) -> None:
        await self._redis.xack(stream_name(agent), group_name(agent), entry_id)  # type: ignore[no-untyped-call]

    async def queue_depth(self, agent: AgentId | str) -> int:
        try:
            return int(await self._redis.xlen(stream_name(agent)))
        except Exception:
            return 0

    async def close(self) -> None:
        await self._redis.aclose()  # type: ignore[attr-defined]

    # ----- internals -----

    @staticmethod
    def _decode(value: Any) -> str:
        return value.decode() if isinstance(value, bytes) else str(value)

    @staticmethod
    def _extract_msg(fields: dict[Any, Any]) -> str | None:
        raw = fields.get(b"msg") or fields.get("msg")
        if isinstance(raw, bytes):
            return raw.decode()
        return raw if isinstance(raw, str) else None

    async def _parse_or_dlq(
        self, raw: str | None, *, eid: str, stream: str, group: str
    ) -> AgentMessage | None:
        if raw is None:
            await self._redis.xack(stream, group, eid)  # type: ignore[no-untyped-call]
            return None
        try:
            return AgentMessage.model_validate_json(raw)
        except Exception as e:  # noqa: BLE001
            _log.warning("bus.consume.invalid_msg", entry_id=eid, error=str(e))
            await self._redis.xadd(DLQ_STREAM, {"raw": raw, "reason": str(e)})
            await self._redis.xack(stream, group, eid)  # type: ignore[no-untyped-call]
            return None
