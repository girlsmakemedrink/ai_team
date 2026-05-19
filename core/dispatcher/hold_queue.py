"""In-memory dependency gate for sub-task assignments. See iter_3.md Phase 2C.

When the Team Lead emits sub-tasks with `metadata["depends_on"] = [<uuid>, ...]`,
the dispatcher gates each outbound `task_assignment` through this queue.
A message whose predecessors are not all `done` is held off the bus
(but already audited and feed-published — the intent is observable to
the owner). When a predecessor's `TASK_REPORT(status=done)` lands, any
newly unblocked messages are released and published.

State is in-memory and per-dispatcher-process; a restart drops every
held message. The single-process iter-3 dispatcher tolerates this — see
`docs/iterations/iter_3.md` for the iter-4 upgrade path.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from dataclasses import dataclass
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from uuid import UUID

    from core.messaging.schemas import AgentMessage

_log = structlog.get_logger(__name__)


@dataclass(slots=True)
class _Held:
    msg: AgentMessage
    depends_on: set[UUID]


class HoldQueue:
    """Single-process dependency-ordered release queue."""

    def __init__(self) -> None:
        self._done: dict[UUID, set[UUID]] = defaultdict(set)
        self._held: dict[UUID, list[_Held]] = defaultdict(list)
        self._lock = asyncio.Lock()

    async def hold(self, msg: AgentMessage, depends_on: set[UUID]) -> bool:
        """Hold *msg* if any predecessor is not yet done.

        Returns ``True`` when the message is held (caller should NOT
        publish to the bus). Returns ``False`` when every predecessor
        was already done at call time (caller should publish
        immediately).
        """
        if not depends_on:
            return False
        async with self._lock:
            outstanding = depends_on - self._done[msg.correlation_id]
            if not outstanding:
                return False
            self._held[msg.correlation_id].append(_Held(msg=msg, depends_on=outstanding))
            _log.info(
                "hold_queue.hold",
                correlation_id=str(msg.correlation_id),
                message_id=str(msg.message_id),
                outstanding=[str(u) for u in outstanding],
            )
            return True

    async def mark_done(self, correlation_id: UUID, task_id: UUID) -> list[AgentMessage]:
        """Record a predecessor as done and return any newly released messages."""
        async with self._lock:
            self._done[correlation_id].add(task_id)
            released: list[AgentMessage] = []
            still_held: list[_Held] = []
            for h in self._held[correlation_id]:
                h.depends_on.discard(task_id)
                if not h.depends_on:
                    released.append(h.msg)
                else:
                    still_held.append(h)
            self._held[correlation_id] = still_held
        if released:
            _log.info(
                "hold_queue.released",
                correlation_id=str(correlation_id),
                task_id=str(task_id),
                count=len(released),
            )
        return released

    async def mark_failed(self, correlation_id: UUID, task_id: UUID) -> list[AgentMessage]:
        """Drop held messages waiting on a failed predecessor.

        A FAILED predecessor means its dependents cannot proceed; releasing
        them to chase a failed dep is wrong. We drop and return them so the
        caller can route them to the owner via an alert (or simply log the
        drop).
        """
        async with self._lock:
            dropped: list[AgentMessage] = []
            still_held: list[_Held] = []
            for h in self._held[correlation_id]:
                if task_id in h.depends_on:
                    dropped.append(h.msg)
                else:
                    still_held.append(h)
            self._held[correlation_id] = still_held
        if dropped:
            _log.warning(
                "hold_queue.dropped_after_failure",
                correlation_id=str(correlation_id),
                failed_task_id=str(task_id),
                count=len(dropped),
            )
        return dropped
