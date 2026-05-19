# Iteration 5 — Plan

- **Status**: Draft (awaiting owner approval)
- **Plan author**: Claude (Opus 4.7)
- **Date drafted**: 2026-05-19
- **Base commit**: `c3ef49a` on `main` (iter-4 squash)
- **Branch**: `worktree-iter-5` (cut from `origin/main` at plan commit)
- **Anchors (do not contradict)**: ADR-001 (orchestrator), ADR-004
  (per-agent tool allowlist), ADR-008 (LLM access), iter-4 retro +
  demo report
- **Carry-overs addressed**: items 1–5 of
  `docs/iterations/iter_5_handoff.md` — dispatcher exception →
  failed report, `claude -p` permissions policy, per-agent
  `_stamp_metrics` parity, stderr-tee in headless adapter, and
  the re-run demo that finally closes the `pending_review` loop.
- **Deferred unchanged** (carry-over items 6–11 from iter-5 handoff):
  HoldQueue persistence, `audit_writer` Postgres role, hash-chain
  alert job, `GitHubTargetRepo`, TL transactional decomposition,
  `pytest-rerunfailures` pin.

## Goal — one sentence

Make every "agent crashed mid-turn" or "Frontend hit a permissions
gate" failure surface as a terminal `TASK_REPORT(failed)` the
HoldQueue understands, so the iter-4 demo's stalled chain can't
recur — then re-run the demo end-to-end through `pending_review` →
owner approve, the loop iter-3 and iter-4 both reached for.

## Success criteria (binary, measurable)

1. **Agent `handle()` exception → synthetic `TASK_REPORT(failed)`.**
   When `agent.handle(msg)` raises any `Exception`, the dispatcher
   constructs a `TASK_REPORT(status=failed, summary=str(exc)[:1000])`
   from the failing agent, routes it through the same outbound
   pipeline as a real agent output (audit + feed + task-state +
   bus + `HoldQueue.mark_failed`), and the root task rolls up to
   `failed` per the iter-3 `derive_parent_status` rule. Pinned by
   integration test: a stub agent whose `handle()` raises causes
   the root task to flip terminal within 10 s.
2. **`claude -p` agent invocations use `--permission-mode
   acceptEdits`.** Headless adapter passes the flag by default for
   agent calls; gated by a single class-level toggle for tests that
   want the legacy interactive mode. Pinned by unit test asserting
   the flag is present in the constructed argv.
3. **Every agent that overrides `handle()` stamps
   `metadata["llm"]`.** Each subclass (`ProductManagerAgent`,
   `ArchitectAgent`, `BackendDeveloperAgent`, `DesignerAgent`,
   `FrontendDeveloperAgent`, `QaEngineerAgent`, `DevopsAgent`,
   `SreSupportAgent`, `MarketResearcherAgent`) wraps its
   `build_outputs(...)` call in `self._stamp_metrics(...)`. Pinned
   by a parametrised unit test that iterates every agent class
   and asserts non-empty `metadata["llm"]` on every output.
4. **Headless adapter logs stdout on non-zero exit.** Today only
   stderr is logged when `claude -p exited 1`; iter-4 demo's
   Backend hit a case where stderr was empty but stdout carried
   the actual error. Adapter now `log.error("llm.invoke.failed",
   returncode=…, stderr=…, stdout=…)` with stdout truncated to
   2 KB. Pinned by unit test using a scripted subprocess that
   writes to stdout and exits 1.
5. **Real-LLM e2e demo reaches `pending_review` → owner approve.**
   `scripts/demo_iter_5.sh` (clone of iter-4 demo) runs to
   completion: per-message SQL table includes rows for every
   recipient (PM, Architect, Backend, Designer, Frontend, QA);
   QA produces a `pending_review`; `uv run ai-team approve <id>`
   completes the loop; the root `Task` flips from `in_progress`
   to `done` (or `failed` with all child statuses captured) via
   the iter-3 rollup. Captured in
   `docs/iterations/iter_5_demo_report.md`.
6. **All gates green**: `make lint typecheck sec test
   test-integration smoke-llm`. Diff-cover ≥ 80 % on the iter-5
   diff vs `origin/main`. Ruff format clean (the iter-4 CI miss
   that re-ran the workflow).
7. **`docs/iterations/iter_5_retro.md` + `iter_6_handoff.md`**.

## Non-goals (explicitly deferred)

- **HoldQueue persistence to Postgres.** Still iter-6+. The
  iter-4 retro's call still stands: defer until a real outage hits
  or a second dispatcher process appears.
- **`audit_writer` restricted Postgres role enforcement.** Still
  deferred from iter-2/3/4.
- **Hash-chain alert job.** Still deferred.
- **`GitHubTargetRepo` implementation.** Waiting on first
  commercial product (ADR-009).
- **TL decomposition transactional insert.** A TL crash mid-batch
  still leaves orphan child rows; iter-6+ once we add a second
  dispatcher process.
- **`pytest-rerunfailures` plugin pin.** Hasn't reproduced
  meaningfully in iter-3 or iter-4; defer.
- **MCP long-lived transport** (Unix sockets / SSE). Iter-4's
  direct-python invocation is enough; iter-6+ if cold-start
  re-surfaces under concurrent load.
- **Refactoring `BaseAgent.handle()` to a template method.**
  Tempting (would prevent the iter-3 metric-stamping regression
  from recurring), but each subclass already does its own
  schema / session / tool-list wiring inside `handle()`. The
  one-line `self._stamp_metrics(...)` fix per subclass keeps the
  blast radius small and the diff reviewable.

## Decisions to confirm with owner (defaults below in **bold**)

1. **Permission mode: `acceptEdits` vs `bypassPermissions` vs
   "prefer MCP write_file_in_scope"?**
   - (a) `acceptEdits` — auto-accept file edits and tool uses but
        still gates dangerous shell commands. The smallest blast
        radius.
   - (b) `bypassPermissions` (alias of `--dangerously-skip-permissions`)
        — agents can do anything. Maximum throughput; minimum
        defense-in-depth.
   - (c) Leave permissions at default and rewrite agent prompts
        to prefer MCP `write_file_in_scope` over Claude's `Write`
        tool. The MCP server already enforces `AI_TEAM_PATH_PREFIXES`
        scope, so the inner `claude -p`'s interactive gate is
        bypassed by routing through our own server.

   **Default: (a) `acceptEdits`.** Defense in depth matters more
   than throughput; this is the smallest change that closes
   iter-4's Failure 2. (c) would also work but requires touching
   every agent prompt, which is more diff to land iter-5. We can
   layer (c) in iter-6+ as a hardening pass.

2. **Per-agent `_stamp_metrics`: one-line touch per subclass OR
   refactor `BaseAgent.handle()` to template method?**
   - (a) Touch each of the 9 subclasses' `handle()` to wrap the
        `build_outputs(...)` return in `self._stamp_metrics(...)`.
        ~9 lines of code change + 1 parametrised test.
   - (b) Refactor `BaseAgent.handle()` into a public `handle()` that
        delegates to a protected `_handle_inner()` template method
        each subclass fills in. Public `handle()` does the stamping
        once.

   **Default: (a) per-subclass touch.** Reviewer can see the
   stamping in each agent; the parametrised test pins it as a
   regression guard. (b) is cleaner architecturally but is a
   bigger refactor that we can do in iter-6+ if subclass `handle()`
   bodies keep accruing.

3. **Dispatcher synthetic failed report: include the exception
   message in `summary`, or sanitise?**
   - (a) Include `str(exc)[:1000]` verbatim. Faster to debug; risks
        leaking secret-like substrings into audit_log.
   - (b) Include only the exception **type** and a generic message;
        full traceback only in structlog.
   - (c) Hybrid: type + first line of exc message, truncated to
        500 chars.

   **Default: (c) hybrid.** Enough to diagnose from the demo report
   without dumping every internal in audit_log. The structlog
   `dispatcher.agent.handle.failed` event (already emitted) carries
   the full traceback for forensic use.

## Plan — six phases

### Phase 0 — Branch + plan commit

`git checkout -b worktree-iter-5 origin/main` (already done as part
of plan drafting). Commit this plan as `docs(iter-5): plan`. Surface
for owner review **before** any code changes. Phase 1+ starts only
after approval. Cost: $0.

### Phase 1 — Dispatcher exception → synthetic TASK_REPORT(failed)

The headline fix. When `agent.handle(msg)` raises, the dispatcher
should build a terminal `TASK_REPORT(failed)` from the failed
agent and run it through the same outbound pipeline as a real
output. The HoldQueue then drops dependents, the TaskStateReducer
rolls up the parent, and the team_feed shows the failure.

**Files:**
- Modify: `core/dispatcher/dispatcher.py`
- Test: `tests/integration/test_dispatcher_e2e.py` (new test for
  exception path) and a new unit test if helpful for the synthesis
  helper.

#### 1A — Failing integration test

Add a `_RaisingAgent` test double under `tests/integration/`
that raises a known exception on `handle()`. Wire it into the
dispatcher in a new integration test
`test_agent_handle_exception_synthesises_failed_report` that:

1. Submits a `task_assignment` to `_RaisingAgent`.
2. Polls `audit_log` for 10 s until a `task_report(status=failed)`
   appears with `sender=<the raising agent>`, `recipient=team_lead`
   (or `user`, depending on the upstream `sender` — see 1C
   below).
3. Verifies the synthesised report's `payload.summary` contains
   the exception type name.
4. Verifies the matching `Task` row's `status` flipped to `failed`
   via the iter-3 rollup (if a `parent_task_id` was set on the
   incoming).

Run: `pytest tests/integration/test_dispatcher_e2e.py::test_agent_handle_exception_synthesises_failed_report -v`
Expected: FAIL — no `task_report(failed)` appears today because the
dispatcher's `except` block doesn't emit anything.

#### 1B — Failing unit test (synthesis helper)

Extract the synthesis to a small pure helper
`_synthesise_failed_report(agent: BaseAgent, incoming: AgentMessage,
exc: BaseException) -> AgentMessage` in
`core/dispatcher/dispatcher.py` so we can unit-test it without
infra. Add a test in `tests/unit/test_dispatcher.py` (new file or
existing helpers module):

```python
def test_synthesise_failed_report_carries_correlation_and_task_id() -> None:
    incoming = _stub_task_assignment(task_id=UUID(...), parent_task_id=UUID(...))
    exc = RuntimeError("boom")
    out = _synthesise_failed_report(_FakeAgent(), incoming, exc)
    assert out.message_type == MessageType.TASK_REPORT
    assert out.sender == _FakeAgent.role
    assert out.recipient == AgentId.TEAM_LEAD
    assert out.correlation_id == incoming.correlation_id
    payload = out.payload
    assert isinstance(payload, TaskReportPayload)
    assert payload.status == TaskStatus.FAILED
    assert payload.task_id == incoming.payload.task_id
    assert "RuntimeError" in payload.summary
    assert out.metadata.get("parent_task_id") == str(incoming.payload.parent_task_id_or_none)
```

Run: `pytest tests/unit/test_dispatcher.py::test_synthesise_failed_report_carries_correlation_and_task_id -v`
Expected: FAIL — helper doesn't exist.

#### 1C — Implement the synthesis helper + wire into dispatcher

```python
# core/dispatcher/dispatcher.py — top-level helper near _parse_depends_on

def _synthesise_failed_report(
    *, agent: BaseAgent, incoming: AgentMessage, exc: BaseException
) -> AgentMessage:
    """Build a terminal TASK_REPORT(failed) for an agent that crashed.

    Lives at module scope so unit tests can exercise it without spinning
    up the dispatcher. Recipient defaults to TEAM_LEAD; for `user`-sent
    assignments the report goes back to USER so the root rollup still
    fires (the dispatcher only inserts a child Task row when an
    assignment carries `parent_task_id`).
    """
    payload_in = incoming.payload
    task_id = (
        payload_in.task_id
        if isinstance(payload_in, TaskAssignmentPayload)
        else uuid4()
    )
    parent_task_id = incoming.metadata.get("parent_task_id") if incoming.metadata else None
    type_name = type(exc).__name__
    first_line = str(exc).splitlines()[0] if str(exc) else ""
    summary = f"{type_name}: {first_line}"[:500]
    recipient = (
        AgentId.USER if incoming.sender == AgentId.USER else AgentId.TEAM_LEAD
    )
    metadata: dict[str, object] = {}
    if parent_task_id:
        metadata["parent_task_id"] = parent_task_id
    return AgentMessage(
        correlation_id=incoming.correlation_id,
        sender=agent.role,
        recipient=recipient,
        message_type=MessageType.TASK_REPORT,
        priority=Priority.P1,  # failures are high-priority for owner visibility
        payload=TaskReportPayload(
            task_id=task_id,
            status=TaskStatus.FAILED,
            progress_pct=0,
            summary=summary,
        ),
        metadata=metadata,
    )
```

Then wire it into the dispatcher's existing except block:

```python
# core/dispatcher/dispatcher.py — replace lines 125-132

try:
    outputs = await agent.handle(msg)
except Exception as exc:
    _log.exception(
        "dispatcher.agent.handle.failed",
        agent=agent.role.value,
    )
    agent_errors_total.labels(agent=agent.role.value, error_type="handle").inc()
    outputs = [_synthesise_failed_report(agent=agent, incoming=msg, exc=exc)]
```

The downstream `for out in outputs:` loop already audits, feed-publishes,
records task state, calls `HoldQueue.mark_failed`, and bus-publishes.
**No other dispatcher changes are needed** — the synthetic report
flows through the same pipeline as a real one.

Run: both new tests should now PASS. Existing dispatcher tests
should still pass.

#### 1D — Commit

`feat(dispatcher): synthesise TASK_REPORT(failed) when handle() raises`

### Phase 2 — `claude -p` agent permission mode (`acceptEdits`)

Frontend's iter-4 demo run blocked because the inner `claude -p`
gates file writes outside the project working dir at an interactive
prompt. The MCP path scope is already wide open; the gate is one
layer up. Pass `--permission-mode acceptEdits` so agent sessions
auto-accept edits.

**Files:**
- Modify: `core/llm/claude_code_headless.py`
- Test: `tests/unit/test_claude_code_headless.py` (existing file
  for adapter unit tests)

#### 2A — Failing unit test

```python
def test_invoke_passes_permission_mode_accept_edits(monkeypatch) -> None:
    """Adapter passes --permission-mode acceptEdits by default so
    agent sessions don't stall on interactive write prompts. See
    iter_4_demo_report.md Failure 2."""
    captured_argv: list[list[str]] = []

    async def fake_exec(*args, **kwargs):
        captured_argv.append(list(args))
        return _stub_subprocess(stdout=_minimal_claude_p_json(), returncode=0)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)

    client = ClaudeCodeHeadlessClient()
    asyncio.run(client.invoke(
        system_prompt="...", user_message="...", model="haiku"
    ))

    argv = captured_argv[0]
    assert "--permission-mode" in argv
    assert "acceptEdits" == argv[argv.index("--permission-mode") + 1]
```

Run: `pytest tests/unit/test_claude_code_headless.py::test_invoke_passes_permission_mode_accept_edits -v`
Expected: FAIL — the flag isn't passed today.

#### 2B — Implement

Add to the cmd builder right after `--max-budget-usd`:

```python
# Insert in core/llm/claude_code_headless.py:117
cmd += ["--permission-mode", "acceptEdits"]
```

Run: the new test passes. Existing adapter unit tests must still
pass (verify with `pytest tests/unit/test_claude_code_headless.py -v`).

#### 2C — Commit

`feat(llm): pass --permission-mode acceptEdits for agent sessions`

### Phase 3 — Per-agent `_stamp_metrics` parity

Today only TL and `BaseAgent.handle()`'s default path stamp
`metadata["llm"]`. Every subclass that overrides `handle()` skips
it. iter-4 demo had to flag "(no metrics)" for 5 rows. Fix: each
overriding subclass calls `self._stamp_metrics(outputs, response)`
before returning.

**Files (one-line edit each):**
- Modify: `agents/product_manager/agent.py`
- Modify: `agents/architect/agent.py`
- Modify: `agents/backend_developer/agent.py`
- Modify: `agents/designer/agent.py`
- Modify: `agents/frontend_developer/agent.py`
- Modify: `agents/qa_engineer/agent.py`
- Modify: `agents/devops/agent.py`
- Modify: `agents/sre_support/agent.py`
- Modify: `agents/market_researcher/agent.py`
- Test: `tests/unit/test_agent_metric_stamping.py` (new
  parametrised unit test)

#### 3A — Failing parametrised unit test

```python
# tests/unit/test_agent_metric_stamping.py
"""Pin: every agent subclass that overrides handle() stamps metadata['llm'].

Iter-4 demo report Failure 3 — only TL stamped metrics. Iter-5
brings the other 9 subclasses to parity."""
from __future__ import annotations

import pytest

from agents.architect import ArchitectAgent
from agents.backend_developer import BackendDeveloperAgent
from agents.designer import DesignerAgent
from agents.devops import DevopsAgent
from agents.frontend_developer import FrontendDeveloperAgent
from agents.market_researcher import MarketResearcherAgent
from agents.product_manager import ProductManagerAgent
from agents.qa_engineer import QaEngineerAgent
from agents.sre_support import SreSupportAgent

from .helpers import _StubLLM, _TaskAssignmentMessage, _stub_llm_response_for


@pytest.mark.parametrize("agent_cls", [
    ProductManagerAgent, ArchitectAgent, BackendDeveloperAgent,
    DesignerAgent, FrontendDeveloperAgent, QaEngineerAgent,
    DevopsAgent, SreSupportAgent, MarketResearcherAgent,
])
@pytest.mark.asyncio
async def test_handle_stamps_llm_metrics(agent_cls) -> None:
    """Each agent's handle() must stamp metadata['llm'] on every
    outbound message, so the demo SQL query can extract per-agent
    metrics in one paste."""
    stub_response = _stub_llm_response_for(agent_cls)
    agent = agent_cls(llm=_StubLLM(stub_response))
    incoming = _TaskAssignmentMessage(recipient=agent_cls.role)
    outputs = await agent.handle(incoming)
    assert outputs, f"{agent_cls.__name__} returned no outputs"
    for out in outputs:
        llm = out.metadata.get("llm")
        assert llm is not None, (
            f"{agent_cls.__name__} produced an output without "
            f"metadata['llm']: {out.message_type.value}"
        )
        assert "tokens_in" in llm
        assert "tokens_out" in llm
        assert "model" in llm
```

The `_stub_llm_response_for(agent_cls)` helper returns a minimal
valid `LLMResponse` whose `structured` field matches each agent's
schema. Keep the helper compact:

```python
# tests/unit/helpers.py (new file or extend if it exists)
def _stub_llm_response_for(agent_cls) -> LLMResponse:
    """Return a minimal valid LLMResponse for an agent's expected schema."""
    if agent_cls is ProductManagerAgent:
        structured = {"summary": "x", "stories": [_minimal_story()]}
    elif agent_cls is ArchitectAgent:
        structured = {"summary": "x", "decision": "y", "context": "z"}
    # ... etc, one minimal valid response per schema
    else:
        structured = {"summary": "x"}
    return LLMResponse(
        text="",
        structured=structured,
        session_id="t",
        tokens=TokensUsage(input=1, output=1, cached_input=0, model="claude-haiku-4-5"),
        cost_estimate_cents=0,
        duration_ms=1,
        validated_against_schema=True,
    )
```

Run: `pytest tests/unit/test_agent_metric_stamping.py -v`
Expected: FAIL for every agent except where `handle()` is the
BaseAgent default (none, in practice — every subclass overrides).

#### 3B — Touch each subclass

Per-subclass diff (PM shown; the other 8 follow the same shape):

```python
# agents/product_manager/agent.py — line 156, current:
return self.build_outputs(response, msg)

# After:
return self._stamp_metrics(self.build_outputs(response, msg), response)
```

Re-run the parametrised test. Expected: PASS for all 9 agents.

#### 3C — Commit

`feat(agents): stamp metadata['llm'] in every overridden handle()`

(Single commit for all 9 agents — small touches, semantically the
same change, easier to review together.)

### Phase 4 — Stderr-tee + stdout-on-failure in headless adapter

iter-4 demo's Backend crashed with `claude -p exited 1` and empty
stderr. Today's adapter only logs stderr. Add stdout to the failure
log so the next silent exit gives us a diagnostic.

**Files:**
- Modify: `core/llm/claude_code_headless.py` (lines 175-178)
- Test: `tests/unit/test_claude_code_headless.py`

#### 4A — Failing unit test

```python
def test_invoke_logs_stdout_on_non_zero_exit(monkeypatch, caplog) -> None:
    """When claude -p exits non-zero, the adapter logs both stderr
    AND stdout. Iter-4 demo had an empty-stderr crash with the actual
    error on stdout. See iter_4_demo_report.md Failure 1."""
    async def fake_exec(*args, **kwargs):
        return _stub_subprocess(
            stdout=b"actual error message on stdout",
            stderr=b"",
            returncode=1,
        )
    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)

    client = ClaudeCodeHeadlessClient()
    with pytest.raises(LLMInvocationError):
        asyncio.run(client.invoke(
            system_prompt="x", user_message="y", model="haiku"
        ))

    # Check the structlog event carries stdout.
    failed = [r for r in caplog.records if "llm.invoke.failed" in r.getMessage()]
    assert failed
    assert "actual error message on stdout" in failed[0].getMessage()
```

Run: expected FAIL — stdout isn't logged today.

#### 4B — Implement

```python
# core/llm/claude_code_headless.py — replace lines 175-178:
if proc.returncode != 0:
    err = stderr.decode(errors="replace")[:1000]
    out = stdout.decode(errors="replace")[:2000]
    log.error("llm.invoke.failed", returncode=proc.returncode, stderr=err, stdout=out)
    raise LLMInvocationError(
        f"claude -p exited {proc.returncode}: stderr={err!r} stdout={out!r}"
    )
```

#### 4C — Commit

`feat(llm): log stdout on claude -p non-zero exit`

### Phase 5 — Real-LLM e2e demo re-run

Cost budget: ~$1.50 expected, $3.50 ceiling (chain now runs to
completion; QA's Sonnet turn is the only added cost over iter-4).

**Files:**
- Create: `scripts/demo_iter_5.sh` (near-clone of
  `scripts/demo_iter_4.sh`)
- Modify: `Makefile` (alias `demo` → `demo-iter-5`)

#### 5A — `scripts/demo_iter_5.sh`

Fork `demo_iter_4.sh`. Differences:
- Title and task description say "iter-5"
- Config filename: `.iter5-mcp.json`
- Comment block at top describes iter-5's three fixes
- Otherwise identical (still 20-min wall-clock, still v2 spec, still
  direct-python MCP, still `AI_TEAM_DEMO_NON_INTERACTIVE=1` toggle)

#### 5B — Makefile

```makefile
demo: demo-iter-5 ## Alias for the current iteration's demo

demo-iter-5: ## Run iter-5 e2e (dispatcher exception fix + acceptEdits + per-agent metrics)
	bash scripts/demo_iter_5.sh

demo-iter-4: ## Run iter-4 e2e (regression baseline)
	bash scripts/demo_iter_4.sh
```

`demo-iter-3` and `demo-iter-2` stay as deeper regression baselines.

#### 5C — Commit + run

Commit the demo script + Makefile alias as
`chore(demo): demo_iter_5.sh — full-chain validation`.

Then run pre-flight:
- `.env` populated, `docker info`, `claude --version`,
  `gh auth status`, `.venv/bin/python --version`
- `make smoke-llm` PASS
- `uv run python scripts/measure_mcp_coldstart.py` PASS
- Quota at session start above the 30 % threshold

Then run the demo:
`AI_TEAM_DEMO_NON_INTERACTIVE=1 bash scripts/demo_iter_5.sh`

Approve QA's pending_review with
`uv run ai-team approve <id> --comment "iter-5 demo close-out"`.

#### 5D — Demo report

Write `docs/iterations/iter_5_demo_report.md` with:
- Chain timeline table from the single SQL query (now showing
  metrics for every row, not just TL — Phase 3's win)
- Verification of each iter-5 deliverable end-to-end:
  - Dispatcher synthesised a `task_report(failed)` for any agent
    that crashed mid-turn (or no crashes — equally fine).
  - Frontend completed its file write without an interactive
    permissions stall.
  - Every per-recipient row has non-empty `metadata.llm`.
- Cost / quota summary
- pending_review row evidence + owner-approve transcript
- Action items for iter-6

If the chain breaks mid-run, the report captures the failure mode
and informs iter-6 priorities — same posture as iter-3/4. Do not
paper over real failures.

### Phase 6 — Validation gates + retro + iter-6 handoff

| # | Task | Output |
|---|------|--------|
| 6A | `make lint typecheck sec test test-integration smoke-llm` all green | local terminal |
| 6B | **Run `uv run ruff format --check .`** (the iter-4 CI miss) | local terminal |
| 6C | Diff-cover ≥ 80 % on iter-5 diff vs `origin/main` | coverage report |
| 6D | `docs/iterations/iter_5_retro.md` — what shipped, what didn't, surprises, stats | committed retro |
| 6E | `docs/iterations/iter_6_handoff.md` — carry-overs (HoldQueue persistence, audit_writer role, hash-chain alert, GitHubTargetRepo, TL txn decomp, pytest-rerunfailures), hard constraints, ready-to-paste prompt | committed handoff |
| 6F | Open PR; squash-merge once CI green (self-approve per CLAUDE.md "dev-PR" layer) | merged PR; main at iter-5 squash |

## Risk register

- **Synthetic `task_report(failed)` interacts badly with TL's
  BLOCKED auto-routing.** TL's `_maybe_route_blocked` only fires on
  `status=BLOCKED`; the synthetic report's status is `failed`, so
  the auto-route path is skipped by construction. Sanity-check this
  in the integration test.
- **`--permission-mode acceptEdits` is too narrow.** If the demo
  surfaces another permissions-related stall, fall back to
  `bypassPermissions` in a follow-up commit. The flag is one
  string; the choice is reversible.
- **Per-agent stamping breaks an existing test that depends on
  missing metadata.** Unlikely (no test today checks for
  `metadata['llm'] == {}`), but if so, update the test rather than
  the production code.
- **The parametrised `test_handle_stamps_llm_metrics` requires a
  minimal-valid-LLMResponse-per-schema helper.** Some agent schemas
  are dense (Backend's response schema in particular). If a stub
  response can't be hand-rolled for one agent, mark that case
  `pytest.xfail("schema too dense for stub")` and pin the
  one-line stamping change with a direct unit test on that
  subclass.
- **Real-LLM demo still doesn't reach `pending_review`.** If QA's
  Sonnet turn fails or the new permissions mode unblocks Frontend
  but trips Backend differently, iter-5 demo report captures the
  new failure and informs iter-6. The deliverables themselves
  (Phases 1-4) don't depend on the demo passing.
- **Diff-cover dips below 80 %.** The dispatcher synthesis path
  adds maybe 15 lines; the parametrised test exercises every
  agent's `handle()` body. The phase 4 stdout-logging change is
  ~3 lines. We're comfortably above the gate; if `_stamp_metrics`
  one-line touches show as missed-coverage, the parametrised test
  exercises them.

## Cost projection

| Phase | Type | Estimate |
|-------|------|----------|
| 0     | docs | $0 |
| 1     | code + tests | $0 (no LLM) |
| 2     | code + 1 unit test | $0 |
| 3     | 9 one-line touches + parametrised test | $0 |
| 4     | 4 lines + unit test | $0 |
| 5     | real-LLM demo | ~$1.50 expected, $3.50 ceiling |
| 6     | docs + CI | $0 |
| **Total** | | **~$1.50 expected, $3.50 ceiling** |

Quota check before Phase 5 same as iter-3/4.

## Workflow

- Plan-before-code: this file lands as commit 1; no Phase-1+ code
  until owner approves the plan.
- Conventional commits; squash-merge on the iter-5 PR.
- Each phase's "Commit" row in tables above is one (and only one)
  commit. Phase 3 collapses 9 one-line edits into one commit; Phase 1
  has the helper extraction + dispatcher wiring in one commit.
- Run `make lint typecheck sec test` **and** `uv run ruff format
  --check .` after each phase to keep the branch shippable mid-flight
  (the iter-4 CI miss was a `ruff format` drift).
- Final demo report goes in the same PR.

## Ready-to-paste prompt for iter-6

Lives in `docs/iterations/iter_6_handoff.md` (Phase 6E).
