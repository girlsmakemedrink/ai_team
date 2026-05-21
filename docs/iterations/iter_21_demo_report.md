# Iter-21 real-LLM end-to-end demo — report

- **Date**: 2026-05-21
- **Run by**: Claude (Opus 4.7) per `docs/iterations/iter_21.md`
  Phase 5
- **Script**: `AI_TEAM_DEMO_NON_INTERACTIVE=1 bash
  scripts/demo_iter_21.sh`
- **Task**: idea-validator v2 (same shape as iter-17..20)
- **Correlation ID**:
  `97accb9a-8d28-4a67-a311-e4f65d19edaa`
- **Outcome**: **Partial — iter-21's two contracts
  (Backend tripwire + TL re-decomposition) ship
  cleanly but neither path was exercised in this
  run. TL's natural Backend task description was
  short (~440 chars, no file-path tokens), so the
  tripwire heuristic didn't fire. Backend timed
  out at 600s anyway and reported FAILED, which
  TL has no auto-recovery path for. Architect
  spend dropped back to baseline ($0.80 vs
  iter-20's $2.88) — the climbing trajectory was
  variance, not a trend. QA pending_review row
  remains deferred for the 3rd iteration.**

## Verdict in one line

**The iter-21 commit shape is correct (tripwire +
re-decomp handler land cleanly, all 428 unit
tests pass), Architect spend is back to baseline,
and the bash auto-approve fix works — but the
tripwire heuristic (char count, file-path tokens)
is the wrong heuristic for TL's natural Backend
descriptions, which are short and abstract even
when the underlying scope is too large. iter-22
needs a different layer of defense: either a
mid-flight check on the Backend LLM side, OR a
much stricter description threshold paired with
a Backend prompt that says "self-eject as
BLOCKED(task_too_large) if you cannot fit the
work into 200 LOC."**

## What worked (wins)

### Win #1 — Architect spend dropped to $0.80 (vs iter-20 $2.88)

| Iter | Architect cost | Architect wall-clock |
|-----:|---------------:|---------------------:|
| 19   | $0.78          | 473 s (10K out tok)  |
| 20   | $2.88          | 473 s                |
| 21   | **$0.80**      | **153 s** (11K out)  |

iter-20's 3.7× escalation was variance, not a
trend. iter-21's Architect produced ADR-0029
(`docs/adr/0029-idea-validator-v2-iter-21-be-core-decomposition-dag.md`,
17.7 KB) in 153s — 3.1× faster than iter-20's
473s for similar output volume. Architect now
has ADR-0028 as a stable pointer; less
re-derivation needed.

Carry-over #3 from `iter_21_handoff.md`
(Architect spend watch escalating) is closed
without further action.

### Win #2 — Architect cited iter-21 commit SHAs verbatim

Excerpt from ADR-0029:

> "...the iter-21 runtime tripwire (commits
> `096bf1c` + `c913b0f` — Backend rejects
> task_too_large pre-LLM; TL re-decomposes on
> BLOCKED)."

Architect read the iter-21 worktree (uncommitted
to main yet — these are local commits on
`worktree-iter-21`) and cited the Phase 1 + Phase
2 SHAs. Same pattern as iter-20 (commit `1a275fc`
cited in ADR-0028). The agents continue to
consume the iter-N constraint shipping process
correctly.

### Win #3 — Branch-isolation fix from iter-20 held

Post-demo: `git rev-parse --abbrev-ref HEAD` →
`worktree-iter-21`; `git worktree list` shows
only the parent worktrees (no agent worktrees
leaked); `.claude/agent-worktrees/` cleaned by
EXIT trap. iter-20 Phase 1 contract still works
end-to-end under iter-21 stress.

### Win #4 — Bash auto-approve fix produced the expected branch

The 3-iteration heredoc-vs-pipe carry-over fix
(`python3 - "$JSON" <<'PY' ... sys.argv[1]`) ran
without JSONDecodeError. With no pending_reviews
in the DB, the script correctly printed
`(no pending_reviews — chain didn't reach QA)`
instead of crashing on stdin parsing. The bug
class is closed even though the demo didn't
produce a pending_review row to approve.

### Win #5 — Frontend's BLOCKED was architecturally correct

Frontend reported BLOCKED with summary:

> "requires Backend — POST /analyze endpoint
> needed for live form and result-panel features;
> prohibited in v2 by ADR-0011 §No-backend-handshake
> and ADR-0013 §3; HTML <form> prohibited by US-4
> AC-6..."

Frontend refused to add a server-form pattern
that the v2 spec explicitly prohibits — citing
ADR-0011 §No-backend-handshake. This is the
right call. Not a regression; the agent is
preserving spec invariants under conflicting
inputs.

## What didn't (caveats)

### Caveat A — Backend tripwire didn't fire because TL's description was short

TL's Backend `task_assignment` description (audit
row 318):

> "Per ADR-0029 + PRD: implement idea-validator
> CLI entry point and scoring/validation core
> under examples/sandbox/idea-validator/.
> Strictly ≤200 LOC new/modified code (excluding
> tests). Unit tests with MockLLMClient covering
> happy path + 1 edge case. No real LLM in
> tests. Update Makefile target if needed."

- **Length**: 440 chars (well under the 1500-char
  threshold).
- **File-path tokens**: zero (the description
  references a directory `examples/sandbox/idea-validator/`
  which doesn't match the regex `[A-Za-z][A-Za-z0-9_/.-]+\.[a-z]+`
  — needs a `.ext`).
- **Result**: `_is_task_too_large` returned
  `(False, "")`. The tripwire did not fire.

But the underlying SCOPE of the task was still
too large for one Backend LLM turn —
"implement CLI entry point + scoring/validation
core + unit tests" ≈ the full ADR-0029
decomposition (5 subtasks, 90/120/90/180/120
LOC). Backend's LLM call timed out at 600s
having produced `src/`, `tests/`, `sample/`,
`pyproject.toml`, `conftest.py` directories
(visible post-demo) but no DONE report.

**Insight**: TL's natural emission shape is
**short and abstract** even for large scopes.
The tripwire's heuristic (char count >1500,
file-path tokens ≥3) doesn't match this shape at
all. It would catch a TL that over-narrates
(thousands of chars enumerating every file), but
real TL output describes intent in 200-500 chars
and trusts Backend to plan the rest.

This is the headline finding for iter-22.

### Caveat B — TL re-decomposition handler is correct but didn't trigger

Audit row 326: Backend reports `status=failed,
blocked_on=null, summary="LLMTimeoutError: claude
-p timed out after 600s; stdout=''"`. TL's
`_maybe_route_blocked` only triggers for
`status=blocked, blocked_on='task_too_large'`.
A FAILED report from a timeout is not auto-routed
— it surfaces in the digest only.

So iter-21's Phase 2 handler shipped correctly
(all 19 unit tests pass) but the chain didn't
produce the input shape it handles. The handler
itself is good; the upstream signal (Backend's
BLOCKED instead of FAILED) is missing.

### Caveat C — Architect ADR-0029 came AFTER TL had already dispatched Backend

Timeline (audit IDs):

```
315  team_lead     → broadcast            (DAG preview)
316  team_lead     → product_manager      task_assignment
317  team_lead     → architect            task_assignment
318  team_lead     → backend_developer    task_assignment   <-- single coarse Backend task
319  team_lead     → designer             task_assignment
320  team_lead     → frontend_developer   task_assignment
321  team_lead     → qa_engineer          task_assignment
322  product_manager    → team_lead       task_report DONE
323  architect          → team_lead       task_report DONE  <-- ADR-0029 lands here
324  designer           → team_lead       task_report DONE
325  frontend_developer → team_lead       task_report BLOCKED (spec correct)
326  backend_developer  → team_lead       task_report FAILED (LLMTimeout)
```

TL dispatched all 6 sub-assignments in the initial
decomposition turn (315-321). Architect's
ADR-0029 — with the 5-way be_core decomposition
DAG explicitly designed to satisfy the iter-21
tripwire's ≤200 LOC limit — came back AFTER
Backend was already running its coarse single
subtask.

There is no DAG-aware "wait for Architect's ADR
before dispatching Backend" path in the current
TL. The iter-20 `depends_on` slug mechanism
exists but TL didn't use it here — Backend was
emitted as a parallel sibling, not a dependent.

iter-22 candidate: TL should auto-`depends_on`
Backend's first subtask on Architect's completion
when ADR is part of the brief. This is a
non-trivial prompt edit but lines up with the
"TL over-decomposition prompt hint" carry-over.

### Caveat D — QA pending_review row STILL deferred

Now 3-iteration deferred (iter-19 → iter-20 →
iter-21). Backend's failure cascade-dropped QA
from the HoldQueue. `SELECT FROM pending_reviews`
returns 1 row (the iter-18 historic-first row,
still `approved`). No iter-21 row.

iter-22 has the same primary blocker: Backend
must complete its first turn under 600s. Until
Backend is reliably small-scoped, the chain
doesn't reach QA.

## Cost / quota

| Component | Cost   | Notes                                    |
|-----------|-------:|------------------------------------------|
| TL        | $0.15  | initial decomposition (broadcast counted) |
| PM        | $0.23  | 269s, 15K tokens out                     |
| Architect | $0.80  | 153s, 11K tokens out — back to baseline  |
| Designer  | $0.20  | 255s, 14K tokens out                     |
| Frontend  | $0.09  | 123s, BLOCKED (architecturally correct)  |
| Backend   | ~$0.50 est | 600s timeout, no DONE                  |
| **Total** | **~$1.97** | under $5 ceiling                     |

iter-21 ran cheaper than iter-19 ($2.00) AND
iter-20 ($4.25). Architect's drop was the
biggest single delta.

## Artifacts produced this iteration

- **`agents/backend_developer/agent.py`** (MODIFIED):
  iter-21 tripwire — `_is_task_too_large` helper
  + pre-flight short-circuit in `handle()` +
  `blocked_on` kwarg on `_report_to_tl`. 5 new
  unit tests. **Did not fire in this demo run.**
- **`agents/team_lead/agent.py`** (MODIFIED): TL
  re-decomposition handler for
  `blocked_on='task_too_large'` with anti-loop
  marker. 2 new unit tests. **Did not trigger in
  this demo run** (no BLOCKED(task_too_large)
  produced).
- **`scripts/demo_iter_21.sh`** (NEW, 368 lines):
  iter-21 demo + heredoc-vs-pipe bash fix.
  Bash fix verified manually + reproduced the
  old-pattern bug to confirm root cause.
- **`scripts/demo_iter_18.sh`, `_19.sh`, `_20.sh`**
  (MODIFIED): warning comments added so future
  iters don't re-introduce the antipattern.
- **`docs/adr/0029-idea-validator-v2-iter-21-be-core-decomposition-dag.md`**
  (PRODUCED BY ARCHITECT during demo): pins a
  5-subtask DAG with explicit LOC budgets
  (90/120/90/180/120). Cites commits `096bf1c`
  + `c913b0f` (iter-21 tripwire + handler).
  Untracked in git on the iter-21 branch (agent
  artifact in `docs/adr/`).
- **`apps/web/idea-validator/index.html`** (PRODUCED
  BY FRONTEND, 199 lines): static landing page
  per ADR-0013 §2. Frontend completed the static
  page; the BLOCKED was specifically on the
  server-form ask, not on the static page.
- **`examples/sandbox/idea-validator/`** (PARTIAL
  by BACKEND): `src/`, `tests/`, `sample/`,
  `conftest.py`, `pyproject.toml` directories
  appeared post-demo but Backend never reported
  DONE.

## Why this demo matters (and doesn't)

**iter-21's contract layer ships correctly.** All
428 unit tests pass; mypy/ruff/bandit/smoke-llm
green; the tripwire and re-decomp handler are
both wired and tested. The bash fix is verified.
Architect spend trajectory is closed.

**But the tripwire heuristic was the wrong
heuristic for real-world TL output.** This is a
useful empirical signal: heuristics designed
against hypothetical "TL emits a 3000-char
description" cases don't survive contact with
the actual LLM behavior. iter-20's TL
decomposition prompt teaches Backend
sub-decomposition, but TL doesn't always follow
it — and even when it does, individual subtasks
can still exceed 200 LOC of WORK without
exceeding 1500 chars of TEXT.

**What would actually close the Backend timeout
problem** (candidates for iter-22):

1. **Backend prompt edit + self-eject**: Backend's
   prompt explicitly says "before writing any
   code, count the files the task description
   requires. If >2 files OR >200 LOC of code
   needed, return BLOCKED(task_too_large)
   immediately with `blocked_on='task_too_large'`."
   This shifts the judgment from a Python regex
   to the LLM, which can read INTENT not just
   text.

2. **Architect→Backend `depends_on` rule**:
   when TL's decomposition includes both
   Architect AND Backend, TL must emit Backend
   with `depends_on=[architect_subtask]`. Then
   Backend receives Architect's ADR (with the
   decomposition DAG) and can reason about
   scope from a concrete document.

3. **Stricter tripwire threshold + content-aware
   token regex**: lower the threshold (e.g., 400
   chars), broaden the file-path regex to match
   directory mentions (`examples/sandbox/idea-validator/`
   should count), tighten the file-path heuristic
   to >=2 instead of >=3 unknown paths. Higher
   false-positive rate, more re-decompositions,
   slower chain — but at least the tripwire
   fires.

4. **Mid-flight Backend timeout halving**:
   reduce Backend's per-turn timeout to 300s.
   Force two turns of 300s each instead of one
   600s. Backend's stop-and-checkpoint behavior
   may be better than its long-run behavior.

Option 1 looks best — cheapest, no Python
heuristic to maintain, leverages LLM judgment
where the LLM is strongest (semantic scope, not
text size).

## Action items for iter-22

1. **(NEW TOP)** **Backend self-eject prompt**.
   Backend's system prompt gains a new "Scope
   pre-flight" section: enumerate the files
   you'd need to create/modify; if total >2
   files OR estimated >200 LOC, emit
   `task_report(blocked, blocked_on='task_too_large')`
   on turn 1 with no code written. Pair with a
   pin test that asserts the prompt rule. The
   Python tripwire (iter-21) stays as a backstop
   for OBVIOUSLY-too-large descriptions but is
   no longer the primary defense.

2. **(NEW)** **TL Architect→Backend dependency
   rule**. When TL decomposes a brief that
   includes BOTH Architect AND Backend, TL MUST
   emit Backend with `depends_on=[architect_*]`.
   Architect's ADR becomes available to Backend
   as part of the unblock task. This is a TL
   prompt edit + a unit test pin.

3. **(NEW)** **Tripwire threshold tightening**
   (optional, may not be needed if #1 + #2
   land). Lower description threshold to 400
   chars, broaden file-path regex to count
   directory mentions, lower the file-path
   trigger to 2. Investigate cost of running
   #1 + #2 first; the Python tripwire may not
   need tuning if Backend self-ejects reliably.

4. **Re-attempt the QA-emitted pending_review row
   criterion** — now 3-iteration deferred.
   Highest-priority objective for the demo
   re-run once Backend's first-turn timeout is
   solved.

5. **Architect spend trajectory: closed** —
   $0.78 (iter-19) → $2.88 (iter-20) → $0.80
   (iter-21). iter-20 was an outlier, not a
   trend. No action needed.

6. **Carry-overs unchanged** from iter-21
   handoff items 5-15 (HoldQueue persistence,
   `pytest-rerunfailures` plugin pin, TL
   auto-hop investigation, TL
   over-decomposition prompt hint partial
   address by #2 above, `audit_writer` role,
   hash-chain alert, `GitHubTargetRepo`, TL
   transactional insert, `BaseAgent`
   template-method refactor, `mark_task_done` /
   `update_task_status` real impls, substrate
   `--allowed-tools ""` fix).

## Stats

- **Wall-clock**: ~30 min (chain reached Backend
  timeout at the 600s mark; demo's poll loop
  expired after that).
- **Cost**: ~$1.97 (below $5 ceiling; below
  iter-20's $4.25 and iter-19's $2.00).
- **Agents successful**: 4 of 5 LLM-bound (PM,
  Architect, Designer, Frontend-static-page —
  Frontend's BLOCKED was architecturally
  correct, not a failure). Backend failed at
  600s; QA cascade-dropped.
- **Orchestrator HEAD**: stayed on
  `worktree-iter-21` throughout. iter-20
  branch-isolation fix held.
- **`pending_reviews` row**: NOT WRITTEN.
  Iter-19/20/21 deferred criterion still
  pending. Now 3-iteration deferred.
- **Tripwire firings**: 0 (heuristic mismatch).
- **TL re-decomposition trigger**: 0 (no
  BLOCKED(task_too_large) produced upstream).
- **Architect ADRs produced**: 1 (ADR-0029).
- **Total audit rows**: 13 (1 user-init, 1 TL
  broadcast, 6 TL→agent assignments, 5
  agent→TL reports).
