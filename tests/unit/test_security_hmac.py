from uuid import uuid4

import pytest

from core.messaging.schemas import (
    AgentId,
    AgentMessage,
    MessageType,
    Priority,
    TaskReportPayload,
    TaskStatus,
)
from core.security.hmac_signer import HMACSigner, InvalidSignatureError


@pytest.fixture
def signer() -> HMACSigner:
    return HMACSigner.from_string("a" * 64)


@pytest.fixture
def message() -> AgentMessage:
    return AgentMessage(
        correlation_id=uuid4(),
        sender=AgentId.PRODUCT_MANAGER,
        recipient=AgentId.TEAM_LEAD,
        message_type=MessageType.TASK_REPORT,
        priority=Priority.P3,
        payload=TaskReportPayload(
            task_id=uuid4(),
            status=TaskStatus.DONE,
            progress_pct=100,
            summary="Finished.",
        ),
    )


def test_sign_and_verify_roundtrip(signer: HMACSigner, message: AgentMessage) -> None:
    signed = signer.with_signature(message)
    assert signed.hmac_signature is not None
    signer.verify(signed)


def test_verify_missing_signature(signer: HMACSigner, message: AgentMessage) -> None:
    with pytest.raises(InvalidSignatureError, match="missing"):
        signer.verify(message)


def test_verify_wrong_secret_fails(signer: HMACSigner, message: AgentMessage) -> None:
    signed = signer.with_signature(message)
    other = HMACSigner.from_string("b" * 64)
    with pytest.raises(InvalidSignatureError):
        other.verify(signed)


def test_signature_changes_when_payload_changes(signer: HMACSigner, message: AgentMessage) -> None:
    signed_a = signer.with_signature(message)
    altered = message.model_copy(
        update={
            "payload": TaskReportPayload(
                task_id=message.payload.task_id,  # type: ignore[union-attr]
                status=TaskStatus.IN_PROGRESS,
                progress_pct=50,
                summary="Different.",
            )
        }
    )
    signed_b = signer.with_signature(altered)
    assert signed_a.hmac_signature != signed_b.hmac_signature


def test_secret_must_be_long_enough() -> None:
    with pytest.raises(ValueError, match="at least 32"):
        HMACSigner.from_string("short")
