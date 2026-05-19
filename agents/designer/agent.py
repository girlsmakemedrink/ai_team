"""Designer agent. Sonnet-tier. Emits design notes to docs/design/.

See ADR-001, ADR-004 (path scope: docs/design/ + prompts/designer.md),
ADR-006 (Sonnet for default agents).
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
# Mutable so tests can monkeypatch.
_DESIGN_DIR: Path = _REPO_ROOT / "docs" / "design"

_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


DESIGN_NOTE_SCHEMA: dict[str, object] = {
    "type": "object",
    "required": ["title", "slug", "summary", "layout", "decisions", "links"],
    "additionalProperties": False,
    "properties": {
        "title": {"type": "string", "minLength": 1, "maxLength": 200},
        "slug": {"type": "string", "pattern": "^[a-z0-9]+(-[a-z0-9]+)*$"},
        "summary": {"type": "string", "minLength": 1, "maxLength": 2_000},
        "layout": {"type": "string", "minLength": 1, "maxLength": 10_000},
        "decisions": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["name", "choice", "rationale"],
                "additionalProperties": False,
                "properties": {
                    "name": {"type": "string", "minLength": 1},
                    "choice": {"type": "string", "minLength": 1},
                    "rationale": {"type": "string", "minLength": 1},
                },
            },
        },
        "links": {"type": "array", "items": {"type": "string"}},
    },
}


def _render_design_markdown(*, design: dict[str, Any]) -> str:
    lines: list[str] = [
        f"# Design — {design['title']}",
        "",
        "- **Status**: Draft (Designer agent; pending owner approval)",
        "",
        "## Summary",
        "",
        str(design.get("summary", "")).strip(),
        "",
        "## Layout",
        "",
        "```",
        str(design.get("layout", "")).rstrip(),
        "```",
        "",
        "## Decisions",
        "",
    ]
    for d in design.get("decisions", []):
        lines.append(f"### {d.get('name', '?')}")
        lines.append("")
        lines.append(f"**Choice**: {d.get('choice', '?')}")
        lines.append("")
        lines.append(d.get("rationale", "").strip())
        lines.append("")
    lines.append("## References")
    lines.append("")
    for link in design.get("links", []):
        lines.append(f"- {link}")
    lines.append("")
    return "\n".join(lines)


class DesignerAgent(BaseAgent):
    role: ClassVar[AgentId] = AgentId.DESIGNER
    model_tier: ClassVar = "sonnet"
    # iter-8: UX brief + wireframe drafting on the v2 task reliably
    # takes 3-5 min on Sonnet; the 300 s BaseAgent default timed out
    # in the iter-7 demo. Match Architect / Backend / Frontend /
    # DevOps's 600 s.
    llm_timeout_s: ClassVar[int] = 600
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
    system_prompt_path: ClassVar[Path] = _REPO_ROOT / "prompts" / "designer.md"
    # Per ADR-004: writes only under docs/design/.
    mcp_env: ClassVar[dict[str, str]] = {
        "AI_TEAM_PATH_PREFIXES": "docs/design",
    }

    def build_outputs(self, response: LLMResponse, incoming: AgentMessage) -> list[AgentMessage]:
        if not isinstance(incoming.payload, TaskAssignmentPayload):
            return []

        design = response.structured
        if not design or "title" not in design or "slug" not in design:
            return [self._fail_report(incoming, "LLM did not return a parseable design note")]

        slug = str(design["slug"])
        if not _SLUG_RE.match(slug):
            return [self._fail_report(incoming, f"invalid slug {slug!r}")]

        filename = f"{slug}.md"
        try:
            _DESIGN_DIR.mkdir(parents=True, exist_ok=True)
            markdown = _render_design_markdown(design=design)
            (_DESIGN_DIR / filename).write_text(markdown)
        except OSError as e:
            return [self._fail_report(incoming, f"failed to write design: {e}")]

        artifact_rel = f"docs/design/{filename}"
        return [
            AgentMessage(
                correlation_id=incoming.correlation_id,
                sender=AgentId.DESIGNER,
                recipient=AgentId.TEAM_LEAD,
                message_type=MessageType.TASK_REPORT,
                priority=incoming.priority,
                payload=TaskReportPayload(
                    task_id=incoming.payload.task_id,
                    status=TaskStatus.DONE,
                    progress_pct=100,
                    summary=f"Design — {design['title']}",
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
            json_schema=DESIGN_NOTE_SCHEMA,
            env=dict(self.mcp_env) if self.mcp_env else None,
        )
        return self._stamp_metrics(self.build_outputs(response, msg), response)

    def _fail_report(self, incoming: AgentMessage, reason: str) -> AgentMessage:
        assert isinstance(incoming.payload, TaskAssignmentPayload)
        return AgentMessage(
            correlation_id=incoming.correlation_id,
            sender=AgentId.DESIGNER,
            recipient=AgentId.TEAM_LEAD,
            message_type=MessageType.TASK_REPORT,
            priority=incoming.priority,
            payload=TaskReportPayload(
                task_id=incoming.payload.task_id,
                status=TaskStatus.FAILED,
                progress_pct=0,
                summary=f"Designer could not write design: {reason}",
            ),
        )
