# ADR-0006 — Cost & context optimisation strategy

- **Status**: Accepted
- **Date**: 2026-05-18

## Context

Under the Claude Max 5x subscription, the *programmatic* budget (used by
`claude -p` and any future Agent SDK use) is capped (≈ $100/month, post
2026-06-15 split). Extra usage is disabled in the owner's account, so
exceeding the cap means the system *stops working* until the next
billing cycle.

Therefore cost is not a soft optimisation goal; it's a hard runtime
constraint. Every agent invocation must be deliberate about model
choice, context size, and caching.

## Decision

### Tiered model selection

| Tier   | Model               | Use cases                                                                                              |
|--------|---------------------|--------------------------------------------------------------------------------------------------------|
| Haiku  | `claude-haiku-4-5`  | Routing decisions, summarisation, checkpoint digests, redaction, feed-event compression, retry triage. |
| Sonnet | `claude-sonnet-4-6` | Default for all working agents (PM, Designer, BE, FE, DevOps, QA, SRE, Market).                        |
| Opus   | `claude-opus-4-7`   | Architect; Team Lead when making non-trivial decomposition or arbitration decisions.                   |

The agent class declares its default `model_tier`; specific tool calls
can up- or down-tier via `LLMClient.invoke(model=...)` if justified.
Up-tiering an "everyday" agent to Opus is a code change, not a runtime
flag — review-able.

### Prompt caching

Every `claude -p` invocation uses `--resume <session-id>` keyed on
`(agent_id, correlation_id)`. This:

- Keeps the role's system prompt and stable project context in the
  cache (avoiding repeated input tokens on every turn).
- Forms a per-task conversation thread that maps 1:1 to the bus
  correlation tree.

Cache key invalidation:

- New `correlation_id` → new session → cache cold.
- System prompt change (agent role file edited) → new session
  (sessions include the system prompt by content hash).
- Manual reset via `LLMClient.reset_session(agent_id, correlation_id)`.

### Context window management (sliding + summarisation)

When the per-session token estimate approaches 70 % of the model's
window (configurable, default Sonnet = 200k → trigger at 140k):

1. Trigger a Haiku-backed `summarise()` call over the oldest 50 % of
   the conversation.
2. Replace the summarised segment with a single condensed message tagged
   `[CONTEXT SUMMARY]`.
3. Continue with the agent's next turn.

The summariser is in `core/llm/context.py` and is unit-tested with a
fixed corpus.

### Correlation-scoped context

When an agent receives a new message, it does **not** load full bus
history. Instead, it loads:

- The current message.
- Up to N most-recent messages in the same `correlation_id`
  (default N = 10).
- A standing role-context block (the agent's own prompt + project
  invariants).

If the agent needs more history, it calls
`mcp__ai_team_bus__read_audit_log_summary(correlation_id=…, since=…)`,
which returns a Haiku-summarised digest rather than raw rows.

### Quota tracking & gates

- **Token accounting**: every `LLMClient.invoke()` returns a
  `TokensUsage{input, output, cached_input, model}` from the `usage`
  field of `claude -p --output-format json`. We sum into Prometheus
  counter `agent_llm_tokens_used_total{agent, model, tier}`.
- **Cost estimate**: a static price table per model gives
  `cost_estimate_cents` per call. Aggregated daily and shown in TL
  digests.
- **Subscription quota gauge**: `subscription_quota_used_pct`. Until we
  have a reliable API to read actual Anthropic quota, this is an
  *estimate* from our own accounting, calibrated weekly against the
  owner's Anthropic dashboard. Iteration 0 smoke test investigates
  whether a direct quota read is possible.
- **Soft warning at 70 %**: feed event + TL digest highlights what
  could be optimised (top-N agents by token spend).
- **Pause non-critical at 90 %**: regression suite, monitoring tasks,
  Market Researcher trend scans suspend. Active user tasks continue.
- **Hard stop at 100 %**: Anthropic naturally rejects calls; our wrapper
  marks the dispatcher as `quota_exhausted` and refuses to start new
  tasks until rollover (or owner upgrades the plan).

### Cost hygiene rules (enforced in code review)

- Agents must declare expected `max_turns_per_task` in their class.
  Default cap 8. Overruns → log + truncate, not retry.
- No agent may call Opus more than 3 times per `correlation_id`
  without owner approval (enforced as a counter in the LLMClient).
- System prompts must be deduplicated — they sit in `prompts/<role>.md`
  and are loaded once per session; never inlined.
- Tools that perform external fetches (`WebFetch`, MCP search) must
  return summarised content suitable for direct LLM consumption — no
  raw HTML pages of 100k tokens passed back as tool output.

## Consequences

### Positive

- Three controls (model tier, caching, summarisation) cover the
  dominant cost drivers.
- Soft → pause → stop progression gives the owner advance warning
  before the system breaks.
- Quota state is observable on the Grafana dashboard and in TL
  digests — surprise overrun is impossible.

### Negative

- Quota estimation accuracy depends on calibration; first month
  will need correction against the Anthropic dashboard.
- Summarisation introduces information loss; we mitigate with
  audit-log replay capability ([ADR-003]).
- Per-correlation sessions can fragment caching if an agent works on
  many short tasks. Acceptable; if it becomes a problem we can move
  to per-(agent × day) sessions instead.

## Alternatives considered

- **Single model everywhere (Sonnet).** Rejected — Opus is needed for
  Architect quality, Haiku saves real money on routing/summaries.
- **Anthropic prompt caching via API.** Not available via `claude -p`
  in the same form; we rely on session resumption instead, which
  produces similar economics.
- **Cost-based throttling that delays tasks.** Rejected — adds latency
  invisibly; explicit pause/stop is more honest.

## References

- [ADR-001 — Orchestrator][ADR-001]
- [ADR-008 — LLM access][ADR-008]
- [ADR-007 — Visibility][ADR-007] (TL digests surface quota state)

[ADR-001]: 0001-orchestrator-choice.md
[ADR-007]: 0007-visibility-checkpoints.md
[ADR-008]: 0008-llm-access-strategy.md
