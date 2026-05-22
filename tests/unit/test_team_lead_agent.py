"""Tests for TeamLeadAgent — Opus, decomposition + BLOCKED auto-routing.

The decomposition path is exercised end-to-end via the integration test
`tests/integration/test_dispatcher_e2e.py`. This file unit-tests the
new Phase-4 BLOCKED-routing branch in isolation (pure dispatch, no LLM
call needed)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import uuid4

import pytest

from agents.team_lead import TeamLeadAgent
from agents.team_lead.agent import _AUTO_ROUTED_MARKER
from core.messaging.schemas import (
    AgentId,
    AgentMessage,
    BroadcastPayload,
    MessageType,
    Priority,
    TaskAssignmentPayload,
    TaskReportPayload,
    TaskStatus,
)

if TYPE_CHECKING:
    from uuid import UUID

    from core.llm.base import LLMResponse


class _StubLLM:
    """TL.handle() should never call the LLM for BLOCKED routing.
    If it does, this stub raises so the test fails loudly."""

    async def invoke(self, **kwargs: object) -> LLMResponse:  # pragma: no cover
        raise AssertionError("TL invoked LLM during BLOCKED routing")

    async def reset_session(self, session_id: str) -> None:
        return None


def _blocked_report(
    *,
    sender: AgentId = AgentId.DEVOPS,
    blocked_on: str | None = "backend_developer",
    summary: str = "DevOps blocked: blocked: requires backend_developer (agents/foo.py).",
) -> AgentMessage:
    return AgentMessage(
        correlation_id=uuid4(),
        sender=sender,
        recipient=AgentId.TEAM_LEAD,
        message_type=MessageType.TASK_REPORT,
        priority=Priority.P2,
        payload=TaskReportPayload(
            task_id=uuid4(),
            status=TaskStatus.BLOCKED,
            progress_pct=0,
            summary=summary,
            artifacts=[],
            blocked_on=blocked_on,
        ),
    )


@pytest.mark.asyncio
async def test_routes_blocked_with_explicit_blocked_on_field() -> None:
    agent = TeamLeadAgent(llm=_StubLLM())
    msg = _blocked_report(blocked_on="backend_developer")

    outputs = await agent.handle(msg)

    assert len(outputs) == 1
    out = outputs[0]
    assert out.sender == AgentId.TEAM_LEAD
    assert out.recipient == AgentId.BACKEND_DEVELOPER
    assert out.message_type == MessageType.TASK_ASSIGNMENT
    payload = out.payload
    assert isinstance(payload, TaskAssignmentPayload)
    assert payload.title.startswith("Unblock:")
    assert _AUTO_ROUTED_MARKER in payload.description
    assert "DevOps" in payload.description or "devops" in payload.description
    # Same correlation chain — auditor follows one thread.
    assert out.correlation_id == msg.correlation_id


@pytest.mark.asyncio
async def test_routes_blocked_by_parsing_summary_when_blocked_on_missing() -> None:
    agent = TeamLeadAgent(llm=_StubLLM())
    msg = _blocked_report(
        blocked_on=None,
        summary="Frontend blocked: blocked: requires backend_developer (new API endpoint).",
    )

    outputs = await agent.handle(msg)

    assert len(outputs) == 1
    assert outputs[0].recipient == AgentId.BACKEND_DEVELOPER


@pytest.mark.asyncio
async def test_does_not_loop_when_summary_already_auto_routed() -> None:
    """Anti-loop: if a BLOCKED report itself originated from a prior
    auto-route, TL refuses to route a second time."""
    agent = TeamLeadAgent(llm=_StubLLM())
    msg = _blocked_report(
        blocked_on="backend_developer",
        summary=(
            f"Backend blocked: [{_AUTO_ROUTED_MARKER} from devops] cannot "
            "complete; needs Backend territory but tools are insufficient."
        ),
    )

    outputs = await agent.handle(msg)

    assert outputs == []


@pytest.mark.asyncio
async def test_ignores_blocked_with_no_target() -> None:
    """No blocked_on field and no parseable summary → no-op. Owner
    sees the BLOCKED in the digest."""
    agent = TeamLeadAgent(llm=_StubLLM())
    msg = _blocked_report(blocked_on=None, summary="DevOps blocked: unknown reason.")

    outputs = await agent.handle(msg)

    assert outputs == []


@pytest.mark.asyncio
async def test_ignores_blocked_with_unknown_target_role() -> None:
    """`blocked_on='someone_random'` AND unparseable summary → no-op.
    Owner sees in digest. (If blocked_on doesn't resolve but the summary
    *does* mention a valid role, that's covered by the summary-parsing
    fallback above.)"""
    agent = TeamLeadAgent(llm=_StubLLM())
    msg = _blocked_report(
        blocked_on="someone_random",
        summary="DevOps blocked: tooling issue, no clear owner.",
    )

    outputs = await agent.handle(msg)

    assert outputs == []


@pytest.mark.asyncio
async def test_ignores_blocked_targeting_team_lead_itself() -> None:
    """`blocked_on='team_lead'` → no-op. Self-routing would loop."""
    agent = TeamLeadAgent(llm=_StubLLM())
    msg = _blocked_report(blocked_on="team_lead")

    outputs = await agent.handle(msg)

    assert outputs == []


@pytest.mark.asyncio
async def test_skips_non_blocked_task_reports() -> None:
    """DONE / FAILED / IN_PROGRESS reports are not re-routed."""
    agent = TeamLeadAgent(llm=_StubLLM())
    msg = AgentMessage(
        correlation_id=uuid4(),
        sender=AgentId.BACKEND_DEVELOPER,
        recipient=AgentId.TEAM_LEAD,
        message_type=MessageType.TASK_REPORT,
        priority=Priority.P2,
        payload=TaskReportPayload(
            task_id=uuid4(),
            status=TaskStatus.DONE,
            progress_pct=100,
            summary="OK",
        ),
    )

    outputs = await agent.handle(msg)

    assert outputs == []


# === iter-21: BLOCKED(task_too_large) → TL self-targeted re-decomp ===


@pytest.mark.asyncio
async def test_re_decomposes_on_blocked_task_too_large() -> None:
    """When Backend's iter-21 tripwire fires, TL emits a self-targeted
    task_assignment carrying the original description (echoed in the
    BLOCKED summary) and a re-decompose instruction."""
    agent = TeamLeadAgent(llm=_StubLLM())
    msg = _blocked_report(
        sender=AgentId.BACKEND_DEVELOPER,
        blocked_on="task_too_large",
        summary=(
            "task too large: description 1800 chars > 1500 threshold\n\n"
            "original task description (first 800 chars):\n"
            "Implement the idea-validator pipeline including the "
            "data-model layer, the service layer, and the API surface."
        ),
    )

    outputs = await agent.handle(msg)

    assert len(outputs) == 1
    out = outputs[0]
    assert out.sender == AgentId.TEAM_LEAD
    assert out.recipient == AgentId.TEAM_LEAD
    assert out.message_type == MessageType.TASK_ASSIGNMENT
    assert isinstance(out.payload, TaskAssignmentPayload)
    assert _AUTO_ROUTED_MARKER in out.payload.description
    assert "re-decompose" in out.payload.description.lower()
    assert "idea-validator pipeline" in out.payload.description
    assert out.correlation_id == msg.correlation_id
    # iter-29a regression guard: the self-task_assignment must reuse the
    # BLOCKED Backend task_id, not generate a fresh uuid4(). A fresh ID
    # would be an orphan (the dispatcher skips persisting self-assigns)
    # and any decomp child inserted under it would fail the
    # tasks_parent_task_id_fkey constraint.
    assert isinstance(msg.payload, TaskReportPayload)
    assert out.payload.task_id == msg.payload.task_id


@pytest.mark.asyncio
async def test_re_decomposes_on_blocked_via_summary_prefix() -> None:
    """iter-24: primary self-eject signal is the BLOCKED summary's
    Scope pre-flight prefix. Even when the LLM fills blocked_on with
    something completely unrelated (e.g. demo R#1's verbose paragraph
    about untracked directories), TL recognises the prefix and routes
    via re-decomposition. This is structural — the prompt template
    forces the LLM to copy "Scope pre-flight:" verbatim.
    """
    agent = TeamLeadAgent(llm=_StubLLM())
    msg = _blocked_report(
        sender=AgentId.BACKEND_DEVELOPER,
        blocked_on="examples/ is untracked in worktree-iter-NN and absent from main",
        summary=(
            "Scope pre-flight: 3 files / 230 LOC estimated. Echoing "
            "original task description: Implement the idea-validator core "
            "pipeline including the data-model layer and the service layer."
        ),
    )
    outputs = await agent.handle(msg)
    assert len(outputs) == 1
    assert outputs[0].recipient == AgentId.TEAM_LEAD
    assert isinstance(outputs[0].payload, TaskAssignmentPayload)
    assert "re-decompose" in outputs[0].payload.description.lower()
    assert "idea-validator core" in outputs[0].payload.description


@pytest.mark.asyncio
async def test_blocked_without_scope_prefix_does_not_route_to_re_decomp() -> None:
    """Inverse: a genuine non-scope BLOCKED (e.g. blocked_on=devops)
    should NOT trigger the re-decomposition path. TL's normal routing
    (route to AgentId(blocked_on)) should handle it instead.
    """
    agent = TeamLeadAgent(llm=_StubLLM())
    msg = _blocked_report(
        sender=AgentId.BACKEND_DEVELOPER,
        blocked_on="devops",  # legitimate dependency on DevOps work
        summary="Need CI workflow that runs pytest on the new branch.",
    )
    outputs = await agent.handle(msg)
    # Should route to DevOps (one auto-hop), not self-target re-decomp.
    assert len(outputs) == 1
    assert outputs[0].recipient == AgentId.DEVOPS
    assert outputs[0].sender == AgentId.TEAM_LEAD


@pytest.mark.asyncio
async def test_re_decomposes_on_blocked_with_task_too_large_substring() -> None:
    """iter-23 belt-and-suspenders: even if the schema enum is somehow
    bypassed and Backend emits a verbose blocked_on like
    "task_too_large: 3 files exceeds limit", TL still recognises it and
    routes through the re-decompose path. Substring match catches
    legacy/in-flight messages from older builds where the LLM
    interpreted the prompt example as paraphrasable.
    """
    agent = TeamLeadAgent(llm=_StubLLM())
    msg = _blocked_report(
        sender=AgentId.BACKEND_DEVELOPER,
        blocked_on="task_too_large: 3 production files exceed 2-file scope",
        summary="Backend scope estimate exceeds turn-1 budget",
    )
    outputs = await agent.handle(msg)
    assert len(outputs) == 1
    assert outputs[0].recipient == AgentId.TEAM_LEAD
    assert isinstance(outputs[0].payload, TaskAssignmentPayload)
    assert "re-decompose" in outputs[0].payload.description.lower()


def test_tl_prompt_teaches_mandatory_architect_backend_depends_on() -> None:
    """iter-22 Phase 2: when both architect and backend_developer are
    in the same decomposition, Backend MUST depends_on Architect."""
    from pathlib import Path

    text = (Path(__file__).resolve().parents[2] / "prompts" / "team_lead.md").read_text()
    # Pin substrings from the new rule:
    assert "Architect" in text and "Backend" in text
    assert "MUST" in text
    assert "depends_on" in text
    # The rule must be conditional ("when both roles co-occur"):
    assert "co-occur" in text.lower() or "both" in text.lower()


@pytest.mark.asyncio
async def test_anti_loop_refuses_second_re_decomp_on_already_routed_marker() -> None:
    """Anti-loop guard: if the BLOCKED summary already carries the
    'auto-routed already' marker (Backend's tripwire echoes it when
    the incoming task description already had the auto-route marker),
    TL refuses a second re-decomp hop."""
    agent = TeamLeadAgent(llm=_StubLLM())
    msg = _blocked_report(
        sender=AgentId.BACKEND_DEVELOPER,
        blocked_on="task_too_large",
        summary=(
            "[auto-routed already] task too large: 1700 chars > 1500 threshold\n\n"
            "original task description (first 800 chars):\n"
            "second re-decomp attempt should refuse."
        ),
    )

    outputs = await agent.handle(msg)

    assert outputs == []


# === depends_on / metadata stamping (iter-3 Phase 2) ===


def _stub_llm_response(structured: dict[str, Any]) -> LLMResponse:
    """Build a minimal LLMResponse — only `structured` is exercised by build_outputs."""
    from core.llm.base import LLMResponse, TokensUsage  # local import to keep file lean

    return LLMResponse(
        text="",
        structured=structured,
        session_id="test-session",
        tokens=TokensUsage(input=10, output=20, cached_input=0, model="claude-opus-4-7"),
        cost_estimate_cents=5,
        duration_ms=123,
        validated_against_schema=True,
    )


def _incoming_task(task_id: UUID | None = None) -> AgentMessage:
    return AgentMessage(
        correlation_id=uuid4(),
        sender=AgentId.USER,
        recipient=AgentId.TEAM_LEAD,
        message_type=MessageType.TASK_ASSIGNMENT,
        priority=Priority.P2,
        payload=TaskAssignmentPayload(
            task_id=task_id or uuid4(),
            title="root",
            description="root task",
        ),
    )


def test_build_outputs_emits_one_message_per_subtask() -> None:
    agent = TeamLeadAgent(llm=_StubLLM())
    incoming = _incoming_task()
    plan = {
        "summary": "decomposed",
        "subtasks": [
            {
                "id": "arch",
                "recipient": "architect",
                "title": "Design",
                "description": "Write ADR",
                "priority": "P2",
                "depends_on": [],
            },
            {
                "id": "be",
                "recipient": "backend_developer",
                "title": "Build",
                "description": "Implement per ADR",
                "priority": "P2",
                "depends_on": ["arch"],
            },
        ],
    }
    outputs = agent.build_outputs(_stub_llm_response(plan), incoming)

    assignments = [o for o in outputs if o.message_type == MessageType.TASK_ASSIGNMENT]
    assert len(assignments) == 2
    arch_out, be_out = assignments
    assert arch_out.recipient == AgentId.ARCHITECT
    assert be_out.recipient == AgentId.BACKEND_DEVELOPER


def test_build_outputs_stamps_subtask_id_and_parent_task_id() -> None:
    agent = TeamLeadAgent(llm=_StubLLM())
    incoming = _incoming_task()
    plan = {
        "summary": "x",
        "subtasks": [
            {
                "id": "arch",
                "recipient": "architect",
                "title": "T",
                "description": "D",
                "priority": "P2",
                "depends_on": [],
            }
        ],
    }
    outputs = agent.build_outputs(_stub_llm_response(plan), incoming)
    assert isinstance(incoming.payload, TaskAssignmentPayload)

    assignments = [o for o in outputs if o.message_type == MessageType.TASK_ASSIGNMENT]
    arch = assignments[0]
    assert arch.metadata.get("subtask_id") == "arch"
    assert arch.metadata.get("parent_task_id") == str(incoming.payload.task_id)


def test_build_outputs_resolves_depends_on_to_predecessor_uuids() -> None:
    agent = TeamLeadAgent(llm=_StubLLM())
    incoming = _incoming_task()
    plan = {
        "summary": "x",
        "subtasks": [
            {
                "id": "arch",
                "recipient": "architect",
                "title": "T",
                "description": "D",
                "priority": "P2",
                "depends_on": [],
            },
            {
                "id": "be",
                "recipient": "backend_developer",
                "title": "T",
                "description": "D",
                "priority": "P2",
                "depends_on": ["arch"],
            },
        ],
    }
    outputs = agent.build_outputs(_stub_llm_response(plan), incoming)
    assignments = [o for o in outputs if o.message_type == MessageType.TASK_ASSIGNMENT]
    arch_msg, be_msg = assignments
    arch_payload = arch_msg.payload
    be_payload = be_msg.payload
    assert isinstance(arch_payload, TaskAssignmentPayload)
    assert isinstance(be_payload, TaskAssignmentPayload)

    # be.metadata["depends_on"] is a list of UUID strings matching arch's
    # payload.task_id (not arch's message_id and not arch's slug).
    assert be_msg.metadata.get("depends_on") == [str(arch_payload.task_id)]
    # arch has no predecessors → empty list (NOT missing key).
    assert arch_msg.metadata.get("depends_on") == []


def test_build_outputs_handles_subtasks_missing_depends_on_key() -> None:
    """Backwards compatible: a subtask with no `depends_on` key is treated as []."""
    agent = TeamLeadAgent(llm=_StubLLM())
    incoming = _incoming_task()
    plan = {
        "summary": "x",
        "subtasks": [
            {
                "id": "arch",
                "recipient": "architect",
                "title": "T",
                "description": "D",
                "priority": "P2",
            }
        ],
    }
    outputs = agent.build_outputs(_stub_llm_response(plan), incoming)
    assignments = [o for o in outputs if o.message_type == MessageType.TASK_ASSIGNMENT]
    assert assignments[0].metadata.get("depends_on") == []


def test_build_outputs_rejects_unknown_depends_on_slug() -> None:
    """Forward-ref / unknown slug → loud failure (TASK_REPORT to USER)."""
    agent = TeamLeadAgent(llm=_StubLLM())
    incoming = _incoming_task()
    plan = {
        "summary": "x",
        "subtasks": [
            {
                "id": "be",
                "recipient": "backend_developer",
                "title": "T",
                "description": "D",
                "priority": "P2",
                "depends_on": ["arch"],  # slug that doesn't exist in this decomposition
            }
        ],
    }
    outputs = agent.build_outputs(_stub_llm_response(plan), incoming)
    assert len(outputs) == 1
    fail = outputs[0]
    assert fail.recipient == AgentId.USER
    assert fail.message_type == MessageType.TASK_REPORT
    fail_payload = fail.payload
    assert isinstance(fail_payload, TaskReportPayload)
    assert fail_payload.status == TaskStatus.FAILED
    assert "depends_on" in fail_payload.summary.lower() or "arch" in fail_payload.summary


def test_build_outputs_supports_forward_reference() -> None:
    """A subtask listed earlier can depend_on one listed later — both
    slugs are in the same decomposition. Order at runtime is enforced
    by HoldQueue, not by list order."""
    agent = TeamLeadAgent(llm=_StubLLM())
    incoming = _incoming_task()
    plan = {
        "summary": "x",
        "subtasks": [
            # 'qa' listed first, depends on 'be' listed later
            {
                "id": "qa",
                "recipient": "qa_engineer",
                "title": "T",
                "description": "D",
                "priority": "P3",
                "depends_on": ["be"],
            },
            {
                "id": "be",
                "recipient": "backend_developer",
                "title": "T",
                "description": "D",
                "priority": "P2",
                "depends_on": [],
            },
        ],
    }
    outputs = agent.build_outputs(_stub_llm_response(plan), incoming)
    assignments = [o for o in outputs if o.message_type == MessageType.TASK_ASSIGNMENT]
    qa_msg, be_msg = assignments
    be_payload = be_msg.payload
    assert isinstance(be_payload, TaskAssignmentPayload)
    assert qa_msg.metadata.get("depends_on") == [str(be_payload.task_id)]


def test_build_outputs_returns_fail_report_when_no_subtasks() -> None:
    agent = TeamLeadAgent(llm=_StubLLM())
    incoming = _incoming_task()
    outputs = agent.build_outputs(_stub_llm_response(None), incoming)  # type: ignore[arg-type]
    assert len(outputs) == 1
    assert outputs[0].recipient == AgentId.USER
    payload = outputs[0].payload
    assert isinstance(payload, TaskReportPayload)
    assert payload.status == TaskStatus.FAILED


# === iter-4 Phase 3: pin conservative depends_on rule wording ===


def test_tl_prompt_includes_conservative_depends_on_rule() -> None:
    """Pin the iter-4 rule wording so a future prompt edit doesn't
    silently revert the discipline. See iter_3_demo_report.md Failure 3
    (TL added depends_on=[backend, design] on Frontend despite the v2
    spec saying the landing page is static)."""
    prompt_path = TeamLeadAgent.system_prompt_path
    text = prompt_path.read_text()
    assert "literally cannot start without" in text, (
        "TL prompt must teach conservative depends_on — see iter_4.md Phase 3"
    )
    assert "Before emitting, audit each `depends_on` entry" in text


# === iter-20 Phase 2: pin Backend decomposition guidance ===


def test_tl_prompt_teaches_backend_decomposition() -> None:
    """iter-20 Phase 2: TL prompt must explicitly instruct
    decomposition of large Backend tasks. Backend's 600s timeout
    was the chain-killer in iter-19 demo run #1; iter-20 prompts
    TL to avoid emitting single huge Backend subtasks. See
    iter_19_demo_report.md Caveat A."""
    text = TeamLeadAgent.system_prompt_path.read_text()
    assert "200 LOC" in text or "200 lines" in text, (
        "TL prompt missing iter-20 Backend-decomposition guidance"
    )
    assert "backend" in text.lower()


# === iter-4 Phase 4: DAG-preview broadcast ===


def test_build_outputs_emits_dag_preview_broadcast() -> None:
    """TL's outputs include exactly one BROADCAST message describing
    the planned DAG, alongside the per-subtask assignments. Lets the
    owner see the plan in `ai-team watch` seconds before agents start
    — catches a wrong DAG before it commits resources. See
    iter_4.md Phase 4."""
    agent = TeamLeadAgent(llm=_StubLLM())
    incoming = _incoming_task()
    plan = {
        "summary": "test plan",
        "subtasks": [
            {
                "id": "arch",
                "recipient": "architect",
                "title": "T",
                "description": "D",
                "priority": "P2",
                "depends_on": [],
            },
            {
                "id": "be",
                "recipient": "backend_developer",
                "title": "T",
                "description": "D",
                "priority": "P2",
                "depends_on": ["arch"],
            },
        ],
    }
    outputs = agent.build_outputs(_stub_llm_response(plan), incoming)

    broadcasts = [o for o in outputs if o.message_type == MessageType.BROADCAST]
    assignments = [o for o in outputs if o.message_type == MessageType.TASK_ASSIGNMENT]
    assert len(broadcasts) == 1
    assert len(assignments) == 2

    preview = broadcasts[0].payload
    assert isinstance(preview, BroadcastPayload)
    assert preview.topic == "tl.dag_preview"
    # The body must mention both slugs and the dependency relationship.
    assert "arch" in preview.body
    assert "be" in preview.body
    assert "depends_on" in preview.body or "→" in preview.body
