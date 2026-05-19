"""Market Researcher agent. Sonnet-tier. Writes market scans.

Per ADR-001, ADR-004 (path scope: docs/sandbox/ideas/ + docs/market/;
`WebFetch` is on the allowlist — the only agent that gets it this
iteration), ADR-006 (Sonnet).
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

if TYPE_CHECKING:
    from core.llm.base import LLMResponse

_log = structlog.get_logger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[2]
# Default destination; the agent picks `docs/sandbox/ideas/` for
# product ideas, `docs/market/` for sector scans (decided by the LLM
# via a `destination` field — kept simple for iter-2b).
_IDEAS_DIR: Path = _REPO_ROOT / "docs" / "sandbox" / "ideas"

_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


MARKET_SCAN_SCHEMA: dict[str, object] = {
    "type": "object",
    "required": [
        "title",
        "slug",
        "summary",
        "competitors",
        "market_size",
        "top_risks",
        "top_opportunities",
        "viability_score",
        "score_rationale",
    ],
    "additionalProperties": False,
    "properties": {
        "title": {"type": "string", "minLength": 1, "maxLength": 200},
        "slug": {"type": "string", "pattern": "^[a-z0-9]+(-[a-z0-9]+)*$"},
        "summary": {"type": "string", "minLength": 1, "maxLength": 2_000},
        "competitors": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["name", "positioning"],
                "additionalProperties": False,
                "properties": {
                    "name": {"type": "string"},
                    "url": {"type": "string"},
                    "positioning": {"type": "string"},
                },
            },
        },
        "market_size": {"type": "string"},
        "top_risks": {"type": "array", "items": {"type": "string"}},
        "top_opportunities": {"type": "array", "items": {"type": "string"}},
        "viability_score": {"type": "integer", "minimum": 1, "maximum": 10},
        "score_rationale": {"type": "string"},
    },
}


def _render_scan_markdown(scan: dict[str, Any]) -> str:
    lines: list[str] = [
        f"# Market scan — {scan['title']}",
        "",
        "- **Status**: Draft (Market Researcher agent; pending owner approval)",
        f"- **Viability score**: {scan.get('viability_score', '?')}/10",
        "",
        "## Summary",
        "",
        str(scan.get("summary", "")).strip(),
        "",
        "## Competitors",
        "",
    ]
    for c in scan.get("competitors", []):
        url = f" ({c.get('url')})" if c.get("url") else ""
        lines.append(f"- **{c.get('name', '?')}**{url}: {c.get('positioning', '?')}")
    lines.append("")
    lines.append("## Market size")
    lines.append("")
    lines.append(str(scan.get("market_size", "")).strip())
    lines.append("")
    lines.append("## Top risks")
    lines.append("")
    for r in scan.get("top_risks", []):
        lines.append(f"- {r}")
    lines.append("")
    lines.append("## Top opportunities")
    lines.append("")
    for o in scan.get("top_opportunities", []):
        lines.append(f"- {o}")
    lines.append("")
    lines.append("## Score rationale")
    lines.append("")
    lines.append(str(scan.get("score_rationale", "")).strip())
    lines.append("")
    return "\n".join(lines)


class MarketResearcherAgent(BaseAgent):
    role: ClassVar[AgentId] = AgentId.MARKET_RESEARCHER
    model_tier: ClassVar = "sonnet"
    allowed_tools: ClassVar[tuple[str, ...]] = (
        "Read",
        "Glob",
        "Grep",
        "WebFetch",
        "mcp__ai_team_repo__write_file_in_scope",
        "mcp__ai_team_bus__publish_message",
        "mcp__ai_team_bus__read_team_feed",
        "mcp__ai_team_tasks__mark_task_done",
        "mcp__ai_team_tasks__request_human_review",
    )
    system_prompt_path: ClassVar[Path] = _REPO_ROOT / "prompts" / "market_researcher.md"
    # Per ADR-004: writes only to ideas/ and market/.
    mcp_env: ClassVar[dict[str, str]] = {
        "AI_TEAM_PATH_PREFIXES": "docs/sandbox/ideas,docs/market",
    }
    llm_timeout_s: ClassVar[int] = 300
    max_turns: ClassVar[int] = 15

    def build_outputs(self, response: LLMResponse, incoming: AgentMessage) -> list[AgentMessage]:
        if not isinstance(incoming.payload, TaskAssignmentPayload):
            return []

        scan = response.structured
        if not scan or "title" not in scan or "slug" not in scan:
            return [self._fail(incoming, "LLM did not return a parseable market scan")]

        slug = str(scan["slug"])
        if not _SLUG_RE.match(slug):
            return [self._fail(incoming, f"invalid slug {slug!r}")]

        filename = f"{slug}.md"
        try:
            _IDEAS_DIR.mkdir(parents=True, exist_ok=True)
            (_IDEAS_DIR / filename).write_text(_render_scan_markdown(scan))
        except OSError as e:
            return [self._fail(incoming, f"failed to write market scan: {e}")]

        artifact_rel = f"docs/sandbox/ideas/{filename}"
        score = scan.get("viability_score", "?")
        summary = f"{scan['title']} — viability {score}/10"
        assert isinstance(incoming.payload, TaskAssignmentPayload)
        return [
            AgentMessage(
                correlation_id=incoming.correlation_id,
                sender=AgentId.MARKET_RESEARCHER,
                recipient=AgentId.TEAM_LEAD,
                message_type=MessageType.TASK_REPORT,
                priority=incoming.priority,
                payload=TaskReportPayload(
                    task_id=incoming.payload.task_id,
                    status=TaskStatus.DONE,
                    progress_pct=100,
                    summary=summary,
                    artifacts=[artifact_rel],
                ),
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
            json_schema=MARKET_SCAN_SCHEMA,
            env=dict(self.mcp_env) if self.mcp_env else None,
        )
        return self._stamp_metrics(self.build_outputs(response, msg), response)

    def _fail(self, incoming: AgentMessage, reason: str) -> AgentMessage:
        assert isinstance(incoming.payload, TaskAssignmentPayload)
        return AgentMessage(
            correlation_id=incoming.correlation_id,
            sender=AgentId.MARKET_RESEARCHER,
            recipient=AgentId.TEAM_LEAD,
            message_type=MessageType.TASK_REPORT,
            priority=incoming.priority,
            payload=TaskReportPayload(
                task_id=incoming.payload.task_id,
                status=TaskStatus.FAILED,
                progress_pct=0,
                summary=f"Market Researcher could not write scan: {reason}",
            ),
        )
