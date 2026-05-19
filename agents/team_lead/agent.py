"""Team Lead agent. Opus-tier. Decomposes user tasks into sub-assignments.

See ADR-001, ADR-006 (Opus only for TL / Architect), ADR-007 (checkpoint
digests).
"""

from __future__ import annotations

import re
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
    from uuid import UUID

    from core.llm.base import LLMResponse

_log = structlog.get_logger(__name__)

# Marker the TL inserts in auto-routed task descriptions; it also blocks
# a second auto-route to prevent BLOCKED-ping-pong (DevOps → Backend →
# DevOps → ...). One auto-hop is allowed; further BLOCKED reports on the
# same chain surface in the digest for the owner.
_AUTO_ROUTED_MARKER = "auto-routed"
_BLOCKED_SUMMARY_RE = re.compile(r"blocked:\s*requires\s+(\w+)", re.IGNORECASE)


# Per-subtask slug pattern, also reused for depends_on references.
# Lowercase, starts with a letter, only [a-z0-9_], <=32 chars. Keeps
# decomposition output compact and prevents LLM-side typos from sneaking
# in unexpected characters.
_SUBTASK_ID_PATTERN = r"^[a-z][a-z0-9_]{0,31}$"


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
                "required": ["id", "recipient", "title", "description", "priority"],
                "additionalProperties": False,
                "properties": {
                    "id": {"type": "string", "pattern": _SUBTASK_ID_PATTERN},
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
                    "depends_on": {
                        "type": "array",
                        "items": {"type": "string", "pattern": _SUBTASK_ID_PATTERN},
                        "default": [],
                    },
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

    def build_outputs(self, response: LLMResponse, incoming: AgentMessage) -> list[AgentMessage]:
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

        subtasks = plan.get("subtasks", [])

        # Pass 1: assign a UUID to every slug so forward references work
        # (a subtask listed earlier in the array can depend on one
        # listed later — runtime ordering is enforced by the dispatcher's
        # HoldQueue, not by list position).
        slug_to_task_id: dict[str, UUID] = {}
        for sub in subtasks:
            slug = sub.get("id")
            if not isinstance(slug, str):
                self._log.warning("tl.bad_subtask_missing_id", subtask=sub)
                continue
            slug_to_task_id[slug] = uuid4()

        # Pass 2: build the outbound AgentMessages. depends_on slugs that
        # don't resolve to a sibling fail the whole decomposition loudly
        # (LLM-side bug → owner sees a TASK_REPORT(FAILED), retries).
        outputs: list[AgentMessage] = []
        for sub in subtasks:
            try:
                slug = sub["id"]
                recipient = AgentId(sub["recipient"])
                priority = Priority(sub.get("priority", "P3"))
            except (ValueError, KeyError) as e:
                self._log.warning("tl.bad_subtask", error=str(e), subtask=sub)
                continue

            depends_on_slugs = sub.get("depends_on", []) or []
            depends_on_task_ids: list[str] = []
            for dep_slug in depends_on_slugs:
                if dep_slug not in slug_to_task_id:
                    return [
                        self._fail_report(
                            incoming,
                            f"subtask {slug!r} declares unknown depends_on slug {dep_slug!r}",
                        )
                    ]
                depends_on_task_ids.append(str(slug_to_task_id[dep_slug]))

            outputs.append(
                AgentMessage(
                    correlation_id=incoming.correlation_id,
                    sender=AgentId.TEAM_LEAD,
                    recipient=recipient,
                    message_type=MessageType.TASK_ASSIGNMENT,
                    priority=priority,
                    payload=TaskAssignmentPayload(
                        task_id=slug_to_task_id[slug],
                        title=str(sub["title"])[:200],
                        description=str(sub["description"])[:10_000],
                        target_repo=incoming.payload.target_repo,
                    ),
                    metadata={
                        "subtask_id": slug,
                        "depends_on": depends_on_task_ids,
                        "parent_task_id": str(incoming.payload.task_id),
                    },
                )
            )
        return outputs

    # Override to attach the schema. We don't need session_id on TL since
    # decompositions are single-turn.
    async def handle(self, msg: AgentMessage) -> list[AgentMessage]:
        if msg.message_type == MessageType.TASK_REPORT:
            return self._maybe_route_blocked(msg)
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

    def _maybe_route_blocked(self, msg: AgentMessage) -> list[AgentMessage]:
        """Route a BLOCKED task_report to the indicated role.

        Pure dispatch — no LLM call. Saves an Opus turn on every routing
        hop. Returns an empty list when there's nothing to do (the owner
        sees the BLOCKED report in the digest as before).
        """
        if not isinstance(msg.payload, TaskReportPayload):
            return []
        if msg.payload.status != TaskStatus.BLOCKED:
            return []

        # Anti-loop: if the BLOCKED report was already an auto-routed
        # follow-up, refuse to re-route a second time. The chain stops
        # and the owner sees it in the digest.
        if _AUTO_ROUTED_MARKER in msg.payload.summary.lower():
            self._log.info(
                "tl.blocked_route_skipped_already_routed",
                sender=msg.sender.value,
                correlation_id=str(msg.correlation_id),
            )
            return []

        target = self._parse_blocked_target(msg.payload)
        if target is None or target == AgentId.TEAM_LEAD:
            return []
        self._log.info(
            "tl.blocked_route",
            from_=msg.sender.value,
            to=target.value,
            correlation_id=str(msg.correlation_id),
        )
        return [
            AgentMessage(
                correlation_id=msg.correlation_id,
                sender=AgentId.TEAM_LEAD,
                recipient=target,
                message_type=MessageType.TASK_ASSIGNMENT,
                priority=msg.priority,
                payload=TaskAssignmentPayload(
                    task_id=uuid4(),
                    title=f"Unblock: {msg.payload.summary[:160]}",
                    description=(
                        f"[{_AUTO_ROUTED_MARKER} from {msg.sender.value}] "
                        f"{msg.sender.value} reported BLOCKED on this work. "
                        f"Their summary:\n\n{msg.payload.summary}\n\n"
                        f"Resolve the prerequisite, then report back to "
                        f"the Team Lead."
                    ),
                ),
            )
        ]

    @staticmethod
    def _parse_blocked_target(payload: TaskReportPayload) -> AgentId | None:
        # Preferred: explicit `blocked_on` field on the payload.
        if payload.blocked_on:
            try:
                return AgentId(payload.blocked_on)
            except ValueError:
                pass
        # Fallback: parse "blocked: requires <role>" from the summary.
        m = _BLOCKED_SUMMARY_RE.search(payload.summary)
        if m:
            try:
                return AgentId(m.group(1).lower())
            except ValueError:
                return None
        return None

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
