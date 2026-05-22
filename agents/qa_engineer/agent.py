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

import re
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar

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
_RANKING_DIR: Path = _REPO_ROOT / "docs" / "products" / "_candidates"
_VALIDATE_DIR: Path = _REPO_ROOT / "docs" / "products"

_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


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


RANK_BRAINSTORM_SCHEMA: dict[str, object] = {
    "type": "object",
    "required": ["intent_completed", "ranking_summary", "top_3_overall"],
    "additionalProperties": False,
    "properties": {
        "intent_completed": {"type": "string", "enum": ["rank_brainstorm_candidates"]},
        "ranking_summary": {"type": "string", "minLength": 1, "maxLength": 2_000},
        "top_3_overall": {
            "type": "array",
            "minItems": 3,
            "maxItems": 3,
            "items": {"type": "string", "pattern": "^[a-z0-9]+(-[a-z0-9]+)*$"},
        },
    },
}


SYNTHESIZE_VALIDATION_SCHEMA: dict[str, object] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "intent_completed",
        "recommendation",
        "confidence",
        "top_risks",
        "fatal_flaws",
        "build_window",
        "next_steps",
        "summary",
        "artifacts",
    ],
    "properties": {
        "intent_completed": {"const": "synthesize_validation"},
        "recommendation": {"enum": ["go", "go_with_caveats", "pivot", "kill"]},
        "confidence": {"type": "integer", "minimum": 0, "maximum": 5},
        "top_risks": {
            "type": "array",
            "minItems": 0,
            "maxItems": 5,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["name", "severity", "mitigation"],
                "properties": {
                    "name": {"type": "string", "maxLength": 200},
                    "severity": {"type": "integer", "minimum": 1, "maximum": 5},
                    "mitigation": {"type": "string", "maxLength": 500},
                },
            },
        },
        "fatal_flaws": {
            "type": "array",
            "items": {"type": "string", "maxLength": 500},
            "default": [],
        },
        "build_window": {
            "enum": ["4-6 weeks", "6-8 weeks", "8-12 weeks", "12+ weeks", "unknown"],
        },
        "next_steps": {
            "type": "array",
            "minItems": 1,
            "maxItems": 7,
            "items": {"type": "string", "maxLength": 300},
        },
        "summary": {"type": "string", "maxLength": 2000},
        "artifacts": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 1,
        },
    },
}


def _coerce_recommendation_for_fatal_flaws(response: dict[str, Any]) -> dict[str, Any]:
    """Cross-field invariant enforcement: fatal_flaws non-empty implies
    recommendation in {"kill", "pivot"}. JSON Schema can't express the
    conditional; if the LLM violated it, override to "kill" and record
    the original in a metadata field for the audit trail.
    """
    fatal = response.get("fatal_flaws") or []
    rec = response.get("recommendation")
    if fatal and rec not in {"kill", "pivot"}:
        coerced = dict(response)
        coerced["recommendation"] = "kill"
        coerced["_coerced_from"] = rec
        return coerced
    return response


def _escape_pipes(s: str) -> str:
    """Escape `|` in GFM table cells."""
    return s.replace("|", "\\|")


def _render_validation_summary_markdown(response: dict[str, Any], slug: str) -> str:
    """Render SYNTHESIZE_VALIDATION_SCHEMA output as _validation_summary.md
    with a top-of-file YAML block followed by prose sections.
    """
    lines: list[str] = []
    lines.append("---")
    lines.append(f"slug: {slug}")
    lines.append(f"recommendation: {response['recommendation']}")
    lines.append(f"confidence: {response['confidence']}")
    lines.append(f"build_window: {response['build_window']}")
    lines.append(f"fatal_flaws_count: {len(response.get('fatal_flaws') or [])}")
    if "_coerced_from" in response:
        lines.append(f"recommendation_coerced_from: {response['_coerced_from']}")
    lines.append("---")
    lines.append("")
    lines.append(f"# Validation summary: {slug}\n")
    lines.append("## Recommendation\n")
    lines.append(f"**{response['recommendation']}** (confidence {response['confidence']}/5)\n")
    lines.append("## Summary\n")
    lines.append(response["summary"])
    lines.append("")

    fatal = response.get("fatal_flaws") or []
    if fatal:
        lines.append("## Fatal flaws\n")
        for item in fatal:
            lines.append(f"- {item}")
        lines.append("")

    risks = response.get("top_risks") or []
    if risks:
        lines.append("## Risk register\n")
        lines.append("| # | Risk | Severity (1-5) | Mitigation |")
        lines.append("|---|---|---|---|")
        for i, r in enumerate(risks, 1):
            lines.append(
                f"| {i} | {_escape_pipes(r['name'])} | {r['severity']}"
                f" | {_escape_pipes(r['mitigation'])} |"
            )
        lines.append("")

    lines.append("## Next steps\n")
    for step in response["next_steps"]:
        lines.append(f"- {step}")
    lines.append("")
    return "\n".join(lines)


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
    # Per ADR-004: QA writes to tests/ (regression cases) and
    # docs/products/_candidates (combined ranking from rank_brainstorm intent).
    mcp_env: ClassVar[dict[str, str]] = {
        "AI_TEAM_PATH_PREFIXES": "tests/,docs/products/_candidates",
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
        intent = (incoming.payload.inputs or {}).get("intent")
        if intent == "synthesize_validation":
            return self._build_synthesize_validation_outputs(response, incoming)
        if intent == "rank_brainstorm_candidates":
            return self._build_rank_outputs(response, incoming)
        return self._build_qa_report_outputs(response, incoming)

    def _build_qa_report_outputs(
        self, response: LLMResponse, incoming: AgentMessage
    ) -> list[AgentMessage]:
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

    def _build_rank_outputs(
        self, response: LLMResponse, incoming: AgentMessage
    ) -> list[AgentMessage]:
        assert isinstance(incoming.payload, TaskAssignmentPayload)
        rank = response.structured or {}
        if rank.get("intent_completed") != "rank_brainstorm_candidates":
            return [
                self._report_to_tl(
                    incoming,
                    status=TaskStatus.FAILED,
                    summary="QA: rank response missing intent_completed field",
                )
            ]

        # Resolve artifacts: explicit list OR glob fallback.
        explicit = (incoming.payload.inputs or {}).get("brainstorm_artifacts") or []
        if explicit:
            artifact_paths = [str(p) for p in explicit]
        else:
            artifact_paths = [
                str(p.relative_to(_REPO_ROOT))
                for p in sorted(_RANKING_DIR.glob("_brainstorm_*.md"))
            ]

        top_3 = rank.get("top_3_overall", [])
        summary_text = rank.get("ranking_summary", "")

        try:
            _RANKING_DIR.mkdir(parents=True, exist_ok=True)
            ranking_md = self._render_combined_ranking(artifact_paths, top_3, summary_text)
            (_RANKING_DIR / "_combined_ranking.md").write_text(ranking_md)
        except OSError as e:
            return [
                self._report_to_tl(
                    incoming,
                    status=TaskStatus.FAILED,
                    summary=f"QA: failed to write combined ranking: {e}",
                )
            ]

        return [
            self._report_to_tl(
                incoming,
                status=TaskStatus.DONE,
                summary=f"Ranking complete. Top-3: {', '.join(top_3)}. {summary_text}"[:2_000],
            )
        ]

    def _render_combined_ranking(
        self,
        artifact_paths: list[str],
        top_3: list[str],
        summary: str,
    ) -> str:
        lines: list[str] = [
            "# Combined brainstorm ranking",
            "",
            "- **Status**: Draft (QA-merged; pending owner review)",
            f"- **Source artifacts**: {len(artifact_paths)}",
            "",
            "## Overall top-3 (QA selection)",
            "",
        ]
        for slug in top_3:
            lines.append(f"- `{slug}`")
        lines.append("")
        lines.append("## Source brainstorms")
        lines.append("")
        for path in artifact_paths:
            lines.append(f"- {path}")
        lines.append("")
        lines.append("## QA notes")
        lines.append("")
        lines.append(summary.strip())
        lines.append("")
        return "\n".join(lines)

    def _build_synthesize_validation_outputs(
        self, response: LLMResponse, incoming: AgentMessage
    ) -> list[AgentMessage]:
        assert isinstance(incoming.payload, TaskAssignmentPayload)
        inputs = incoming.payload.inputs or {}
        slug = str(inputs.get("slug", ""))
        raw = response.structured or {}

        if not raw or raw.get("intent_completed") != "synthesize_validation":
            return [
                self._fail_report(
                    incoming,
                    "missing or malformed structured_output",
                    kind="validation synthesis",
                )
            ]

        coerced = _coerce_recommendation_for_fatal_flaws(raw)

        out_dir = _VALIDATE_DIR / slug
        try:
            out_dir.mkdir(parents=True, exist_ok=True)
            artifact_path = out_dir / "_validation_summary.md"
            artifact_path.write_text(_render_validation_summary_markdown(coerced, slug=slug))
        except OSError as e:
            return [
                self._fail_report(
                    incoming,
                    f"failed to write _validation_summary.md: {e}",
                    kind="validation synthesis",
                )
            ]

        artifact_rel = f"docs/products/{slug}/_validation_summary.md"
        summary_text = str(
            coerced.get("summary")
            or (
                f"{slug}: recommendation={coerced['recommendation']},"
                f" confidence={coerced['confidence']},"
                f" fatal_flaws={len(coerced.get('fatal_flaws') or [])}"
            )
        )
        return [
            AgentMessage(
                correlation_id=incoming.correlation_id,
                sender=AgentId.QA_ENGINEER,
                recipient=AgentId.TEAM_LEAD,
                message_type=MessageType.TASK_REPORT,
                priority=incoming.priority,
                payload=TaskReportPayload(
                    task_id=incoming.payload.task_id,
                    status=TaskStatus.DONE,
                    progress_pct=100,
                    summary=summary_text[:2_000],
                    artifacts=[artifact_rel],
                ),
            )
        ]

    async def handle(self, msg: AgentMessage) -> list[AgentMessage]:
        if msg.message_type != MessageType.TASK_ASSIGNMENT:
            return []
        assert isinstance(msg.payload, TaskAssignmentPayload)
        inputs = msg.payload.inputs or {}
        intent = inputs.get("intent")

        max_budget_usd: float | None = None

        if intent == "synthesize_validation":
            slug = str(inputs.get("slug", ""))
            if not _SLUG_RE.match(slug):
                return [
                    self._fail_report(
                        msg,
                        f"input_validation — invalid slug {slug!r}",
                        kind="validation synthesis",
                    )
                ]
            schema: dict[str, object] = SYNTHESIZE_VALIDATION_SCHEMA
            session_id = str(msg.payload.task_id)
            max_budget_usd = 2.50
            env: dict[str, str] = dict(self.mcp_env) or {}
            env["AI_TEAM_PATH_PREFIXES"] = (
                f"docs/sandbox/ideas,docs/market,docs/products/_candidates,docs/products/{slug}"
            )
        elif intent == "rank_brainstorm_candidates":
            schema = RANK_BRAINSTORM_SCHEMA
            session_id = str(msg.correlation_id)
            env = dict(self.mcp_env) if self.mcp_env else {}
        else:
            schema = QA_REPORT_SCHEMA
            session_id = str(msg.correlation_id)
            env = dict(self.mcp_env) if self.mcp_env else {}

        invoke_kwargs: dict[str, Any] = {
            "system_prompt": self.system_prompt(),
            "user_message": self._user_message_for(msg),
            "model": self.model_tier,
            "allowed_tools": self.allowed_tools,
            "session_id": session_id,
            "timeout_s": self.llm_timeout_s,
            "max_turns": self.max_turns,
            "json_schema": schema,
            "env": env if env else None,
        }
        if max_budget_usd is not None:
            invoke_kwargs["max_budget_usd"] = max_budget_usd

        response = await self._llm.invoke(**invoke_kwargs)
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
        # `summary` is the QA_REPORT_SCHEMA field; `ranking_summary` is the
        # RANK_BRAINSTORM_SCHEMA field. Try both before falling back to the
        # generic placeholder so the owner sees meaningful text in
        # `ai-team list-pending` for either intent.
        summary = str(
            report.get("summary")
            or report.get("ranking_summary")
            or "QA verdict (Python safety net)"
        ).strip()
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

    def _fail_report(
        self, incoming: AgentMessage, reason: str, *, kind: str = "QA report"
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
                status=TaskStatus.FAILED,
                progress_pct=0,
                summary=f"QA could not write {kind}: {reason}",
            ),
        )
