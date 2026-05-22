"""TL decomposition under inputs.intent == 'brainstorm_products' must
emit one MR sub-task per niche (no depends_on between them) and one
QA sub-task gated on all 3.

Pattern A (all-at-once): TL emits all 4 task_assignments in the
initial build_outputs() call.  The dispatcher's HoldQueue gates the
QA subtask off the bus until the 3 MR tasks report DONE — that is the
dispatcher's concern, not the TL's.  This test exercises only TL's
decomposition routing logic against a scripted LLM response.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from agents.team_lead.agent import TeamLeadAgent
from core.llm.base import LLMResponse, TokensUsage
from core.messaging.schemas import (
    AgentId,
    AgentMessage,
    MessageType,
    Priority,
    TaskAssignmentPayload,
)

# ---------------------------------------------------------------------------
# Stub LLM — returns a scripted decomposition response.
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
# inputs.intent == "brainstorm_products" after the prompt section is added.
# DECOMPOSITION_SCHEMA now allows an optional `inputs` field on subtask items
# (additionalProperties was extended in agents/team_lead/agent.py Step 1).
# build_outputs() propagates subtask["inputs"] → TaskAssignmentPayload.inputs.
# ---------------------------------------------------------------------------

_ROOT_CONSTRAINTS: dict[str, object] = {"solo_developer": True}


def _scripted_decomposition() -> dict[str, object]:
    return {
        "summary": "Brainstorm 5 candidates per niche, then rank.",
        "subtasks": [
            {
                "id": "brainstorm_dev_tools",
                "recipient": "market_researcher",
                "title": "Brainstorm 5 dev_tools candidates",
                "description": "Brainstorm 5 monetizable candidates in the dev_tools niche.",
                "priority": "P2",
                "depends_on": [],
                "inputs": {
                    "mode": "brainstorm_niche",
                    "niche": "dev_tools",
                    "candidates": 5,
                    "constraints": _ROOT_CONSTRAINTS,
                },
            },
            {
                "id": "brainstorm_b2b_smb",
                "recipient": "market_researcher",
                "title": "Brainstorm 5 b2b_smb candidates",
                "description": "Brainstorm 5 monetizable candidates in the b2b_smb niche.",
                "priority": "P2",
                "depends_on": [],
                "inputs": {
                    "mode": "brainstorm_niche",
                    "niche": "b2b_smb",
                    "candidates": 5,
                    "constraints": _ROOT_CONSTRAINTS,
                },
            },
            {
                "id": "brainstorm_creator_tools",
                "recipient": "market_researcher",
                "title": "Brainstorm 5 creator_tools candidates",
                "description": "Brainstorm 5 monetizable candidates in the creator_tools niche.",
                "priority": "P2",
                "depends_on": [],
                "inputs": {
                    "mode": "brainstorm_niche",
                    "niche": "creator_tools",
                    "candidates": 5,
                    "constraints": _ROOT_CONSTRAINTS,
                },
            },
            {
                "id": "rank_candidates",
                "recipient": "qa_engineer",
                "title": "Rank all brainstorm candidates",
                "description": (
                    "Read 3 brainstorm artifacts; merge; rank by composite_score; "
                    "write _combined_ranking.md; request_human_review."
                ),
                "priority": "P2",
                "depends_on": [
                    "brainstorm_dev_tools",
                    "brainstorm_b2b_smb",
                    "brainstorm_creator_tools",
                ],
                "inputs": {
                    "intent": "rank_brainstorm_candidates",
                },
            },
        ],
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _incoming_brainstorm_task() -> AgentMessage:
    """Root TASK_ASSIGNMENT with inputs.intent == 'brainstorm_products'."""
    return AgentMessage(
        correlation_id=uuid4(),
        sender=AgentId.USER,
        recipient=AgentId.TEAM_LEAD,
        message_type=MessageType.TASK_ASSIGNMENT,
        priority=Priority.P2,
        payload=TaskAssignmentPayload(
            task_id=uuid4(),
            title="Brainstorm monetizable products",
            description="Find the best product candidates across 3 niches.",
            inputs={
                "intent": "brainstorm_products",
                "niches": ["dev_tools", "b2b_smb", "creator_tools"],
                "candidates_per_niche": 5,
                "constraints": {"solo_developer": True},
            },
        ),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_tl_decomposes_brainstorm_products_emits_4_assignments() -> None:
    """Pattern A: all 4 subtasks are emitted at once from build_outputs().

    3 go to market_researcher (no depends_on between them — parallel).
    1 goes to qa_engineer, gated on all 3 MR slugs.
    The HoldQueue in the dispatcher handles the actual gating at runtime.
    """
    plan = _scripted_decomposition()
    agent = TeamLeadAgent(llm=_StubLLM(plan))
    incoming = _incoming_brainstorm_task()

    # Use build_outputs directly so we don't need an async test runner for
    # a purely synchronous path (build_outputs is sync).
    from core.llm.base import LLMResponse, TokensUsage

    response = LLMResponse(
        text="",
        structured=plan,
        session_id="stub",
        tokens=TokensUsage(input=10, output=20, cached_input=0, model="claude-opus-4-7"),
        cost_estimate_cents=5,
        duration_ms=100,
        validated_against_schema=True,
    )
    outputs = agent.build_outputs(response, incoming)

    assignments = [o for o in outputs if o.message_type == MessageType.TASK_ASSIGNMENT]
    broadcasts = [o for o in outputs if o.message_type == MessageType.BROADCAST]

    # 3 MR + 1 QA
    assert len(assignments) == 4, f"Expected 4 assignments, got {len(assignments)}"
    # 1 DAG-preview broadcast at index 0
    assert len(broadcasts) == 1

    mr_assignments = [a for a in assignments if a.recipient == AgentId.MARKET_RESEARCHER]
    qa_assignments = [a for a in assignments if a.recipient == AgentId.QA_ENGINEER]

    assert len(mr_assignments) == 3, f"Expected 3 MR assignments, got {len(mr_assignments)}"
    assert len(qa_assignments) == 1, f"Expected 1 QA assignment, got {len(qa_assignments)}"


def test_tl_mr_subtasks_have_no_depends_on() -> None:
    """The 3 MR sub-tasks must have depends_on=[] — they run in parallel."""
    plan = _scripted_decomposition()
    agent = TeamLeadAgent(llm=_StubLLM(plan))
    incoming = _incoming_brainstorm_task()

    from core.llm.base import LLMResponse, TokensUsage

    response = LLMResponse(
        text="",
        structured=plan,
        session_id="stub",
        tokens=TokensUsage(input=10, output=20, cached_input=0, model="claude-opus-4-7"),
        cost_estimate_cents=5,
        duration_ms=100,
        validated_against_schema=True,
    )
    outputs = agent.build_outputs(response, incoming)

    mr_assignments = [
        o
        for o in outputs
        if o.message_type == MessageType.TASK_ASSIGNMENT
        and o.recipient == AgentId.MARKET_RESEARCHER
    ]

    for mr in mr_assignments:
        assert mr.metadata.get("depends_on") == [], (
            f"MR subtask {mr.metadata.get('subtask_id')!r} must have no depends_on"
        )


def test_tl_qa_subtask_gated_on_all_3_mr_task_ids() -> None:
    """QA's metadata['depends_on'] must reference the UUIDs of all 3 MR tasks."""
    plan = _scripted_decomposition()
    agent = TeamLeadAgent(llm=_StubLLM(plan))
    incoming = _incoming_brainstorm_task()

    from core.llm.base import LLMResponse, TokensUsage

    response = LLMResponse(
        text="",
        structured=plan,
        session_id="stub",
        tokens=TokensUsage(input=10, output=20, cached_input=0, model="claude-opus-4-7"),
        cost_estimate_cents=5,
        duration_ms=100,
        validated_against_schema=True,
    )
    outputs = agent.build_outputs(response, incoming)

    assignments = [o for o in outputs if o.message_type == MessageType.TASK_ASSIGNMENT]

    mr_task_ids = {
        str(o.payload.task_id)
        for o in assignments
        if o.recipient == AgentId.MARKET_RESEARCHER and isinstance(o.payload, TaskAssignmentPayload)
    }
    assert len(mr_task_ids) == 3

    qa_assignment = next(o for o in assignments if o.recipient == AgentId.QA_ENGINEER)
    qa_depends_on = set(qa_assignment.metadata.get("depends_on", []))

    assert qa_depends_on == mr_task_ids, (
        f"QA depends_on {qa_depends_on!r} must equal MR task IDs {mr_task_ids!r}"
    )


def test_tl_mr_subtask_slugs_cover_all_3_niches() -> None:
    """Each of the 3 niches appears in exactly one MR subtask slug."""
    plan = _scripted_decomposition()
    agent = TeamLeadAgent(llm=_StubLLM(plan))
    incoming = _incoming_brainstorm_task()

    from core.llm.base import LLMResponse, TokensUsage

    response = LLMResponse(
        text="",
        structured=plan,
        session_id="stub",
        tokens=TokensUsage(input=10, output=20, cached_input=0, model="claude-opus-4-7"),
        cost_estimate_cents=5,
        duration_ms=100,
        validated_against_schema=True,
    )
    outputs = agent.build_outputs(response, incoming)

    mr_slugs = {
        o.metadata.get("subtask_id", "")
        for o in outputs
        if o.message_type == MessageType.TASK_ASSIGNMENT
        and o.recipient == AgentId.MARKET_RESEARCHER
    }

    expected_niches = {"dev_tools", "b2b_smb", "creator_tools"}
    for niche in expected_niches:
        assert any(niche in slug for slug in mr_slugs), (
            f"No MR subtask slug contains niche {niche!r}; got slugs {mr_slugs!r}"
        )


def test_tl_qa_subtask_slug_is_rank_candidates() -> None:
    """QA subtask must have the canonical slug 'rank_candidates'."""
    plan = _scripted_decomposition()
    agent = TeamLeadAgent(llm=_StubLLM(plan))
    incoming = _incoming_brainstorm_task()

    from core.llm.base import LLMResponse, TokensUsage

    response = LLMResponse(
        text="",
        structured=plan,
        session_id="stub",
        tokens=TokensUsage(input=10, output=20, cached_input=0, model="claude-opus-4-7"),
        cost_estimate_cents=5,
        duration_ms=100,
        validated_against_schema=True,
    )
    outputs = agent.build_outputs(response, incoming)

    qa_assignments = [
        o
        for o in outputs
        if o.message_type == MessageType.TASK_ASSIGNMENT and o.recipient == AgentId.QA_ENGINEER
    ]
    assert len(qa_assignments) == 1
    assert qa_assignments[0].metadata.get("subtask_id") == "rank_candidates"


def test_tl_prompt_includes_brainstorm_products_intent() -> None:
    """Pin that the prompt teaches 'brainstorm_products' intent routing."""
    text = TeamLeadAgent.system_prompt_path.read_text()
    assert "brainstorm_products" in text, (
        "TL prompt must include the 'brainstorm_products' intent section"
    )
    assert "market_researcher" in text
    assert "rank_brainstorm_candidates" in text, (
        "TL prompt must teach QA to run 'rank_brainstorm_candidates'"
    )


def _build_outputs_for_plan(plan: dict[str, object]) -> list[AgentMessage]:
    """Helper: run build_outputs() synchronously with a scripted LLM response."""
    from core.llm.base import LLMResponse, TokensUsage

    agent = TeamLeadAgent(llm=_StubLLM(plan))
    incoming = _incoming_brainstorm_task()
    response = LLMResponse(
        text="",
        structured=plan,
        session_id="stub",
        tokens=TokensUsage(input=10, output=20, cached_input=0, model="claude-opus-4-7"),
        cost_estimate_cents=5,
        duration_ms=100,
        validated_against_schema=True,
    )
    return agent.build_outputs(response, incoming)


def test_tl_mr_subtasks_propagate_structured_inputs() -> None:
    """build_outputs() must forward subtask['inputs'] into payload.inputs for MR tasks.

    This verifies the fix for the design gap where the previous implementation
    encoded mode/niche in description text — downstream MR dispatch reads
    payload.inputs.mode, not description.
    """
    plan = _scripted_decomposition()
    outputs = _build_outputs_for_plan(plan)

    mr_assignments = [
        o
        for o in outputs
        if o.message_type == MessageType.TASK_ASSIGNMENT
        and o.recipient == AgentId.MARKET_RESEARCHER
        and isinstance(o.payload, TaskAssignmentPayload)
    ]
    assert len(mr_assignments) == 3

    niche_to_assignment = {}
    for a in mr_assignments:
        assert isinstance(a.payload, TaskAssignmentPayload)
        niche = a.payload.inputs.get("niche")
        assert niche is not None, (
            f"MR subtask {a.metadata.get('subtask_id')!r} missing inputs.niche"
        )
        niche_to_assignment[niche] = a

    for niche in ("dev_tools", "b2b_smb", "creator_tools"):
        assert niche in niche_to_assignment, f"No MR subtask found for niche {niche!r}"
        niche_payload = niche_to_assignment[niche].payload
        assert isinstance(niche_payload, TaskAssignmentPayload)
        inputs = niche_payload.inputs
        assert inputs.get("mode") == "brainstorm_niche", (
            f"MR subtask for {niche!r} missing inputs.mode='brainstorm_niche'; got {inputs!r}"
        )
        assert inputs.get("niche") == niche, (
            f"MR subtask inputs.niche mismatch: expected {niche!r}, got {inputs.get('niche')!r}"
        )
        assert inputs.get("candidates") == 5, (
            f"MR subtask for {niche!r} missing inputs.candidates=5; got {inputs!r}"
        )
        assert inputs.get("constraints") == _ROOT_CONSTRAINTS, (
            f"MR subtask for {niche!r} constraints mismatch: got {inputs.get('constraints')!r}"
        )


def test_tl_qa_subtask_propagates_structured_inputs() -> None:
    """build_outputs() must forward subtask['inputs'] into payload.inputs for the QA task.

    QA dispatch (Task 6) reads payload.inputs.intent == 'rank_brainstorm_candidates'
    to choose the ranking workflow — without this, QA falls back to its default mode.
    """
    plan = _scripted_decomposition()
    outputs = _build_outputs_for_plan(plan)

    qa_assignments = [
        o
        for o in outputs
        if o.message_type == MessageType.TASK_ASSIGNMENT
        and o.recipient == AgentId.QA_ENGINEER
        and isinstance(o.payload, TaskAssignmentPayload)
    ]
    assert len(qa_assignments) == 1
    qa_payload = qa_assignments[0].payload
    assert isinstance(qa_payload, TaskAssignmentPayload)
    qa_inputs = qa_payload.inputs
    assert qa_inputs == {"intent": "rank_brainstorm_candidates"}, (
        "QA subtask payload.inputs mismatch: expected rank_brainstorm_candidates, "
        f"got {qa_inputs!r}"
    )


def test_tl_subtasks_without_inputs_field_default_to_empty_dict() -> None:
    """Backward-compatibility: subtasks that omit 'inputs' must produce payload.inputs == {}.

    Pre-iter-26a decompositions never included an 'inputs' key. The schema
    change must be backward-compatible — existing TL outputs must still work.
    """
    plan: dict[str, object] = {
        "summary": "Legacy decomposition without inputs field.",
        "subtasks": [
            {
                "id": "arch",
                "recipient": "architect",
                "title": "Design the system",
                "description": "Write an ADR.",
                "priority": "P2",
                "depends_on": [],
                # NOTE: no 'inputs' key — simulates pre-iter-26a LLM output
            },
        ],
    }
    outputs = _build_outputs_for_plan(plan)

    assignments = [o for o in outputs if o.message_type == MessageType.TASK_ASSIGNMENT]
    assert len(assignments) == 1
    assert isinstance(assignments[0].payload, TaskAssignmentPayload)
    assert assignments[0].payload.inputs == {}, (
        f"Expected empty inputs for legacy subtask, got {assignments[0].payload.inputs!r}"
    )
