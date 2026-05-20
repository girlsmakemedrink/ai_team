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
    # Multi-step workflow (read spec → write code → run tests → PR) needs
    # a longer leash than the default; bump to give 6+ minutes per turn.
    llm_timeout_s: ClassVar[int] = 600
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
            ),
        )
