"""Unit tests for `maybe_route_mcp_race_to_blocked`.

iter-10: the LLM emits `task_report(failed)` when its `claude
-p` session's MCP subprocess fails mid-run. The iter-9
pre-flight gate (Phase 1 of iter-9) catches deterministic
startup failures but not these mid-session races. The
substring patterns here are derived verbatim from iter-8 +
iter-9 demo Backend summaries — see
`iter_8_demo_report.md` Failure 1 +
`iter_9_demo_report.md` Failure 1 + `iter_10.md`
success criterion #2.
"""

from __future__ import annotations

from uuid import uuid4

from core.dispatcher.mcp_race_router import maybe_route_mcp_race_to_blocked
from core.messaging.schemas import (
    AgentId,
    AgentMessage,
    MessageType,
    Priority,
    TaskAssignmentPayload,
    TaskReportPayload,
    TaskStatus,
)


def _failed_report(summary: str) -> AgentMessage:
    return AgentMessage(
        correlation_id=uuid4(),
        sender=AgentId.BACKEND_DEVELOPER,
        recipient=AgentId.TEAM_LEAD,
        message_type=MessageType.TASK_REPORT,
        priority=Priority.P1,
        payload=TaskReportPayload(
            task_id=uuid4(),
            status=TaskStatus.FAILED,
            progress_pct=0,
            summary=summary,
        ),
    )


def test_routes_iter9_demo_summary_to_blocked() -> None:
    """iter-9 demo Backend (audit row 124) reported:
    'MCP server ai-team-repo never connected, and the Bash
    tool requires manual approval...'. Verbatim substring."""
    summary = (
        "Backend Developer: tests failed. Implemented the full "
        "idea-validator pipeline. All source files were written "
        "to the worktree filesystem but could not be committed "
        "or pushed: MCP server ai-team-repo never connected, "
        "and the Bash tool requires manual approval for all "
        "git/uv/make commands in this session."
    )
    msg = _failed_report(summary)
    out = maybe_route_mcp_race_to_blocked(msg)

    assert isinstance(out.payload, TaskReportPayload)
    assert out.payload.status == TaskStatus.BLOCKED
    assert out.payload.blocked_on == "mcp_unhealthy"
    # Verbatim summary preserved — the LLM's wording is the
    # most useful diagnostic for the owner.
    assert out.payload.summary == summary
    # task_id, progress_pct, artifacts, kind unchanged.
    assert isinstance(msg.payload, TaskReportPayload)
    assert out.payload.task_id == msg.payload.task_id


def test_routes_iter8_demo_summary_to_blocked() -> None:
    """iter-8 demo Backend reported: 'the ai-team-repo MCP
    server never finished connecting (all three ToolSearch
    retries returned still connecting)'. Two patterns match
    this — both should route."""
    summary = (
        "Backend Developer: tests failed. Blocked: the "
        "`ai-team-repo` MCP server never finished connecting "
        '(all three ToolSearch retries returned "still '
        'connecting"), and the native `git checkout -b` Bash '
        "command was blocked by the permission sandbox."
    )
    out = maybe_route_mcp_race_to_blocked(_failed_report(summary))
    assert isinstance(out.payload, TaskReportPayload)
    assert out.payload.status == TaskStatus.BLOCKED
    assert out.payload.blocked_on == "mcp_unhealthy"


def test_leaves_non_matching_failed_report_unchanged() -> None:
    """A genuine test-assertion failure must NOT route to
    BLOCKED — that would mask code bugs as infrastructure
    problems."""
    summary = (
        "Backend Developer: tests failed. AssertionError in "
        "test_models.py line 42: expected score==7, got 5."
    )
    msg = _failed_report(summary)
    out = maybe_route_mcp_race_to_blocked(msg)

    assert isinstance(out.payload, TaskReportPayload)
    assert out.payload.status == TaskStatus.FAILED
    assert out.payload.blocked_on is None


def test_leaves_done_and_blocked_reports_unchanged() -> None:
    """Status filter: only `failed` reports are subject to
    rewriting. A `done` summary that mentions MCP in passing
    must stay `done`."""
    done_base = _failed_report("ok")
    assert isinstance(done_base.payload, TaskReportPayload)
    done = done_base.model_copy(
        update={
            "payload": done_base.payload.model_copy(
                update={
                    "status": TaskStatus.DONE,
                    "progress_pct": 100,
                    "summary": "MCP server connected; tests passed.",
                }
            )
        }
    )
    blocked_base = _failed_report("ok")
    assert isinstance(blocked_base.payload, TaskReportPayload)
    blocked = blocked_base.model_copy(
        update={
            "payload": blocked_base.payload.model_copy(
                update={
                    "status": TaskStatus.BLOCKED,
                    "summary": "MCP server never connected (already blocked).",
                    "blocked_on": "budget",
                }
            )
        }
    )

    out_done = maybe_route_mcp_race_to_blocked(done)
    out_blocked = maybe_route_mcp_race_to_blocked(blocked)

    assert isinstance(out_done.payload, TaskReportPayload)
    assert out_done.payload.status == TaskStatus.DONE
    assert isinstance(out_blocked.payload, TaskReportPayload)
    assert out_blocked.payload.status == TaskStatus.BLOCKED
    assert out_blocked.payload.blocked_on == "budget"  # not clobbered


def test_leaves_non_task_report_messages_unchanged() -> None:
    """Task assignments, broadcasts, etc. pass through
    untouched even when payload text happens to contain
    matching substrings."""
    msg = AgentMessage(
        correlation_id=uuid4(),
        sender=AgentId.TEAM_LEAD,
        recipient=AgentId.BACKEND_DEVELOPER,
        message_type=MessageType.TASK_ASSIGNMENT,
        priority=Priority.P2,
        payload=TaskAssignmentPayload(
            task_id=uuid4(),
            title="Implement X",
            description=(
                "Build the validator. Note: if the MCP server "
                "never connected, that's an infra issue, not "
                "a code bug."
            ),
        ),
    )
    out = maybe_route_mcp_race_to_blocked(msg)
    # Same object reference — fast pass-through for non-matches.
    assert out is msg
