"""SQLAlchemy 2.x async models. See ADR-003, ADR-007."""

from __future__ import annotations

from datetime import datetime  # noqa: TC003  required at runtime by SQLAlchemy
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.sql import func


class Base(DeclarativeBase):
    pass


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    correlation_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False, index=True)
    sender: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    recipient: Mapped[str] = mapped_column(String(50), nullable=False)
    message_type: Mapped[str] = mapped_column(String(50), nullable=False)
    priority: Mapped[str] = mapped_column(String(5), nullable=False)
    iteration: Mapped[int | None] = mapped_column(Integer)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    hmac_sig: Mapped[str] = mapped_column(String(128), nullable=False)
    prev_hash: Mapped[str | None] = mapped_column(String(128))
    hmac_hash: Mapped[str] = mapped_column(String(128), nullable=False)


class AuditLogVerification(Base):
    __tablename__ = "audit_log_verifications"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    verified_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    window_start_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    window_end_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    chain_ok: Mapped[bool] = mapped_column(Boolean, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)


class FeedEvent(Base):
    __tablename__ = "feed_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    message_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), nullable=False, unique=True, index=True
    )
    correlation_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False, index=True)
    sender: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    recipient: Mapped[str] = mapped_column(String(50), nullable=False)
    message_type: Mapped[str] = mapped_column(String(50), nullable=False)
    priority: Mapped[str] = mapped_column(String(5), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    redacted_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    correlation_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    target_repo: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    assigned_agent: Mapped[str | None] = mapped_column(String(50), index=True)
    priority: Mapped[str] = mapped_column(String(5), nullable=False, default="P3")
    iteration: Mapped[int | None] = mapped_column(Integer)
    parent_task_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("tasks.id")
    )


class Checkpoint(Base):
    __tablename__ = "checkpoints"

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    trigger: Mapped[str] = mapped_column(String(30), nullable=False)
    correlation_id: Mapped[UUID | None] = mapped_column(PgUUID(as_uuid=True), index=True)
    iteration: Mapped[int | None] = mapped_column(Integer)
    digest_markdown: Mapped[str] = mapped_column(Text, nullable=False)
    quota_used_pct: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)


class PendingReview(Base):
    __tablename__ = "pending_reviews"

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    correlation_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False, index=True)
    requesting_agent: Mapped[str] = mapped_column(String(50), nullable=False)
    task_id: Mapped[UUID | None] = mapped_column(PgUUID(as_uuid=True))
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    target_artifact: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolution_comment: Mapped[str | None] = mapped_column(Text)
