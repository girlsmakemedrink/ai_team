# Iter-23 real-LLM demo — report

- **Date**: 2026-05-21
- **Run by**: Claude (Opus 4.7) per `docs/iterations/iter_23.md` Phase 6
- **Script**: `AI_TEAM_DEMO_NON_INTERACTIVE=1 bash
  scripts/demo_iter_23.sh`
- **Task**: idea-validator v2 (same shape as iter-17..22)
- **Outcome**: **PARTIAL — the iter-23 core deliverable (QA Python
  safety net) was decisively proven by the Phase 2 end-to-end test
  (`tests/integration/test_qa_request_human_review_real_llm.py`,
  3/3 PASSED). The two full chain demo attempts did NOT reach QA
  due to upstream Backend issues that surfaced new defects each
  time. The QA-emitted `pending_reviews` row criterion is closed
  in isolation but not via the full chain; "criterion met"
  remains pending until iter-24's upstream stability work.**

## Verdict in one line

**iter-23's safety net works — but the full demo chain still
doesn't reach QA. Two distinct upstream Backend failure modes
surfaced (blocked_on routing + budget-exhaustion theory), neither
of which the iter-23 safety net is designed to address. The
isolated Phase 2 e2e test proves that when QA's turn DOES run,
the row lands deterministically.**

## Two demo runs

### Run #1 — correlation `6e294dad-f275-4fb5-b70f-247ff1a7dff2`

- t+0m: TL decomposed, dispatched 6 agent assignments (rows 345-351).
- t+5m: PM, Architect, Designer, Frontend all DONE (rows 352-355).
- t+15m: Backend BLOCKED (row 356) with
  `blocked_on="tests can't be collected in clean branch: examples/
  is untracked in iter-2c and absent from main; be_core-data
  requires 3 production files in a clean worktree, exceeding the
  2-file scope limit"`, duration 428s, cost $0.41.
- t+15m → t+45m: **chain stalled**. No new audit rows.

**Root cause**: TL's iter-21 re-decomposition handler
(`agents/team_lead/agent.py:273`) required EXACT match against
the canonical token `"task_too_large"`. The LLM filled `blocked_on`
with a verbose free-form sentence describing the scope problem
instead. Auto-re-decomp didn't fire; chain never reached QA.

**Hot-fix attempt #1** (commit `82ba755`):

1. `agents/backend_developer/agent.py` — added enum constraint to
   `BACKEND_REPORT_SCHEMA["properties"]["blocked_on"]` restricting
   it to `["task_too_large", "budget", "mcp_unhealthy", null]`.
   Intent: `--json-schema` physically rejects free-form strings;
   the LLM is forced to use a canonical routing token.
2. `agents/team_lead/agent.py:273` — added substring fallback
   (`"task_too_large" in bo.lower()`) as belt-and-suspenders.
3. `prompts/backend_developer.md` — explicit "MUST be the literal
   string `task_too_large` — no elaboration" instruction. Pin
   test added.

### Run #2 — correlation `c941d96a-b9ee-4575-aeb6-812f297dd8e8`

- t+0m to t+5m: same shape — PM/Architect/Designer/Frontend all DONE.
- t+15m: **Backend BLOCKED with `blocked_on="budget"`** (row 369,
  empty `metadata.llm`). Iter-6's
  `LLMBudgetExhaustedError`-synthesis path — Backend's `claude -p`
  subprocess exhausted its $2.50 per-call max budget cap before
  producing any structured response.
- t+44m: demo's 45-min poll expired. Phase 6.5/7 retry-blocked
  triggered:
- Row 370: TL re-assigned Backend (the `ai-team retry-blocked`
  manual recovery step).
- Row 371: Backend BLOCKED(budget) AGAIN. Same shape.
- **Final criterion check: ✗ qa_engineer pending_reviews count=0.**

**Most likely root cause**: the enum constraint on `blocked_on`
introduced in hot-fix attempt #1 caused `claude -p`'s
`--json-schema` validation to enter a retry loop. The LLM kept
producing free-form `blocked_on` strings (its natural behavior,
unchanged from run #1); each one failed schema validation;
`claude -p` retried internally until the $2.50 per-call budget
was exhausted. **No direct evidence** (the API log was cleaned up
by the EXIT trap) but the audit-log shape is consistent and the
timing matches.

### Decision: revert enum, ship as-is

Commit `88402b8` reverts the enum constraint back to
`{"type": ["string", "null"]}`. The routing defense now relies on:

- TL substring matcher (`"task_too_large" in bo.lower()`) — handles
  any blocked_on that mentions the canonical token anywhere.
- Backend prompt's explicit literal-token instruction.

Neither defense catches run #1's pure-free-form blocked_on
(no `task_too_large` substring), but the prompt change reduces
the likelihood. iter-24 needs a more robust scope-detection
mechanism — see "Action items" below.

A third demo run was NOT attempted. Two consecutive ~$2 demo
runs had already shown the chain doesn't reliably reach QA for
reasons unrelated to the iter-23 safety net. Burning a third
~$2 wasn't going to add evidence beyond what the e2e test
already proves.

## What worked (major wins)

### Win #1 — QA Python safety net validated 3/3 end-to-end

`tests/integration/test_qa_request_human_review_real_llm.py`:
3 parametrized runs against real Postgres + real `claude -p`,
each one synthesizing a Backend `task_report(done)`-shaped
TaskAssignment and observing the safety net behavior.

```
[run 0] qa.safety_net.row_inserted reason=llm_skipped_request_human_review_tool
[run 1] qa.safety_net.row_inserted reason=llm_skipped_request_human_review_tool
[run 2] qa.safety_net.row_inserted reason=llm_skipped_request_human_review_tool
3 passed in 220.01s (0:03:40) — total cost $0.10.
```

**Key observation**: in EVERY run, QA's LLM produced a valid
schema-conformant QA JSON but did NOT invoke
`mcp__ai_team_tasks__request_human_review`. The safety net wrote
the `pending_reviews` row directly via the injected
`session_factory` each time. **Without this safety net, the row
would never have appeared regardless of how long the demo polled.**

This is the iter-23 core deliverable. It works.

### Win #2 — Decisive root-cause Phase 1 diagnostic

Phase 1 of iter-23 (Pre-Phase-2) ran the same QA test BEFORE the
safety net existed and observed 0/3 tool-call invocations. That
single $0.15, 15-min experiment overturned 4 iterations of
"the QA blocker is upstream timing" diagnosis: the LLM was the
actual culprit, just never observed because the chain hadn't
reached QA in real conditions.

Inverting the iter-23 handoff's prescribed order (do the demo
first, hope for the criterion) saved ~$2 + 45 min by collapsing
all uncertainty into a $0.15 experiment.

### Win #3 — iter-21/22 contract layer continues to hold

- Backend self-eject prompt path fired in run #1 (BLOCKED on turn
  1, ~7 min not 600s timeout — improvement over iter-19/20/21).
- TL Architect→Backend depends_on rule applied (HoldQueue held
  Backend until Architect's ADR landed).
- All 4 non-Backend agents (PM/Architect/Designer/Frontend) DONE
  cleanly in run #1, similar in run #2.

### Win #4 — Cost trend

| Iter | Cost      | Notes                                          |
|-----:|----------:|------------------------------------------------|
| 19   | $2.00     | Backend timed out, no QA                       |
| 20   | $4.25     | Backend timed out (Architect spike)            |
| 21   | $1.97     | Backend timed out, no QA                       |
| 22   | $2.02     | Backend self-ejected; QA in flight on poll exit |
| 23 R#1 | ~$2.10  | Backend BLOCKED (free-form blocked_on)         |
| 23 R#2 | ~$1.60  | Backend BLOCKED(budget) twice                  |

Combined iter-23 demo spend ~$3.70, plus $0.15 Phase 1 + $0.10
Phase 2 e2e = ~$4.00 total. Within the $5/iteration ceiling.

## What didn't (caveats)

### Caveat A — QA-emitted `pending_reviews` row deferred for 5th iter

The full real-LLM demo's chain did not reach QA in either run.
**5-iteration deferred** (was 4 entering iter-23). But the
failure mode has shifted again:

- iter-19/20/21: Backend timed out FATALLY, cascade-dropped QA.
- iter-22: Backend self-ejected cleanly; demo poll expired with
  Backend recovery turn in flight.
- iter-23 R#1: Backend self-ejected with non-canonical
  `blocked_on`; TL exact-match failed; chain stalled at Backend
  BLOCKED → no QA invocation.
- iter-23 R#2: Backend BLOCKED(budget) before producing any
  structured output (likely schema-enum-induced retry loop;
  unverified).

The pattern across all 5 iterations: **the chain has never
delivered QA a clean Backend DONE in a real-LLM demo**. That's
the upstream stability problem iter-24 needs to address.

But the iter-23 e2e test demonstrates that **when QA does get
to run, the safety net produces the row deterministically**.
The architectural fix is shipped; what's missing is upstream
reliability.

### Caveat B — Hot-fix #1 (enum constraint) likely caused budget burn in R#2

Without the API log it can't be confirmed, but the
audit-log/timing shape is consistent with `claude -p`'s
`--json-schema` validation rejecting LLM-produced free-form
`blocked_on` strings and retrying internally until the $2.50
per-call budget cap fires `LLMBudgetExhaustedError`. iter-24
should run an A/B mini-test (with/without enum on the same
prompt) to confirm or rule out this theory before re-introducing
strict validation anywhere.

### Caveat C — Backend's preflight reasoning sometimes elaborates

Run #1's `blocked_on` was: "tests can't be collected in clean
branch: examples/ is untracked in iter-2c and absent from main;
be_core-data requires 3 production files in a clean worktree,
exceeding the 2-file scope limit". The LLM made a thoughtful
diagnostic call but routed it through the wrong field — should
have been in `summary`. Even with iter-23's "MUST be the literal
string" prompt update, the LLM may still drift. A safer fix:
**detect "Scope pre-flight:" in `summary` as a structural
indicator and ignore `blocked_on` entirely for routing
purposes**. iter-24 candidate.

### Caveat D — Backend's notion of "clean branch" matters

Run #1's blocked_on noted "examples/ is untracked in iter-2c
and absent from main". The worktree-iter-23 branch (cut from
origin/main) doesn't have `examples/` committed; previous demos
had it staged-but-not-committed in the orchestrator worktree.
Backend's `git worktree add` to a fresh branch from main does
not carry untracked files, so Backend correctly observes
"empty examples/ directory" and treats it as a problem.

This is actually a separate issue from blocked_on routing.
Either commit a `examples/sandbox/idea-validator/` scaffold to
main, or teach Backend that a missing target directory is
acceptable (it WRITES the scaffold). iter-24 candidate.

### Caveat E — Frontend BLOCKED on architecturally-prohibited request (same as iter-21/22)

Spec-correct refusal, not a regression.

## Cost / quota

| Component               | Cost   | Notes                                |
|-------------------------|-------:|--------------------------------------|
| Phase 1 diagnostic      | $0.15  | 3 runs × 5 min, decisive 0/3         |
| Phase 2 e2e validation  | $0.10  | 3 runs × 73s, 3/3 PASSED             |
| Demo R#1                | ~$2.10 | TL exact-match bug                   |
| Demo R#2                | ~$1.60 | Likely enum-induced budget burn      |
| **Total iter-23**       | **~$4.00** | Under $5 ceiling                |

## Stats

- **Wall-clock**: ~3 hours including planning, TDD, both demo
  runs, hot-fix, revert, retro.
- **Cost**: ~$4.00 observable.
- **Unit tests**: 441 (+8 vs iter-22: 4 QA safety net, 1
  retry_blocked, 1 TL substring, 2 Backend schema/prompt pins).
- **Integration tests**: 50 + 1 dual-marker real_llm
  (3 parametrize runs).
- **Orchestrator HEAD**: stayed on `worktree-iter-23` throughout
  both demo runs.
- **`pending_reviews` row in demo**: NOT WRITTEN — 5-iteration
  deferred at the chain level, but the safety net is proven in
  isolation.
- **Architect spend**: $0.65/$0.59 — well within baseline range.

## Action items for iter-24

1. **(NEW TOP)** **Backend stability — Round 2.** Both
   iter-23 demo runs failed at Backend before reaching QA. The
   chain has not delivered a clean Backend DONE in any of
   iter-19→23. iter-24 needs a focused investigation of
   *why* Backend struggles:
   - Run #1: scope self-eject worked, routing failed.
   - Run #2: budget exhaustion before structured output (likely
     enum-retry-loop; needs A/B verification).
   Concrete steps:
   - A/B test: same prompt, with vs without `--json-schema` enum
     on a field. Observe whether enum violations trigger budget
     burns. If confirmed, document as a substrate-level pitfall
     in CLAUDE.md and ADR-008.
   - Add log capture to demo's EXIT trap — preserve the API log
     in `docs/iterations/iter_24_demo_logs/<correlation>.log`
     for forensic analysis.

2. **(NEW)** **Structural scope-detection in TL instead of
   blocked_on routing.** Per Caveat C: detect
   `"Scope pre-flight:"` in the `summary` field as the canonical
   self-eject signal, regardless of `blocked_on` content. The
   summary template in `prompts/backend_developer.md:25` already
   starts with that prefix.

3. **(NEW)** **Commit `examples/sandbox/idea-validator/` scaffold
   to main.** Per Caveat D: Backend's `git worktree add` from
   main can't see untracked files in the orchestrator worktree.
   A minimal scaffold (just empty `__init__.py` + README) avoids
   the false BLOCKED.

4. **(NEW)** **Confirm or deny the enum-retry-loop theory.**
   See action #1's A/B test. If confirmed, document; if denied,
   we have a different undiagnosed budget-burn cause to chase.

5. **Re-attempt QA-emitted `pending_reviews` row in full demo.**
   5-iteration deferred. With #1 closed (Backend reaches DONE),
   the iter-23 safety net (already shipped) will land the row.
   Conservative estimate: iter-24 first try should succeed if
   the upstream chain delivers QA's turn.

6. **Carry-overs unchanged from iter-23 handoff items 5-15.**

## Why this demo matters

**iter-23 shipped the right architectural fix and proved it
works**. The 4-iteration "QA blocker" theory of "demo poll
window expired" was decisively wrong — Phase 1's $0.15
experiment showed the LLM has been silently failing to call the
MCP tool the entire time. The Python-side safety net closes
that gap structurally.

**But the demo also surfaced a deeper problem**: the chain has
never delivered Backend DONE in 5 iterations. Each iter found a
different upstream Backend failure mode. iter-23's enum-revert
suggests `--json-schema` constraints may themselves be a
substrate-level pitfall that needs careful handling.

iter-24's job is to make Backend reliable enough that the
already-proven safety net can do its work in production
conditions.
