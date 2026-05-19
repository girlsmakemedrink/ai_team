# Iteration 6 — Plan

- **Status**: Draft (awaiting owner approval)
- **Plan author**: Claude (Opus 4.7)
- **Date drafted**: 2026-05-19
- **Base commit**: `997873b` on `main` (iter-5 squash)
- **Branch**: `worktree-iter-6` (cut from `origin/main` at plan commit)
- **Anchors (do not contradict)**: ADR-001 (orchestrator), ADR-006
  (model tier per agent), ADR-008 (LLM access), iter-5 retro + demo
  report
- **Carry-overs addressed**: items 1–5 of
  `docs/iterations/iter_6_handoff.md` — raise per-tier budgets,
  `LLMBudgetExhaustedError` + dispatcher BLOCKED synthesis,
  `TaskStateReducer.on_drop`, demo wall-clock bump, and the
  re-run that finally closes the `pending_review` loop.
- **Deferred unchanged** (carry-over items 6–13 from iter-6 handoff):
  HoldQueue persistence, `audit_writer` Postgres role, hash-chain
  alert, `GitHubTargetRepo`, TL transactional decomposition,
  `pytest-rerunfailures` pin, `BaseAgent` template-method refactor,
  pre-flight MCP health-gate.

## Goal — one sentence

Close the iter-5 demo's `error_max_budget_usd` failure mode by
raising per-tier budget caps and gracefully surfacing
budget-exhaustion as `BLOCKED` (not `failed`), patch the
`HoldQueue.mark_failed` → `TaskStateReducer` gap that left
dropped child tasks `in_progress`, give v2-shaped demo chains
30 min of wall-clock instead of 20 — then re-run end-to-end
through `pending_review` → owner approve, the loop iter-3/4/5
all reached for.

## Success criteria (binary, measurable)

1. **Per-tier `--max-budget-usd` defaults raised.** New values in
   `core/llm/base.py:DEFAULT_MAX_BUDGET_USD_PER_TIER`: haiku
   `$0.30`, sonnet `$1.50`, opus `$4.00`. Unit test pins the
   values (so future "let's tighten the budgets" edits surface
   in review with reasoning attached).
2. **`LLMBudgetExhaustedError` distinct from
   `LLMInvocationError`.** New class in `core/llm/base.py`. The
   headless adapter detects
   `subtype=error_max_budget_usd` on `claude -p`'s stdout JSON
   (we already capture stdout per iter-5 Phase 4) and raises the
   distinct error. Unit test pins both the parsing and the raise.
3. **Dispatcher synthesises `BLOCKED` for
   `LLMBudgetExhaustedError`.** When `agent.handle()` raises this
   specific exception, the dispatcher emits a
   `TASK_REPORT(status=BLOCKED, summary="budget exhausted: …",
   blocked_on="budget")` instead of the iter-5 default
   `TASK_REPORT(status=failed, …)`. The HoldQueue **does not**
   drop dependents on `BLOCKED` (matches iter-3 contract: only
   `failed` cascades). The owner sees the BLOCKED report in
   `ai-team digest` and can manually retry with elevated budget.
   Integration test pins this behavior.
4. **`TaskStateReducer.on_drop` updates dropped child tasks.**
   When `HoldQueue.mark_failed` returns dropped messages, the
   dispatcher walks each, calls `TaskStateReducer.on_drop(child_task_id)`,
   and the corresponding `Task` row flips from `in_progress`
   to `failed`. Pure-logic unit test for the reducer + integration
   test for the dispatcher wiring.
5. **`scripts/demo_iter_6.sh` lands** with 30-min wall-clock (bumped
   from iter-5's 20). `make demo` aliases to it; iter-5/4/3/2
   demos stay as regression baselines.
6. **Real-LLM e2e demo reaches `pending_review` → owner approve.**
   Chain runs PM → Architect → Backend → Designer → Frontend →
   QA; QA produces a `pending_review`; `uv run ai-team approve
   <id>` completes the loop; root `Task` flips terminal via the
   iter-3 rollup. Captured in
   `docs/iterations/iter_6_demo_report.md`.
7. **All gates green**: `make lint typecheck sec test
   test-integration smoke-llm`. Diff-cover ≥ 80 % on the iter-6
   diff vs `origin/main`. Ruff format clean.
8. **`docs/iterations/iter_6_retro.md` + `iter_7_handoff.md`**.

## Non-goals (explicitly deferred)

- **In-adapter auto-retry on budget exhaustion.** Tempting (would
  let the agent transparently bump and try again); deferred to
  iter-7+. iter-6 surfaces BLOCKED to the owner; retry is manual
  for now. Reasons: (a) auto-retry doubles spend on a stuck
  agent; (b) we need a per-correlation retry counter to bound
  it, which is more code than the budget bump itself.
- **TL auto-router for `BLOCKED(budget_exhausted)`.** TL's
  existing BLOCKED router parses summary for
  `blocked: requires <role>`. Budget exhaustion doesn't have a
  recipient role to route to; auto-routing it would need a
  different code path. Deferred.
- **HoldQueue persistence to Postgres.** Still iter-7+.
- **`audit_writer` restricted Postgres role.** Still deferred
  from iter-2/3/4/5.
- **Hash-chain alert job.** Still deferred.
- **`GitHubTargetRepo` implementation.** Waiting on first
  commercial product.
- **TL transactional decomposition.** Still deferred.
- **`pytest-rerunfailures` plugin pin.** Iter-5 saw the
  testcontainers race once (30 errors → second run all 30
  passed). Defer pinning until it bites in CI, not just local.
- **`BaseAgent.handle()` template-method refactor.** Iter-5
  per-subclass touch held; defer until a new agent rolls in.
- **Pre-flight MCP health-gate.** Iter-4's direct-python
  invocation is enough; defer until a future demo trips on it.

## Decisions to confirm with owner (defaults below in **bold**)

1. **Per-tier budget values?** Three concrete sets to choose from:
   - (a) Conservative bump: haiku `$0.20`, sonnet `$1.00`, opus
        `$3.00`. Tight but doubles iter-5's caps.
   - (b) **Mid bump (recommended): haiku `$0.30`, sonnet
        `$1.50`, opus `$4.00`.** Triples sonnet; doubles opus.
        Backend's iter-5 run spent $0.50 in 13 turns before
        crashing; a complete implementation realistically wants
        $1.00-$1.50. Opus headroom is for Architect's longer
        sessions (iter-5 demo Architect used $0.72 of the $2.00
        opus cap — comfortable but a real iteration could
        squeeze).
   - (c) Generous: haiku `$0.50`, sonnet `$3.00`, opus `$8.00`.
        Reduces the chance of any budget event in iter-6 demo
        to near-zero; costs more on a runaway loop.

   **Default: (b).** Cost per demo run is bounded (~$3-5
   ceiling), runaway-loop protection stays meaningful, headroom
   for a complete 6-agent chain is realistic.

2. **Budget exhaustion → BLOCKED only, or in-adapter auto-retry?**
   - (a) **BLOCKED only (recommended)**: adapter raises
        `LLMBudgetExhaustedError`; dispatcher synthesises a
        BLOCKED report; owner sees it in the digest and
        manually re-issues with elevated budget if desired.
        Simpler, owner-visible.
   - (b) In-adapter auto-retry: one retry with 2x budget; raise
        only if second attempt also exhausts. Faster path to
        success but doubles worst-case spend.

   **Default: (a).** Iter-6 should be cautious about adding
   auto-recovery loops; the budget bump from decision #1 is
   the primary fix. Auto-retry is iter-7+ work.

3. **Dropped child task status: `failed` or new `dropped` enum?**
   - (a) **`failed` (recommended)**: dropped tasks roll up via
        the existing `derive_parent_status` "any failed →
        root failed" rule.
   - (b) New `DROPPED` enum on `TaskStatus`: semantically
        distinct from a real agent failure. Requires schema
        bump + migration + reducer changes.

   **Default: (a).** A dropped task is failed-by-cascade; the
   distinction isn't load-bearing for the rollup, just for
   forensics. iter-7+ could add the enum if forensics need it.

4. **Demo wall-clock: hard 30 min, or wait-for-pending_review
   with a longer hard cap?**
   - (a) **30 min hard cap (recommended)**: same shape as
        iter-3/4/5, just longer. Predictable demo run time.
   - (b) Adaptive: poll for pending_review with no time cap;
        rely on `make demo` being Ctrl-C-able. Worst-case
        runaway = forever.

   **Default: (a).** Hard cap keeps the demo's wall-time
   predictable; if 30 min isn't enough, iter-7 bumps to 45.

## Plan — six phases

### Phase 0 — Branch + plan commit

`git checkout -b worktree-iter-6 origin/main` (already done).
Commit this plan as `docs(iter-6): plan`. Surface for owner
review **before** any code changes. Phase 1+ starts only after
approval. Cost: $0.

### Phase 1 — Raise per-tier `--max-budget-usd` defaults

**Files:**
- Modify: `core/llm/base.py` (lines 108-112)
- Test: `tests/unit/test_llm_base.py` (new or extend existing)

#### 1A — Failing pin test

```python
# tests/unit/test_llm_base.py — append (or new file)
from core.llm.base import DEFAULT_MAX_BUDGET_USD_PER_TIER


def test_default_budget_per_tier_matches_iter6_values() -> None:
    """Pin the iter-6 budget caps so a future tightening surfaces
    in review with reasoning. See iter_5_demo_report.md Failure 1
    + iter_6.md decision #1."""
    assert DEFAULT_MAX_BUDGET_USD_PER_TIER == {
        "haiku": 0.30,
        "sonnet": 1.50,
        "opus": 4.00,
    }
```

Run: expected FAIL — values are currently `0.10 / 0.50 / 2.00`.

#### 1B — Implement

```python
# core/llm/base.py:108-112 — replace:
DEFAULT_MAX_BUDGET_USD_PER_TIER: dict[ModelTier, float] = {
    "haiku": 0.30,
    "sonnet": 1.50,
    "opus": 4.00,
}
```

Run: test passes.

#### 1C — Commit

`feat(llm): raise per-tier --max-budget-usd defaults`

### Phase 2 — `LLMBudgetExhaustedError` + dispatcher BLOCKED synthesis

The two changes ride together because they're a single contract:
adapter detects budget exhaustion → raises distinct error → dispatcher
synthesises BLOCKED.

**Files:**
- Modify: `core/llm/base.py` (add class)
- Modify: `core/llm/claude_code_headless.py` (detect + raise)
- Modify: `core/dispatcher/dispatcher.py` (catch + synthesise BLOCKED)
- Test: `tests/unit/test_claude_code_headless.py`
- Test: `tests/unit/test_dispatcher.py`
- Test: `tests/integration/test_dispatcher_e2e.py`

#### 2A — Failing unit test: adapter raises distinct error

```python
# tests/unit/test_claude_code_headless.py — append
@pytest.mark.asyncio
async def test_invoke_raises_budget_exhausted_on_error_max_budget_subtype() -> None:
    """When claude -p's stdout JSON carries subtype=error_max_budget_usd
    (the iter-5 demo's Backend signature), the adapter raises the
    distinct LLMBudgetExhaustedError so the dispatcher can route it to
    BLOCKED instead of failed. See iter_6.md Phase 2."""
    client = ClaudeCodeHeadlessClient()

    stdout_payload = json.dumps({
        "type": "result",
        "subtype": "error_max_budget_usd",
        "is_error": True,
        "session_id": "s",
        "total_cost_usd": 0.5,
        "usage": {"input_tokens": 1, "output_tokens": 1},
    }).encode()

    class _FailingProc:
        returncode = 1
        async def communicate(self) -> tuple[bytes, bytes]:
            return stdout_payload, b""

    async def _fake_create(*_cmd: str, **_kwargs: Any) -> _FailingProc:
        return _FailingProc()

    with (
        patch(
            "core.llm.claude_code_headless.asyncio.create_subprocess_exec",
            new=AsyncMock(side_effect=_fake_create),
        ),
        pytest.raises(LLMBudgetExhaustedError),
    ):
        await client.invoke(system_prompt="sp", user_message="u", model="sonnet")
```

Run: expected FAIL — `LLMBudgetExhaustedError` doesn't exist.

#### 2B — Failing unit test: dispatcher synthesises BLOCKED

```python
# tests/unit/test_dispatcher.py — append
def test_synthesise_blocked_report_for_budget_exhausted() -> None:
    """When the dispatcher catches LLMBudgetExhaustedError, it should
    synthesise TASK_REPORT(status=BLOCKED, blocked_on='budget') instead
    of the default FAILED. BLOCKED does NOT cascade-drop dependents."""
    from core.llm.base import LLMBudgetExhaustedError
    incoming = _incoming_assignment(task_id=uuid4())
    exc = LLMBudgetExhaustedError("budget exhausted: $0.50 over cap")
    out = _synthesise_failed_report(
        role=AgentId.BACKEND_DEVELOPER, incoming=incoming, exc=exc
    )
    payload = out.payload
    assert isinstance(payload, TaskReportPayload)
    assert payload.status == TaskStatus.BLOCKED
    assert payload.blocked_on == "budget"
    assert "LLMBudgetExhaustedError" in payload.summary
```

Run: expected FAIL — synth helper always emits FAILED today.

#### 2C — Failing integration test: BLOCKED doesn't drop dependents

```python
# tests/integration/test_dispatcher_e2e.py — append, follows the
# _RaisingBackend pattern from iter-5 Phase 1
class _BudgetExhaustedBackend(BaseAgent):
    role: ClassVar[AgentId] = AgentId.BACKEND_DEVELOPER
    system_prompt_path: ClassVar[Path] = Path("/dev/null")
    def __init__(self) -> None:
        self._cached_prompt: str | None = None
    def system_prompt(self) -> str:
        return "stub"
    async def handle(self, msg: AgentMessage) -> list[AgentMessage]:
        raise LLMBudgetExhaustedError("simulated budget cap")
    def build_outputs(self, response, incoming):
        return []


async def test_budget_exhausted_emits_blocked_does_not_cascade_drop(
    redis_url, session_factory, db_session
):
    """When Backend raises LLMBudgetExhaustedError, the synthesised
    report is BLOCKED (not failed). QA (depends_on=backend) stays held
    rather than getting dropped. Root Task stays in_progress."""
    # ... full setup like test_agent_handle_exception_synthesises_failed_report
    # but with _BudgetExhaustedBackend and a TL response that includes a QA
    # subtask depends_on=[be]. Assert:
    #   - Backend's audit row has status=blocked, blocked_on=budget
    #   - QA's child Task is still in_progress (not failed)
    #   - QA's task_assignment is still held in HoldQueue (not bus-published)
    #   - Root Task stays in_progress (no terminal cascade)
```

Run: expected FAIL.

#### 2D — Implement

```python
# core/llm/base.py — append after LLMInvocationError:
class LLMBudgetExhaustedError(LLMError):
    """Raised when `claude -p` returns subtype=error_max_budget_usd on
    its stdout response JSON. The dispatcher catches this distinctly
    and synthesises TASK_REPORT(status=BLOCKED) so dependents aren't
    cascade-dropped — owner can manually retry with elevated budget."""
```

```python
# core/llm/claude_code_headless.py — replace the non-zero-exit block:
if proc.returncode != 0:
    err = stderr.decode(errors="replace")[:1000]
    out = stdout.decode(errors="replace")[:2000]
    log.error(
        "llm.invoke.failed",
        returncode=proc.returncode,
        stderr=err,
        stdout=out,
    )
    # iter-6: detect budget exhaustion specifically so the dispatcher
    # can route it to BLOCKED instead of FAILED.
    if _is_budget_exhausted_stdout(out):
        raise LLMBudgetExhaustedError(
            f"claude -p budget exhausted: stdout={out!r}"
        )
    raise LLMInvocationError(
        f"claude -p exited {proc.returncode}: stderr={err!r} stdout={out!r}"
    )


def _is_budget_exhausted_stdout(out: str) -> bool:
    """Return True iff out is JSON with subtype=error_max_budget_usd.
    Robust against truncation and non-JSON prefixes."""
    if "error_max_budget_usd" not in out:
        return False
    try:
        parsed = json.loads(out)
    except (json.JSONDecodeError, TypeError):
        return False
    return isinstance(parsed, dict) and parsed.get("subtype") == "error_max_budget_usd"
```

```python
# core/dispatcher/dispatcher.py — extend _synthesise_failed_report:
def _synthesise_failed_report(
    *, role: AgentId, incoming: AgentMessage, exc: BaseException
) -> AgentMessage:
    ...
    # iter-6: route budget-exhaustion to BLOCKED, not FAILED, so the
    # HoldQueue doesn't cascade-drop dependents.
    if isinstance(exc, LLMBudgetExhaustedError):
        status = TaskStatus.BLOCKED
        blocked_on = "budget"
        priority = Priority.P2
    else:
        status = TaskStatus.FAILED
        blocked_on = None
        priority = Priority.P1
    type_name = type(exc).__name__
    first_line = str(exc).splitlines()[0] if str(exc) else ""
    summary = f"{type_name}: {first_line}"[:500]
    ...
    return AgentMessage(
        ...
        payload=TaskReportPayload(
            task_id=task_id,
            status=status,
            progress_pct=0,
            summary=summary,
            blocked_on=blocked_on,
        ),
        ...
        priority=priority,
    )
```

Also: the dispatcher's existing `except Exception as exc:` block
catches all exceptions including `LLMBudgetExhaustedError` (it's a
subclass of `LLMError` which is `Exception`). The synth helper's
isinstance check routes it to BLOCKED. **No changes to the except
block itself**.

Add import of `LLMBudgetExhaustedError` in
`core/dispatcher/dispatcher.py`.

Run: 3 new tests pass; existing dispatcher tests still pass
(critical — Phase 1's `RuntimeError` test still routes to FAILED).

#### 2E — Commit

`feat(llm): distinct LLMBudgetExhaustedError → dispatcher BLOCKED`

### Phase 3 — `TaskStateReducer.on_drop`

**Files:**
- Modify: `core/persistence/task_state.py` (add `on_drop`)
- Modify: `core/dispatcher/dispatcher.py` (call `on_drop` per-dropped)
- Test: `tests/unit/test_task_state.py` (new pure-logic test)
- Test: `tests/integration/test_dispatcher_e2e.py` (extend existing
  three-stage test to assert dropped child tasks flip terminal)

#### 3A — Failing pure-logic unit test

```python
# tests/unit/test_task_state.py — append
def test_on_drop_marks_child_failed_and_rolls_up() -> None:
    """Dropped tasks flip to FAILED so the rollup can include them.
    No new DROPPED status (per iter-6 decision #3). See iter_5_demo_
    report.md Failure 3."""
    reducer = TaskStateReducer(session_factory=...)
    # ... assertions using the existing pattern in test_task_state.py
```

#### 3B — Failing integration: extend three-stage test to assert drop rollup

Make the iter-3 dependency test exercise a failing predecessor so
QA gets dropped, then assert QA's child Task flips to `failed` and
the root rolls up correctly.

#### 3C — Implement

```python
# core/persistence/task_state.py — add method:
async def on_drop(self, task_ids: list[UUID]) -> None:
    """Flip dropped children's status to FAILED. Triggers a parent
    rollup if all siblings are terminal."""
    if not task_ids:
        return
    async with self._session_factory() as session:
        # ... bulk-update child rows; collect parent_task_ids; rollup
```

```python
# core/dispatcher/dispatcher.py — in the existing branch:
elif signed.payload.status == TaskStatus.FAILED:
    dropped = await self._hold_queue.mark_failed(
        signed.correlation_id, signed.payload.task_id
    )
    for d in dropped:
        _log.warning(...)
    # iter-6: mark dropped children's tasks terminal so the rollup
    # accounts for them.
    if self._task_state is not None and dropped:
        await self._task_state.on_drop([
            d.payload.task_id for d in dropped
            if isinstance(d.payload, TaskAssignmentPayload)
        ])
```

Run: both new tests pass; existing rollup tests still pass.

#### 3D — Commit

`feat(persistence): TaskStateReducer.on_drop — terminalise dropped children`

### Phase 4 — Demo wall-clock + `scripts/demo_iter_6.sh`

**Files:**
- Create: `scripts/demo_iter_6.sh` (clone of iter-5 with 30-min cap)
- Modify: `Makefile`

#### 4A — Clone and bump

Fork `scripts/demo_iter_5.sh` verbatim. Differences:
- Header rewritten for iter-6 (budget bump, BLOCKED, on_drop)
- `deadline=$((SECONDS + 1800))` (1800 s = 30 min, was 1200 s)
- Config filename: `.iter6-mcp.json`
- Task title: "iter-6 demo: idea-validator v2 …"

#### 4B — Makefile alias

```makefile
demo: demo-iter-6 ## Alias for the current iteration's demo
demo-iter-6: ## Run iter-6 e2e (raised budgets + BLOCKED on budget exhaustion + on_drop + 30-min wall)
	bash scripts/demo_iter_6.sh
demo-iter-5: ## Run iter-5 e2e — regression baseline
	bash scripts/demo_iter_5.sh
# (demo-iter-4 / iter-3 / iter-2 stay unchanged.)
```

#### 4C — Commit

`chore(demo): demo_iter_6.sh — 30-min wall-clock + iter-6 fixes`

### Phase 5 — Real-LLM e2e demo

Cost budget: ~$2.50 expected (Backend now actually completes;
Frontend completes; QA reports), $5.00 ceiling. Higher than iter-5
because the chain runs all the way.

| # | Task | Output |
|---|------|--------|
| 5A | Pre-flight: `.env`, `docker info`, `claude --version`, `gh auth status`, `make smoke-llm` PASS, `uv run python scripts/measure_mcp_coldstart.py` PASS, quota check | terminal capture |
| 5B | `AI_TEAM_DEMO_NON_INTERACTIVE=1 bash scripts/demo_iter_6.sh` | chain runs PM → Architect → Backend → Designer → Frontend → QA; pending_review row appears |
| 5C | `uv run ai-team list-pending` → capture review row; `uv run ai-team approve <id> --comment "iter-6 demo close-out"` | review approved |
| 5D | Single SQL query → per-agent table with metrics for every row | per-agent table |
| 5E | Write `docs/iterations/iter_6_demo_report.md` | committed report |

**If the chain still breaks** mid-run (e.g., a NEW failure mode
under raised budgets), the report captures it and informs iter-7.
Same posture as iter-3/4/5: don't paper over.

### Phase 6 — Validation gates + retro + iter-7 handoff

| # | Task | Output |
|---|------|--------|
| 6A | `make lint typecheck sec test test-integration smoke-llm` all green | terminal |
| 6B | `uv run ruff format --check .` clean | terminal |
| 6C | Diff-cover ≥ 80 % on iter-6 diff vs `origin/main` | coverage report |
| 6D | `docs/iterations/iter_6_retro.md` — what shipped, what didn't, surprises, stats | committed retro |
| 6E | `docs/iterations/iter_7_handoff.md` — carry-overs, hard constraints, ready-to-paste prompt | committed handoff |
| 6F | Open PR; squash-merge once CI green | merged PR; main at iter-6 squash |

## Risk register

- **Raised budgets push a runaway loop's spend higher.** Worst-case
  pre-iter-6: a stuck Sonnet agent burns $0.50 before failing. Post-
  iter-6: $1.50. Mitigation: per-agent `llm_timeout_s` (already
  600 s for Backend/Frontend/DevOps) caps wall-clock; quota gates
  still apply at 70/90/100%.
- **`error_max_budget_usd` detection is fragile.** If `claude -p`
  changes its error-JSON shape, the adapter falls through to the
  generic `LLMInvocationError` and the chain cascades-drops as
  before. Acceptable: iter-5 stdout-tee still surfaces the actual
  error; iter-7 can re-tune the detector.
- **Multiple agents hit budget concurrently.** Then multiple BLOCKED
  reports land at the owner; current digest renders them
  individually. Owner experience may be noisy in a worst-case but
  not incorrect.
- **`on_drop` rollup races with `on_report`.** Both can fire on the
  same task. Mitigation: `on_drop` is idempotent (FAILED status
  doesn't change once set); the rollup `derive_parent_status`
  already handles terminal statuses non-repeatable.
- **30-min wall is still not enough.** Then iter-7 bumps to 45.
- **Diff-cover dips below 80 %.** Phase 2's new `LLMBudgetExhaustedError`
  + adapter branch is small; should be covered by the new tests.
  If we dip, add a test for `_is_budget_exhausted_stdout` truncation
  edge cases.

## Cost projection

| Phase | Type | Estimate |
|-------|------|----------|
| 0     | docs | $0 |
| 1     | code + 1 unit test | $0 |
| 2     | code + 3 tests | $0 |
| 3     | code + 2 tests | $0 |
| 4     | shell + Makefile | $0 |
| 5     | real-LLM demo | ~$2.50 expected, $5.00 ceiling |
| 6     | docs + CI | $0 |
| **Total** | | **~$2.50 expected, $5.00 ceiling** |

Quota check before Phase 5. The $5.00 ceiling is the iter-6 upper
bound under raised budgets; if quota is tight, defer Phase 5 to
the next window.

## Workflow

- Plan-before-code: this file lands as commit 1; no Phase-1+ code
  until owner approves the plan.
- Conventional commits; squash-merge on the iter-6 PR.
- Each phase's "Commit" row in tables above is one (and only one)
  commit.
- Run `make lint typecheck sec test` **and** `uv run ruff format
  --check .` after each phase to keep the branch shippable.
- Final demo report goes in the same PR.

## Ready-to-paste prompt for iter-7

Lives in `docs/iterations/iter_7_handoff.md` (Phase 6E).
