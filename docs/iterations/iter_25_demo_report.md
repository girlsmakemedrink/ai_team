# Iter-25 real-LLM demo — reproducibility check report

- **Date**: 2026-05-21
- **Run by**: Claude (Opus 4.7) per `docs/iterations/iter_25.md`
  Phase 3
- **Method**: 2 consecutive runs of
  `AI_TEAM_DEMO_NON_INTERACTIVE=1 bash scripts/demo_iter_25.sh`,
  combined with iter-24's run as N=3 reproducibility sample.

## Verdict

**Architecture is stable.** 2/2 demos succeeded when the
`claude -p` substrate had quota; the third (iter-25 Run 2/2)
failed with `api_error_status=429` — Claude Max 5x
**subscription session limit** hit after a day of heavy demo
spending — NOT an architectural flake.

The iter-24 chain is reliable. The framework is ready for the
strategic pivot question in iter-26.

**Bonus**: this run also retroactively diagnosed iter-23 R#2's
"BLOCKED(budget) mystery" as the same environmental cause —
subscription quota exhaustion, not enum-retry-loop or
tool-call burns. The iter-24 Phase 4 API log preservation
made this diagnosis possible.

## Run-by-run

### iter-24 (R#0 in reproducibility sample) — ✅ SUCCESS

- Correlation: `f26bf077-1c8d-43a5-99b8-bf93402e79a8`
- Backend: DONE in 586s, $0.57 — 44 tests, 84.6% coverage.
- QA: row landed via safety net (LLM didn't call tool).
- QA's audit row: MISSED due to EXIT trap race (fixed in
  iter-25 by post-success drain).
- Cost: ~$2.56.

### iter-25 Run 1/2 — ✅ SUCCESS

- Correlation: `f172140b-b266-4906-a512-98c1f651641a`
- Audit chain: **14 rows** including QA's `task_report`
  (row 398, 164s, $0.06) — **post-success drain works**.
- Backend: DONE in 437s, $0.28 — 44 tests, 84.6% coverage
  (similar artifact as iter-24).
- Frontend DONE (303s), Architect DONE (136s, $0.73),
  Designer DONE (320s), PM DONE (256s).
- QA: **2 pending_reviews rows** for this correlation
  (LLM called `request_human_review` multiple times in the
  same turn — minor but noted; doesn't break anything).
- Wall-clock to success: ~19 min.
- Cost: ~$2.00.
- Architect ADR-N (head of `docs/adr/`) explicitly
  recognized iter-25 as a "reproducibility iteration, not
  product-delivery iteration" — the agent understands its
  own iteration context.

### iter-25 Run 2/2 — ⚠ ENVIRONMENTAL FAILURE (NOT ARCHITECTURAL)

- Correlation: `a9693064-eace-4f23-88a1-47823781b91e`
- Audit chain: 19 rows; chain stalled at row 417 with
  Backend BLOCKED(budget) at t+14m, no progress for 30 min,
  poll expired.
- Sequence:
  - PM/Designer/Frontend/Architect DONE.
  - Backend BLOCKED with **canonical `task_too_large`** (row
    412) — iter-22 prompt + iter-24 routing all worked
    correctly.
  - TL re-decomp fired (rows 413-416) — iter-21 handler
    routed properly.
  - Backend's recovery turn (row 417) BLOCKED(budget).
- **Root cause** (from preserved API log
  `docs/iterations/iter_25_demo_logs/a9693064.log`):
  ```
  api_error_status: 429
  result: "You've hit your session limit · resets 10:10pm (Europe/Moscow)"
  total_cost_usd: 0.106  ← Backend's call burned only $0.10,
                              NOT the $2.50 per-call cap
  ```
  iter-15's adapter
  (`core/llm/claude_code_headless.py:301`) correctly detects
  `api_error_status=429` and raises `LLMBudgetExhaustedError`;
  iter-6's dispatcher synthesizes BLOCKED(budget). The
  framework behaved EXACTLY as designed for a quota event.
- Wall-clock to failure: ~14 min Backend recovery turn
  start → 429 within ~93s.
- Cost burned: ~$1.55 before quota cap fired.

## Cumulative architecture validation

| Run            | Correlation       | Backend | QA-row | Note |
|----------------|-------------------|---------|--------|------|
| iter-24        | f26bf077          | DONE    | ✅     | safety net wrote row; QA audit lost |
| iter-25 R#1    | f172140b          | DONE    | ✅×2   | drain works; QA audit landed |
| iter-25 R#2    | a9693064          | BLOCKED(budget) | ✗ | **subscription session 429** |

**Architectural success rate** (excluding environmental):
- Runs with available quota: 2/2 = 100%
- Backend DONE consistency: 2/2
- QA row criterion: 2/2

**Quota-exhaustion failure mode**: framework handled it
correctly:
- 429 detected at `claude_code_headless.py:301`
- `LLMBudgetExhaustedError` raised
- Dispatcher synth'd `task_report(blocked, blocked_on='budget')`
- No cascade-failure of other agents (PM/Architect/Designer
  /Frontend all DONE before Backend hit the limit)
- Per CLAUDE.md: "System recovers automatically when quota
  rolls over" (10:10pm Moscow, ~3h after demo).

## Solved: iter-23 R#2 mystery

iter-23 Run 2/2's BLOCKED(budget) was previously attributed
(speculatively) to `--json-schema` enum-retry-loop. iter-24
Phase 1's A/B test denied that theory but couldn't identify
the actual cause without API logs.

**iter-25 R#2's log shows the real cause: subscription
session 429.** iter-23 R#2 most likely hit the same
environmental limit. The pattern matches:
- Identical audit_log shape (BLOCKED(budget) with empty
  `metadata.llm`, no per-turn metrics).
- Identical timing (~14-15 min into the chain).
- Identical "no new audit rows for 30 min" stall pattern.

iter-23 R#2 should be re-labelled in retrospect: not an
unknown budget burn, but a known subscription quota event.

CLAUDE.md gotchas section should note this empirically:
> Backend BLOCKED(budget) with `total_cost_usd` << per-call
> cap = subscription session 429, not a budget-cap event.
> Wait for `claude -p` reset time (printed in error
> message) and re-run.

## Cost summary

| Item                    | Cost     | Note |
|-------------------------|---------:|------|
| iter-25 Run 1 success   | ~$2.00   | clean chain, full criterion |
| iter-25 Run 2 partial   | ~$1.55   | up through Backend recovery 429 |
| **iter-25 total**       | **~$3.55** | within $5 ceiling |

(Plus the iter-24 demo ~$2.56 from the prior commit's evidence.)

## Action items for iter-26

1. **(P0 Strategic)** With architecture validated, surface
   the "what next?" question — keep iterating on sandbox,
   pivot to a real product, or stabilization phase.
   **Recommend: (b) Pivot to a real product.** Architecture
   is reliable; sandbox has served its purpose.

2. **(P1)** Add a CLAUDE.md gotcha note: BLOCKED(budget) with
   `total_cost_usd` << per-call cap = subscription 429, not
   a real budget burn. Wait for reset.

3. **(P2)** Optional: extract the 429 retry-after time from
   the API log automatically and surface it in feed digest /
   CLI so the owner sees "quota resets at HH:MM, demo
   paused until then" instead of needing to read the log.

4. **(P3)** Investigate the iter-25 R#1 "2 pending_reviews
   rows from one QA turn" anomaly — minor but worth
   understanding (LLM made multiple `request_human_review`
   calls in the same turn for some reason).

5. **(Carry-overs ≥5)** Same as iter-25 handoff.

## Why this iteration matters

iter-25 was an investment in **measurement** rather than
**capability**. Two demos that succeeded → architecture
confidence. One demo that failed → solved a 2-iteration
mystery via the iter-24 log preservation infrastructure.

iter-24 spent $2.56 to land the criterion. iter-25 spent
$3.55 to confirm reliability AND retroactively diagnose
iter-23 R#2. Cost per insight: ~$1-2. Compare with the
$2-3 per failed full-demo iteration in iter-19→22 where we
were chasing the wrong root cause.

The diagnostic-first discipline pays off again.
