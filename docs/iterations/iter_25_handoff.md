# Iteration 25 handoff

> Read **after** `CLAUDE.md`,
> `docs/iterations/iter_24_retro.md`, and
> `docs/iterations/iter_24_demo_report.md`.

## Where we are (2026-05-21 EOD, iter-24 merged)

🎯 **iter-24 closed the 5-iteration-deferred QA-emitted
`pending_reviews` row criterion.** A real-LLM demo
(correlation `f26bf077-1c8d-43a5-99b8-bf93402e79a8`)
produced a clean 13-row audit chain: PM → Architect →
Designer → Backend → Frontend all DONE, QA produced the
owner-approval row (44 tests / 84.6% coverage). First time
across iter-19..24.

**The framework architecture is now sufficient for the
sandbox idea-validator task to run end-to-end under real
LLMs.** This is a substantive milestone. The next
iteration's challenge shifts from "make the chain work" to
"what does the team build next?"

iter-24 ships:
- **Phase 2**: TL `_maybe_route_blocked` detects
  `summary.startswith("Scope pre-flight")` as canonical
  self-eject signal — structural, not semantic. Removes
  the iter-23 R#1 routing fragility.
- **Phase 3**: Backend prompt instructs that a missing
  target directory is NORMAL and should be created via
  `write_file_in_scope`. Pin test enforces. Removes the
  iter-23 R#1 "examples/ untracked" self-eject path.
- **Phase 1** (research): A/B test denied the iter-23
  enum-retry-loop theory. `claude -p` remaps LLM output
  to the nearest valid enum value rather than retrying
  internally. iter-23's enum revert was architecturally
  correct but for a different reason than the original
  commit claimed.
- **Phase 4**: Demo EXIT trap MOVES the API log to
  `docs/iterations/iter_24_demo_logs/${CORRELATION:0:8}.log`
  instead of deleting it. Forensic value for future
  demos.
- **Phase 4 hotfix**: Demo's final acceptance check now
  queries the DB directly (status-agnostic) instead of
  `/api/reviews` (pending-only). Avoids false-negative
  CRITERION NOT MET messages.

## iter-25 priorities (in order)

### 1. (Strategic) — What does the team build next?

iter-19..24 spent six iterations on framework reliability.
The sandbox idea-validator now runs end-to-end. The
framework is ready to attempt a different product.

The owner should decide:
- (a) **Keep iterating on the sandbox** — add more
  agents/features to idea-validator (e.g., a CLI, a
  database, a real LLM analysis stage). Risk: keeps the
  framework in self-test mode forever.
- (b) **Pivot to a real product** — pick one of the
  monetizable ideas in `docs/sandbox/idea_validator_*.md`
  (or elsewhere) and have the team build it from a fresh
  PRD. Risk: discovers framework limitations under a
  different shape of work.
- (c) **Stabilization phase** — close the deferred
  carry-overs (HoldQueue persistence, GitHubTargetRepo,
  BaseAgent refactor) before any new product work. Risk:
  invests in tech debt cleanup the framework may never
  exercise.

iter-25's plan-doc should surface the question and let
the owner pick. Recommendation: (b), but only after a
reproducibility check (#2 below) confirms iter-24 wasn't
a lucky one-off.

### 2. Reproducibility check (P1)

iter-24's demo was the FIRST clean Backend DONE in 5+
iterations. Re-run the same demo at least once more,
ideally twice, to confirm the iter-22..24 cumulative
fixes are stable across LLM samples — not just a lucky
run.

If 3/3 re-runs all produce QA rows: chain reliability is
proven. If 1-2/3: identify what's still flaky.

Cost: ~$3-5. Risk-reducer for any pivot decision (#1).

### 3. Demo poll-loop post-success drain (P2)

iter-24's demo broke the poll loop the moment
`qa_reviews=1` detected — but QA's `task_report` audit
write was still pending. Adding a 30-60s "drain" sleep
after success lets the audit log complete. Trivial
change in `scripts/demo_iter_25.sh` (clone of iter-24).

### 4. Commit `examples/sandbox/idea-validator/` scaffold to main (P2)

iter-24's prompt edit fixed the Backend missing-dir
problem at the LLM-instruction layer. A more robust fix:
commit a minimal scaffold (`__init__.py`, `pyproject.toml`,
`tests/`, `README.md`) so the dir exists in main and
Backend's `git worktree add` from main has it from
turn 1. Belt-and-suspenders with the prompt.

### 5. (P3) Investigate iter-23 R#2 BLOCKED(budget) root cause

iter-24 Phase 1 ruled out the enum-retry-loop theory.
The actual cause of iter-23 R#2's $2.50 budget burn
remains unknown. With API log preservation now in place,
the next time it recurs we can analyze forensically. Not
blocking; capture iff observed.

### 6. (Carry-overs ≥5 unchanged)

- HoldQueue persistence (Postgres).
- `pytest-rerunfailures` plugin pin.
- TL auto-hop investigation.
- `audit_writer` restricted Postgres role.
- Hash-chain alert job.
- `GitHubTargetRepo` implementation.
- TL decomposition transactional insert.
- `BaseAgent.handle()` template-method refactor.
- `mark_task_done` / `update_task_status` real impls.
- Substrate-level `--allowed-tools ""` fix.

## Hard constraints (additions from iter-24)

All prior iteration constraints hold. iter-24 additions:

- **iter-24: TL `_maybe_route_blocked` checks
  `summary.startswith("Scope pre-flight")` FIRST**, then
  iter-23's substring on `blocked_on`. Both feed into
  `_re_decompose_on_too_large`.
- **iter-24: `_SCOPE_PREFLIGHT_SUMMARY_PREFIX = "Scope
  pre-flight"`** is the routing signal name. Don't
  change the prompt template's "Scope pre-flight:" prefix
  without updating this constant + pin tests.
- **iter-24: Backend prompt has a "Target directory
  handling (iter-24)" section** with explicit
  "missing target dir is NORMAL" guidance. Pin test
  `test_backend_prompt_handles_missing_target_dir`.
- **iter-24: Demo EXIT trap MOVES API log to
  `docs/iterations/iter_24_demo_logs/${CORRELATION:0:8}.log`**.
  Clone-and-adjust in `scripts/demo_iter_25.sh`.
- **iter-24: Demo final acceptance check uses
  `docker exec psql` against `pending_reviews` directly**
  (status-agnostic). Don't revert to `/api/reviews`
  filtering — that was the iter-24 false-negative bug.
- **iter-24 lesson recorded**: `--json-schema` enum
  constraints are SAFE — claude -p remaps to nearest
  valid value rather than retry-looping. iter-23's
  "enum suspected of budget burn" caveat is REFUTED.
  Future schema design may use enum freely.

## What iter-24 specifically did NOT do

- **Did not address the iter-23 R#2 budget-burn cause
  beyond ruling out the enum theory.** Still open as
  P3 carry-over.
- **Did not commit an `examples/sandbox/idea-validator/`
  scaffold to main.** iter-25 #4 carry-over.
- **Did not extend demo poll loop with post-success
  drain.** iter-25 #3 carry-over.
- **Did not address carry-overs ≥5.** Same as iter-23.
- **Did not yet plan the framework's next "real
  product" iteration.** iter-25 #1 surfaces the
  question.

## Inherited decisions (do not contradict without revisiting)

All iter-19..24 decisions hold. New iter-24 decisions:

- **iter-24**: TL routes via summary prefix (primary) +
  blocked_on substring (fallback). The summary prefix is
  the canonical signal.
- **iter-24**: Missing target dirs are not blockers —
  Backend creates them. (Was iter-23 R#1 self-eject path;
  now anti-prompted.)
- **iter-24** (recorded lesson): `--json-schema` enum
  constraints are safe on claude -p. iter-23's "enum
  suspected" caveat removed from CLAUDE.md / ADR-008
  guidance.

## Ready-to-paste prompt for the new session

```
Starting Iteration 25 on the ai_team project.

First, read these in this order:

1. CLAUDE.md
2. docs/iterations/iter_24_retro.md (the win — 5-iter
   QA criterion finally met, Backend DONE for first
   time, all 6 agents DONE'd cleanly)
3. docs/iterations/iter_24_demo_report.md (clean
   13-row audit chain, $1.73 total, real-LLM demo at
   correlation f26bf077-1c8d-43a5-99b8-bf93402e79a8)
4. docs/iterations/iter_25_handoff.md (this file —
   strategic options + small operational fixes)

Iter-25 priorities (in order):

1. (STRATEGIC) Surface the "what next?" question for
   the owner: (a) keep iterating on the sandbox, (b)
   pivot to a real product, or (c) stabilization
   phase. Recommend (b) but only after #2 confirms
   reproducibility.

2. Reproducibility check — re-run the iter-24-shape
   demo 1-2 more times to confirm Backend DONE is
   stable across LLM samples.

3. (P2) Demo poll-loop post-success drain (30-60s)
   so QA's audit row gets written before EXIT trap
   kills the dispatcher.

4. (P2) Commit examples/sandbox/idea-validator/
   scaffold to main as belt-and-suspenders alongside
   iter-24's prompt edit.

5. (P3) Investigate iter-23 R#2 BLOCKED(budget) if
   it ever recurs (now have API log preservation).

Workflow: plan-before-code. Draft
docs/iterations/iter_25.md first, surface for review
(especially the strategic question in #1), then code.
Run validation + PR merges yourself.

Constraints unchanged from iter-24 — see CLAUDE.md
gotchas + the "Hard constraints" section of
iter_25_handoff.md.

PR merge gotcha: use `gh api -X PUT
repos/.../pulls/<N>/merge -f merge_method=squash` to
bypass gh CLI's local-checkout failure.

When ready, create the iter-25 task list and surface
the plan.
```
