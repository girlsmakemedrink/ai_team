# Iteration 12 — Plan

- **Status**: Draft (awaiting owner approval)
- **Plan author**: Claude (Opus 4.7)
- **Date drafted**: 2026-05-20
- **Base commit**: `e0e0192` on `main` (iter-11 squash)
- **Branch**: `worktree-iter-12` (cut from `origin/main` at plan
  commit)
- **Anchors (do not contradict)**: ADR-001 (orchestrator),
  ADR-002 (message schema), ADR-008 (LLM access), iter-11
  retro + demo report.
- **Carry-overs addressed**: items 1–2 of
  `docs/iterations/iter_12_handoff.md` — extend the iter-10
  substring router with new pattern tuples; re-run the
  iter-11-shape demo to finally exercise iter-11's
  retry-blocked end-to-end and close the `pending_review`
  loop iter-3..11 all reached for.
- **Deferred unchanged** (carry-over items 3–12 from iter-12
  handoff): startup-time MCP failure investigation,
  Architect's $2.47/call spend watch, TL Backend
  decomposition, HoldQueue persistence, `audit_writer`
  Postgres role, hash-chain alert, `GitHubTargetRepo`,
  transactional TL decomposition,
  `pytest-rerunfailures` plugin pin, `BaseAgent`
  template-method refactor.

## Goal — one sentence

Add two pattern tuples to `core/dispatcher/mcp_race_router.py`
catching iter-11 demo's Backend phrasing
(`"mcp__ai_team_repo__* tools were unavailable
throughout the session"`), then re-run the demo so
iter-11's `ai-team retry-blocked` actually engages
end-to-end and the chain finally reaches `pending_review`.

## Success criteria (binary, measurable)

1. **`_MCP_RACE_PATTERNS` extended** in
   `core/dispatcher/mcp_race_router.py:39-43` with two new
   tuples:
   - `("mcp__ai_team_repo", "unavailable")` — matches
     iter-11 demo Backend's wording verbatim
   - `("MCP tools", "unavailable")` — catches a slightly
     different phrasing the LLM might emit in future runs.

   Pattern semantics unchanged (each tuple = all substrings
   must co-occur in the summary). False-positive risk stays
   near-zero — both require the LLM to specifically name an
   MCP component plus the word "unavailable".
2. **One new unit test** in
   `tests/unit/test_mcp_race_router.py` pins iter-11 demo
   Backend's verbatim summary against the new patterns.
   Existing iter-10 tests for the three original patterns
   must still pass.
3. **`make lint typecheck sec test test-integration
   smoke-llm`** all green. Diff-cover ≥ 80 %.
4. **Real-LLM demo** (`scripts/demo_iter_12.sh`) re-runs
   the iter-11-shape task. Three valid outcome branches:
   - **(a) Backend → BLOCKED via new tuple → owner runs
     `ai-team retry-blocked <task_id>` → second Backend
     attempt → DONE → QA runs → `pending_review` row
     appears → owner approves → chain closes.** This is
     the long-awaited end-to-end close.
   - **(b) Backend → BLOCKED → retry → BLOCKED again →
     owner retries again (capped at 5) → eventually
     succeeds OR caps out.** Still recoverable; demo
     report names whichever happened.
   - **(c) Backend → DONE on first attempt (MCP race
     didn't fire this run).** Less informative but the
     happy-path validation; demo report explicitly notes
     that the router didn't exercise + iter-13 picks up
     "force the race to verify retry path" as an action
     item.
5. **All gates green on PR.** `make lint typecheck sec
   test test-integration smoke-llm` all pass.
   `uv run ruff format --check .` clean. 0 high-severity
   bandit findings.

## Phases

Plan-before-code: this document lands as Phase 0's commit.
No Phase 1+ work until the owner approves.

### Phase 0 — Plan + branch setup

- [ ] **Cut branch from origin/main** (already done at
  draft time):
  ```bash
  git checkout -b worktree-iter-12 origin/main
  ```
- [ ] **Commit this plan**:
  ```bash
  git add docs/iterations/iter_12.md
  git commit -m "docs(iter-12): plan — extend substring router + retry-demo close-the-loop"
  ```
- [ ] **Open draft PR** with the plan link + the iter-11
  demo's findings as motivation.

### Phase 1 — Extend `_MCP_RACE_PATTERNS` + unit test (TDD)

**Files**:
- Modify: `core/dispatcher/mcp_race_router.py:39-43` — add
  two tuples.
- Modify: `tests/unit/test_mcp_race_router.py` — add one
  test pinning iter-11 demo Backend's summary.

#### Step 1.1 — Failing test first (RED)

- [ ] **Add the failing test** to
  `tests/unit/test_mcp_race_router.py`:

  ```python
  def test_routes_iter11_demo_backend_summary() -> None:
      """iter-11 demo correlation ccac21dc — Backend FAILED
      with this verbatim summary. iter-10's three pattern
      tuples didn't match; iter-12 adds two more.
      """
      summary = (
          "Backend Developer: tests failed. ... "
          "BLOCKED: could not create branch, run tests, or "
          "open PR — mcp__ai_team_repo__* tools were "
          "unavailable throughout the session and Bash is "
          "blocked for git/uv/pytest per role constraints. "
          "Branch name is the intended name; git operations "
          "must be completed in a session where MCP tools "
          "are available."
      )
      msg = _failed_report_with_summary(summary)
      out = maybe_route_mcp_race_to_blocked(msg)
      assert out.payload.status == TaskStatus.BLOCKED
      assert out.payload.blocked_on == "mcp_unhealthy"
  ```

  Use the same `_failed_report_with_summary` helper the
  existing iter-10 tests use (if present); otherwise build
  the `AgentMessage` inline mirroring the other iter-10
  test patterns.

- [ ] **Run the test** — expect FAIL because none of
  iter-10's three patterns match this summary:

  ```bash
  uv run pytest tests/unit/test_mcp_race_router.py -v
  ```

  Expected: 1 new FAIL (status stays FAILED, not BLOCKED).
  Other iter-10 tests stay green.

#### Step 1.2 — Add the two pattern tuples (GREEN)

- [ ] **Edit
  `core/dispatcher/mcp_race_router.py:39-43`** to extend
  the tuple-of-tuples:

  ```python
  _MCP_RACE_PATTERNS: tuple[tuple[str, ...], ...] = (
      ("MCP server", "never connected"),
      ("MCP server", "never finished connecting"),
      ("MCP server", "still connecting"),
      # iter-12: Backend's iter-11 demo wording —
      # "mcp__ai_team_repo__* tools were unavailable
      # throughout the session". Pattern (a) catches the
      # mcp__-prefixed phrasing; (b) catches the more
      # general "MCP tools" + "unavailable" form. See
      # iter_11_demo_report.md Failure 1.
      ("mcp__ai_team_repo", "unavailable"),
      ("MCP tools", "unavailable"),
  )
  ```

- [ ] **Update the module docstring** in the same file
  to add iter-11 demo's wording to the historical list
  (line 11-15 area):

  ```python
  - iter-11 demo: "BLOCKED: ... mcp__ai_team_repo__*
                    tools were unavailable throughout the
                    session"
  ```

- [ ] **Run tests — expect GREEN**:

  ```bash
  uv run pytest tests/unit/test_mcp_race_router.py -v
  uv run pytest tests/unit -q
  ```

  Expected: all unit tests pass (existing iter-10 + new
  iter-11 + everything else unchanged).

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
  git commit -m "feat(mcp-router): two new pattern tuples for iter-11 phrasing"
  ```

### Phase 2 — Demo script + real-LLM run

**Files**:
- Create: `scripts/demo_iter_12.sh` — clone of
  `demo_iter_11.sh` with iter-12 header noting the
  router extension; `.iter12-mcp.json` config filename.
- Modify: `Makefile` — `make demo` aliases to
  `demo-iter-12`; iter-11 stays as a regression
  baseline.

#### Step 2.1 — Demo script

- [ ] **Copy + adapt**:

  ```bash
  cp scripts/demo_iter_11.sh scripts/demo_iter_12.sh
  chmod +x scripts/demo_iter_12.sh
  ```

  Edit the header to say `iter-12`, replace the iter-11
  three-fix narrative with the iter-12 router-extension
  narrative, and rename `.iter11-mcp.json` →
  `.iter12-mcp.json`. The BLOCKED-surfacing tail
  (printing the `retry-blocked` invocation) stays
  unchanged — it's exactly what we want exercised this
  iteration.

- [ ] **Makefile alias**:

  ```makefile
  demo: demo-iter-12 ## Alias for the current iteration's demo

  demo-iter-12: ## Run iter-12 e2e (router tuples + retry-blocked close)
  	bash scripts/demo_iter_12.sh

  demo-iter-11: ## Run iter-11 e2e — regression baseline
  	bash scripts/demo_iter_11.sh
  ```

- [ ] **Syntax check + commit**:

  ```bash
  bash -n scripts/demo_iter_12.sh
  git add scripts/demo_iter_12.sh Makefile
  git commit -m "chore(demo): demo_iter_12.sh + Makefile alias"
  ```

#### Step 2.2 — Pre-flight + real-LLM run

- [ ] **Pre-flight smoke check** (ADR-008):

  ```bash
  make smoke-llm
  ```

  Expected: PASS. If transient latency fail, re-run once
  (iter-11 saw this; it cleared on second try).

- [ ] **Stash agent demo outputs from prior runs** so the
  iter-12 demo starts from a clean working tree:

  ```bash
  git status --short
  ```

  Expected: only iter-12 plan + (later) iter-12 commits
  staged. If `apps/web/`, `docs/adr/0010-0019`,
  `docs/design/`, `examples/` are untracked from prior
  runs, **leave them alone** — they're harmless target_repo
  artifacts and don't affect the demo. (CLAUDE.md ADR-009.)

- [ ] **Run the demo**:

  ```bash
  AI_TEAM_DEMO_NON_INTERACTIVE=1 bash scripts/demo_iter_12.sh
  ```

  Wall-clock budget 30 min; cost ceiling $5.00.

- [ ] **If Backend lands BLOCKED**: surface the task_id and
  retry:

  ```bash
  # Find the BLOCKED Backend task:
  docker exec ai_team_postgres psql -U ai_team -d ai_team -t -c "
    SELECT payload_json -> 'payload' ->> 'task_id'
    FROM audit_log
    WHERE correlation_id = '<CORR>'
      AND sender = 'backend_developer'
      AND payload_json -> 'payload' ->> 'status' = 'blocked'
    ORDER BY id DESC LIMIT 1;
  "
  # Then retry it:
  uv run ai-team retry-blocked <task_id>
  # Watch the chain continue:
  uv run ai-team watch --correlation <CORR:8>
  ```

  Capture the retry's outcome (Backend DONE → QA runs →
  `pending_review`) in the demo report.

- [ ] **If `pending_review` appears**: approve:

  ```bash
  uv run ai-team list-pending
  uv run ai-team approve <review_id>
  ```

  This closes the loop iter-3..11 all reached for.

#### Step 2.3 — Demo report

- [ ] **Write `docs/iterations/iter_12_demo_report.md`**
  mirroring `iter_11_demo_report.md`'s structure:

  - Outcome paragraph naming which success-criterion branch
    (4a / 4b / 4c) the run hit.
  - "What worked" / "What didn't" sections.
  - Audit-log timeline table (same SQL as iter-11).
  - Cost / quota table from `metadata.llm`.
  - Artifacts produced (including any retry_attempt=2
    audit rows, QA artifacts if produced).
  - Action items for iter-13 (if any).
  - "Why this demo is a net win" closing.

- [ ] **Commit**:

  ```bash
  git add docs/iterations/iter_12_demo_report.md
  git commit -m "docs(iter-12): real-LLM demo report"
  ```

### Phase 3 — Retro + iter-13 handoff + gates + merge

#### Step 3.1 — Final gate sweep

- [ ] **Run every gate**:

  ```bash
  make lint typecheck sec test test-integration smoke-llm
  uv run ruff format --check .
  ```

  Expected: all green; 0 high-severity bandit;
  410 + N new tests pass.

- [ ] **Diff-cover ≥ 80%** with combined unit + integration
  coverage:

  ```bash
  uv run pytest tests/unit tests/integration --cov --cov-report=xml -q
  uv run diff-cover coverage.xml --compare-branch=origin/main --fail-under=80
  ```

  Expected: PASS. Phase 1 is one-tuple + one test, near
  100 % on those lines. Phase 2 is shell + docs.

#### Step 3.2 — Retro + iter-13 handoff

- [ ] **Write `docs/iterations/iter_12_retro.md`** mirroring
  iter_11_retro.md's structure:

  - "What shipped" — phase summary with commit references.
  - "What went well" / "What didn't" / "Surprises" — short
    bullets, evidence-anchored.
  - "Action items for iter-13" — depends on Phase 2's
    outcome:
    - If chain closed (4a): iter-13 focus is **TL Backend
      decomposition** + carry-over cleanup (the loop is
      proven, optimisation is next).
    - If BLOCKED-loop (4b): iter-13 focus is
      **investigating why retries keep racing the MCP** +
      possibly TL Backend decomposition.
    - If happy-path (4c): iter-13 focus is **forcing the
      MCP race in a test environment** so the retry path
      gets exercised before relying on it in production.
  - "Stats" — commits, tests, real-LLM spend, diff-cover.
  - "Ready-to-paste prompt for iter-13" → points to
    handoff doc.

- [ ] **Write `docs/iterations/iter_13_handoff.md`** — same
  structure as iter_12_handoff.md.

- [ ] **Commit**:

  ```bash
  git add docs/iterations/iter_12_retro.md docs/iterations/iter_13_handoff.md
  git commit -m "docs(iter-12): retro + iter-13 handoff"
  ```

#### Step 3.3 — Mark PR ready, watch CI, squash-merge

- [ ] **Mark PR ready** + **watch CI** + **squash-merge**:

  ```bash
  gh pr ready
  gh pr checks --watch
  gh pr merge --squash
  ```

  (Skip `--delete-branch` if it fails the way iter-11's
  did — main is checked out in the primary worktree.
  Branch on GitHub auto-deletes anyway.)

## What we are NOT doing this iteration

- **Startup-time MCP failure investigation** (carry-over
  item 3 from iter-12 handoff). Useful but exploratory;
  decoupled from closing the retry-blocked loop.
- **TL Backend decomposition** (carry-over from iter-9/10/11).
  Significant work touching TL's `build_outputs` and
  system prompt; deferred until retry-blocked is proven
  end-to-end.
- **Architect's $2.47/call spend watch** — pure data
  collection, no code change. iter-13 picks up if pattern
  reproduces.
- **HoldQueue persistence, audit_writer role, hash-chain
  alert, GitHubTargetRepo, transactional TL,
  pytest-rerunfailures pin, BaseAgent template refactor.**
  Long-standing carry-overs untouched.

## Risks

- **MCP race doesn't fire this run.** The race is
  intermittent. iter-12 success criterion 4c covers this:
  demo report explicitly notes the router didn't get
  exercised + iter-13 picks up "force the race" as an
  action item. The router extension's unit test still
  pins the new pattern tuples behind a verbatim iter-11
  summary, so the code change is validated against the
  real failure mode regardless.
- **MCP race fires but Backend's NEW phrasing differs
  from both iter-10 and iter-12 tuples.** Possible if the
  LLM emits a third variant. We'd see Backend FAILED, no
  router rewrite. iter-13 adds another tuple — the
  pattern-tuple design from iter-10 is built for exactly
  this incremental addition.
- **Retry hits the 5-attempt cap.** Possible if MCP is
  persistently broken in this demo's environment. iter-11's
  cap prevents quota burn; iter-12 demo report would name
  the outcome (still a clean stop, not a hang).
- **Multiple retries → Backend's cached_input keeps
  growing**, possibly hitting opus/sonnet input-token
  limits. Backend's iter-11 demo cached_input was 2.6 M;
  4 retries on top could be 5-6 M. claude -p has its own
  limits per call. iter-12 should keep an eye on this in
  the audit_log per-retry — if total tokens per retry
  grows beyond ~3 M cached, iter-13 needs a strategy
  (clear cache, restart session, decompose).

## Cost projection

| Phase | Type                          | Estimate                  |
|-------|-------------------------------|---------------------------|
| 0     | docs                          | $0                        |
| 1     | code + 1 unit test            | $0                        |
| 2     | shell + real-LLM demo + retries | ~$2.00 expected (one chain + one retry); +$0.50 if BLOCKED-loop |
| 3     | docs + CI                     | $0                        |
| **Total** |                           | **~$2.50 expected, $5 ceiling** |

Quota check before Phase 2. iter-11 spent $3.41 (driven
by Architect's $2.47); iter-12 may come in lower if
Architect's session is shorter (no fresh consolidation
needed, the iter-11 ADR is on disk) OR higher if multiple
retries happen.

## Workflow

- Plan-before-code: this file lands as Phase 0's commit;
  no Phase-1+ code until owner approves.
- Conventional commits; squash-merge on the iter-12 PR.
- Each phase's "Commit" row is one (and only one) commit.
- Run `make lint typecheck sec test` after each phase.
- Final demo report goes in the same PR.

## Ready-to-paste prompt for iter-13

Lives in `docs/iterations/iter_13_handoff.md` (Phase 3.2).
