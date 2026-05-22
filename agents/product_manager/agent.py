"""Product Manager agent. Sonnet-tier. Emits user stories from a task_assignment.

See ADR-001, ADR-006 (Sonnet for default agents).
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
_BACKLOG_DIR = _REPO_ROOT / "docs" / "backlog"
_VALIDATE_DIR: Path = _REPO_ROOT / "docs" / "products"

_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

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


VALIDATE_REVENUE_SCHEMA: dict[str, object] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "intent_completed",
        "buyer_persona",
        "addressable_population_estimate",
        "pricing_tiers",
        "cac_envelope_usd",
        "ltv_envelope_usd",
        "time_to_first_revenue_weeks",
        "time_to_1k_mrr_weeks",
        "break_even_users",
        "revenue_forecast",
        "verdict",
        "summary",
        "artifacts",
    ],
    "properties": {
        "intent_completed": {"const": "validate_revenue_model"},
        "buyer_persona": {"type": "string", "maxLength": 1000},
        "addressable_population_estimate": {"type": "string", "maxLength": 500},
        "pricing_tiers": {
            "type": "array",
            "minItems": 2,
            "maxItems": 4,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["name", "price_usd_monthly", "target_user"],
                "properties": {
                    "name": {"type": "string", "maxLength": 100},
                    "price_usd_monthly": {"type": "number", "minimum": 0},
                    "target_user": {"type": "string", "maxLength": 300},
                },
            },
        },
        "cac_envelope_usd": {"type": "number", "minimum": 0},
        "ltv_envelope_usd": {"type": "number", "minimum": 0},
        "time_to_first_revenue_weeks": {"type": "integer", "minimum": 1},
        "time_to_1k_mrr_weeks": {"type": "integer", "minimum": 1},
        "break_even_users": {"type": "integer", "minimum": 1},
        "revenue_forecast": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "conservative_mrr_month_6",
                "base_mrr_month_6",
                "optimistic_mrr_month_6",
            ],
            "properties": {
                "conservative_mrr_month_6": {"type": "number", "minimum": 0},
                "base_mrr_month_6": {"type": "number", "minimum": 0},
                "optimistic_mrr_month_6": {"type": "number", "minimum": 0},
            },
        },
        "verdict": {"enum": ["viable", "viable_with_caveats", "not_viable"]},
        "summary": {"type": "string", "maxLength": 2000},
        "artifacts": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 1,
        },
    },
}


def _escape_pipes(s: str) -> str:
    """Escape `|` in GFM table cells."""
    return s.replace("|", "\\|")


def _render_revenue_markdown(response: dict[str, Any], slug: str) -> str:
    """Render VALIDATE_REVENUE_SCHEMA output as revenue.md."""
    lines: list[str] = []
    lines.append(f"# Revenue model: {slug}\n")
    lines.append(f"- Verdict: **{response['verdict']}**")
    lines.append(f"- Break-even users: **{response['break_even_users']}**")
    lines.append(f"- Time to first revenue: **{response['time_to_first_revenue_weeks']} weeks**")
    lines.append(f"- Time to $1k MRR: **{response['time_to_1k_mrr_weeks']} weeks**\n")
    lines.append("## Summary\n")
    lines.append(response["summary"])
    lines.append("")
    lines.append("## Buyer persona\n")
    lines.append(response["buyer_persona"])
    lines.append("")
    lines.append("## Addressable population\n")
    lines.append(response["addressable_population_estimate"])
    lines.append("")
    lines.append("## Pricing tiers\n")
    lines.append("| Tier | $/month | Target user |")
    lines.append("|---|---|---|")
    for t in response["pricing_tiers"]:
        lines.append(
            f"| {_escape_pipes(t['name'])} | ${t['price_usd_monthly']:g}"
            f" | {_escape_pipes(t['target_user'])} |"
        )
    lines.append("")
    lines.append("## Unit economics\n")
    lines.append(f"- CAC envelope: **${response['cac_envelope_usd']:g}** / user")
    lines.append(f"- LTV envelope: **${response['ltv_envelope_usd']:g}** / user")
    lines.append("")
    lines.append("## Revenue forecast (month 6)\n")
    rf = response["revenue_forecast"]
    lines.append(f"- Conservative: ${rf['conservative_mrr_month_6']:.0f} MRR")
    lines.append(f"- Base:         ${rf['base_mrr_month_6']:.0f} MRR")
    lines.append(f"- Optimistic:   ${rf['optimistic_mrr_month_6']:.0f} MRR")
    lines.append("")
    return "\n".join(lines)


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
    # iter-19: explicit non-empty whitelist replaces iter-3's `()`
    # which fell back to claude -p's permissive default (all configured
    # MCP + native tools allowed) — see iter_18_demo_report.md Caveat
    # 1. PM emits one structured-JSON turn via --json-schema;
    # Read/Glob/Grep cover the rare case of consulting docs/backlog/
    # for prior stories. No MCP tools, no Write/Edit, no Bash.
    allowed_tools: ClassVar[tuple[str, ...]] = ("Read", "Glob", "Grep")
    system_prompt_path: ClassVar[Path] = _REPO_ROOT / "prompts" / "product_manager.md"
    # iter-19: bumped 300 → 600 after iter-18 demo run #1 hit the
    # 300s wall and burned $1.75 on tenacity retries. iter-17 had
    # already measured PM at 277s (92% of cap). Joins the LLM-bound
    # majority (Backend / Architect / Designer / Frontend / DevOps)
    # at the iter-11 default of 600s.
    llm_timeout_s: ClassVar[int] = 600

    def build_outputs(self, response: LLMResponse, incoming: AgentMessage) -> list[AgentMessage]:
        if incoming.message_type != MessageType.TASK_ASSIGNMENT or not isinstance(
            incoming.payload, TaskAssignmentPayload
        ):
            return []

        inputs = incoming.payload.inputs or {}
        intent = inputs.get("intent")

        if intent == "validate_revenue_model":
            return self._build_validate_revenue_outputs(response, incoming)

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

    def _build_validate_revenue_outputs(
        self, response: LLMResponse, incoming: AgentMessage
    ) -> list[AgentMessage]:
        assert isinstance(incoming.payload, TaskAssignmentPayload)
        inputs = incoming.payload.inputs or {}
        slug = str(inputs.get("slug", ""))
        out = response.structured or {}

        if not out or out.get("intent_completed") != "validate_revenue_model":
            return [
                self._fail_report(
                    incoming,
                    "missing or malformed structured_output",
                    kind="revenue validation",
                )
            ]

        out_dir = _VALIDATE_DIR / slug
        try:
            out_dir.mkdir(parents=True, exist_ok=True)
            artifact_path = out_dir / "revenue.md"
            artifact_path.write_text(_render_revenue_markdown(out, slug=slug))
        except OSError as e:
            return [
                self._fail_report(
                    incoming,
                    f"failed to write revenue.md: {e}",
                    kind="revenue validation",
                )
            ]

        artifact_rel = f"docs/products/{slug}/revenue.md"
        summary = str(out.get("summary") or "validate_revenue_model completed")
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
                    summary=summary[:2_000],
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

        if intent == "validate_revenue_model":
            slug = str(inputs.get("slug", ""))
            if not _SLUG_RE.match(slug):
                return [
                    self._fail_report(
                        msg,
                        f"validate_revenue_model: input_validation — invalid slug {slug!r}",
                        kind="revenue validation",
                    )
                ]
            schema: dict[str, object] = VALIDATE_REVENUE_SCHEMA
            session_id = str(msg.payload.task_id)
            max_budget_usd = 3.50
            env: dict[str, str] = self._build_env(msg)
            env["AI_TEAM_PATH_PREFIXES"] = f"docs/backlog,docs/products/{slug}"
        else:
            schema = USER_STORIES_SCHEMA
            session_id = str(msg.correlation_id)
            env = self._build_env(msg)

        invoke_kwargs: dict[str, Any] = {
            "system_prompt": self.system_prompt(),
            "user_message": self._user_message_for(msg),
            "model": self.model_tier,
            "allowed_tools": self.allowed_tools,
            "session_id": session_id,
            "timeout_s": self.llm_timeout_s,
            "max_turns": self.max_turns,
            "json_schema": schema,
            "env": env,
        }
        if max_budget_usd is not None:
            invoke_kwargs["max_budget_usd"] = max_budget_usd

        response = await self._llm.invoke(**invoke_kwargs)
        return self._stamp_metrics(self.build_outputs(response, msg), response)

    def _fail_report(
        self, incoming: AgentMessage, reason: str, *, kind: str = "user-stories"
    ) -> AgentMessage:
        assert isinstance(incoming.payload, TaskAssignmentPayload)
        return AgentMessage(
            correlation_id=incoming.correlation_id,
            sender=AgentId.PRODUCT_MANAGER,
            recipient=AgentId.TEAM_LEAD,
            message_type=MessageType.TASK_REPORT,
            priority=incoming.priority,
            payload=TaskReportPayload(
                task_id=incoming.payload.task_id,
                status=TaskStatus.FAILED,
                progress_pct=0,
                summary=f"Product Manager could not write {kind}: {reason}",
            ),
        )
