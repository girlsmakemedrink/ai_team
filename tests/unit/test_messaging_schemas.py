from uuid import uuid4

import pytest
from pydantic import ValidationError

from core.messaging.schemas import (
    SCHEMA_VERSION,
    AgentId,
    AgentMessage,
    MessageType,
    Priority,
    TaskAssignmentPayload,
    TaskReportPayload,
    TaskStatus,
)


def _make_task_report() -> AgentMessage:
    return AgentMessage(
        correlation_id=uuid4(),
        sender=AgentId.PRODUCT_MANAGER,
        recipient=AgentId.TEAM_LEAD,
        message_type=MessageType.TASK_REPORT,
        priority=Priority.P3,
        payload=TaskReportPayload(
            task_id=uuid4(),
            status=TaskStatus.IN_PROGRESS,
            progress_pct=50,
            summary="halfway",
        ),
    )


def test_minimal_message_roundtrips() -> None:
    msg = _make_task_report()
    raw = msg.model_dump_json()
    decoded = AgentMessage.model_validate_json(raw)
    assert decoded == msg


def test_schema_version_stamped() -> None:
    msg = _make_task_report()
    assert msg.schema_version == SCHEMA_VERSION


def test_payload_discriminator_picks_right_subclass() -> None:
    payload = TaskAssignmentPayload(task_id=uuid4(), title="x", description="y")
    msg = AgentMessage(
        correlation_id=uuid4(),
        sender=AgentId.USER,
        recipient=AgentId.TEAM_LEAD,
        message_type=MessageType.TASK_ASSIGNMENT,
        priority=Priority.P2,
        payload=payload,
    )
    raw = msg.model_dump_json()
    decoded = AgentMessage.model_validate_json(raw)
    assert isinstance(decoded.payload, TaskAssignmentPayload)


def test_message_is_frozen() -> None:
    msg = _make_task_report()
    with pytest.raises(ValidationError):
        msg.sender = AgentId.QA_ENGINEER  # type: ignore[misc]


def test_priority_default_is_p3() -> None:
    msg = AgentMessage(
        correlation_id=uuid4(),
        sender=AgentId.TEAM_LEAD,
        recipient=AgentId.USER,
        message_type=MessageType.TASK_REPORT,
        payload=TaskReportPayload(
            task_id=uuid4(),
            status=TaskStatus.DONE,
            progress_pct=100,
            summary="done",
        ),
    )
    assert msg.priority == Priority.P3


def test_progress_pct_bounds() -> None:
    with pytest.raises(ValidationError):
        TaskReportPayload(
            task_id=uuid4(),
            status=TaskStatus.IN_PROGRESS,
            progress_pct=101,
            summary="oops",
        )


def test_canonical_json_is_stable() -> None:
    msg = _make_task_report()
    a = msg.canonical_json()
    b = msg.canonical_json()
    assert a == b


def test_canonical_json_excludes_signature_when_requested() -> None:
    msg = _make_task_report()
    with_sig = msg.model_copy(update={"hmac_signature": "deadbeef"})
    assert with_sig.canonical_json(include_signature=False) == msg.canonical_json()
    assert with_sig.canonical_json(include_signature=True) != msg.canonical_json()
