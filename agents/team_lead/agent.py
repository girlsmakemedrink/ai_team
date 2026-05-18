"""Team Lead agent. Opus-tier. Decomposes user tasks into sub-assignments.

See ADR-001, ADR-006 (Opus only for TL / Architect), ADR-007 (checkpoint
digests).
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, ClassVar
from uuid import uuid4

import structlog

from agents._base import BaseAgent
from core.messaging.schemas import (
    AgentId,
    AgentMessage,
    MessageType,
    Priority,
    TaskAssignmentPayload,
    TaskReportPayload,
    TaskStatus,
)

if TYPE_CHECKING:
    from core.llm.base import LLMResponse

_log = structlog.get_logger(__name__)

# JSON schema enforced via --json-schema in the LLM call.
DECOMPOSITION_SCHEMA: dict[str, object] = {
    "type": "object",
    "required": ["summary", "subtasks"],
    "additionalProperties": False,
    "properties": {
        "summary": {"type": "string"},
        "subtasks": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "required": ["recipient", "title", "description", "priority"],
                "additionalProperties": False,
                "properties": {
                    "recipient": {
                        "type": "string",
                        "enum": [
                            "product_manager",
                            "architect",
                            "designer",
                            "backend_developer",
                            "frontend_developer",
                            "devops",
                            "qa_engineer",
                            "sre_support",
                            "market_researcher",
                        ],
                    },
                    "title": {"type": "string", "minLength": 1, "maxLength": 200},
                    "description": {"type": "string", "minLength": 1, "maxLength": 10000},
                    "priority": {"type": "string", "enum": ["P1", "P2", "P3", "P4"]},
                },
            },
        },
    },
}


class TeamLeadAgent(BaseAgent):
    role: ClassVar[AgentId] = AgentId.TEAM_LEAD
    model_tier: ClassVar = "opus"
    allowed_tools: ClassVar[tuple[str, ...]] = ()
    system_prompt_path: ClassVar[Path] = (
        Path(__file__).resolve().parents[2] / "prompts" / "team_lead.md"
    )

    def build_outputs(
        self, response: LLMResponse, incoming: AgentMessage
    ) -> list[AgentMessage]:
        if incoming.message_type != MessageType.TASK_ASSIGNMENT:
            self._log.info(
                "tl.ignore_non_assignment",
                message_type=incoming.message_type.value,
            )
            return []

        if not isinstance(incoming.payload, TaskAssignmentPayload):
            return []  # type narrowing for the discriminated union

        plan = response.structured
        if plan is None or "subtasks" not in plan:
            return [self._fail_report(incoming, "LLM did not return parseable JSON")]

        outputs: list[AgentMessage] = []
        for sub in plan.get("subtasks", []):
            try:
                recipient = AgentId(sub["recipient"])
                priority = Priority(sub.get("priority", "P3"))
            except (ValueError, KeyError) as e:
                self._log.warning("tl.bad_subtask", error=str(e), subtask=sub)
                continue
            outputs.append(
                AgentMessage(
                    correlation_id=incoming.correlation_id,
                    sender=AgentId.TEAM_LEAD,
                    recipient=recipient,
                    message_type=MessageType.TASK_ASSIGNMENT,
                    priority=priority,
                    payload=TaskAssignmentPayload(
                        task_id=uuid4(),
                        title=str(sub["title"])[:200],
                        description=str(sub["description"])[:10_000],
                        target_repo=incoming.payload.target_repo,
                    ),
                )
            )
        return outputs

    # Override to attach the schema. We don't need session_id on TL since
    # decompositions are single-turn.
    async def handle(self, msg: AgentMessage) -> list[AgentMessage]:
        if msg.message_type != MessageType.TASK_ASSIGNMENT:
            self._log.debug("tl.skip", message_type=msg.message_type.value)
            return []
        user_msg = self._user_message_for(msg)
        response = await self._llm.invoke(
            system_prompt=self.system_prompt(),
            user_message=user_msg,
            model=self.model_tier,
            allowed_tools=self.allowed_tools,
            timeout_s=self.llm_timeout_s,
            max_turns=self.max_turns,
            json_schema=DECOMPOSITION_SCHEMA,
        )
        return self.build_outputs(response, msg)

    def _fail_report(self, incoming: AgentMessage, reason: str) -> AgentMessage:
        payload_task_id = (
            incoming.payload.task_id
            if isinstance(incoming.payload, TaskAssignmentPayload)
            else uuid4()
        )
        return AgentMessage(
            correlation_id=incoming.correlation_id,
            sender=AgentId.TEAM_LEAD,
            recipient=AgentId.USER,
            message_type=MessageType.TASK_REPORT,
            priority=Priority.P2,
            payload=TaskReportPayload(
                task_id=payload_task_id,
                status=TaskStatus.FAILED,
                progress_pct=0,
                summary=f"Team Lead could not decompose the task: {reason}",
            ),
        )
