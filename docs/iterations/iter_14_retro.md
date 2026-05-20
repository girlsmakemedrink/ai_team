# Iteration 14 — Retrospective

**Closed**: 2026-05-20. 5 commits on `worktree-iter-14`
(plan + router tuple + demo script + demo report +
retro/handoff). All gates green; real-LLM demo run captured
in `docs/iterations/iter_14_demo_report.md`.

**Headline**: iter-14 shipped its tactical deliverable
clean (one pattern tuple `("mcp__ai_team_repo", "never
connected")` + 1 unit test pinning iter-13's row 180
verbatim summary), but the real-LLM demo's Backend
invented a FIFTH distinct MCP-race phrasing — "**failed
to connect**" + "**not available**" — none of the six
current tuples match. **The pattern-tuple approach is
empirically diminishing-returns**: three iterations
(iter-12/13/14) of one-tuple-per-iteration, three demos
where Backend picks new wording. **iter-15 needs a
structural move, not another tuple**.

## What shipped

Phase 0 — Plan (`docs/iterations/iter_14.md`, 506 lines)
committed on `worktree-iter-14` cut from `origin/main` at
`ced1642`.

Phase 1 — `_MCP_RACE_PATTERNS` extension + 1 new unit
test:

- One new tuple `("mcp__ai_team_repo", "never connected")`
  appended at `core/dispatcher/mcp_race_router.py:60-69`
  with explanatory comment + iter-13 demo reference.
- Module docstring's historical-list updated with iter-13
  demo's wording entry.
- `test_routes_iter13_demo_backend_summary_to_blocked`
  pins iter-13 row 180 summary verbatim (TDD: started as
  RED — my first draft summary accidentally contained
  "unavailable" which the iter-12 tuple already catches;
  rewrote summary to drop "unavailable" before the new
  tuple was added; tuple then matched as expected).
- All 7 router tests pass; all 373 unit tests pass; no
  regressions.

Phase 2 — Demo script + real-LLM run + report:

- `scripts/demo_iter_14.sh` clone of `demo_iter_13.sh`
  with header narrative updated; iter-13 auto-retry-blocked
  + auto-approve tail preserved; `.iter13-mcp.json` →
  `.iter14-mcp.json`.
- `Makefile` `demo` alias points at iter-14; iter-13 stays
  as regression baseline.
- Two real-LLM runs:
  - **Run #1**: Architect hit Anthropic Max-5x session
    limit (HTTP 429, "resets 12:10pm Europe/Moscow") at
    row 190. Cost: $0.59 burned. Authoritative
    quota-exhausted signal per ADR-008.
  - **Run #2** (after 12:10 MSK reset): Full chain shape
    executed but Backend hit the MCP race at startup with
    FOURTH distinct phrasing. PM/Architect/Designer/
    Frontend all done; Backend FAILED (4¢/75s — barely
    started); QA cascade-dropped. Cost: $1.89.
- Grand total: $2.48 across both runs. Under the $5
  ceiling but expensive for a non-closing demo.
- Demo report (`docs/iterations/iter_14_demo_report.md`,
  ~360 lines) documents outcome 4c + the full
  cross-product-matcher design for iter-15.

Phase 3 — Final gate sweep + retro/handoff + merge.

## What went well

- **TDD caught my own bug.** First draft of the new unit
  test PASSED immediately — TDD's RED-first discipline
  caught that my test summary text already contained
  `"unavailable"` (caught by an iter-12 tuple), so the
  test wasn't actually proving the new tuple did anything.
  Rewrote the summary to drop "unavailable" → test went
  RED → new tuple added → test went GREEN. Without TDD
  this would have shipped a no-op tuple.
- **Quota-truncation handled gracefully.** Run #1's
  Architect 429 didn't corrupt state. Dispatcher
  synthesized `task_report(failed)` per iter-5's
  exception path; cascade correctly dropped dependents;
  no orphan rows; chain HMAC intact.
- **Demo script's `docker exec` papercut from iter-13
  stayed fixed.** No host-psql auth-fails on either run.
  Commit `1a24699` is durable.
- **Cost discipline held even with quota burn.** $2.48
  total vs $5 ceiling. iter-13's $1.86 is the natural
  baseline.
- **Outcome 4c was explicitly planned for.** Plan's
  Phase 2 success criteria #4c covered this exact
  eventuality, and the iter-14 risk section flagged
  "MCP race fires with a fourth distinct phrasing —
  iter-15 picks up another tuple OR moves to a more
  general design." No surprise at the negative outcome.

## What didn't

- **The `pending_review` loop did not close.** Fourteen
  demos in a row now. iter-14 reached the same shape as
  iter-13 (chain runs, Backend FAILED, QA cascade-dropped)
  but with Backend giving up faster (75s vs 544s) — the
  pre-iter-9 startup-time MCP race recurred this run.
- **Pattern-tuple approach showing diminishing returns.**
  After 5 tuples across iter-10/12/14:
  - iter-9 phrasing: "MCP server ai-team-repo never connected"
  - iter-11 phrasing: "mcp__ai_team_repo__* tools were unavailable"
  - iter-13 phrasing: "mcp__ai_team_repo server never connected"
  - iter-14 phrasing: "MCP server ... failed to connect" + "tools ... not available"
  - Three consecutive iterations of one-tuple-per-
    iteration; three consecutive demos where Backend
    invented new wording. The LLM's natural-language
    variation outpaces the matcher's incremental scaling.
- **Architect cost spiked iter-12 $0.59 → iter-13 $0.84
  → iter-14 $0.98**, despite no new content (Architect
  re-derived ADR-0021 already on disk from iter-13). The
  TL-over-decomposition prompt-hint carry-over is now
  visibly expensive — Architect's $0.98 of $1.89 (run #2)
  is half the chain's spend.
- **Backend's `--resume` continuation tree on disk
  (`examples/sandbox/idea-validator/`) didn't help this
  run** — Backend's session never got past ToolSearch
  startup, so it couldn't even re-grep the existing
  implementation. The "iter-13 tree as resume point"
  carry-over hypothesis is correct in principle but
  requires Backend to actually start a session.

## Surprises

- **Backend's failure mode shifted from mid-session race
  (iter-11/12/13) to startup-time race (iter-14, like
  iter-7/8/9 baseline).** Earlier hypothesis (long sessions
  → bigger MCP-race window) was that race exposure
  correlates with session length. iter-14 saw the race fire
  in the first 75s of a Backend session that wouldn't have
  needed to be long. Suggests the MCP-subprocess race is
  not purely a "long-running" phenomenon — there's a
  startup-time variant the iter-9 pre-flight gate doesn't
  catch (in-process probe passes; claude -p's spawned MCP
  fails).
- **Quota session limit hit DESPITE smoke-llm passing 5
  min earlier.** The 12:10 MSK reset was 30 min before
  the smoke run, but smoke uses haiku tier (cheap, low
  token count); the demo's opus/sonnet calls quickly
  consumed enough quota to trip the session window.
  Smoke isn't an early-warning indicator for session
  quota.

## Action items for iter-15

The demo report has the full design under "Failure 1 →
option 1" (cross-product matcher); below is the
prioritised handoff. **iter-15 should pick option 1
(generalisation) over option 2 (TL decomposition)** as
its Phase-1 deliverable — generalisation is small (~30
LOC + 5 unit tests), tactical, closes the immediate gap
defensibly. TL decomposition is the right next step but
is a separate, larger effort and would be better as a
focused iter-16 / iter-17 with its own plan + dedicated
demo runs.

1. **(top)** **Cross-product MCP-race matcher** —
   `core/dispatcher/mcp_race_router.py`. Replace
   `_MCP_RACE_PATTERNS` (or co-exist with it) with
   `_MCP_TOKEN_SET` × `_MCP_FAILURE_VERB_SET`. Match if
   any MCP-token AND any failure-verb co-occur. Unit-test
   all 5 previously observed phrasings (iter-9, iter-11,
   iter-13, iter-14 startup-race, iter-14 unavailable-
   pattern) + 2 negative-case regression tests (genuine
   AssertionError summary, done-status MCP-mention).
2. **TL Backend decomposition** — SIX-iteration carry-over.
   Pair structurally with #1 in a future iter-16 or pull
   forward if iter-15 #1 finishes fast.
3. **`api_error_status=429` → BLOCKED(blocked_on='budget')**
   in `ClaudeCodeHeadlessClient` or dispatcher. Catches
   the quota-session-limit case (iter-14 run #1) so it's
   recoverable via retry-blocked after reset. ~20 LOC + 2
   tests.
4. **TL over-decomposition prompt hint.** Architect cost
   trajectory iter-12→13→14 ($0.59→$0.84→$0.98) confirms
   re-derivation is happening. Small prompt edit; iter-15
   if scope allows.
5. **HoldQueue persistence (Postgres-backed).**
   In-memory queue keeps losing held assignments on
   restart. Still deferred but actively hurts demos.
6. **Carry-overs unchanged**: `pytest-rerunfailures`
   plugin pin, startup-time MCP investigation (the
   iter-14 demo handed us data here — startup-time race
   reproduces), `audit_writer` Postgres role, hash-chain
   alert, `GitHubTargetRepo`, transactional TL,
   `BaseAgent` template refactor.

## Stats

- **Commits on `worktree-iter-14`**: 5 (plan + router tuple
  + demo script + demo report + this retro/handoff).
- **LOC delta**: +~870 (plan 506 + router 11 + test 30 +
  demo script 28 modified + demo report 360 + retro/handoff
  TBD).
- **Tests**: +1 (`test_routes_iter13_demo_backend_summary_to_blocked`).
  All 415 tests pass (373 unit + 42 integration).
- **Real-LLM spend**: $2.48 across two runs (run #1
  $0.59 quota-truncated Architect; run #2 $1.89 full
  chain Backend-failed). Under the $5 ceiling.
- **Diff-cover**: vacuous PASS (only data + comments
  changed; no executable lines tracked, gate condition
  met).
- **Demo wall-clock**: ~12 min combined (run #1 ~3 min
  before 429; run #2 ~9 min full chain).

## Ready-to-paste prompt for iter-15

Lives in `docs/iterations/iter_15_handoff.md`.
