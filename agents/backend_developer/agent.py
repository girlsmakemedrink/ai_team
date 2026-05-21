"""Backend Developer agent. Sonnet-tier. Code + tests + PR.

Per ADR-001 (custom orchestrator), ADR-004 (no raw Bash; everything via
mcp__ai_team_repo__*), ADR-006 (Sonnet for default agents), ADR-009
(target-repo abstraction).

The Python class is thin: it invokes claude -p once per task_assignment
with the right system prompt, allowed_tools, and a JSON schema for the
final task_report. The actual code-writing / test-running / branch /
commit / push / PR-open all happen inside the LLM turn via the MCP
tools listed in `allowed_tools`. `build_outputs` unpacks the structured
response into an AgentMessage back to the Team Lead.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

import structlog

from agents._base import BaseAgent
from core.messaging.schemas import (
    AgentId,
    AgentMessage,
    MessageType,
    TaskAssignmentPayload,
    TaskReportPayload,
    TaskStatus,
)

if TYPE_CHECKING:
    from core.llm.base import LLMResponse

_log = structlog.get_logger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[2]


# iter-21: runtime tripwire. The TL prompt edit shipped in iter-20 makes TL
# emit smaller Backend subtasks structurally (audit rows 305+306 in the
# iter-20 demo), but LLM compliance on the soft "≤200 LOC" instruction is
# imperfect — 1 of 2 subtasks still hit the 600s timeout. The pre-flight
# check below catches obviously-too-large work BEFORE burning the LLM
# turn (~$0.50 + 10 min saved per failure). TL's iter-21 re-decomposition
# handler routes the resulting BLOCKED(task_too_large) back through a
# self-targeted decomposition. See docs/iterations/iter_20_demo_report.md
# §Caveat A and docs/iterations/iter_21.md Phase 1.
_MAX_DESCRIPTION_CHARS = 1500
_MAX_UNKNOWN_FILE_PATHS = 3
_FILE_PATH_RE = re.compile(r"[A-Za-z][A-Za-z0-9_/.-]+\.[a-z]+")
_AUTO_ROUTED_HINT = "[auto-routed"


def _is_task_too_large(description: str, target_repo_root: Path) -> tuple[bool, str]:
    """Pre-flight heuristic for the Backend tripwire.

    Returns (True, diagnostic) when the description plausibly exceeds
    ~200 LOC scope, (False, "") otherwise. Heuristics OR-combined:

    - Description char count > 1500.
    - >= 3 distinct file-path-shaped tokens that don't already exist on
      disk under `target_repo_root`.

    Thresholds are deliberately conservative — false negatives fall back
    to the existing 600s timeout (iter-20 baseline). False positives
    trigger TL's auto-hop re-decomposition, capped at one hop by the
    anti-loop marker.
    """
    char_count = len(description)
    if char_count > _MAX_DESCRIPTION_CHARS:
        return True, f"description {char_count} chars > {_MAX_DESCRIPTION_CHARS} threshold"
    tokens = set(_FILE_PATH_RE.findall(description))
    unknown = sorted(t for t in tokens if not (target_repo_root / t).exists())
    if len(unknown) >= _MAX_UNKNOWN_FILE_PATHS:
        sample = ", ".join(unknown[:5])
        return True, (
            f"{len(unknown)} file-path tokens not on disk "
            f"(>= {_MAX_UNKNOWN_FILE_PATHS} threshold): {sample}"
        )
    return False, ""


BACKEND_REPORT_SCHEMA: dict[str, object] = {
    "type": "object",
    "required": ["branch", "summary", "files_written", "tests_passed", "pr_url"],
    "additionalProperties": False,
    "properties": {
        "branch": {
            "type": "string",
            "pattern": r"^agent/backend_developer/[a-zA-Z0-9._\-/]+$",
        },
        "summary": {"type": "string", "minLength": 1, "maxLength": 2_000},
        "files_written": {"type": "array", "items": {"type": "string"}},
        "tests_passed": {"type": "boolean"},
        "pr_url": {"type": "string"},
    },
}


class BackendDeveloperAgent(BaseAgent):
    role: ClassVar[AgentId] = AgentId.BACKEND_DEVELOPER
    model_tier: ClassVar = "sonnet"
    # Per ADR-004 Backend row: Read/Glob/Grep for survey; NO raw
    # Bash/Write/Edit; everything else through mcp__ai_team_repo__*.
    allowed_tools: ClassVar[tuple[str, ...]] = (
        "Read",
        "Glob",
        "Grep",
        "mcp__ai_team_repo__status",
        "mcp__ai_team_repo__create_branch",
        "mcp__ai_team_repo__write_file_in_scope",
        "mcp__ai_team_repo__run_shell",
        "mcp__ai_team_repo__open_pr",
        "mcp__ai_team_bus__publish_message",
        "mcp__ai_team_bus__read_team_feed",
        "mcp__ai_team_tasks__mark_task_done",
        "mcp__ai_team_tasks__request_human_review",
    )
    # iter-11: --allowed-tools already excludes Bash, but iter-10
    # demo Backend reported "Bash hooks blocked the pytest command"
    # anyway — the LLM was perceiving Bash as available and trying it.
    # Belt-and-suspenders: name Bash in --disallowed-tools so claude -p
    # denies it explicitly before the LLM even tries. See
    # iter_10_demo_report.md Failure 1.
    disallowed_tools: ClassVar[tuple[str, ...]] = ("Bash",)
    system_prompt_path: ClassVar[Path] = _REPO_ROOT / "prompts" / "backend_developer.md"
    # Per ADR-004 path-scope row: writes anywhere in target_repo EXCEPT
    # infra/ and .github/workflows/ (DevOps territory). `*` allow plus
    # explicit denylist via scope.py's AI_TEAM_PATH_DENY_PREFIXES.
    mcp_env: ClassVar[dict[str, str]] = {
        "AI_TEAM_PATH_PREFIXES": "*",
        "AI_TEAM_PATH_DENY_PREFIXES": "infra/,.github/workflows/",
    }
    # Multi-step workflow (read spec → write code → run tests → PR)
    # inherits BaseAgent's iter-11 default of 600 s. max_turns stays
    # bumped past BaseAgent's 8 because Backend's loop is long.
    max_turns: ClassVar[int] = 30

    def build_outputs(self, response: LLMResponse, incoming: AgentMessage) -> list[AgentMessage]:
        if not isinstance(incoming.payload, TaskAssignmentPayload):
            return []

        report = response.structured
        if not report or "tests_passed" not in report:
            return [
                self._report_to_tl(
                    incoming,
                    status=TaskStatus.FAILED,
                    summary="Backend Developer: LLM did not return a parseable task_report",
                    artifacts=[],
                )
            ]

        tests_passed = bool(report.get("tests_passed"))
        pr_url = str(report.get("pr_url", "")).strip()
        summary = str(report.get("summary", "")).strip()
        files_written = [str(p) for p in report.get("files_written", [])]

        if not tests_passed:
            return [
                self._report_to_tl(
                    incoming,
                    status=TaskStatus.FAILED,
                    summary=f"Backend Developer: tests failed. {summary}"[:2_000],
                    artifacts=files_written,
                )
            ]

        full_summary = f"{summary} PR: {pr_url}" if pr_url else summary
        return [
            self._report_to_tl(
                incoming,
                status=TaskStatus.DONE,
                summary=full_summary[:2_000],
                artifacts=files_written,
            )
        ]

    async def handle(self, msg: AgentMessage) -> list[AgentMessage]:
        if msg.message_type != MessageType.TASK_ASSIGNMENT:
            return []
        if not isinstance(msg.payload, TaskAssignmentPayload):
            return []
        # iter-21: tripwire short-circuit BEFORE LLM invocation. See module
        # docstring on _is_task_too_large for rationale.
        target_root = Path(os.environ.get("AI_TEAM_REPO_ROOT", str(_REPO_ROOT)))
        too_large, diag = _is_task_too_large(msg.payload.description, target_root)
        if too_large:
            already_routed = _AUTO_ROUTED_HINT in msg.payload.description.lower()
            marker = "[auto-routed already] " if already_routed else ""
            summary = (
                f"{marker}task too large: {diag}\n\n"
                f"original task description (first 800 chars):\n"
                f"{msg.payload.description[:800]}"
            )[:2_000]
            self._log.info(
                "backend.tripwire_blocked",
                diag=diag,
                char_count=len(msg.payload.description),
                already_routed=already_routed,
                correlation_id=str(msg.correlation_id),
            )
            return [
                self._report_to_tl(
                    msg,
                    status=TaskStatus.BLOCKED,
                    summary=summary,
                    artifacts=[],
                    blocked_on="task_too_large",
                )
            ]
        response = await self._llm.invoke(
            system_prompt=self.system_prompt(),
            user_message=self._user_message_for(msg),
            model=self.model_tier,
            allowed_tools=self.allowed_tools,
            session_id=str(msg.correlation_id),
            timeout_s=self.llm_timeout_s,
            max_turns=self.max_turns,
            json_schema=BACKEND_REPORT_SCHEMA,
            env=dict(self.mcp_env) if self.mcp_env else None,
        )
        return self._stamp_metrics(self.build_outputs(response, msg), response)

    def _report_to_tl(
        self,
        incoming: AgentMessage,
        *,
        status: TaskStatus,
        summary: str,
        artifacts: list[str],
        blocked_on: str | None = None,
    ) -> AgentMessage:
        assert isinstance(incoming.payload, TaskAssignmentPayload)
        return AgentMessage(
            correlation_id=incoming.correlation_id,
            sender=AgentId.BACKEND_DEVELOPER,
            recipient=AgentId.TEAM_LEAD,
            message_type=MessageType.TASK_REPORT,
            priority=incoming.priority,
            payload=TaskReportPayload(
                task_id=incoming.payload.task_id,
                status=status,
                progress_pct=100 if status == TaskStatus.DONE else 0,
                summary=summary,
                artifacts=artifacts,
                blocked_on=blocked_on,
            ),
        )
