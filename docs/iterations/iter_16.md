# Iteration 16 — Plan

- **Status**: Draft (awaiting owner approval)
- **Plan author**: Claude (Opus 4.7)
- **Date drafted**: 2026-05-20
- **Base commit**: `8dddf52` on `main` (iter-15 squash)
- **Branch**: `worktree-iter-16` (cut from `origin/main` at plan
  commit)
- **Anchors (do not contradict)**: ADR-001 (orchestrator),
  ADR-008 (LLM access), iter-15 retro + demo report.
- **Carry-overs addressed**: items 1–2 of
  `docs/iterations/iter_16_handoff.md` — add the two new
  failure verbs the iter-15 demo's row 218 surfaced
  (`"unreachable"`, `"unavailability"`) to
  `_MCP_FAILURE_VERB_SET`; re-run the iter-15-shape demo
  to finally close the `pending_review` loop iter-3..15
  all reached for.
- **Deferred unchanged** (carry-over items 3–13 from iter-16
  handoff): TL over-decomposition prompt hint (now FIVE-
  iteration carry-over; small but bundle-with-#1 if scope
  allows), TL Backend decomposition (SIX-iteration carry-
  over), HoldQueue persistence, `pytest-rerunfailures`
  plugin pin, startup-time MCP failure investigation,
  Architect spend watch, `audit_writer` Postgres role,
  hash-chain alert, `GitHubTargetRepo`, transactional TL
  decomposition, `BaseAgent` template refactor.

## Goal — one sentence

Add `"unreachable"` and `"unavailability"` to
`_MCP_FAILURE_VERB_SET`, then re-run the iter-15-shape
demo so Backend's third attempt commits the
implementation tree (US-1 AC-7 `## Files` section +
updated `sample/report.md` + matching test assertion
already in the working tree from iter-15) and the chain
finally reaches `pending_review`.

## Success criteria (binary, measurable)

1. **`_MCP_FAILURE_VERB_SET` extended** in
   `core/dispatcher/mcp_race_router.py` with two new
   entries:
   - `"unreachable"` — matches the iter-15 demo row 218
     phrasing "MCP tools (ai-team-repo) were
     unreachable".
   - `"unavailability"` — matches the iter-15 demo row
     218 phrasing "blocked by the same MCP
     unavailability". (Worth noting: `"unavailable"`
     is NOT a substring of `"unavailability"` —
     `"unavailab"` is common but position 9 differs:
     "le" vs "lity". Iter-15 demo report Failure 1
     confirmed this empirically.)

   Set semantics unchanged (any token AND any verb
   co-occur → BLOCKED). Cross-product is now 3 x 9 = 27
   combinations. Both additions are domain-specific
   (verbal/noun forms of "service unavailable" that
   LLMs naturally produce when reporting MCP outages) →
   near-zero false-positive risk preserved.

2. **One new unit test** in
   `tests/unit/test_mcp_race_router.py`
   (`test_routes_iter15_demo_backend_retry_summary_to_blocked`)
   pins iter-15 demo correlation
   `efbd0ccc-f607-4592-861a-aaa74973dace` row 218
   summary verbatim. Existing 9 router tests stay green
   (cross-product additions are strict superset).

3. **`make lint typecheck sec test test-integration
   smoke-llm`** all green. Diff-cover ≥ 80 %.
   `uv run ruff format --check .` clean. 0 high-severity
   bandit findings.

4. **Real-LLM demo** (`scripts/demo_iter_16.sh`) re-runs
   the iter-15-shape task. Three valid outcome branches:
   - **(a) Chain reaches `pending_review` end-to-end.**
     Backend's third attempt should benefit from
     iter-15's cross-product matcher + iter-16's two new
     verbs + the implementation tree already in working
     state from iter-15. The remaining work is: commit
     the iter-15-added `report_writer.py` `## Files`
     section + updated `sample/report.md` +
     `tests/test_stages.py` assertion → run pytest →
     open PR. If MCP is healthy during that window,
     Backend produces a clean `task_report(done)`, QA
     runs the v2 smoke + regression suite, emits
     `request_human_review`, `pending_review` row
     appears, demo auto-approves, **chain closes**.
     **The long-awaited iter-3..15 close.**
   - **(b) Backend hits MCP race again, cross-product
     catches it, retry-blocked engages, eventually
     succeeds OR caps out at 5 retries.** Still
     recoverable. Demo report names the path; if Backend
     succeeds within budget the loop closes; if it caps
     out, iter-17 picks up TL Backend decomposition
     (SIX-iteration carry-over).
   - **(c) Backend hits MCP race with a phrasing whose
     tokens fall OUTSIDE the two sets** (a NEW token or
     a tenth failure verb). Documents the verbatim
     phrasing; iter-17 picks up the new entry. Less
     likely than 4c-from-iter-14 was — the verb set is
     now broad enough to cover "MCP X is Y" where Y is
     any standard service-unavailable phrase.

## Phases

Plan-before-code: this document lands as Phase 0's commit.
No Phase 1+ work until the owner approves.

### Phase 0 — Plan + branch setup

- [x] **Cut branch from origin/main** (done at draft time):
  ```bash
  git checkout -b worktree-iter-16 origin/main
  ```
- [ ] **Commit this plan**:
  ```bash
  git add docs/iterations/iter_16.md
  git commit -m "docs(iter-16): plan — two new failure verbs + close pending_review loop"
  ```
- [ ] **Open draft PR** with the plan link + iter-15
  demo's findings as motivation.

### Phase 1 — Extend `_MCP_FAILURE_VERB_SET` + unit test (TDD)

**Files**:
- Modify: `core/dispatcher/mcp_race_router.py` — append
  two entries to `_MCP_FAILURE_VERB_SET` + update the
  docstring's historical-failures list with iter-15 demo
  wording.
- Modify: `tests/unit/test_mcp_race_router.py` — add
  one test pinning iter-15 demo row 218 verbatim.

#### Step 1.1 — Failing test first (RED)

- [ ] **Add the failing test** to
  `tests/unit/test_mcp_race_router.py`:

  ```python
  def test_routes_iter15_demo_backend_retry_summary_to_blocked() -> None:
      """iter-15 demo (correlation efbd0ccc-f607-4592-861a-
      aaa74973dace) Backend's retry session (row 218) reported
      the failure with two NEW verbs not in iter-15's
      _MCP_FAILURE_VERB_SET: 'MCP tools ... were unreachable'
      + 'blocked by the same MCP unavailability'. Both are
      domain-specific synonyms of 'unavailable' / 'not
      available' the LLM picked organically. iter-16 adds
      them as set entries (the cross-product design's
      intended extension path). Pinned verbatim from
      iter_15_demo_report.md Failure 1.
      """
      summary = (
          "Backend Developer: tests failed. The "
          "idea-validator v2 implementation was already "
          "substantially complete. Code audit identified "
          "two spec violations that were fixed. Tests "
          "could not be run: MCP tools (ai-team-repo) "
          "were unreachable and native Bash is blocked "
          "for pytest/uv per role constraints. Branch "
          "creation, commit, push, and PR open are all "
          "blocked by the same MCP unavailability. "
          "Recommend re-running this task once the "
          "ai-team-repo MCP server is healthy."
      )
      out = maybe_route_mcp_race_to_blocked(_failed_report(summary))
      assert isinstance(out.payload, TaskReportPayload)
      assert out.payload.status == TaskStatus.BLOCKED
      assert out.payload.blocked_on == "mcp_unhealthy"
      assert out.payload.summary == summary
  ```

  Note the test deliberately excludes the iter-15 row
  218 sentence "Recommend re-running this task once the
  ai-team-repo MCP server is healthy" — that contains
  "MCP server" + "healthy", and "MCP server" IS in the
  token set; if "healthy" were a failure verb the
  matcher might fire spuriously. (It's not, but worth
  documenting the false-positive frontier the cross-
  product still respects.)

- [ ] **Run the test** — expect FAIL because neither
  "unreachable" nor "unavailability" is in the current
  verb set (iter-15 demo proved this empirically):

  ```bash
  uv run pytest tests/unit/test_mcp_race_router.py -v
  ```

  Expected: 9 PASS + 1 FAIL (the new iter-15-row-218
  test; status stays FAILED, not BLOCKED).

#### Step 1.2 — Add the two verbs (GREEN)

- [ ] **Edit
  `core/dispatcher/mcp_race_router.py`** to append two
  set entries:

  ```python
  _MCP_FAILURE_VERB_SET: frozenset[str] = frozenset(
      {
          "never connected",
          "never finished connecting",
          "still connecting",
          "unavailable",
          "not available",
          "failed to connect",
          "could not connect",
          # iter-16: Backend's iter-15 demo retry surfaced two
          # new domain-specific synonyms of "unavailable".
          # `"unavailable"` is NOT a substring of
          # `"unavailability"` (position 9 differs: "le" vs
          # "lity") so it needs its own entry. See
          # iter_15_demo_report.md Failure 1.
          "unreachable",
          "unavailability",
      }
  )
  ```

- [ ] **Update the module docstring** with iter-15 demo's
  wording in the historical-failures list:

  ```python
  - iter-15 demo: Backend retry (correlation efbd0ccc-...)
                    "MCP tools (ai-team-repo) were unreachable
                    ... blocked by the same MCP unavailability"
                  (added iter-16 — two new domain-specific
                  synonyms of "unavailable" the LLM picked
                  organically. Same cross-product design;
                  just two more set entries.)
  ```

- [ ] **Run tests — expect GREEN**:

  ```bash
  uv run pytest tests/unit/test_mcp_race_router.py -v
  uv run pytest tests/unit -q
  ```

  Expected: all 10 router tests pass; 378 unit tests
  pass.

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
  git commit -m "feat(mcp-router): two new failure verbs from iter-15 demo"
  ```

### Phase 2 — Demo script + real-LLM run + report

**Files**:
- Create: `scripts/demo_iter_16.sh` — clone of
  `demo_iter_15.sh` with iter-16 header narrative;
  `.iter16-mcp.json` config filename.
- Modify: `Makefile` — `make demo` aliases to
  `demo-iter-16`; iter-15 stays as a regression
  baseline.

#### Step 2.1 — Demo script

- [ ] **Copy + adapt**:

  ```bash
  cp scripts/demo_iter_15.sh scripts/demo_iter_16.sh
  chmod +x scripts/demo_iter_16.sh
  ```

  Update the header to say `iter-16`, replace the
  iter-15 cross-product narrative with iter-16's
  two-new-verbs narrative, and rename
  `.iter15-mcp.json` → `.iter16-mcp.json`. The
  auto-retry-blocked + auto-approve tail (steps 6.5/7
  + 6.6/7) stays unchanged — it's exactly what we want
  exercised this iteration.

- [ ] **Makefile alias**:

  ```makefile
  demo: demo-iter-16 ## Alias for the current iteration's demo

  demo-iter-16: ## Run iter-16 e2e (two new verbs + close pending_review loop)
  	bash scripts/demo_iter_16.sh

  demo-iter-15: ## Run iter-15 e2e — regression baseline (cross-product matcher)
  	bash scripts/demo_iter_15.sh
  ```

- [ ] **Syntax check + commit**:

  ```bash
  bash -n scripts/demo_iter_16.sh
  git add scripts/demo_iter_16.sh Makefile
  git commit -m "chore(demo): demo_iter_16.sh + Makefile alias"
  ```

#### Step 2.2 — Pre-flight + real-LLM run

- [ ] **Pre-flight smoke**:

  ```bash
  make smoke-llm
  ```

  Expected: PASS. iter-15 saw no flakes; iter-16 may.
  Re-run once on flake.

- [ ] **Sanity-check the working tree**:

  ```bash
  git status --short
  ```

  Expected: only iter-16 commits; leave untracked
  `examples/sandbox/idea-validator/` etc. ALONE — those
  are iter-15's implementation artifacts the demo's
  third attempt should commit.

- [ ] **Run the demo**:

  ```bash
  AI_TEAM_DEMO_NON_INTERACTIVE=1 bash scripts/demo_iter_16.sh
  ```

  Wall-clock budget 45 min (30 initial + 15 retry).
  Cost ceiling $5.00.

- [ ] **Capture outcomes** — auto-retry-blocked tail
  prints which branch (4a/4b/4c) was hit. Pull the
  audit_log via `docker exec` to confirm final task
  state.

#### Step 2.3 — Demo report

- [ ] **Write `docs/iterations/iter_16_demo_report.md`**
  mirroring `iter_15_demo_report.md`'s structure:

  - Outcome paragraph naming which 4a / 4b / 4c branch
    the run hit.
  - "What worked" / "What didn't" sections.
  - Audit-log timeline table (same SQL as iter-15).
  - Cost / quota table from `metadata.llm`.
  - Artifacts produced (any new commits, QA artifacts,
    pending_review row).
  - If criterion 4a or 4b ends in close: explicit note
    that **the `pending_review` loop closed end-to-end
    for the first time in sixteen iterations**.
  - If criterion 4c: verbatim new phrasing + iter-17
    candidate set additions.
  - "Why this demo is a net win" closing.

- [ ] **Commit**:

  ```bash
  git add docs/iterations/iter_16_demo_report.md
  git commit -m "docs(iter-16): real-LLM demo report"
  ```

### Phase 3 — Retro + iter-17 handoff + gates + merge

#### Step 3.1 — Final gate sweep

- [ ] **Run every gate**:

  ```bash
  make lint typecheck sec test test-integration smoke-llm
  uv run ruff format --check .
  ```

  Expected: all green; 0 high-severity bandit;
  ~420 + 1 new test passes.

- [ ] **Diff-cover ≥ 80%**:

  ```bash
  uv run pytest tests/unit tests/integration --cov --cov-report=xml -q
  uv run diff-cover coverage.xml --compare-branch=origin/main --fail-under=80
  ```

#### Step 3.2 — Retro + iter-17 handoff

- [ ] **Write `docs/iterations/iter_16_retro.md`** mirroring
  iter_15_retro.md's structure.

- [ ] **Write `docs/iterations/iter_17_handoff.md`** — same
  structure as iter_16_handoff.md. iter-17 priority
  depends on the demo outcome:
  - 4a (loop closed): iter-17 focus shifts to
    **TL Backend decomposition** (now SEVEN-iteration
    carry-over) + HoldQueue persistence. The tactical
    layer (matcher + retry + routing) is proven;
    structural improvements are next.
  - 4b (retries succeed eventually): same as 4a, plus
    note that retry path is exercised + stable.
  - 4c (new phrasing escapes): one or two more verb-set
    entries + TL Backend decomposition.

- [ ] **Commit**:

  ```bash
  git add docs/iterations/iter_16_retro.md docs/iterations/iter_17_handoff.md
  git commit -m "docs(iter-16): retro + iter-17 handoff"
  ```

#### Step 3.3 — Mark PR ready, watch CI, squash-merge

- [ ] **Mark PR ready** + **watch CI** + **squash-merge**:

  ```bash
  gh pr ready
  gh pr checks --watch
  gh pr merge --squash
  ```

## What we are NOT doing this iteration

- **TL over-decomposition prompt hint** (carry-over #3
  from iter-16 handoff). Originally considered as
  bundle-with-#1 in this plan, but excluded to keep
  iter-16's diff laser-focused on the loop close.
  Architect's $0.98 plateau is real but not blocking;
  iter-17 picks up.
- **TL Backend decomposition** (SIX-iteration carry-
  over). The proper next-iteration work after the
  tactical close — needs its own plan + scoped
  refactor + dedicated demo runs.
- **HoldQueue persistence, audit_writer role, hash-
  chain alert, GitHubTargetRepo, transactional TL,
  pytest-rerunfailures pin, BaseAgent template
  refactor.** Long-standing carry-overs untouched.

## Risks

- **MCP race fires AGAIN with a new phrasing** (criterion
  4c). The verb set now has 9 entries; cross-product
  covers 27 combinations. Possible if the LLM emits
  e.g. "MCP server timed out" — `"timed out"` would be
  a new verb. iter-17 picks up. The verb-set-extension
  path is exactly what the cross-product design was
  built for; this is no longer a structural issue.
- **Backend's third attempt session length exceeds
  600s.** iter-15 retry was 413s for an audit-only
  session. Adding commit + push + pytest run + open PR
  could push past the cap. Mitigations:
  - If timeout fires, `LLMTimeoutError` raises and
    dispatcher synthesizes `task_report(failed)` —
    NOT routed to BLOCKED (timeout isn't an MCP race).
    iter-17 carries over TL Backend decomposition as
    structural fix.
  - The iter-15 retry's tree changes are already on
    disk; even a timeout-truncated commit could be
    inspected by the owner manually.
- **MCP server actually broken (not racing).** The
  underlying MCP server reliability hasn't improved
  iter-by-iter — we've only added detection +
  routing + retry. If MCP is fundamentally unhealthy
  this run, retries cap at 5 and demo report names
  the outcome cleanly. iter-17 should investigate
  startup-time MCP failure (now 8-iteration carry-
  over).
- **Quota session-limit hits.** iter-15's 429 routing
  is in place; if quota fires during this demo, it's
  now a BLOCKED row + recoverable via retry-blocked.
  No $0.59 burn.

## Cost projection

| Phase | Type                          | Estimate                  |
|-------|-------------------------------|---------------------------|
| 0     | docs                          | $0                        |
| 1     | code + 1 unit test            | $0                        |
| 2     | shell + real-LLM demo + 0-2 retries | ~$2.00 expected; +$1 if multi-retry |
| 3     | docs + CI                     | $0                        |
| **Total** |                           | **~$2.00 expected, $5 ceiling** |

iter-15 spent $1.99 with substantial Backend work +
retry; iter-16 expected similar or lower if Backend's
third attempt succeeds quickly (most of the
implementation work is already done on disk).

## Workflow

- Plan-before-code: this file lands as Phase 0's commit.
- Conventional commits; squash-merge on the iter-16 PR.
- Each phase's "Commit" row is one (and only one) commit.
- Run `make lint typecheck sec test` after each phase.
- Final demo report goes in the same PR.

## Ready-to-paste prompt for iter-17

Lives in `docs/iterations/iter_17_handoff.md` (Phase 3.2).
