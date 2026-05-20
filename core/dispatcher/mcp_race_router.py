"""Substring router for LLM-emitted MCP-race task_reports.

iter-10: the iter-9 pre-flight gate (`core/llm/mcp_health.py`)
catches deterministic startup failures — module import errors,
`Context.from_env` validation. But the iter-8 + iter-9 demos
showed the actual race surface is mid-session: claude -p's
MCP subprocess spawn fails AFTER the gate's in-process probe
passes. The LLM detects this and emits a schema-valid
`task_report(failed)` whose summary names the failure
verbatim:

  - iter-9 demo: "MCP server ai-team-repo never connected"
  - iter-8 demo: "the ai-team-repo MCP server never finished
                  connecting (all three ToolSearch retries
                  returned 'still connecting')"
  - iter-11 demo: "BLOCKED: ... mcp__ai_team_repo__* tools
                    were unavailable throughout the session"
                  (added iter-12 — different shape: names
                  the mcp__-prefixed tool, not the MCP
                  server, and uses the word "unavailable"
                  rather than "never connected")

This module substring-matches those patterns and rewrites
to `BLOCKED(blocked_on='mcp_unhealthy')` so dependents stay
held in the HoldQueue (mirrors iter-6's
`LLMBudgetExhaustedError → BLOCKED` contract). The rewrite
happens BEFORE HMAC-sign in the dispatcher's outbound loop —
audit / feed / task_state / HoldQueue all see one consistent
BLOCKED version.

False-positive risk is near-zero: each pattern requires the
co-occurrence of "MCP server" plus a specific failure verb,
wording the LLM only produces when actually reporting an MCP
outage. A genuine pytest AssertionError summary won't match.
"""

from __future__ import annotations

from core.messaging.schemas import AgentMessage, TaskReportPayload, TaskStatus

# Each tuple is one pattern: ALL substrings must appear in the
# summary for that pattern to match. Derived from iter-8 +
# iter-9 + iter-11 demo Backend reports verbatim. Add new
# patterns here (not regex) when a new shape appears in a
# real-LLM demo.
_MCP_RACE_PATTERNS: tuple[tuple[str, ...], ...] = (
    ("MCP server", "never connected"),
    ("MCP server", "never finished connecting"),
    ("MCP server", "still connecting"),
    # iter-12: Backend's iter-11 demo wording —
    # "mcp__ai_team_repo__* tools were unavailable
    # throughout the session". The first tuple catches the
    # mcp__-prefixed phrasing exactly; the second catches
    # the slightly more general "MCP tools" + "unavailable"
    # form a future run might emit. Both still require
    # both substrings to co-occur — near-zero false-positive
    # risk. See iter_11_demo_report.md Failure 1.
    ("mcp__ai_team_repo", "unavailable"),
    ("MCP tools", "unavailable"),
)


def maybe_route_mcp_race_to_blocked(msg: AgentMessage) -> AgentMessage:
    """If `msg` is a `task_report(failed)` whose summary
    matches an MCP-race pattern, return a copy with
    `payload.status=BLOCKED, payload.blocked_on='mcp_unhealthy'`.
    Otherwise return `msg` unchanged (same object reference).

    The summary is preserved verbatim — the LLM's exact
    wording is the most useful diagnostic for the owner.
    """
    payload = msg.payload
    if not isinstance(payload, TaskReportPayload):
        return msg
    if payload.status != TaskStatus.FAILED:
        return msg
    if not _matches_any_pattern(payload.summary):
        return msg
    return msg.model_copy(
        update={
            "payload": payload.model_copy(
                update={
                    "status": TaskStatus.BLOCKED,
                    "blocked_on": "mcp_unhealthy",
                }
            )
        }
    )


def _matches_any_pattern(summary: str) -> bool:
    return any(all(tok in summary for tok in pat) for pat in _MCP_RACE_PATTERNS)
