"""Tests for BackendDeveloperAgent — Sonnet, code + tests + PR.

The agent's Python side is thin: it invokes claude -p with the right
system prompt, allowed_tools (MCP-only, no raw Bash/Write), and a
JSON-schema for the structured task_report. The actual code-writing,
test-running, branch-creating, and PR-opening happens *inside the LLM
turn*, via the `mcp__ai_team_repo__*` tools — those are exercised in
end-to-end demo, not here. Unit tests pin: agent identity, allowed
tools, structured-response unpacking, failure paths.
"""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import pytest

from agents.backend_developer import BackendDeveloperAgent
from agents.backend_developer.agent import _is_task_too_large
from core.llm.base import LLMResponse, TokensUsage
from core.messaging.schemas import (
    AgentId,
    AgentMessage,
    MessageType,
    Priority,
    TaskAssignmentPayload,
    TaskReportPayload,
    TaskStatus,
)

_REPO_ROOT_FOR_PROMPT = Path(__file__).resolve().parents[2]


class _StubLLM:
    def __init__(self, response: LLMResponse) -> None:
        self._response = response
        self.calls: list[dict[str, object]] = []

    async def invoke(self, **kwargs: object) -> LLMResponse:
        self.calls.append(kwargs)
        return self._response

    async def reset_session(self, session_id: str) -> None:
        return None


def _backend_response(
    *,
    pr_url: str = "https://github.com/x/y/pull/42",
    tests_passed: bool = True,
) -> LLMResponse:
    structured = {
        "branch": "agent/backend_developer/iter2-idea-validator",
        "summary": "Implemented idea-validator pipeline with tests.",
        "files_written": [
            "examples/sandbox/idea-validator/src/pipeline.py",
            "examples/sandbox/idea-validator/tests/test_pipeline.py",
        ],
        "tests_passed": tests_passed,
        "pr_url": pr_url,
    }
    return LLMResponse(
        text=json.dumps(structured),
        structured=structured,
        tools_used=[],
        session_id="be-sess",
        tokens=TokensUsage(input=100, output=200, model="claude-sonnet-4-6"),
        cost_estimate_cents=15,
        duration_ms=2000,
        validated_against_schema=True,
        raw={},
    )


def _task_assignment() -> AgentMessage:
    return AgentMessage(
        correlation_id=uuid4(),
        sender=AgentId.TEAM_LEAD,
        recipient=AgentId.BACKEND_DEVELOPER,
        message_type=MessageType.TASK_ASSIGNMENT,
        priority=Priority.P2,
        payload=TaskAssignmentPayload(
            task_id=uuid4(),
            title="Implement idea-validator pipeline",
            description="See ADR-0010 and docs/sandbox/idea_validator_spec.md.",
            target_repo="examples/sandbox/idea-validator",
        ),
    )


def test_role_and_model_tier() -> None:
    assert BackendDeveloperAgent.role == AgentId.BACKEND_DEVELOPER
    assert BackendDeveloperAgent.model_tier == "sonnet"


def test_allowed_tools_excludes_raw_bash_write_edit() -> None:
    """ADR-004: Backend gets MCP tools only; raw Bash / Write / Edit are forbidden."""
    forbidden = {"Bash", "Write", "Edit", "MultiEdit"}
    overlap = set(BackendDeveloperAgent.allowed_tools) & forbidden
    assert not overlap, f"Backend must not have raw {overlap} access"


def test_mcp_env_uses_allow_star_with_infra_denylist() -> None:
    """Backend writes anywhere in target_repo EXCEPT infra/ and
    .github/workflows/ (DevOps territory) — `*` allow + denylist
    via scope.py's AI_TEAM_PATH_DENY_PREFIXES."""
    env = BackendDeveloperAgent.mcp_env
    assert env["AI_TEAM_PATH_PREFIXES"] == "*"
    deny = env["AI_TEAM_PATH_DENY_PREFIXES"]
    assert "infra/" in deny
    assert ".github/workflows/" in deny


def test_allowed_tools_includes_mcp_repo_surface() -> None:
    """Backend's whole point is having the MCP repo tools."""
    needed = {
        "mcp__ai_team_repo__create_branch",
        "mcp__ai_team_repo__write_file_in_scope",
        "mcp__ai_team_repo__run_shell",
        "mcp__ai_team_repo__open_pr",
    }
    missing = needed - set(BackendDeveloperAgent.allowed_tools)
    assert not missing, f"Backend allowlist is missing {missing}"


@pytest.mark.asyncio
async def test_handle_reports_done_with_pr_url_on_success() -> None:
    agent = BackendDeveloperAgent(llm=_StubLLM(_backend_response()))
    outputs = await agent.handle(_task_assignment())

    assert len(outputs) == 1
    report = outputs[0]
    assert report.sender == AgentId.BACKEND_DEVELOPER
    assert report.recipient == AgentId.TEAM_LEAD
    assert report.message_type == MessageType.TASK_REPORT
    payload = report.payload
    assert isinstance(payload, TaskReportPayload)
    assert payload.status.value == "done"
    assert "https://github.com/x/y/pull/42" in payload.summary
    assert payload.artifacts == [
        "examples/sandbox/idea-validator/src/pipeline.py",
        "examples/sandbox/idea-validator/tests/test_pipeline.py",
    ]


@pytest.mark.asyncio
async def test_handle_reports_failed_when_tests_did_not_pass() -> None:
    agent = BackendDeveloperAgent(llm=_StubLLM(_backend_response(tests_passed=False)))
    outputs = await agent.handle(_task_assignment())

    payload = outputs[0].payload
    assert isinstance(payload, TaskReportPayload)
    assert payload.status.value == "failed"
    assert "tests failed" in payload.summary.lower()


@pytest.mark.asyncio
async def test_handle_reports_failed_on_missing_structured_output() -> None:
    bad = LLMResponse(
        text="model wandered",
        structured=None,
        tools_used=[],
        session_id="x",
        tokens=TokensUsage(input=1, output=1, model="claude-sonnet-4-6"),
        cost_estimate_cents=0,
        duration_ms=1,
        validated_against_schema=False,
        raw={},
    )
    agent = BackendDeveloperAgent(llm=_StubLLM(bad))
    outputs = await agent.handle(_task_assignment())

    payload = outputs[0].payload
    assert isinstance(payload, TaskReportPayload)
    assert payload.status.value == "failed"


@pytest.mark.asyncio
async def test_handle_skips_non_task_assignment() -> None:
    agent = BackendDeveloperAgent(llm=_StubLLM(_backend_response()))
    other = AgentMessage(
        correlation_id=uuid4(),
        sender=AgentId.TEAM_LEAD,
        recipient=AgentId.BACKEND_DEVELOPER,
        message_type=MessageType.QUESTION,
        priority=Priority.P3,
        payload={"kind": "question", "question_id": str(uuid4()), "text": "hi"},
    )
    assert await agent.handle(other) == []


# ---------- iter-21 tripwire tests ----------
#
# Backend pre-flight rejects too-large task_assignments BEFORE invoking
# the LLM (and burning 600s on doomed work). See iter_21.md Phase 1.


def _tripwire_assignment(description: str) -> AgentMessage:
    return AgentMessage(
        correlation_id=uuid4(),
        sender=AgentId.TEAM_LEAD,
        recipient=AgentId.BACKEND_DEVELOPER,
        message_type=MessageType.TASK_ASSIGNMENT,
        priority=Priority.P1,
        payload=TaskAssignmentPayload(
            task_id=uuid4(),
            title="tripwire probe",
            description=description,
        ),
    )


def test_is_task_too_large_fires_on_long_description(tmp_path: Path) -> None:
    description = "create core/foo.py and tests/unit/test_foo.py\n\n" + ("x" * 1600)
    too_large, diag = _is_task_too_large(description, tmp_path)
    assert too_large is True
    assert "1500" in diag or "chars" in diag.lower()


def test_is_task_too_large_fires_on_three_unknown_file_paths(tmp_path: Path) -> None:
    description = (
        "Implement the data-model layer.\n\n"
        "Write core/foo/alpha.py, core/foo/beta.py, "
        "and tests/unit/test_foo_alpha.py."
    )
    too_large, diag = _is_task_too_large(description, tmp_path)
    assert too_large is True
    assert "file" in diag.lower() or "path" in diag.lower()


def test_is_task_too_large_does_not_fire_on_small_task(tmp_path: Path) -> None:
    (tmp_path / "core").mkdir()
    (tmp_path / "core" / "existing.py").write_text("# stub")
    description = "Edit core/existing.py to add the validate() helper."
    too_large, diag = _is_task_too_large(description, tmp_path)
    assert too_large is False, diag


@pytest.mark.asyncio
async def test_handle_emits_blocked_with_task_too_large_on_long_description(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("AI_TEAM_REPO_ROOT", str(tmp_path))
    stub = _StubLLM(_backend_response())
    agent = BackendDeveloperAgent(llm=stub)
    msg = _tripwire_assignment("x" * 1700)

    outputs = await agent.handle(msg)

    assert stub.calls == [], "LLM must not be invoked on tripwire reject"
    assert len(outputs) == 1
    report = outputs[0]
    assert report.sender == AgentId.BACKEND_DEVELOPER
    assert report.recipient == AgentId.TEAM_LEAD
    assert report.message_type == MessageType.TASK_REPORT
    assert isinstance(report.payload, TaskReportPayload)
    assert report.payload.status == TaskStatus.BLOCKED
    assert report.payload.blocked_on == "task_too_large"
    assert "task too large" in report.payload.summary.lower()


@pytest.mark.asyncio
async def test_handle_blocked_summary_echoes_auto_route_marker(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("AI_TEAM_REPO_ROOT", str(tmp_path))
    stub = _StubLLM(_backend_response())
    agent = BackendDeveloperAgent(llm=stub)
    msg = _tripwire_assignment(
        "[auto-routed from team_lead] re-decompose this work.\n\n" + ("x" * 1600)
    )

    outputs = await agent.handle(msg)

    assert stub.calls == []
    assert len(outputs) == 1
    report = outputs[0]
    assert isinstance(report.payload, TaskReportPayload)
    assert "auto-routed already" in report.payload.summary.lower()


# ---------- iter-22 LLM-self-eject tests ----------
#
# The Python tripwire (iter-21) is now defense-in-depth. The primary
# defense is the LLM emitting status='blocked' on turn 1 from its
# Scope pre-flight. See iter_22.md Phase 1.


def _backend_blocked_response(
    *,
    blocked_on: str = "task_too_large",
    summary: str = "Scope pre-flight: 3 files / 250 LOC estimated; emitting BLOCKED.",
) -> LLMResponse:
    structured = {
        "branch": "",
        "summary": summary,
        "files_written": [],
        "tests_passed": False,
        "pr_url": "",
        "status": "blocked",
        "blocked_on": blocked_on,
    }
    return LLMResponse(
        text=json.dumps(structured),
        structured=structured,
        tools_used=[],
        session_id="be-blocked-sess",
        tokens=TokensUsage(input=50, output=80, model="claude-sonnet-4-6"),
        cost_estimate_cents=3,
        duration_ms=4_000,
        validated_against_schema=True,
        raw={},
    )


@pytest.mark.asyncio
async def test_handle_emits_blocked_when_llm_self_ejects() -> None:
    agent = BackendDeveloperAgent(llm=_StubLLM(_backend_blocked_response()))
    outputs = await agent.handle(_task_assignment())

    assert len(outputs) == 1
    report = outputs[0]
    assert isinstance(report.payload, TaskReportPayload)
    assert report.payload.status == TaskStatus.BLOCKED
    assert report.payload.blocked_on == "task_too_large"
    assert "scope" in report.payload.summary.lower()


@pytest.mark.asyncio
async def test_handle_self_eject_passes_blocked_on_through() -> None:
    agent = BackendDeveloperAgent(
        llm=_StubLLM(_backend_blocked_response(blocked_on="custom_reason"))
    )
    outputs = await agent.handle(_task_assignment())

    report = outputs[0]
    assert isinstance(report.payload, TaskReportPayload)
    assert report.payload.status == TaskStatus.BLOCKED
    assert report.payload.blocked_on == "custom_reason"


@pytest.mark.asyncio
async def test_handle_legacy_tests_passed_path_still_works() -> None:
    """Backward compat: LLM that returns the old schema (no `status`
    field) is mapped to DONE/FAILED via `tests_passed` as before."""
    agent = BackendDeveloperAgent(llm=_StubLLM(_backend_response()))
    outputs = await agent.handle(_task_assignment())

    report = outputs[0]
    assert isinstance(report.payload, TaskReportPayload)
    assert report.payload.status == TaskStatus.DONE


def test_backend_prompt_teaches_scope_preflight() -> None:
    prompt_path = _REPO_ROOT_FOR_PROMPT / "prompts" / "backend_developer.md"
    text = prompt_path.read_text()
    assert "Scope pre-flight" in text
    assert "task_too_large" in text
    # Allow ASCII or unicode comparator in the LOC threshold:
    assert "200 LOC" in text
    # File count threshold (any phrasing):
    assert (
        ">2 files" in text
        or "> 2 files" in text
        or "more than 2 files" in text.lower()
        or "2 files" in text
    )


def test_backend_schema_blocked_on_permissive_string_or_null() -> None:
    """iter-23: BACKEND_REPORT_SCHEMA's blocked_on is `string | null`.

    Originally (iter-23 hot-fix attempt #1) constrained to an enum,
    but demo run #2 showed Backend's claude -p subprocess exhausting
    its $2.50 budget cap on what looked like a --json-schema retry
    loop. Reverted to permissive type; the routing defense lives in
    TL's substring matcher + the Backend prompt's literal-token
    instruction.
    """
    from agents.backend_developer.agent import BACKEND_REPORT_SCHEMA

    props = BACKEND_REPORT_SCHEMA["properties"]
    assert isinstance(props, dict)
    blocked_on_prop = props["blocked_on"]
    assert isinstance(blocked_on_prop, dict)
    assert blocked_on_prop.get("type") == ["string", "null"]
    # No enum: enum constraint suspected of causing budget burns in
    # iter-23 demo run #2 (correlation c941d96a-b9ee-4575-aeb6-812f297dd8e8).
    assert "enum" not in blocked_on_prop


def test_backend_prompt_handles_missing_target_dir() -> None:
    """iter-24: Backend prompt instructs the LLM that a missing target
    directory is NORMAL for first tasks and should be created via
    write_file_in_scope, NOT treated as a scope-too-large self-eject.

    iter-23 demo run #1 caught the LLM self-ejecting because
    `examples/` was untracked in the orchestrator and absent from
    main. That was incorrect — Backend is the agent that fills the
    scaffold. This pin prevents future prompt edits from quietly
    dropping the guidance.
    """
    prompt_path = _REPO_ROOT_FOR_PROMPT / "prompts" / "backend_developer.md"
    text = prompt_path.read_text().lower()
    # Some phrasing that conveys "missing target dir is normal, do
    # not self-eject for that reason; create it".
    assert "target directory" in text or "target dir" in text
    assert any(
        marker in text
        for marker in [
            "normal for a first task",
            "missing scaffold",
            "do not self-eject just because the target directory is empty",
        ]
    )


def test_backend_prompt_mandates_literal_blocked_on_token() -> None:
    """iter-23: the prompt must instruct the LLM to use the literal
    `task_too_large` string for the blocked_on field — no
    paraphrasing, no description. Demo run #1 LLM produced
    "tests can't be collected... exceeding the 2-file scope limit"
    which TL ignored. Pin the literal-token instruction so future
    prompt edits don't quietly drop it."""
    prompt_path = _REPO_ROOT_FOR_PROMPT / "prompts" / "backend_developer.md"
    text = prompt_path.read_text().lower()
    # Some phrasing that conveys "use the literal canonical token".
    assert any(
        marker in text
        for marker in [
            "must be the literal",
            'literal string `"task_too_large"`',
            "no elaboration",
        ]
    ), "Backend prompt must mandate literal task_too_large for blocked_on"
