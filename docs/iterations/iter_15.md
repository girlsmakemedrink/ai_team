# Iteration 15 — Plan

- **Status**: Draft (awaiting owner approval)
- **Plan author**: Claude (Opus 4.7)
- **Date drafted**: 2026-05-20
- **Base commit**: `88f9c60` on `main` (iter-14 squash)
- **Branch**: `worktree-iter-15` (cut from `origin/main` at plan
  commit)
- **Anchors (do not contradict)**: ADR-001 (orchestrator),
  ADR-008 (LLM access), iter-14 retro + demo report.
- **Carry-overs addressed**: items 1–3 of
  `docs/iterations/iter_15_handoff.md` — generalise the
  substring router from tuple-of-tuples to cross-product
  matcher (closes the pattern-tuple diminishing-returns
  trend); re-run iter-14-shape demo; add
  `api_error_status=429 → BLOCKED(blocked_on='budget')`
  routing (small + recovers the iter-14 run-#1 quota burn
  pattern).
- **Deferred unchanged** (carry-over items 4–14 from iter-15
  handoff): TL Backend decomposition (SIX-iteration
  carry-over), TL over-decomposition prompt hint,
  HoldQueue persistence, `pytest-rerunfailures` plugin
  pin, startup-time MCP investigation, Architect spend
  watch, `audit_writer` Postgres role, hash-chain alert,
  `GitHubTargetRepo`, transactional TL decomposition,
  `BaseAgent` template refactor.

## Goal — one sentence

Replace the diminishing-returns tuple-of-tuples
`_MCP_RACE_PATTERNS` with a cross-product matcher (any
MCP-token × any failure-verb), add 429 → BLOCKED routing
so quota-session-limit hits are recoverable, then re-run
the iter-14-shape demo to finally close the
`pending_review` loop iter-3..14 all reached for.

## Success criteria (binary, measurable)

1. **Cross-product matcher** in
   `core/dispatcher/mcp_race_router.py`:
   - Two new module-level constants:
     - `_MCP_TOKEN_SET: frozenset[str] = frozenset({"MCP
       server", "MCP tools", "mcp__ai_team_repo"})`
       (`mcp__ai_team_repo__` is a substring of
       `mcp__ai_team_repo`, so it's redundant — keep the
       set minimal).
     - `_MCP_FAILURE_VERB_SET: frozenset[str] = frozenset(
       {"never connected", "never finished connecting",
       "still connecting", "unavailable", "not available",
       "failed to connect", "could not connect"})`.
   - `_matches_any_pattern(summary)` rewritten to check
     `any(tok in summary for tok in _MCP_TOKEN_SET) and
     any(verb in summary for verb in _MCP_FAILURE_VERB_SET)`.
   - `_MCP_RACE_PATTERNS` is REMOVED (superseded by the
     cross-product — no compatibility seam needed since
     all five existing verbatim-summary tests will pass
     against the cross-product matcher).
   - Module docstring updated to explain the design
     shift: "iter-15 generalises the iter-10 tuple-of-
     tuples after five iterations confirmed the LLM's
     phrasing variety outpaces incremental tuple
     addition (see iter_14_demo_report.md). Each set is
     narrow + domain-specific → near-zero false-positive
     property preserved; full cross product covers the
     combinatorial space."

2. **All five existing router unit tests stay green**
   against the new matcher (`test_routes_iter9...`,
   `iter8...`, `iter11...`, `iter13...`, plus
   `test_leaves_non_matching_failed_report_unchanged` +
   `test_leaves_done_and_blocked_reports_unchanged` +
   `test_leaves_non_task_report_messages_unchanged`).
   No verbatim summaries change; the matcher is a
   strict superset of the tuple matcher for these cases.

3. **Two new unit tests** in
   `tests/unit/test_mcp_race_router.py`:
   - `test_routes_iter14_demo_backend_summary_to_blocked` —
     pins iter-14 demo run-#2 row 201 verbatim summary
     ("MCP server `ai-team-repo` failed to connect" + "tools
     ... were not available after three ToolSearch retries")
     against the cross-product matcher. Cross-product
     catches both halves; previously no tuple matched.
   - `test_cross_product_does_not_match_unrelated_failures` —
     pins a genuine `AssertionError` summary AND a Bash
     permission-error summary to ensure neither MCP-token
     NOR failure-verb co-occurs in them. Negative case
     defending against false positives.

4. **429 → BLOCKED routing** in
   `core/llm/claude_code_headless.py`:
   - Add module-level constant
     `_QUOTA_SESSION_LIMIT_MARKERS = ("api_error_status", "429")`
     + helper `_is_quota_session_limit_stdout(stdout: str) -> bool`
     mirroring `_is_session_id_collision_stderr`.
   - In `invoke()`, after non-zero spawn and BEFORE
     raising `LLMInvocationError`, check the stdout for
     the quota-session-limit markers. If matched, raise
     `LLMBudgetExhaustedError` (already defined per
     iter-6) instead, with the verbatim
     `result.result` text as `reason`. The dispatcher's
     existing iter-6 path routes
     `LLMBudgetExhaustedError → BLOCKED(blocked_on='budget')`
     unchanged.
   - 2 unit tests pinning iter-14 run #1's stdout
     verbatim ("You've hit your session limit · resets
     12:10pm (Europe/Moscow)") + a regression for
     non-429 errors (LLMInvocationError still raised).

5. **`make lint typecheck sec test test-integration
   smoke-llm`** all green. Diff-cover ≥ 80 %.
   `uv run ruff format --check .` clean. 0 high-severity
   bandit findings.

6. **Real-LLM demo** (`scripts/demo_iter_15.sh`) re-runs
   the iter-14-shape task. Three valid outcome branches:
   - **(a) Chain reaches `pending_review` end-to-end.**
     Backend's third attempt benefits from
     iter-13's session fallback + iter-15's
     cross-product matcher + the implementation tree on
     disk from iter-13's `--resume` session. Whether
     Backend hits the MCP race (now BLOCKED via the
     cross-product) and retries OR succeeds first try,
     QA picks up its held assignment → `pending_review`
     row appears → demo auto-approves → chain closes.
     **The long-awaited end-to-end close
     iter-3..14 all reached for.**
   - **(b) Backend hits a phrasing whose tokens fall
     OUTSIDE the cross-product sets** (e.g., new MCP
     server name like `mcp__github`, or a failure verb
     like "timed out"). Documents the verbatim
     phrasing; iter-16 picks up the new entry. Less
     likely than 4c-from-iter-14 was, because the
     cross-product covers all 5 previously-observed
     phrasings + their natural variations.
   - **(c) Quota session-limit fires (like iter-14 run
     #1)** and 429-routing engages. Dispatcher emits
     `BLOCKED(blocked_on='budget')`. Auto-retry-blocked
     in the demo's tail picks it up — IF the reset
     window allows. If not, demo report names the
     quota-truncation but the chain stays recoverable
     (no $0.59 wasted spend; future invocations can
     resume).

## Phases

Plan-before-code: this document lands as Phase 0's commit.
No Phase 1+ work until the owner approves.

### Phase 0 — Plan + branch setup

- [x] **Cut branch from origin/main** (done at draft time):
  ```bash
  git checkout -b worktree-iter-15 origin/main
  ```
- [ ] **Commit this plan**:
  ```bash
  git add docs/iterations/iter_15.md
  git commit -m "docs(iter-15): plan — cross-product matcher + 429 routing + close pending_review loop"
  ```
- [ ] **Open draft PR** with the plan link + the iter-14
  demo's findings as motivation.

### Phase 1 — Cross-product matcher (TDD)

**Files**:
- Modify: `core/dispatcher/mcp_race_router.py` — replace
  `_MCP_RACE_PATTERNS` with `_MCP_TOKEN_SET` +
  `_MCP_FAILURE_VERB_SET`; rewrite `_matches_any_pattern`.
- Modify: `tests/unit/test_mcp_race_router.py` — add 2
  new tests; existing 7 tests stay verbatim.

#### Step 1.1 — Failing test first (RED)

- [ ] **Add the failing test** to
  `tests/unit/test_mcp_race_router.py`:

  ```python
  def test_routes_iter14_demo_backend_summary_to_blocked() -> None:
      """iter-14 demo run #2 (correlation b6e21108-2f3e-...)
      Backend row 201 reported the failure with a FIFTH
      distinct phrasing — 'MCP server `ai-team-repo` failed
      to connect' + 'tools ... were not available'. Neither
      iter-10's three tuples nor iter-12's two tuples nor
      iter-14's one tuple catches this combination. iter-15
      generalises to a cross-product matcher. Pinned
      verbatim from `iter_14_demo_report.md` Run #2 row 201.
      """
      summary = (
          "Backend Developer: tests failed. BLOCKED — "
          "MCP server `ai-team-repo` failed to connect. "
          "Tools `mcp__ai_team_repo__write_file_in_scope`, "
          "`mcp__ai_team_repo__run_shell`, "
          "`mcp__ai_team_repo__create_branch`, and "
          "`mcp__ai_team_repo__open_pr` were not available "
          "after three ToolSearch retries. Role constraints "
          "prohibit falling back to native Bash/Write/Edit."
      )
      out = maybe_route_mcp_race_to_blocked(_failed_report(summary))
      assert isinstance(out.payload, TaskReportPayload)
      assert out.payload.status == TaskStatus.BLOCKED
      assert out.payload.blocked_on == "mcp_unhealthy"
      assert out.payload.summary == summary


  def test_cross_product_does_not_match_unrelated_failures() -> None:
      """Sanity: an AssertionError summary + a Bash
      permission-error summary contain NO MCP-token AND
      NO failure-verb. Must stay FAILED."""
      assertion_summary = (
          "Backend Developer: tests failed. AssertionError "
          "in test_models.py line 42: expected score==7, "
          "got 5. Stack trace below."
      )
      bash_summary = (
          "Backend Developer: tests failed. Bash command "
          "'rm -rf /' was denied by permission sandbox; "
          "task could not proceed."
      )
      for summary in (assertion_summary, bash_summary):
          out = maybe_route_mcp_race_to_blocked(_failed_report(summary))
          assert isinstance(out.payload, TaskReportPayload)
          assert out.payload.status == TaskStatus.FAILED
          assert out.payload.blocked_on is None
  ```

- [ ] **Run the tests** — expect 1 new FAIL (iter14 test)
  + 1 new PASS (negative case, tuple matcher also rejects):

  ```bash
  uv run pytest tests/unit/test_mcp_race_router.py -v
  ```

  Expected: 8 PASS + 1 FAIL (iter14 — neither MCP-token
  nor failure-verb set exists yet, so existing tuple
  matcher won't catch it).

#### Step 1.2 — Cross-product matcher (GREEN)

- [ ] **Rewrite
  `core/dispatcher/mcp_race_router.py`** with two
  frozensets + a cross-product check. Replace lines
  46-60 (the `_MCP_RACE_PATTERNS` tuple) with:

  ```python
  # iter-15 replaces iter-10's tuple-of-tuples with a
  # cross-product of two narrow token sets. Each set is
  # domain-specific (MCP-naming tokens × claude -p MCP-
  # failure verbs); a summary matches iff it contains
  # ANY token from each set. Empirical motivation: after
  # five iterations of one-tuple-per-iteration (iter-10
  # through iter-14), the LLM produced four distinct
  # phrasings — the natural-language variation outpaced
  # incremental tuple addition. The cross-product covers
  # 3 × 7 = 21 combinations while preserving the
  # near-zero false-positive property: both sets are
  # narrow enough that genuine bugs ("AssertionError",
  # "import failed") contain no MCP-token at all.

  _MCP_TOKEN_SET: frozenset[str] = frozenset({
      "MCP server",
      "MCP tools",
      "mcp__ai_team_repo",
  })

  _MCP_FAILURE_VERB_SET: frozenset[str] = frozenset({
      "never connected",
      "never finished connecting",
      "still connecting",
      "unavailable",
      "not available",
      "failed to connect",
      "could not connect",
  })
  ```

  And the `_matches_any_pattern` helper becomes:

  ```python
  def _matches_any_pattern(summary: str) -> bool:
      has_mcp_token = any(tok in summary for tok in _MCP_TOKEN_SET)
      has_failure_verb = any(verb in summary for verb in _MCP_FAILURE_VERB_SET)
      return has_mcp_token and has_failure_verb
  ```

  Update the module docstring's historical-failure list
  to add iter-14 demo's wording + a note that iter-15
  replaces the tuple-of-tuples with the cross-product.

- [ ] **Run tests — expect ALL GREEN**:

  ```bash
  uv run pytest tests/unit/test_mcp_race_router.py -v
  uv run pytest tests/unit -q
  ```

  Expected: 9 router tests pass (7 original verbatim
  summaries via cross-product + 2 new); all 374 unit
  tests pass.

- [ ] **Lint + format + mypy**:

  ```bash
  uv run ruff check core/dispatcher/mcp_race_router.py tests/unit/test_mcp_race_router.py
  uv run ruff format --check core/dispatcher/mcp_race_router.py tests/unit/test_mcp_race_router.py
  uv run mypy core/dispatcher/mcp_race_router.py
  ```

- [ ] **Commit**:

  ```bash
  git add core/dispatcher/mcp_race_router.py tests/unit/test_mcp_race_router.py
  git commit -m "refactor(mcp-router): cross-product matcher replaces tuple-of-tuples"
  ```

### Phase 2 — 429 → BLOCKED routing (TDD)

**Files**:
- Modify: `core/llm/claude_code_headless.py` — add
  `_QUOTA_SESSION_LIMIT_MARKERS` + helper +
  `LLMBudgetExhaustedError` raise path.
- Modify: `tests/unit/test_claude_code_headless.py` —
  add 2 new tests (positive: 429 routes to budget
  exhausted; regression: non-429 still LLMInvocationError).

#### Step 2.1 — Failing test first (RED)

- [ ] **Add failing tests** mirroring the iter-13
  collision-retry test shape (`_ScriptedProc` helper).
  Positive case pins iter-14 run #1 stdout verbatim:

  ```python
  async def test_invoke_routes_429_session_limit_to_budget_exhausted() -> None:
      """iter-14 run #1 (correlation 7568ee93-...)
      Architect's claude -p exited 1 with this verbatim
      stdout — Anthropic's Max-5x session limit. iter-15
      routes this to LLMBudgetExhaustedError (existing
      iter-6 path) so the dispatcher emits
      BLOCKED(blocked_on='budget') instead of FAILED.
      Pinned from iter_14_demo_report.md Run #1."""
      stdout = (
          b'{"type":"result","subtype":"success",'
          b'"is_error":true,"api_error_status":429,'
          b'"duration_ms":115347,"num_turns":2,'
          b'"result":"You\'ve hit your session limit '
          b'\\u00b7 resets 12:10pm (Europe/Moscow)",'
          b'"stop_reason":"stop_sequence","session_id":"abc",'
          b'"total_cost_usd":0.587}'
      )
      proc = _ScriptedProc(returncode=1, stdout=stdout, stderr=b"")
      # ... wire proc via the same monkeypatch shape iter-13
      # uses. assert raises LLMBudgetExhaustedError, NOT
      # LLMInvocationError. Check the exception's `reason`
      # contains the verbatim "session limit" phrase.
  ```

  And a regression test:

  ```python
  async def test_invoke_non_429_error_still_raises_llm_invocation_error() -> None:
      """Generic non-zero exit without api_error_status=429
      markers must still raise LLMInvocationError. Defence
      against false-positive 429 routing."""
      stdout = b'{"type":"result","is_error":true,"result":"some other failure"}'
      # ... raises LLMInvocationError as before.
  ```

- [ ] **Run** — expect both FAIL (no 429-detection code
  yet → either both raise LLMInvocationError or test
  setup errors).

#### Step 2.2 — 429 detection + route (GREEN)

- [ ] **Add to `core/llm/claude_code_headless.py`** after
  `_SESSION_COLLISION_MARKERS` (existing iter-13
  constant):

  ```python
  _QUOTA_SESSION_LIMIT_MARKERS: tuple[str, ...] = (
      "api_error_status",
      "429",
      "session limit",
  )


  def _is_quota_session_limit_stdout(out: str) -> bool:
      """iter-15: Anthropic's Max-5x session limit
      surfaces in `claude -p` stdout as a result JSON
      with api_error_status=429 + a "session limit ·
      resets ..." message. iter-14 run #1 burned $0.59
      on this; routing to LLMBudgetExhaustedError lets
      the dispatcher emit BLOCKED(blocked_on='budget')
      so retry-blocked can recover after reset.
      Substring-only match — same near-zero false-positive
      shape as the session-id collision check."""
      return all(m in out for m in _QUOTA_SESSION_LIMIT_MARKERS)
  ```

  And in `invoke()`, after the `_is_session_id_collision_stderr`
  branch (iter-13) and BEFORE the final
  `raise LLMInvocationError(...)`, add:

  ```python
  if returncode != 0 and _is_quota_session_limit_stdout(
      stdout.decode(errors="replace")[:2000]
  ):
      log.info(
          "llm.invoke.quota_session_limit",
          model=model,
          has_session=bool(session_id),
      )
      raise LLMBudgetExhaustedError(
          model=model,
          reason="claude -p session limit (api_error_status=429)",
      )
  ```

  `LLMBudgetExhaustedError` already exists per iter-6;
  no new exception class needed.

- [ ] **Run tests — expect GREEN**:

  ```bash
  uv run pytest tests/unit/test_claude_code_headless.py -v
  ```

  Expected: 26+ adapter tests pass (existing 24 from
  iter-13's three + iter-14 baseline, plus 2 new).

- [ ] **Lint + format + mypy + commit**:

  ```bash
  uv run ruff check core/llm/claude_code_headless.py tests/unit/test_claude_code_headless.py
  uv run ruff format --check .
  uv run mypy core/llm/claude_code_headless.py
  git add core/llm/claude_code_headless.py tests/unit/test_claude_code_headless.py
  git commit -m "feat(llm): route 429 session limit to LLMBudgetExhaustedError"
  ```

### Phase 3 — Demo script + real-LLM run + report

**Files**:
- Create: `scripts/demo_iter_15.sh` — clone of
  `demo_iter_14.sh` with iter-15 header + `.iter15-mcp.json`.
- Modify: `Makefile` — `demo` aliases to `demo-iter-15`;
  iter-14 stays as regression baseline.

#### Step 3.1 — Demo script

- [ ] **Copy + adapt**:

  ```bash
  cp scripts/demo_iter_14.sh scripts/demo_iter_15.sh
  chmod +x scripts/demo_iter_15.sh
  ```

  Update header to say `iter-15`, replace iter-14 narrative
  with iter-15's cross-product + 429-routing narrative.
  Rename `.iter14-mcp.json` → `.iter15-mcp.json`.

- [ ] **Makefile**:

  ```makefile
  demo: demo-iter-15 ## Alias for the current iteration's demo

  demo-iter-15: ## Run iter-15 e2e (cross-product matcher + 429 routing + close loop)
  	bash scripts/demo_iter_15.sh

  demo-iter-14: ## Run iter-14 e2e — regression baseline (single tuple add)
  	bash scripts/demo_iter_14.sh
  ```

- [ ] **Commit**:

  ```bash
  bash -n scripts/demo_iter_15.sh
  git add scripts/demo_iter_15.sh Makefile
  git commit -m "chore(demo): demo_iter_15.sh + Makefile alias"
  ```

#### Step 3.2 — Pre-flight + real-LLM run

- [ ] **Pre-flight smoke**:

  ```bash
  make smoke-llm
  ```

- [ ] **Run demo**:

  ```bash
  AI_TEAM_DEMO_NON_INTERACTIVE=1 bash scripts/demo_iter_15.sh
  ```

  Wall-clock budget 45 min; cost ceiling $5.00.

- [ ] **Capture outcomes** per success criterion 6 (a/b/c).
  The auto-retry-blocked + auto-approve tail (preserved
  from iter-13/14) does most of the work.

#### Step 3.3 — Demo report

- [ ] **Write `docs/iterations/iter_15_demo_report.md`**
  mirroring iter_14_demo_report.md's structure. Name
  which 6a/6b/6c branch the run hit.

- [ ] **Commit**:

  ```bash
  git add docs/iterations/iter_15_demo_report.md
  git commit -m "docs(iter-15): real-LLM demo report"
  ```

### Phase 4 — Retro + iter-16 handoff + gates + merge

#### Step 4.1 — Final gate sweep

- [ ] **Run every gate**:

  ```bash
  make lint typecheck sec test test-integration smoke-llm
  uv run ruff format --check .
  ```

- [ ] **Diff-cover ≥ 80%**:

  ```bash
  uv run pytest tests/unit tests/integration --cov --cov-report=xml -q
  uv run diff-cover coverage.xml --compare-branch=origin/main --fail-under=80
  ```

#### Step 4.2 — Retro + iter-16 handoff

- [ ] **Write `docs/iterations/iter_15_retro.md`** —
  mirror iter_14_retro.md's structure.
- [ ] **Write `docs/iterations/iter_16_handoff.md`** —
  mirror iter_15_handoff.md's structure. iter-16
  priority depends on the demo outcome:
  - 6a (loop closed): **TL Backend decomposition** — SIX-
    iteration carry-over, structural fix to follow the
    tactical close.
  - 6b (sets need extending): one more entry in either
    `_MCP_TOKEN_SET` or `_MCP_FAILURE_VERB_SET` + TL
    Backend decomposition.
  - 6c (quota fired, recovered): more
    quota-handling improvements + TL Backend
    decomposition.

- [ ] **Commit**:

  ```bash
  git add docs/iterations/iter_15_retro.md docs/iterations/iter_16_handoff.md
  git commit -m "docs(iter-15): retro + iter-16 handoff"
  ```

#### Step 4.3 — Mark PR ready, watch CI, squash-merge

- [ ] **Mark PR ready** + **watch CI** + **squash-merge**:

  ```bash
  gh pr ready
  gh pr checks --watch
  gh pr merge --squash
  ```

## What we are NOT doing this iteration

- **TL Backend decomposition** (six-iteration carry-over).
  Pairs structurally with the tactical close, but
  splitting Backend's prompt + adding multi-output
  TL.build_outputs deserves its own focused iteration.
  iter-16 if iter-15 closes the loop.
- **HoldQueue persistence (Postgres-backed).** Now
  actively hurts demos but iter-15's three Phase-1+2+3
  deliverables fill the iteration budget.
- **TL over-decomposition prompt hint, audit_writer
  role, hash-chain alert, GitHubTargetRepo, transactional
  TL, pytest-rerunfailures pin, BaseAgent template
  refactor.** Long-standing carry-overs untouched.

## Risks

- **Cross-product false-positives.** Possible if an
  agent's legitimate summary contains both an MCP-token
  AND a failure-verb but the failure ISN'T an MCP race.
  Examples to consider: "MCP server connected; tests
  failed: assertion" (contains "MCP server" but no
  failure verb co-occurs). The two negative tests in
  Phase 1 + the existing `test_leaves_non_matching_failed
  _report_unchanged` cover this corner. If a real-LLM
  demo surfaces a false-positive, iter-16 narrows the
  token set OR adds a require-non-co-occurring-token
  layer.
- **MCP race doesn't fire this run.** Backend's
  `--resume`-able tree on disk might let it finish on
  the first attempt, in which case the cross-product
  matcher doesn't get exercised. That's still
  success-criterion 6a (the loop closes); demo report
  notes the matcher's unit-test coverage is what
  validates the design.
- **Quota session-limit hits during demo.** Now
  recoverable via #2 deliverable. iter-14 run #1's
  $0.59 burn no longer happens — instead BLOCKED row
  appears, retry-blocked engages after reset.
- **Backend's tree on disk is too stale.** Less likely
  (the spec hasn't changed since iter-13), but if
  iter-13's implementation has drifted from the v2
  spec's new edges, Backend rewrites large parts →
  session lengthens → race window opens. Mitigation:
  cross-product catches the resulting race regardless.

## Cost projection

| Phase | Type                          | Estimate                  |
|-------|-------------------------------|---------------------------|
| 0     | docs                          | $0                        |
| 1     | code + 2 unit tests           | $0                        |
| 2     | code + 2 unit tests           | $0                        |
| 3     | shell + real-LLM demo + 0-2 retries | ~$2.50 expected; +$1 if multi-retry |
| 4     | docs + CI                     | $0                        |
| **Total** |                           | **~$2.50 expected, $5 ceiling** |

iter-14 spent $2.48 (run #1 $0.59 burn + run #2 $1.89
chain). iter-15 expected lower if 429-routing engages
cleanly (no truncated burns) AND comparable on the
chain side. Architect's $0.98/call trajectory may
continue but the TL-over-decomposition prompt hint
(carry-over #4) is deferred to iter-16.

## Workflow

- Plan-before-code; this file = Phase 0's commit.
- Conventional commits; squash-merge on the iter-15 PR.
- Each phase's "Commit" row is one (and only one) commit.
- Run `make lint typecheck sec test` after each phase.
- Final demo report goes in the same PR.

## Ready-to-paste prompt for iter-16

Lives in `docs/iterations/iter_16_handoff.md` (Phase 4.2).
