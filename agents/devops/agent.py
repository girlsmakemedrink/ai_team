"""DevOps agent. Sonnet-tier. Modifies infra/, .github/workflows/, Makefile.

Per ADR-001 / ADR-004 (path scope: infra+workflows+Makefile+compose+scripts)
/ ADR-006 (Sonnet).
"""

from __future__ import annotations

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
_BLOCKED_RE = re.compile(r"blocked:\s*requires\s+(\w+)", re.IGNORECASE)


DEVOPS_REPORT_SCHEMA: dict[str, object] = {
    "type": "object",
    "required": ["target_files", "changes", "rationale", "validation_step", "branch"],
    "additionalProperties": False,
    "properties": {
        "target_files": {"type": "array", "items": {"type": "string"}, "minItems": 1},
        "changes": {"type": "string", "minLength": 1, "maxLength": 2_000},
        "rationale": {"type": "string", "minLength": 1, "maxLength": 2_000},
        "validation_step": {"type": "string", "minLength": 1, "maxLength": 1_000},
        "pr_url": {"type": "string"},
        "branch": {
            "type": "string",
            "pattern": r"^agent/devops/[a-zA-Z0-9._\-/]+$",
        },
    },
}


class DevOpsAgent(BaseAgent):
    role: ClassVar[AgentId] = AgentId.DEVOPS
    model_tier: ClassVar = "sonnet"
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
    system_prompt_path: ClassVar[Path] = _REPO_ROOT / "prompts" / "devops.md"
    # Per ADR-004: write only to infra, CI workflows, Makefile, compose, scripts.
    mcp_env: ClassVar[dict[str, str]] = {
        "AI_TEAM_PATH_PREFIXES": ("infra,.github/workflows,Makefile,docker-compose.yml,scripts"),
    }
    llm_timeout_s: ClassVar[int] = 600
    max_turns: ClassVar[int] = 20

    def build_outputs(self, response: LLMResponse, incoming: AgentMessage) -> list[AgentMessage]:
        if not isinstance(incoming.payload, TaskAssignmentPayload):
            return []

        report = response.structured
        if not report or "changes" not in report:
            return [
                self._report(
                    incoming, TaskStatus.FAILED, "DevOps: LLM did not return a parseable report", []
                )
            ]

        target_files = [str(p) for p in report.get("target_files", [])]
        changes = str(report.get("changes", "")).strip()
        validation = str(report.get("validation_step", "")).strip()
        pr_url = str(report.get("pr_url", "")).strip()

        # "blocked: requires Backend" or "blocked: ..." → escalate to TL.
        # Populate blocked_on so TL can auto-route without re-parsing summary.
        if validation.lower().startswith("blocked"):
            return [
                self._report(
                    incoming,
                    TaskStatus.BLOCKED,
                    f"DevOps blocked: {validation}",
                    target_files,
                    blocked_on=_parse_blocked_role(validation),
                )
            ]

        summary_bits: list[str] = [changes]
        if validation:
            summary_bits.append(f"Validation: {validation}")
        if pr_url:
            summary_bits.append(f"PR: {pr_url}")
        full_summary = " ".join(summary_bits)[:2_000]

        return [self._report(incoming, TaskStatus.DONE, full_summary, target_files)]

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
            json_schema=DEVOPS_REPORT_SCHEMA,
            env=dict(self.mcp_env) if self.mcp_env else None,
        )
        return self._stamp_metrics(self.build_outputs(response, msg), response)

    def _report(
        self,
        incoming: AgentMessage,
        status: TaskStatus,
        summary: str,
        artifacts: list[str],
        *,
        blocked_on: str | None = None,
    ) -> AgentMessage:
        assert isinstance(incoming.payload, TaskAssignmentPayload)
        return AgentMessage(
            correlation_id=incoming.correlation_id,
            sender=AgentId.DEVOPS,
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


def _parse_blocked_role(validation: str) -> str | None:
    """Extract the role from `blocked: requires <role>` if it resolves
    to a known AgentId, else None."""
    m = _BLOCKED_RE.search(validation)
    if not m:
        return None
    try:
        return AgentId(m.group(1).lower()).value
    except ValueError:
        return None
