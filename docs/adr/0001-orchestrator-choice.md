# ADR-0001 — Orchestrator choice: hybrid (custom outer + `claude -p` inner)

- **Status**: Accepted
- **Date**: 2026-05-18
- **Decision-makers**: Owner + (Architect agent once available)
- **Supersedes**: —

## Context

`ai_team` requires an orchestration substrate that supports:

- Many cooperating agents that send each other structured messages.
- Durable, replayable message history (Redis Streams) with append-only audit
  (Postgres).
- Human-in-the-loop checkpoints (`pending_review` queue) on every task
  completion, with a queryable digest for the owner.
- A live, redacted, broadcast-able feed of *all* inter-agent communication
  (`team_feed`).
- Per-agent tool allowlisting (least-privilege per [ADR-004]).
- Strict cost control under a Claude Max 5x subscription quota with **no**
  pay-as-you-go API billing as fallback (see [ADR-008]).

Three orchestrator strategies were on the table:

1. **CrewAI** — high-level multi-agent framework with its own internal
   routing, hierarchical/sequential process model, and Pydantic-typed agents.
2. **LangGraph** — explicit graph-based agent runtime with built-in
   checkpointers, human-in-the-loop interrupt patterns, and streaming.
3. **Custom minimal orchestrator** — our own Python actor system on Redis +
   Pydantic + Postgres, with `claude -p` subprocesses as the LLM substrate.

## Decision

Adopt a **hybrid** approach:

- **Outer orchestrator (custom)** — a small (~500 LOC) Python actor system in
  `core/messaging/`:
  - Redis Streams as the canonical, durable message bus (XADD / XREADGROUP).
  - Pub/Sub channel `team_feed` for live broadcast.
  - Pydantic v2 models (`AgentMessage`, see [ADR-002]) for all wire formats.
  - Postgres for state (`tasks`, `audit_log`, `feed_events`, `checkpoints`,
    `pending_reviews`).
  - FastAPI as the owner-facing entry point.
- **Inner LLM execution (`claude -p`)** — each agent's `handle()` invokes
  `claude -p` via the `LLMClient` adapter ([ADR-008]). Tool execution is
  delegated to Claude Code's native tools (Read, Write, Edit, Bash, WebFetch)
  plus our custom MCP servers (`mcp-ai-team-bus`, `mcp-ai-team-tasks`).
  We do **not** implement a tool-execution loop ourselves.

The outer orchestrator owns: routing, audit, budget, feed, human approval
queue, state machine, persistence, and replay. The inner LLM owns: reasoning
within a single turn, tool calls within `--allowed-tools` scope.

## Consequences

### Positive

- **Boring, observable foundation.** Redis + Postgres + Pydantic + FastAPI are
  all 5+-year-stable. Every message is inspectable via `psql` or `redis-cli`.
- **One canonical bus.** No risk of LangGraph state and our audit log
  disagreeing about what happened.
- **No tool-execution code to maintain.** Claude Code already implements
  Read/Write/Edit/Bash with security and editing semantics. We get them free.
- **Native subscription auth.** `claude -p` uses the same auth as interactive
  Claude Code — no API key needed (see [ADR-008]).
- **Pluggable LLM backend.** The `LLMClient` Protocol lets us swap `claude -p`
  for Claude Agent SDK (or anything else) without touching agent code.
- **Direct security review.** All cross-agent routing and audit code is ours,
  in our repo, < 1000 LOC — easy to review.

### Negative

- **Subprocess latency.** Each LLM call spawns a `claude` process. Cost on
  M-series Macs is ~0.3–0.6 s startup. We accept this — agent turns are
  rare enough that latency is dominated by the LLM call itself.
- **No native function-calling semantics.** Tools come from Claude Code +
  MCP, not from a typed Python function-calling API. Agents return
  structured JSON in their final response which we parse. This is *simpler*
  in practice but different from the `anthropic` SDK pattern.
- **We own the actor loop.** Bugs in routing/backoff/retry are on us. We
  mitigate with thorough unit tests and conservative defaults
  (`tenacity` for retries, structured logging).
- **Concurrency model is process-based, not in-process.** We can't share
  in-memory state across agent invocations. Everything goes through
  Postgres/Redis. Acceptable trade-off; in fact it's a property — agents are
  forced through the audited bus.

### Neutral

- Adds a dependency on the `claude` CLI being installed locally and on the
  Iteration 5 server. This is an acceptable runtime requirement.
- Migrating to Claude Agent SDK later is a one-class change behind the
  `LLMClient` Protocol — no churn elsewhere.

## Alternatives considered

### CrewAI (rejected)

- Internal routing competes with our Redis Streams bus → two sources of
  truth for the same messages.
- Built around in-process Python agents with the `anthropic` SDK — doesn't
  fit our `claude -p` subprocess substrate ([ADR-008]).
- Sanitizer/redaction at every hop would have to be re-implemented inside
  CrewAI's internals.
- "Boring stack" lost — CrewAI is newer than LangGraph and has had several
  breaking releases.

### LangGraph (rejected)

- Best-of-class for static graphs with checkpointing. Our domain is dynamic
  actor routing (Team Lead decides who works on what at runtime), expressed
  via `add_conditional_edges`, which works but is awkward.
- Built-in checkpointers would create a *second* persistence layer alongside
  our Postgres state — duplicated truth, harder to audit.
- LangGraph couples to LangChain primitives; we'd be plumbing `claude -p`
  through them, getting little value back.
- Acceptable fallback if our actor model breaks down at scale; revisit at
  Iteration 5 if needed.

### Pure `claude -p` with no Python orchestrator (rejected)

- No way to enforce HMAC-signed audit log, owner-token-gated entry,
  Prometheus metrics, or budget kill-switch.
- `claude` doesn't speak Redis Streams or know about our bus.
- The outer orchestrator is non-negotiable infrastructure.

## Validation

A smoke experiment in Iteration 0 (`scripts/smoke_claude_p.py`) must confirm:

- 5+ concurrent `claude -p` calls succeed without contention.
- `--allowed-tools` actually restricts available tools.
- `--output-format json` exposes accurate token usage.
- Startup latency < 3 s on owner's hardware.
- `--resume <session-id>` measurably reduces tokens on a repeated context.

If any check fails, this ADR is revisited *before* Iteration 1 begins. The
fallback is LangGraph with our Redis layer recast as a *transport* rather
than the canonical bus.

## References

- [ADR-002 — Message schema][ADR-002]
- [ADR-008 — LLM access strategy][ADR-008]
- [ADR-004 — Tool inventory][ADR-004]
- Claude Code headless mode docs (`claude -p --help`).
- LangGraph docs: https://langchain-ai.github.io/langgraph/

[ADR-002]: 0002-message-schema.md
[ADR-004]: 0004-tool-inventory.md
[ADR-008]: 0008-llm-access-strategy.md
