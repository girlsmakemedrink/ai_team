from core.observability.logging import (
    bind_correlation_id,
    clear_correlation_id,
    configure_logging,
    correlation_id_var,
)
from core.observability.metrics import (
    agent_errors_total,
    agent_human_approvals_pending,
    agent_llm_tokens_used_total,
    agent_message_processing_duration,
    audit_log_write_failures_total,
    message_bus_queue_depth,
    registry,
    render_metrics,
    subscription_quota_used_pct,
)


def test_configure_logging_runs_without_error() -> None:
    # basicConfig is idempotent under pytest (which configures logging first);
    # smoke test that calling configure_logging doesn't blow up.
    configure_logging("DEBUG")
    configure_logging("INFO")


def test_correlation_id_bind_clear() -> None:
    token = bind_correlation_id("abc-123")
    assert correlation_id_var.get() == "abc-123"
    clear_correlation_id(token)
    assert correlation_id_var.get() is None


def test_correlation_id_accepts_uuid() -> None:
    from uuid import uuid4

    u = uuid4()
    token = bind_correlation_id(u)
    assert correlation_id_var.get() == str(u)
    clear_correlation_id(token)


def test_render_metrics_emits_exposition() -> None:
    blob = render_metrics().decode()
    assert "agent_message_processing_duration_seconds" in blob
    assert "subscription_quota_used_pct" in blob


def test_all_expected_metrics_registered() -> None:
    # If any of these were missing, import would fail; this is a contract
    # smoke test that the module exposes the full Prometheus contract.
    for m in (
        agent_message_processing_duration,
        agent_errors_total,
        agent_llm_tokens_used_total,
        agent_human_approvals_pending,
        subscription_quota_used_pct,
        message_bus_queue_depth,
        audit_log_write_failures_total,
    ):
        assert m is not None
    assert registry is not None


def test_metric_increments_visible_in_render() -> None:
    agent_errors_total.labels(agent="qa_engineer", error_type="test").inc()
    out = render_metrics().decode()
    assert "agent_errors_total" in out
