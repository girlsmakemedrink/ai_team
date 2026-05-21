# Iteration 25 — reproducibility check + strategic surface

> **Status**: DRAFT — owner approved starting with the
> reproducibility check.
> **Branch**: `worktree-iter-25` (cut from `a4c012d`).
> **Predecessor**: `iter_24_retro.md` + `iter_25_handoff.md`.
> **Scope**: confirm iter-24's clean Backend DONE was not a
> lucky LLM sample. If reproducible → strategic question
> for the owner ("what next?"). If flaky → identify the
> remaining instability.

## TL;DR

iter-24 closed the 5-iter QA criterion in a single real-LLM
demo. That's one data point. iter-25 runs the same demo
2 more times to confirm Backend DONE is **stable across
LLM samples**. Three consecutive successes proves the
iter-19..24 architecture is sufficient for the sandbox
task; a flaky outcome means there's residual instability
to diagnose before pivoting to a real product.

Plus the small operational fix from iter-25 handoff #3:
post-success poll-loop drain so QA's audit row gets
written before the EXIT trap kills the dispatcher.

## Goals

1. **(P0)** Establish whether iter-24's Backend DONE
   chain is reproducible across 2-3 consecutive demo
   runs.
2. **(P1)** Add a 60s post-success drain to the demo
   poll loop so QA's `task_report` audit row gets
   written before EXIT trap shutdown (iter-24 Caveat B).
3. **(P0, post-evidence)** Surface the strategic
   question for the owner: keep iterating on the
   sandbox, pivot to a real product, or close
   deferred carry-overs first.

## Non-goals

- Committing the `examples/sandbox/idea-validator/`
  scaffold to main (iter-25 handoff #4) — deferred
  until the strategic decision is made. If owner
  picks a real product (option b), the sandbox
  scaffold may become obsolete.
- Carry-overs ≥5 in iter-25 handoff — explicitly
  deferred.
- Any new substrate, schema, or prompt changes —
  iter-25 is a reproducibility iteration, not a
  feature iteration.

## Phases

### Phase 0 — Plan + branch ✅ (in flight)

- [x] Cut `worktree-iter-25` from `origin/main` (`a4c012d`).
- [ ] Write this plan.
- [ ] Surface to owner.

### Phase 1 — Demo script: clone + post-success drain

Clone `scripts/demo_iter_24.sh` → `scripts/demo_iter_25.sh`.
Single change: after the poll loop breaks on
`qa_review_count >= 1`, add a 60-second drain sleep so the
dispatcher can finish publishing QA's outbound `task_report`
and the audit_writer can flush it.

iter-24 demo's audit_log stopped at row 384 (Frontend
DONE). QA's row was missing because the EXIT trap fired
before QA's outbound message reached the audit. The
60-second drain solves this without complicating the
success-detection logic.

**Files**:
- Create: `scripts/demo_iter_25.sh` (clone + 1 small edit)
- Modify: `Makefile` (demo-iter-25 target + demo alias)
- Comment-warn: `scripts/demo_iter_24.sh` HISTORICAL

### Phase 2 — Validation gates

`uv run pytest tests/unit -q && uv run ruff check . &&
uv run ruff format --check . && uv run mypy . && make sec`.

No new tests this iteration (the demo script is a
shell-script change; integration tests don't exercise it
directly). Just confirm no regression from the brief
edits.

### Phase 3 — Reproducibility check (real-LLM)

Run `AI_TEAM_DEMO_NON_INTERACTIVE=1 bash
scripts/demo_iter_25.sh` 2 consecutive times. (iter-24's
demo is run #1 of the reproducibility sample by extension —
N=3 total.)

**Per-run record**:
- Correlation ID
- Pass/fail criterion (QA-emitted pending_reviews row)
- Backend behavior (DONE / BLOCKED / timeout)
- Total cost (audit_log sum)
- Wall-clock
- Any anomalies

**Decision rule**:
- **3/3 (counting iter-24)**: architecture is stable.
  Proceed to Phase 4 strategic surface with confidence.
- **2/3**: one anomaly. Document but architecture is
  mostly OK; strategic decision proceeds with a noted
  flakiness risk.
- **1/3 or 0/3**: significant flakiness. Phase 4
  becomes "what's still unreliable?" instead of
  "what's next?"

### Phase 4 — Strategic surface in retro

Based on Phase 3 evidence, the iter-25 retro presents
the strategic options to the owner:

- **(a) Keep iterating on sandbox** — add features to
  idea-validator. Pros: continues exercising the
  framework. Cons: framework stays in self-test mode
  indefinitely.
- **(b) Pivot to a real product** — pick a monetizable
  idea (from `docs/sandbox/` or new), have the team
  build it from a fresh PRD. Pros: finally produces
  commercial value. Cons: discovers framework
  limitations under a different shape of work.
- **(c) Stabilization phase** — close deferred
  carry-overs (HoldQueue persistence, GitHubTargetRepo,
  BaseAgent refactor, ≥5) before new product work.
  Pros: pays down debt. Cons: invests in cleanup the
  framework may not need under different products.

iter-25 retro recommends (b) iff Phase 3 = 3/3, OR
(c) iff Phase 3 < 2/3.

### Phase 5 — Retro + iter-26 handoff + PR merge

Standard close-out.

## Risks + mitigations

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| One of 2 demo runs fails | Medium | Document the specific failure shape; 2/3 is still informative; only blocks pivot if a clear regression. |
| Both runs fail differently | Low | iter-24 contracts are layered; complete chain failure across 2 runs suggests a substrate/quota issue. Capture API logs (now preserved) and analyze. |
| Cost overrun | Low | 2 demos × ~$2 = ~$4. Plus minor docs ~$0. Plenty of headroom in $5 ceiling. |
| Owner not ready to decide strategic | Low | Plan still produces valuable evidence; strategic decision can defer to iter-26. |

## Hard constraints (unchanged from iter-24)

All carry forward. iter-25 has no new architectural
constraints — it's a reproducibility iteration.

## Cost / time

| Phase | Cost | Time |
|-------|-----:|-----:|
| 0 Plan | $0 | 15 min |
| 1 Demo script | $0 | 10 min |
| 2 Gates | $0 | 10 min |
| 3 Reproducibility (2 demos) | ~$4 | ~50 min |
| 4 Retro draft | $0 | 20 min |
| 5 PR + merge | $0 | 15 min |
| **Total** | **~$4** | **~2 h** |
