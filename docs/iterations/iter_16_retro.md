# Iteration 16 — Retrospective

**Closed**: 2026-05-20. 5 commits on `worktree-iter-16`
(plan + verb-set extension + demo script + demo report +
retro/handoff). All gates green; real-LLM demo run
captured in `docs/iterations/iter_16_demo_report.md`.

**Headline**: iter-16's verb-set extension shipped clean
(2 new entries: `"unreachable"` + `"unavailability"`,
1 unit test pinning iter-15 row 218 verbatim, all 10
router tests pass). The real-LLM demo's
**cross-product matcher caught BOTH Backend attempts**
(row 230 + row 233 — zero FAILED rows in the chain),
demonstrating the matcher layer is now empirically
robust. **The `pending_review` loop did not close** —
not because of a matcher gap, but because (a) the demo
script's auto-retry tail loops only once and (b) MCP
keeps racing every Backend session. Both are iter-17
structural fixes. The "phrasing diminishing-returns"
problem that iter-12/13/14 reproduced is **decisively
solved**.

## What shipped

Phase 0 — Plan (`docs/iterations/iter_16.md`, 501 lines)
committed on `worktree-iter-16` cut from `origin/main` at
`8dddf52`.

Phase 1 — `_MCP_FAILURE_VERB_SET` extension + 1 new
unit test:

- Two new set entries appended:
  - `"unreachable"` — synonym of "unavailable" the LLM
    picked organically in iter-15 row 218.
  - `"unavailability"` — noun form of "unavailable".
    Necessary as a SEPARATE entry because `"unavailable"`
    is NOT a substring of `"unavailability"` (position 9
    differs: "le" vs "lity").
- Cross-product space now 3 x 9 = 27 token-verb
  combinations from a 12-element bill of materials.
- `test_routes_iter15_demo_backend_retry_summary_to_blocked`
  pins iter-15 demo row 218 summary verbatim.
- All 9 existing router tests stay green (additive).
- TDD discipline: failing test first (RED), set entries
  added (GREEN).

Phase 2 — Demo script + real-LLM run + report:

- `scripts/demo_iter_16.sh` clone of `demo_iter_15.sh`
  with header updated for iter-16's verb-set narrative;
  `.iter15-mcp.json` → `.iter16-mcp.json`.
- `Makefile` `demo` alias points at iter-16; iter-15
  stays as regression baseline.
- Real-LLM run, correlation
  `4b74be45-e13c-441a-a5a6-9aac249beba8`, cost $1.33
  total — **32 % cheaper than iter-15's $1.99**.
- **The cross-product matcher caught BOTH Backend
  attempts.** Row 230 (first attempt) routed BLOCKED
  via `"MCP server"` + `"never connected"`; row 233
  (retry) routed BLOCKED via `"mcp__ai_team_repo"` +
  `"never connected"`. Zero FAILED rows in the chain.
- Backend's retry summary reports the v2 implementation
  tree as spec-complete (7-stage pipeline, models,
  factories, sanitizer, exit-code table, 5 test
  modules) — only pytest verification is blocked by the
  persistent MCP race.
- Demo's auto-retry tail engaged once but the second
  BLOCKED isn't auto-retried within the same run.
- Demo report (`docs/iterations/iter_16_demo_report.md`,
  ~355 lines) documents outcome 4b + the iter-17 path.

Phase 3 — Final gate sweep + retro/handoff + merge.

## What went well

- **The matcher/router layer is now empirically
  robust.** Five iterations of one-tuple-per-iteration
  followed by iter-15's structural shift + iter-16's
  trivial set extension — and the matcher catches every
  observed phrasing across all five iter-9/11/13/14/15
  demos AND both of this run's Backend attempts. The
  diminishing-returns trap is decisively closed.
- **Cost dropped 32 % iteration-over-iteration**
  ($1.99 → $1.33). Architect dropped to $0.63 (vs
  iter-15's $0.98) — caching the on-main ADR-0021 paid
  off cleanly. iter-16 didn't even need the TL
  over-decomposition prompt hint to see savings.
- **Two consecutive Backend retries both went BLOCKED
  with zero FAILED rows.** This is the cleanest chain
  shape across 17 iterations. The dispatcher's
  BLOCKED-routing + HoldQueue + cascade-drop
  machinery + retry-blocked CLI all worked exactly as
  designed.
- **TDD caught the test ordering immediately.** RED
  test (iter-15 row 218 summary) failed as expected
  before the set entries; passed after. No no-op
  tests this iteration.
- **iter-15's session-id fallback + 429 routing
  stayed defensive (not exercised this run)** — no
  collisions, no quota burn. Both are unit-test-pinned
  for future incidents.
- **No regressions.** 378 unit tests + 42 integration
  tests pass. The verb-set additions are uniformly
  additive.

## What didn't

- **The `pending_review` loop did not close** —
  sixteen demos. iter-16 surfaced the actual remaining
  gap clearly: it's **not** a matcher issue (matcher
  catches every race), **it's** an environment +
  automation issue (MCP keeps racing AND the demo's
  one-retry tail doesn't loop). Both are addressable
  in iter-17 with focused work.
- **MCP server kept racing every Backend session
  this run** — 2-for-2. The startup-time MCP failure
  investigation carry-over (now 9-iteration deferred)
  has reached the point where it's blocking
  end-to-end validation. iter-17 should pick this up
  as a focused-investigation iteration.
- **Demo script's auto-retry loops once** — when the
  second BLOCKED appeared, no automation kicked in.
  Backend has 3 more retry attempts available before
  the cap; could have been called. Trivial bash fix
  in iter-17.
- **TL auto-hop didn't engage** (per CLAUDE.md
  iter-2c). After row 230, no TL re-emit appeared
  before the retry-blocked CLI call (row 232). Either
  the auto-hop isn't wired or it's silently
  overridden by the retry endpoint. Worth an
  investigation in iter-17.
- **Integration test `test_transitive_drops_cascade_
  through_hold_queue` flakes** — passes in isolation,
  flaky when run after unit tests. Carry-over from
  iter-12+ (testcontainers port-mapping race). The
  `pytest-rerunfailures` plugin pin would auto-retry.

## Surprises

- **iter-16's two new verbs (`"unreachable"`,
  `"unavailability"`) DID NOT get exercised** in
  production — Backend used iter-10-era verbs both
  times. The defensive coverage is good but the
  empirical run reproduced an already-handled
  phrasing. **The unit test layer is what validates
  the new verbs; the demo can't be expected to
  reproduce every LLM word choice.**
- **Architect cost halved despite no prompt change**
  ($0.98 → $0.63). The TL over-decomposition prompt
  hint carry-over may have been over-attributed:
  cache effects from ADR-0021 being on main are
  doing most of the work.
- **Both Backend attempts BLOCKED but didn't
  cascade-drop** — Designer + Frontend completed
  successfully because they don't depend on Backend
  in the depends_on DAG (Designer is parallel,
  Frontend depends on Designer). The cascade only
  hits QA. iter-7's transitive cascade behaved
  correctly.

## Action items for iter-17

The demo report has the full design (`docs/iterations/
iter_16_demo_report.md` section "Action items for
iter-17"). Prioritised:

1. **(top)** **Demo auto-retry loop** — `step 6.5/7`
   in the demo script calls retry-blocked iteratively
   on every BLOCKED Backend row appearing in the wait
   window (up to the 5-retry cap). ~20 LOC, or
   factor into a new `ai-team retry-loop CLI`
   command. Pairs with #2.
2. **Startup-time MCP failure investigation** —
   9-iteration carry-over. With the matcher
   guaranteed to catch the race, this is now the
   blocking issue. Diff orchestrator's MCP spawn vs
   claude -p's; inspect logs at higher verbosity;
   maybe add an MCP-health retry loop at spawn time.
3. **TL auto-hop investigation** — confirm whether
   the iter-2c BLOCKED auto-hop is wired + firing.
   ~30 min reading.
4. **TL Backend decomposition** — SEVEN-iteration
   carry-over. If iter-17's third-attempt session
   tries to commit + push + run pytest + open PR,
   could exceed 600s. Defer to iter-18 unless
   timeout actually hits.
5. **TL over-decomposition prompt hint** — Architect
   $0.63 this run was great (cache), but new ADRs
   future iterations bring will spike again. Small
   prompt edit; iter-17 if scope allows.
6. **HoldQueue persistence (Postgres-backed)** —
   demo's QA hold lost again on Backend's
   terminal-BLOCKED.
7. **`pytest-rerunfailures` plugin pin** —
   testcontainers flake confirmed reproducing.
8. **Carry-overs unchanged**: audit_writer Postgres
   role, hash-chain alert, GitHubTargetRepo,
   transactional TL, `BaseAgent` template refactor.

## Stats

- **Commits on `worktree-iter-16`**: 5 (plan + verbs
  + demo script + demo report + this retro/handoff).
- **LOC delta**: +~1300 (plan 501 + matcher 16 +
  matcher test 35 + demo script 302 + demo report 355
  + retro/handoff TBD).
- **Tests**: +1 (`test_routes_iter15_demo_backend_
  retry_summary_to_blocked`). 378 unit + 42
  integration tests pass.
- **Real-LLM spend**: $1.33 single run, no quota
  truncation. **32% below iter-15's $1.99** and well
  under the $5 ceiling.
- **Diff-cover**: vacuous PASS (data + tests +
  docs); same shape as iter-14/15 PRs.
- **Demo wall-clock**: ~12 min initial chain + ~4
  min retry + auto-approve wait. Total ~16 min.

## Ready-to-paste prompt for iter-17

Lives in `docs/iterations/iter_17_handoff.md`.
