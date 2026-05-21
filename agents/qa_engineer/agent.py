"""QA Engineer agent. Sonnet. Runs the test suite, reports back to TL.

Per ADR-001 / ADR-004 / ADR-006. Like Backend, the Python class is thin:
it sets system prompt + JSON-schema, the LLM does the actual work via
mcp__ai_team_repo__run_shell(pytest).

iter-23 Phase 2: adds a Python-side safety net for the
`request_human_review` MCP tool-call. Phase 1 evidence (0/3 runs in
tests/integration/test_qa_request_human_review_real_llm.py) showed
the LLM produces schema-valid QA JSON but does NOT invoke the tool
under --json-schema pressure. Without a backstop, the
`pending_reviews` row — the owner-approval gate — never lands, which
broke the chain in iter-19→22 (4-iter deferred criterion). Safety
net inspects `response.tools_used`; if the MCP tool name is absent,
the agent INSERTs the row directly via an injected session_factory.
Mirror of `tools/mcp_servers/ai_team_tasks/handlers.py:handle_request_human_review`
INSERT shape; deliberately a direct DB write (not an import from
tools/) to keep agents/ → tools/ layer separation clean.
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
from core.persistence.models import PendingReview

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from core.llm.base import LLMClient, LLMResponse

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


_REQUEST_HUMAN_REVIEW_TOOL = "mcp__ai_team_tasks__request_human_review"


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

    def __init__(
        self,
        *,
        llm: LLMClient,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
    ) -> None:
        # iter-23 Phase 2: session_factory plumbed by the dispatcher
        # (apps/api/main.py); None in unit-test paths that mock the LLM
        # but don't need a DB. Safety net degrades to log-and-skip when
        # absent.
        super().__init__(llm=llm)
        self._session_factory = session_factory

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
        outputs = self._stamp_metrics(self.build_outputs(response, msg), response)
        await self._ensure_pending_review_row(response, msg)
        return outputs

    async def _ensure_pending_review_row(
        self, response: LLMResponse, incoming: AgentMessage
    ) -> None:
        """Safety net: write pending_reviews row if LLM forgot to call the tool.

        Phase 1 evidence (iter-23, 0/3 runs) shows the LLM produces
        valid schema-conformant JSON but skips
        `mcp__ai_team_tasks__request_human_review` under
        `--json-schema` pressure. Without this backstop the
        owner-approval gate never opens and the QA chain doesn't close.
        """
        tool_names = {t.name for t in response.tools_used}
        if _REQUEST_HUMAN_REVIEW_TOOL in tool_names:
            return

        report = response.structured or {}
        summary = str(report.get("summary") or "QA verdict (Python safety net)").strip()
        if not summary:
            summary = "QA verdict (Python safety net)"

        if self._session_factory is None:
            _log.warning(
                "qa.safety_net.no_session_factory",
                correlation_id=str(incoming.correlation_id),
                summary_preview=summary[:80],
            )
            return

        assert isinstance(incoming.payload, TaskAssignmentPayload)
        try:
            async with self._session_factory() as session:
                review = PendingReview(
                    correlation_id=incoming.correlation_id,
                    requesting_agent="qa_engineer",
                    task_id=incoming.payload.task_id,
                    summary=summary[:2_000],
                )
                session.add(review)
                await session.commit()
            _log.warning(
                "qa.safety_net.row_inserted",
                correlation_id=str(incoming.correlation_id),
                task_id=str(incoming.payload.task_id),
                reason="llm_skipped_request_human_review_tool",
            )
        except Exception:
            # Never silently swallow; log and continue so the
            # task_report still surfaces the QA verdict.
            _log.exception(
                "qa.safety_net.insert_failed",
                correlation_id=str(incoming.correlation_id),
            )

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
