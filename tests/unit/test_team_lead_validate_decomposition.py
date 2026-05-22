"""TL `validate_product` intent: 4-subtask DAG with 3-parallel + 1-gated.

Validates inputs propagation, depends_on shape, recipients, and slug
propagation across subtasks.

All three tests are pure-Python (no async, no LLM subprocess) and rely on
the scripted _FAKE_DECOMP fixture + build_outputs().  The schema extension
(optional `inputs` on subtask items) and build_outputs propagation both
landed in iter-26a commit 68e8c31 — these tests verify that existing
plumbing accepts the validate_product decomposition shape.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import jsonschema  # type: ignore[import-untyped]

from agents.team_lead.agent import DECOMPOSITION_SCHEMA, TeamLeadAgent
from core.llm.base import LLMResponse, TokensUsage
from core.messaging.schemas import (
    AgentId,
    AgentMessage,
    MessageType,
    Priority,
    TaskAssignmentPayload,
)

# ---------------------------------------------------------------------------
# Stub LLM
# ---------------------------------------------------------------------------


class _StubLLM:
    def __init__(self, structured: dict[str, Any]) -> None:
        self._structured = structured

    async def invoke(self, **kwargs: object) -> LLMResponse:
        return LLMResponse(
            text="",
            structured=self._structured,
            session_id="stub-session",
            tokens=TokensUsage(input=10, output=20, cached_input=0, model="claude-opus-4-7"),
            cost_estimate_cents=5,
            duration_ms=123,
            validated_against_schema=True,
        )

    async def reset_session(self, session_id: str) -> None:
        return None


# ---------------------------------------------------------------------------
# Scripted decomposition — mirrors what the real LLM should emit for
# inputs.intent == "validate_product" after the prompt section is appended.
# ---------------------------------------------------------------------------

_FAKE_DECOMP: dict[str, Any] = {
    "summary": "Validate telegram-tech-publisher candidate",
    "subtasks": [
        {
            "id": "comp",
            "recipient": "market_researcher",
            "title": "Deep competitor scan for telegram-tech-publisher",
            "description": "Standard-depth competitor + signal scrape.",
            "priority": "P2",
            "depends_on": [],
            "inputs": {
                "intent": "validate_competitors",
                "slug": "telegram-tech-publisher",
                "depth": "standard",
                "candidate_brief": "**Slug:** telegram-tech-publisher\n...",
                "target_market": "developer_influencers_telegram_500_to_100k_subs",
                "constraints": {"owner_profile": "solo_developer"},
            },
        },
        {
            "id": "tech",
            "recipient": "architect",
            "title": "Tech-risk register for telegram-tech-publisher",
            "description": "Telegram Bot API limits + voice calibration feasibility.",
            "priority": "P2",
            "depends_on": [],
            "inputs": {
                "intent": "validate_tech_risk",
                "slug": "telegram-tech-publisher",
                "candidate_brief": "**Slug:** telegram-tech-publisher\n...",
                "constraints": {"owner_profile": "solo_developer"},
            },
        },
        {
            "id": "rev",
            "recipient": "product_manager",
            "title": "Revenue model stress-test for telegram-tech-publisher",
            "description": "Pricing tiers + CAC/LTV envelope + break-even.",
            "priority": "P2",
            "depends_on": [],
            "inputs": {
                "intent": "validate_revenue_model",
                "slug": "telegram-tech-publisher",
                "candidate_brief": "**Slug:** telegram-tech-publisher\n...",
                "target_market": "developer_influencers_telegram_500_to_100k_subs",
                "constraints": {"owner_profile": "solo_developer"},
            },
        },
        {
            "id": "synth",
            "recipient": "qa_engineer",
            "title": "Validation synthesis + go/no-go for telegram-tech-publisher",
            "description": "Read 3 upstream artifacts; emit recommendation.",
            "priority": "P2",
            "depends_on": ["comp", "tech", "rev"],
            "inputs": {
                "intent": "synthesize_validation",
                "slug": "telegram-tech-publisher",
                "upstream_ids": ["comp", "tech", "rev"],
            },
        },
    ],
}


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _incoming_validate_task() -> AgentMessage:
    """Root TASK_ASSIGNMENT with inputs.intent == 'validate_product'."""
    return AgentMessage(
        correlation_id=uuid4(),
        sender=AgentId.USER,
        recipient=AgentId.TEAM_LEAD,
        message_type=MessageType.TASK_ASSIGNMENT,
        priority=Priority.P2,
        payload=TaskAssignmentPayload(
            task_id=uuid4(),
            title="Validate product: telegram-tech-publisher",
            description="**Slug:** telegram-tech-publisher\n...",
            inputs={
                "intent": "validate_product",
                "slug": "telegram-tech-publisher",
                "depth": "standard",
                "candidate_brief": "**Slug:** telegram-tech-publisher\n...",
                "constraints": {"owner_profile": "solo_developer"},
            },
        ),
    )


def _make_response() -> LLMResponse:
    return LLMResponse(
        text="",
        structured=_FAKE_DECOMP,
        session_id="stub",
        tokens=TokensUsage(input=10, output=20, cached_input=0, model="claude-opus-4-7"),
        cost_estimate_cents=5,
        duration_ms=100,
        validated_against_schema=True,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_validate_product_decomposition_passes_schema_validation() -> None:
    """The four-subtask DAG validates against DECOMPOSITION_SCHEMA."""
    jsonschema.validate(_FAKE_DECOMP, DECOMPOSITION_SCHEMA)


def test_validate_product_inputs_propagate_to_subtasks() -> None:
    """build_outputs propagates inputs into TaskAssignmentPayload.inputs
    for every subtask (iter-26a 68e8c31 plumbing)."""
    agent = TeamLeadAgent(llm=_StubLLM(_FAKE_DECOMP))
    incoming = _incoming_validate_task()
    response = _make_response()

    outputs = agent.build_outputs(response, incoming)
    assignments = [m for m in outputs if m.message_type == MessageType.TASK_ASSIGNMENT]

    assert len(assignments) == 4, f"Expected 4 assignments, got {len(assignments)}"

    recipients = {a.recipient for a in assignments}
    assert recipients == {
        AgentId.MARKET_RESEARCHER,
        AgentId.ARCHITECT,
        AgentId.PRODUCT_MANAGER,
        AgentId.QA_ENGINEER,
    }

    intents = {
        a.payload.inputs.get("intent")
        for a in assignments
        if isinstance(a.payload, TaskAssignmentPayload)
    }
    assert intents == {
        "validate_competitors",
        "validate_tech_risk",
        "validate_revenue_model",
        "synthesize_validation",
    }


def test_synth_subtask_depends_on_other_three() -> None:
    """QA's metadata['depends_on'] must reference the UUIDs of the other 3 tasks."""
    agent = TeamLeadAgent(llm=_StubLLM(_FAKE_DECOMP))
    incoming = _incoming_validate_task()
    response = _make_response()

    outputs = agent.build_outputs(response, incoming)
    assignments = [m for m in outputs if m.message_type == MessageType.TASK_ASSIGNMENT]

    qa_assignment = next(a for a in assignments if a.recipient == AgentId.QA_ENGINEER)
    qa_depends_on = set(qa_assignment.metadata.get("depends_on", []))

    assert len(qa_depends_on) == 3, f"Expected 3 depends_on, got {len(qa_depends_on)}"

    other_task_ids = {
        str(a.payload.task_id)
        for a in assignments
        if a.recipient != AgentId.QA_ENGINEER and isinstance(a.payload, TaskAssignmentPayload)
    }
    assert qa_depends_on == other_task_ids, (
        f"QA depends_on {qa_depends_on!r} must equal other 3 task IDs {other_task_ids!r}"
    )
