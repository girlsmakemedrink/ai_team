# ADR-0008 — LLM access strategy

- **Status**: Accepted
- **Date**: 2026-05-18

## Context

**Hard constraint, set by owner**: all LLM access must go through the
Claude Max 5x subscription. No separate Anthropic API key. No
pay-as-you-go billing. After the 2026-06-15 interactive/programmatic
split, Max 5x grants ≈ $100/month programmatic budget; extra usage is
explicitly disabled in the owner's Anthropic account, providing a hard
natural ceiling.

This rules out the obvious "use the `anthropic` Python SDK" architecture
that most multi-agent frameworks expect (CrewAI, LangGraph, etc.). We
need a substrate that authenticates via the existing Claude Code (CLI)
session.

Options surveyed:

1. **`claude -p` (Claude Code headless mode)** — official, subprocess
   interface, supports `--system-prompt`, `--allowed-tools`,
   `--output-format json`, `--model`, `--resume <session>`. Uses the
   same subscription auth as interactive Claude Code.
2. **Claude Agent SDK** — Python SDK released by Anthropic for building
   agents. Currently configured for API-key auth; subscription-auth
   support is on the roadmap but not confirmed available to us today.
3. **HTTP wrapper around `claude` CLI** — unnecessary indirection.

We pick (1) for primary, and design an interface that makes
swapping in (2) a one-class change once it supports subscription auth.

## Decision

Introduce a tiny `LLMClient` Protocol in `core/llm/` with three
implementations: `ClaudeCodeHeadlessClient` (primary),
`ClaudeAgentSDKClient` (stub), `MockLLMClient` (tests). Every agent's
`handle()` calls `LLMClient.invoke(...)`. No agent code touches a
subprocess directly.

### Interface

```python
# core/llm/base.py

class TokensUsage(BaseModel):
    input: int
    output: int
    cached_input: int = 0
    model: str

class ToolUse(BaseModel):
    name: str
    input: dict[str, Any]
    output_summary: str | None

class LLMResponse(BaseModel):
    text: str                           # final assistant text
    structured: dict | None             # parsed JSON if agent emitted JSON
    tools_used: list[ToolUse]
    session_id: str                     # for --resume
    tokens: TokensUsage
    cost_estimate_cents: int
    duration_ms: int
    raw: dict                           # full claude -p JSON for debugging

class LLMClient(Protocol):
    async def invoke(
        self,
        *,
        system_prompt: str,
        user_message: str,
        model: Literal["haiku", "sonnet", "opus"] = "sonnet",
        allowed_tools: Sequence[str] = (),
        disallowed_tools: Sequence[str] = (),
        session_id: str | None = None,
        mcp_servers: Sequence[str] = (),
        timeout_s: int = 120,
        max_turns: int = 8,
    ) -> LLMResponse: ...

    async def reset_session(self, session_id: str) -> None: ...
```

### `ClaudeCodeHeadlessClient` (primary)

- Builds command:
  `claude -p <prompt> --output-format json --system-prompt-file <tmp> --allowed-tools <list> --disallowed-tools <list> --model <model-id> [--resume <sid>] [--mcp-config <file>]`
- `system_prompt` is written to a temp file (not exposed on command line — avoids
  shell-escape pitfalls and length limits).
- Spawn via `asyncio.create_subprocess_exec`. Read full stdout (JSON).
  stderr goes to structured log.
- Parse `usage` from JSON → `TokensUsage`. Compute `cost_estimate_cents`
  from a static price table per model.
- `session_id` propagated from response so the next call with the same
  `(agent_id, correlation_id)` resumes the cache.
- Timeout enforced via `asyncio.wait_for`; on timeout we `proc.kill()`
  and raise `LLMTimeoutError`.
- All invocations and outcomes logged to `structlog` with structured
  fields including `agent`, `model`, `tokens.*`, `duration_ms`.

Model ID mapping (configurable via env, defaults in `.env.example`):

| Tier   | Default model ID    |
|--------|---------------------|
| Haiku  | `claude-haiku-4-5`  |
| Sonnet | `claude-sonnet-4-6` |
| Opus   | `claude-opus-4-7`   |

### `ClaudeAgentSDKClient` (stub)

```python
class ClaudeAgentSDKClient:
    async def invoke(self, **kwargs) -> LLMResponse:
        raise NotImplementedError(
            "Agent SDK backend pending subscription-auth support. "
            "Tracking: https://github.com/anthropics/claude-code/issues/<TODO>"
        )
```

Re-enabled when Anthropic ships subscription-mode auth for the SDK and we
verify it counts against the same Max 5x programmatic quota.

### `MockLLMClient` (tests)

- Returns canned responses keyed by `sha256(system_prompt || user_message)`.
- Fixture corpus in `tests/fixtures/llm_responses/<role>/<sha>.json`.
- New tests record live responses once (under `--real-llm`) and replay
  thereafter (cassettes).
- Used by every unit and integration test by default.

### Custom MCP servers

`claude -p` is told about our MCP servers via `--mcp-config <file>`
pointing to JSON like:

```json
{
  "mcpServers": {
    "ai-team-bus":   { "command": "uv", "args": ["run", "python", "-m", "tools.mcp_servers.ai_team_bus"] },
    "ai-team-tasks": { "command": "uv", "args": ["run", "python", "-m", "tools.mcp_servers.ai_team_tasks"] }
  }
}
```

Tools surface to the agent as `mcp__ai_team_bus__publish_message`, etc.
The `allowed_tools` list in `LLMClient.invoke()` controls which tools
(native + MCP) the agent can use this turn.

### Smoke validation (Iteration 0)

`scripts/smoke_claude_p.py` is a required Iteration-0 deliverable. It
verifies:

| Property                                           | Threshold                                     |
|----------------------------------------------------|-----------------------------------------------|
| Concurrent invocations (5 in parallel)             | All succeed, no contention                    |
| `--allowed-tools` actually restricts tool use      | Forbidden tool unavailable to model           |
| `usage` field present and numeric in JSON output   | `tokens.input` and `tokens.output` both > 0   |
| Cold-start latency p50 / p99                       | < 3 s / < 6 s on owner's hardware             |
| `--resume` caching savings on repeated context     | ≥ 30 % input-token reduction on second turn   |
| MCP server discoverable and callable               | Stub tool returns expected payload            |

Report written to `docs/iterations/iter_0_smoke_report.md`. If any
threshold misses, this ADR is revisited *before* Iteration 1 (the
fallback is to revisit ADR-001 and consider Claude Agent SDK with API-key
billing as a Phase-2 option — which the owner has ruled out, so we'd
need to discuss).

## Consequences

### Positive

- Single hard constraint (subscription only) directly modelled in the
  architecture rather than worked around.
- Adapter pattern lets us migrate to Agent SDK without churn elsewhere.
- Tool execution is delegated to a battle-tested CLI (Claude Code) —
  we don't reinvent file editing or shell sandboxing.
- Per-call `usage` reporting gives accurate cost telemetry.

### Negative

- Subprocess startup overhead (~300–600 ms). Acceptable; the LLM call
  itself dominates wall-clock.
- We're coupled to `claude` CLI being installed and authenticated. The
  Iteration 5 server provisioning includes installing it.
- Structured "function-calling" semantics are different: we ask agents
  to emit final JSON in their response text and parse it, rather than
  using native `tool_use` blocks. Has worked well in production
  elsewhere; if it becomes problematic we can layer a small parser
  with re-prompt-on-error.

### Neutral

- The mock-based test suite is fast and free; CI's standard PR check
  stays under a minute. The cost of real-LLM testing is bounded by the
  `make test-real-llm` workflow's quota check (skips if < 10 %
  remaining).

## Alternatives considered

- **Anthropic Python SDK with API key.** Rejected by owner — violates
  subscription-only constraint.
- **Wrap `claude` in an HTTP daemon.** Rejected — unnecessary
  indirection.
- **Build agents inside Claude Code itself (custom slash commands).**
  Considered, but doesn't give us the audited message bus, Postgres
  state, or human approval queue.

## References

- [ADR-001 — Orchestrator][ADR-001]
- [ADR-004 — Tool inventory][ADR-004]
- [ADR-006 — Cost optimisation][ADR-006]
- Claude Code headless docs (`claude -p --help`).
- Claude Agent SDK: https://docs.claude.com/en/api/agent-sdk

[ADR-001]: 0001-orchestrator-choice.md
[ADR-004]: 0004-tool-inventory.md
[ADR-006]: 0006-cost-context-optimization.md
