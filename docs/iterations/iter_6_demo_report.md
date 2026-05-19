# Iter-6 real-LLM end-to-end demo — report

- **Date**: 2026-05-19 (iter-6 session)
- **Run by**: Claude (Opus 4.7) per `docs/iterations/iter_6.md` Phase 5
- **Script**: `AI_TEAM_DEMO_NON_INTERACTIVE=1 bash scripts/demo_iter_6.sh`
- **Task**: idea-validator v2 (`docs/sandbox/idea_validator_v2_spec.md`)
- **Correlation ID**: `d209c81b-5a94-4655-a758-28961eda4e3a`
- **Outcome**: **All three iter-6 plumbing deliverables (raised
  per-tier budgets, `LLMBudgetExhaustedError` → BLOCKED synthesis,
  `TaskStateReducer.on_drop`) compiled, unit-tested, and exercised
  in-process. The real-LLM chain validated `on_drop` end-to-end —
  backend_developer and designer were dropped after architect failed,
  and iter-6's `on_drop` correctly flipped their child Task rows
  from `in_progress` → `failed`, then rolled the root up to `failed`
  via `derive_parent_status`. The chain did NOT reach
  `pending_review` because Architect's `claude -p` hit a NEW
  failure mode: `LLMTimeoutError: claude -p timed out after 300s`
  (the per-call timeout, not the budget cap iter-6 raised). Two
  derived gaps surfaced — see Failures 1 and 2 — and both inform
  iter-7's first phase.** Backend's iter-5 budget-cap problem did
  NOT recur: the chain stopped before Backend even started, on a
  different failure mode entirely.

## Verdict in one line

iter-6 closed the iter-5 cascade-drop bookkeeping gap (be + design
now terminate correctly when arch fails) but surfaced two new gaps:
**Architect's per-call timeout is too short for the v2 chain** and
**on_drop does not cascade further-downstream drops into HoldQueue**
(fe and qa remain held forever after design is dropped).

## What worked (iter-6 deliverables, two of three confirmed)

1. **Per-tier `--max-budget-usd` defaults raised.** TL ran on opus
   `$4.00`; PM ran on sonnet `$1.50`. Neither exceeded the new cap.
   Backend never ran this iteration (dropped before invocation), so
   the bump itself is unverified against a long-running Backend
   session — iter-7 demo will retest once Architect is unblocked.
2. **`LLMBudgetExhaustedError` → BLOCKED synthesis** — NOT EXERCISED
   this run. The Architect's failure mode was `LLMTimeoutError`, not
   `error_max_budget_usd`. The dispatcher's BLOCKED branch is unit-
   and integration-tested but didn't trip in this real-LLM demo.
   Iter-7 demo will likely exercise it if Backend ever runs to
   $1.50.
3. **`TaskStateReducer.on_drop` validated end-to-end.** Architect's
   real `TASK_REPORT(failed)` triggered `HoldQueue.mark_failed(arch)`,
   which dropped the held messages for `backend_developer` and
   `designer` (both `depends_on=[arch]`). The dispatcher then called
   `task_state.on_drop([be_id, design_id])`, which:
   - Flipped both child Task rows from `in_progress` → `failed`.
   - Rolled the root Task up to `failed` via `derive_parent_status`
     (any-failed dominates per iter-3 rule).
   - Pre-iter-6, both child rows would have remained `in_progress`
     indefinitely (iter-5 demo Failure 3).
4. **iter-5 deliverables held under iter-6.** Dispatcher's synth-
   failed path emitted `audit_log.id=45` (`status=failed`,
   `summary="LLMTimeoutError: claude -p timed out after 300s"`); the
   `_synthesise_failed_report` helper carried the type-name + first-
   line shape from iter-5 Phase 1. `acceptEdits` permission mode
   unchanged. Per-agent `_stamp_metrics` parity: TL/broadcast rows
   carry full metrics (37–43); PM row 44 carries full metrics; the
   synth-failed row 45 has empty metrics (signature of a synthesised
   failure — no LLM call attributed).

## Chain timeline

Single SQL paste (correlation `d209c81b-5a94-4655-a758-28961eda4e3a`):

| id | t        | sender → recipient            | type            | status | model            | tin | tout | cents | duration_ms |
|----|----------|-------------------------------|-----------------|--------|------------------|-----|------|-------|-------------|
| 36 | 11:45:53 | user → team_lead              | task_assignment |        |                  |     |      |       |             |
| 37 | 11:46:22 | team_lead → broadcast         | broadcast       |        | claude-opus-4-7  | 7   | 1669 | 12    | 29258       |
| 38 | 11:46:22 | team_lead → product_manager   | task_assignment |        | claude-opus-4-7  | 7   | 1669 | 12    | 29258       |
| 39 | 11:46:22 | team_lead → architect         | task_assignment |        | claude-opus-4-7  | 7   | 1669 | 12    | 29258       |
| 40 | 11:46:22 | team_lead → backend_developer | task_assignment |        | claude-opus-4-7  | 7   | 1669 | 12    | 29258       |
| 41 | 11:46:22 | team_lead → designer          | task_assignment |        | claude-opus-4-7  | 7   | 1669 | 12    | 29258       |
| 42 | 11:46:22 | team_lead → frontend_developer| task_assignment |        | claude-opus-4-7  | 7   | 1669 | 12    | 29258       |
| 43 | 11:46:22 | team_lead → qa_engineer       | task_assignment |        | claude-opus-4-7  | 7   | 1669 | 12    | 29258       |
| 44 | 11:48:31 | product_manager → team_lead   | task_report     | done   | claude-sonnet-4-6| 120 | 6553 | 9     | 128936      |
| 45 | 11:53:31 | architect → team_lead         | task_report     | failed | (synthesised)    |     |      |       |             |
| —  | (dropped)| backend_developer             | (HoldQueue.mark_failed after row 45) | — | — | — | — | — | — |
| —  | (dropped)| designer                      | (HoldQueue.mark_failed after row 45) | — | — | — | — | — | — |
| —  | (held)   | frontend_developer            | (still in HoldQueue waiting on dropped design) | — | — | — | — | — | — |
| —  | (held)   | qa_engineer                   | (still in HoldQueue waiting on dropped be + fe) | — | — | — | — | — | — |

TL's DAG (from audit row 37 broadcast + per-assignment `depends_on`
metadata): `pm_clarify` (no deps) → `arch` (depends_on=pm_clarify) →
{`be`, `design`} (both depends_on=arch) → `fe` (depends_on=design) →
`qa` (depends_on=[be, fe]). Correct v2 shape.

## What didn't (failure modes for iter-7)

### Failure 1 — Architect `claude -p` timed out at 300 s

**The chain's actual stopping point.** Architect's `claude -p`
exceeded the per-call timeout of 300 s (5 min). The default
`timeout_s=120` was overridden somewhere on the Architect path — the
adapter saw a `TimeoutError` from `asyncio.wait_for(...)` and raised
`LLMTimeoutError`. The synth-failed row 45 carries the message
verbatim.

Architect spent 5 min on its session — likely working on the ADR +
system design draft for v2 (the iter-5 demo's Architect took 2:34
on the same task with the same v2 scope, so this iteration's
Architect either: (a) deepened the analysis, (b) hit MCP/tool-use
roundtrips that pushed it past 300 s, or (c) was waiting on a
tool-use that never completed). Cannot disambiguate without seeing
Architect's stdout — the synth helper only captures the exception
type + first line.

Possible iter-7 fixes:

- **Raise Architect's per-call `llm_timeout_s`** to 600 s (same as
  Backend / Frontend / DevOps, which iter-2b already bumped for
  longer-running tasks). One-line per-agent override. Architect's
  ADR-writing chain is comparable in length to a Backend
  implementation.
- **Capture stdout in `LLMTimeoutError` exception messages**
  (currently the timeout path doesn't tee stdout — only the
  non-zero-exit path does). Would give iter-7+ visibility into
  what Architect was doing when the timer fired.
- **Move per-agent `llm_timeout_s` into a ClassVar default** on
  `BaseAgent` so future agents inherit a sensible long timeout
  without per-subclass touches.

Recommended: option (a) first (cheap, decisive), option (b) right
after (defense-in-depth, ~3 lines of code).

### Failure 2 — `on_drop` does not cascade drops into HoldQueue

**A pre-existing gap that iter-6's fix exposed.** When Architect
failed, the dispatcher correctly:

1. Called `HoldQueue.mark_failed(arch_task_id)` → got back held
   messages for `be` and `design`.
2. Called `task_state.on_drop([be, design])` → flipped both child
   Task rows to `failed`.
3. Root Task rolled up to `failed` (any-failed wins).

But `frontend_developer` (depends_on=[design]) and `qa_engineer`
(depends_on=[be, fe]) remained held in `HoldQueue` indefinitely:
their predecessors are now `failed` in the **Task table** but not
in the **HoldQueue's `_done`/`_held` state** (mark_failed only fires
on real `TASK_REPORT(failed)` rows, not on derived/dropped tasks).
Net effect: fe and qa stay `in_progress` forever in the tasks table
even though the root has already rolled up to `failed`.

This doesn't break the root rollup (iter-3's `derive_parent_status`
needs only one `failed` child to flip the parent), but it leaves
the `tasks` table with stale `in_progress` rows after a multi-level
cascade.

Possible iter-7 fixes:

- **Cascade drops through HoldQueue**: after `on_drop(task_ids)`
  flips child rows, also call `HoldQueue.mark_failed(...)` for each
  dropped task id. This recursively drops further-downstream
  dependents, and `on_drop` runs again on those new drops, etc.
  Cycle-safe because the same task_id can't be held twice (and
  already-terminal rows are skipped on the second `on_drop` call).
- **Synthesise a derived `TASK_REPORT(failed)` for each drop**:
  emit a synthetic terminal report from the dispatcher for each
  dropped task, routing through the same outbound pipeline. Cleaner
  in audit semantics (every terminal status has an audit row) but
  more code than option (a).

Recommended: option (a). One `for d in dropped: await
HoldQueue.mark_failed(...)` loop inside the dispatcher's drop
branch. The `on_drop` reducer already handles the resulting
recursive drops idempotently.

### Failure 3 — Backend's iter-5 budget-cap problem did NOT reproduce

This is a non-finding: the iter-6 raised cap (`sonnet: $1.50`) is
**unverified** against a long-running Backend session because
Backend never ran. The chain stopped on Architect's timeout before
Backend's hold-queue gate opened. iter-7 demo will retest the
budget bump once Architect is unblocked.

## What this demo confirmed for iter-6

✅ `TaskStateReducer.on_drop` end-to-end. Two child rows (`be`,
   `design`) correctly flipped from `in_progress` → `failed` via
   the dispatcher's `mark_failed` → `on_drop` wiring. Root Task
   rolled up to `failed` via `derive_parent_status`.

✅ iter-5 synth-failed path under a new exception type
   (`LLMTimeoutError`). The synthesised report carries the correct
   shape: `summary="LLMTimeoutError: claude -p timed out after
   300s"`, status `failed`, routes to `team_lead`. Pre-iter-5 this
   would have hung the chain.

✅ Per-agent `_stamp_metrics` parity. PM's task_report row carries
   full `metadata.llm` (model, tokens_in, tokens_out, cost_cents,
   duration_ms, validated_against_schema). Architect's synth row
   correctly has empty metrics (synthesised failure signature).

✅ Per-tier budget defaults applied. TL ran on opus `$4.00`; PM ran
   on sonnet `$1.50`. Neither exceeded.

✅ Demo wall-clock 30 min infrastructure landed. The deadline=1800
   variable is correct; the script polls every 10 s as iter-5.

## What this demo did NOT confirm

❌ End-to-end chain → `pending_review` → owner approve. Stalled on
   Architect's 300 s timeout — a NEW failure mode unrelated to
   iter-5's budget cap.

❌ `LLMBudgetExhaustedError` → BLOCKED synthesis. Architect didn't
   exhaust budget; it timed out. The BLOCKED branch is unit- and
   integration-tested but unexercised in real-LLM this run.

❌ Backend running under the raised sonnet `$1.50` cap. Backend
   never started — dropped after Architect failed.

❌ Frontend, QA against real LLM. Same posture as iter-3/4/5: held
   correctly behind dropped predecessors.

❌ `on_drop` cascade through multiple dependency levels. The
   demo's two-level cascade (design → fe; be → qa) revealed that
   `on_drop` only handles direct-predecessor drops, not transitive
   ones. See Failure 2.

## Cost / quota

Real metrics this run, from `metadata.llm`:

| Agent              | Model         | tokens_in | tokens_out | cost_cents | duration_ms |
|--------------------|---------------|-----------|------------|------------|-------------|
| TL                 | opus-4-7      | 7         | 1669       | 12         | 29258       |
| PM                 | sonnet-4-6    | 120       | 6553       | 9          | 128936      |
| Architect (timeout)| (synthesised) | —         | —          | ~$0¹       | 300000      |
| **Total**          |               |           |            | **~$0.21** | —           |

¹ Architect's `claude -p` was killed by the asyncio timeout before
the result JSON could be parsed; `total_cost_usd` from the response
was lost. Conservative estimate ~$0 to $0.10 (Opus, 5 min) but the
true cost may have been higher and counted against the
subscription quota.

Well under the $5.00 ceiling. iter-7 demo will likely spend more
once Architect runs to completion (estimate: $1.50-$2.50 total for
a full chain through QA).

## Artifacts produced this run

- 1 root `Task` row, **status: `failed`** (rolled up correctly via
  on_drop's parent-rollup path).
- 6 child Task rows:
  - 1 `done` (PM)
  - 3 `failed` (Architect via real synth, Backend + Designer via
    iter-6 `on_drop`)
  - 2 stuck `in_progress` (Frontend, QA — see Failure 2)
- 10 audit_log rows (chain intact, HMAC valid, every agent that
  reported carries real metrics).
- 10+ feed_event rows.
- Files written: none of substance. PM probably refined backlog
  notes inside its session (not yet auto-committed). Architect's
  in-flight ADR draft was killed by the timeout — partial output
  may sit on disk under `docs/adr/` or `docs/design/` but was not
  surveyed.

## Action items for iter-7

1. **(top)** **Raise Architect's per-call `llm_timeout_s` to 600 s.**
   Architect spent 300 s on the v2 ADR + system design draft and
   timed out. One-line per-agent override; matches the timeout
   already in place for Backend / Frontend / DevOps.
2. **Capture stdout in `LLMTimeoutError` exception messages.** The
   non-zero-exit path teed stdout in iter-5 Phase 4; the timeout
   path doesn't. Without it, future timeouts are diagnostic dead-
   ends.
3. **Cascade drops through HoldQueue in `on_drop`.** After
   `on_drop(task_ids)` flips child rows, also call
   `HoldQueue.mark_failed(...)` for each — recursive drops are
   idempotent. Closes Failure 2.
4. **Re-run iter-6-shape demo** after (1)+(3) to finally close the
   `pending_review` loop iter-3/4/5/6 all reached for.
5. **Carry-overs unchanged from iter-6 handoff**: HoldQueue
   persistence, `audit_writer` Postgres role, hash-chain alert,
   `GitHubTargetRepo`, TL transactional decomposition,
   `pytest-rerunfailures` plugin pin, `BaseAgent.handle()`
   template-method refactor, pre-flight MCP health-gate.

## Why this demo is still a net win

- **iter-6's three deliverables all shipped behind tests** (1 unit
  + 4 unit + 1 integration for Phase 1+2; 1 unit + 1 integration
  for Phase 3) and stay green in CI.
- **`on_drop`'s end-to-end validation closes iter-5 Failure 3.**
  Pre-iter-6, be + design would have stayed `in_progress`
  indefinitely; post-iter-6, they correctly terminate and feed
  the root rollup.
- **Architect's timeout is a new, narrower failure mode** than
  iter-5's budget exhaustion. The dispatcher caught it cleanly via
  iter-5's synth-failed path, with summary=`LLMTimeoutError: ...`
  — diagnosable without any iter-7 work.
- **The cascade-drop gap (Failure 2) is now visible** in the tasks
  table; iter-7 has a precise target instead of "the chain hangs
  somewhere."
- Total spend was ~$0.21, well under the $5.00 ceiling.

iter-6 ships with these caveats documented; iter-7's Phase 1 lands
the two follow-up fixes and re-runs the demo.
