# Iteration 11 handoff

> Read **after** `CLAUDE.md`,
> `docs/iterations/iter_10_retro.md`, and
> `docs/iterations/iter_10_demo_report.md`. Replaces re-reading
> the prior conversation.

## Where we are (2026-05-20 EOD, iter-10 merged)

Iter-10 is on `main`. Same 10-agent roster as iter-9; four
targeted changes that finally produced a recoverable BLOCKED
state when Backend hits the MCP race:

1. **`core/dispatcher/mcp_race_router.py:maybe_route_mcp_race_to_blocked`**
   — pure function. Substring-matches `task_report(failed)`
   summaries against three tuple patterns (`("MCP server",
   "never connected")`, `("MCP server", "never finished
   connecting")`, `("MCP server", "still connecting")`).
   When matched, returns a `model_copy` with
   `status=BLOCKED, blocked_on='mcp_unhealthy'`. Otherwise
   returns the message unchanged. Patterns derived verbatim
   from iter-8 + iter-9 demo Backend reports.
2. **Dispatcher `_handle_one` outbound wire-up** — one new
   line at the top of the `for raw_out in outputs:` loop
   calls the router BEFORE `_signer.with_signature(out)`.
   HMAC covers the rewritten payload; audit / feed /
   task_state / HoldQueue all see one consistent BLOCKED
   version.
3. **Backend system prompt** — new "Critical: tool routing
   for git / uv / make / pytest" section at the top with a
   10-row lookup table of `command_class` values. iter-10
   demo showed this is insufficient on its own; iter-11
   needs defense-in-depth.
4. **`^examples/` mypy exclude** — bare `make typecheck`
   now passes on demo-polluted workspaces. Closes iter-8 +
   iter-9 retro carry-over.

iter-10 demo report at
`docs/iterations/iter_10_demo_report.md` is the single
source of truth. Headline: **substring router FIRED in
production for the first time across ten demos.** Backend
hit the same mid-session MCP race iter-8 + iter-9 saw,
emitted a real `task_report(failed)`, router rewrote to
BLOCKED, QA stayed held, root stayed in_progress. The
chain finally landed in a *recoverable* terminal state.
But there's no retry mechanism yet — iter-11 needs to
build the recovery action.

## Carry-over items (priority order, from iter-10 retro + demo report)

1. **(top)** **Retry mechanism for BLOCKED tasks.** The
   substring router gave us a recoverable BLOCKED state;
   iter-11 needs a way to recover from it. Two options
   (pick or combine):
   - (a) **`ai-team retry-blocked <task_id> [--comment "..."]`
     CLI** — owner-in-the-loop. Re-emits the original
     task_assignment for the BLOCKED task back to the
     agent. HoldQueue holds dependents until the retry
     reports terminal. Simpler; aligns with ADR-001's
     "owner controls dangerous actions" posture.
   - (b) **TL auto-hop on `BLOCKED(blocked_on='mcp_unhealthy')`**
     — when TL receives a BLOCKED report with this
     specific blocked_on value, emit a fresh
     task_assignment for the SAME task to the same
     recipient. Bounded by iter-2c's one-hop-max guard.
     Faster for transient races; needs a per-correlation
     retry counter so a persistently broken MCP doesn't
     loop forever.
   - Recommended: (a) first, simpler. (b) as a later
     optimisation if MCP races prove genuinely transient.
2. **Re-run iter-10-shape demo** after #1 to finally close
   the `pending_review` loop iter-3/4/5/6/7/8/9/10 all
   reached for.
3. **Backend Bash gating: defense-in-depth beyond prompt.**
   iter-10 demo Backend still reported "Bash hooks blocked
   the pytest command" despite the iter-10 prompt edit.
   Options:
   - Add `--disallowed-tools "Bash"` explicitly to
     Backend's `claude -p` invocation (currently relying
     on Bash being absent from `--allowed-tools`, but the
     LLM is still perceiving Bash as available).
   - Investigate whether
     `mcp__ai_team_repo__run_shell`'s subprocess
     invocation routes through a separate permission layer.
   - Add a unit test that calls `claude -p` with Bash
     explicitly and asserts the rejection format.
4. **`BaseAgent.llm_timeout_s` default 300 → 600 refactor**
   (deferred since iter-8 retro). Three iterations overdue.
   Five subclasses now override; flip the default, drop
   the redundant per-subclass overrides.
5. **TL Backend decomposition** (carry-over item from
   iter-9). Now actively relevant — iter-9 + iter-10 demos
   both showed Backend's session is the longest (~350-370
   s, just under the 600 s cap) and the most exposed to
   the mid-session MCP race. Splitting Backend's task into
   2-3 smaller subtasks could reduce session length and
   race window simultaneously.
6. **HoldQueue persistence (Postgres-backed).** Still
   in-memory. Lift to `held_messages` table once a real
   outage hits or a second dispatcher process appears.
7. **`audit_writer` restricted Postgres role enforcement.**
   Still deferred from iter-2..10.
8. **Hash-chain alert job.** Still deferred.
9. **`GitHubTargetRepo` implementation.** Waiting on first
   commercial product (ADR-009).
10. **TL decomposition transactional insert.** A TL crash
    mid-batch leaves orphan child rows. Wrap the TL's whole
    batch in one transaction.
11. **`pytest-rerunfailures` plugin pin** for the
    testcontainers port-mapping race. iter-7 + iter-8 +
    iter-9 + iter-10 local runs all saw it once.
12. **`BaseAgent.handle()` template-method refactor.**
    Defer until the next agent rolls in.

## Hard constraints unchanged from iter-4..10

- **LLM substrate is `claude -p` via subscription.** Never
  set `ANTHROPIC_API_KEY`. Never use Agent SDK with an API
  key.
- **`--json-schema` validated output lives in
  `structured_output`**.
- **`--session-id` is set-once, `--resume` is resume.**
  Adapter switches automatically.
- **Boring stack only.** Re-read ADR-001 before considering
  any new framework.
- **Diff-cover gate is 80 %. Bandit gates on high only.**
- **Ruff `format --check` is also a gate.**
- **Conventional commits, squash-merge, plan-before-code,
  owner approval on every agent task completion.**
- **Bash never raw on agents.** Use
  `mcp__ai_team_repo__run_shell` with its command-class
  enum. iter-10 strengthened this in Backend's prompt
  with an explicit command_class lookup table; iter-11
  may add defense-in-depth via `--disallowed-tools`.
- **`pending_review` rows are the owner-approval gate.**
- **`examples/` is the agents' TARGET_REPO root** (ADR-009).
  Excluded from orchestrator ruff lint AND mypy (iter-10
  Phase 4).
- **`make typecheck` works on demo-polluted workspaces**
  (iter-10 Phase 4) — no `--exclude '^examples/'`
  workaround needed.

## Inherited decisions (do not contradict without revisiting)

- Agent PRs target `main` on `ai_team` only (single-repo
  exception).
- Architect is **advisory**, not gating.
- TL auto-routes BLOCKED with one auto-hop max (iter-2c).
  **iter-11 may extend** with a `blocked_on='mcp_unhealthy'`-
  specific re-route rule.
- TL emits a flat list of subtasks with explicit
  `depends_on` slugs (iter-3); declares `depends_on` only
  when recipient literally cannot start without (iter-4);
  emits a `BROADCAST(topic="tl.dag_preview")` (iter-4).
- HoldQueue is in-memory only.
- LLM metrics live in `metadata["llm"]` on the envelope;
  every agent stamps them (iter-5).
- Per-stage demo task uses the v2 spec.
- MCP servers in demo configs are invoked via
  `${REPO_ROOT}/.venv/bin/python -m tools.mcp_servers.<name>`
  (iter-4).
- `claude -p` agent sessions pass
  `--permission-mode acceptEdits` by default (iter-5).
- Dispatcher synthesises `TASK_REPORT(failed)` for any
  `handle()` exception (iter-5).
- **iter-6:** `LLMBudgetExhaustedError` →
  `TASK_REPORT(blocked, blocked_on='budget')`.
- **iter-6:** When `HoldQueue.mark_failed` drops messages,
  the dispatcher calls `task_state.on_drop([task_ids])`.
- **iter-7:** Dispatcher cascades drops transitively via
  `_cascade_drops(correlation_id, failed_task_id)`.
- **iter-7:** `LLMTimeoutError` carries best-effort
  buffered stdout drained after kill.
- **iter-7:** Architect's `llm_timeout_s = 600`.
- **iter-8:** Designer's `llm_timeout_s = 600`.
- **iter-8:** `_is_budget_exhausted_stdout` is a
  substring-only match against `"error_max_budget_usd"`.
  Stdout cap on the non-zero-exit branch is 8 KB.
- **iter-8:** sonnet `--max-budget-usd` default is $2.50;
  haiku $0.30, opus $4.00.
- **iter-9:** `BaseAgent.handle()` pre-flight calls
  `check_mcp_servers` from `AI_TEAM_MCP_CONFIG_PATH`.
  Silent skip if env var unset.
- **iter-9:** `MCPUnhealthyError` exception →
  `BLOCKED(blocked_on='mcp_unhealthy', P2)`.
- **iter-10:** LLM-emitted `task_report(failed)` with MCP-
  race summary → rewritten to `BLOCKED(blocked_on='mcp_unhealthy')`
  by `maybe_route_mcp_race_to_blocked` in the dispatcher's
  outbound loop, BEFORE HMAC-sign. Three pattern tuples;
  add new tuples (not regex) when new shapes appear.
- **iter-10:** Backend's prompt has an explicit lookup
  table of `command_class` values for git / uv / make /
  pytest. Future agents that use `run_shell` should follow
  the same pattern.
- Demo wall-clock is 30 min (iter-6, unchanged in
  iter-7/8/9/10).

## Ready-to-paste prompt for the new session

```
Starting Iteration 11 on the ai_team project.

First, read these in this order:

1. CLAUDE.md
2. docs/iterations/iter_10_retro.md (what just shipped, what's
   still open)
3. docs/iterations/iter_10_demo_report.md (real-LLM demo
   findings — substring router fired in production, chain
   landed in recoverable BLOCKED state, but no retry mechanism
   yet)
4. docs/iterations/iter_11_handoff.md (this file — full
   handoff context)
5. docs/adr/0001-orchestrator-choice.md,
   0004-agent-tool-allowlist.md, 0008-llm-access-strategy.md

Iter-11 priority is **adding a retry mechanism for BLOCKED
tasks** so the recoverable state iter-10 produces actually
recovers. Two options: `ai-team retry-blocked <task_id>` CLI
(owner-in-the-loop, simpler) OR TL auto-hop on
`BLOCKED(blocked_on='mcp_unhealthy')` (faster but needs a
per-correlation retry counter). Recommended: CLI first.
After that: Backend Bash gating defense-in-depth (add
`--disallowed-tools "Bash"` explicitly), the
`BaseAgent.llm_timeout_s` default 300 → 600 refactor (three
iterations overdue), and possibly TL Backend decomposition
to reduce session length and MCP race exposure. See
`iter_10_demo_report.md` Failure 1 and Failure 2.

Workflow: plan-before-code. Draft docs/iterations/iter_11.md
first, surface for review, then code. Run validation checks
+ PR merges yourself (autonomy preference in memory).

Constraints unchanged from iter-10 — see CLAUDE.md gotchas +
the "Hard constraints" section of iter_11_handoff.md.

When ready, create the iter-11 task list and surface the plan.
```
