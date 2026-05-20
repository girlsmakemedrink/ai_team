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
  - iter-13 demo: "BLOCKER: mcp__ai_team_repo server never
                    connected (ToolSearch tried 4 times across
                    2 sessions)"
                  (added iter-14 — different again: mixes
                  the mcp__-prefixed tool name from iter-12
                  with the "never connected" failure verb
                  from iter-10; neither prior tuple catches
                  the combination on its own)
  - iter-14 demo: "MCP server `ai-team-repo` failed to
                    connect. Tools `mcp__ai_team_repo__...`
                    were not available after three ToolSearch
                    retries"
                  (added iter-15 — empirical motivation for
                  the design shift: three iterations of one-
                  tuple-per-iteration and the LLM produced
                  four distinct phrasings. iter-15 replaces
                  the tuple-of-tuples with a cross-product
                  of two narrow token sets.)

This module substring-matches those patterns and rewrites
to `BLOCKED(blocked_on='mcp_unhealthy')` so dependents stay
held in the HoldQueue (mirrors iter-6's
`LLMBudgetExhaustedError → BLOCKED` contract). The rewrite
happens BEFORE HMAC-sign in the dispatcher's outbound loop —
audit / feed / task_state / HoldQueue all see one consistent
BLOCKED version.

False-positive risk is near-zero: each set is narrow and
domain-specific. A summary matches iff it contains ANY
MCP-naming token AND ANY MCP-failure verb. A genuine pytest
AssertionError summary contains no MCP-token at all; a
report mentioning "MCP server connected; tests passed"
contains no failure verb. Both safe.
"""

from __future__ import annotations

from core.messaging.schemas import AgentMessage, TaskReportPayload, TaskStatus

# iter-15: cross-product matcher replacing iter-10's
# `_MCP_RACE_PATTERNS` tuple-of-tuples. A summary matches iff
# it contains ANY MCP-naming token from `_MCP_TOKEN_SET` AND
# ANY MCP-failure verb from `_MCP_FAILURE_VERB_SET`. Both sets
# are narrow + domain-specific → near-zero false-positive
# property preserved while covering the combinatorial space
# (3 x 7 = 21 combinations from a 10-element bill of
# materials). When a future demo surfaces a new token or
# verb, add it to the relevant set (not a new tuple). See
# `iter_14_demo_report.md` "Failure 1 → option 1" for the
# design rationale.
_MCP_TOKEN_SET: frozenset[str] = frozenset(
    {
        "MCP server",
        "MCP tools",
        "mcp__ai_team_repo",
    }
)

_MCP_FAILURE_VERB_SET: frozenset[str] = frozenset(
    {
        "never connected",
        "never finished connecting",
        "still connecting",
        "unavailable",
        "not available",
        "failed to connect",
        "could not connect",
    }
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
    has_mcp_token = any(tok in summary for tok in _MCP_TOKEN_SET)
    has_failure_verb = any(verb in summary for verb in _MCP_FAILURE_VERB_SET)
    return has_mcp_token and has_failure_verb
