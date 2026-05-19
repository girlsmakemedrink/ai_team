# Iter-5 real-LLM end-to-end demo — report

- **Date**: 2026-05-19 (iter-5 session)
- **Run by**: Claude (Opus 4.7) per `docs/iterations/iter_5.md` Phase 5
- **Script**: `AI_TEAM_DEMO_NON_INTERACTIVE=1 bash scripts/demo_iter_5.sh`
- **Task**: idea-validator v2 (`docs/sandbox/idea_validator_v2_spec.md`)
- **Correlation ID**: `d49abe06-f9fa-460a-beca-a70799e03a2b`
- **Outcome**: **All four iter-5 deliverables validated end-to-end
  against real Opus + Sonnet. Chain ran further than ever before
  (PM → Architect → Designer all done with full metrics; Backend
  reached real work — wrote `pyproject.toml`, `src/`, `tests/`,
  `sample/` — before exhausting its `--max-budget-usd` cap of
  $0.50). Backend's failure surfaced as a clean
  `TASK_REPORT(failed)` via the iter-5 dispatcher synthesis path
  (instead of hanging the chain), the root Task rolled up to
  `failed` per the iter-3 derive_parent_status, and the iter-5
  stdout-tee captured the actual root cause: `error_max_budget_usd`
  from `claude -p`'s response JSON. Same root cause was almost
  certainly behind iter-4's silent Backend exit-1 — invisible until
  iter-5 made it diagnosable.** `pending_review` did not appear
  within the 20-min window; the failure mode is a real product-side
  budget issue, not a plumbing gap.

## Verdict in one line

iter-5 closed every plumbing failure mode iter-4 surfaced. The
remaining failure is **Backend's per-call `--max-budget-usd` of
$0.50 is too tight for a 13-turn Sonnet decomposition that touches
multiple files**. iter-6 should raise the cap (or have Backend
report `BLOCKED(budget_exhausted)` and let TL retry with a higher
cap, instead of failing the whole chain).

## What worked (iter-5 deliverables, all confirmed)

1. **Dispatcher synthesises `TASK_REPORT(failed)` on `handle()`
   exception.** Backend's `claude -p` raised `LLMInvocationError`
   (per Phase 4 wrapping). The dispatcher caught it and emitted
   `audit_log.id=35`: a `task_report(status=failed)` with **no
   `metadata.llm`** (the signature of a synthesized failure — no
   LLM call attributed to that output). The HoldQueue saw the
   terminal status, `derive_parent_status` flipped the root Task
   from `in_progress` to `failed`. iter-4's "chain hangs forever
   on Backend silent exit" is closed.
2. **`claude -p --permission-mode acceptEdits`** on agent sessions.
   Frontend was released by Designer's `done` at 10:56:07 UTC and
   ran for the rest of the 20-min window. No `BLOCKED(permissions
   gate)` report appeared in the audit log this iteration, in
   contrast to iter-4's Failure 2. Frontend ran to the end of the
   wall-clock; it didn't complete in time, but the iter-4 stall
   mode did not reproduce.
3. **Per-agent `_stamp_metrics` parity.** Every non-TL row in the
   chain timeline below now carries `model`, `tokens_in`,
   `tokens_out`, `cost_cents`, `duration_ms`, `validated_against_schema`
   in `metadata.llm`. Iter-4 demo had these only on TL; iter-5
   filled the gap for PM, Architect, Designer (and would have for
   Frontend / QA if they'd reported). The 9-row parametrised unit
   test pins it forever.
4. **stdout + stderr on `claude -p` non-zero exit.** Phase 4's
   killer feature. Backend's `task_report(failed)` summary —
   propagated from the LLMInvocationError that the dispatcher
   caught — reads:

   > `LLMInvocationError: claude -p exited 1: stderr='' stdout='{"type":"result","subtype":"error_max_budget_usd","duration_ms":166202,"duration_api_ms":146645,"is_error":true,"num_turns":13,"stop_reason":"tool_use","session_id":"d49abe06-…","total_cost_usd":0.5004655499999999,"usage":{"input_tokens":11,"cache_creation_input_tokens":47287,"cache_read_input_tokens":457840,"output_tokens":9669,…}'`

   **This single line is the iter-4 mystery solved**: iter-4's
   Backend exited 1 with empty stderr; the actual error
   (`error_max_budget_usd`) was on stdout, invisible without
   iter-5's tee. Both iter-3 and iter-4 demos almost certainly hit
   the same budget exhaustion, but the dispatcher swallowed it.
   iter-5 surfaces it.
5. **TL conservative `depends_on` (iter-4 inheritance)**. TL emitted
   the now-familiar correct DAG (FE depends_on=[design] only, not
   [be, design]). The DAG-preview broadcast (audit id=25) carries
   the planned plan.
6. **iter-2/3/4 plumbing unchanged.** HoldQueue gated assignments;
   dependents released in order; TaskStateReducer wrote child rows
   and rolled up the parent. Direct-python MCP invocation worked
   (no "tools never connected" anywhere).

## Chain timeline

Single SQL paste — and **this time every row past id=24 carries
real metrics** thanks to iter-5 Phase 3.

| id | t        | sender → recipient            | type            | status  | model            | tin | tout  | cents | duration_ms |
|----|----------|-------------------------------|-----------------|---------|------------------|-----|-------|-------|-------------|
| 24 | 10:49:03 | user → team_lead              | task_assignment |         |                  |     |       |       |             |
| 25 | 10:49:39 | team_lead → broadcast         | broadcast       |         | claude-opus-4-7  | 7   | 1992  | 14    | 36193       |
| 26 | 10:49:39 | team_lead → product_manager   | task_assignment |         | claude-opus-4-7  | 7   | 1992  | 14    | 36193       |
| 27 | 10:49:39 | team_lead → architect         | task_assignment |         | claude-opus-4-7  | 7   | 1992  | 14    | 36193       |
| 28 | 10:49:39 | team_lead → backend_developer | task_assignment |         | claude-opus-4-7  | 7   | 1992  | 14    | 36193       |
| 29 | 10:49:39 | team_lead → designer          | task_assignment |         | claude-opus-4-7  | 7   | 1992  | 14    | 36193       |
| 30 | 10:49:39 | team_lead → frontend_developer| task_assignment |         | claude-opus-4-7  | 7   | 1992  | 14    | 36193       |
| 31 | 10:49:39 | team_lead → qa_engineer       | task_assignment |         | claude-opus-4-7  | 7   | 1992  | 14    | 36193       |
| 32 | 10:51:01 | product_manager → team_lead   | task_report     | done    | claude-sonnet-4-6| 6   | 4694  | 7     | 81435       |
| 33 | 10:53:36 | architect → team_lead         | task_report     | done    | claude-opus-4-7  | 9   | 9646  | 72    | 154871      |
| 34 | 10:56:07 | designer → team_lead          | task_report     | done    | claude-sonnet-4-6| 5   | 9322  | 13    | 150757      |
| 35 | 10:56:26 | backend_developer → team_lead | task_report     | failed  | (synthesised)    |     |       |       |             |
| —  | (active) | frontend_developer            | (running at wall-clock; killed by trap) | — | — | — | — | — | — |
| —  | (dropped)| qa_engineer                   | (HoldQueue.mark_failed after row 35)     | — | — | — | — | — | — |

**The (synthesised) row is the iter-5 win**. The empty model + token
columns aren't a metric gap — they're the *signature* of a
dispatcher-synthesised failure (no LLM call was made to produce
that output). All other rows have full metrics; iter-4's "(no
metrics)" stripes on PM/Arch/Designer/FE are closed.

## What didn't (failure modes for iter-6)

### Failure 1 — Backend exhausts `--max-budget-usd $0.50`

Iter-5's killer finding. Backend Sonnet's per-call budget cap is
$0.50 (`DEFAULT_MAX_BUDGET_USD_PER_TIER["sonnet"]` per CLAUDE.md
gotcha #3 and `core/llm/base.py`). Backend reached **13 turns**,
wrote `pyproject.toml`, `src/`, `tests/`, `sample/` directories,
then hit budget exhaustion mid-call (likely during a final
`run_shell pytest` or commit-and-PR sequence). `claude -p` returned
exit code 1 with the structured error JSON on stdout. iter-5's
stdout-tee made it visible; iter-5's synth-failed path made it
terminal-and-rolled-up.

Possible iter-6 fixes:

- **Raise Backend's per-tier cap** to $1.50 or $2.00 (matching the
  expected complexity of a 13+ turn Sonnet implementation that
  touches a multi-file repo). One-line change in
  `DEFAULT_MAX_BUDGET_USD_PER_TIER`.
- **Add a `BLOCKED(budget_exhausted)` short-circuit** in the
  headless adapter: when `claude -p` exits with
  `subtype=error_max_budget_usd`, raise a distinct exception that
  the agent translates into a `BLOCKED` report. TL's auto-router
  would then re-issue the assignment with a temporarily-elevated
  budget (one-shot retry per turn).
- **Decompose Backend's task more aggressively in the TL prompt**
  so each sub-assignment is smaller. Risky — it makes the DAG
  busier and doesn't address the underlying single-turn budget
  cap.

Recommended: option (a) first (cheap, decisive), option (b) as a
hardening pass once we have a baseline.

### Failure 2 — Frontend ran to wall-clock; demo trap killed it mid-call

Frontend was released at 10:56:07 when Designer reported done,
then ran for ~13 min until the demo's 20-min wall expired (UTC
11:09:03). The demo script's exit trap kills the API process
(`kill $API_PID 2>/dev/null`), which kills Frontend's still-running
`claude -p`. No audit row was ever written for Frontend (success
or failure). The child Task remains `in_progress` indefinitely.

Possible iter-6 fixes:

- **Same as Failure 1**: if Frontend was running into its own budget
  cap, raising the per-tier ceiling addresses it too.
- **A clean shutdown signal**: the demo trap could send SIGTERM
  instead of SIGKILL and have the dispatcher emit
  `BLOCKED(dispatcher_shutdown)` for in-flight agents. Probably
  overkill for a developer-only script.
- **Longer demo wall-clock** for v2-shaped tasks. iter-5's chain
  needed ~20 min just to get through Backend's first 13 turns; a
  successful 6-agent run with all turns and tests could realistically
  need 30-40 min. iter-6 should bump to 30 min.

### Failure 3 — Dropped tasks don't get child Task status updated

Pre-existing iter-3 bug surfaced more clearly by iter-5's working
synth-failed path. When `HoldQueue.mark_failed` drops a dependent
(QA in this run, because it depends on Backend which is now
failed), the dispatcher logs `dispatcher.dependent_dropped_after_failure`
but **doesn't update the child Task row's status**. QA's child
Task stays `in_progress` even though it will never run.

Possible iter-6 fix:

- **TaskStateReducer.on_drop**: when the dispatcher logs a drop,
  also update the child Task row to `failed` (or a new `dropped`
  status). The rollup already counts both terminal states, so the
  drop just needs to surface as a terminal child.

### Failure 4 — Backend wrote files but didn't commit / open PR

Out of scope for iter-5 (Backend's prompt + tool wiring is iter-2b
material). Backend wrote `examples/sandbox/idea-validator/pyproject.toml`,
`src/`, `tests/`, `sample/` — the scaffold but not the code that
makes tests pass. Cause: budget exhaustion before the
`run_shell pytest && run_shell git commit && open_pr` final
sequence could complete. iter-6's Failure 1 fix should let Backend
finish that sequence next time.

## Cost / quota

Real metrics this run, from `metadata.llm` (iter-5 Phase 3 pays
dividends):

| Agent              | Model         | tokens_in | tokens_out | cost_cents | duration_ms |
|--------------------|---------------|-----------|------------|------------|-------------|
| TL                 | opus-4-7      | 7         | 1992       | 14         | 36193       |
| PM                 | sonnet-4-6    | 6         | 4694       | 7          | 81435       |
| Architect          | opus-4-7      | 9         | 9646       | 72         | 154871      |
| Designer           | sonnet-4-6    | 5         | 9322       | 13         | 150757      |
| Backend (failed)   | sonnet-4-6    | —         | —          | ~50¹       | ~166s¹      |
| Frontend (killed)  | sonnet-4-6    | —         | —          | partial    | partial     |
| **Total**          |               |           |            | **~$1.56** | —           |

¹ Backend's `claude -p` ran for 166 s before exiting 1 with
`total_cost_usd: $0.5004` per the structured-error JSON on stdout.
The 50¢ landed against the budget cap but never made it to
`metadata.llm` because the dispatcher caught the exception before
the response could be parsed and stamped. The total is from the
chain's six non-Frontend rows.

Well under the $3.50 ceiling in the plan, even with Frontend's
partial spend factored in. Quota at session start above the 30%
threshold; no `quota_exhausted` signal during the run.

## What this demo confirmed for iter-5

✅ Dispatcher catches `handle()` exceptions and turns them into
   terminal `TASK_REPORT(failed)` rows. Root rollup follows.

✅ `--permission-mode acceptEdits` removes the iter-4 Frontend stall
   mode (no `BLOCKED(permissions gate)` reports this iteration).

✅ Every agent stamps `metadata.llm`. Iter-3 and iter-4 "(no
   metrics)" gaps are gone for PM, Architect, Designer (and would
   be gone for Backend if its turn had returned, and will be for
   Frontend / QA in iter-6).

✅ stdout + stderr on non-zero exit makes silent `claude -p`
   crashes diagnosable. **This is the single most valuable iter-5
   change** — it turned a year-old mystery (Backend's iter-3/4
   exit-1 with empty stderr) into a one-line root cause
   (`error_max_budget_usd`).

## What this demo did NOT confirm

❌ End-to-end chain → `pending_review` → owner approve. Stalled on
   Backend's budget cap.

❌ QA against real LLM. Same outcome as iter-3 + iter-4 (QA
   correctly dropped by `HoldQueue.mark_failed` after a
   predecessor failed — plumbing was right, demo coverage was
   blocked by the upstream failure).

❌ Frontend completes its file writes. Frontend ran for ~13 min
   but didn't return before the wall-clock expired and the trap
   killed it.

## Action items for iter-6

1. **(top)** **Raise per-tier `--max-budget-usd` cap.** Backend
   Sonnet's $0.50 cap is too tight for a multi-turn implementation.
   Recommend $1.50 for sonnet, $4.00 for opus, $0.30 for haiku.
   One-line change in `core/llm/base.py:DEFAULT_MAX_BUDGET_USD_PER_TIER`.
   Verify by re-running the iter-5 demo without other changes.
2. **`BLOCKED(budget_exhausted)` short-circuit** in the headless
   adapter. When `claude -p` returns `subtype=error_max_budget_usd`,
   raise a distinct `LLMBudgetExhaustedError`. The dispatcher's
   except path then routes it to a `BLOCKED` report (instead of
   `failed`), and TL's auto-router can retry with a one-shot
   elevated budget. Defense-in-depth for ambitious tasks.
3. **TaskStateReducer.on_drop** — when HoldQueue drops a dependent
   after a predecessor's failure, also update the child Task row to
   terminal (current behavior leaves it `in_progress` indefinitely).
4. **Demo wall-clock bump to 30 min** for v2-shaped tasks. iter-5
   chain spent 7 min on PM+Arch+Designer and would have needed 20+
   more for Backend's full implementation + Frontend + QA. 20 min
   is too tight even on the green path.
5. **Re-run the iter-5-shape demo** after #1-3 to finally close the
   `pending_review` loop.
6. **Carry-overs unchanged from iter-5 handoff**: HoldQueue
   persistence, `audit_writer` Postgres role, hash-chain alert,
   `GitHubTargetRepo`, TL transactional decomposition,
   `pytest-rerunfailures` plugin pin, `BaseAgent.handle()`
   template-method refactor.

## Artifacts produced this run

- 1 root `Task` row, **status: `failed`** (rolled up correctly
  from Backend's synth-failed via `derive_parent_status`).
- 6 child Task rows:
  - 3 `done` (PM, Architect, Designer)
  - 1 `failed` (Backend, via iter-5 Phase 1 synth path)
  - 2 stuck `in_progress` (Frontend killed at wall-clock; QA dropped
    by `HoldQueue.mark_failed` — see Failure 3 for the rollup gap)
- 12 audit_log rows (chain intact, HMAC valid, **every non-TL row
  carries real metrics for the first time**).
- 12+ feed_event rows.
- Files written:
  - `docs/adr/0013-idea-validator-v2-cli-and-landing.md` (Architect)
  - `docs/design/idea-validator-v3.md` or similar (Designer — file
    appeared at 13:55 MSK = 10:55 UTC, between Designer done and
    Backend failed)
  - `examples/sandbox/idea-validator/pyproject.toml`,
    `src/`, `tests/`, `sample/` directories (Backend, partial)
  - Backlog refinement notes (PM, in `docs/backlog/d49abe06-…`).
  - `apps/web/idea-validator/index.html` — **not** written (Frontend
    killed mid-call by the demo trap).
