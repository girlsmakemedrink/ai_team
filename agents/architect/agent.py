"""Architect agent. Opus-tier. Emits ADR markdown to docs/adr/.

See ADR-001 (orchestrator), ADR-006 (Opus only for TL/Architect),
ADR-004 (path-scope: docs/adr/ only — agent route uses MCP
write_file_in_scope, never raw Write).

Architect's role is advisory: it writes an ADR as a side-artefact,
Backend reads it via Read, but TL is still the only gating router.
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
# Mutable module-level so tests can monkeypatch it without subclassing.
_ADR_DIR: Path = _REPO_ROOT / "docs" / "adr"

_ADR_FILENAME_RE = re.compile(r"^(\d{4})-.*\.md$")
_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


ADR_SCHEMA: dict[str, object] = {
    "type": "object",
    "required": [
        "title",
        "slug",
        "context",
        "decision",
        "consequences",
        "alternatives",
        "references",
    ],
    "additionalProperties": False,
    "properties": {
        "title": {"type": "string", "minLength": 1, "maxLength": 200},
        "slug": {"type": "string", "pattern": "^[a-z0-9]+(-[a-z0-9]+)*$"},
        "context": {"type": "string", "minLength": 1, "maxLength": 10_000},
        "decision": {"type": "string", "minLength": 1, "maxLength": 10_000},
        "consequences": {
            "type": "object",
            "required": ["positive", "negative", "neutral"],
            "additionalProperties": False,
            "properties": {
                "positive": {"type": "array", "items": {"type": "string"}},
                "negative": {"type": "array", "items": {"type": "string"}},
                "neutral": {"type": "array", "items": {"type": "string"}},
            },
        },
        "alternatives": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["name", "reason_rejected"],
                "additionalProperties": False,
                "properties": {
                    "name": {"type": "string", "minLength": 1},
                    "reason_rejected": {"type": "string", "minLength": 1},
                },
            },
        },
        "references": {"type": "array", "items": {"type": "string"}},
    },
}


def _next_adr_number(adr_dir: Path) -> int:
    """Return max(existing NNNN) + 1, or 1 if no existing ADRs."""
    if not adr_dir.is_dir():
        return 1
    nums: list[int] = []
    for entry in adr_dir.iterdir():
        m = _ADR_FILENAME_RE.match(entry.name)
        if m:
            nums.append(int(m.group(1)))
    return (max(nums) + 1) if nums else 1


def _render_adr_markdown(
    *,
    number: int,
    title: str,
    slug: str,
    context: str,
    decision: str,
    consequences: dict[str, list[str]],
    alternatives: list[dict[str, str]],
    references: list[str],
) -> str:
    lines: list[str] = [
        f"# ADR-{number:04d} — {title}",
        "",
        "- **Status**: Draft (Architect agent; pending owner approval)",
        "",
        "## Context",
        "",
        context.strip(),
        "",
        "## Decision",
        "",
        decision.strip(),
        "",
        "## Consequences",
        "",
        "### Positive",
        "",
    ]
    lines.extend(f"- {item}" for item in consequences.get("positive", []))
    lines.append("")
    lines.append("### Negative")
    lines.append("")
    lines.extend(f"- {item}" for item in consequences.get("negative", []))
    lines.append("")
    lines.append("### Neutral")
    lines.append("")
    lines.extend(f"- {item}" for item in consequences.get("neutral", []))
    lines.append("")
    lines.append("## Alternatives considered")
    lines.append("")
    for alt in alternatives:
        lines.append(f"### {alt.get('name', '?')}")
        lines.append("")
        lines.append(alt.get("reason_rejected", "").strip())
        lines.append("")
    lines.append("## References")
    lines.append("")
    for ref in references:
        lines.append(f"- {ref}")
    lines.append("")
    return "\n".join(lines)


class ArchitectAgent(BaseAgent):
    role: ClassVar[AgentId] = AgentId.ARCHITECT
    model_tier: ClassVar = "opus"
    # Inherits BaseAgent's iter-11 default of 600 s. iter-7: ADR +
    # system-design drafts reliably take 2-5 min on Opus.
    # Per ADR-004: writes only via MCP wrapper, no raw Write/Edit/Bash.
    # Read/Glob/Grep stay so Architect can survey the codebase before deciding.
    # WebFetch stays for citing external docs.
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
    system_prompt_path: ClassVar[Path] = _REPO_ROOT / "prompts" / "architect.md"
    # Per ADR-004 path-scope row.
    mcp_env: ClassVar[dict[str, str]] = {
        "AI_TEAM_PATH_PREFIXES": "docs/adr,docs/architecture.md",
    }

    def build_outputs(self, response: LLMResponse, incoming: AgentMessage) -> list[AgentMessage]:
        if not isinstance(incoming.payload, TaskAssignmentPayload):
            return []

        adr = response.structured
        if not adr or "title" not in adr or "slug" not in adr:
            return [self._fail_report(incoming, "LLM did not return a parseable ADR")]

        slug = str(adr["slug"])
        if not _SLUG_RE.match(slug):
            return [self._fail_report(incoming, f"invalid slug {slug!r}")]

        number = _next_adr_number(_ADR_DIR)
        filename = f"{number:04d}-{slug}.md"
        try:
            _ADR_DIR.mkdir(parents=True, exist_ok=True)
            markdown = _render_adr_markdown(
                number=number,
                title=str(adr["title"]),
                slug=slug,
                context=str(adr.get("context", "")),
                decision=str(adr.get("decision", "")),
                consequences=_clean_consequences(adr.get("consequences", {})),
                alternatives=_clean_alternatives(adr.get("alternatives", [])),
                references=[str(r) for r in adr.get("references", [])],
            )
            (_ADR_DIR / filename).write_text(markdown)
        except OSError as e:
            return [self._fail_report(incoming, f"failed to write ADR: {e}")]

        artifact_rel = f"docs/adr/{filename}"
        return [
            AgentMessage(
                correlation_id=incoming.correlation_id,
                sender=AgentId.ARCHITECT,
                recipient=AgentId.TEAM_LEAD,
                message_type=MessageType.TASK_REPORT,
                priority=incoming.priority,
                payload=TaskReportPayload(
                    task_id=incoming.payload.task_id,
                    status=TaskStatus.DONE,
                    progress_pct=100,
                    summary=f"ADR-{number:04d} — {adr['title']}",
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
            json_schema=ADR_SCHEMA,
            env=dict(self.mcp_env) if self.mcp_env else None,
        )
        return self._stamp_metrics(self.build_outputs(response, msg), response)

    def _fail_report(self, incoming: AgentMessage, reason: str) -> AgentMessage:
        assert isinstance(incoming.payload, TaskAssignmentPayload)
        return AgentMessage(
            correlation_id=incoming.correlation_id,
            sender=AgentId.ARCHITECT,
            recipient=AgentId.TEAM_LEAD,
            message_type=MessageType.TASK_REPORT,
            priority=incoming.priority,
            payload=TaskReportPayload(
                task_id=incoming.payload.task_id,
                status=TaskStatus.FAILED,
                progress_pct=0,
                summary=f"Architect could not write ADR: {reason}",
            ),
        )


def _clean_consequences(raw: Any) -> dict[str, list[str]]:
    if not isinstance(raw, dict):
        return {"positive": [], "negative": [], "neutral": []}
    return {
        key: [str(item) for item in (raw.get(key) or [])]
        for key in ("positive", "negative", "neutral")
    }


def _clean_alternatives(raw: Any) -> list[dict[str, str]]:
    if not isinstance(raw, list):
        return []
    out: list[dict[str, str]] = []
    for item in raw:
        if isinstance(item, dict) and "name" in item and "reason_rejected" in item:
            out.append(
                {
                    "name": str(item["name"]),
                    "reason_rejected": str(item["reason_rejected"]),
                }
            )
    return out
