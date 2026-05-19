# Iter-7 real-LLM end-to-end demo — report

- **Date**: 2026-05-19 (iter-7 session)
- **Run by**: Claude (Opus 4.7) per `docs/iterations/iter_7.md` Phase 6
- **Script**: `AI_TEAM_DEMO_NON_INTERACTIVE=1 bash scripts/demo_iter_7.sh`
- **Task**: idea-validator v2 (`docs/sandbox/idea_validator_v2_spec.md`)
- **Correlation ID**: `b85b54ff-a751-4cfb-a4ba-ab0fc81c9fc2`
- **Outcome**: **All three iter-7 plumbing deliverables (Architect
  `llm_timeout_s` = 600 s, `LLMTimeoutError` stdout capture,
  transitive drop cascade through HoldQueue) validated end-to-end.
  The chain ran further than ever before: PM done, Architect done
  (ADR-0014 written, $1.77, 5:18 — would have timed out at 300 s
  pre-iter-7), Designer failed (timeout at 300 s — same failure
  mode that previously hit Architect; Designer didn't get the
  per-agent bump this iteration), Backend failed (`claude -p`
  budget exhausted at 11 turns under sonnet $1.50, total
  `total_cost_usd=$1.50`). iter-7's transitive cascade fix
  validated end-to-end too: Frontend (depends_on=design) and QA
  (depends_on=[be, fe]) correctly terminated via `on_drop` →
  HoldQueue cascade — both would have stayed `in_progress`
  pre-iter-7.** Chain did NOT reach `pending_review` — Designer
  needs the same 600 s bump Architect got, and iter-6's
  `LLMBudgetExhaustedError` BLOCKED detector failed to trigger
  because the 2000-byte stdout cap truncated the JSON the
  detector tries to parse. Both inform iter-8.

## Verdict in one line

iter-7 closed iter-6's transitive-drop gap (fe + qa now terminate)
and the Architect 300 s timeout, but surfaced two more narrow
failure modes: **Designer also needs `llm_timeout_s=600`** and
**`_is_budget_exhausted_stdout` doesn't tolerate the
2000-byte-truncated JSON the adapter actually produces** (real
budget exhaustion routed to `LLMInvocationError → FAILED` instead
of `LLMBudgetExhaustedError → BLOCKED`).

## What worked (iter-7 deliverables, all three confirmed)

1. **Architect's per-call `llm_timeout_s = 600 s`** validated. ADR
   writing took 318 s (5:18) — comfortably past the old 300 s
   cap, well under the new 600 s. `total_cost_usd=$1.77` against
   the $4.00 opus budget. Audit row 55 carries full metrics.
2. **`LLMTimeoutError` carries buffered stdout.** Designer timed
   out at 300 s; the synth-failed report summary reads
   `LLMTimeoutError: claude -p timed out after 300s; stdout=''`.
   The `stdout=''` is empty because Designer hadn't flushed any
   output yet (300 s into an interactive session), but the field
   is present and would carry diagnostic data when the process
   has buffered output. iter-5 Phase 4 parity for the timeout
   path achieved.
3. **Transitive drop cascade through HoldQueue.** Designer's
   FAILED dropped Frontend (depends_on=[design]) via the
   dispatcher's queue-driven loop; Backend's FAILED dropped QA
   (depends_on=[be, fe]). Both child Task rows correctly flipped
   to `failed` via `on_drop`. Pre-iter-7, fe + qa would have
   stayed `in_progress` indefinitely (iter-6 demo Failure 2).
   Root rolled up to `failed` via `derive_parent_status`.

## What didn't (failure modes for iter-8)

### Failure 1 — Designer also needs `llm_timeout_s=600`

Designer's `claude -p` timed out at 300 s on the v2 UX brief +
landing-page wireframe task. Same failure mode that hit Architect
in iter-6; iter-7's fix only bumped Architect. iter-8 should bump
Designer to 600 s (and probably PM too as a defense-in-depth pass,
since PM did its work in 215 s this run — comfortably under 300 s,
but tight for a more ambitious v3 task).

Possible iter-8 fix:

- **Add `llm_timeout_s: ClassVar[int] = 600` to Designer.** One
  line. Maybe also PM, Architect (already done), QA. SRE/Support
  + MarketResearcher can stay at 300 s — their work is bounded.
- **Better: lift the default in `BaseAgent` from 300 → 600.**
  Five subclasses already explicitly override; if a sixth needs
  600, the per-subclass overrides become noise. Carry-over
  item #14 from iter-7 handoff captures this.

Recommended: bump Designer to 600 first (one-liner like iter-7
Phase 1), then survey whether the BaseAgent default should also
shift in iter-8 or iter-9.

### Failure 2 — `_is_budget_exhausted_stdout` defeated by 2000-byte truncation

Backend hit `error_max_budget_usd` at 11 turns under the
iter-6-raised sonnet $1.50 cap (`total_cost_usd=$1.5040`). The
synth-failed report shows the error JSON correctly:

> `LLMInvocationError: claude -p exited 1: stderr='' stdout='{"type":"result","subtype":"error_max_budget_usd","duration_ms":341973,...`

But the synth helper emitted `status=failed`, not
`status=blocked`. This means iter-6's
`LLMBudgetExhaustedError` → BLOCKED branch did NOT fire on a real
`error_max_budget_usd` event — its first real-LLM test.

Root cause: `core/llm/claude_code_headless.py` caps stdout at
2000 chars before calling `_is_budget_exhausted_stdout(out)`. The
detector requires a complete `json.loads(out)` parse — the
substring match passes, but the JSON parse fails on the
truncated object, returning False. The adapter falls through to
`LLMInvocationError`, and the dispatcher routes it to FAILED
(cascade-drops dependents) instead of BLOCKED (holds them for
manual retry).

Real consequence: Backend's failure cascade-dropped QA (via
HoldQueue.mark_failed) instead of leaving QA held for owner
retry. The unit test
`test_is_budget_exhausted_stdout_robust_against_truncated_json`
(iter-6 Phase 6) pinned the False-on-truncation behavior — but
proved a "feature" that's actually a bug.

Possible iter-8 fixes:

- **Substring-match the marker alone**: if `"error_max_budget_usd"
  in out`, raise `LLMBudgetExhaustedError` without requiring a
  successful JSON parse. Robust to truncation; false-positive
  risk is near-zero because the marker is a structured response
  field, not natural-language text.
- **Bump the stdout cap** to 8 KB or 16 KB. Memory cost is
  trivial. Doesn't help if a real future error JSON exceeds 16
  KB, so iter-8 should also do option (a).
- **Best: both.** Substring detector is the load-bearing fix;
  larger cap is defense-in-depth + better diagnostics in logs.

Recommended: (a) + (b) together in iter-8 Phase 1.

### Failure 3 — sonnet $1.50 cap still too tight for v2 Backend

Backend ran 11 turns, wrote `pyproject.toml`, `src/`, `tests/`,
and was deep into implementation when budget ran out at
`total_cost_usd=$1.5040`. iter-5 demo hit the $0.50 cap at 13
turns; iter-6 raised to $1.50; iter-7 hit it at 11 turns. The
pattern: Backend gets within striking distance every iteration
and runs out. iter-8 could:

- **Raise sonnet cap to $3.00.** Doubles iter-7's cap; gives
  Backend ~20 turns of room. Cost concern: a runaway loop hits
  $3.00 ceiling per agent per call.
- **Decompose the Backend task more aggressively.** TL prompt
  changes — split into "scaffold + tests" + "implement happy
  path" + "implement edge cases" as separate subtasks.
- **Wait for the BLOCKED detector fix (iter-8 Phase 1)** and let
  the owner manually re-issue with a one-shot elevated budget.
  Lowest cost ceiling, slowest path to closing the loop.

Recommended: combine (a) modest bump to $2.50 + the BLOCKED
detector fix. Aggressive decomposition is iter-9+ if needed.

## Chain timeline

Single SQL paste (correlation `b85b54ff-a751-4cfb-a4ba-ab0fc81c9fc2`):

| id | t        | sender → recipient            | type            | status | model            | cents | duration_ms |
|----|----------|-------------------------------|-----------------|--------|------------------|-------|-------------|
| 46 | 12:46:33 | user → team_lead              | task_assignment |        |                  |       |             |
| 47 | 12:47:04 | team_lead → broadcast         | broadcast       |        | claude-opus-4-7  | 13    | 31845       |
| 48 | 12:47:04 | team_lead → product_manager   | task_assignment |        | claude-opus-4-7  | 13    | 31845       |
| 49 | 12:47:05 | team_lead → architect         | task_assignment |        | claude-opus-4-7  | 13    | 31845       |
| 50 | 12:47:05 | team_lead → backend_developer | task_assignment |        | claude-opus-4-7  | 13    | 31845       |
| 51 | 12:47:05 | team_lead → designer          | task_assignment |        | claude-opus-4-7  | 13    | 31845       |
| 52 | 12:47:05 | team_lead → frontend_developer| task_assignment |        | claude-opus-4-7  | 13    | 31845       |
| 53 | 12:47:05 | team_lead → qa_engineer       | task_assignment |        | claude-opus-4-7  | 13    | 31845       |
| 54 | 12:50:40 | product_manager → team_lead   | task_report     | done   | claude-sonnet-4-6| 20    | 215787      |
| 55 | 12:55:58 | architect → team_lead         | task_report     | done   | claude-opus-4-7  | 177   | 318088      |
| 56 | 13:00:59 | designer → team_lead          | task_report     | failed | (synthesised)    |       |             |
| 57 | 13:01:44 | backend_developer → team_lead | task_report     | failed | (synthesised)    |       |             |
| —  | (dropped)| frontend_developer            | (via on_drop after design failed)        | — | — | — | — |
| —  | (dropped)| qa_engineer                   | (via on_drop transitively after fe + be) | — | — | — | — |

The `(synthesised)` rows for Designer (id=56) and Backend (id=57)
carry the dispatcher's exception type + first line per iter-5
Phase 1. Empty metrics columns are expected (no successful LLM
response to attribute).

TL's DAG (from correlation's audit row 47 broadcast + per-row
`depends_on`): `pm_clarify` (no deps) → `arch` (depends_on=pm) →
{`be`, `design`} (both depends_on=arch) → `fe` (depends_on=design)
→ `qa` (depends_on=[be, fe]). Correct v2 shape.

## What this demo confirmed for iter-7

✅ **Architect `llm_timeout_s = 600 s`**. ADR + system-design
   draft completed in 318 s — past iter-6's 300 s timeout, well
   under iter-7's 600 s. `total_cost_usd=$1.77` ($4.00 cap).

✅ **`LLMTimeoutError` carries buffered stdout (the field)**.
   Designer's synth report reads
   `LLMTimeoutError: claude -p timed out after 300s; stdout=''`.
   Empty in this run (Designer hadn't flushed) but the field is
   present and will carry data when there is some.

✅ **Transitive drop cascade through HoldQueue**. Designer's
   FAILED → fe dropped via direct cascade → fe Task row flipped
   to `failed` via `on_drop`. Backend's FAILED → qa dropped (be
   was one of qa's predecessors) → qa Task row flipped. Both fe
   and qa would have stayed `in_progress` pre-iter-7 (iter-6
   demo Failure 2 closed).

✅ **Root rollup**. Root Task `a10250fc-…` flipped to `failed`
   via `derive_parent_status` (any-failed dominates).

## What this demo did NOT confirm

❌ End-to-end chain → `pending_review` → owner approve. Stalled
   on Designer 300 s timeout + Backend budget cap. **Six demos
   in a row** (iter-2c, iter-3, iter-4, iter-5, iter-6, iter-7)
   stopped short of the full loop; each iteration's failure mode
   is narrower than the last.

❌ `LLMBudgetExhaustedError` → BLOCKED on real `claude -p`
   exhaustion. The detector's complete-JSON-parse requirement
   defeated by the 2000-byte stdout cap. Unit tests pass
   (iter-6); real-LLM does not.

❌ Designer running to completion on the v2 task. Same 300 s
   timeout pattern that hit Architect in iter-6. Designer needs
   the same one-line bump in iter-8.

## Cost / quota

Real metrics from `metadata.llm`:

| Agent              | Model         | tokens_in | tokens_out | cost_cents | duration_ms |
|--------------------|---------------|-----------|------------|------------|-------------|
| TL                 | opus-4-7      | 7         | 1992       | 13         | 31845       |
| PM                 | sonnet-4-6    | 6         | 13486      | 20         | 215787      |
| Architect          | opus-4-7      | 9         | 23740      | 177        | 318088      |
| Designer (timeout) | (synthesised) | —         | —          | partial    | 300000      |
| Backend (budget)   | (synthesised) | —         | —          | ~150¹      | 341973      |
| Frontend (dropped) | —             | —         | —          | $0         | —           |
| QA (dropped)       | —             | —         | —          | $0         | —           |
| **Total**          |               |           |            | **~$3.60** | —           |

¹ Backend's `claude -p` reported `total_cost_usd=$1.5040` in the
truncated stdout before the dispatcher caught it. Designer's
partial spend before the timeout is unknown but bounded — empty
stdout suggests minimal billable work.

Approaching the $5.00 ceiling. iter-8's first run will start
from PM+Architect+Designer succeeding (~$2.10) and Backend
running to a higher cap; if all six agents complete, total may
be $4-5. Quota stayed healthy throughout.

## Artifacts produced this run

- 1 root `Task` row, **status: `failed`** (rolled up via the
  any-failed cascade).
- 6 child Task rows:
  - 2 `done` (PM, Architect)
  - 4 `failed` (Designer + Backend via real synth; Frontend + QA
    via iter-7 transitive `on_drop`)
- 12 audit_log rows (chain intact, HMAC valid, full metrics on
  every non-synth row).
- Files written:
  - `docs/adr/0014-…` (Architect, ADR for idea-validator v2)
  - `docs/design/idea-validator.md` (Designer, partial — the UX
    brief was being written when the 300 s timer fired; the
    visible content shown in the demo log header was substantive)
  - `examples/sandbox/idea-validator/pyproject.toml`,
    `examples/sandbox/idea-validator/src/`,
    `examples/sandbox/idea-validator/tests/` (Backend, scaffold
    + partial implementation; 22156 output tokens before budget
    exhaustion)
  - `apps/web/idea-validator/index.html` — NOT written (Frontend
    dropped before it could start).
  - QA artifacts — NOT written (QA dropped transitively).

## Action items for iter-8

1. **(top)** **Bump Designer `llm_timeout_s` to 600 s.** Same
   one-line fix as iter-7's Architect. Consider whether
   `BaseAgent` default should shift from 300 → 600 (carry-over
   item #14 from iter-7 handoff).
2. **Fix `_is_budget_exhausted_stdout` against truncated JSON.**
   Substring match alone (without requiring full JSON parse),
   plus a stdout-cap bump to 8 KB for diagnostic richness. Without
   this, iter-6's BLOCKED branch never fires in real-LLM.
3. **Modest sonnet budget bump to $2.50.** Backend hit $1.50
   cap at 11 turns; $2.50 gives ~18 turns of headroom. Pair with
   #2 so a real exhaustion routes to BLOCKED + owner retry.
4. **Re-run iter-7-shape demo** after #1-3 to finally close the
   `pending_review` loop iter-3/4/5/6/7 all reached for.
5. **Carry-overs unchanged from iter-7 handoff**: HoldQueue
   persistence, `audit_writer` Postgres role, hash-chain alert,
   `GitHubTargetRepo`, TL transactional decomposition,
   `pytest-rerunfailures` plugin pin, `BaseAgent` template-method
   refactor, pre-flight MCP health-gate, `BaseAgent.llm_timeout_s`
   default bump (now overdue with #1).

## Why this demo is a net win

- **All three iter-7 deliverables shipped behind tests** (1 unit +
  2 unit + 1 integration for the new tests; plus 4 reducer
  integration tests for `on_drop` edges) and stay green in CI.
- **Architect's 600 s timeout closed iter-6 Failure 1.** Architect
  completed for the first time across six demos.
- **Transitive cascade closed iter-6 Failure 2.** fe + qa
  terminate correctly even when their predecessor was dropped,
  not failed-via-report. The 3-level integration test pinned it;
  the real-LLM run validated it.
- **Architect's 318 s runtime confirms the 600 s margin is right.**
  Not over-engineered; not under-engineered.
- **Two new failure modes are narrow and well-understood.**
  Designer timeout has the exact same shape as iter-6's Architect
  timeout (one-line fix). BLOCKED detector's JSON-parse strictness
  is fixable with one substring check.

iter-7 ships with these caveats documented; iter-8's Phase 1 lands
the two follow-up fixes and re-runs the demo. The chain is
genuinely close to `pending_review` now — Backend wrote 22 KB of
output before exhausting budget, which means the LLM is doing
real implementation work, not stuck on plumbing.
