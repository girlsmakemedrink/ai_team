# Iteration 8 handoff

> Read **after** `CLAUDE.md`, `docs/iterations/iter_7_retro.md`, and
> `docs/iterations/iter_7_demo_report.md`. Replaces re-reading the
> prior conversation.

## Where we are (2026-05-19 EOD, iter-7 merged)

Iter-7 is on `main`. Same 10-agent roster as iter-6; three
targeted fixes that close the iter-6 demo's stalled-chain
failure modes:

1. **Architect's per-call `llm_timeout_s` raised to 600 s.**
   Matches Backend / Frontend / DevOps. Validated end-to-end:
   Architect's v2 ADR + system-design draft completed in 318 s
   ($1.77), past the iter-6 300 s wall and well under the new
   600 s.
2. **`LLMTimeoutError` carries buffered stdout.** Drain pattern
   after `proc.kill()` + `proc.wait()`. Drain failure is
   non-fatal — degrades to an empty buffer with a
   `llm.invoke.timeout.drain_failed` warning. iter-5 Phase 4
   parity for the timeout path. The field is now always present
   even when empty.
3. **Dispatcher cascades drops through HoldQueue (transitive).**
   Extracted `_cascade_drops(correlation_id, failed_task_id)` —
   queue-driven loop where every dropped task_id becomes a new
   failure trigger. Cycle-safe via HoldQueue's strictly-shrinking
   `_held` state and `on_drop`'s terminal-row guard. iter-6
   demo's fe + qa stuck `in_progress` after `design` was dropped
   is closed: Frontend + QA now correctly terminate.

iter-7 demo report at `docs/iterations/iter_7_demo_report.md`
is the single source of truth. Headline: Architect completed for
the first time across six demos; chain still didn't reach
`pending_review` — two narrow new failure modes (Designer 300 s
timeout, BLOCKED detector defeated by stdout truncation).

## Carry-over items (priority order, from iter-7 retro + demo report)

1. **(top)** **Bump Designer's `llm_timeout_s` to 600 s.** Same
   one-line fix as iter-7's Architect; same failure mode the
   iter-7 demo Designer hit. PM + QA may also need it for v2-
   shape tasks — survey at the same time. Consider lifting
   `BaseAgent.llm_timeout_s` default from 300 → 600 since 5+
   subclasses now override.
2. **Fix `_is_budget_exhausted_stdout` against truncated JSON.**
   Substring match alone (without requiring full JSON parse)
   plus a stdout-cap bump to 8 KB for diagnostic richness.
   iter-6's BLOCKED branch failed its first real-LLM test
   because the adapter's 2 KB stdout cap truncated the JSON the
   detector tries to parse — fell through to `LLMInvocationError
   → FAILED → cascade-drop` instead of `BLOCKED → owner manual
   retry`. Also flip the iter-6
   `test_is_budget_exhausted_stdout_robust_against_truncated_json`
   assertion: the new contract is "True on truncated JSON if
   marker present."
3. **Modest sonnet budget bump to $2.50.** Backend hit $1.50
   cap at 11 turns; $2.50 gives ~18 turns of headroom. Pair
   with #2 so a real exhaustion routes to BLOCKED + owner
   manual retry rather than FAILED + cascade-drop.
4. **Re-run iter-7-shape demo** after #1-3 to finally close the
   `pending_review` → owner approve loop that iter-3/4/5/6/7
   all reached for.
5. **HoldQueue persistence (Postgres-backed).** Still in-memory.
   Lift to `held_messages` table once a real outage hits or
   once a second dispatcher process appears.
6. **`audit_writer` restricted Postgres role enforcement.** Still
   deferred from iter-2/3/4/5/6/7.
7. **Hash-chain alert job.** Still deferred.
8. **`GitHubTargetRepo` implementation.** Waiting on first
   commercial product (ADR-009).
9. **TL decomposition transactional insert.** A TL crash
   mid-batch leaves orphan child rows. Wrap the TL's whole batch
   in one transaction.
10. **`pytest-rerunfailures` plugin pin** for the testcontainers
    port-mapping race.
11. **`BaseAgent.handle()` template-method refactor.** Defer
    until the next agent rolls in.
12. **Pre-flight MCP health-gate in the dispatcher.** Defer until
    a future demo trips on it.
13. **`BaseAgent.llm_timeout_s` default 300 → 600.** Five
    subclasses now override (Architect, Backend, Frontend,
    DevOps, plus iter-8's incoming Designer). When the override
    count exceeds the inheritance count, the default should
    shift. Either iter-8 Phase 1 (alongside Designer) or iter-9.

## Hard constraints unchanged from iter-4 / iter-5 / iter-6 / iter-7

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
  Excluded from orchestrator ruff lint.

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
  blocked_on='budget')` instead of `failed` (BUT: detector
  currently broken for real-LLM truncated JSON — iter-8 #2 fixes).
- **iter-6:** When `HoldQueue.mark_failed` drops messages, the
  dispatcher calls `task_state.on_drop([task_ids])`. Reuses
  `failed`, no new `dropped` enum.
- **iter-7:** Dispatcher cascades drops transitively via
  `_cascade_drops(correlation_id, failed_task_id)`.
- **iter-7:** `LLMTimeoutError` carries best-effort buffered
  stdout drained after kill.
- **iter-7:** Architect's `llm_timeout_s = 600` (one-off; the
  base default + a survey of other agents lands in iter-8).
- Anti-loop guard for TL routing is summary-string check, not a
  metadata counter (iter-2c).
- Demo wall-clock is 30 min (iter-6, unchanged in iter-7).
- Per-tier `--max-budget-usd` defaults are `haiku 0.30 / sonnet
  1.50 / opus 4.00` (iter-6; sonnet likely bumps to 2.50 in
  iter-8 #3).

## Ready-to-paste prompt for the new session

```
Starting Iteration 8 on the ai_team project.

First, read these in this order:

1. CLAUDE.md
2. docs/iterations/iter_7_retro.md (what just shipped, what's still open)
3. docs/iterations/iter_7_demo_report.md (real-LLM demo findings — Designer
   timeout + BLOCKED detector bug)
4. docs/iterations/iter_8_handoff.md (this file — full handoff context)
5. docs/adr/0001-orchestrator-choice.md, 0004-agent-tool-allowlist.md,
   0008-llm-access-strategy.md

Iter-8 priority is **bumping Designer's `llm_timeout_s` to 600s** and
**fixing _is_budget_exhausted_stdout against truncated JSON** so the
iter-6 BLOCKED branch finally fires on real claude -p exhaustion.
After that, modest sonnet cap bump to $2.50 and re-run the iter-7
demo to finally close the `pending_review` loop iter-3/4/5/6/7 all
reached for. See `iter_7_demo_report.md` Failures 1 and 2.

Workflow: plan-before-code. Draft docs/iterations/iter_8.md first,
surface for review, then code. Run validation checks + PR merges
yourself (autonomy preference in memory).

Constraints unchanged from iter-7 — see CLAUDE.md gotchas + the
"Hard constraints" section of iter_8_handoff.md.

When ready, create the iter-8 task list and surface the plan.
```
