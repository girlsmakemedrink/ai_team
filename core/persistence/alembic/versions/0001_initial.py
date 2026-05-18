"""Initial schema: audit_log, feed_events, tasks, checkpoints, pending_reviews.

Revision ID: 0001
Revises:
Create Date: 2026-05-18
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "audit_log",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "timestamp", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.Column("correlation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sender", sa.String(50), nullable=False),
        sa.Column("recipient", sa.String(50), nullable=False),
        sa.Column("message_type", sa.String(50), nullable=False),
        sa.Column("priority", sa.String(5), nullable=False),
        sa.Column("iteration", sa.Integer()),
        sa.Column("payload_json", postgresql.JSONB(), nullable=False),
        sa.Column("hmac_sig", sa.String(128), nullable=False),
        sa.Column("prev_hash", sa.String(128)),
        sa.Column("hmac_hash", sa.String(128), nullable=False),
    )
    op.create_index("ix_audit_log_timestamp", "audit_log", ["timestamp"])
    op.create_index("ix_audit_log_correlation_id", "audit_log", ["correlation_id"])
    op.create_index("ix_audit_log_sender", "audit_log", ["sender"])

    op.create_table(
        "audit_log_verifications",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "verified_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.Column("window_start_id", sa.BigInteger(), nullable=False),
        sa.Column("window_end_id", sa.BigInteger(), nullable=False),
        sa.Column("chain_ok", sa.Boolean(), nullable=False),
        sa.Column("notes", sa.Text()),
    )

    op.create_table(
        "feed_events",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "timestamp", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.Column("message_id", postgresql.UUID(as_uuid=True), nullable=False, unique=True),
        sa.Column("correlation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sender", sa.String(50), nullable=False),
        sa.Column("recipient", sa.String(50), nullable=False),
        sa.Column("message_type", sa.String(50), nullable=False),
        sa.Column("priority", sa.String(5), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("redacted_payload", postgresql.JSONB(), nullable=False),
    )
    op.create_index("ix_feed_events_timestamp", "feed_events", ["timestamp"])
    op.create_index("ix_feed_events_correlation_id", "feed_events", ["correlation_id"])
    op.create_index("ix_feed_events_sender", "feed_events", ["sender"])

    op.create_table(
        "tasks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.Column("correlation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("target_repo", sa.String(500)),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("assigned_agent", sa.String(50)),
        sa.Column("priority", sa.String(5), nullable=False, server_default="P3"),
        sa.Column("iteration", sa.Integer()),
        sa.Column(
            "parent_task_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tasks.id"),
        ),
    )
    op.create_index("ix_tasks_correlation_id", "tasks", ["correlation_id"])
    op.create_index("ix_tasks_assigned_agent", "tasks", ["assigned_agent"])

    op.create_table(
        "checkpoints",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.Column("trigger", sa.String(30), nullable=False),
        sa.Column("correlation_id", postgresql.UUID(as_uuid=True)),
        sa.Column("iteration", sa.Integer()),
        sa.Column("digest_markdown", sa.Text(), nullable=False),
        sa.Column("quota_used_pct", sa.Float(), nullable=False, server_default="0"),
    )
    op.create_index("ix_checkpoints_created_at", "checkpoints", ["created_at"])
    op.create_index("ix_checkpoints_correlation_id", "checkpoints", ["correlation_id"])

    op.create_table(
        "pending_reviews",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.Column("correlation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("requesting_agent", sa.String(50), nullable=False),
        sa.Column("task_id", postgresql.UUID(as_uuid=True)),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("target_artifact", sa.String(500)),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.Column("resolution_comment", sa.Text()),
    )
    op.create_index("ix_pending_reviews_created_at", "pending_reviews", ["created_at"])
    op.create_index("ix_pending_reviews_correlation_id", "pending_reviews", ["correlation_id"])

    # === ADR-003: audit_writer role with INSERT-only grant ===
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT FROM pg_catalog.pg_roles WHERE rolname = 'audit_writer'
            ) THEN
                CREATE ROLE audit_writer NOLOGIN;
            END IF;
        END
        $$;
        """
    )
    op.execute("GRANT INSERT ON audit_log TO audit_writer;")
    op.execute("GRANT USAGE, SELECT ON SEQUENCE audit_log_id_seq TO audit_writer;")


def downgrade() -> None:
    op.execute("REVOKE ALL ON audit_log FROM audit_writer;")
    op.execute("REVOKE USAGE, SELECT ON SEQUENCE audit_log_id_seq FROM audit_writer;")
    op.execute("DROP ROLE IF EXISTS audit_writer;")

    op.drop_table("pending_reviews")
    op.drop_table("checkpoints")
    op.drop_table("tasks")
    op.drop_table("feed_events")
    op.drop_table("audit_log_verifications")
    op.drop_table("audit_log")
