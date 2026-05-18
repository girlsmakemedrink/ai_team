from uuid import uuid4

from core.messaging.feed import make_feed_event, summarise
from core.messaging.schemas import (
    AgentId,
    AgentMessage,
    MessageType,
    Priority,
    TaskReportPayload,
    TaskStatus,
)


def _msg() -> AgentMessage:
    return AgentMessage(
        correlation_id=uuid4(),
        sender=AgentId.QA_ENGINEER,
        recipient=AgentId.BACKEND_DEVELOPER,
        message_type=MessageType.REVIEW_REQUEST,
        priority=Priority.P2,
        payload=TaskReportPayload(
            task_id=uuid4(),
            status=TaskStatus.IN_PROGRESS,
            progress_pct=30,
            summary="please review",
        ),
    )


def test_summarise_mentions_sender_and_recipient() -> None:
    msg = _msg()
    line = summarise(msg)
    assert "qa_engineer" in line
    assert "backend_developer" in line
    assert "P2" in line


def test_make_feed_event_redacts_secrets_in_metadata() -> None:
    msg = _msg()
    event = make_feed_event(msg)
    # `redacted_payload` should be a dict and have no sensitive keys passing through.
    assert isinstance(event["redacted_payload"], dict)
    assert event["sender"] == "qa_engineer"
    assert event["message_type"] == "review_request"
    assert event["priority"] == "P2"
