# Iteration 9 handoff

> Read **after** `CLAUDE.md`, `docs/iterations/iter_8_retro.md`,
> and `docs/iterations/iter_8_demo_report.md`. Replaces
> re-reading the prior conversation.

## Where we are (2026-05-19 EOD, iter-8 merged)

Iter-8 is on `main`. Same 10-agent roster as iter-7; three
targeted fixes that close the iter-7 demo's two narrow failure
modes:

1. **Designer's per-call `llm_timeout_s` raised to 600 s.**
   Matches iter-7's Architect override + Backend / Frontend /
   DevOps. Validated end-to-end: Designer's UX brief +
   wireframe completed in 138 s ($0.12), past iter-7's 300 s
   wall and well under the new 600 s.
2. **`_is_budget_exhausted_stdout` substring-only match + 8 KB
   stdout cap.** Detector now returns True if the marker
   `error_max_budget_usd` appears anywhere in the captured
   stdout, regardless of whether the surrounding JSON parses.
   Adapter's non-zero-exit stdout cap bumped 2 KB → 8 KB.
   Pinned behind 3 unit tests (flip + no-marker guard + cap
   bump). Not exercised against real-LLM this iteration —
   Backend didn't reach exhaustion (see iter-9 carry-over #2).
3. **Sonnet `--max-budget-usd` raised $1.50 → $2.50.** Pinned
   behind an updated unit test. Also not exercised against
   real-LLM — Backend spent 8 ¢ before bailing via the new MCP
   race failure mode.

iter-8 demo report at `docs/iterations/iter_8_demo_report.md`
is the single source of truth. Headline: Designer + Frontend
completed for the first time across seven demos (5 of 6 child
task rows terminal-good); chain still didn't reach
`pending_review` because Backend's `claude -p` session couldn't
connect to the `ai-team-repo` MCP server (all three ToolSearch
retries returned "still connecting"). The MCP startup race is
iter-9's load-bearing blocker.

## Carry-over items (priority order, from iter-8 retro + demo report)

1. **(top)** **Pre-flight MCP health-gate in `BaseAgent.handle()`
   (or dispatcher).** Before invoking `claude -p`, ping each
   declared MCP server (`ai-team-bus`, `ai-team-tasks`,
   `ai-team-repo`) with a no-op tool call and retry with
   exponential backoff until each responds. Bail the whole
   `handle()` with a `BLOCKED(mcp_unhealthy)` report if any
   server is still down after a bounded wait (suggested: 30 s).
   This is the load-bearing fix for iter-8's demo failure.
   Carry-over item #12 from `iter_8_handoff.md` upgraded from
   "defer" to top. Must not destroy prompt-cache savings (iter-8
   demo had 1.1 M cached input tokens on Backend's call alone
   despite the bail — keep that intact).
2. **Re-run iter-8-shape demo** after #1 to finally close the
   `pending_review` → owner approve loop iter-3/4/5/6/7/8 all
   reached for. Same 30-min wall-clock, same v2 task. If Backend
   reaches budget exhaustion this time, iter-8's Phase 2
   substring-detector + 8 KB cap finally light up against
   real-LLM.
3. **Dispatcher routing for `MCP-unhealthy` summaries.** Defense
   in depth on top of #1: when an LLM-generated
   `task_report(failed)` summary substring-matches an MCP-race
   pattern (e.g. "MCP server never finished connecting" or "all
   * retries returned 'still connecting'"), surface as BLOCKED
   rather than FAILED + cascade-drop. Covers the case where the
   race happens mid-run after a successful initial ping.
4. **`BaseAgent.llm_timeout_s` default 300 → 600 + drop
   redundant per-subclass overrides.** Five subclasses now
   override (Architect, Backend, Frontend, DevOps, Designer);
   only PM, QA, SRE, MarketResearcher, TL inherit the 300 s
   default. The override count exceeds the inheritance count
   for v2-shape tasks — flip the default and drop the now-
   redundant overrides. Carry-over item #13 from
   `iter_8_handoff.md`.
5. **Add `^examples/` to `[tool.mypy].exclude` in
   `pyproject.toml`.** Symmetric with the existing ruff
   exclusion (per CLAUDE.md / ADR-009). iter-8's demo left
   untracked `examples/sandbox/idea-validator/tests/__init__.py`,
   which collided with the project's `tests/__init__.py` and
   broke local `make typecheck`. The fix is a one-line config
   change; CI on a fresh PR checkout is unaffected, but local
   gate runs by anyone who's run a demo are.
6. **HoldQueue persistence (Postgres-backed).** Still in-memory.
   Lift to `held_messages` table once a real outage hits or a
   second dispatcher process appears.
7. **`audit_writer` restricted Postgres role enforcement.** Still
   deferred from iter-2/3/4/5/6/7/8.
8. **Hash-chain alert job.** Still deferred.
9. **`GitHubTargetRepo` implementation.** Waiting on first
   commercial product (ADR-009).
10. **TL decomposition transactional insert.** A TL crash
    mid-batch leaves orphan child rows. Wrap the TL's whole
    batch in one transaction.
11. **`pytest-rerunfailures` plugin pin** for the testcontainers
    port-mapping race. This race has bitten both iter-7 and
    iter-8 local runs — promote to a real iteration if it bites
    CI.
12. **`BaseAgent.handle()` template-method refactor.** Defer
    until the next agent rolls in.
13. **TL decomposition of Backend task** (iter-7 retro action
    item, deferred). Backend's task may be structurally too
    large for a single agent session — 5 stage modules +
    pipeline + CLI + reports + tests + scripts. Consider
    splitting into "scaffold + tests" + "stages" + "pipeline +
    CLI" as separate subtasks. Has interaction with #1: smaller
    sessions = faster MCP connect = less race risk.

## Hard constraints unchanged from iter-4 / iter-5 / iter-6 / iter-7 / iter-8

- **LLM substrate is `claude -p` via subscription.** Never set
  `ANTHROPIC_API_KEY`. Never use Agent SDK with an API key.
- **`--json-schema` validated output lives in `structured_output`**.
- **`--session-id` is set-once, `--resume` is resume.** Adapter
  switches automatically.
- **Boring stack only.** Re-read ADR-001 before considering any
  new framework.
- **Diff-cover gate is 80 %. Bandit gates on high only.**
- **Ruff `format --check` is also a gate.**
- **Conventional commits, squash-merge, plan-before-code, owner
  approval on every agent task completion.**
- **Bash never raw on agents.** Use `mcp__ai_team_repo__run_shell`
  with its command-class enum.
- **`pending_review` rows are the owner-approval gate.**
- **`examples/` is the agents' TARGET_REPO root** (ADR-009).
  Excluded from orchestrator ruff lint; iter-9 #5 adds the
  symmetric mypy exclusion.

## Inherited decisions (do not contradict without revisiting)

- Agent PRs target `main` on `ai_team` only (single-repo
  exception).
- Architect is **advisory**, not gating.
- TL auto-routes BLOCKED with one auto-hop max (iter-2c).
- TL emits a flat list of subtasks with explicit `depends_on`
  slugs (iter-3); declares `depends_on` only when recipient
  literally cannot start without (iter-4); emits a
  `BROADCAST(topic="tl.dag_preview")` (iter-4).
- HoldQueue is in-memory only.
- LLM metrics live in `metadata["llm"]` on the envelope; every
  agent stamps them (iter-5).
- Per-stage demo task uses the v2 spec.
- MCP servers in demo configs are invoked via
  `${REPO_ROOT}/.venv/bin/python -m tools.mcp_servers.<name>`
  (iter-4).
- `claude -p` agent sessions pass `--permission-mode acceptEdits`
  by default (iter-5).
- Dispatcher synthesises `TASK_REPORT(failed)` for any `handle()`
  exception (iter-5).
- **iter-6:** `LLMBudgetExhaustedError` → `TASK_REPORT(blocked,
  blocked_on='budget')` instead of `failed`.
- **iter-6:** When `HoldQueue.mark_failed` drops messages, the
  dispatcher calls `task_state.on_drop([task_ids])`. Reuses
  `failed`, no new `dropped` enum.
- **iter-7:** Dispatcher cascades drops transitively via
  `_cascade_drops(correlation_id, failed_task_id)`.
- **iter-7:** `LLMTimeoutError` carries best-effort buffered
  stdout drained after kill.
- **iter-7:** Architect's `llm_timeout_s = 600` (one-off; the
  base default + a survey of other agents lands in iter-9 per
  carry-over #4).
- **iter-8:** Designer's `llm_timeout_s = 600`.
- **iter-8:** `_is_budget_exhausted_stdout` is a substring-only
  match against `"error_max_budget_usd"` — no JSON parse
  required. Stdout cap on the non-zero-exit branch is 8 KB.
- **iter-8:** sonnet `--max-budget-usd` default is $2.50; haiku
  $0.30, opus $4.00 unchanged.
- Anti-loop guard for TL routing is summary-string check, not a
  metadata counter (iter-2c).
- Demo wall-clock is 30 min (iter-6, unchanged in iter-7 / iter-8).

## Ready-to-paste prompt for the new session

```
Starting Iteration 9 on the ai_team project.

First, read these in this order:

1. CLAUDE.md
2. docs/iterations/iter_8_retro.md (what just shipped, what's still open)
3. docs/iterations/iter_8_demo_report.md (real-LLM demo findings — MCP
   server connect race in Backend's session is iter-9's load-bearing
   blocker for the pending_review loop)
4. docs/iterations/iter_9_handoff.md (this file — full handoff context)
5. docs/adr/0001-orchestrator-choice.md, 0004-agent-tool-allowlist.md,
   0008-llm-access-strategy.md

Iter-9 priority is **adding a pre-flight MCP health-gate to
BaseAgent.handle() (or the dispatcher)** so a `claude -p` session
isn't invoked until the declared MCP servers respond, then re-running
the iter-8 demo to finally close the `pending_review` → owner approve
loop iter-3/4/5/6/7/8 all reached for. After that: an MCP-race
substring router in the dispatcher (defense in depth), the
`BaseAgent.llm_timeout_s` 300 → 600 structural refactor (5+ subclasses
now override), and the `examples/` mypy exclude one-liner. See
`iter_8_demo_report.md` Failure 1.

Workflow: plan-before-code. Draft docs/iterations/iter_9.md first,
surface for review, then code. Run validation checks + PR merges
yourself (autonomy preference in memory).

Constraints unchanged from iter-8 — see CLAUDE.md gotchas + the
"Hard constraints" section of iter_9_handoff.md.

When ready, create the iter-9 task list and surface the plan.
```
