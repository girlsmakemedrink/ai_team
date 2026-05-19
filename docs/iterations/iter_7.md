# Iteration 7 — Plan

- **Status**: Draft (awaiting owner approval)
- **Plan author**: Claude (Opus 4.7)
- **Date drafted**: 2026-05-19
- **Base commit**: `c920eb8` on `main` (iter-6 squash)
- **Branch**: `worktree-iter-7` (cut from `origin/main` at plan commit)
- **Anchors (do not contradict)**: ADR-001 (orchestrator), ADR-006
  (model tier per agent), ADR-008 (LLM access), ADR-009
  (TARGET_REPO abstraction), iter-6 retro + demo report
- **Carry-overs addressed**: items 1–5 of
  `docs/iterations/iter_7_handoff.md` — raise Architect's
  per-call `llm_timeout_s`, capture stdout on
  `LLMTimeoutError`, cascade drops through HoldQueue in `on_drop`,
  dedicated reducer integration tests, and the re-run that
  finally closes the `pending_review` → owner approve loop
  iter-3/4/5/6 all reached for.
- **Deferred unchanged** (carry-over items 6–14 from iter-7
  handoff): HoldQueue persistence, `audit_writer` Postgres role,
  hash-chain alert, `GitHubTargetRepo`, TL transactional
  decomposition, `pytest-rerunfailures` pin, `BaseAgent`
  template-method refactor, pre-flight MCP health-gate,
  `llm_timeout_s` as `ClassVar` default on `BaseAgent`.

## Goal — one sentence

Close the iter-6 demo's `LLMTimeoutError` failure mode (Architect
timed out at 300 s on the v2 ADR + system-design draft) and the
transitive-drop gap (`on_drop` doesn't cascade through HoldQueue,
leaving `fe` + `qa` stuck `in_progress` when `design` was
dropped), then re-run end-to-end through `pending_review` → owner
approve — the loop iter-3/4/5/6 all reached for.

## Success criteria (binary, measurable)

1. **Architect's per-call `llm_timeout_s` raised to 600 s.**
   New `ClassVar[int] = 600` override in
   `agents/architect/agent.py` matching Backend / Frontend /
   DevOps (which already have 600 s). Unit test pins the value
   so a future "tighten" surfaces in review.
2. **`LLMTimeoutError` carries the in-flight stdout.** Mirrors
   iter-5 Phase 4 for the non-zero-exit path. When `claude -p`
   times out, the adapter kills the process, drains any
   buffered stdout (best-effort), and raises
   `LLMTimeoutError(f"claude -p timed out after {timeout_s}s;
   stdout={out!r}")`. Empty stdout when nothing buffered is
   acceptable. Unit test pins the shape.
3. **`on_drop` cascades through HoldQueue.** Dispatcher's
   FAILED-cascade branch becomes a queue-driven loop: every
   `task_id` returned by `HoldQueue.mark_failed` is itself
   pushed back into the loop as a new trigger, so transitive
   dependents (fe → qa) get dropped in the same pass. The
   reducer's `on_drop` is called once per batch and is idempotent
   on terminal rows. Integration test pins the three-level
   cascade: `arch FAILED → {be, design} dropped → fe (via
   design) dropped → qa (via fe + be) dropped → all four child
   Tasks flip to failed → root rolls up to failed`.
4. **`tests/integration/test_task_state_reducer.py` lands** with
   four edge-case tests: (a) `on_drop([missing_uuid])` is a no-op
   that logs `task_state.drop_no_matching_child`; (b)
   `on_drop([already_failed_id])` is a no-op that logs
   `task_state.drop_skipped_already_terminal`; (c) parent rollup
   handles a parent whose status already matches the derived
   status (no double-write); (d) parent rollup logs
   `task_state.parent_missing_on_drop` when `parent_task_id` is
   set but the parent row doesn't exist. Lifts iter-6's 68.8 %
   reducer diff-cover to >90 %.
5. **`scripts/demo_iter_7.sh` lands.** Clone of `demo_iter_6.sh`
   with iter-7 header (Architect timeout 600 s + cascading drops
   + LLMTimeoutError stdout). Same 30-min wall-clock; same
   v2-shaped task. `make demo` aliases to `demo-iter-7`;
   iter-6/5/4/3/2 demos stay as regression baselines.
6. **Real-LLM e2e demo reaches `pending_review` → owner approve.**
   Chain runs PM → Architect → Backend → Designer → Frontend →
   QA; QA produces a `pending_review`; `uv run ai-team approve
   <id>` completes the loop; root `Task` flips terminal via the
   iter-3 rollup. Captured in
   `docs/iterations/iter_7_demo_report.md`.
7. **All gates green**: `make lint typecheck sec test
   test-integration smoke-llm`. Diff-cover ≥ 80 % on the iter-7
   diff vs `origin/main`. Ruff format clean.
8. **`docs/iterations/iter_7_retro.md` + `iter_8_handoff.md`**.

## Non-goals (explicitly deferred)

- **In-adapter auto-retry on budget exhaustion.** Same posture
  as iter-6 non-goal #1. iter-7 still surfaces BLOCKED to the
  owner.
- **TL auto-router for `BLOCKED(budget_exhausted)`.** Same
  posture as iter-6.
- **HoldQueue persistence to Postgres.** Still iter-8+.
- **`audit_writer` restricted Postgres role.** Still deferred
  from iter-2/3/4/5/6.
- **Hash-chain alert job.** Still deferred.
- **`GitHubTargetRepo` implementation.** Waiting on first
  commercial product.
- **TL transactional decomposition.** Still deferred.
- **`pytest-rerunfailures` plugin pin.** iter-6 saw the
  testcontainers race once; one retry passed. Defer pinning
  until it bites in CI, not just local.
- **`BaseAgent.handle()` template-method refactor.** Defer until
  the next agent rolls in.
- **Pre-flight MCP health-gate.** Iter-4's direct-python is
  enough; defer until a future demo trips on it.
- **`BaseAgent.llm_timeout_s` default bump from 300 → 600.**
  Three subclasses have already overridden (Backend, Frontend,
  DevOps); iter-7 adds Architect. If a fifth needs 600 s,
  iter-8 should bump the base default and remove the per-
  subclass overrides. Until then, the explicit per-subclass
  values document the intent.

## Decisions to confirm with owner (defaults below in **bold**)

1. **Architect timeout value?**
   - (a) **600 s (recommended)**: matches Backend / Frontend /
        DevOps. iter-6 demo's Architect timed out at 300 s;
        iter-5 demo's Architect finished in 154 s. 600 s gives
        2-4× headroom while still bounding worst-case wall-clock.
   - (b) 900 s: bigger margin, but `claude -p` rarely needs >5
        min on Opus. Risk: 30-min demo wall + 900 s timeouts
        could pile up.

   **Default: (a).**

2. **`LLMTimeoutError` stdout capture mechanism?**
   - (a) **Best-effort drain after kill (recommended)**: after
        `proc.kill()`, call `await proc.communicate()` (or read
        from the pipe directly) to grab whatever buffered. May
        return empty when the process hadn't flushed yet —
        acceptable. Simple, no new failure modes.
   - (b) Stream stdout to a temp file via a wrapper, then read
        the file after kill. More robust but adds a file
        lifecycle to manage.

   **Default: (a).** If empty stdout becomes a pain in iter-8+,
   reach for (b).

3. **Cascade-drop mechanism in dispatcher?**
   - (a) **Queue-driven loop in dispatcher (recommended)**:
        every `task_id` returned by `HoldQueue.mark_failed`
        becomes a new trigger; loop until no more drops. Calls
        `task_state.on_drop` once per inner iteration. Cycle-
        safe because already-terminal rows are skipped by the
        reducer's existing guard.
   - (b) Synthesise a derived `TASK_REPORT(failed)` for each
        dropped task and re-enter the dispatcher's outbound
        pipeline. Cleaner audit semantics (every terminal row
        has an audit row) but emits N synthetic reports for an
        N-level cascade, which can spam the feed.

   **Default: (a).** Option (b) is iter-8+ if forensics need
   the derived audit rows.

4. **New reducer test file location?**
   - (a) **`tests/integration/test_task_state_reducer.py`
        (recommended)**: matches the existing
        `tests/integration/test_dispatcher_e2e.py` pattern.
        Dedicated file for reducer-direct tests.
   - (b) Extend `tests/integration/test_dispatcher_e2e.py`
        with reducer-direct tests. Co-locates reducer + dispatcher
        e2e, but blurs the dispatcher-vs-reducer concern.

   **Default: (a).**

## Plan — seven phases

### Phase 0 — Branch + plan commit

`git checkout -b worktree-iter-7 origin/main` (already done).
Commit this plan as `docs(iter-7): plan`. Surface for owner
review **before** any code changes. Phase 1+ starts only after
approval. Cost: $0.

### Phase 1 — Architect `llm_timeout_s` = 600 s

**Files:**
- Modify: `agents/architect/agent.py` (add ClassVar override)
- Test: `tests/unit/test_architect_agent.py` (new test or extend
  existing)

#### 1A — Failing pin test

```python
# tests/unit/test_architect_agent.py — append (or new file)
def test_llm_timeout_s_is_600_for_architect() -> None:
    """Architect's per-call timeout must be 600 s (matches Backend /
    Frontend / DevOps) so the v2 ADR + system-design draft has
    headroom. iter-6 demo timed out at 300 s. See
    docs/iterations/iter_6_demo_report.md Failure 1 + iter_7.md
    decision #1."""
    from agents.architect import ArchitectAgent
    assert ArchitectAgent.llm_timeout_s == 600
```

Run: expected FAIL — Architect currently inherits `BaseAgent`'s
300 s.

#### 1B — Implement

```python
# agents/architect/agent.py — add ClassVar near other ClassVars
# (around line 65, next to allowed_tools / model_tier):
    llm_timeout_s: ClassVar[int] = 600
```

Run: test passes.

#### 1C — Commit

`feat(architect): raise llm_timeout_s to 600s`

### Phase 2 — `LLMTimeoutError` captures stdout

**Files:**
- Modify: `core/llm/claude_code_headless.py` (drain stdout in
  timeout branch + structlog + raise)
- Test: `tests/unit/test_claude_code_headless.py` (new test)

#### 2A — Failing unit test

```python
# tests/unit/test_claude_code_headless.py — append
@pytest.mark.asyncio
async def test_invoke_timeout_includes_buffered_stdout() -> None:
    """When `claude -p` times out mid-call, the adapter must drain
    whatever buffered stdout is available and include it in the
    raised LLMTimeoutError. iter-6 demo's Architect timeout produced
    a bare "claude -p timed out after 300s" with no diagnostic data;
    iter-5 Phase 4 closed the same gap for the non-zero-exit path.
    See iter_6_demo_report.md Failure 1 + iter_7.md Phase 2."""
    client = ClaudeCodeHeadlessClient()

    class _HangingProc:
        returncode = None  # still running
        async def communicate(self) -> tuple[bytes, bytes]:
            # First call (with timeout) raises TimeoutError; second
            # call (after kill, drain) returns buffered bytes.
            if not getattr(self, "_killed", False):
                raise TimeoutError("communicate timed out")
            return b"partial buffered stdout from claude", b""

        def kill(self) -> None:
            self._killed = True

        async def wait(self) -> None:
            return None

    async def _fake_create(*_cmd: str, **_kwargs: Any) -> _HangingProc:
        return _HangingProc()

    with (
        patch(
            "core.llm.claude_code_headless.asyncio.create_subprocess_exec",
            new=AsyncMock(side_effect=_fake_create),
        ),
        patch(
            "core.llm.claude_code_headless.asyncio.wait_for",
            new=AsyncMock(side_effect=TimeoutError()),
        ),
        pytest.raises(LLMTimeoutError, match="partial buffered stdout"),
    ):
        await client.invoke(
            system_prompt="sp",
            user_message="u",
            model="haiku",
            timeout_s=1,
        )
```

Run: expected FAIL — current adapter raises bare
`LLMTimeoutError(f"claude -p timed out after {timeout_s}s")`.

#### 2B — Implement

```python
# core/llm/claude_code_headless.py — replace the existing timeout
# branch:
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=timeout_s
            )
        except TimeoutError as e:
            proc.kill()
            await proc.wait()
            # iter-7: drain any buffered stdout after the kill so
            # the raised exception carries diagnostic data. iter-6
            # demo's Architect timeout was a diagnostic dead-end;
            # mirrors iter-5 Phase 4 for the non-zero-exit path.
            buffered_out = ""
            try:
                drained_out, _ = await proc.communicate()
                buffered_out = drained_out.decode(errors="replace")[:2000]
            except Exception:  # noqa: BLE001
                # Drain failure is non-fatal — fall back to bare
                # timeout message.
                pass
            log.error(
                "llm.invoke.timeout",
                timeout_s=timeout_s,
                buffered_stdout=buffered_out,
            )
            raise LLMTimeoutError(
                f"claude -p timed out after {timeout_s}s; "
                f"stdout={buffered_out!r}"
            ) from e
```

Run: test passes.

#### 2C — Commit

`feat(llm): capture buffered stdout in LLMTimeoutError`

### Phase 3 — Cascade drops through HoldQueue

**Files:**
- Modify: `core/dispatcher/dispatcher.py` (queue-driven loop in
  the FAILED branch)
- Test: `tests/integration/test_dispatcher_e2e.py` (extend
  existing iter-6 on_drop test or add new three-level test)

#### 3A — Failing integration test

Add a new test that exercises a three-level cascade. The existing
iter-6 test `test_dropped_dependent_child_task_flips_to_failed`
uses a 2-stage DAG (arch → be). The new test needs arch → design →
fe to expose the cascade gap.

```python
# tests/integration/test_dispatcher_e2e.py — append
def _tl_three_level_cascade_response() -> LLMResponse:
    """TL emits arch (no deps) → design (depends_on=arch) →
    fe (depends_on=design). When arch fails, iter-7's cascade must
    drop design AND fe (transitive)."""
    return LLMResponse(
        text="",
        structured={
            "summary": "Three-level cascade test.",
            "subtasks": [
                {"id": "arch", "recipient": "architect",
                 "title": "Design", "description": "ADR.",
                 "priority": "P2", "depends_on": []},
                {"id": "design", "recipient": "designer",
                 "title": "UX brief", "description": "Wireframes.",
                 "priority": "P2", "depends_on": ["arch"]},
                {"id": "fe", "recipient": "frontend_developer",
                 "title": "Landing page",
                 "description": "Impl per design.",
                 "priority": "P3", "depends_on": ["design"]},
            ],
        },
        tools_used=[],
        session_id="tl-iter7-cascade",
        tokens=TokensUsage(input=10, output=20, model="claude-opus-4-7"),
        cost_estimate_cents=0, duration_ms=100, raw={},
    )


# Reuse _RaisingArchitect and the _StaticDoneAgent variants from
# iter-6 tests. Add a Designer + Frontend stub if not already present.
class _StubDesigner(_StaticDoneAgentBase):
    role: ClassVar[AgentId] = AgentId.DESIGNER

class _StubFrontend(_StaticDoneAgentBase):
    role: ClassVar[AgentId] = AgentId.FRONTEND_DEVELOPER


async def test_transitive_drops_cascade_through_hold_queue(
    redis_url, session_factory, db_session
):
    """Three-level cascade: arch FAILED → design dropped →
    fe dropped (transitive, via the dropped design predecessor).
    All three child Task rows must flip to failed; root rolls up
    to failed. Closes iter-6 demo Failure 2.
    See iter_7.md Phase 3."""
    # ... setup mirrors test_dropped_dependent_child_task_flips_to_failed
    # but with three stub agents and the three-level DAG.
    # Assert:
    #   - design's Task row flips to failed via on_drop (direct dependent)
    #   - fe's Task row flips to failed via on_drop (transitive)
    #   - HoldQueue is empty at end (no leaks)
    #   - root rolls up to failed
```

Run: expected FAIL — fe stays `in_progress` because today's
dispatcher only handles direct drops.

#### 3B — Implement

```python
# core/dispatcher/dispatcher.py — replace the existing FAILED branch
# (lines ~178-202):
                    elif signed.payload.status == TaskStatus.FAILED:
                        # iter-7: drive the cascade with a queue.
                        # Every dropped task_id becomes a new trigger
                        # for HoldQueue.mark_failed, so transitive
                        # dependents (e.g. fe in arch→design→fe) get
                        # dropped in the same pass. Idempotent —
                        # already-terminal Task rows are skipped by
                        # the reducer's on_drop guard.
                        to_drop_triggers: list[UUID] = [
                            signed.payload.task_id
                        ]
                        while to_drop_triggers:
                            trigger_id = to_drop_triggers.pop(0)
                            dropped = await self._hold_queue.mark_failed(
                                signed.correlation_id, trigger_id
                            )
                            if not dropped:
                                continue
                            for d in dropped:
                                _log.warning(
                                    "dispatcher.dependent_dropped_after_failure",
                                    correlation_id=str(d.correlation_id),
                                    message_id=str(d.message_id),
                                    failed_task_id=str(trigger_id),
                                )
                            dropped_task_ids = [
                                d.payload.task_id
                                for d in dropped
                                if isinstance(d.payload, TaskAssignmentPayload)
                            ]
                            if self._task_state is not None and dropped_task_ids:
                                await self._task_state.on_drop(dropped_task_ids)
                            # Each dropped task_id is now itself a
                            # failure trigger for further dependents.
                            to_drop_triggers.extend(dropped_task_ids)
```

Run: test passes. Run iter-6's existing
`test_dropped_dependent_child_task_flips_to_failed` (two-level
cascade) to confirm no regression.

#### 3C — Commit

`feat(dispatcher): cascade drops through HoldQueue (transitive)`

### Phase 4 — `tests/integration/test_task_state_reducer.py`

**Files:**
- Create: `tests/integration/test_task_state_reducer.py`

#### 4A — File scaffold + four edge-case tests

```python
# tests/integration/test_task_state_reducer.py — new file
"""Direct integration tests for TaskStateReducer.on_drop edge cases.

The happy path (drop terminalises child + rolls up parent) is
covered by tests/integration/test_dispatcher_e2e.py's
test_dropped_dependent_child_task_flips_to_failed (iter-6) and
test_transitive_drops_cascade_through_hold_queue (iter-7). This
file pins the protective guards the dispatcher never hits in
practice but on_drop is responsible for.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import uuid4

import pytest

from core.messaging.schemas import AgentId, Priority
from core.persistence.models import Task
from core.persistence.task_state import TaskStateReducer

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = pytest.mark.integration


async def test_on_drop_no_op_when_task_id_missing(
    session_factory: async_sessionmaker[AsyncSession],
    db_session: AsyncSession,
) -> None:
    """on_drop with a task_id that doesn't exist in the tasks table
    is a no-op (logs `task_state.drop_no_matching_child` and moves
    on). Common in production when the dispatcher's hold-queue
    state outlives a row's deletion."""
    _ = db_session
    reducer = TaskStateReducer(session_factory)
    nonexistent = uuid4()
    await reducer.on_drop([nonexistent])  # must not raise


async def test_on_drop_skipped_when_child_already_terminal(
    session_factory: async_sessionmaker[AsyncSession],
    db_session: AsyncSession,
) -> None:
    """on_drop on a task_id whose row is already terminal must not
    re-flip it (idempotent + protects against late drops racing
    with an earlier `on_report` that beat them)."""
    _ = db_session
    child_id = uuid4()
    async with session_factory() as session:
        session.add(Task(
            id=child_id, correlation_id=uuid4(),
            title="t", description="d", status="failed",
            assigned_agent="backend_developer",
            priority=Priority.P2.value,
        ))
        await session.commit()
    reducer = TaskStateReducer(session_factory)
    await reducer.on_drop([child_id])
    async with session_factory() as session:
        row = (await session.execute(select(Task).where(Task.id == child_id))).scalar_one()
    assert row.status == "failed"  # unchanged


async def test_on_drop_parent_rollup_no_op_when_parent_status_unchanged(
    session_factory: async_sessionmaker[AsyncSession],
    db_session: AsyncSession,
) -> None:
    """When the parent's existing status already equals the derived
    status (parent already failed), the rollup must short-circuit
    without a redundant write."""
    _ = db_session
    parent_id = uuid4()
    child_id = uuid4()
    async with session_factory() as session:
        session.add(Task(
            id=parent_id, correlation_id=uuid4(),
            title="root", description="r", status="failed",
            assigned_agent="team_lead", priority=Priority.P2.value,
        ))
        session.add(Task(
            id=child_id, correlation_id=uuid4(),
            title="c", description="d", status="in_progress",
            assigned_agent="backend_developer",
            priority=Priority.P2.value, parent_task_id=parent_id,
        ))
        await session.commit()
    reducer = TaskStateReducer(session_factory)
    await reducer.on_drop([child_id])
    # Parent stayed failed (no exception, no regression to a
    # different status).
    async with session_factory() as session:
        parent = (await session.execute(
            select(Task).where(Task.id == parent_id)
        )).scalar_one()
    assert parent.status == "failed"


async def test_on_drop_parent_rollup_handles_missing_parent_row(
    session_factory: async_sessionmaker[AsyncSession],
    db_session: AsyncSession,
) -> None:
    """When a child's parent_task_id points to a row that no longer
    exists (rare — deletion race), on_drop logs
    `task_state.parent_missing_on_drop` and moves on without
    raising."""
    _ = db_session
    nonexistent_parent = uuid4()
    child_id = uuid4()
    async with session_factory() as session:
        session.add(Task(
            id=child_id, correlation_id=uuid4(),
            title="c", description="d", status="in_progress",
            assigned_agent="backend_developer",
            priority=Priority.P2.value,
            parent_task_id=nonexistent_parent,
        ))
        await session.commit()
    reducer = TaskStateReducer(session_factory)
    await reducer.on_drop([child_id])  # must not raise
    async with session_factory() as session:
        row = (await session.execute(
            select(Task).where(Task.id == child_id)
        )).scalar_one()
    assert row.status == "failed"  # child was terminalised
```

Plus the `from sqlalchemy import select` import at the top.

Run: all four pass. Confirm diff-cover on
`core/persistence/task_state.py` is now >90 %.

#### 4B — Commit

`test(persistence): on_drop edge-case integration tests`

### Phase 5 — Demo wall + `scripts/demo_iter_7.sh`

**Files:**
- Create: `scripts/demo_iter_7.sh` (clone of iter-6 with iter-7
  header)
- Modify: `Makefile`

#### 5A — Clone and bump

Fork `scripts/demo_iter_6.sh` verbatim. Differences:
- Header rewritten for iter-7 (Architect timeout 600 s, cascade
  drops, LLMTimeoutError stdout, reducer edge-case tests)
- Same `deadline=$((SECONDS + 1800))` (30 min)
- Config filename: `.iter7-mcp.json`
- Task title: "iter-7 demo: idea-validator v2 …"

#### 5B — Makefile alias

```makefile
demo: demo-iter-7 ## Alias for the current iteration's demo
demo-iter-7: ## Run iter-7 e2e (Architect 600s + cascade drops + LLMTimeoutError stdout + reducer edges)
	bash scripts/demo_iter_7.sh
demo-iter-6: ## Run iter-6 e2e — regression baseline
	bash scripts/demo_iter_6.sh
# (iter-5 / iter-4 / iter-3 / iter-2 unchanged.)
```

Also add `demo-iter-7` to the `.PHONY` list.

#### 5C — Commit

`chore(demo): demo_iter_7.sh — iter-7 fixes header`

### Phase 6 — Real-LLM e2e demo

Cost budget: ~$2.50 expected (Backend now actually completes —
previously dropped on Architect timeout), $5.00 ceiling. Higher
than iter-6 because the chain runs all the way.

| # | Task | Output |
|---|------|--------|
| 6A | Pre-flight: `.env`, `docker info`, `claude --version`, `gh auth status`, `make smoke-llm` PASS, quota check | terminal capture |
| 6B | `AI_TEAM_DEMO_NON_INTERACTIVE=1 bash scripts/demo_iter_7.sh` | chain runs PM → Architect → Backend → Designer → Frontend → QA; pending_review row appears |
| 6C | `uv run ai-team list-pending` → capture review row; `uv run ai-team approve <id> --comment "iter-7 demo close-out"` | review approved |
| 6D | Single SQL query → per-agent table with metrics for every row | per-agent table |
| 6E | Write `docs/iterations/iter_7_demo_report.md` | committed report |

**If the chain still breaks** mid-run (a NEW failure mode under
the iter-7 fixes), the report captures it and informs iter-8.
Same posture as iter-3/4/5/6: don't paper over.

### Phase 7 — Validation gates + retro + iter-8 handoff

| # | Task | Output |
|---|------|--------|
| 7A | `make lint typecheck sec test test-integration smoke-llm` all green | terminal |
| 7B | `uv run ruff format --check .` clean | terminal |
| 7C | Diff-cover ≥ 80 % on iter-7 diff vs `origin/main` | coverage report |
| 7D | `docs/iterations/iter_7_retro.md` — what shipped, what didn't, surprises, stats | committed retro |
| 7E | `docs/iterations/iter_8_handoff.md` — carry-overs, hard constraints, ready-to-paste prompt | committed handoff |
| 7F | Open PR; squash-merge once CI green via `gh api -X PUT .../merge -f merge_method=squash` (worktree can't `gh pr merge`) | merged PR; main at iter-7 squash |

## Risk register

- **Architect 600 s lets a stuck Opus loop burn more quota.**
  Worst-case pre-iter-7: 300 s × Opus pricing ≈ $0.30/run.
  Post-iter-7: 600 s × Opus ≈ $0.60/run. Acceptable given the
  $4.00 budget cap; if a runaway loop hits both 600 s + $4
  before the chain notices, we have a separate iter-8 problem.
- **Best-effort stdout drain returns empty when the process
  hadn't flushed.** Then the iter-7 `LLMTimeoutError` carries
  the same bare message as iter-6 — no regression, just no
  improvement for that specific race. Mitigation: structlog
  also records `buffered_stdout=""` so the field is at least
  visible in logs even when empty.
- **Cascade loop iterates forever on a malformed HoldQueue
  state.** Mitigation: each iteration either drains messages
  out of `_held` or returns empty `dropped` and exits. HoldQueue
  state is bounded by `_held` size, which only shrinks under
  `mark_failed`. No fixpoint cycle risk.
- **Reducer edge-case tests duplicate parts of the dispatcher
  e2e test.** Acceptable: dispatcher e2e covers the
  reducer-via-dispatcher path; reducer-direct tests cover the
  guards the dispatcher never hits in practice. Different
  inputs, different assertions.
- **Demo wall-clock 30 min still not enough if a full chain
  with Backend + Frontend + QA exceeds it.** Then iter-8 bumps
  to 45 min.
- **Diff-cover dips below 80 %.** Phase 2's exception-handling
  branch in the timeout path may be hard to cover at unit level
  (the `except Exception` swallow on drain failure). If we dip,
  add a test that forces `proc.communicate()` to raise after
  kill.

## Cost projection

| Phase | Type | Estimate |
|-------|------|----------|
| 0     | docs | $0 |
| 1     | code + 1 unit test | $0 |
| 2     | code + 1 unit test | $0 |
| 3     | code + 1 integration test | $0 |
| 4     | 4 integration tests | $0 |
| 5     | shell + Makefile | $0 |
| 6     | real-LLM demo | ~$2.50 expected, $5.00 ceiling |
| 7     | docs + CI | $0 |
| **Total** | | **~$2.50 expected, $5.00 ceiling** |

Quota check before Phase 6. The $5.00 ceiling is the iter-7
upper bound under raised budgets + Architect's longer timeout;
if quota is tight, defer Phase 6 to the next window.

## Workflow

- Plan-before-code: this file lands as commit 1; no Phase-1+
  code until owner approves the plan.
- Conventional commits; squash-merge on the iter-7 PR.
- Each phase's "Commit" row in tables above is one (and only
  one) commit.
- Run `make lint typecheck sec test` **and** `uv run ruff format
  --check .` after each phase to keep the branch shippable.
- Final demo report goes in the same PR.

## Ready-to-paste prompt for iter-8

Lives in `docs/iterations/iter_8_handoff.md` (Phase 7E).
