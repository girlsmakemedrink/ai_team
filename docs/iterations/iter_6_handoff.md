# Iteration 6 handoff

> Read **after** `CLAUDE.md`, `docs/iterations/iter_5_retro.md`, and
> `docs/iterations/iter_5_demo_report.md`. Replaces re-reading the
> prior conversation.

## Where we are (2026-05-19 EOD, iter-5 merged)

Iter-5 is on `main`. Same 10-agent roster as iter-4; four targeted
fixes that close the iter-4 demo's stalled-chain failure modes:

1. **Dispatcher synthesises `TASK_REPORT(failed)` when `handle()`
   raises.** iter-4 demo's silent Backend `claude -p exited 1`
   logged a traceback but emitted nothing, so HoldQueue never saw
   a terminal status. iter-5 wires a module-level helper
   (`_synthesise_failed_report`) into the dispatcher's except
   block — the synthetic report runs through the same outbound
   pipeline as a real one (audit + feed + task-state +
   HoldQueue.mark_failed + bus), so dependents drop correctly and
   the root rolls up to `failed`.
2. **`claude -p --permission-mode acceptEdits`** on every agent
   invocation. iter-4 demo's Frontend stalled on the inner `claude
   -p`'s interactive write-approval prompt; iter-5 auto-accepts
   edits so the chain doesn't depend on a human keystroke. MCP
   path scope (AI_TEAM_PATH_PREFIXES) and dangerous-shell gating
   are unchanged — defense-in-depth.
3. **Per-agent `_stamp_metrics` parity.** All 9 subclasses that
   override `handle()` now wrap `build_outputs(...)` in
   `self._stamp_metrics(..., response)`. iter-4 demo's per-message
   SQL query had empty `metadata.llm` for 5+ rows; iter-5 closes
   that gap. Parametrised unit test pins it as a regression guard.
4. **stdout + stderr on `claude -p` non-zero exit.** iter-4 demo's
   Backend exited 1 with empty stderr. iter-5 also captures stdout
   (2 KB cap) on failure — both in the structlog event and the
   raised `LLMInvocationError` message. The next silent exit will
   be diagnosable.

Iter-5 demo report at `docs/iterations/iter_5_demo_report.md` is
the single source of truth on whether the chain finally reached
`pending_review` → owner approve.

## Carry-over items (priority order, from iter-5 retro + demo report)

1. **(top)** **Raise per-tier `--max-budget-usd` cap.** iter-5's
   stdout-tee surfaced the iter-3/4 mystery: Backend's `claude -p`
   exit-1 was `error_max_budget_usd` (budget exhausted at the
   $0.50 Sonnet default after 13 turns). One-line change in
   `core/llm/base.py:DEFAULT_MAX_BUDGET_USD_PER_TIER`. Recommended
   ceilings: haiku $0.30, sonnet $1.50, opus $4.00.
2. **`BLOCKED(budget_exhausted)` short-circuit** in the headless
   adapter. When `claude -p` returns
   `subtype=error_max_budget_usd`, raise a distinct
   `LLMBudgetExhaustedError`. The dispatcher's except path then
   routes it to a `BLOCKED` report (instead of `failed`), and TL's
   auto-router can retry with a one-shot elevated budget.
3. **TaskStateReducer.on_drop** — when `HoldQueue.mark_failed`
   drops a dependent after a predecessor's failure, also update
   the child Task row to terminal. iter-5 demo's QA task stayed
   `in_progress` indefinitely even though it will never run.
4. **Demo wall-clock bump to 30 min** for v2-shaped tasks. iter-5
   chain spent 7 min on PM+Arch+Designer alone; a full 6-agent
   run needs 30+. Update `scripts/demo_iter_6.sh` to a 1800-s
   deadline.
5. **Re-run the iter-5-shape demo** after #1-3 to finally close
   the `PM → Architect → Backend → QA → pending_review →
   owner-approve` loop iter-3/4/5 all reached for.
6. **HoldQueue persistence (Postgres-backed).** Still in-memory.
   Lift to `held_messages` table once a real outage hits or once a
   second dispatcher process appears.
7. **`audit_writer` restricted Postgres role enforcement.** Still
   deferred from iter-2/3/4.
8. **Hash-chain alert job.** Still deferred.
9. **`GitHubTargetRepo` implementation.** Waiting on first
   commercial product (ADR-009).
10. **TL decomposition transactional insert.** A TL crash mid-batch
    leaves orphan child rows. Wrap the TL's whole batch in one
    transaction.
11. **`pytest-rerunfailures` plugin pin** for the testcontainers
    port-mapping race. Iter-5 saw it twice (30 errors → second
    run all 30 passed). Pin the plugin and add `--reruns 1` for the
    integration suite.
12. **`BaseAgent.handle()` template-method refactor.** iter-5
    default (a) was a per-subclass touch; if a future subclass adds
    another override, the `_stamp_metrics` discipline can silently
    regress again. The template-method refactor is the structural
    fix; defer until the next agent rolls in.
13. **Pre-flight MCP health-gate in the dispatcher.** Iter-4
    eliminated the iter-3 MCP cold-start failure mode via direct-
    python invocation; iter-5 hasn't seen it reappear. If a future
    demo trips on it, add a per-server `tools/list` ping on
    dispatcher startup that gates agent invocations.

## Hard constraints unchanged from iter-4 / iter-5

- **LLM substrate is `claude -p` via subscription.** Never set
  `ANTHROPIC_API_KEY`. Never use Agent SDK with an API key.
- **`--json-schema` validated output lives in `structured_output`**.
- **`--session-id` is set-once, `--resume` is resume.** Adapter
  switches automatically.
- **Boring stack only.** Re-read ADR-001 before considering any
  new framework.
- **Diff-cover gate is 80 %. Bandit gates on high only.**
- **Ruff `format --check` is also a gate.** Iter-4's CI miss made
  this explicit; iter-5 plan called it out as a Phase 6 step.
- **Conventional commits, squash-merge, plan-before-code, owner
  approval on every agent task completion.**
- **Bash never raw on agents.** Use `mcp__ai_team_repo__run_shell`
  with its command-class enum.
- **`pending_review` rows are the owner-approval gate.** Even when
  CI is green, an agent's `task_report` waits for `ai-team approve
  <id>`.

## Inherited decisions (do not contradict without revisiting)

- Agent PRs target `main` on `ai_team` only (single-repo exception).
- Architect is **advisory**, not gating.
- TL auto-routes BLOCKED with one auto-hop max (iter-2c).
- TL emits a flat list of subtasks with explicit `depends_on`
  slugs (iter-3); declares `depends_on` only when recipient
  literally cannot start without (iter-4); emits a
  `BROADCAST(topic="tl.dag_preview")` (iter-4).
- HoldQueue is in-memory only.
- LLM metrics live in `metadata["llm"]` on the envelope; every
  agent stamps them (iter-5).
- Per-stage demo task uses the v2 spec
  (`docs/sandbox/idea_validator_v2_spec.md`).
- MCP servers in demo configs are invoked via
  `${REPO_ROOT}/.venv/bin/python -m tools.mcp_servers.<name>`
  (iter-4), not `uv run python -m …`.
- `claude -p` agent sessions pass `--permission-mode acceptEdits`
  by default (iter-5). Override per-call only if a test needs the
  legacy interactive mode.
- Dispatcher synthesises `TASK_REPORT(failed)` for any `handle()`
  exception (iter-5). The except path is no longer silent.
- Anti-loop guard for TL routing is summary-string check, not a
  metadata counter (iter-2c).

## Ready-to-paste prompt for the new session

```
Starting Iteration 6 on the ai_team project.

First, read these in this order:

1. CLAUDE.md
2. docs/iterations/iter_5_retro.md (what just shipped, what's still open)
3. docs/iterations/iter_5_demo_report.md (real-LLM demo findings)
4. docs/iterations/iter_6_handoff.md (this file — full handoff context)
5. docs/adr/0001-orchestrator-choice.md, 0004-agent-tool-allowlist.md,
   0008-llm-access-strategy.md

Iter-6 priority is **raising `--max-budget-usd` per-tier caps** so
Backend's `claude -p` stops hitting the $0.50 ceiling 13 turns in.
After that, layer `BLOCKED(budget_exhausted)` short-circuit + the
`on_drop` rollup fix, then re-run the demo to finally close the
`pending_review` → owner approve loop iter-3/4/5 all reached for.
See `iter_5_demo_report.md` Failure 1.

Workflow: plan-before-code. Draft docs/iterations/iter_6.md first,
surface for review, then code. Run validation checks + PR merges
yourself (autonomy preference in memory).

Constraints unchanged from iter-5 — see CLAUDE.md gotchas + the
"Hard constraints" section of iter_6_handoff.md.

When ready, create the iter-6 task list and surface the plan.
```
