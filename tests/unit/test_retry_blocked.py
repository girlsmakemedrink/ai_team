"""Unit tests for retry_blocked helper. iter-11 Phase 1."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from core.messaging.schemas import (
    AgentId,
    AgentMessage,
    MessageType,
    Priority,
    TaskAssignmentPayload,
    TaskReportPayload,
    TaskStatus,
)
from core.retry.retry_blocked import (
    RetryEligibility,
    RetryNotEligible,
    build_retry_message,
    check_retry_eligibility,
)


def _assignment(
    task_id: UUID,
    correlation_id: UUID,
    recipient: AgentId,
    *,
    retry_attempt: int | None = None,
) -> AgentMessage:
    meta: dict[str, object] = {}
    if retry_attempt is not None:
        meta["retry_attempt"] = retry_attempt
    return AgentMessage(
        correlation_id=correlation_id,
        sender=AgentId.TEAM_LEAD,
        recipient=recipient,
        message_type=MessageType.TASK_ASSIGNMENT,
        priority=Priority.P2,
        payload=TaskAssignmentPayload(
            task_id=task_id,
            title="Build X",
            description="Do the thing",
            target_repo="examples/sandbox/idea-validator",
        ),
        metadata=meta,
    )


def _report(
    task_id: UUID,
    correlation_id: UUID,
    status: TaskStatus,
    *,
    blocked_on: str | None = None,
) -> AgentMessage:
    return AgentMessage(
        correlation_id=correlation_id,
        sender=AgentId.BACKEND_DEVELOPER,
        recipient=AgentId.TEAM_LEAD,
        message_type=MessageType.TASK_REPORT,
        priority=Priority.P2,
        payload=TaskReportPayload(
            task_id=task_id,
            status=status,
            progress_pct=0,
            summary="x",
            blocked_on=blocked_on,
        ),
    )


class TestEligibility:
    def test_blocked_mcp_unhealthy_is_eligible(self) -> None:
        task_id = uuid4()
        cid = uuid4()
        rows = [
            _assignment(task_id, cid, AgentId.BACKEND_DEVELOPER),
            _report(task_id, cid, TaskStatus.BLOCKED, blocked_on="mcp_unhealthy"),
        ]
        result = check_retry_eligibility(task_id, rows)
        assert isinstance(result, RetryEligibility)
        # 1 prior assignment + this retry → attempt number 2
        assert result.retry_attempt == 2
        assert isinstance(result.original_assignment.payload, TaskAssignmentPayload)
        assert result.original_assignment.payload.task_id == task_id

    def test_blocked_budget_is_eligible(self) -> None:
        task_id = uuid4()
        cid = uuid4()
        rows = [
            _assignment(task_id, cid, AgentId.BACKEND_DEVELOPER),
            _report(task_id, cid, TaskStatus.BLOCKED, blocked_on="budget"),
        ]
        result = check_retry_eligibility(task_id, rows)
        assert isinstance(result, RetryEligibility)
        assert result.retry_attempt == 2

    def test_blocked_task_too_large_is_eligible(self) -> None:
        """iter-23: TL auto-re-decomposes task_too_large BLOCKEDs, but
        the owner-side `ai-team retry-blocked` CLI should also accept
        it (iter-22 demo Caveat C: 422 was misleading)."""
        task_id = uuid4()
        cid = uuid4()
        rows = [
            _assignment(task_id, cid, AgentId.BACKEND_DEVELOPER),
            _report(task_id, cid, TaskStatus.BLOCKED, blocked_on="task_too_large"),
        ]
        result = check_retry_eligibility(task_id, rows)
        assert isinstance(result, RetryEligibility)
        assert result.retry_attempt == 2

    def test_blocked_unknown_blocked_on_not_eligible(self) -> None:
        task_id = uuid4()
        cid = uuid4()
        rows = [
            _assignment(task_id, cid, AgentId.BACKEND_DEVELOPER),
            _report(task_id, cid, TaskStatus.BLOCKED, blocked_on="unknown_reason"),
        ]
        with pytest.raises(RetryNotEligible, match="not recoverable"):
            check_retry_eligibility(task_id, rows)

    def test_not_currently_blocked_not_eligible(self) -> None:
        task_id = uuid4()
        cid = uuid4()
        rows = [
            _assignment(task_id, cid, AgentId.BACKEND_DEVELOPER),
            _report(task_id, cid, TaskStatus.DONE),
        ]
        with pytest.raises(RetryNotEligible, match="not currently blocked"):
            check_retry_eligibility(task_id, rows)

    def test_no_task_rows_not_eligible(self) -> None:
        task_id = uuid4()
        with pytest.raises(RetryNotEligible, match="no such task"):
            check_retry_eligibility(task_id, [])

    def test_retry_attempt_cap(self) -> None:
        task_id = uuid4()
        cid = uuid4()
        # 5 assignments (initial + 4 retries) → next retry would be the 6th, rejected.
        rows = [
            _assignment(task_id, cid, AgentId.BACKEND_DEVELOPER),
            _assignment(task_id, cid, AgentId.BACKEND_DEVELOPER, retry_attempt=2),
            _assignment(task_id, cid, AgentId.BACKEND_DEVELOPER, retry_attempt=3),
            _assignment(task_id, cid, AgentId.BACKEND_DEVELOPER, retry_attempt=4),
            _assignment(task_id, cid, AgentId.BACKEND_DEVELOPER, retry_attempt=5),
            _report(task_id, cid, TaskStatus.BLOCKED, blocked_on="mcp_unhealthy"),
        ]
        with pytest.raises(RetryNotEligible, match="retry cap reached"):
            check_retry_eligibility(task_id, rows)

    def test_no_report_yet_not_eligible(self) -> None:
        task_id = uuid4()
        cid = uuid4()
        rows = [_assignment(task_id, cid, AgentId.BACKEND_DEVELOPER)]
        with pytest.raises(RetryNotEligible, match="no report yet"):
            check_retry_eligibility(task_id, rows)


class TestBuildRetryMessage:
    def test_same_task_id_and_correlation_id_fresh_message_id(self) -> None:
        task_id = uuid4()
        cid = uuid4()
        original = _assignment(task_id, cid, AgentId.BACKEND_DEVELOPER)
        retry = build_retry_message(original=original, retry_attempt=2)

        assert isinstance(retry.payload, TaskAssignmentPayload)
        assert retry.payload.task_id == task_id
        assert retry.correlation_id == cid
        assert retry.recipient == AgentId.BACKEND_DEVELOPER
        assert retry.metadata["retry_attempt"] == 2
        assert retry.message_id != original.message_id
        # HMAC must be re-signed by caller.
        assert retry.hmac_signature is None
