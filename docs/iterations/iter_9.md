# Iteration 9 — Plan

- **Status**: Draft (awaiting owner approval)
- **Plan author**: Claude (Opus 4.7)
- **Date drafted**: 2026-05-19
- **Base commit**: `2228cc0` on `main` (iter-8 squash)
- **Branch**: `worktree-iter-9` (cut from `origin/main` at plan commit)
- **Anchors (do not contradict)**: ADR-001 (orchestrator), ADR-004
  (per-agent tool allowlist), ADR-006 (model tier per agent),
  ADR-008 (LLM access), iter-8 retro + demo report
- **Carry-overs addressed**: items 1–2 of
  `docs/iterations/iter_9_handoff.md` — pre-flight MCP
  health-gate, and the re-run that should finally close the
  `pending_review` → owner approve loop iter-3/4/5/6/7/8 all
  reached for.
- **Deferred unchanged** (carry-over items 3–13 from iter-9
  handoff): dispatcher MCP-race substring router,
  `BaseAgent.llm_timeout_s` default 300 → 600 refactor,
  `^examples/` mypy exclude, HoldQueue persistence,
  `audit_writer` Postgres role, hash-chain alert,
  `GitHubTargetRepo`, TL transactional decomposition,
  `pytest-rerunfailures` plugin pin, `BaseAgent` template-method
  refactor, TL Backend decomposition.

## Goal — one sentence

Close iter-8's MCP-server connect race by adding a pre-flight
import-and-env check in `BaseAgent.handle()` that routes
deterministic startup failures to `BLOCKED(mcp_unhealthy)` (not
`FAILED + cascade-drop`), then re-run the iter-8 demo to finally
reach `pending_review`.

## Success criteria (binary, measurable)

1. **`core/llm/mcp_health.py` lands** with one public
   function `check_mcp_servers(config_path: str | None) -> list[str]`
   that returns a list of unhealthy server entries (`"<name>:
   <reason>"`) or `[]` when all known servers are healthy /
   no config / no known servers. Five unit tests pin the
   contract: (a) happy path with all three of our servers
   healthy, (b) import error on one server surfaces by name,
   (c) missing required env var for `ai_team_repo` surfaces by
   name, (d) `config_path is None` returns `[]` silently, (e)
   third-party server in config is silently skipped.
2. **`MCPUnhealthyError(LLMError)` lands in `core/llm/base.py`**
   alongside the existing `LLMBudgetExhaustedError`,
   `LLMTimeoutError`, `LLMInvocationError`. No new module just
   for the exception — keeps related errors together.
3. **`BaseAgent.handle()` calls `check_mcp_servers` before
   `_invoke_with_retries`** and raises `MCPUnhealthyError` if
   any server unhealthy. One new unit test: when the check
   returns unhealthy, `handle()` raises `MCPUnhealthyError`
   AND never calls `self._llm.invoke(...)` (asserted via the
   mock LLM client's invocation count). Skips silently when
   `AI_TEAM_MCP_CONFIG_PATH` is unset (preserves all existing
   mocked-LLM unit tests).
4. **Dispatcher routes `MCPUnhealthyError` to BLOCKED.**
   `core/dispatcher/dispatcher.py` `_synth_failed_report`
   extends the iter-6 special-case: `MCPUnhealthyError` →
   `status=BLOCKED, blocked_on='mcp_unhealthy', priority=P2`.
   Mirrors the existing `LLMBudgetExhaustedError` branch.
   One new integration test: dispatcher catches
   `MCPUnhealthyError`, emits a `task_report(blocked,
   blocked_on='mcp_unhealthy')`, dependent messages stay held
   in HoldQueue (not cascade-dropped).
5. **`scripts/demo_iter_9.sh` lands.** Clone of `demo_iter_8.sh`
   with iter-9 header (pre-flight MCP health-gate +
   `MCPUnhealthyError` → BLOCKED). Same 30-min wall-clock.
   `make demo` aliases to `demo-iter-9`; iter-8/7/6/5/4/3/2
   demos stay as regression baselines. `.iter9-mcp.json` is the
   config filename.
6. **Real-LLM e2e demo reaches `pending_review` → owner
   approve.** Chain runs PM → Architect → Backend → Designer →
   Frontend → QA; QA produces a `pending_review`; `uv run
   ai-team approve <id>` completes the loop; root `Task` flips
   terminal via the iter-3 rollup. Captured in
   `docs/iterations/iter_9_demo_report.md`. **OR**: if Backend
   trips the gate, BLOCKED routes cleanly (no cascade-drop) and
   the owner-retry path is exercised. **OR**: if a NEW failure
   mode appears past Backend, the report captures it and
   informs iter-10. Same posture as iter-3/4/5/6/7/8.
7. **All gates green**: `make lint typecheck sec test
   test-integration smoke-llm`. Diff-cover ≥ 80 % on the
   iter-9 diff vs `origin/main`. Ruff format clean.
8. **`docs/iterations/iter_9_retro.md` + `iter_10_handoff.md`**.

## Non-goals (explicitly deferred)

- **Dispatcher substring router on MCP-race summaries**
  (handoff item #3). Defense-in-depth for races that happen
  mid-run after a successful pre-flight ping. iter-10 picks up
  once iter-9's gate is proven in production.
- **`BaseAgent.llm_timeout_s` default 300 → 600 refactor**
  (handoff item #4). Touches 5+ agent files; iter-9 stays
  narrow. iter-10 work.
- **`^examples/` mypy exclude** (handoff item #5). One-line
  config fix; bundling into iter-9 would slightly widen scope.
  iter-10 work — sized to pair with #4.
- **Spawn-and-handshake MCP probe.** The brainstorm picked
  direct Python import as the strategy; spawn-and-handshake
  catches more races but doubles per-agent startup cost. If
  the import-only probe doesn't fully close the loop, iter-10
  extends.
- **Auto-retry on MCPUnhealthyError in dispatcher.** Same
  posture as iter-6/7/8 budget non-goal — surface to owner,
  don't auto-retry. Pairs with the substring router as a
  later iteration.
- **HoldQueue persistence, `audit_writer` Postgres role,
  hash-chain alert, `GitHubTargetRepo`, TL transactional
  decomposition, `pytest-rerunfailures` plugin pin,
  `BaseAgent` template-method refactor, TL Backend
  decomposition.** All deferred unchanged from iter-8 handoff.

## Decisions to confirm with owner (defaults below in **bold**)

1. **Gate scope — which servers to probe?**
   - (a) **Only `tools.mcp_servers.*` modules (recommended)**:
        skip third-party servers in the config (e.g. context7
        in development). We don't own their health; can't
        meaningfully probe them; not load-bearing for the
        demo.
   - (b) Probe everything in the config: catches third-party
        outages too but the surface is open-ended (we'd need
        per-server probe logic) and not the iter-8 failure
        mode.

   **Default: (a).** Narrowest fix to the observed failure.

2. **Gate failure → status?**
   - (a) **`BLOCKED(mcp_unhealthy)` (recommended)**: mirrors
        iter-6 `LLMBudgetExhaustedError → BLOCKED` pattern.
        Held messages stay in HoldQueue for owner manual
        retry; dependents stay held, not cascade-dropped.
        Better outcome shape than iter-8 demo's cascade-drop.
   - (b) `FAILED` + cascade-drop: simpler (no new dispatcher
        branch) but reproduces the exact iter-8 outcome the
        fix is meant to improve.

   **Default: (a).** Decided in brainstorming.

3. **Probe technique for our servers?**
   - (a) **`importlib.import_module(...)` + (for ai_team_repo)
        `Context.from_env(...)` (recommended)**: catches
        deterministic startup failures (ModuleNotFoundError,
        broken __init__ chain, missing env vars). Near-instant
        (< 100 ms total for all 3 servers). Doesn't catch
        stdio-handshake races.
   - (b) Subprocess + handshake (`python -m … --health-check`):
        catches stdio races too but requires adding a
        `--health-check` flag to each server module and costs
        ~50 ms × N servers per agent invocation.
   - (c) Both: import first (fast-fail), subprocess only if
        import passes (slow-path). More complex; iter-9 stays
        narrow.

   **Default: (a).** Decided in brainstorming. iter-10 can
   add (b) if races slip through.

4. **Gate call placement in `BaseAgent.handle()`?**
   - (a) **Top of `handle()`, before `_user_message_for`
        (recommended)**: fail fastest, no wasted work
        building the prompt. Saves the JSON-serialise +
        sanitize step.
   - (b) Inside `_invoke_with_retries`, on each attempt: would
        re-check across retries (the `LLMTimeoutError` retry
        path triggers up to 3 attempts), but the gate is a
        one-shot deterministic check — re-checking just
        re-does the import.

   **Default: (a).** Cheaper, clearer.

## Plan — seven phases

### Phase 0 — Branch + plan commit

`git checkout -b worktree-iter-9 origin/main` (already done).
Commit this plan as `docs(iter-9): plan`. Surface for owner
review **before** any code changes. Phase 1+ starts only after
approval. Cost: $0.

### Phase 1 — `core/llm/mcp_health.py` + `MCPUnhealthyError`

**Files:**
- New: `core/llm/mcp_health.py` (~50 LOC)
- Modify: `core/llm/base.py` (add `MCPUnhealthyError` class)
- New: `tests/unit/test_mcp_health.py` (~120 LOC, 5 tests)

#### 1A — Failing tests

```python
# tests/unit/test_mcp_health.py — new file
import json
from pathlib import Path
import pytest

from core.llm.mcp_health import check_mcp_servers


def _write_config(tmp_path: Path, servers: dict) -> str:
    path = tmp_path / "mcp.json"
    path.write_text(json.dumps({"mcpServers": servers}))
    return str(path)


def test_check_returns_empty_for_three_healthy_servers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Happy path: all three of our servers import + (for repo)
    env validates. See iter_9.md success criterion #1(a)."""
    monkeypatch.setenv("AI_TEAM_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("AI_TEAM_PATH_PREFIXES", "*")
    config = _write_config(tmp_path, {
        "ai-team-bus": {"command": "python", "args": ["-m", "tools.mcp_servers.ai_team_bus"]},
        "ai-team-tasks": {"command": "python", "args": ["-m", "tools.mcp_servers.ai_team_tasks"]},
        "ai-team-repo": {
            "command": "python",
            "args": ["-m", "tools.mcp_servers.ai_team_repo"],
            "env": {"AI_TEAM_REPO_ROOT": str(tmp_path), "AI_TEAM_PATH_PREFIXES": "*"},
        },
    })
    assert check_mcp_servers(config) == []


def test_check_returns_none_when_config_path_none() -> None:
    """No config = nothing to probe = silent skip. Preserves
    all existing mocked-LLM unit tests where no MCP is wired."""
    assert check_mcp_servers(None) == []


def test_check_surfaces_import_error_by_name(tmp_path: Path) -> None:
    """If a server's module fails to import, the result names it.
    Reproduces the iter-8 demo failure mode in unit form."""
    config = _write_config(tmp_path, {
        "ai-team-broken": {
            "command": "python",
            "args": ["-m", "tools.mcp_servers.nonexistent_module"],
        },
    })
    result = check_mcp_servers(config)
    assert len(result) == 1
    assert "ai-team-broken" in result[0]
    assert "ModuleNotFoundError" in result[0] or "ImportError" in result[0]


def test_check_surfaces_missing_env_var_for_repo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ai_team_repo requires AI_TEAM_REPO_ROOT — if absent in
    both the cfg env and os.environ, surface it."""
    monkeypatch.delenv("AI_TEAM_REPO_ROOT", raising=False)
    config = _write_config(tmp_path, {
        "ai-team-repo": {
            "command": "python",
            "args": ["-m", "tools.mcp_servers.ai_team_repo"],
            # intentionally no env block
        },
    })
    result = check_mcp_servers(config)
    assert any("ai-team-repo" in r for r in result)


def test_check_skips_third_party_servers_silently(tmp_path: Path) -> None:
    """Unknown modules (e.g. context7) are not ours to probe;
    silent skip. See iter_9.md decision #1(a)."""
    config = _write_config(tmp_path, {
        "context7": {"command": "npx", "args": ["-y", "@upstash/context7-mcp"]},
        "some-third-party": {"command": "python", "args": ["-m", "other.package"]},
    })
    assert check_mcp_servers(config) == []
```

Run: expected FAIL — module doesn't exist yet.

#### 1B — Implement

```python
# core/llm/base.py — add alongside existing LLM exceptions
class MCPUnhealthyError(LLMError):
    """Raised when a required MCP server fails its pre-flight
    health check. iter-9: routed to BLOCKED(mcp_unhealthy) by
    the dispatcher, mirroring iter-6's LLMBudgetExhaustedError
    → BLOCKED pattern. See iter_8_demo_report.md Failure 1 +
    iter_9.md success criterion #4."""
```

```python
# core/llm/mcp_health.py — new file
"""Pre-flight health check for ai-team MCP servers.

iter-9: the iter-8 demo surfaced an MCP-server connect race
inside Backend's `claude -p` session (all three ToolSearch
retries returned "still connecting"). This module catches the
deterministic startup failures (module import errors, missing
env vars) in-process before claude -p ever spawns, so failures
route to BLOCKED + owner retry instead of FAILED + cascade-drop.
Stdio-handshake races are NOT caught — iter-10's substring
router on the failure summary covers those.
"""
from __future__ import annotations

import importlib
import json
import os
from pathlib import Path

_OUR_PACKAGE = "tools.mcp_servers"


def check_mcp_servers(config_path: str | None) -> list[str]:
    """Return list of unhealthy server entries (one string per
    bad server, formatted "<name>: <reason>"), or [] when all
    known servers are healthy / config missing / no known
    servers in config.

    Only probes servers whose module path starts with
    `tools.mcp_servers.*` (our code). Third-party servers
    (context7, etc.) are silently skipped — we don't own
    their health and can't meaningfully probe them.
    """
    if not config_path:
        return []
    try:
        config = json.loads(Path(config_path).read_text())
    except (OSError, json.JSONDecodeError):
        return []
    servers = config.get("mcpServers") or {}
    unhealthy: list[str] = []
    for name, cfg in servers.items():
        module = _module_from_args(cfg.get("args") or [])
        if module is None or not module.startswith(_OUR_PACKAGE + "."):
            continue
        try:
            importlib.import_module(module)
            if module.endswith(".ai_team_repo"):
                _validate_repo_env(cfg.get("env") or {})
        except Exception as exc:  # noqa: BLE001 — surface every failure mode
            unhealthy.append(f"{name}: {type(exc).__name__}: {exc}")
    return unhealthy


def _module_from_args(args: list[str]) -> str | None:
    """Extract the module name from a `python -m <module>` argv."""
    for i, a in enumerate(args):
        if a == "-m" and i + 1 < len(args):
            return args[i + 1]
    return None


def _validate_repo_env(cfg_env: dict[str, str]) -> None:
    """Mimic `Context.from_env` env-var checks without
    instantiating the full Context (which touches the
    filesystem)."""
    effective = {**os.environ, **cfg_env}
    if not effective.get("AI_TEAM_REPO_ROOT"):
        raise ValueError("AI_TEAM_REPO_ROOT not set in env or cfg.env")
```

Run: 5 tests pass.

#### 1C — Commit

`feat(llm): add MCP server pre-flight health check`

### Phase 2 — `BaseAgent.handle()` wire-up

**Files:**
- Modify: `agents/_base/agent.py` (add `_mcp_health_check` +
  call site)
- Modify: `tests/unit/test_base_agent.py` (1 new test)

#### 2A — Failing test

```python
# tests/unit/test_base_agent.py — append
@pytest.mark.asyncio
async def test_handle_raises_mcp_unhealthy_and_skips_llm_invoke(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When the pre-flight MCP check returns unhealthy,
    handle() raises MCPUnhealthyError before ever invoking
    the LLM. See iter_9.md success criterion #3."""
    from core.llm.base import MCPUnhealthyError

    config = tmp_path / "mcp.json"
    config.write_text(json.dumps({
        "mcpServers": {
            "ai-team-broken": {
                "command": "python",
                "args": ["-m", "tools.mcp_servers.nonexistent_xyz"],
            }
        }
    }))
    monkeypatch.setenv("AI_TEAM_MCP_CONFIG_PATH", str(config))

    mock_llm = MockLLMClient(responses=["{}"])
    agent = _TestAgent(llm=mock_llm)
    msg = _make_task_assignment()

    with pytest.raises(MCPUnhealthyError, match="ai-team-broken"):
        await agent.handle(msg)
    assert mock_llm.invoke_call_count == 0  # never reached the LLM
```

Run: expected FAIL — BaseAgent doesn't check MCP health.

#### 2B — Implement

```python
# agents/_base/agent.py — add to BaseAgent
import os
from core.llm.base import LLMTimeoutError, MCPUnhealthyError, ModelTier
from core.llm.mcp_health import check_mcp_servers

# in BaseAgent.handle(), AT THE TOP before _user_message_for:
async def handle(self, msg: AgentMessage) -> list[AgentMessage]:
    """Default LLM-backed processing. Subclasses can override."""
    unhealthy = check_mcp_servers(os.environ.get("AI_TEAM_MCP_CONFIG_PATH"))
    if unhealthy:
        raise MCPUnhealthyError(
            f"MCP servers unhealthy ({len(unhealthy)}): "
            + "; ".join(unhealthy)
        )
    user_msg = self._user_message_for(msg)
    # ... rest unchanged
```

Run: new test passes; all existing BaseAgent / per-agent tests
stay green (no MCP config in unit tests → silent skip).

#### 2C — Commit

`feat(base-agent): pre-flight MCP health check in handle()`

### Phase 3 — Dispatcher routes `MCPUnhealthyError` to BLOCKED

**Files:**
- Modify: `core/dispatcher/dispatcher.py` (extend BLOCKED
  branch in `_synth_failed_report`)
- Modify: `tests/integration/test_dispatcher_e2e.py` (1 new
  test)

#### 3A — Failing test

```python
# tests/integration/test_dispatcher_e2e.py — append
async def test_mcp_unhealthy_emits_blocked_not_failed_or_cascade(
    integration_db, integration_bus, integration_feed,
) -> None:
    """When an agent's MCP pre-flight raises MCPUnhealthyError,
    the dispatcher emits task_report(blocked,
    blocked_on='mcp_unhealthy') and held dependents stay in
    HoldQueue (not cascade-dropped). Mirrors iter-6's BLOCKED
    branch for budget exhaustion. See iter_9.md success
    criterion #4."""
    from core.llm.base import MCPUnhealthyError

    # ... build a dispatcher with one agent whose handle() raises
    #     MCPUnhealthyError; assign a task with a dependent task;
    #     drive the dispatcher; assert:
    #     - audit_log row with status=blocked, blocked_on='mcp_unhealthy'
    #     - HoldQueue still holds the dependent (not dropped)
    #     - parent Task row stays in_progress (no any-failed rollup yet)
```

Run: expected FAIL — dispatcher routes MCPUnhealthyError to
FAILED via the existing else-branch.

#### 3B — Implement

```python
# core/dispatcher/dispatcher.py — extend the iter-6 branch in
# _synth_failed_report:
from core.llm.base import LLMBudgetExhaustedError, MCPUnhealthyError

# ...
if isinstance(exc, LLMBudgetExhaustedError):
    status = TaskStatus.BLOCKED
    blocked_on: str | None = "budget"
    priority = Priority.P2
elif isinstance(exc, MCPUnhealthyError):
    # iter-9: MCP pre-flight failures are recoverable by owner
    # (e.g. fix the env var, restart docker), not crashes.
    # Held dependents stay in HoldQueue, not cascade-dropped.
    # See iter_8_demo_report.md Failure 1 + iter_9.md decision #2.
    status = TaskStatus.BLOCKED
    blocked_on = "mcp_unhealthy"
    priority = Priority.P2
else:
    status = TaskStatus.FAILED
    blocked_on = None
    priority = Priority.P1
```

Run: new integration test passes; all existing dispatcher tests
stay green.

#### 3C — Commit

`feat(dispatcher): route MCPUnhealthyError to BLOCKED(mcp_unhealthy)`

### Phase 4 — Demo wall + `scripts/demo_iter_9.sh`

**Files:**
- Create: `scripts/demo_iter_9.sh` (clone of iter-8)
- Modify: `Makefile`

#### 4A — Clone and re-header

Fork `scripts/demo_iter_8.sh`. Differences:
- Header rewritten for iter-9 (pre-flight MCP health-gate +
  BLOCKED routing)
- Same `deadline=$((SECONDS + 1800))` (30 min)
- Config filename: `.iter9-mcp.json`
- Task title: "iter-9 demo: idea-validator v2 …"

#### 4B — Makefile alias

```makefile
demo: demo-iter-9 ## Alias for the current iteration's demo
demo-iter-9: ## Run iter-9 e2e (pre-flight MCP health-gate)
	bash scripts/demo_iter_9.sh
demo-iter-8: ## Run iter-8 e2e — regression baseline
	bash scripts/demo_iter_8.sh
# (iter-7 / iter-6 / iter-5 / iter-4 / iter-3 / iter-2 unchanged.)
```

Add `demo-iter-9` to the `.PHONY` list.

#### 4C — Commit

`chore(demo): demo_iter_9.sh — pre-flight MCP health-gate`

### Phase 5 — Real-LLM e2e demo

Cost budget: ~$2 expected (Backend now completes; prompt
caching is hot from iter-8), $5 ceiling. May come in lower
than iter-8's $1.13 if Backend's session re-uses the cached
context.

| # | Task | Output |
|---|------|--------|
| 5A | Pre-flight: `.env`, `docker info`, `claude --version`, `gh auth status`, `make smoke-llm` PASS, quota check | terminal capture |
| 5B | `AI_TEAM_DEMO_NON_INTERACTIVE=1 bash scripts/demo_iter_9.sh` | chain runs PM → Architect → Backend → Designer → Frontend → QA; pending_review row appears |
| 5C | `uv run ai-team list-pending` → capture review row; `uv run ai-team approve <id> --comment "iter-9 demo close-out"` | review approved |
| 5D | Single SQL query → per-agent table with metrics for every row | per-agent table |
| 5E | Write `docs/iterations/iter_9_demo_report.md` | committed report |

**If the chain still breaks** mid-run (a NEW failure mode under
iter-9's gate), the report captures it and informs iter-10.
Same posture as iter-3/4/5/6/7/8.

### Phase 6 — Validation gates + retro + iter-10 handoff

| # | Task | Output |
|---|------|--------|
| 6A | `make lint typecheck sec test test-integration smoke-llm` all green (typecheck via `uv run mypy --exclude '^examples/' .` until handoff #5 lands the symmetric exclude) | terminal |
| 6B | `uv run ruff format --check .` clean | terminal |
| 6C | Diff-cover ≥ 80 % on iter-9 diff vs `origin/main` | coverage report |
| 6D | `docs/iterations/iter_9_retro.md` — what shipped, what didn't, surprises, stats | committed retro |
| 6E | `docs/iterations/iter_10_handoff.md` — carry-overs, hard constraints, ready-to-paste prompt | committed handoff |
| 6F | Open PR; squash-merge once CI green via `gh api -X PUT .../merge -f merge_method=squash` (worktree can't `gh pr merge`) | merged PR; main at iter-9 squash |

## Risk register

- **Import-only check misses async-handshake races.** Accepted
  — handoff item #3 (dispatcher MCP-race substring router)
  is iter-10's defense-in-depth. If iter-9's demo still trips
  on a stdio race (claude -p says "still connecting" even
  though our import probe passed), it informs iter-10's
  priority.
- **`importlib.import_module` may have side effects** for some
  modules (top-level code that opens connections, etc.). The
  three modules we ship are pure imports — no top-level I/O
  beyond defining `_TOOL_LIST` and `main`. Verified by reading
  the source. Future MCP server modules must keep this
  property; documented in the docstring of `mcp_health.py`.
- **`Context.from_env` validation drift.** iter-9's gate
  duplicates a small subset of `Context.from_env`'s checks
  (just AI_TEAM_REPO_ROOT). If `Context.from_env` adds new
  required env vars, our gate could pass while the actual
  spawn fails. Mitigated by the same dispatcher exception
  synthesis path catching the spawn failure; the BLOCKED route
  may not fire but FAILED + cascade-drop is the existing
  behavior — no regression. iter-10 can lift this to call
  `Context.from_env` directly.
- **NEW failure mode emerges past Backend.** Frontend, QA
  haven't run to completion across seven demos — may surface
  their own timeout or budget gaps. Captured in the demo
  report; iter-10 picks them up. Cache hit rates are very
  high now, so this is the most likely category of new
  failure (rare interactions, not budget/timeout).
- **`make typecheck` still fails locally** on demo-polluted
  workspaces (handoff #5 deferred). Worked around in Phase 6A
  with explicit `--exclude '^examples/'`; CI on a fresh PR
  checkout is unaffected. Surface in the retro again so
  iter-10 isn't tempted to re-defer.

## Cost projection

| Phase | Type | Estimate |
|-------|------|----------|
| 0     | docs | $0 |
| 1     | code + 5 unit tests | $0 |
| 2     | code + 1 unit test | $0 |
| 3     | code + 1 integration test | $0 |
| 4     | shell + Makefile | $0 |
| 5     | real-LLM demo | ~$2 expected, $5 ceiling |
| 6     | docs + CI | $0 |
| **Total** | | **~$2 expected, $5 ceiling** |

Quota check before Phase 5. iter-7 demo spent $3.60, iter-8
spent $1.13; iter-9 may come in close to $1-2 if cache stays
hot. Backend's full implementation under sonnet $2.50 will be
the swing factor — if it completes, expect $2-3; if it hits
the cap, iter-8's substring detector fires and routes BLOCKED
within $2.50 of spend.

## Workflow

- Plan-before-code: this file lands as commit 1; no Phase-1+
  code until owner approves the plan.
- Conventional commits; squash-merge on the iter-9 PR.
- Each phase's "Commit" row is one (and only one) commit.
- Run `make lint typecheck sec test` **and** `uv run ruff format
  --check .` after each phase to keep the branch shippable.
- Final demo report goes in the same PR.

## Ready-to-paste prompt for iter-10

Lives in `docs/iterations/iter_10_handoff.md` (Phase 6E).
