"""QA Engineer agent. Sonnet. Runs the test suite, reports back to TL.

Per ADR-001 / ADR-004 / ADR-006. Like Backend, the Python class is thin:
it sets system prompt + JSON-schema, the LLM does the actual work via
mcp__ai_team_repo__run_shell(pytest).
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


QA_REPORT_SCHEMA: dict[str, object] = {
    "type": "object",
    "required": ["suite_passed", "tests_run", "tests_failed", "failures", "summary"],
    "additionalProperties": False,
    "properties": {
        "suite_passed": {"type": "boolean"},
        "tests_run": {"type": "integer", "minimum": 0},
        "tests_failed": {"type": "integer", "minimum": 0},
        "coverage_pct": {"type": "number", "minimum": 0, "maximum": 100},
        "failures": {"type": "array", "items": {"type": "string"}},
        "summary": {"type": "string", "minLength": 1, "maxLength": 2_000},
    },
}


class QAEngineerAgent(BaseAgent):
    role: ClassVar[AgentId] = AgentId.QA_ENGINEER
    model_tier: ClassVar = "sonnet"
    allowed_tools: ClassVar[tuple[str, ...]] = (
        "Read",
        "Glob",
        "Grep",
        "mcp__ai_team_repo__status",
        "mcp__ai_team_repo__run_shell",
        "mcp__ai_team_bus__publish_message",
        "mcp__ai_team_bus__read_team_feed",
        "mcp__ai_team_tasks__mark_task_done",
        "mcp__ai_team_tasks__request_human_review",
    )
    system_prompt_path: ClassVar[Path] = _REPO_ROOT / "prompts" / "qa_engineer.md"
    # Per ADR-004: QA's only writes are to tests/ (regression cases).
    mcp_env: ClassVar[dict[str, str]] = {
        "AI_TEAM_PATH_PREFIXES": "tests/",
    }
    llm_timeout_s: ClassVar[int] = 300
    max_turns: ClassVar[int] = 15

    def build_outputs(self, response: LLMResponse, incoming: AgentMessage) -> list[AgentMessage]:
        if not isinstance(incoming.payload, TaskAssignmentPayload):
            return []

        report = response.structured
        if not report or "suite_passed" not in report:
            return [
                self._report_to_tl(
                    incoming,
                    status=TaskStatus.FAILED,
                    summary="QA Engineer: LLM did not return a parseable QA report",
                )
            ]

        suite_passed = bool(report.get("suite_passed"))
        summary = str(report.get("summary", "")).strip()
        coverage_pct = report.get("coverage_pct")
        failures = [str(f) for f in report.get("failures") or []]

        full_summary = summary
        if coverage_pct is not None and "coverage" not in full_summary.lower():
            full_summary = f"{summary} ({coverage_pct}% coverage)"
        if failures and not suite_passed:
            sample = "; ".join(failures[:3])
            full_summary = f"{full_summary}. Failed: {sample}"

        return [
            self._report_to_tl(
                incoming,
                status=TaskStatus.DONE if suite_passed else TaskStatus.FAILED,
                summary=full_summary[:2_000],
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
            json_schema=QA_REPORT_SCHEMA,
            env=dict(self.mcp_env) if self.mcp_env else None,
        )
        return self._stamp_metrics(self.build_outputs(response, msg), response)

    def _report_to_tl(
        self,
        incoming: AgentMessage,
        *,
        status: TaskStatus,
        summary: str,
    ) -> AgentMessage:
        assert isinstance(incoming.payload, TaskAssignmentPayload)
        return AgentMessage(
            correlation_id=incoming.correlation_id,
            sender=AgentId.QA_ENGINEER,
            recipient=AgentId.TEAM_LEAD,
            message_type=MessageType.TASK_REPORT,
            priority=incoming.priority,
            payload=TaskReportPayload(
                task_id=incoming.payload.task_id,
                status=status,
                progress_pct=100 if status == TaskStatus.DONE else 0,
                summary=summary,
            ),
        )
