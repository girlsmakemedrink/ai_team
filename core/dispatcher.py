"""Central orchestration: consumes from the bus, drives agents, audits + republishes.

See ADR-001. One dispatcher process; one asyncio task per agent. Messages
are processed serially per agent (no concurrent invocations of the same
agent — keeps audit chain deterministic).
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import structlog

from core.observability.logging import bind_correlation_id, clear_correlation_id
from core.observability.metrics import (
    agent_errors_total,
    agent_message_processing_duration,
)
from core.security.hmac_signer import HMACSigner, InvalidSignatureError

if TYPE_CHECKING:
    from agents._base import BaseAgent
    from core.audit.writer import AuditLogWriter
    from core.messaging.bus import MessageBus
    from core.messaging.feed import FeedPublisher
    from core.messaging.schemas import AgentId, AgentMessage

_log = structlog.get_logger(__name__)


class AgentDispatcher:
    """Run a collection of agents against the bus."""

    def __init__(
        self,
        *,
        bus: MessageBus,
        feed: FeedPublisher,
        audit: AuditLogWriter,
        signer: HMACSigner,
        agents: dict[AgentId, BaseAgent],
        iteration: int | None = None,
    ) -> None:
        self._bus = bus
        self._feed = feed
        self._audit = audit
        self._signer = signer
        self._agents = agents
        self._iteration = iteration
        self._shutdown = asyncio.Event()

    async def run(self) -> None:
        await self._bus.ensure_streams(list(self._agents.keys()))
        agent_tasks = [
            asyncio.create_task(
                self._run_agent(agent),
                name=f"dispatcher-{agent.role.value}",
            )
            for agent in self._agents.values()
        ]
        try:
            await self._shutdown.wait()
        finally:
            for task in agent_tasks:
                task.cancel()
            await asyncio.gather(*agent_tasks, return_exceptions=True)

    def shutdown(self) -> None:
        self._shutdown.set()

    # ----- per-agent loop -----

    async def _run_agent(self, agent: BaseAgent) -> None:
        consumer_name = f"{agent.role.value}-1"
        log = _log.bind(agent=agent.role.value)
        log.info("dispatcher.agent.start")
        try:
            async for entry_id, msg in self._bus.consume(
                agent.role, consumer_name=consumer_name
            ):
                if self._shutdown.is_set():
                    break
                await self._handle_one(agent, msg, entry_id)
        except asyncio.CancelledError:
            log.info("dispatcher.agent.cancelled")
            raise
        except Exception:
            log.exception("dispatcher.agent.crashed")
            agent_errors_total.labels(
                agent=agent.role.value, error_type="loop_crash"
            ).inc()

    async def _handle_one(
        self, agent: BaseAgent, msg: AgentMessage, entry_id: str
    ) -> None:
        token = bind_correlation_id(msg.correlation_id)
        try:
            try:
                self._signer.verify(msg)
            except InvalidSignatureError:
                agent_errors_total.labels(
                    agent=agent.role.value, error_type="bad_signature"
                ).inc()
                _log.warning(
                    "dispatcher.signature.invalid",
                    sender=msg.sender.value,
                    message_id=str(msg.message_id),
                )
                await self._bus.ack(agent.role, entry_id)
                return

            # Audit the inbound (this agent received this message).
            await self._audit.write_message(msg, iteration=self._iteration)

            outputs: list[AgentMessage] = []
            with agent_message_processing_duration.labels(
                agent=agent.role.value, message_type=msg.message_type.value
            ).time():
                try:
                    outputs = await agent.handle(msg)
                except Exception:
                    _log.exception(
                        "dispatcher.agent.handle.failed",
                        agent=agent.role.value,
                    )
                    agent_errors_total.labels(
                        agent=agent.role.value, error_type="handle"
                    ).inc()

            for out in outputs:
                signed = self._signer.with_signature(out)
                await self._audit.write_message(signed, iteration=self._iteration)
                await self._bus.publish(signed)
                await self._feed.publish(signed)

            await self._bus.ack(agent.role, entry_id)
        finally:
            clear_correlation_id(token)
