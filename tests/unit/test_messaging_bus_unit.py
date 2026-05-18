"""Unit tests for messaging.bus helpers that don't need Redis."""

from core.messaging.bus import (
    DLQ_STREAM,
    group_name,
    stream_name,
)
from core.messaging.schemas import AgentId


def test_stream_name_for_enum() -> None:
    assert stream_name(AgentId.QA_ENGINEER) == "bus:msgs:qa_engineer"


def test_stream_name_for_string() -> None:
    assert stream_name("custom_agent") == "bus:msgs:custom_agent"


def test_group_name_for_enum() -> None:
    assert group_name(AgentId.TEAM_LEAD) == "cg:team_lead"


def test_dlq_stream_constant() -> None:
    assert DLQ_STREAM == "bus:dlq"
