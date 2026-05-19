"""Product Manager agent. Sonnet-tier. Emits user stories from a task_assignment.

See ADR-001, ADR-006 (Sonnet for default agents).
"""

from __future__ import annotations

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
_BACKLOG_DIR = _REPO_ROOT / "docs" / "backlog"

USER_STORIES_SCHEMA: dict[str, object] = {
    "type": "object",
    "required": ["summary", "stories"],
    "additionalProperties": False,
    "properties": {
        "summary": {"type": "string", "maxLength": 2000},
        "stories": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "required": [
                    "id",
                    "as_a",
                    "i_want",
                    "so_that",
                    "acceptance_criteria",
                    "priority",
                ],
                "additionalProperties": False,
                "properties": {
                    "id": {"type": "string"},
                    "as_a": {"type": "string"},
                    "i_want": {"type": "string"},
                    "so_that": {"type": "string"},
                    "acceptance_criteria": {
                        "type": "array",
                        "minItems": 1,
                        "items": {"type": "string"},
                    },
                    "priority": {"type": "string", "enum": ["P1", "P2", "P3"]},
                },
            },
        },
    },
}


def _render_markdown(plan: dict[str, Any], incoming: AgentMessage) -> str:
    title = (
        incoming.payload.title
        if isinstance(incoming.payload, TaskAssignmentPayload)
        else "(no title)"
    )
    lines = [
        f"# Backlog — {title}",
        "",
        f"Correlation: `{incoming.correlation_id}`",
        "",
        "## Summary",
        "",
        str(plan.get("summary", "(no summary)")),
        "",
        "## Stories",
        "",
    ]
    for s in plan.get("stories", []):
        lines.append(f"### {s.get('id', 'US-?')} — {s.get('priority', 'P3')}")
        lines.append("")
        lines.append(f"**As a** {s.get('as_a', '?')}")
        lines.append(f"**I want** {s.get('i_want', '?')}")
        lines.append(f"**So that** {s.get('so_that', '?')}")
        lines.append("")
        lines.append("Acceptance criteria:")
        for ac in s.get("acceptance_criteria", []):
            lines.append(f"- {ac}")
        lines.append("")
    return "\n".join(lines)


class ProductManagerAgent(BaseAgent):
    role: ClassVar[AgentId] = AgentId.PRODUCT_MANAGER
    model_tier: ClassVar = "sonnet"
    allowed_tools: ClassVar[tuple[str, ...]] = ()
    system_prompt_path: ClassVar[Path] = _REPO_ROOT / "prompts" / "product_manager.md"

    def build_outputs(self, response: LLMResponse, incoming: AgentMessage) -> list[AgentMessage]:
        if incoming.message_type != MessageType.TASK_ASSIGNMENT or not isinstance(
            incoming.payload, TaskAssignmentPayload
        ):
            return []

        plan = response.structured or {}
        summary = str(plan.get("summary", "(no stories generated)"))[:2_000]

        # Persist long-form markdown under docs/backlog/.
        artifact_path: Path | None = None
        try:
            _BACKLOG_DIR.mkdir(parents=True, exist_ok=True)
            artifact_path = _BACKLOG_DIR / f"{incoming.correlation_id}.md"
            artifact_path.write_text(_render_markdown(plan, incoming))
        except OSError:
            _log.exception("pm.artifact.write_failed", correlation_id=str(incoming.correlation_id))
            artifact_path = None

        return [
            AgentMessage(
                correlation_id=incoming.correlation_id,
                sender=AgentId.PRODUCT_MANAGER,
                recipient=AgentId.TEAM_LEAD,
                message_type=MessageType.TASK_REPORT,
                priority=incoming.priority,
                payload=TaskReportPayload(
                    task_id=incoming.payload.task_id,
                    status=TaskStatus.DONE,
                    progress_pct=100,
                    summary=summary,
                    artifacts=[str(artifact_path.relative_to(_REPO_ROOT))] if artifact_path else [],
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
            json_schema=USER_STORIES_SCHEMA,
        )
        return self._stamp_metrics(self.build_outputs(response, msg), response)
