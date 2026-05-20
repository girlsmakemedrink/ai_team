"""Owner-initiated retry of BLOCKED task_assignments.

iter-11: when a task reaches BLOCKED with a recoverable `blocked_on`
value (currently 'mcp_unhealthy' or 'budget'), the owner can issue
`ai-team retry-blocked <task_id>` to re-emit the original
task_assignment with the same task_id and correlation_id
(load-bearing — HoldQueue dependents key off task_id, so a fresh
task_id would orphan QA + friends). A `retry_attempt` counter rides
on the envelope metadata to cap at 5 attempts total.

Pure logic; the FastAPI endpoint does the I/O (audit log read,
bus publish, tasks-row update).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING
from uuid import uuid4

from core.messaging.schemas import (
    AgentMessage,
    MessageType,
    TaskAssignmentPayload,
    TaskReportPayload,
    TaskStatus,
)

if TYPE_CHECKING:
    from collections.abc import Sequence
    from uuid import UUID


RECOVERABLE_BLOCKED_ON: frozenset[str] = frozenset({"mcp_unhealthy", "budget"})
RETRY_ATTEMPT_CAP: int = 5


class RetryNotEligible(Exception):
    """The task is not in a retryable state."""


@dataclass(slots=True)
class RetryEligibility:
    original_assignment: AgentMessage
    latest_report: AgentMessage
    retry_attempt: int


def check_retry_eligibility(
    task_id: UUID, rows: Sequence[AgentMessage]
) -> RetryEligibility:
    """Inspect audit_log rows for ``task_id``. Raise if not retryable."""
    assignments = [
        r
        for r in rows
        if r.message_type == MessageType.TASK_ASSIGNMENT
        and isinstance(r.payload, TaskAssignmentPayload)
        and r.payload.task_id == task_id
    ]
    reports = [
        r
        for r in rows
        if r.message_type == MessageType.TASK_REPORT
        and isinstance(r.payload, TaskReportPayload)
        and r.payload.task_id == task_id
    ]
    if not assignments:
        raise RetryNotEligible(f"no such task: {task_id}")
    if not reports:
        raise RetryNotEligible(f"task {task_id} has no report yet")

    latest_report = reports[-1]
    payload = latest_report.payload
    assert isinstance(payload, TaskReportPayload)
    if payload.status != TaskStatus.BLOCKED:
        raise RetryNotEligible(
            f"task {task_id} not currently blocked (status={payload.status.value})"
        )
    if payload.blocked_on not in RECOVERABLE_BLOCKED_ON:
        raise RetryNotEligible(
            f"task {task_id} blocked_on={payload.blocked_on!r} not recoverable"
        )

    attempt_number = len(assignments) + 1
    if attempt_number > RETRY_ATTEMPT_CAP:
        raise RetryNotEligible(
            f"task {task_id} retry cap reached ({RETRY_ATTEMPT_CAP} attempts)"
        )
    return RetryEligibility(
        original_assignment=assignments[0],
        latest_report=latest_report,
        retry_attempt=attempt_number,
    )


def build_retry_message(
    *, original: AgentMessage, retry_attempt: int
) -> AgentMessage:
    """Build the re-emit. Fresh message_id, same task_id+correlation_id."""
    return original.model_copy(
        update={
            "message_id": uuid4(),
            "metadata": {**original.metadata, "retry_attempt": retry_attempt},
            "hmac_signature": None,
        }
    )
