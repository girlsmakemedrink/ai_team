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
    BroadcastPayload,
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
# iter-21: special blocked_on value emitted by Backend's runtime
# tripwire. Triggers a TL self-targeted re-decomposition turn instead
# of the usual "route to AgentId(blocked_on)" path (task_too_large is
# not a valid AgentId). See docs/iterations/iter_21.md Phase 2.
_TASK_TOO_LARGE_BLOCKED_ON = "task_too_large"
_ALREADY_ROUTED_MARKER = "auto-routed already"
# iter-24: more reliable routing signal than `blocked_on`. Backend's
# Scope pre-flight prompt template (prompts/backend_developer.md:25)
# guarantees the BLOCKED summary starts with this literal prefix. The
# `blocked_on` field is semantic (LLM elaborates into it); the summary
# prefix is structural (the LLM copies it from the template). iter-23
# demo R#1 stalled because the LLM put scope description into
# blocked_on instead of the canonical token; this signal sidesteps
# that fragility entirely.
_SCOPE_PREFLIGHT_SUMMARY_PREFIX = "Scope pre-flight"


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
                    "inputs": {
                        "type": "object",
                        "default": {},
                        "additionalProperties": True,
                    },
                },
            },
        },
    },
}


class TeamLeadAgent(BaseAgent):
    role: ClassVar[AgentId] = AgentId.TEAM_LEAD
    model_tier: ClassVar = "opus"
    # iter-19: explicit non-empty whitelist replaces iter-1's `()`
    # which fell back to claude -p's permissive default (all configured
    # MCP + native tools allowed) — see iter_18_demo_report.md Caveat
    # 1. TL emits one structured-JSON decomposition turn;
    # Read/Glob/Grep cover consulting docs/iterations/ or
    # docs/sandbox/ for the source spec. No MCP tools, no Write/Edit,
    # no Bash.
    allowed_tools: ClassVar[tuple[str, ...]] = ("Read", "Glob", "Grep")
    system_prompt_path: ClassVar[Path] = (
        Path(__file__).resolve().parents[2] / "prompts" / "team_lead.md"
    )
    # TL decomposition turns are short (~30 s observed across iter-3..10
    # demos). Stays at 300 after iter-11 flipped BaseAgent's default
    # to 600.
    llm_timeout_s: ClassVar[int] = 300

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
                        inputs=sub.get("inputs") or {},
                    ),
                    metadata={
                        "subtask_id": slug,
                        "depends_on": depends_on_task_ids,
                        "parent_task_id": str(incoming.payload.task_id),
                    },
                )
            )

        # iter-4 Phase 4: emit a DAG-preview broadcast at index 0 so the
        # owner sees the planned decomposition in `ai-team watch` before
        # the per-subtask assignments hit the bus. Informational only;
        # not a gate. See iter_3_demo_report.md Failure 3 for context.
        if outputs:
            outputs.insert(
                0,
                AgentMessage(
                    correlation_id=incoming.correlation_id,
                    sender=AgentId.TEAM_LEAD,
                    recipient=AgentId.BROADCAST,
                    message_type=MessageType.BROADCAST,
                    priority=Priority.P3,
                    payload=BroadcastPayload(
                        topic="tl.dag_preview",
                        body=self._render_dag_markdown(subtasks),
                    ),
                    metadata={"parent_task_id": str(incoming.payload.task_id)},
                ),
            )
        return outputs

    @staticmethod
    def _render_dag_markdown(subtasks: list[dict[str, object]]) -> str:
        """Render a per-subtask depends_on summary the owner can scan in
        `ai-team watch`. Bullet per subtask with slug → recipient and
        any declared dependencies."""
        lines: list[str] = ["## Decomposition plan"]
        for sub in subtasks:
            slug = sub.get("id", "?")
            recipient = sub.get("recipient", "?")
            deps_raw = sub.get("depends_on") or []
            deps = [str(d) for d in deps_raw] if isinstance(deps_raw, list) else []
            deps_str = f" depends_on=[{', '.join(deps)}]" if deps else ""
            title = str(sub.get("title", ""))[:80]
            lines.append(f"- **{slug}** → `{recipient}`{deps_str}: {title}")
        return "\n".join(lines)

    # Override to attach the schema. We don't need session_id on TL since
    # decompositions are single-turn.
    async def handle(self, msg: AgentMessage) -> list[AgentMessage]:
        if msg.message_type == MessageType.TASK_REPORT:
            # Blocked-routing is pure dispatch (no LLM call), so no
            # metrics to stamp.
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
            env=self._build_env(msg),
        )
        outputs = self.build_outputs(response, msg)
        return self._stamp_metrics(outputs, response)

    def _maybe_route_blocked(self, msg: AgentMessage) -> list[AgentMessage]:
        """Route a BLOCKED task_report to the indicated role.

        Pure dispatch — no LLM call. Saves an Opus turn on every routing
        hop. Returns an empty list when there's nothing to do (the owner
        sees the BLOCKED report in the digest as before).

        iter-21: blocked_on='task_too_large' is a special case — TL
        re-decomposes the original Backend work via a self-targeted
        task_assignment. See _re_decompose_on_too_large.
        """
        if not isinstance(msg.payload, TaskReportPayload):
            return []
        if msg.payload.status != TaskStatus.BLOCKED:
            return []

        # iter-24: primary self-eject signal is the BLOCKED summary's
        # Scope pre-flight prefix — structurally enforced by Backend's
        # prompt template (prompts/backend_developer.md:25). This is
        # immune to the iter-23 R#1 failure mode where the LLM filled
        # blocked_on with a free-form sentence instead of the canonical
        # token. iter-23 substring on blocked_on stays as a fallback
        # for legacy in-flight messages.
        summary = (msg.payload.summary or "").strip()
        bo = (msg.payload.blocked_on or "").strip()
        if (
            summary.startswith(_SCOPE_PREFLIGHT_SUMMARY_PREFIX)
            or bo == _TASK_TOO_LARGE_BLOCKED_ON
            or _TASK_TOO_LARGE_BLOCKED_ON in bo.lower()
        ):
            return self._re_decompose_on_too_large(msg)

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

    def _re_decompose_on_too_large(self, msg: AgentMessage) -> list[AgentMessage]:
        """iter-21: self-targeted task_assignment that triggers a TL re-decomp.

        Backend's tripwire echoes the original task description (first
        800 chars) into the BLOCKED summary; we forward that into the
        new task_assignment. TL's standard handle() runs the
        decomposition LLM and emits smaller Backend subtasks.

        Anti-loop: refuse if the BLOCKED summary already carries the
        'auto-routed already' marker (Backend's tripwire propagates it
        when the incoming task description was itself an auto-route).
        """
        assert isinstance(msg.payload, TaskReportPayload)
        summary = msg.payload.summary
        if _ALREADY_ROUTED_MARKER in summary.lower():
            self._log.info(
                "tl.task_too_large_anti_loop_refused",
                sender=msg.sender.value,
                correlation_id=str(msg.correlation_id),
            )
            return []
        self._log.info(
            "tl.task_too_large_re_decompose",
            sender=msg.sender.value,
            correlation_id=str(msg.correlation_id),
        )
        description = (
            f"[{_AUTO_ROUTED_MARKER} from {msg.sender.value}] "
            f"{msg.sender.value} reported BLOCKED(task_too_large). "
            "Re-decompose the original work into 2-3 smaller subtasks "
            "of <=100 LOC each (or fewer if that's still too large), "
            "and dispatch them to backend_developer with explicit "
            "depends_on slugs where needed. Backend's original BLOCKED "
            f"report follows:\n\n{summary}"
        )[:10_000]
        return [
            AgentMessage(
                correlation_id=msg.correlation_id,
                sender=AgentId.TEAM_LEAD,
                recipient=AgentId.TEAM_LEAD,
                message_type=MessageType.TASK_ASSIGNMENT,
                priority=msg.priority,
                payload=TaskAssignmentPayload(
                    task_id=uuid4(),
                    title=f"Re-decompose: {summary[:80]}",
                    description=description,
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
