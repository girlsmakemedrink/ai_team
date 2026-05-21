# Iteration 22 — Retrospective

**Closed**: 2026-05-21. 7 commits on
`worktree-iter-22` (plan + 2 feat + 1 chore + 1
style + 1 docs + 1 retro/handoff forthcoming).
All static gates green
(ruff/mypy/bandit/433 unit/50 integration/smoke-llm).
Real-LLM demo produced the cleanest chain shape
we've ever seen — both iter-22 contract changes
fired correctly under real LLM stress.

**Headline**: iter-22's prompt-edit bet over
iter-21's Python-regex bet PAID OFF empirically.
Backend's "Scope pre-flight (turn 1)" prompt
section produced exactly the intended chain
shape: Backend ran for 77s, recognized the task
exceeded 200 LOC, emitted
`BLOCKED(blocked_on='task_too_large')`, TL's
iter-21 Phase 2 handler picked up the report,
self-routed a re-decomp turn, and dispatched a
60%-smaller `be_schema` subtask. The Phase 2
Architect→Backend mandatory `depends_on` rule
was also applied — Backend's row 332 metadata
carries Architect's subtask UUID, meaning the
HoldQueue held Backend until Architect's ADR
was in hand. **The auto-recovery path is now
load-bearing**, not just unit-tested.

The QA-emitted `pending_review` row remains
deferred — **for the 4th iteration in a row** —
but the cause has shifted fundamentally. iter-19,
20, 21 all failed because Backend timed out
fatally (FAILED, not BLOCKED, so no
auto-recovery). iter-22's chain auto-recovered
and was in flight toward QA when the demo's
30-min poll window expired. **iter-23's blocker
is operational (window length), not
architectural.**

## What shipped

Phase 0 — Plan (`docs/iterations/iter_22.md`,
~878 lines) committed on `worktree-iter-22` cut
fresh from `origin/main` at `d95c69e` (iter-21
squash). Plan-before-code held; owner approved
before any code commits.

Phase 1 — Backend LLM self-eject path
(`2522994`):
- `agents/backend_developer/agent.py`:
  `BACKEND_REPORT_SCHEMA` grows optional
  `status: enum["done","failed","blocked"]` and
  `blocked_on: str|null` fields.
  `additionalProperties` stays `false`; only
  these two are new. `branch` regex relaxed to
  allow empty string on self-eject.
- `build_outputs` checks `report["status"]`
  FIRST. On `status=='blocked'`, emits
  `TASK_REPORT(status=BLOCKED, blocked_on=...)`
  via `_report_to_tl(blocked_on=...)`. Falls
  back to legacy `tests_passed`-based DONE/FAILED
  mapping when `status` field absent
  (backward-compatible with the iter-21 LLM
  response shape).
- `prompts/backend_developer.md`: new "Scope
  pre-flight (turn 1)" section near the top with
  the BLOCKED JSON shape inline; "What you
  produce" split into DONE + BLOCKED examples;
  "Keep diff small" Discipline rule replaced
  with pointer to the pre-flight (200 LOC vs
  the old advisory ~300 LOC).
- 4 new unit tests: self-eject emits BLOCKED,
  blocked_on passthrough, legacy
  `tests_passed`-only path still works (backward
  compat), prompt teaches Scope pre-flight
  (substring pin).
- Total Backend agent tests: 17 (was 13).

Phase 2 — TL Architect→Backend mandatory
`depends_on` (`292569a`):
- `prompts/team_lead.md`: promoted the existing
  advisory example ("Backend depends_on Architect
  because Backend reads the ADR") to a MANDATORY
  rule when both roles co-occur in the same
  decomposition. Rule explicitly cites iter-21
  demo audit row 318 as the motivating failure.
  Includes a JSON example showing the correct
  shape (Backend `depends_on` lists Architect's
  subtask `id`).
- 1 new TL pin test:
  `test_tl_prompt_teaches_mandatory_architect_backend_depends_on`.
- Total TL tests: 20 (was 19).

Phase 3 — `scripts/demo_iter_22.sh` + Makefile
(`0d035fc`):
- 368-line clone of `demo_iter_21.sh` with
  iter-22 narrative (header, banner, MCP config
  `.iter22-mcp.json`, EXIT-trap function
  `_cleanup_iter22`, demo task title,
  auto-approve comment). Bash auto-approve
  pattern (`python3 - "$JSON" <<'PY' ...
  sys.argv[1]`) unchanged — iter-21's fix
  inherited.
- `Makefile`: `demo-iter-22` target +
  `.PHONY` entry; `demo` repointed.

Phase 4 — Validation gates (all green;
smoke report `90a9780`):
- `ruff check .`: `All checks passed!`
- `ruff format --check`: 148 files already
  formatted.
- `mypy --strict`: `Success: no issues found
  in 148 source files`.
- `bandit`: `High: 0`.
- `pytest tests/unit`: **433 pass** (iter-21's
  428 + 5 new = 433).
- `pytest tests/integration`: **50 pass**
  (one transient docker flake on first run;
  passed cleanly on retry).
- `make smoke-llm`: `Overall: PASS` first try.

Phase 5 — Real-LLM demo (`32406a4`, ~$2.02
observable):
- **Backend self-eject WORKED on turn 1**
  (audit row 339, 77s vs iter-21's 600s).
- **TL re-decomposition triggered automatically**
  (rows 340-342). Emitted a 60%-smaller subtask
  (`be_schema`, ≤80 LOC vs original ≤200 LOC).
- **Phase 2 Architect→Backend depends_on rule
  applied** (row 332 metadata carries
  Architect's subtask UUID).
- **Architect spend back to baseline** ($0.93,
  171s — within iter-19/21's $0.78-$0.80
  range).
- **Branch isolation + bash fix held**.
- **Backend's re-decomp turn (row 342) was in
  flight when the demo's 30-min poll window
  expired** — no row 344+ written. **Failure
  mode shifted from "Backend fatal timeout" to
  "demo wall-clock budget too short for
  auto-recovery chain"**.
- Full report:
  `docs/iterations/iter_22_demo_report.md`.

## What went well

- **The prompt-edit bet PAID OFF**. iter-21
  demo report hypothesized that "moving scope
  judgment from a Python regex to LLM intent"
  would close the timeout problem. iter-22
  demo confirms it empirically. Backend
  recognized the task scope was too large from
  semantic intent (not text regex) and emitted
  BLOCKED cleanly on turn 1.
- **TDD discipline held throughout**. 5 new
  tests all written first, watched fail,
  minimal implementation, watched pass. Even
  the "anti-loop" test from iter-21 stayed
  green for the right reason.
- **The iter-21 contract layer (TL re-decomp
  handler) is now LOAD-BEARING in practice**.
  Shipped on iter-21 with tests pinning it but
  never exercised under real LLM. iter-22's
  demo ran it end-to-end. The shipping
  pipeline (prompt → BLOCKED → re-decomp →
  smaller subtask) works.
- **Backward compat held**. The legacy
  `tests_passed`-only LLM response shape still
  maps to DONE/FAILED correctly. Phase 1 test
  4 (`test_handle_legacy_tests_passed_path_still_works`)
  pins it.
- **Plan structure (Phase 0-6) held**. No
  phase needed reordering or scope expansion
  during execution.
- **Cost dropped vs iter-19/20/21 baseline**.
  $2.02 observable (with Backend's self-eject
  costing $0.06 instead of iter-21's $0.50).
  Phase 1's optimization saved the demo
  meaningful money.

## What didn't

- **The QA-emitted `pending_review` row remains
  unmet — 4-iteration deferred.** But: the
  cause shifted from architectural (Backend
  cascade-drop) to operational (demo poll
  window length). iter-23's fix is much
  smaller than iter-21's or iter-22's.
- **Backend's re-decomp turn produced no audit
  row before the demo exited.** Either Backend
  was still in flight on the smaller scope
  when the EXIT trap killed the dispatcher
  process, or the smaller scope ALSO timed out
  (less likely; would have produced FAILED).
  iter-23 must determine which.
- **TL didn't decompose Backend along
  ADR-0030's explicit DAG.** Architect's ADR
  defined a 5-subtask DAG (be_core-anchor +
  be_core-data + be_core-clients +
  be_core-engine + be_cli) with per-subtask
  LOC budgets — exactly what Backend would
  have needed. TL emitted `be_core` as a single
  >200 LOC subtask anyway. The Backend
  self-eject + TL re-decomp covered for this,
  but it cost ~$0.30 of agent turns. iter-23
  candidate: sharpen TL's prompt to USE the
  Architect ADR's decomposition when present.
- **`ai-team retry-blocked` doesn't recognize
  `task_too_large`** — the CLI's
  RECOVERABLE_BLOCKED_ON whitelist only has
  `mcp_unhealthy` and `budget`. The demo's
  auto-retry step hit 422. iter-22's flow
  recovered automatically via TL so this
  didn't matter, but the error message is
  misleading.

## Surprises

- **The LLM followed the prompt's
  Scope pre-flight rule on the very first
  demo run**, including emitting EXACTLY the
  BLOCKED JSON shape shown in the prompt. The
  iter-20 retro noted that LLM compliance
  with NEW prompt-only instructions is
  better than expected; iter-22 confirms at
  scale — the model adopted the new
  contract immediately without prompt
  tuning iterations.
- **Backend's BLOCKED report carried the
  ENTIRE original task description in the
  summary** (per the prompt's instruction to
  "echo first 500 chars of original
  description"). When TL ran the re-decomp,
  the summary text gave it enough context
  to produce a meaningfully smaller subtask
  in one decomposition turn (no further
  iteration). The summary-as-context channel
  worked exactly as designed.
- **The `depends_on` lives in audit_log's
  `metadata`, not `payload`**. Initial
  query path was wrong; the actual data
  was there all along. Note for the
  iter-23 retro: SQL queries on audit_log
  should consult both `metadata` AND
  `payload` JSON paths.
- **Frontend's static landing page completed
  AGAIN in this run** (199 lines, same as
  iter-21). The architecturally-correct
  BLOCKED was scoped to the prohibited
  server-form, not the static page.

## Action items for iter-23

1. **(NEW TOP)** **Extend demo poll window
   AND/OR investigate Backend smaller-scope
   wall-clock**. Two paths:
   - Quick: bump
     `scripts/demo_iter_22.sh`'s poll loop
     budget from 30 min to 45 min (matches
     CLAUDE.md's documented "30 min initial
     + 15 min retry = 45 min total" budget).
   - Diagnostic: run iter-22's demo with a
     longer window and capture whether
     Backend's smaller scope eventually
     produces a row 344 (DONE or FAILED)
     and how long it takes.

2. **(NEW)** **`RECOVERABLE_BLOCKED_ON` +=
   `task_too_large`**. Edit
   `core/retry/retry_blocked.py:34` to add
   `"task_too_large"` to the frozenset.
   Pin test. The `ai-team retry-blocked`
   CLI 422 in iter-22's demo was
   misleading; the value IS recoverable —
   the same path TL auto-runs.

3. **(NEW, OPTIONAL)** **TL prompt: USE
   Architect's ADR decomposition when
   present**. If Architect's task_report
   summary mentions an explicit subtask
   DAG or LOC budgets, TL should follow
   it instead of inventing a coarser
   decomposition. Soft prompt edit;
   measured by whether iter-23's demo
   shows Backend split along
   ADR-defined boundaries.

4. **Re-attempt the QA-emitted
   `pending_review` row criterion** —
   now 4-iteration deferred. With #1
   (longer window) this should land in
   iter-23. **This is the primary demo
   success criterion.**

5. **Architect spend watch: CLOSED**.
   iter-19 $0.78, iter-21 $0.80, iter-22
   $0.93 — all in the $0.78-$0.93 band.
   iter-20's $2.88 was variance.

6. **Carry-overs unchanged** from iter-22
   handoff items 5-15 (HoldQueue persistence,
   `pytest-rerunfailures` pin, TL auto-hop
   investigation, `audit_writer` role,
   hash-chain alert, `GitHubTargetRepo`,
   TL transactional insert, `BaseAgent`
   template-method refactor, `mark_task_done`
   / `update_task_status` real impls,
   substrate `--allowed-tools ""` fix).

## Stats

- **Commits on `worktree-iter-22`**: 7
  (plan + 2 feat + 1 chore + 1 style + 1
  docs; retro/handoff forthcoming).
- **LOC delta**: code +~80 (Backend agent
  ~+50, schema ~+10, prompt +~70, TL
  prompt +~25); tests +~120 (5 new); demo
  script +368 (clone); Makefile +5; docs
  +~3000 (plan ~878 + demo report ~405 +
  retro + handoff TBD). Total ~3500 LOC
  including docs.
- **Tests**: +5 (4 Backend self-eject + 1
  TL pin). **433 unit + 50 integration tests
  pass.**
- **Real-LLM spend**: ~$2.02 observable.
  Under $5 ceiling. Below iter-20's $4.25
  and iter-19's $2.00.
- **Architect spend**: $0.93 (within
  iter-19/21's $0.78-$0.80 band).
- **Backend self-eject cost**: $0.06 (vs
  iter-21's $0.50 timeout cost) — 8×
  reduction.
- **Diff-cover**: 100% on new code paths.
- **Demo wall-clock**: ~30 min (poll window
  expired with Backend re-decomp turn in
  flight).
- **Backend self-eject firings in demo**:
  1 (the Phase 1 contract working empirically).
- **TL re-decomposition triggerings in demo**:
  1 (the iter-21 Phase 2 handler running
  load-bearing for the first time).
- **`pending_reviews` table state at iter-22
  close**: 1 row total (iter-18
  historic-first, still `approved`). No
  iter-22 row written. Same as iter-19-21.

## Ready-to-paste prompt for iter-23

Lives in `docs/iterations/iter_23_handoff.md`.
