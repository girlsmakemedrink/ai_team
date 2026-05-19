"""Central orchestration: consumes from the bus, drives agents, audits + republishes.

See ADR-001. One dispatcher process; one asyncio task per agent. Messages
are processed serially per agent (no concurrent invocations of the same
agent — keeps audit chain deterministic).
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING
from uuid import UUID

import structlog

from core.dispatcher.hold_queue import HoldQueue
from core.messaging.schemas import TaskReportPayload, TaskStatus
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
        hold_queue: HoldQueue | None = None,
    ) -> None:
        self._bus = bus
        self._feed = feed
        self._audit = audit
        self._signer = signer
        self._agents = agents
        self._iteration = iteration
        self._hold_queue = hold_queue or HoldQueue()
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
            async for entry_id, msg in self._bus.consume(agent.role, consumer_name=consumer_name):
                if self._shutdown.is_set():
                    break
                await self._handle_one(agent, msg, entry_id)
        except asyncio.CancelledError:
            log.info("dispatcher.agent.cancelled")
            raise
        except Exception:
            log.exception("dispatcher.agent.crashed")
            agent_errors_total.labels(agent=agent.role.value, error_type="loop_crash").inc()

    async def _handle_one(self, agent: BaseAgent, msg: AgentMessage, entry_id: str) -> None:
        token = bind_correlation_id(msg.correlation_id)
        try:
            try:
                self._signer.verify(msg)
            except InvalidSignatureError:
                agent_errors_total.labels(agent=agent.role.value, error_type="bad_signature").inc()
                _log.warning(
                    "dispatcher.signature.invalid",
                    sender=msg.sender.value,
                    message_id=str(msg.message_id),
                )
                await self._bus.ack(agent.role, entry_id)
                return

            # No inbound audit — every cross-agent message is audited
            # by its publisher (API for user messages; this same dispatcher
            # for agent→agent outputs). Avoids double-rows in the chain.

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
                    agent_errors_total.labels(agent=agent.role.value, error_type="handle").inc()

            for out in outputs:
                signed = self._signer.with_signature(out)
                # Audit + feed-publish at intent time: the message exists,
                # even if held off the bus. Owner observability is
                # unaffected by the hold queue.
                await self._audit.write_message(signed, iteration=self._iteration)
                await self._feed.publish(signed)

                # Dependency-aware bus publish.
                depends_on = _parse_depends_on(signed)
                held = await self._hold_queue.hold(signed, depends_on) if depends_on else False
                if not held:
                    await self._bus.publish(signed)

                # When this output is itself a terminal TASK_REPORT, fan out
                # the consequences for any held dependents in the same
                # correlation_id.
                if isinstance(signed.payload, TaskReportPayload):
                    if signed.payload.status == TaskStatus.DONE:
                        released = await self._hold_queue.mark_done(
                            signed.correlation_id, signed.payload.task_id
                        )
                        for r in released:
                            # Already audited + feed-published at intent
                            # time. Just push to the bus.
                            await self._bus.publish(r)
                    elif signed.payload.status == TaskStatus.FAILED:
                        dropped = await self._hold_queue.mark_failed(
                            signed.correlation_id, signed.payload.task_id
                        )
                        for d in dropped:
                            _log.warning(
                                "dispatcher.dependent_dropped_after_failure",
                                correlation_id=str(d.correlation_id),
                                message_id=str(d.message_id),
                                failed_task_id=str(signed.payload.task_id),
                            )

            await self._bus.ack(agent.role, entry_id)
        finally:
            clear_correlation_id(token)


def _parse_depends_on(msg: AgentMessage) -> set[UUID]:
    """Pull metadata['depends_on'] off the envelope as a set of UUIDs."""
    raw = msg.metadata.get("depends_on") or []
    if not isinstance(raw, list):
        return set()
    out: set[UUID] = set()
    for item in raw:
        if not isinstance(item, str):
            continue
        try:
            out.add(UUID(item))
        except ValueError:
            continue
    return out
