# Iteration 25 retrospective

> **Status**: closed — iter-25 confirmed iter-24's
> architecture is stable across LLM samples, retroactively
> diagnosed the iter-23 R#2 "BLOCKED(budget) mystery", and
> validated the iter-24 Phase 4 API log preservation
> investment.

## Headline outcomes

✅ **Reproducibility confirmed.** 2/2 demos with available
quota produced the criterion (Backend DONE → QA row).
Backend chain works reliably under real-LLM conditions.

✅ **Post-success drain works.** iter-25 Run 1 produced 14
audit rows including QA's `task_report` (row 398, 164s,
$0.06). iter-24's missing QA audit row was the trap-race
problem the drain fix targets; it's resolved.

✅ **Solved the iter-23 R#2 mystery.** iter-25 Run 2/2's
preserved API log showed `api_error_status=429: "You've
hit your session limit · resets 10:10pm (Europe/Moscow)"`
with `total_cost_usd: 0.106` (far below the $2.50 per-call
cap). The "BLOCKED(budget) budget burn" theory across
iter-23 and iter-24 retros was **environmental, not
architectural** — Claude Max 5x subscription session
quota, not enum-retry-loop, not tool-call burn. The
framework correctly detected the 429 and synthesized
BLOCKED(budget) per iter-15's design.

✅ **iter-24 Phase 4 (API log preservation) paid off
immediately.** Without it, iter-25 R#2's 429 would have
been just another unknowable "BLOCKED(budget)". The log
solved a 2-iteration mystery on its first demo. Best
investment of the iter-23..25 sequence.

## What went well

1. **Tight iteration scope.** iter-25 had ONE code change
   (60s post-success drain) and ran 2 demos. Result: more
   diagnostic value than the previous iterations
   combined, because we knew exactly what we were
   measuring.
2. **Diagnostic discipline carried forward.** iter-23
   Phase 1's mini-test pattern, iter-24's A/B test, and
   iter-25's preserved-log analysis all stack into a
   coherent "instrument first, fix later" methodology.
3. **The iter-24 fixes held across re-runs.** Run 1
   replicated iter-24's success cleanly (Backend DONE,
   QA row); Run 2's failure was external (quota), not a
   regression.
4. **The framework recovered gracefully from quota
   exhaustion.** No cascade failures, no
   uncaught exceptions, clean BLOCKED(budget) synthesis.
   The owner-recovery path (`ai-team retry-blocked`) is
   ready when quota rolls over.

## What didn't go well

1. **Spent ~$3.55 to validate "architecture works".**
   In retrospect, that's a lot. Could the validation
   have been cheaper? Possibly — one re-run instead of
   two might have been enough given the iter-24 result.
   But N=3 sample (counting iter-24) gives stronger
   confidence than N=2.
2. **Run 2's quota exhaustion came as a surprise.**
   I didn't track cumulative spend across the session.
   The iter-23 + iter-24 + iter-25 P1 + iter-25 R#1 had
   already consumed significant Max 5x quota; Run 2 was
   the straw. iter-26 should add a "quota check" step
   before each demo.
3. **2 pending_reviews rows from a single QA turn (Run
   1)** was an unexpected anomaly. Not a bug per se —
   the LLM called `request_human_review` more than once
   — but it suggests the QA prompt could be tighter.

## Lessons learned

- **`api_error_status=429` with `total_cost_usd` << cap
  = subscription quota event**, not a real budget burn.
  This pattern has now appeared 2-3 times (iter-23 R#2,
  iter-25 R#2, possibly others). Should be a CLAUDE.md
  gotcha entry.
- **Preserved logs are worth their weight in retro
  time.** The single line of API log output ("session
  limit · resets 10:10pm") closed a 2-iteration mystery.
  Generalize the iter-24 Phase 4 pattern: any future
  demo script EXIT trap should preserve, not delete,
  observability artifacts.
- **Reproducibility checks pay off when N≥2.** A
  single successful demo (iter-24) doesn't distinguish
  "architecture stable" from "lucky LLM sample". Two
  successes do. Three would be ideal but N=2 + the
  environmental third gives sufficient signal.
- **Don't conflate environmental failures with
  architectural ones.** iter-23 R#2's "BLOCKED(budget)
  retry-loop theory" wasted an A/B test in iter-24 that
  proved nothing wrong with enum constraints. A better
  diagnostic-first move would have been: "preserve the
  log, see what the 429 message actually says."

## Iteration stats

- **Wall-clock**: ~1.5 hours session time.
- **Cost**: ~$3.55 LLM spend (Run 1 ~$2.00 + Run 2
  ~$1.55).
- **Commits to `worktree-iter-25`**:
  - `c5a4f30` — chore(demo): iter-25 reproducibility
    script + post-success drain (Phases 0-2)
  - [pending] — docs(iter-25): demo report + retro +
    iter-26 handoff
- **Tests**: 444 unit (unchanged), 50 integration
  (unchanged), 4 real_llm (unchanged).
- **Files touched**: `scripts/demo_iter_25.sh` (NEW),
  `scripts/demo_iter_24.sh` (HISTORICAL comment),
  `Makefile` (target + alias).
- **Demos run**: 2 (1 success, 1 quota-blocked).

## Updated trend table (now N=3)

| Run            | Backend | QA-row | Cost | Note |
|----------------|---------|--------|------|------|
| iter-24        | DONE    | ✅      | $2.56 | first clean chain |
| iter-25 R#1    | DONE    | ✅      | $2.00 | drain works; QA audit landed |
| iter-25 R#2    | BLOCKED(budget) | ✗ | $1.55 | **quota 429 — environmental** |

Architectural success rate (quota-available runs): **2/2**.

## Strategic surface (Phase 4 output)

iter-25 was the reproducibility iteration before any
strategic pivot. The owner can now decide with evidence:

- **(a) Keep iterating on the sandbox** — Pros: known
  shape, continues exercising framework. Cons: framework
  stays in self-test mode; sandbox is now "done" — what
  more is there to validate?
- **(b) Pivot to a real product** ⭐ **RECOMMENDED** —
  architecture is reliable; framework is ready for a
  different shape of work. Pick a monetizable idea (from
  `docs/sandbox/idea_validator_*.md` or new), fresh PRD,
  let the team build. Risk: discovers framework
  limitations under unfamiliar shape — but those are
  the discoveries worth making.
- **(c) Stabilization phase** — close ≥5 carry-overs
  (HoldQueue persistence, GitHubTargetRepo, BaseAgent
  refactor) before product work. Pros: pays down debt.
  Cons: invests in cleanup the framework may not need
  under different products.

iter-26 should open with this decision.

## Action items for iter-26

See `docs/iterations/iter_26_handoff.md`. Top items:

1. **(STRATEGIC)** Pick (a)/(b)/(c). Recommend (b)
   pivot.
2. **(P1)** Add CLAUDE.md gotcha: 429 with low
   `total_cost_usd` = subscription quota, not budget
   cap.
3. **(P2)** Pre-demo quota check to avoid the iter-25
   R#2 surprise.
4. **(P3)** Investigate "2 pending_reviews per turn"
   anomaly (iter-25 R#1).
5. **(Carry-overs ≥5)** Same as iter-25 handoff.

## What iter-25 specifically did NOT do

- Did not commit an `examples/sandbox/idea-validator/`
  scaffold to main (deferred until strategic decision).
- Did not address any carry-over ≥5.
- Did not investigate the "2 pending_reviews" Run 1
  anomaly (P3 carry-over to iter-26).
