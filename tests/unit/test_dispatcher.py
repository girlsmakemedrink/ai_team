"""Unit tests for module-level helpers in core/dispatcher/dispatcher.py.

The integration path is covered by tests/integration/test_dispatcher_e2e.py.
This file tests the small pure helpers without spinning up bus/feed/audit.
"""

from __future__ import annotations

from uuid import UUID, uuid4

from core.dispatcher.dispatcher import _synthesise_failed_report
from core.messaging.schemas import (
    AgentId,
    AgentMessage,
    MessageType,
    Priority,
    TaskAssignmentPayload,
    TaskReportPayload,
    TaskStatus,
)


def _incoming_assignment(
    *,
    sender: AgentId = AgentId.TEAM_LEAD,
    task_id: UUID | None = None,
    parent_task_id: UUID | None = None,
) -> AgentMessage:
    metadata: dict[str, object] = {}
    if parent_task_id is not None:
        metadata["parent_task_id"] = str(parent_task_id)
    return AgentMessage(
        correlation_id=uuid4(),
        sender=sender,
        recipient=AgentId.BACKEND_DEVELOPER,
        message_type=MessageType.TASK_ASSIGNMENT,
        priority=Priority.P2,
        payload=TaskAssignmentPayload(
            task_id=task_id or uuid4(),
            title="t",
            description="d",
        ),
        metadata=metadata,
    )


def test_synthesise_failed_report_carries_correlation_and_task_id() -> None:
    """The synthetic report inherits correlation_id and reuses the
    incoming task_id so the TaskStateReducer rollup can match it to
    the existing child Task row."""
    task_id = uuid4()
    parent_task_id = uuid4()
    incoming = _incoming_assignment(task_id=task_id, parent_task_id=parent_task_id)
    exc = RuntimeError("boom on line 42")

    out = _synthesise_failed_report(role=AgentId.BACKEND_DEVELOPER, incoming=incoming, exc=exc)

    assert out.message_type == MessageType.TASK_REPORT
    assert out.sender == AgentId.BACKEND_DEVELOPER
    assert out.correlation_id == incoming.correlation_id

    payload = out.payload
    assert isinstance(payload, TaskReportPayload)
    assert payload.status == TaskStatus.FAILED
    assert payload.task_id == task_id  # matches incoming, not a fresh uuid
    # Hybrid summary: type name + first line, truncated.
    assert "RuntimeError" in payload.summary
    assert "boom on line 42" in payload.summary

    # parent_task_id rides on metadata so the rollup hits the right
    # parent Task row.
    assert out.metadata.get("parent_task_id") == str(parent_task_id)


def test_synthesise_failed_report_routes_to_team_lead_for_agent_sender() -> None:
    """When the incoming was TL → agent, the failed report routes back
    to TL so the BLOCKED auto-router / rollup path stays consistent
    with real agent task_reports."""
    incoming = _incoming_assignment(sender=AgentId.TEAM_LEAD)
    out = _synthesise_failed_report(
        role=AgentId.BACKEND_DEVELOPER, incoming=incoming, exc=ValueError("x")
    )
    assert out.recipient == AgentId.TEAM_LEAD


def test_synthesise_failed_report_routes_to_user_when_user_was_sender() -> None:
    """A root-task `user → TL` assignment that crashes inside TL itself
    reports back to USER. (TL doesn't normally raise; this guards the
    edge case so a TL crash still rolls up to the owner.)"""
    incoming = _incoming_assignment(sender=AgentId.USER)
    # The role on the synth report is the agent that crashed (TL here);
    # recipient routes back to USER because that's where the chain
    # originated.
    out = _synthesise_failed_report(role=AgentId.TEAM_LEAD, incoming=incoming, exc=KeyError("k"))
    assert out.recipient == AgentId.USER
    assert out.sender == AgentId.TEAM_LEAD


def test_synthesise_failed_report_truncates_long_exception_message() -> None:
    """summary is capped — TaskReportPayload.summary has max_length=2000
    on the schema side; the helper caps to 500 so the audit row stays
    skim-friendly. Full traceback is in structlog."""
    long_msg = "x" * 5_000
    out = _synthesise_failed_report(
        role=AgentId.BACKEND_DEVELOPER,
        incoming=_incoming_assignment(),
        exc=RuntimeError(long_msg),
    )
    payload = out.payload
    assert isinstance(payload, TaskReportPayload)
    assert len(payload.summary) <= 500


def test_synthesise_failed_report_priority_is_p1() -> None:
    """Failures are high-priority for owner visibility."""
    out = _synthesise_failed_report(
        role=AgentId.BACKEND_DEVELOPER,
        incoming=_incoming_assignment(),
        exc=RuntimeError("x"),
    )
    assert out.priority == Priority.P1


# === iter-6 Phase 2: budget-exhausted → BLOCKED synthesis ===


def test_synthesise_blocked_report_for_budget_exhausted() -> None:
    """When the dispatcher catches LLMBudgetExhaustedError, it should
    synthesise TASK_REPORT(status=BLOCKED, blocked_on='budget') instead
    of the default FAILED. BLOCKED does NOT cascade-drop dependents.
    See iter_6.md Phase 2."""
    from core.llm.base import LLMBudgetExhaustedError

    incoming = _incoming_assignment(task_id=uuid4())
    exc = LLMBudgetExhaustedError("budget exhausted: $0.50 over cap")
    out = _synthesise_failed_report(role=AgentId.BACKEND_DEVELOPER, incoming=incoming, exc=exc)
    payload = out.payload
    assert isinstance(payload, TaskReportPayload)
    assert payload.status == TaskStatus.BLOCKED
    assert payload.blocked_on == "budget"
    assert "LLMBudgetExhaustedError" in payload.summary
    # Routes to TL like a normal blocked report.
    assert out.recipient == AgentId.TEAM_LEAD


def test_synthesise_blocked_priority_is_p2_not_p1() -> None:
    """BLOCKED(budget) is recoverable by the owner; not as urgent as a
    crash. P2 keeps it visible without paging."""
    from core.llm.base import LLMBudgetExhaustedError

    out = _synthesise_failed_report(
        role=AgentId.BACKEND_DEVELOPER,
        incoming=_incoming_assignment(),
        exc=LLMBudgetExhaustedError("x"),
    )
    assert out.priority == Priority.P2
