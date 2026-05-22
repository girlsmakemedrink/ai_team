"""Central orchestration: consumes from the bus, drives agents, audits + republishes.

See ADR-001. One dispatcher process; one asyncio task per agent. Messages
are processed serially per agent (no concurrent invocations of the same
agent — keeps audit chain deterministic).
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import structlog

from core.dispatcher.hold_queue import HoldQueue
from core.dispatcher.mcp_race_router import maybe_route_mcp_race_to_blocked
from core.llm.base import LLMBudgetExhaustedError, MCPUnhealthyError
from core.messaging.schemas import (
    AgentId,
    AgentMessage,
    MessageType,
    Priority,
    TaskAssignmentPayload,
    TaskReportPayload,
    TaskStatus,
)
from core.observability.logging import bind_correlation_id, clear_correlation_id
from core.observability.metrics import (
    agent_errors_total,
    agent_message_processing_duration,
)
from core.security.hmac_signer import HMACSigner, InvalidSignatureError
from core.target_repo.registry import resolve_target_repo

if TYPE_CHECKING:
    from agents._base import BaseAgent
    from core.audit.writer import AuditLogWriter
    from core.messaging.bus import MessageBus
    from core.messaging.feed import FeedPublisher
    from core.persistence.task_state import TaskStateReducer

_log = structlog.get_logger(__name__)

_AI_TEAM_ROOT_DEFAULT = Path(__file__).resolve().parents[2]


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
        task_state: TaskStateReducer | None = None,
        ai_team_root: Path | None = None,
    ) -> None:
        self._bus = bus
        self._feed = feed
        self._audit = audit
        self._signer = signer
        self._agents = agents
        self._iteration = iteration
        self._hold_queue = hold_queue or HoldQueue()
        # Optional: when provided, the dispatcher writes child Task rows
        # and rolls parent status up from child terminals. None disables
        # the bookkeeping (used by tests that don't care about the rollup
        # and by environments that haven't set up the tasks table yet).
        self._task_state = task_state
        self._ai_team_root = ai_team_root or _AI_TEAM_ROOT_DEFAULT
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
                    # iter-29c: resolve payload.target_repo into a
                    # workspace path and stash on msg.metadata so
                    # BaseAgent injects AI_TEAM_REPO_ROOT + cwd. Failures
                    # fall through to the existing _synthesise_failed_report.
                    await self._maybe_resolve_target_repo_workspace(msg)
                    outputs = await agent.handle(msg)
                except Exception as exc:
                    _log.exception(
                        "dispatcher.agent.handle.failed",
                        agent=agent.role.value,
                    )
                    agent_errors_total.labels(agent=agent.role.value, error_type="handle").inc()
                    # iter-5: synthesise a terminal TASK_REPORT(failed) so
                    # the HoldQueue + rollup + team_feed see the crash.
                    # Without this, iter-4's silent Backend exit-1 leaves
                    # downstream agents held forever.
                    outputs = [_synthesise_failed_report(role=agent.role, incoming=msg, exc=exc)]

            for raw_out in outputs:
                # iter-10: route LLM-emitted MCP-race failures to
                # BLOCKED before HMAC-sign so dependents stay held
                # in HoldQueue instead of cascade-dropping. Pure
                # pass-through for non-matching messages (no copy
                # made). See iter_9_demo_report.md Failure 1 +
                # iter_10.md success criterion #3.
                out = maybe_route_mcp_race_to_blocked(raw_out)
                signed = self._signer.with_signature(out)
                # Audit + feed-publish at intent time: the message exists,
                # even if held off the bus. Owner observability is
                # unaffected by the hold queue.
                await self._audit.write_message(signed, iteration=self._iteration)
                await self._feed.publish(signed)

                # Task-state bookkeeping. Sub-task assignments insert
                # child rows so the rollup has something to track.
                # task_reports update the matching child + flip the
                # parent when all children are terminal.
                await self._maybe_record_task_state(signed)

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
                        await self._cascade_drops(
                            correlation_id=signed.correlation_id,
                            failed_task_id=signed.payload.task_id,
                        )

            await self._bus.ack(agent.role, entry_id)
        finally:
            clear_correlation_id(token)

    async def _maybe_resolve_target_repo_workspace(self, msg: AgentMessage) -> None:
        """Resolve payload.target_repo and stash workspace path on
        msg.metadata['target_repo_workspace'] for BaseAgent to read.

        No-op when:
        - msg is not a TaskAssignment;
        - payload.target_repo is None (self-hosting path).

        Raises whatever `resolve_target_repo`, `ensure_local_clone`, or
        `prepare_for_task` raises (ValueError, GitCommandError, etc.).
        `_handle_one`'s outer try/except catches and synthesises a FAILED
        report via the existing iter-5 substrate.
        """
        if not isinstance(msg.payload, TaskAssignmentPayload):
            return
        identifier = msg.payload.target_repo
        if not identifier:
            return
        repo = resolve_target_repo(identifier, ai_team_root=self._ai_team_root)
        workspace = await repo.ensure_local_clone()
        await repo.prepare_for_task()
        msg.metadata["target_repo_workspace"] = str(workspace)

    async def _maybe_record_task_state(self, msg: AgentMessage) -> None:
        """Forward task lifecycle events to the TaskStateReducer if wired."""
        if self._task_state is None:
            return
        if msg.message_type == MessageType.TASK_ASSIGNMENT and isinstance(
            msg.payload, TaskAssignmentPayload
        ):
            parent_raw = msg.metadata.get("parent_task_id")
            if not isinstance(parent_raw, str):
                # Root assignments (e.g. user → TL) carry no parent; no
                # child row to insert.
                return
            try:
                parent_task_id = UUID(parent_raw)
            except ValueError:
                _log.warning(
                    "dispatcher.task_state.bad_parent_uuid",
                    parent_raw=parent_raw,
                    message_id=str(msg.message_id),
                )
                return
            await self._task_state.on_assignment(
                child_task_id=msg.payload.task_id,
                parent_task_id=parent_task_id,
                correlation_id=msg.correlation_id,
                recipient=msg.recipient.value,
                title=msg.payload.title,
                description=msg.payload.description,
                priority=msg.priority.value,
                target_repo=msg.payload.target_repo,
                iteration=self._iteration,
            )
        elif msg.message_type == MessageType.TASK_REPORT and isinstance(
            msg.payload, TaskReportPayload
        ):
            await self._task_state.on_report(
                task_id=msg.payload.task_id, status=msg.payload.status.value
            )

    async def _cascade_drops(self, *, correlation_id: UUID, failed_task_id: UUID) -> None:
        """Walk the HoldQueue + reducer drop pipeline transitively.

        iter-7: drive the cascade with a queue. Every task_id returned
        by `HoldQueue.mark_failed` becomes a new failure trigger so
        transitive dependents (e.g. fe → qa in arch→design→fe→qa)
        get dropped in the same pass.

        Cycle-safe: `mark_failed` only drains `_held` entries that match
        the trigger, and `on_drop` is idempotent on already-terminal
        rows. The reducer's `on_drop` flips dropped child Task rows to
        `failed` and rolls parents up via `derive_parent_status`.

        iter-6 baseline (just one level deep) closed iter-5 demo
        Failure 3; iter-7 extends to N levels (closes iter-6 demo
        Failure 2 — fe + qa stuck `in_progress` after design dropped).
        """
        to_drop_triggers: list[UUID] = [failed_task_id]
        while to_drop_triggers:
            trigger_id = to_drop_triggers.pop(0)
            dropped = await self._hold_queue.mark_failed(correlation_id, trigger_id)
            if not dropped:
                continue
            for d in dropped:
                _log.warning(
                    "dispatcher.dependent_dropped_after_failure",
                    correlation_id=str(d.correlation_id),
                    message_id=str(d.message_id),
                    failed_task_id=str(trigger_id),
                )
            dropped_task_ids = [
                d.payload.task_id for d in dropped if isinstance(d.payload, TaskAssignmentPayload)
            ]
            if self._task_state is not None and dropped_task_ids:
                await self._task_state.on_drop(dropped_task_ids)
            # Each dropped task_id is now a failure trigger for any
            # further-downstream dependents.
            to_drop_triggers.extend(dropped_task_ids)


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


def _synthesise_failed_report(
    *, role: AgentId, incoming: AgentMessage, exc: BaseException
) -> AgentMessage:
    """Build a terminal TASK_REPORT for an agent that crashed.

    Iter-4 demo's Backend hit `claude -p exited 1` with empty stderr;
    the dispatcher's except block logged the traceback but emitted
    nothing, so the HoldQueue never saw a terminal status for Backend
    and QA stayed held until the 20-min wall-clock. iter-5 wires this
    helper into that except path: the synthetic report runs through
    the same outbound pipeline as a real one (audit + feed +
    task-state + HoldQueue.mark_failed + bus), so the chain rolls
    up correctly on crash.

    iter-6: `LLMBudgetExhaustedError` is special-cased to BLOCKED (not
    FAILED). BLOCKED leaves dependents held in the HoldQueue rather
    than cascade-dropping them — the owner can manually retry with
    elevated budget. See iter_6.md Phase 2.

    `recipient` is USER when the incoming was a root-task user → TL
    assignment (so the rollup still surfaces to the owner); otherwise
    it routes back to TEAM_LEAD, matching how real agents report
    completion / failure.
    """
    payload_in = incoming.payload
    task_id = payload_in.task_id if isinstance(payload_in, TaskAssignmentPayload) else uuid4()
    parent_raw = incoming.metadata.get("parent_task_id") if incoming.metadata else None
    type_name = type(exc).__name__
    first_line = str(exc).splitlines()[0] if str(exc) else ""
    summary = f"{type_name}: {first_line}"[:500]
    recipient = AgentId.USER if incoming.sender == AgentId.USER else AgentId.TEAM_LEAD
    metadata: dict[str, object] = {}
    if isinstance(parent_raw, str):
        metadata["parent_task_id"] = parent_raw

    if isinstance(exc, LLMBudgetExhaustedError):
        status = TaskStatus.BLOCKED
        blocked_on: str | None = "budget"
        priority = Priority.P2  # recoverable by owner; not a crash
    elif isinstance(exc, MCPUnhealthyError):
        # iter-9: MCP pre-flight failures are recoverable by owner
        # (fix env var, restart container, etc.), not crashes. Same
        # held-not-dropped posture as the budget branch. See
        # iter_8_demo_report.md Failure 1 + iter_9.md decision #2.
        status = TaskStatus.BLOCKED
        blocked_on = "mcp_unhealthy"
        priority = Priority.P2
    else:
        status = TaskStatus.FAILED
        blocked_on = None
        priority = Priority.P1  # crashes are high-priority for owner visibility

    return AgentMessage(
        correlation_id=incoming.correlation_id,
        sender=role,
        recipient=recipient,
        message_type=MessageType.TASK_REPORT,
        priority=priority,
        payload=TaskReportPayload(
            task_id=task_id,
            status=status,
            progress_pct=0,
            summary=summary,
            blocked_on=blocked_on,
        ),
        metadata=metadata,
    )
