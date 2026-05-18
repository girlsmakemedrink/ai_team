"""Smoke tests that persistence models import and have expected columns."""

from core.persistence.models import (
    AuditLog,
    AuditLogVerification,
    Base,
    Checkpoint,
    FeedEvent,
    PendingReview,
    Task,
)


def test_all_models_share_base() -> None:
    for model in (AuditLog, AuditLogVerification, FeedEvent, Task, Checkpoint, PendingReview):
        assert issubclass(model, Base)


def test_audit_log_has_prev_hash_chain_columns() -> None:
    cols = {c.name for c in AuditLog.__table__.columns}
    assert {"hmac_sig", "prev_hash", "hmac_hash"}.issubset(cols)


def test_audit_log_keyed_for_replay() -> None:
    cols = {c.name for c in AuditLog.__table__.columns}
    assert "correlation_id" in cols
    assert "timestamp" in cols
    assert "payload_json" in cols


def test_feed_events_has_redacted_payload() -> None:
    cols = {c.name for c in FeedEvent.__table__.columns}
    assert "redacted_payload" in cols
    assert "summary" in cols


def test_task_has_target_repo_field() -> None:
    cols = {c.name for c in Task.__table__.columns}
    assert "target_repo" in cols  # ADR-009
    assert "assigned_agent" in cols


def test_pending_review_status_default() -> None:
    cols = {c.name: c for c in PendingReview.__table__.columns}
    assert "status" in cols


def test_checkpoint_carries_quota() -> None:
    cols = {c.name for c in Checkpoint.__table__.columns}
    assert "quota_used_pct" in cols
    assert "digest_markdown" in cols
