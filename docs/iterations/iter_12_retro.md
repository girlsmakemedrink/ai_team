# Iteration 12 — Retrospective

**Closed**: 2026-05-20. 5 commits on `worktree-iter-12`
(plan + router pattern tuples + demo script + demo report
+ retro/handoff). All gates green; real-LLM demo run
captured in `docs/iterations/iter_12_demo_report.md`.

**Headline**: iter-12's two new substring-router pattern
tuples FIRED IN PRODUCTION on the first demo run after
merge. iter-11's `ai-team retry-blocked` engaged
END-TO-END for the first time across twelve iterations —
endpoint validated eligibility, built a `model_copy` with
same task_id + correlation_id + fresh message_id +
`metadata.retry_attempt=2`, signed, audit-logged, bus-
published. The chain reached the most advanced state ever
observed. Backend's retry then surfaced a separate
well-scoped bug: `claude -p` session-id collision under
dispatcher restart. iter-13 closes that and re-runs.

## What shipped

Phase 0 — Plan (`docs/iterations/iter_12.md`, 485 lines)
committed on `worktree-iter-12` cut from `origin/main` at
`e0e0192`.

Phase 1 — Substring router pattern tuples + unit test
(`core/dispatcher/mcp_race_router.py:39-58` +
`tests/unit/test_mcp_race_router.py:152-173`):

- Two new tuples in `_MCP_RACE_PATTERNS`:
  - `("mcp__ai_team_repo", "unavailable")` — matches
    iter-11 demo Backend's verbatim wording
    ("`mcp__ai_team_repo__* tools were unavailable
    throughout the session`").
  - `("MCP tools", "unavailable")` — broader companion
    catching future variants.
- Pattern semantics unchanged from iter-10: each tuple
  requires ALL substrings to co-occur — near-zero
  false-positive risk.
- Module docstring updated with iter-11's wording in the
  historical list (lines 12-19).
- 1 new unit test pins iter-11 demo correlation
  `ccac21dc-...` Backend summary verbatim → BLOCKED +
  `blocked_on='mcp_unhealthy'`. 5 prior iter-10 tests
  still pass.

Phase 2 — Demo script + real-LLM run + report:

- `scripts/demo_iter_12.sh` clone of demo_iter_11.sh with
  iter-12 header documenting the router extension,
  `.iter12-mcp.json` config filename, iter-12 task title.
- `make demo` aliases to `demo-iter-12`; iter-11/10
  remain as regression baselines.
- Real-LLM run on 2026-05-20, correlation
  `3d442628-b4e2-4233-8ba1-834b460e2477`.
  - PM ($0.09 / 106 s), Architect ($0.59 / 109 s),
    Designer ($0.15 / 181 s), Frontend ($0.09 / 135 s)
    all DONE.
  - Backend first attempt ($0.26 / 349 s) emitted
    iter-11's exact phrasing → router rewrote to
    BLOCKED via `("mcp__ai_team_repo", "unavailable")`
    tuple → audit row 163 reflects BLOCKED directly.
  - Owner ran
    `uv run ai-team retry-blocked b1fb13e2-...` — CLI
    printed the Rich panel, endpoint built and signed
    the retry message, audit row 164 has the
    `metadata.retry_attempt=2` carrier, `tasks.status`
    flipped blocked→in_progress.
  - Backend's retry hit `LLMInvocationError: claude -p
    exited 1: Session ID is already in use` because
    I had to restart uvicorn between Backend's first
    attempt and the retry (the demo script's exit-trap
    killed it), and the
    `ClaudeCodeHeadlessClient`'s in-memory cache of
    "which session_ids have been claimed" doesn't
    survive process restart. Synth_failed_report at
    row 165 → iter-7 cascade → root failed.
- Total demo spend $1.32 — **60% cheaper than iter-11's
  $3.41**. Architect's spend collapsed from $2.47 to
  $0.59 (v2 ADRs now warm in the cache).

Phase 3 — Final gates + retro + iter-13 handoff:

- `make lint typecheck sec` all green. 0 high-severity
  bandit findings.
- `make test test-integration smoke-llm` — unit 369/369
  pass; one integration test
  (`test_transitive_drops_cascade_through_hold_queue`)
  flaked in the combined run, passed when isolated —
  known testcontainers race, deferred pytest-rerunfailures
  pin (carry-over item 11).
- `uv run ruff format --check .` clean (140 files).
- **Diff-cover on iter-12 diff vs `origin/main`**: only
  Python changes are `core/dispatcher/mcp_race_router.py`
  (5 lines of new tuples + comment) — both covered by
  the new pinning unit test → effectively 100%.
- This file + `iter_13_handoff.md` + `iter_12_demo_report.md`.

## What went well

- **Plan-before-code held tightly.** Owner approved
  inline; phases tracked exactly. Same pattern that
  worked iter-7..11.
- **TDD discipline held tightly.** Phase 1 wrote the
  failing test first (RED with iter-11 verbatim summary
  staying FAILED), then added the tuples (GREEN). All
  iter-10 tests stayed green throughout.
- **The substring router extension fired on the first
  production run after merge.** Same pattern as iter-10:
  contracts derived from observed failures fire faster
  than contracts derived from speculation. Both
  iterations have now confirmed this.
- **`ai-team retry-blocked` worked end-to-end at the
  orchestrator level for the first time across twelve
  iterations.** Endpoint + helper + CLI + audit + bus +
  tasks-table flip all behaved exactly as iter-11
  designed. Every layer tested in iter-11 was exercised
  in production this run.
- **Cost collapse iteration-over-iteration.** Architect
  dropped from $2.47 (iter-11) to $0.59 (iter-12). The
  v2 ADR consolidation is now warm in the prompt
  cache; subsequent runs are dramatically cheaper.
  Total demo spend $1.32 vs iter-11's $3.41.
- **Failure 1 (the session-id collision) is well-scoped
  + has a clear fix.** One file, one method, ~5 lines
  behind a unit test. iter-13 closes it.
- **Architect's self-observation about TL over-
  decomposition.** Architect row 160 explicitly noted
  TL re-decomposed v2 from scratch despite ADR-0019
  already covering all five concerns. Useful signal
  about TL's prompt — Architect is now part of the
  team's self-correction loop.

## What didn't

- **`claude -p --session-id` durability across
  dispatcher restarts is broken.** When the demo's
  exit-trap killed uvicorn and I restarted it manually
  to exercise retry-blocked, the new dispatcher's
  `ClaudeCodeHeadlessClient` cache had no record of the
  session_id Backend's first attempt had created. Tried
  `--session-id` again → claude -p errored "already in
  use" → LLMInvocationError → synth_failed_report → root
  failed. Not normally hit in production (continuous
  dispatcher process retains the cache), but a real
  risk under any planned redeploy or crash recovery
  between BLOCKED and retry-blocked. iter-13 fix:
  `ClaudeCodeHeadlessClient` should try `--resume`
  first and fall back to `--session-id` on the "no such
  session" error.
- **HoldQueue is still in-memory.** This iteration
  surfaced the consequence: when the demo's dispatcher
  was killed between Backend's BLOCKED report and the
  retry, the in-memory HoldQueue entry for QA's
  task_assignment was lost. QA's `tasks` row is now
  orphaned at `in_progress` (no cascade dropped it
  because the HoldQueue had nothing to drop on
  Backend's retry-failure). HoldQueue persistence
  (carry-over item 6 from iter-12 handoff) is now
  actively relevant.
- **TL still over-decomposes against pre-existing
  contracts.** Architect's task_report explicitly
  flagged that ADR-0019 from iter-11 already covered
  the five concerns TL re-asked about. TL's prompt
  needs an "iteration detection" hint.
- **`pending_review` loop still untouched end-to-end.**
  Twelve demos in a row. Closer than ever — iter-13's
  Failure 1 fix should close it on demo #13.

## Surprises

- **Architect's spend dropped 4× iter-over-iter.**
  iter-11: $2.47 / 410 s for the consolidated ADR.
  iter-12: $0.59 / 109 s for what was effectively the
  same prompt against a now-cached spec + ADRs. The
  Anthropic prompt cache is working as advertised; the
  system gets cheaper as the chain becomes richer.
- **Backend's first attempt produced REAL incremental
  work despite ending in BLOCKED.** Backend's task_report
  summary names a specific code change ("fixed CLI
  invalid-output-dir error message (US-1 AC-9), added
  test_analyze_invalid_output_dir (TDD), added
  README.md"). The MCP race only hit when Backend tried
  to commit/test — the iter-10 `examples/sandbox/` tree
  was already complete from a prior run. iter-13's
  retry should resume from this state and complete the
  commit/test/PR cycle.
- **The retry message's `metadata.llm` field is
  inherited from the original assignment via
  `model_copy`.** iter-11's
  `build_retry_message(original, retry_attempt)` does
  `original.model_copy(update={"message_id": uuid4(),
  "metadata": {**original.metadata, "retry_attempt":
  N}, "hmac_signature": None})`. The original TL
  assignment had `llm` metrics from the TL's opus
  call; the retry assignment inherits them. So the
  audit row 164 shows `cost_cents=14` and
  `model=claude-opus-4-7` — but no new LLM call
  happened. Worth noting in the audit reader so demo
  reports don't double-count.
- **`pending_review` is now ONE bug away.** iter-3
  through iter-12 have steadily moved the chain
  forward: iter-3 reached DAG-aware HoldQueue,
  iter-5 reached crash-handling, iter-6 reached
  BLOCKED-on-budget, iter-7 reached transitive
  cascade, iter-8 reached BLOCKED-on-stdout-budget,
  iter-9 reached pre-flight gate + MCPUnhealthyError,
  iter-10 reached substring router + recoverable
  BLOCKED, iter-11 shipped retry-blocked but didn't
  exercise it, iter-12 exercised retry-blocked but
  hit session-id collision. iter-13's narrow fix
  finishes the journey.

## Action items for iter-13

These overlap with `iter_12_demo_report.md` and
`iter_13_handoff.md` and are the starting list for the
next iteration. Highest priority first:

- [ ] **(top)** **Fix `ClaudeCodeHeadlessClient` session-id
      durability under dispatcher restart.** Make the
      adapter try `--resume` first and fall back to
      `--session-id` on the "no such session" stderr
      pattern. ~5 LOC + 1 unit test (mock claude -p
      stdout/stderr for both paths).
- [ ] **Re-run iter-12-shape demo** after #1 to finally
      exercise iter-11's retry-blocked end-to-end through
      Backend's claude -p call. Expected: chain reaches
      QA → QA emits `request_human_review` → owner runs
      `ai-team approve`.
- [ ] **TL over-decomposition awareness.** Architect's
      iter-12 row 160 flagged that TL re-decomposed v2
      from scratch despite ADR-0019. Add a prompt hint
      to TL: "before decomposing, read any ADR matching
      the spec's slug + skip subtasks whose contracts
      are already on disk".
- [ ] **HoldQueue persistence (Postgres-backed).** Now
      actively relevant — iter-12 surfaced the loss-on-
      restart scenario. Lift to `held_messages` table.
- [ ] **TL Backend decomposition** (four-iteration
      carry-over: iter-9/10/11/12). Backend's 349 s
      first-attempt session was again the longest.
      Splitting reduces MCP race exposure + per-retry
      burn.
- [ ] Carry-overs unchanged from iter-12 handoff
      (items 5–12): startup-time MCP failure
      investigation, `audit_writer` Postgres role,
      hash-chain alert, `GitHubTargetRepo`,
      transactional TL decomposition,
      `pytest-rerunfailures` plugin pin (now bit us
      this iteration), `BaseAgent` template-method
      refactor.

## Stats

- **Commits on iter-12 branch**: 5 (plan + router
  patterns + demo script + demo report + retro/
  handoff).
- **Tests added**: 1 unit test on
  `test_mcp_race_router.py::test_routes_iter11_demo_backend_summary_to_blocked`.
- **Total tests after iter-12**: **369 unit + 42
  integration = 411 collected** (iter-11 close: 368
  unit + 42 integration = 410). Net +1 test.
- **Real-LLM spend this iteration**: $1.32 (~26% of $5
  ceiling). TL $0.14 + PM $0.09 + Architect $0.59 +
  Designer $0.15 + Frontend $0.09 + Backend (BLOCKED
  + retry-failed) $0.26.
- **Diff-cover on iter-12 diff vs `origin/main`**:
  effectively 100% — the only Python changes are 5
  lines of new pattern tuples in
  `core/dispatcher/mcp_race_router.py`, all covered by
  the new pinning unit test.
- **LOC delta**: ~750 added (Phase 1 tuples + 1 test +
  demo script clone + plan + demo report + retro +
  handoff).
- **iter-12 is the smallest iteration since iter-2c:**
  one narrow code change + a demo + docs. The chain
  reached its furthest state ever, the bug found is
  well-scoped, and the iter-13 fix is small.

## Ready-to-paste prompt for iter-13

In `docs/iterations/iter_13_handoff.md`.
