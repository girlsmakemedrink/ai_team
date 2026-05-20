# Iteration 13 — Plan

- **Status**: Draft (awaiting owner approval)
- **Plan author**: Claude (Opus 4.7)
- **Date drafted**: 2026-05-20
- **Base commit**: `0220fe4` on `main` (iter-12 squash)
- **Branch**: `worktree-iter-13` (already cut from `origin/main`
  at plan-draft time)
- **Anchors (do not contradict)**: ADR-001 (orchestrator),
  ADR-008 (LLM access), iter-12 retro + demo report.
- **Carry-overs addressed**: items 1–2 of
  `docs/iterations/iter_13_handoff.md` — fix
  `ClaudeCodeHeadlessClient` session-id durability under
  dispatcher restart; re-run the demo end-to-end through
  Backend's retry to finally close the `pending_review`
  loop iter-3..12 all reached for.
- **Deferred unchanged** (carry-over items 3–13 from iter-13
  handoff): TL over-decomposition prompt hint, HoldQueue
  persistence, TL Backend decomposition,
  `pytest-rerunfailures` plugin pin, startup-time MCP
  failure investigation, Architect spend watch,
  `audit_writer` Postgres role, hash-chain alert,
  `GitHubTargetRepo`, transactional TL decomposition,
  `BaseAgent` template-method refactor.

## Goal — one sentence

Make `ClaudeCodeHeadlessClient` restart-resilient by
catching the "Session ID is already in use" error from
`claude -p` and retrying once with `--resume`, then re-run
the demo so iter-11's retry-blocked CLI finally runs
Backend's full claude -p session to completion — chain
reaches QA, QA emits `request_human_review`, owner
approves, `pending_review` loop closes for the first time
across thirteen iterations.

## Success criteria (binary, measurable)

1. **`ClaudeCodeHeadlessClient` survives dispatcher
   restart** with an existing on-disk session. The
   adapter's first invoke with `session_id=X` after a
   fresh process start (empty `_claimed_sessions`):
   - Builds `--session-id X` (current behavior).
   - On non-zero exit AND stderr containing
     `"Session ID"` AND `"already in use"`: discards the
     cache entry, rebuilds the command with `--resume X`,
     re-spawns once, returns the second response.
   - On any other non-zero exit: raises
     `LLMInvocationError` exactly as before (regression-safe).
   - On the first invoke succeeding: keeps the cache
     entry (no behavior change for the happy path).
   - Cache is updated to reflect "X is known to exist"
     after the successful retry so subsequent invokes use
     `--resume` directly without paying the failed-spawn
     cost.
2. **Unit tests pin the behavior** (`tests/unit/test_claude_code_headless.py`):
   - **Test A**: 1st spawn = returncode=1 + stderr containing
     "Session ID is already in use" + cmd contains
     `--session-id`; 2nd spawn = success + cmd contains
     `--resume`. Assert the return value comes from the
     2nd spawn AND that the 2nd cmd's argv contains
     `--resume` AND NOT `--session-id`.
   - **Test B**: 1st spawn = returncode=1 + stderr
     "Error: --invalid-flag" (a non-session error);
     adapter raises `LLMInvocationError` after the first
     spawn (NO retry). Existing iter-12 tests for the
     error path still pass.
   - **Test C**: After Test A's retry succeeds, a
     subsequent invoke with the same session_id uses
     `--resume` directly (no failed first spawn). Pins
     the cache update.
3. **`make lint typecheck sec test test-integration
   smoke-llm`** all green. Diff-cover ≥ 80 %.
4. **Real-LLM demo** (`scripts/demo_iter_13.sh`)
   exercises the retry-blocked loop **within the same
   dispatcher process** (no restart) and closes the
   chain. Steps:
   a. Submit the v2 task.
   b. Wait for the chain to reach a terminal state for
      Backend (BLOCKED or DONE).
   c. If BLOCKED: run `ai-team retry-blocked
      <backend_task_id>` from within the same script
      (the dispatcher is still alive — its
      `_claimed_sessions` has the session_id, so the
      retry uses `--resume` directly, no iter-13 fix
      needed for this path).
   d. Wait for Backend's retry to produce DONE.
   e. Wait for QA's `request_human_review` →
      `pending_review` row.
   f. Auto-approve via `ai-team approve <id>`.
   g. Print the final chain state.

   Three valid outcome branches:

   - **(a)** Backend BLOCKED → retry succeeds (`--resume`)
     → DONE → QA → pending_review → approved. **The
     long-awaited end-to-end close.**
   - **(b)** Backend DONE on first attempt (race
     didn't fire) → QA → pending_review → approved.
     Also a close, just without the retry exercised.
     Demo report explicitly notes that the iter-13
     fix's effect is proven by the unit tests rather
     than the demo run.
   - **(c)** Backend BLOCKED → retry → BLOCKED again
     (still recoverable) → owner retries up to 5
     times → eventually DONE or caps out. Demo report
     names whichever happened.

5. **All gates green on PR.** `make lint typecheck sec
   test test-integration smoke-llm` all pass.
   `uv run ruff format --check .` clean. 0 high-severity
   bandit findings.

## Phases

Plan-before-code: this document lands as Phase 0's commit.
No Phase 1+ work until the owner approves.

### Phase 0 — Plan + branch setup

- [ ] **Branch already cut** at plan-draft time:
  `git checkout -b worktree-iter-13 origin/main` (done).
- [ ] **Commit this plan**:
  ```bash
  git add docs/iterations/iter_13.md
  git commit -m "docs(iter-13): plan — session-id restart resilience + close pending_review loop"
  ```
- [ ] **Open draft PR**.

### Phase 1 — `ClaudeCodeHeadlessClient` session-id fallback (TDD)

**Files**:
- Modify: `core/llm/claude_code_headless.py` — extract
  the cmd-build + spawn + parse-non-zero-exit into a
  small helper, then wrap with the retry-on-session-id-
  collision logic in `invoke()`.
- Modify: `tests/unit/test_claude_code_headless.py` —
  add Tests A, B, C from success criterion #2.

#### Step 1.1 — Failing test first (RED)

- [ ] **Add Test A** (the load-bearing one): collision
  on first spawn, success on second spawn.

  ```python
  @pytest.mark.asyncio
  async def test_session_id_collision_retries_with_resume() -> None:
      """iter-12 demo (corr 3d442628) hit `Session ID ...
      already in use` when a dispatcher restart left a
      stale session_id on disk. iter-13 adds a single-
      retry fallback: detect the collision in stderr,
      swap --session-id for --resume, re-spawn once.
      """
      client = ClaudeCodeHeadlessClient()
      captured_argvs: list[tuple[str, ...]] = []

      call_count = [0]

      class _FakeProc:
          def __init__(self, returncode: int, stdout: bytes, stderr: bytes) -> None:
              self.returncode = returncode
              self._stdout = stdout
              self._stderr = stderr

          async def communicate(self) -> tuple[bytes, bytes]:
              return self._stdout, self._stderr

      async def _fake_create(*cmd: str, **_: Any) -> _FakeProc:
          captured_argvs.append(cmd)
          call_count[0] += 1
          if call_count[0] == 1:
              return _FakeProc(
                  returncode=1,
                  stdout=b"",
                  stderr=b"Error: Session ID 3d442628 is already in use.\n",
              )
          # Second spawn: success.
          payload = {
              "is_error": False,
              "result": "ok",
              "session_id": "3d442628",
              "usage": {"input_tokens": 1, "output_tokens": 1},
          }
          return _FakeProc(returncode=0, stdout=json.dumps(payload).encode(), stderr=b"")

      with patch(
          "core.llm.claude_code_headless.asyncio.create_subprocess_exec",
          new=AsyncMock(side_effect=_fake_create),
      ):
          response = await client.invoke(
              system_prompt="sp", user_message="u",
              model="haiku", session_id="3d442628",
          )

      assert call_count[0] == 2
      assert "--session-id" in captured_argvs[0]
      assert "--resume" not in captured_argvs[0]
      assert "--resume" in captured_argvs[1]
      assert "--session-id" not in captured_argvs[1]
      assert response.text == "ok"
  ```

- [ ] **Run test — expect FAIL** with
  `LLMInvocationError: claude -p exited 1: ... already
  in use ...`:

  ```bash
  uv run pytest tests/unit/test_claude_code_headless.py::test_session_id_collision_retries_with_resume -v
  ```

  Expected: 1 FAIL with the LLMInvocationError message.

#### Step 1.2 — Implement the fallback (GREEN)

- [ ] **Edit `core/llm/claude_code_headless.py`**:

  Add a module-level helper detecting the collision
  signature:

  ```python
  _SESSION_COLLISION_MARKERS: tuple[str, ...] = (
      "Session ID",
      "already in use",
  )


  def _is_session_id_collision_stderr(err: str) -> bool:
      """True iff `claude -p` rejected --session-id
      because the id is already on disk from a prior
      process. iter-13: detected on `claude -p exited 1`
      with stderr matching all markers — defense against
      the dispatcher-restart scenario iter-12 demo
      surfaced. See iter_12_demo_report.md Failure 1.
      """
      return all(m in err for m in _SESSION_COLLISION_MARKERS)
  ```

  Inside `invoke()`, after the existing non-zero-exit
  detection (around line 222), add the retry branch
  BEFORE the existing `raise LLMInvocationError`:

  ```python
  if proc.returncode != 0:
      err = stderr.decode(errors="replace")[:1000]
      out = stdout.decode(errors="replace")[:8000]
      log.error(
          "llm.invoke.failed",
          returncode=proc.returncode,
          stderr=err,
          stdout=out,
      )
      if _is_budget_exhausted_stdout(out):
          raise LLMBudgetExhaustedError(...)
      # iter-13: session-id collision under dispatcher
      # restart. The on-disk session was created by a
      # previous process; our in-memory cache doesn't
      # know. Retry once with --resume + cache the entry
      # so subsequent invokes skip the failed spawn.
      if session_id and _is_session_id_collision_stderr(err):
          if "--session-id" not in cmd:
              # Defense — this shouldn't happen, but
              # don't loop. Surface as a normal error.
              raise LLMInvocationError(
                  f"claude -p reported session collision but cmd already used --resume: stderr={err!r}"
              )
          log.info(
              "llm.invoke.session_collision.retry_with_resume",
              session_id=session_id,
          )
          # Swap --session-id for --resume in the cmd.
          idx = cmd.index("--session-id")
          cmd[idx] = "--resume"
          # Cache the id so subsequent invokes go direct.
          self._claimed_sessions.add(session_id)
          # Re-spawn once. NB: any other non-zero exit on
          # the retry path raises LLMInvocationError as
          # usual (no infinite retry).
          return await self._spawn_and_parse(
              cmd=cmd,
              model=model,
              model_id=model_id,
              timeout_s=timeout_s,
              env=effective_env,
              json_schema=json_schema,
              log=log,
              start=start,
          )
      raise LLMInvocationError(
          f"claude -p exited {proc.returncode}: stderr={err!r} stdout={out!r}"
      )
  ```

  Extract the spawn-and-parse path into a helper method
  `_spawn_and_parse(...)` so the retry can reuse the
  exact same code path (timeout handling, parsing, budget
  exhaust check, logging). This is the minimal change to
  avoid duplicating ~50 lines.

  Actual helper signature:

  ```python
  async def _spawn_and_parse(
      self,
      *,
      cmd: list[str],
      model: ModelTier,
      model_id: str,
      timeout_s: int,
      env: dict[str, str] | None,
      json_schema: dict[str, Any] | None,
      log: structlog.BoundLogger,
      start: float,
  ) -> LLMResponse: ...
  ```

  The current `invoke()` body's "spawn → wait → check
  returncode → parse" sequence moves into this helper.
  `invoke()` keeps the cmd-build + the retry orchestration.

- [ ] **Run Test A — expect PASS**:

  ```bash
  uv run pytest tests/unit/test_claude_code_headless.py::test_session_id_collision_retries_with_resume -v
  ```

- [ ] **Add Test B** (regression — non-session errors
  still raise):

  ```python
  @pytest.mark.asyncio
  async def test_non_session_error_still_raises_invocation_error() -> None:
      """Regression: errors other than session-id
      collision must still raise LLMInvocationError
      on the first spawn (no retry)."""
      client = ClaudeCodeHeadlessClient()
      call_count = [0]

      class _FakeProc:
          returncode = 1
          async def communicate(self) -> tuple[bytes, bytes]:
              return b"", b"Error: --some-other-flag is invalid\n"

      async def _fake_create(*_cmd: str, **_: Any) -> _FakeProc:
          call_count[0] += 1
          return _FakeProc()

      with patch(
          "core.llm.claude_code_headless.asyncio.create_subprocess_exec",
          new=AsyncMock(side_effect=_fake_create),
      ):
          with pytest.raises(LLMInvocationError, match="--some-other-flag"):
              await client.invoke(
                  system_prompt="sp", user_message="u",
                  model="haiku", session_id="sid-x",
              )
      assert call_count[0] == 1  # No retry happened.
  ```

- [ ] **Add Test C** (cache update after retry):

  ```python
  @pytest.mark.asyncio
  async def test_session_id_collision_caches_for_subsequent_calls() -> None:
      """After a successful collision-retry, subsequent
      invokes with the same session_id use --resume
      directly (no failed first spawn)."""
      client = ClaudeCodeHeadlessClient()
      captured_argvs: list[tuple[str, ...]] = []
      call_count = [0]

      class _FakeProc:
          def __init__(self, rc: int, out: bytes, err: bytes) -> None:
              self.returncode = rc
              self._o = out
              self._e = err
          async def communicate(self) -> tuple[bytes, bytes]:
              return self._o, self._e

      async def _fake_create(*cmd: str, **_: Any) -> _FakeProc:
          captured_argvs.append(cmd)
          call_count[0] += 1
          if call_count[0] == 1:
              return _FakeProc(1, b"",
                  b"Error: Session ID sid-y is already in use.\n")
          payload = {"is_error": False, "result": "ok",
                     "session_id": "sid-y",
                     "usage": {"input_tokens": 1, "output_tokens": 1}}
          return _FakeProc(0, json.dumps(payload).encode(), b"")

      with patch(
          "core.llm.claude_code_headless.asyncio.create_subprocess_exec",
          new=AsyncMock(side_effect=_fake_create),
      ):
          await client.invoke(system_prompt="sp", user_message="u1",
                              model="haiku", session_id="sid-y")
          await client.invoke(system_prompt="sp", user_message="u2",
                              model="haiku", session_id="sid-y")

      # First call: 2 spawns (--session-id then --resume).
      # Second call: 1 spawn (--resume directly, no collision).
      assert call_count[0] == 3
      assert "--session-id" in captured_argvs[0]
      assert "--resume" in captured_argvs[1]
      assert "--resume" in captured_argvs[2]
      assert "--session-id" not in captured_argvs[2]
  ```

- [ ] **Run all three new tests + existing adapter tests
  to confirm GREEN**:

  ```bash
  uv run pytest tests/unit/test_claude_code_headless.py -v
  ```

  Expected: every test passes, including the existing
  iter-12 session/budget/timeout tests.

- [ ] **Full unit suite + lint + format + mypy**:

  ```bash
  uv run pytest tests/unit -q
  uv run ruff check core/llm/claude_code_headless.py tests/unit/test_claude_code_headless.py
  uv run ruff format --check core/llm/claude_code_headless.py tests/unit/test_claude_code_headless.py
  uv run mypy core/llm/claude_code_headless.py
  ```

  Expected: clean.

- [ ] **Commit**:

  ```bash
  git add core/llm/claude_code_headless.py tests/unit/test_claude_code_headless.py
  git commit -m "fix(llm): retry --session-id collision with --resume"
  ```

### Phase 2 — Demo script + real-LLM run

**Files**:
- Create: `scripts/demo_iter_13.sh` — clone of
  `demo_iter_12.sh` with the new
  retry-blocked-and-wait-for-close logic.
- Modify: `Makefile` — `make demo` aliases to
  `demo-iter-13`; iter-12 stays as a regression baseline.

#### Step 2.1 — Demo script

- [ ] **Clone + adapt** `scripts/demo_iter_12.sh`:

  ```bash
  cp scripts/demo_iter_12.sh scripts/demo_iter_13.sh
  chmod +x scripts/demo_iter_13.sh
  ```

  Edit the header to say iter-13 and document the fix.
  Change `.iter12-mcp.json` → `.iter13-mcp.json`.
  Change task title.

  After the existing wait-for-pending_review loop
  (step 6/7), BEFORE step 7/7, INSERT a new "retry
  and wait for close" section:

  ```bash
  step "6.5/7 — If Backend lands BLOCKED, retry within the same dispatcher"
  if command -v psql >/dev/null 2>&1; then
      BLOCKED_TASK_ID=$(PGPASSWORD=ai_team psql -h 127.0.0.1 -U ai_team ai_team -t -A -c "
          SELECT payload_json -> 'payload' ->> 'task_id'
          FROM audit_log
          WHERE correlation_id = '$CORRELATION'
            AND sender = 'backend_developer'
            AND payload_json -> 'payload' ->> 'status' = 'blocked'
          ORDER BY id DESC LIMIT 1;
      " 2>/dev/null)
      if [[ -n "$BLOCKED_TASK_ID" ]]; then
          ok "Backend is BLOCKED on task $BLOCKED_TASK_ID — issuing retry-blocked"
          uv run ai-team retry-blocked "$BLOCKED_TASK_ID" || true
          # Wait up to 15 more minutes for the retry to produce a terminal
          # report + QA pending_review.
          deadline=$((SECONDS + 900))
          while (( SECONDS < deadline )); do
              review_count=$(curl -sf -H "Authorization: Bearer $OWNER_TOKEN" \
                  http://127.0.0.1:8000/api/reviews 2>/dev/null \
                  | python3 -c 'import sys, json; print(len(json.load(sys.stdin)))' 2>/dev/null \
                  || echo 0)
              if [[ "$review_count" -ge 1 ]]; then
                  ok "QA produced pending_review after retry (count=$review_count)"
                  break
              fi
              sleep 10
          done
      else
          ok "No BLOCKED Backend task — chain may have completed first try"
      fi
  fi

  step "6.6/7 — Auto-approve any pending_reviews"
  REVIEWS_JSON=$(curl -sf -H "Authorization: Bearer $OWNER_TOKEN" \
      http://127.0.0.1:8000/api/reviews 2>/dev/null || echo '[]')
  echo "$REVIEWS_JSON" | python3 -c '
  import json, subprocess, sys
  for r in json.load(sys.stdin):
      print(f"approving {r[\"id\"]}")
      subprocess.run(["uv", "run", "ai-team", "approve", r["id"],
                      "--comment", "iter-13 demo auto-approve"], check=False)
  '
  ```

- [ ] **Update Makefile**:

  ```makefile
  demo: demo-iter-13 ## Alias for the current iteration's demo

  demo-iter-13: ## Run iter-13 e2e (session-id fallback + close-the-loop)
  	bash scripts/demo_iter_13.sh

  demo-iter-12: ## Run iter-12 e2e — regression baseline (router tuples)
  	bash scripts/demo_iter_12.sh
  # ... iter-11/10 stay
  ```

- [ ] **Syntax check + commit**:

  ```bash
  bash -n scripts/demo_iter_13.sh
  git add scripts/demo_iter_13.sh Makefile
  git commit -m "chore(demo): demo_iter_13.sh + retry-and-approve close-the-loop"
  ```

#### Step 2.2 — Pre-flight + real-LLM run

- [ ] **Pre-flight smoke**:

  ```bash
  make smoke-llm
  ```

  Expected: PASS (re-run once if median latency flakes
  > 10 s; iter-11/12 both saw this).

- [ ] **Run the demo**:

  ```bash
  AI_TEAM_DEMO_NON_INTERACTIVE=1 bash scripts/demo_iter_13.sh
  ```

  Wall-clock budget 45 min (30 min initial chain + 15 min
  retry-and-close window); cost ceiling $5.00.

- [ ] **Watch for outcome 4(a) / 4(b) / 4(c)** per success
  criteria.

#### Step 2.3 — Demo report

- [ ] **Write `docs/iterations/iter_13_demo_report.md`**
  mirroring iter_12_demo_report.md structure:
  - Outcome paragraph naming which branch.
  - "What worked" / "What didn't" sections.
  - Audit-log timeline.
  - Cost / quota table.
  - Action items for iter-14.
  - Closing.

- [ ] **Commit**:

  ```bash
  git add docs/iterations/iter_13_demo_report.md
  git commit -m "docs(iter-13): real-LLM demo report"
  ```

### Phase 3 — Retro + iter-14 handoff + gates + merge

#### Step 3.1 — Final gate sweep

- [ ] **Run every gate**:

  ```bash
  make lint typecheck sec test test-integration smoke-llm
  uv run ruff format --check .
  ```

  Expected: all green; 0 high-severity bandit findings.

- [ ] **Diff-cover ≥ 80%** (combined unit + integration):

  ```bash
  uv run pytest tests/unit tests/integration --cov --cov-report=xml -q
  uv run diff-cover coverage.xml --compare-branch=origin/main --fail-under=80
  ```

#### Step 3.2 — Retro + iter-14 handoff

- [ ] **Write `docs/iterations/iter_13_retro.md`** with
  the iter-12 structure.
- [ ] **Write `docs/iterations/iter_14_handoff.md`** —
  same structure as iter_13_handoff.md.
- [ ] **Commit**:

  ```bash
  git add docs/iterations/iter_13_retro.md docs/iterations/iter_14_handoff.md
  git commit -m "docs(iter-13): retro + iter-14 handoff"
  ```

#### Step 3.3 — Mark PR ready, watch CI, squash-merge

- [ ] **Mark ready + watch + merge**:

  ```bash
  gh pr ready
  gh pr checks --watch
  gh pr merge --squash
  ```

## What we are NOT doing this iteration

- **HoldQueue persistence to Postgres** (carry-over from
  iter-12). Now actively relevant after iter-12's
  loss-on-restart finding, but bigger than iter-13's
  session-id fix. iter-14 candidate.
- **TL Backend decomposition** — five-iteration carry-over.
  Deferred until retry-blocked loop is proven closed.
- **TL over-decomposition prompt hint** — useful but
  decoupled.
- **`pytest-rerunfailures` plugin pin** — useful but
  decoupled. iter-14 if any iter-13 CI run flakes on it.
- **Startup-time MCP failure investigation** — useful
  but decoupled from closing the loop.
- **Architect spend watch** — purely data collection.
- **All other carry-overs from iter-13 handoff items
  9–13.**

## Risks

- **The collision detector matches a non-collision
  error.** Both markers (`"Session ID"`, `"already in
  use"`) co-occurring in stderr is a tight signature.
  False-positive risk: a future claude -p release could
  reword the error. Mitigation: defensive `if
  "--session-id" not in cmd: raise` guard in the retry
  branch — if the collision detector ever fires when we
  WEREN'T using `--session-id`, we surface the original
  error rather than loop. Pinned by Test B.
- **The retry's `--resume` itself errors** (e.g., session
  expired on disk). The retry's non-zero exit raises
  `LLMInvocationError` exactly as before. Owner sees a
  clear error and can issue another `retry-blocked` with
  a fresh correlation_id if needed. No silent failure.
- **Demo doesn't hit BLOCKED.** Possible if the MCP race
  is transient and Backend completes on first try. Demo
  report names outcome 4(b); fix is still proven by unit
  tests. Re-running the demo on the same day (when the
  race has been reliably reproducible iter-8..12) makes
  4(a) likely.
- **Backend's retry succeeds but QA still fails** for
  unrelated reasons (e.g., test assertions Backend's
  code doesn't pass). Then the chain reaches QA's
  `task_report(failed)` rather than `request_human_review`.
  Demo report names this; iter-14 picks up. iter-13
  still ships the session-id fix.

## Cost projection

| Phase | Type                                | Estimate                  |
|-------|-------------------------------------|---------------------------|
| 0     | docs                                | $0                        |
| 1     | code + 3 unit tests                 | $0                        |
| 2     | shell + real-LLM (chain + retry)    | ~$2.50 expected (one chain + one retry-via-resume); +$0.50 if retry hits BLOCKED again |
| 3     | docs + CI                           | $0                        |
| **Total** |                                 | **~$2.50 expected, $5 ceiling** |

Quota check before Phase 2. iter-12 spent $1.32; iter-13
may come in higher if Backend's retry runs the full
implementation work AND QA executes the test suite.

## Workflow

- Plan-before-code: this file lands as Phase 0's commit;
  no Phase-1+ code until owner approves.
- Conventional commits; squash-merge on the iter-13 PR.
- Each phase's "Commit" row is one (and only one) commit.
- Run `make lint typecheck sec test` after each phase.

## Ready-to-paste prompt for iter-14

Lives in `docs/iterations/iter_14_handoff.md` (Phase 3.2).
