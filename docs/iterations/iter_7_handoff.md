# Iteration 7 handoff

> Read **after** `CLAUDE.md`, `docs/iterations/iter_6_retro.md`, and
> `docs/iterations/iter_6_demo_report.md`. Replaces re-reading the
> prior conversation.

## Where we are (2026-05-19 EOD, iter-6 merged)

Iter-6 is on `main`. Same 10-agent roster as iter-5; three targeted
fixes that close the iter-5 demo's stalled-chain failure modes:

1. **Per-tier `--max-budget-usd` defaults raised** from
   `0.10 / 0.50 / 2.00` to `0.30 / 1.50 / 4.00`. Backend's iter-5
   `error_max_budget_usd` at 13 turns under $0.50 now has $1.50 of
   headroom; Architect's longer Opus sessions have $4.00 (iter-5
   used $0.72 on the same task). Unit test pins the values so
   future "tightening" surfaces in review.
2. **`LLMBudgetExhaustedError` → dispatcher `BLOCKED` synthesis.**
   When `claude -p` returns `subtype=error_max_budget_usd` on
   stdout, the adapter raises a distinct exception class. The
   dispatcher's `_synthesise_failed_report` branches on
   `isinstance(exc, LLMBudgetExhaustedError)` → emits
   `TASK_REPORT(status=BLOCKED, blocked_on='budget', priority=P2)`
   instead of the default FAILED + P1. Crucially, BLOCKED does NOT
   cascade-drop dependents (iter-3 contract) — the owner can
   manually retry with elevated budget without losing held
   downstream work.
3. **`TaskStateReducer.on_drop` terminalises dropped dependents.**
   When `HoldQueue.mark_failed` returns dropped held messages, the
   dispatcher calls `task_state.on_drop([task_ids])`. The reducer
   flips each child Task row from `in_progress` → `failed` and
   rolls parents up via `derive_parent_status`. Closes iter-5
   demo Failure 3 (QA + dropped children stuck `in_progress`
   indefinitely).

iter-6 demo report at `docs/iterations/iter_6_demo_report.md` is
the single source of truth on what worked. Headline: `on_drop`
validated end-to-end; chain still didn't reach `pending_review`
because Architect's `claude -p` hit a NEW failure mode
(`LLMTimeoutError` at 300 s).

## Carry-over items (priority order, from iter-6 retro + demo report)

1. **(top)** **Raise Architect's per-call `llm_timeout_s` to 600 s.**
   Architect's v2 ADR + system-design draft reliably takes 2-5 min;
   the default 300 s is too tight. Match Backend / Frontend /
   DevOps which iter-2b already bumped. One-line per-agent
   override.
2. **Cascade drops through HoldQueue inside `on_drop`.** After
   flipping dropped child rows to `failed`, also call
   `HoldQueue.mark_failed(...)` for each dropped task_id so
   transitive dependents (fe → qa in the v2 chain) get dropped
   too. Recursive drops are idempotent because terminal rows are
   skipped on the second `on_drop` pass. Closes iter-6 demo
   Failure 2.
3. **Capture stdout in `LLMTimeoutError` exception messages.** The
   non-zero-exit path teed stdout in iter-5 Phase 4; the timeout
   path doesn't. Future timeouts deserve the same diagnostic
   visibility — Architect's iter-6 timeout would have been
   pin-pointable if we'd seen its in-flight stdout.
4. **`tests/integration/test_task_state_reducer.py`** —
   dedicated integration tests for `on_drop`'s edge cases (no
   matching child, already-terminal, parent missing, parent
   status equal). Lifts iter-6's 68.8 % diff-cover on the reducer
   to >90 %.
5. **Re-run the iter-6-shape demo** after #1+#2 to finally close
   the `pending_review` → owner approve loop that iter-3/4/5/6
   all reached for.
6. **HoldQueue persistence (Postgres-backed).** Still in-memory.
   Lift to `held_messages` table once a real outage hits or once
   a second dispatcher process appears.
7. **`audit_writer` restricted Postgres role enforcement.** Still
   deferred from iter-2/3/4/5/6.
8. **Hash-chain alert job.** Still deferred.
9. **`GitHubTargetRepo` implementation.** Waiting on first
   commercial product (ADR-009).
10. **TL decomposition transactional insert.** A TL crash mid-batch
    leaves orphan child rows. Wrap the TL's whole batch in one
    transaction.
11. **`pytest-rerunfailures` plugin pin** for the testcontainers
    port-mapping race. Iter-6 saw it once during dispatcher
    integration tests; one retry passed. Pin the plugin and add
    `--reruns 1` for the integration suite.
12. **`BaseAgent.handle()` template-method refactor.** Iter-5
    default (a) was a per-subclass touch; if a future subclass
    adds another override, the `_stamp_metrics` discipline can
    silently regress again. Defer until a new agent rolls in.
13. **Pre-flight MCP health-gate in the dispatcher.** Iter-4
    eliminated the iter-3 MCP cold-start failure mode via
    direct-python invocation; iter-5/6 haven't seen it reappear.
    If a future demo trips on it, add a per-server `tools/list`
    ping on dispatcher startup that gates agent invocations.
14. **Per-agent `llm_timeout_s` as a `ClassVar` default on
    `BaseAgent`.** Once iter-7 raises Architect's timeout in
    addition to Backend/Frontend/DevOps, the pattern is clear and
    deserves a structural home. Saves a per-subclass touch on the
    next long-running agent.

## Hard constraints unchanged from iter-4 / iter-5 / iter-6

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
- **`pending_review` rows are the owner-approval gate.** Even when
  CI is green, an agent's `task_report` waits for `ai-team approve
  <id>`.
- **`examples/` is the agents' TARGET_REPO root** (ADR-009).
  Excluded from orchestrator ruff lint — each example project
  has its own pyproject.

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
  by default (iter-5).
- Dispatcher synthesises `TASK_REPORT(failed)` for any `handle()`
  exception (iter-5).
- **iter-6:** `LLMBudgetExhaustedError` → `TASK_REPORT(blocked,
  blocked_on='budget')` instead of `failed`. Does NOT cascade-drop.
- **iter-6:** When `HoldQueue.mark_failed` drops messages, the
  dispatcher calls `task_state.on_drop([task_ids])` to terminalise
  the dropped children. Reuses `failed`, no new `dropped` enum.
- Anti-loop guard for TL routing is summary-string check, not a
  metadata counter (iter-2c).
- Demo wall-clock is 30 min (iter-6, bumped from 20).
- Per-tier `--max-budget-usd` defaults are `haiku 0.30 / sonnet
  1.50 / opus 4.00` (iter-6).

## Ready-to-paste prompt for the new session

```
Starting Iteration 7 on the ai_team project.

First, read these in this order:

1. CLAUDE.md
2. docs/iterations/iter_6_retro.md (what just shipped, what's still open)
3. docs/iterations/iter_6_demo_report.md (real-LLM demo findings —
   Architect 300s timeout + on_drop cascade gap)
4. docs/iterations/iter_7_handoff.md (this file — full handoff context)
5. docs/adr/0001-orchestrator-choice.md, 0004-agent-tool-allowlist.md,
   0008-llm-access-strategy.md

Iter-7 priority is **raising Architect's `llm_timeout_s` to 600 s**
and **cascading drops through HoldQueue in `on_drop`** so the v2
chain can finally reach `pending_review` → owner approve. After
that, capture stdout in `LLMTimeoutError` for diagnosability, add
dedicated reducer integration tests for `on_drop` edge cases, and
re-run the iter-6-shape demo to close the loop iter-3/4/5/6 all
reached for. See `iter_6_demo_report.md` Failures 1 + 2.

Workflow: plan-before-code. Draft docs/iterations/iter_7.md first,
surface for review, then code. Run validation checks + PR merges
yourself (autonomy preference in memory).

Constraints unchanged from iter-6 — see CLAUDE.md gotchas + the
"Hard constraints" section of iter_7_handoff.md.

When ready, create the iter-7 task list and surface the plan.
```
