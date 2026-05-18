"""Prometheus metrics registry. See ADR-006, ADR-007."""

from __future__ import annotations

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, generate_latest

registry = CollectorRegistry()

agent_message_processing_duration = Histogram(
    "agent_message_processing_duration_seconds",
    "End-to-end processing time for one AgentMessage.",
    labelnames=("agent", "message_type"),
    registry=registry,
)

agent_errors_total = Counter(
    "agent_errors_total",
    "Errors raised inside an agent's handle().",
    labelnames=("agent", "error_type"),
    registry=registry,
)

agent_llm_tokens_used_total = Counter(
    "agent_llm_tokens_used_total",
    "Tokens consumed by an agent on a given model (input/output/cached).",
    labelnames=("agent", "model", "tier"),
    registry=registry,
)

agent_human_approvals_pending = Gauge(
    "agent_human_approvals_pending",
    "Reviews waiting for owner approval.",
    registry=registry,
)

subscription_quota_used_pct = Gauge(
    "subscription_quota_used_pct",
    "Estimated subscription quota used this month, in percent.",
    registry=registry,
)

message_bus_queue_depth = Gauge(
    "message_bus_queue_depth",
    "Pending messages in a Redis Streams queue.",
    labelnames=("queue",),
    registry=registry,
)

audit_log_write_failures_total = Counter(
    "audit_log_write_failures_total",
    "Failed audit-log writes. P1 alert if non-zero.",
    registry=registry,
)


def render_metrics() -> bytes:
    """Return the current metrics serialised as Prometheus exposition."""
    return generate_latest(registry)
