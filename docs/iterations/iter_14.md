# Iteration 14 — Plan

- **Status**: Draft (awaiting owner approval)
- **Plan author**: Claude (Opus 4.7)
- **Date drafted**: 2026-05-20
- **Base commit**: `ced1642` on `main` (iter-13 squash)
- **Branch**: `worktree-iter-14` (cut from `origin/main` at plan
  commit)
- **Anchors (do not contradict)**: ADR-001 (orchestrator),
  ADR-008 (LLM access), iter-13 retro + demo report.
- **Carry-overs addressed**: items 1–2 of
  `docs/iterations/iter_14_handoff.md` — extend the iter-10/12
  substring router with one more pattern tuple catching the
  iter-13 demo's THIRD distinct Backend phrasing
  ("mcp__ai_team_repo server never connected"); re-run the
  iter-13-shape demo to finally close the `pending_review`
  loop iter-3..13 all reached for.
- **Deferred unchanged** (carry-over items 3–13 from iter-14
  handoff): TL Backend decomposition (FIVE-iteration carry-
  over), HoldQueue persistence, TL over-decomposition prompt
  hint, `pytest-rerunfailures` plugin pin, startup-time MCP
  failure investigation, Architect spend watch, `audit_writer`
  Postgres role, hash-chain alert, `GitHubTargetRepo`,
  transactional TL decomposition, `BaseAgent`
  template-method refactor.

## Goal — one sentence

Add one pattern tuple to `core/dispatcher/mcp_race_router.py`
catching iter-13 demo's Backend phrasing
(`"mcp__ai_team_repo server never connected"`), then re-run
the demo so the chain finally reaches `pending_review` end-
to-end and the long-awaited loop closes.

## Success criteria (binary, measurable)

1. **`_MCP_RACE_PATTERNS` extended** in
   `core/dispatcher/mcp_race_router.py:46-60` with one new
   tuple:
   - `("mcp__ai_team_repo", "never connected")` — matches
     iter-13 demo Backend's wording verbatim (row 180:
     "BLOCKER: mcp__ai_team_repo server never connected ...").

   Pattern semantics unchanged (each tuple = all substrings
   must co-occur in the summary). False-positive risk stays
   near-zero — requires the LLM to specifically name the
   `mcp__ai_team_repo`-prefixed component AND say "never
   connected" together. Existing iter-9 test summary
   ("MCP server ai-team-repo never connected") does NOT
   contain `mcp__ai_team_repo` (double-underscore form), so
   no false-positive risk against existing test corpus.
2. **One new unit test** in
   `tests/unit/test_mcp_race_router.py`
   (`test_routes_iter13_demo_backend_summary_to_blocked`)
   pins iter-13 demo Backend's verbatim summary against the
   new tuple. Existing five tests (iter-9 + iter-8 + iter-11
   + happy-path filters + non-task-report) all stay green.
3. **`make lint typecheck sec test test-integration
   smoke-llm`** all green. Diff-cover ≥ 80 %.
4. **Real-LLM demo** (`scripts/demo_iter_14.sh`) re-runs
   the iter-13-shape task. Three valid outcome branches:
   - **(a) Chain reaches `pending_review` end-to-end.**
     Backend's third attempt benefits from iter-13's session
     fallback + iter-14's new tuple + the implementation tree
     already on disk from iter-13's `--resume` session
     (`examples/sandbox/idea-validator/`). If Backend
     BLOCKED → retry → DONE OR Backend DONE on first attempt,
     QA picks up its held assignment, runs the v2 smoke +
     regression suite, emits `request_human_review` →
     `pending_review` row appears → demo auto-approves →
     chain closes. **The long-awaited end-to-end close
     iter-3..13 all reached for.**
   - **(b) Backend → BLOCKED via new tuple → retry → DONE
     → QA → `pending_review` → approved.** Still success;
     the retry path is exercised explicitly. Same as (a)
     terminally, plus one extra audit row showing the
     new tuple fired.
   - **(c) Backend hits a FOURTH distinct phrasing the
     three iter-10 + two iter-12 + iter-14 tuples don't
     match.** Honest failure mode for the pattern-tuple
     approach. iter-15 picks up one more tuple. Demo
     report explicitly names the fourth phrasing verbatim,
     mirroring iter-13's report shape.
5. **All gates green on PR.** `make lint typecheck sec
   test test-integration smoke-llm` all pass.
   `uv run ruff format --check .` clean. 0 high-severity
   bandit findings.

## Phases

Plan-before-code: this document lands as Phase 0's commit.
No Phase 1+ work until the owner approves.

### Phase 0 — Plan + branch setup

- [x] **Cut branch from origin/main** (done at draft time):
  ```bash
  git checkout -b worktree-iter-14 origin/main
  ```
- [ ] **Commit this plan**:
  ```bash
  git add docs/iterations/iter_14.md
  git commit -m "docs(iter-14): plan — close pending_review loop with one more router tuple"
  ```
- [ ] **Open draft PR** with the plan link + the iter-13
  demo's findings as motivation.

### Phase 1 — Extend `_MCP_RACE_PATTERNS` + unit test (TDD)

**Files**:
- Modify: `core/dispatcher/mcp_race_router.py:46-60` — add
  one tuple + docstring entry.
- Modify: `tests/unit/test_mcp_race_router.py` — add one
  test pinning iter-13 demo Backend's row 180 summary.

#### Step 1.1 — Failing test first (RED)

- [ ] **Add the failing test** to
  `tests/unit/test_mcp_race_router.py`:

  ```python
  def test_routes_iter13_demo_backend_summary_to_blocked() -> None:
      """iter-13 demo (correlation 1e7bb0db-a109-4521-ad03-
      175e9fdd3d67) Backend's retry session (row 180) reported
      the failure with a THIRD distinct phrasing that mixes
      iter-12's mcp__-prefixed tool name with iter-10's
      'never connected' failure verb:

        '... BLOCKER: mcp__ai_team_repo server never
        connected (ToolSearch tried 4 times across 2
        sessions); Bash tool auto-approve ...'

      Neither iter-10's three tuples nor iter-12's two
      tuples catch this combination. iter-14 adds one more.
      Pinned verbatim from `iter_13_demo_report.md` Failure 1.
      """
      summary = (
          "Backend Developer: tests failed. All 7 source/test "
          "files are written and verified via grep, but "
          "BLOCKER: mcp__ai_team_repo server never connected "
          "(ToolSearch tried 4 times across 2 sessions); "
          "Bash tool auto-approve for git/uv was also "
          "unavailable in this session."
      )
      out = maybe_route_mcp_race_to_blocked(_failed_report(summary))
      assert isinstance(out.payload, TaskReportPayload)
      assert out.payload.status == TaskStatus.BLOCKED
      assert out.payload.blocked_on == "mcp_unhealthy"
      # Verbatim summary preserved.
      assert out.payload.summary == summary
  ```

- [ ] **Run the test** — expect FAIL because none of the
  five existing tuples match this exact substring pair:

  ```bash
  uv run pytest tests/unit/test_mcp_race_router.py -v
  ```

  Expected: 1 new FAIL (status stays FAILED, not BLOCKED).
  Other five tests stay green.

#### Step 1.2 — Add the pattern tuple (GREEN)

- [ ] **Edit
  `core/dispatcher/mcp_race_router.py:46-60`** to extend
  the tuple-of-tuples with one more entry:

  ```python
  _MCP_RACE_PATTERNS: tuple[tuple[str, ...], ...] = (
      ("MCP server", "never connected"),
      ("MCP server", "never finished connecting"),
      ("MCP server", "still connecting"),
      ("mcp__ai_team_repo", "unavailable"),
      ("MCP tools", "unavailable"),
      # iter-14: Backend's iter-13 demo retry wording —
      # "BLOCKER: mcp__ai_team_repo server never connected
      # (ToolSearch tried 4 times across 2 sessions)". Mixes
      # iter-12's mcp__-prefixed tool name with iter-10's
      # "never connected" failure verb; neither prior tuple
      # catches the combination. See iter_13_demo_report.md
      # Failure 1.
      ("mcp__ai_team_repo", "never connected"),
  )
  ```

- [ ] **Update the module docstring** in the same file
  to add iter-13 demo's wording to the historical list
  (the comment block at lines 16-21):

  ```python
  - iter-13 demo: "BLOCKER: mcp__ai_team_repo server never
                   connected (ToolSearch tried 4 times across
                   2 sessions)"
                  (added iter-14 — different again: mixes
                  the mcp__-prefixed tool name from iter-12
                  with the "never connected" failure verb
                  from iter-10)
  ```

- [ ] **Run tests — expect GREEN**:

  ```bash
  uv run pytest tests/unit/test_mcp_race_router.py -v
  uv run pytest tests/unit -q
  ```

  Expected: all six router tests pass (iter-8 + iter-9 +
  iter-11 + iter-13 + happy-path filters + non-task-report)
  and the rest of the unit suite is unchanged.

- [ ] **Lint + format + mypy**:

  ```bash
  uv run ruff check core/dispatcher/mcp_race_router.py tests/unit/test_mcp_race_router.py
  uv run ruff format --check core/dispatcher/mcp_race_router.py tests/unit/test_mcp_race_router.py
  uv run mypy core/dispatcher/mcp_race_router.py
  ```

  Expected: clean.

- [ ] **Commit**:

  ```bash
  git add core/dispatcher/mcp_race_router.py tests/unit/test_mcp_race_router.py
  git commit -m "feat(mcp-router): one more pattern tuple for iter-13 phrasing"
  ```

### Phase 2 — Demo script + real-LLM run

**Files**:
- Create: `scripts/demo_iter_14.sh` — clone of
  `demo_iter_13.sh` with iter-14 header noting the router
  extension; `.iter14-mcp.json` config filename.
- Modify: `Makefile` — `make demo` aliases to
  `demo-iter-14`; iter-13 stays as a regression baseline.

#### Step 2.1 — Demo script

- [ ] **Copy + adapt**:

  ```bash
  cp scripts/demo_iter_13.sh scripts/demo_iter_14.sh
  chmod +x scripts/demo_iter_14.sh
  ```

  Edit the header to say `iter-14`, replace the iter-13
  session-id narrative with the iter-14 router-extension
  narrative, and rename `.iter13-mcp.json` →
  `.iter14-mcp.json`. The auto-retry-blocked + auto-approve
  tail (steps 6.5/7 + 6.6/7 from iter-13) stays unchanged —
  it's exactly what we want exercised this iteration. The
  `docker exec` fix from iter-13's commit `1a24699` carries
  over verbatim.

- [ ] **Makefile alias**:

  ```makefile
  demo: demo-iter-14 ## Alias for the current iteration's demo

  demo-iter-14: ## Run iter-14 e2e (close pending_review loop with new tuple)
  	bash scripts/demo_iter_14.sh

  demo-iter-13: ## Run iter-13 e2e — regression baseline (session-id fallback)
  	bash scripts/demo_iter_13.sh
  ```

- [ ] **Syntax check + commit**:

  ```bash
  bash -n scripts/demo_iter_14.sh
  git add scripts/demo_iter_14.sh Makefile
  git commit -m "chore(demo): demo_iter_14.sh + Makefile alias"
  ```

#### Step 2.2 — Pre-flight + real-LLM run

- [ ] **Pre-flight smoke check** (ADR-008):

  ```bash
  make smoke-llm
  ```

  Expected: PASS. If transient latency fail, re-run once
  (iter-12 + iter-13 both saw this; it cleared on second try).

- [ ] **Sanity-check the working tree** before launching:

  ```bash
  git status --short
  ```

  Expected: only iter-14 plan + (later) iter-14 commits
  staged. Leave the untracked `apps/web/`, `docs/adr/0010-
  0021`, `docs/design/`, `examples/sandbox/idea-validator/`
  alone — they're target_repo artifacts from prior demos,
  harmless per ADR-009, and the iter-13 Backend tree is the
  load-bearing "almost-done" state we WANT preserved for
  this run's third attempt to resume from.

- [ ] **Run the demo**:

  ```bash
  AI_TEAM_DEMO_NON_INTERACTIVE=1 bash scripts/demo_iter_14.sh
  ```

  Wall-clock budget 30 min; cost ceiling $5.00.

- [ ] **Capture outcomes** — the auto-retry + auto-approve
  flow does most of the work. Expected paths:

  - If Backend reaches DONE (success-criterion 4a or 4b):
    QA picks up its held assignment, `pending_review` row
    appears, demo auto-approves, chain closes. Pull the
    final `tasks.status` row to confirm `done`.
  - If Backend hits a fourth phrasing (criterion 4c): the
    demo's tail steps will see no BLOCKED task to retry
    OR see Backend FAILED again on retry. Either way,
    record the verbatim summary for iter-15.

#### Step 2.3 — Demo report

- [ ] **Write `docs/iterations/iter_14_demo_report.md`**
  mirroring `iter_13_demo_report.md`'s structure:

  - Outcome paragraph naming which success-criterion branch
    (4a / 4b / 4c) the run hit.
  - "What worked" / "What didn't" sections.
  - Audit-log timeline table (same SQL as iter-13).
  - Cost / quota table from `metadata.llm`.
  - Artifacts produced (any new files + final task tree
    state).
  - If criterion 4a or 4b: explicit note that **the
    `pending_review` loop closed end-to-end** for the
    first time in fourteen iterations.
  - If criterion 4c: verbatim fourth phrasing + iter-15
    candidate tuple.
  - "Why this demo is a net win" closing.

- [ ] **Commit**:

  ```bash
  git add docs/iterations/iter_14_demo_report.md
  git commit -m "docs(iter-14): real-LLM demo report"
  ```

### Phase 3 — Retro + iter-15 handoff + gates + merge

#### Step 3.1 — Final gate sweep

- [ ] **Run every gate**:

  ```bash
  make lint typecheck sec test test-integration smoke-llm
  uv run ruff format --check .
  ```

  Expected: all green; 0 high-severity bandit;
  ~410 + 1 new test passes.

- [ ] **Diff-cover ≥ 80%** with combined unit + integration
  coverage:

  ```bash
  uv run pytest tests/unit tests/integration --cov --cov-report=xml -q
  uv run diff-cover coverage.xml --compare-branch=origin/main --fail-under=80
  ```

  Expected: PASS. Phase 1 is one-tuple + one test, near
  100 % on those lines. Phase 2 is shell + docs.

#### Step 3.2 — Retro + iter-15 handoff

- [ ] **Write `docs/iterations/iter_14_retro.md`** mirroring
  iter_13_retro.md's structure:

  - "What shipped" — phase summary with commit references.
  - "What went well" / "What didn't" / "Surprises" — short
    bullets, evidence-anchored.
  - "Action items for iter-15" — depends on Phase 2's
    outcome:
    - If chain closed (4a/4b): iter-15 focus is **TL Backend
      decomposition** (now SIX-iteration carry-over;
      structural fix to follow the proven loop close) +
      HoldQueue persistence. The fourteen-iteration
      retry-blocked-and-router-tuple work is DONE; next
      phase is making Backend's sessions short enough to
      stop hitting MCP races altogether.
    - If still no close (4c): iter-15 focus is **another
      tuple OR a generalisation** of the router (e.g.,
      separate-tuple-per-half "mcp__ai_team_repo" present
      AND any-failure-verb present). The pattern-tuple
      approach has scaled to FIVE tuples; if a sixth is
      needed iter-15 evaluates whether the design is still
      pulling its weight.
  - "Stats" — commits, tests, real-LLM spend, diff-cover.
  - "Ready-to-paste prompt for iter-15" → points to
    handoff doc.

- [ ] **Write `docs/iterations/iter_15_handoff.md`** — same
  structure as iter_14_handoff.md.

- [ ] **Commit**:

  ```bash
  git add docs/iterations/iter_14_retro.md docs/iterations/iter_15_handoff.md
  git commit -m "docs(iter-14): retro + iter-15 handoff"
  ```

#### Step 3.3 — Mark PR ready, watch CI, squash-merge

- [ ] **Mark PR ready** + **watch CI** + **squash-merge**:

  ```bash
  gh pr ready
  gh pr checks --watch
  gh pr merge --squash
  ```

  (Skip `--delete-branch` if it fails the way iter-11/12/13
  did — main is checked out in the primary worktree.
  Branch on GitHub auto-deletes anyway.)

## What we are NOT doing this iteration

- **TL Backend decomposition** (carry-over from
  iter-9/10/11/12/13). Pairs structurally with the
  tactical tuple fix and is the right next iteration after
  the loop closes, but adding it to iter-14 dilutes the
  laser focus on closing the loop. iter-15.
- **HoldQueue persistence** (Postgres-backed). Now
  actively hurts demos with restarts between BLOCKED and
  retry. iter-15 if TL Backend decomposition slips.
- **TL over-decomposition prompt hint** (Architect rows
  iter-12 + iter-13 both self-flagged it). Small prompt
  edit; iter-15 carry-over.
- **`pytest-rerunfailures` plugin pin**,
  **startup-time MCP investigation**,
  **Architect spend watch**,
  **`audit_writer` Postgres role**,
  **hash-chain alert job**,
  **`GitHubTargetRepo`**, **transactional TL decomposition**,
  **`BaseAgent` template refactor.**
  Long-standing carry-overs untouched.

## Risks

- **MCP race doesn't fire this run.** The race is
  intermittent. If Backend's third attempt resumes from
  `--resume`-cached state quickly enough, it may produce
  Backend → DONE on first attempt with no router rewrite
  exercised. That's still success-criterion 4a + a happy
  outcome; demo report would note the new tuple didn't get
  exercised but the chain closed. The pattern-tuple is
  unit-test-pinned regardless.
- **MCP race fires with a fourth distinct phrasing.**
  Possible if the LLM emits yet another shape. Criterion
  4c covers this — record verbatim, iter-15 adds another
  tuple OR moves to a more general design. The
  pattern-tuple approach from iter-10 was explicitly
  designed for this incremental scaling; this is the
  expected long tail.
- **Backend's `examples/sandbox/idea-validator/` tree on
  disk diverges from what the v2 spec now wants.** Less
  likely; the spec hasn't changed since iter-13. But if
  the tree is stale enough that Backend rewrites large
  parts of it, the session length grows again and we
  re-enter the MCP race window. Mitigation: nothing in
  iter-14 — TL Backend decomposition (iter-15) is the
  real fix.
- **Three retries → quota burn.** iter-11 retry cap is
  5; multiple retries this run could spend $3-5 on
  Backend alone. Cost ceiling $5 still holds; if quota
  exhausts mid-run, the dispatcher returns
  `quota_exhausted` cleanly and the demo report names
  the outcome.

## Cost projection

| Phase | Type                          | Estimate                  |
|-------|-------------------------------|---------------------------|
| 0     | docs                          | $0                        |
| 1     | code + 1 unit test            | $0                        |
| 2     | shell + real-LLM demo + retries | ~$2.50 expected (one chain + zero-to-two retries); +$1 if multiple retries |
| 3     | docs + CI                     | $0                        |
| **Total** |                           | **~$2.50 expected, $5 ceiling** |

iter-13 spent $1.86 (Backend's two sessions = $0.41 + $0.08,
Architect's ADR-0021 add = $0.84). iter-14 may come in
lower if Backend's third attempt resumes from `--resume`
cache more quickly OR higher if multiple retries happen.
Architect should be cheap this run (no new ADR expected;
0019-0021 cover the contracts).

## Workflow

- Plan-before-code: this file lands as Phase 0's commit;
  no Phase-1+ code until owner approves.
- Conventional commits; squash-merge on the iter-14 PR.
- Each phase's "Commit" row is one (and only one) commit.
- Run `make lint typecheck sec test` after each phase.
- Final demo report goes in the same PR.

## Ready-to-paste prompt for iter-15

Lives in `docs/iterations/iter_15_handoff.md` (Phase 3.2).
