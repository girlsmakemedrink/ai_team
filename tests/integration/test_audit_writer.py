"""Integration tests for AuditLogWriter: HMAC + prev_hash chain."""
from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import uuid4

import pytest
from sqlalchemy import select, update

from core.audit.writer import AuditLogWriter
from core.messaging.schemas import (
    AgentId,
    AgentMessage,
    MessageType,
    Priority,
    TaskReportPayload,
    TaskStatus,
)
from core.persistence.models import AuditLog

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = pytest.mark.integration

_SECRET = b"a" * 64


def _make_msg(summary: str = "test") -> AgentMessage:
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
            summary=summary,
        ),
    )


async def test_writes_first_row_with_no_prev_hash(
    session_factory: async_sessionmaker[AsyncSession], db_session: AsyncSession
) -> None:
    writer = AuditLogWriter(session_factory, _SECRET)
    msg = _make_msg("first")
    row_id = await writer.write_message(msg)

    row = (
        await db_session.execute(select(AuditLog).where(AuditLog.id == row_id))
    ).scalar_one()
    assert row.prev_hash is None
    assert row.hmac_sig
    assert row.hmac_hash
    assert row.sender == "product_manager"


async def test_chain_links_subsequent_rows(
    session_factory: async_sessionmaker[AsyncSession], db_session: AsyncSession
) -> None:
    writer = AuditLogWriter(session_factory, _SECRET)
    id1 = await writer.write_message(_make_msg("one"))
    id2 = await writer.write_message(_make_msg("two"))
    id3 = await writer.write_message(_make_msg("three"))

    rows = (
        await db_session.execute(
            select(AuditLog).where(AuditLog.id.in_([id1, id2, id3])).order_by(AuditLog.id)
        )
    ).scalars().all()

    # Each row's prev_hash matches the previous row's hmac_hash.
    assert rows[1].prev_hash == rows[0].hmac_hash
    assert rows[2].prev_hash == rows[1].hmac_hash


async def test_verify_chain_intact(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    writer = AuditLogWriter(session_factory, _SECRET)
    for i in range(3):
        await writer.write_message(_make_msg(f"row-{i}"))
    intact, broken = await writer.verify_chain()
    assert intact is True
    assert broken == []


async def test_verify_chain_detects_tamper(
    session_factory: async_sessionmaker[AsyncSession], db_session: AsyncSession
) -> None:
    writer = AuditLogWriter(session_factory, _SECRET)
    for i in range(3):
        await writer.write_message(_make_msg(f"row-{i}"))

    # Pick a middle row and corrupt its payload_json. The hmac_hash
    # stays the same, so the verifier should flag the row as broken
    # because canonical(payload) no longer matches.
    middle = (
        await db_session.execute(
            select(AuditLog).order_by(AuditLog.id).limit(3)
        )
    ).scalars().all()[1]

    corrupted_payload = dict(middle.payload_json)
    corrupted_payload["sender"] = "team_lead"  # change a field
    await db_session.execute(
        update(AuditLog)
        .where(AuditLog.id == middle.id)
        .values(payload_json=corrupted_payload)
    )
    await db_session.commit()

    intact, broken = await writer.verify_chain()
    assert intact is False
    assert middle.id in broken


async def test_wrong_secret_cannot_forge(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    writer = AuditLogWriter(session_factory, _SECRET)
    await writer.write_message(_make_msg("legit"))

    other_writer = AuditLogWriter(session_factory, b"b" * 64)
    intact, broken = await other_writer.verify_chain()
    # With the wrong secret, every row's chain hash fails to verify.
    assert intact is False
    assert len(broken) >= 1
