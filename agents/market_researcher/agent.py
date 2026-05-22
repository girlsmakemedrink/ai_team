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


BRAINSTORM_NICHE_SCHEMA: dict[str, object] = {
    "type": "object",
    "required": [
        "niche",
        "candidates",
        "researcher_top_3_slugs",
        "research_sources_used",
    ],
    "additionalProperties": False,
    "properties": {
        "niche": {
            "type": "string",
            "enum": ["dev_tools", "b2b_smb", "creator_tools"],
        },
        "candidates": {
            "type": "array",
            "minItems": 5,
            "maxItems": 5,
            "items": {
                "type": "object",
                "required": [
                    "title", "slug", "one_paragraph", "target_buyer",
                    "monetization", "known_competitors", "scores",
                    "composite_score", "rationale",
                ],
                "additionalProperties": False,
                "properties": {
                    "title":         {"type": "string", "minLength": 1, "maxLength": 120},
                    "slug":          {"type": "string", "pattern": "^[a-z0-9]+(-[a-z0-9]+)*$"},
                    "one_paragraph": {"type": "string", "minLength": 1, "maxLength": 1500},
                    "target_buyer":  {"type": "string", "minLength": 1, "maxLength": 300},
                    "monetization": {
                        "type": "string",
                        "enum": ["subscription", "per-seat", "usage", "one-time", "freemium"],
                    },
                    "known_competitors": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "required": ["name", "positioning"],
                            "additionalProperties": False,
                            "properties": {
                                "name":        {"type": "string"},
                                "url":         {"type": "string"},
                                "positioning": {"type": "string"},
                            },
                        },
                    },
                    "scores": {
                        "type": "object",
                        "required": [
                            "tam_signal", "solo_fit", "llm_opex_fit",
                            "defensibility", "time_to_first_revenue",
                        ],
                        "additionalProperties": False,
                        "properties": {
                            "tam_signal": {
                                "type": "integer", "minimum": 1, "maximum": 5
                            },
                            "solo_fit": {
                                "type": "integer", "minimum": 1, "maximum": 5
                            },
                            "llm_opex_fit": {
                                "type": "integer", "minimum": 1, "maximum": 5
                            },
                            "defensibility": {
                                "type": "integer", "minimum": 1, "maximum": 5
                            },
                            "time_to_first_revenue": {
                                "type": "integer", "minimum": 1, "maximum": 5
                            },
                        },
                    },
                    "composite_score": {"type": "integer", "minimum": 5, "maximum": 25},
                    "rationale":       {"type": "string", "minLength": 1, "maxLength": 1500},
                },
            },
        },
        "researcher_top_3_slugs": {
            "type": "array",
            "minItems": 3,
            "maxItems": 3,
            "items": {"type": "string", "pattern": "^[a-z0-9]+(-[a-z0-9]+)*$"},
        },
        "research_sources_used": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
}


def _render_brainstorm_markdown(scan: dict[str, Any]) -> str:
    """Render BRAINSTORM_NICHE_SCHEMA output to human-readable Markdown."""
    lines: list[str] = [
        f"# Brainstorm — {scan['niche']}",
        "",
        "- **Status**: Draft (Market Researcher; pending owner approval)",
        f"- **Candidates**: {len(scan['candidates'])}",
        "",
        "## Researcher top-3",
        "",
    ]
    by_slug = {c["slug"]: c for c in scan["candidates"]}
    for slug in scan["researcher_top_3_slugs"]:
        cand = by_slug.get(slug)
        if cand is None:
            lines.append(f"- [missing slug in candidates: `{slug}`]")
        else:
            score = cand["composite_score"]
            lines.append(f"- **{cand['title']}** (`{slug}`) — composite {score}/25")
    lines.append("")
    lines.append("## All candidates")
    lines.append("")
    for cand in scan["candidates"]:
        lines.append(f"### {cand['title']} (`{cand['slug']}`)")
        lines.append("")
        lines.append(cand["one_paragraph"].strip())
        lines.append("")
        lines.append(f"- **Target buyer**: {cand['target_buyer']}")
        lines.append(f"- **Monetization**: {cand['monetization']}")
        s = cand["scores"]
        lines.append(
            f"- **Scores**: TAM {s['tam_signal']} · solo {s['solo_fit']} · "
            f"LLM-OPEX {s['llm_opex_fit']} · defensibility {s['defensibility']} · "
            f"TTFR {s['time_to_first_revenue']} → composite {cand['composite_score']}/25"
        )
        lines.append("")
        if cand["known_competitors"]:
            lines.append("- **Known competitors**:")
            for comp in cand["known_competitors"]:
                url = f" ({comp.get('url')})" if comp.get("url") else ""
                lines.append(f"  - {comp['name']}{url}: {comp['positioning']}")
        lines.append("")
        lines.append(f"_Rationale_: {cand['rationale'].strip()}")
        lines.append("")
    lines.append("## Sources consulted")
    lines.append("")
    for src in scan["research_sources_used"]:
        lines.append(f"- {src}")
    lines.append("")
    return "\n".join(lines)


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
