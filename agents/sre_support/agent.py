"""SRE / Support agent. Sonnet-tier. Writes runbooks + monitoring config.

Per ADR-001 / ADR-004 (path scope: docs/runbooks/ + infra/monitoring/) /
ADR-006 (Sonnet).

Iter-2c ships read tools + WebFetch + path-scoped write only. Shell
(curl / promtool / journalctl) is deferred to iter-5 when the server
environment those would run against exists.
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
_RUNBOOK_DIR: Path = _REPO_ROOT / "docs" / "runbooks"
_MONITORING_DIR: Path = _REPO_ROOT / "infra" / "monitoring"

_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_RUNBOOK_KINDS = ("runbook", "alert", "dashboard")


SRE_REPORT_SCHEMA: dict[str, object] = {
    "type": "object",
    "required": ["title", "slug", "kind", "summary", "steps", "severity"],
    "additionalProperties": False,
    "properties": {
        "title": {"type": "string", "minLength": 1, "maxLength": 200},
        "slug": {"type": "string", "pattern": "^[a-z0-9]+(-[a-z0-9]+)*$"},
        "kind": {"type": "string", "enum": list(_RUNBOOK_KINDS)},
        "summary": {"type": "string", "minLength": 1, "maxLength": 2_000},
        "steps": {"type": "string", "minLength": 1, "maxLength": 10_000},
        "metrics": {"type": "array", "items": {"type": "string"}},
        "severity": {"type": "string", "enum": ["P1", "P2", "P3", "P4"]},
    },
}


def _render_runbook_markdown(*, doc: dict[str, Any]) -> str:
    title = str(doc.get("title", "")).strip()
    kind = str(doc.get("kind", "runbook")).strip()
    severity = str(doc.get("severity", "P3")).strip()
    summary = str(doc.get("summary", "")).strip()
    steps = str(doc.get("steps", "")).rstrip()
    metrics = doc.get("metrics", []) or []

    lines: list[str] = [
        f"# {kind.capitalize()} — {title}",
        "",
        f"- **Status**: Draft (SRE agent; pending owner approval)",
        f"- **Severity**: {severity}",
        "",
        "## Summary",
        "",
        summary,
        "",
        "## Steps",
        "",
        steps,
        "",
    ]
    if metrics:
        lines.append("## Metrics / dashboards")
        lines.append("")
        for m in metrics:
            lines.append(f"- {m}")
        lines.append("")
    return "\n".join(lines)


class SRESupportAgent(BaseAgent):
    role: ClassVar[AgentId] = AgentId.SRE_SUPPORT
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
    system_prompt_path: ClassVar[Path] = _REPO_ROOT / "prompts" / "sre_support.md"
    # Per ADR-004: docs/runbooks/ + infra/monitoring/. Shell tools
    # (curl/promtool/journalctl) are deferred to iter-5 when there's a
    # destination they can usefully run against.
    mcp_env: ClassVar[dict[str, str]] = {
        "AI_TEAM_PATH_PREFIXES": "docs/runbooks,infra/monitoring",
    }

    def build_outputs(self, response: LLMResponse, incoming: AgentMessage) -> list[AgentMessage]:
        if not isinstance(incoming.payload, TaskAssignmentPayload):
            return []

        doc = response.structured
        if not doc or "title" not in doc or "slug" not in doc or "kind" not in doc:
            return [self._fail_report(incoming, "LLM did not return a parseable runbook")]

        slug = str(doc["slug"])
        if not _SLUG_RE.match(slug):
            return [self._fail_report(incoming, f"invalid slug {slug!r}")]
        kind = str(doc["kind"])
        if kind not in _RUNBOOK_KINDS:
            return [self._fail_report(incoming, f"unknown kind {kind!r}")]

        target_dir = _MONITORING_DIR if kind in ("alert", "dashboard") else _RUNBOOK_DIR
        filename = f"{slug}.md"
        try:
            target_dir.mkdir(parents=True, exist_ok=True)
            markdown = _render_runbook_markdown(doc=doc)
            (target_dir / filename).write_text(markdown)
        except OSError as e:
            return [self._fail_report(incoming, f"failed to write {kind}: {e}")]

        rel = target_dir.relative_to(_REPO_ROOT).as_posix()
        artifact_rel = f"{rel}/{filename}"
        return [
            AgentMessage(
                correlation_id=incoming.correlation_id,
                sender=AgentId.SRE_SUPPORT,
                recipient=AgentId.TEAM_LEAD,
                message_type=MessageType.TASK_REPORT,
                priority=incoming.priority,
                payload=TaskReportPayload(
                    task_id=incoming.payload.task_id,
                    status=TaskStatus.DONE,
                    progress_pct=100,
                    summary=f"{kind.capitalize()} — {doc['title']}",
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
            json_schema=SRE_REPORT_SCHEMA,
            env=dict(self.mcp_env) if self.mcp_env else None,
        )
        return self.build_outputs(response, msg)

    def _fail_report(self, incoming: AgentMessage, reason: str) -> AgentMessage:
        assert isinstance(incoming.payload, TaskAssignmentPayload)
        return AgentMessage(
            correlation_id=incoming.correlation_id,
            sender=AgentId.SRE_SUPPORT,
            recipient=AgentId.TEAM_LEAD,
            message_type=MessageType.TASK_REPORT,
            priority=incoming.priority,
            payload=TaskReportPayload(
                task_id=incoming.payload.task_id,
                status=TaskStatus.FAILED,
                progress_pct=0,
                summary=f"SRE could not write artefact: {reason}",
            ),
        )
