# Iter-20 real-LLM end-to-end demo — report

- **Date**: 2026-05-21
- **Run by**: Claude (Opus 4.7) per `docs/iterations/iter_20.md`
  Phase 5
- **Script**: `AI_TEAM_DEMO_NON_INTERACTIVE=1 bash
  scripts/demo_iter_20.sh`
- **Task**: idea-validator v2 (clone of iter-17..19 spec)
- **Correlation ID**:
  `86a96667-b869-491c-a3e1-33acb8714886`
- **Outcome**: **Partial success — major wins on
  iter-20's two top priorities (branch-isolation +
  TL Backend decomposition), but Backend STILL hit
  a 600s timeout on one of the two subtasks → no
  QA-emitted `pending_reviews` row written.**

## Verdict in one line

**Iter-20 Phase 1 (branch-isolation) is
validated end-to-end under real LLM stress — the
orchestrator's HEAD remained on
`worktree-iter-20` throughout the chain.
Iter-20 Phase 2 (TL Backend decomposition prompt
edit) is validated structurally — TL emitted TWO
Backend subtasks instead of one. But the prompt
alone wasn't enough: one of the 2 Backend
subtasks still exceeded 600s on Sonnet. The
chain's QA-row criterion remains deferred to
iter-21+, which must add the runtime tripwire.**

## What worked (major wins)

### Win #1 — Branch-isolation fix held under
real-LLM stress

The iter-19 demo's chain-killer surprise: Backend
ran `handle_create_branch` which executed `git
checkout -b` against the orchestrator's worktree,
switching HEAD mid-chain. iter-20 Phase 1
replaced `git checkout -b` with `git worktree
add` to an isolated path.

**Empirical result**: post-demo,
`git rev-parse --abbrev-ref HEAD` returned
`worktree-iter-20`. **The orchestrator's HEAD was
unaffected by the Backend agent's branch
operations.** The Phase 3 cleanup also worked —
`ls .claude/agent-worktrees/` returns "no such
directory" post-EXIT-trap.

### Win #2 — TL Backend decomposition prompt
edit produced 2 Backend subtasks

Audit-log evidence (rows 305, 306):

```
 305 | team_lead | backend_developer | task_assignment | opus  $0.33   63s
 306 | team_lead | backend_developer | task_assignment | opus  $0.33   63s
```

TL emitted TWO `backend_developer` subtasks in
the decomposition rather than one. The iter-20
Phase 2 prompt edit ("Backend tasks must be
≤200 LOC scope; emit multiple subtasks with
depends_on slugs if larger") had its intended
effect on TL's structural output.

### Win #3 — Architect ADR explicitly references
the iter-20 prompt change

Excerpt from Architect's ADR-0027 (visible in
demo log):

> "The genuinely new content is the seventh:
> the `be_core` ↔ `be_cli` slice boundary,
> motivated by the iter-20 Phase-2 TL-prompt rule
> that Backend work must decompose into ≤200 LOC
> subtasks (commit `1a275fc`). Without an
> Architect-defined seam, TL has no contract to
> dispatch two parallel Backend subtasks against."

The Architect agent READ iter-20's plan, the TL
prompt change, and even cited the commit SHA.
This is a strong signal that the agents are
actually consuming the iter-N constraints we
ship, not just the spec.

### Win #4 — 4 of 5 LLM-bound agents succeeded
under iter-20 code

| Agent     | Tier   | Duration | Cost   | Status |
|-----------|--------|---------:|-------:|:------:|
| TL        | opus   |     63 s | $0.33  | done   |
| PM        | sonnet |    290 s | $0.18  | done   |
| Architect | opus   |    473 s | $2.88  | done   |
| Designer  | sonnet |    356 s | $0.26  | done   |
| Frontend  | sonnet |    158 s | $0.10  | done   |
| Backend   | sonnet |   600 s+ |  ~$0.50 est. | **failed (LLMTimeoutError)** |
| QA        | —      |        — |     —  | cascade-dropped |

Frontend produced a real artifact:
`apps/web/idea-validator/index.html` (199 lines,
file:// landing page with embedded sample report,
zero-JavaScript per the demo task spec).

Architect produced `docs/adr/0027-*.md` referencing
the iter-20 fix.

## What didn't

### Caveat A — Backend STILL timed out at 600s

Even with TL emitting 2 Backend subtasks, ONE of
them was too large to fit in 600s on Sonnet. The
prompt-only fix isn't sufficient — TL's "scope to
≤200 LOC" instruction is advisory, not enforced.
The LLM-side compliance with the prompt is
imperfect on this kind of soft constraint.

**Implication**: iter-21 MUST add the runtime
tripwire that iter-20 deferred — Backend agent
rejects an incoming `task_assignment` whose
description estimates a too-large scope.

### Caveat B — Demo auto-approve bash STILL hit
JSONDecodeError — and the root cause is the
heredoc, NOT bash precedence

iter-18 reported this and "fixed" via `|| echo
'[]'`. iter-19 reported it AGAIN and "fixed" via
`REVIEWS_JSON="${REVIEWS_JSON:-[]}"` +
`printf '%s'`. iter-20 inherits iter-19's "fix"
and it STILL hit:

```
json.decoder.JSONDecodeError: Expecting value: line 1 column 1 (char 0)
```

**The actual root cause**: the bash pattern
`command | python3 <<'PY' ... PY` is a
heredoc-vs-pipe conflict. Bash sets python's
stdin to the HEREDOC (the source code), NOT to
the piped output. So `json.load(sys.stdin)`
parses the python source as JSON, which fails on
the first character.

**The real fix** (iter-21):

```bash
# Pass JSON via argv, run heredoc as -c equivalent:
python3 - "$REVIEWS_JSON" <<'PY'
import json, subprocess, sys
data = json.loads(sys.argv[1])
...
PY
```

The `python3 - "..."` form reads code from stdin
(the heredoc) and `sys.argv[1]` carries the
JSON. No stdin/source conflict.

**This is a 3-iteration carry-over now (iter-18 → iter-19 → iter-20). iter-21 must close it for real.**

### Caveat C — Phase 5 success criterion (QA row)
deferred to iter-21+

Same outcome shape as iter-19's Phase 7: Backend's
failure cascade-dropped QA from the HoldQueue
(per iter-7 dispatcher behavior); no
`pending_reviews` row was written.

Iter-20's Phase 1 + 2 contracts are validated by
unit tests + the partial demo. Phase 5's specific
demo criterion is iter-21's job once the Backend
runtime tripwire lands.

## Cost / quota

| Component | Cost  | Notes |
|-----------|------:|-------|
| TL        | $0.33 | one decomposition turn at 63s. |
| PM        | $0.18 | within 600s new budget. |
| Architect | $2.88 | **carry-over: Architect spend watch** — iter-19 was $0.78, iter-20 is $2.88. Trajectory unfavorable. |
| Designer  | $0.26 |                                     |
| Frontend  | $0.10 |                                     |
| Backend   | ~$0.50 est | timeout, no successful invoke. |
| **Total** | **~$4.25** | under $5 ceiling but close. |

## Artifacts produced this iteration

- **`tools/mcp_servers/ai_team_repo/handlers.py`**
  (MODIFIED): `handle_create_branch` uses `git
  worktree add` + module-level `_ACTIVE_WORKTREE`.
  Three other handlers (`status`, `run_shell`,
  `open_pr`) + `write_file_in_scope` consult
  `_effective_cwd(ctx)`.
- **`prompts/team_lead.md`** (MODIFIED): new
  "Exception for Backend work" section instructs
  TL to decompose Backend work into ≤200 LOC
  subtasks with depends_on slugs.
- **`scripts/demo_iter_20.sh`** (NEW, clone of
  iter-19 with worktree pre-flight + EXIT-trap
  cleanup).
- **`tests/unit/test_mcp_ai_team_repo_handlers.py`**
  (MODIFIED, +2 tests): real tmp git repo
  fixture; `test_create_branch_does_not_switch_orchestrator_head`
  + `test_write_file_after_create_branch_lands_in_worktree`.
- **`tests/unit/test_team_lead_agent.py`** (MODIFIED,
  +1 test): pin TL prompt's iter-20
  Backend-decomposition rule.
- **`docs/adr/0027-idea-validator-v2-iter-19-architecture-pointer.md`**
  (PRODUCED BY AGENT during demo): Architect's
  iter-20 ADR citing the iter-20 Phase 2 commit
  `1a275fc`. (Untracked in git; an agent artifact
  in `docs/adr/`.)

## Why this demo matters

**Two of the three iter-20 priorities are validated
end-to-end under real-LLM stress.**

1. **Branch-isolation** (iter-17 retro #7, now
   2-iteration carry-over): PROVEN closed.
   Orchestrator HEAD stayed pinned. No iter-19-shape
   surprise recurrence.

2. **TL Backend decomposition** (iter-19 retro #1,
   was 10-iteration carry-over): STRUCTURALLY
   proven — TL now emits multiple Backend
   subtasks. But the prompt is advisory; LLM
   compliance is imperfect under stress. iter-21
   adds the runtime tripwire.

3. **QA pending_review row** (iter-19 deferred
   criterion): STILL DEFERRED. Backend timeout
   prevents the chain from reaching QA.

The Architect's explicit citation of commit
`1a275fc` in its ADR is a happy second-order
signal — the iter-N constraint shipping process
is producing readable artifacts that downstream
agents consume correctly.

## Action items for iter-21

1. **(NEW TOP)** **Backend runtime tripwire**.
   Add to `BackendDeveloperAgent.handle()` a
   pre-flight estimator that rejects an
   incoming `task_assignment` whose description
   plausibly exceeds ~200 LOC (or whose target
   files in the working tree already exceed
   that scope). On reject, return
   `BLOCKED(blocked_on='task_too_large')` so
   the chain can recover (TL re-decomposes
   into smaller pieces). Concrete heuristic:
   description char count > 1500 OR description
   contains ≥ 3 distinct file-path-shaped
   tokens that aren't already on disk.

2. **(NEW)** **Demo auto-approve bash fix done
   right**. Three-iteration carry-over.
   Replace `printf | python3 <<'PY'` with
   `python3 - "$JSON" <<'PY' ... sys.argv[1]`.

3. **(NEW)** **Architect spend watch escalating**:
   $0.78 (iter-19) → $2.88 (iter-20). Trajectory
   bad. The TL-over-decomposition hint
   (carry-over #7) is a candidate but doesn't
   explain a 3.7× increase. Investigate
   what Architect's session is doing for 473s on
   opus.

4. **Re-attempt the iter-19/20 demo QA-row
   criterion** under iter-21's fixes.

5. **Carry-overs unchanged** from iter-20 handoff
   (HoldQueue persistence,
   `pytest-rerunfailures` pin, TL auto-hop, TL
   over-decomposition prompt hint, `audit_writer`
   role, hash-chain alert, `GitHubTargetRepo`,
   TL transactional insert, `BaseAgent`
   template-method refactor, `mark_task_done` /
   `update_task_status` real impls, substrate
   `--allowed-tools ""` fix).

## Stats

- **Wall-clock**: ~33 min (chain reached Backend
  timeout at ~30 min, demo's poll loop expired
  after that).
- **Cost**: ~$4.25.
- **Agents successful**: 5 of 6 LLM-bound (TL, PM,
  Architect, Designer, Frontend); Backend failed
  at 600s timeout on one of 2 subtasks.
- **Orchestrator HEAD**: stayed on
  `worktree-iter-20` throughout. Iter-19 Caveat B
  closed.
- **`pending_reviews` row**: NOT WRITTEN. Iter-19
  Phase 7 deferred criterion still pending.
