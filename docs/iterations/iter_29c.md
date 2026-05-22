# Iter-29c Design Spec — cross-repo execution path + TL re-decompose depth cap

> **Status:** design spec (this doc). Implementation plan to follow via `superpowers:writing-plans` after owner approval.
>
> **For agentic workers (later):** REQUIRED SUB-SKILL when the implementation plan lands here: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement task-by-task.

**Goal:** Close the cross-repo agent execution path that iter-28 left as a hole. When a `TaskAssignment` carries `payload.target_repo="<owner>/<repo>"`, the dispatcher resolves it via `resolve_target_repo`, ensures the workspace is cloned, and routes the agent's `claude -p` subprocess into that workspace (cwd + `AI_TEAM_REPO_ROOT` env). Concurrently, cap TL's re-decompose chain via a metadata depth counter so Backend's 1500-char description-length tripwire can no longer trigger runaway loops. End state: iter-29b can dispatch the agent chain (TL → Architect → Backend → QA) against `girlsmakemedrink/telegram-tech-publisher` end-to-end, paying real-LLM quota only on legitimate work — no plumbing crashes, no runaway re-decompose burns.

**Architecture:** Two narrow, independent changes glued by a single new metadata key.

- **Plumbing.** The dispatcher already persists `payload.target_repo` to the `tasks` table (`core/dispatcher/dispatcher.py:226`) but never resolves it. iter-29c adds resolution + clone + workspace stash to `_handle_one` ahead of `agent.handle(msg)`. The workspace path rides on `msg.metadata["target_repo_workspace"]`. `BaseAgent._build_env` reads it and emits `AI_TEAM_REPO_ROOT=<workspace>` (what the MCP server and Backend's tripwire read). `BaseAgent._invoke_with_retries` passes `cwd=<workspace>` to the LLMClient. `ClaudeCodeHeadlessClient.invoke` forwards `cwd` to `asyncio.create_subprocess_exec(cwd=cwd)`. No changes to `AgentMessage` schemas, no new envelope fields.

- **Anti-loop cap.** TL's re-decompose path (`agents/team_lead/agent.py::_re_decompose_on_too_large`) reads `incoming.metadata.get("redecompose_depth", 0)`. When TL emits a re-decompose `TaskAssignment` to itself, it stamps `redecompose_depth=N+1` on the new envelope. If incoming depth ≥ `MAX_REDECOMPOSE_DEPTH = 2`, TL emits `TASK_REPORT(FAILED)` instead of re-decomposing, with a summary explaining the cap was hit. The existing `_AUTO_ROUTED_HINT` marker on subtask descriptions is retained — the depth counter is the hard ceiling that doesn't depend on LLM-generated text propagating the hint.

**Tech Stack:** Existing ai_team stack — Python 3.11, `asyncio.create_subprocess_exec`, `claude -p` subprocess, pytest + pytest-asyncio. No new dependencies.

**Source spec inputs:**
- `docs/adr/0001-orchestrator.md` — dispatcher contract.
- `docs/adr/0008-llm-client-adapter.md` — `LLMClient` Protocol contract (gets `cwd` added).
- `docs/adr/0009-target-repo-abstraction.md` — `TargetRepo` contract + `ensure_local_clone` semantics.
- `docs/iterations/iter_28_retro.md` + `iter_28_handoff.md` — `GitHubTargetRepo` impl; iter-28 closed the abstraction but left the dispatch path open.
- iter-29a session memory + product-repo PR #5 — confirmed the hole live on `correlation 82e6dd62` (2026-05-22): Backend tripwired on product-repo files because cwd defaulted to ai_team root.
- `core/dispatcher/dispatcher.py:111-195`, `agents/_base/agent.py:118-208`, `core/llm/claude_code_headless.py:149-240`, `core/target_repo/registry.py:34-61` — code surfaces being modified.

---

## Non-Goals (out of scope for iter-29c)

- **Running the iter-29b agent chain.** iter-29c proves the plumbing works (smoke + integration tests against a mocked LLM); the real-LLM chain dispatch is iter-29b's responsibility, run by the owner after iter-29c merges.
- **Workspace GC.** Manual `rm -rf ~/.ai_team/workspaces/<slug>` remains the cleanup story. ADR-009's "GC > 14 days" stays deferred.
- **Tripwire threshold tuning.** Backend's 1500-char description-length tripwire (`agents/backend_developer/agent.py:51`) stays at 1500. The depth cap makes the tripwire's existing behavior safe; revisiting the threshold itself is a separate, larger decision (would need data from N runs).
- **`_AUTO_ROUTED_HINT` removal.** The hint stays as belt-and-suspenders; the depth cap is the load-bearing fix.
- **Per-task workspace pinning at task creation time.** The dispatcher resolves per-message at handle time. Persisting "this task ran in workspace X" is already covered by the `tasks` table's `target_repo` column (iter-28). No new column.
- **Multi-repo concurrent dispatch.** One workspace per `target_repo` identifier; concurrent assignments to the same repo serialize on `ensure_local_clone` (already idempotent — clone-or-fetch). Genuine multi-repo parallelism is unchanged from iter-28.
- **Closing other iter-26b/27 carry-overs** (HoldQueue Postgres persistence, BaseAgent template-method refactor, `audit_writer` role, etc.). Single-focus iter.
- **`ANTHROPIC_API_KEY` hygiene checks.** The substrate split is enforced at code-review + grep-check time per [[project-ai-team]] invariants; iter-29c does not add CI gates.

---

## File Structure

### Created

- `tests/unit/test_dispatcher_target_repo_resolution.py` — dispatcher resolves `payload.target_repo`, stashes workspace on `msg.metadata`, calls `agent.handle`. Includes failure path (bad identifier) → synthesized FAILED report.
- `tests/unit/test_base_agent_workspace_env.py` — `_build_env` adds `AI_TEAM_REPO_ROOT` when workspace metadata present; absent when not. `_invoke_with_retries` forwards `cwd` to LLM.
- `tests/unit/test_claude_code_headless_cwd.py` — `ClaudeCodeHeadlessClient.invoke(cwd=…)` passes through to `create_subprocess_exec`. Uses monkeypatch on `asyncio.create_subprocess_exec`.
- `tests/unit/test_team_lead_redecompose_depth_cap.py` — depth=0 re-decomposes (regression guard); depth=`MAX_REDECOMPOSE_DEPTH` emits `TASK_REPORT(FAILED)` with cap-exceeded summary.
- `tests/integration/test_cross_repo_dispatch_e2e.py` — `@pytest.mark.integration`; full dispatcher → BaseAgent → MockLLM chain with `TaskAssignment(target_repo="…")`; asserts MockLLM received the right `cwd` arg. Uses an in-process MockLLMClient that captures kwargs. No real `claude -p`, no real GitHub.
- `scripts/smoke_cross_repo_dispatch.sh` — owner-runnable smoke that submits a synthetic task with `target_repo="girlsmakemedrink/telegram-tech-publisher"` against a mocked LLM and prints the cwd that would have been used. Exercises the real `ensure_local_clone` against the real workspace.
- `docs/iterations/iter_29c_retro.md` — written in Phase C.
- `docs/iterations/iter_29c_handoff.md` — written in Phase C.

### Modified

- `core/dispatcher/dispatcher.py` — `__init__` gains `ai_team_root: Path` kwarg (or reads from a new module-level constant — pick at impl time, prefer kwarg for testability). `_handle_one` resolves `target_repo` and stashes workspace before `agent.handle`. Resolution lives inside the existing `try/except` so failures route through `_synthesise_failed_report`.
- `core/llm/base.py` — `LLMClient` Protocol's `invoke()` gets `cwd: str | None = None`.
- `core/llm/claude_code_headless.py` — `invoke()` accepts `cwd`, forwards to `_spawn_once`, which passes `cwd=cwd` to `asyncio.create_subprocess_exec`. Default `None` means current behavior (inherit parent cwd).
- `core/llm/mock.py` — `MockLLMClient.invoke` accepts and records `cwd` so tests can assert on it.
- `agents/_base/agent.py` — `_build_env` adds `AI_TEAM_REPO_ROOT` from `msg.metadata.get("target_repo_workspace")` when present. `_invoke_with_retries` passes `cwd=msg.metadata.get("target_repo_workspace")` to `self._llm.invoke`.
- `agents/team_lead/agent.py` — `_re_decompose_on_too_large` (or whichever function emits the re-decompose `TaskAssignment`) reads `incoming.metadata.get("redecompose_depth", 0)`, stamps `redecompose_depth=N+1` on the new envelope, and short-circuits to `TASK_REPORT(FAILED)` at `N >= MAX_REDECOMPOSE_DEPTH = 2`.
- `tests/unit/test_dispatcher.py` (or equivalent) — add coverage for the new resolution branch; existing tests should keep passing unchanged (when `payload.target_repo is None`, resolution is skipped — current behavior preserved).
- `Makefile` — add `smoke-cross-repo-dispatch: scripts/smoke_cross_repo_dispatch.sh && bash $<` target. Add to `make help` listing.
- `CLAUDE.md` — update "Current phase" paragraph to mention iter-29c shipped; under "Operating principles", add a one-line note that cross-repo tasks now run with cwd = workspace.

---

## Data Flow (cross-repo task, end-to-end)

```
owner → ai-team submit ... --target-repo girlsmakemedrink/telegram-tech-publisher
  → API → AgentMessage(TaskAssignment, payload.target_repo="girlsmakemedrink/telegram-tech-publisher")
    → bus → AgentDispatcher._handle_one
      → resolve_target_repo("girlsmakemedrink/telegram-tech-publisher", ai_team_root=…)
        → GitHubTargetRepo(identifier)
      → await repo.ensure_local_clone()
        → ~/.ai_team/workspaces/girlsmakemedrink--telegram-tech-publisher/  (clone or fetch)
      → msg.metadata["target_repo_workspace"] = str(repo.root)
      → agent.handle(msg)
        → BaseAgent._build_env(msg):
            AI_TEAM_AGENT_ROLE=team_lead
            AI_TEAM_CORRELATION_ID=<uuid>
            AI_TEAM_TASK_ID=<uuid>
            AI_TEAM_REPO_ROOT=/Users/…/.ai_team/workspaces/girlsmakemedrink--telegram-tech-publisher
            (+ self.mcp_env)
        → BaseAgent._invoke_with_retries(..., cwd=<workspace>)
          → ClaudeCodeHeadlessClient.invoke(..., cwd=<workspace>)
            → asyncio.create_subprocess_exec(claude -p ..., cwd=<workspace>, env=...)
              → claude -p starts in <workspace>
              → MCP server reads AI_TEAM_REPO_ROOT=<workspace>
              → Backend's git / gh / Bash tool calls run in <workspace>
              → Backend's tripwire base-path check reads AI_TEAM_REPO_ROOT
```

For non-`TaskAssignment` messages (TASK_REPORT, BROADCAST) or assignments without `target_repo`: dispatcher skips resolution; agent runs with no workspace metadata; `cwd` is `None`; subprocess inherits dispatcher cwd. ai_team-self-hosting iters (anything without an external `target_repo`) keep working unchanged.

### Re-decompose depth cap flow

```
TL receives TaskAssignment(metadata.redecompose_depth=0 or absent) from owner
  → emits 3 subtask TaskAssignments to Backend (depth not propagated to children;
     it's a TL-internal counter)
Backend tripwires on subtask description length
  → emits TASK_REPORT(BLOCKED, blocked_on="task_too_large") back to TL
TL._re_decompose_on_too_large(report):
  incoming_depth = report.metadata.get("redecompose_depth", 0)
  IF incoming_depth >= MAX_REDECOMPOSE_DEPTH (=2):
    emit TASK_REPORT(FAILED, summary="re-decompose depth cap (2) exceeded; …")
    return
  ELSE:
    emit TaskAssignment(to=TL_SELF, metadata.redecompose_depth=incoming_depth+1, …)
```

The counter rides on TL→TL self-assignments only. Subtask assignments to Backend etc. do not carry the counter (and don't need to). On any cap-exceeded path, the dispatcher cascades the FAILED status normally — dependents drop, owner sees it in feed within one correlation.

---

## Error Handling

- **`resolve_target_repo` raises (bad identifier, unknown shape):** Caught by `_handle_one`'s existing `try/except`. `_synthesise_failed_report` emits `TASK_REPORT(FAILED, summary="<exc type>: <first line>")`. Owner sees the failure in feed; no zombie tasks.
- **`ensure_local_clone` raises (network, missing gh auth, bad SSH config, repo gone):** Same path. Existing iter-28 smoke depends on `gh auth status` and surfaces these clearly; the dispatcher just propagates.
- **`cwd` doesn't exist when subprocess spawns:** `create_subprocess_exec` raises `FileNotFoundError` or `NotADirectoryError`. The existing `ClaudeCodeHeadlessClient._spawn_once` catches `FileNotFoundError` only for the binary itself; cwd errors propagate as generic OSError → `agent.handle` exception path → synthesized FAILED report.
- **Depth cap exceeded:** TL emits a regular `TASK_REPORT(FAILED)` with a clear `summary`. Dispatcher's normal `_cascade_drops` runs; dependents drop; owner notified via feed. No special-case error type.
- **MCP server still reads stale `AI_TEAM_REPO_ROOT`:** Already a per-call env merge via `BaseAgent._build_env` → `claude_code_headless.invoke(env=…)`. iter-29c just adds the right value to that dict; the MCP startup-config code path is unchanged.

No new exception types. No new alerting hooks. All failures route through the existing iter-5 `_synthesise_failed_report` substrate.

---

## Testing

**Unit (`@pytest.mark.unit` default):**

- `tests/unit/test_dispatcher_target_repo_resolution.py`
  - `test_resolves_and_stashes_workspace_for_assignment_with_target_repo`
  - `test_skips_resolution_when_payload_target_repo_is_none`
  - `test_skips_resolution_for_non_assignment_messages`
  - `test_resolution_failure_synthesises_failed_report` (bad identifier)
  - `test_clone_failure_synthesises_failed_report` (raises inside `ensure_local_clone`, asserts FAILED report flows through feed)
- `tests/unit/test_base_agent_workspace_env.py`
  - `test_build_env_includes_repo_root_when_workspace_in_metadata`
  - `test_build_env_omits_repo_root_when_workspace_absent`
  - `test_invoke_passes_cwd_from_metadata`
  - `test_invoke_cwd_is_none_when_metadata_absent`
- `tests/unit/test_claude_code_headless_cwd.py`
  - `test_invoke_forwards_cwd_to_subprocess`
  - `test_invoke_default_cwd_is_none` (regression guard for self-hosting path)
- `tests/unit/test_team_lead_redecompose_depth_cap.py`
  - `test_depth_zero_re_decomposes_as_before`
  - `test_depth_one_re_decomposes_with_incremented_counter`
  - `test_depth_at_cap_emits_failed_report`
  - `test_cap_exceeded_summary_mentions_depth_and_threshold`

**Integration (`@pytest.mark.integration`):**

- `tests/integration/test_cross_repo_dispatch_e2e.py`
  - Spin up an `AgentDispatcher` with one BaseAgent subclass wired to `MockLLMClient`. Submit a `TaskAssignment(target_repo="girlsmakemedrink/telegram-tech-publisher")`. Assert: MockLLM was called with `cwd=<workspace>` and `env["AI_TEAM_REPO_ROOT"]=<workspace>`. No real `claude -p`. Does invoke real `ensure_local_clone` against the existing workspace clone (skip-if-not-cloned, or pre-clone in fixture).

**Smoke (owner-run):**

- `make smoke-cross-repo-dispatch` runs `scripts/smoke_cross_repo_dispatch.sh`:
  1. Confirm `~/.ai_team/workspaces/girlsmakemedrink--telegram-tech-publisher/` exists or clone it.
  2. Submit a synthetic `TaskAssignment` with `target_repo` set, via a temp in-process dispatcher + MockLLM.
  3. Print the resolved workspace path + the `cwd` MockLLM saw + the `AI_TEAM_REPO_ROOT` env value.
  4. Green if all three match the expected workspace.

**Real-LLM smoke (deferred to iter-29b):** the actual `claude -p` chain against the product repo is iter-29b's first test. iter-29c stays mocked-LLM-only to keep cost zero and signal sharp on the plumbing itself.

**Static gates (no change):** `ruff check` strict, `mypy --strict`, `bandit` high-only, ≥80% diff-cover. The `LLMClient` Protocol gets a new optional kwarg — mypy should keep both backends passing.

---

## PR Slicing

Three small PRs, all on ai_team. PR 1 and PR 2 are independent — landing order doesn't matter.

### PR 1 — Cross-repo plumbing (~6 src files + ~5 test files + Makefile + smoke script)

- `core/dispatcher/dispatcher.py`: `_handle_one` resolution branch + constructor `ai_team_root` kwarg.
- `core/llm/base.py`: `LLMClient` Protocol gains `cwd`.
- `core/llm/claude_code_headless.py`: `invoke` + `_spawn_once` accept and forward `cwd`.
- `core/llm/mock.py`: capture `cwd`.
- `agents/_base/agent.py`: `_build_env` + `_invoke_with_retries` workspace plumbing.
- Tests: `test_dispatcher_target_repo_resolution.py`, `test_base_agent_workspace_env.py`, `test_claude_code_headless_cwd.py`, `test_cross_repo_dispatch_e2e.py` (integration).
- `Makefile` + `scripts/smoke_cross_repo_dispatch.sh`.
- Branch: `feat/iter-29c-cross-repo-plumbing`.

### PR 2 — TL re-decompose depth cap

- `agents/team_lead/agent.py`: `MAX_REDECOMPOSE_DEPTH` constant + depth counter + cap branch.
- `tests/unit/test_team_lead_redecompose_depth_cap.py`.
- Branch: `feat/iter-29c-redecompose-depth-cap`.

### PR 3 — iter-29c wrap

- `docs/iterations/iter_29c_retro.md` — what we learned, carry-overs surfaced.
- `docs/iterations/iter_29c_handoff.md` — what iter-29b should pick up first.
- `CLAUDE.md`: "Current phase" + one-line cross-repo dispatch note.
- Branch: `docs/iter-29c-wrap`.

### Spec PR (this doc)

- `docs/iterations/iter_29c.md` — this design spec.
- Branch: `docs/iter-29c-plan`.
- Land first so the impl PRs reference a stable spec.

---

## Plan-time decisions (resolved open questions)

The four open questions from the spec are resolved as follows. The implementation plan that follows operates on these decisions.

1. **`ai_team_root` source in the dispatcher.** Added as `ai_team_root: Path | None = None` kwarg on `AgentDispatcher.__init__`. Default is a module-level `_AI_TEAM_ROOT_DEFAULT = Path(__file__).resolve().parents[2]` (dispatcher.py is at `core/dispatcher/dispatcher.py`, so `parents[2]` is the ai_team repo root). The API lifespan does NOT need to pass the kwarg explicitly — the module-relative default is correct for the production single-process wiring. Tests inject `ai_team_root=tmp_path` explicitly.

2. **TL re-decompose code shape.** Confirmed via read: `_re_decompose_on_too_large` lives at `agents/team_lead/agent.py:345`. PR #47 already fixed the FK bug by reusing `msg.payload.task_id` as the re-decompose anchor — that path is preserved. **Design correction vs spec wording:** the depth counter is in-process state on the `TeamLeadAgent` instance (`self._redecompose_depth: dict[UUID, int]`), keyed by `correlation_id`. The spec's "redecompose_depth on the envelope" wording would have required Backend to echo depth onto its BLOCKED tripwire report — a separate Backend file change, out of the spec's Phase B scope. In-process counter achieves the same load-bearing intent (cap re-decompose chains at depth 2) with single-file scope. The counter is cleared on FAILED-emit and bounded by correlation_id cardinality.

3. **Integration test workspace fixture.** Pre-clone into a `tmp_path`-based workspace inside the test, NOT `~/.ai_team/workspaces/`. Heavier than skip-if-absent but more reliable. Skips when `gh auth status` fails, matching iter-28's smoke. Workspace lives outside `~/.ai_team/workspaces/` so the owner's real workspace stays untouched.

4. **`ensure_local_clone` caching.** Called per-dispatch. The method is already idempotent (clone on first call, `git fetch --all` afterward), and fetch is fast. No in-process cache layer. Revisit only if profiling later shows fetch latency dominates dispatch time.

---

## Phase A — Cross-repo plumbing (PR 1) (Day 1, ~3-4 h)

End state of Phase A: a `TaskAssignment(target_repo="<owner>/<repo>")` flows from dispatcher → resolves the workspace → BaseAgent injects `AI_TEAM_REPO_ROOT` + `cwd` → `claude -p` (or MockLLM) runs in the workspace. All wired and mocked-LLM tested.

### Task A1: Thread `cwd` through `LLMClient` Protocol + implementations

**Files:**
- Modify: `core/llm/base.py` — `LLMClient.invoke()` Protocol signature.
- Modify: `core/llm/claude_code_headless.py` — `invoke()` + `_spawn_once()` forward `cwd`.
- Modify: `core/llm/mock.py` — `MockLLMClient.invoke` accepts + records `cwd`.
- Modify: `core/llm/agent_sdk_stub.py` — stub signature.
- Create: `tests/unit/test_claude_code_headless_cwd.py`.

- [ ] **Step A1.1: Branch from main**

```bash
cd /Users/kirillterskih/ai_team
git checkout main && git pull --ff-only
git checkout -b feat/iter-29c-cross-repo-plumbing
```

- [ ] **Step A1.2: Write failing tests for `cwd` forwarding**

Create `tests/unit/test_claude_code_headless_cwd.py`:

```python
"""Tests for cwd forwarding through ClaudeCodeHeadlessClient. See iter-29c."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.llm.claude_code_headless import ClaudeCodeHeadlessClient


def _fake_proc(stdout: bytes = b'{"result":"hi","session_id":"s","usage":{}}') -> MagicMock:
    proc = MagicMock()
    proc.returncode = 0
    proc.communicate = AsyncMock(return_value=(stdout, b""))
    return proc


@pytest.mark.asyncio
async def test_invoke_forwards_cwd_to_subprocess() -> None:
    client = ClaudeCodeHeadlessClient(binary="claude")
    with patch(
        "core.llm.claude_code_headless.asyncio.create_subprocess_exec",
        new=AsyncMock(return_value=_fake_proc()),
    ) as mock_spawn:
        await client.invoke(system_prompt="sp", user_message="um", cwd="/tmp/ws-X")
    assert mock_spawn.await_args.kwargs.get("cwd") == "/tmp/ws-X"


@pytest.mark.asyncio
async def test_invoke_default_cwd_is_none() -> None:
    """Self-hosting regression guard: omitted cwd → subprocess inherits parent cwd."""
    client = ClaudeCodeHeadlessClient(binary="claude")
    with patch(
        "core.llm.claude_code_headless.asyncio.create_subprocess_exec",
        new=AsyncMock(return_value=_fake_proc()),
    ) as mock_spawn:
        await client.invoke(system_prompt="sp", user_message="um")
    assert mock_spawn.await_args.kwargs.get("cwd") is None
```

- [ ] **Step A1.3: Run new tests — expect FAIL**

```bash
cd /Users/kirillterskih/ai_team && uv run pytest tests/unit/test_claude_code_headless_cwd.py -v
```

Expected: 2 fails — `TypeError: invoke() got an unexpected keyword argument 'cwd'`.

- [ ] **Step A1.4: Add `cwd` to `LLMClient` Protocol**

Edit `core/llm/base.py`. In the `class LLMClient(Protocol):` block, append `cwd: str | None = None,` as the last kwarg before `) -> LLMResponse: ...`. The full new signature:

```python
    async def invoke(
        self,
        *,
        system_prompt: str,
        user_message: str,
        model: ModelTier = "sonnet",
        allowed_tools: Sequence[str] = (),
        disallowed_tools: Sequence[str] = (),
        session_id: str | None = None,
        mcp_config_path: str | None = None,
        timeout_s: int = 120,
        max_turns: int = 8,
        json_schema: dict[str, Any] | None = None,
        max_budget_usd: float | None = None,
        env: dict[str, str] | None = None,
        cwd: str | None = None,
    ) -> LLMResponse: ...
```

- [ ] **Step A1.5: Add `cwd` to `ClaudeCodeHeadlessClient.invoke` and forward through `_spawn_once`**

Edit `core/llm/claude_code_headless.py`:

(a) In the `invoke()` signature, add `cwd: str | None = None,` as the last kwarg.

(b) Update both `_spawn_once` call sites in `invoke` (the initial call near line 235 and the session-collision retry near line 264) to pass `cwd=cwd`:

```python
        returncode, stdout, stderr = await self._spawn_once(
            cmd, timeout_s=timeout_s, env=effective_env, cwd=cwd, log=log
        )
```

(c) In `_spawn_once`'s signature, accept `cwd: str | None`:

```python
    async def _spawn_once(
        self,
        cmd: list[str],
        *,
        timeout_s: int,
        env: dict[str, str] | None,
        cwd: str | None,
        log: Any,
    ) -> tuple[int, bytes, bytes]:
```

(d) Inside `_spawn_once`, pass `cwd=cwd` to `create_subprocess_exec`:

```python
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
                cwd=cwd,
            )
```

- [ ] **Step A1.6: Add `cwd` to `MockLLMClient.invoke` and record it**

Edit `core/llm/mock.py`. Add `cwd: str | None = None,` to `invoke()` (last kwarg) and record it on `self._calls`:

```python
    async def invoke(
        self,
        *,
        system_prompt: str,
        user_message: str,
        model: ModelTier = "sonnet",
        allowed_tools: Sequence[str] = (),
        disallowed_tools: Sequence[str] = (),
        session_id: str | None = None,
        mcp_config_path: str | None = None,
        timeout_s: int = 120,
        max_turns: int = 8,
        json_schema: dict[str, Any] | None = None,
        max_budget_usd: float | None = None,
        env: dict[str, str] | None = None,
        cwd: str | None = None,
    ) -> LLMResponse:
        key = self._make_key(system_prompt, user_message)
        self._calls.append({"key": key, "model": model, "cwd": cwd or ""})
```

- [ ] **Step A1.7: Add `cwd` to `ClaudeAgentSDKClient` stub**

Edit `core/llm/agent_sdk_stub.py`. Add `cwd: str | None = None,` to the `invoke()` signature (last kwarg). The body still raises `NotImplementedError` — no behavioral change.

- [ ] **Step A1.8: Run new tests — expect PASS**

```bash
cd /Users/kirillterskih/ai_team && uv run pytest tests/unit/test_claude_code_headless_cwd.py -v
```

Expected: 2 PASS.

- [ ] **Step A1.9: Run existing LLM + agent tests for regression**

```bash
cd /Users/kirillterskih/ai_team && uv run pytest tests/unit/test_claude_code_headless.py tests/unit/test_base_agent.py -v
```

Expected: all PASS — existing callers don't pass `cwd`, and the default-`None` keeps the subprocess behavior unchanged.

- [ ] **Step A1.10: Lint + typecheck**

```bash
cd /Users/kirillterskih/ai_team && uv run ruff check core/llm/ tests/unit/test_claude_code_headless_cwd.py && uv run mypy core/llm/
```

Expected: clean.

- [ ] **Step A1.11: Commit**

```bash
cd /Users/kirillterskih/ai_team
git add core/llm/base.py core/llm/claude_code_headless.py core/llm/mock.py core/llm/agent_sdk_stub.py tests/unit/test_claude_code_headless_cwd.py
git commit -m "feat(llm): thread cwd through LLMClient protocol + impls (iter-29c step 1/6)"
```

### Task A2: BaseAgent injects `AI_TEAM_REPO_ROOT` env + `cwd` from `msg.metadata`

**Files:**
- Modify: `agents/_base/agent.py` — `_build_env` reads `target_repo_workspace`; `_invoke_with_retries` forwards `cwd`.
- Create: `tests/unit/test_base_agent_workspace_env.py`.

- [ ] **Step A2.1: Write failing tests**

Create `tests/unit/test_base_agent_workspace_env.py`:

```python
"""BaseAgent workspace env + cwd injection. See iter-29c."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from agents._base import BaseAgent
from core.llm.base import LLMResponse, TokensUsage
from core.messaging.schemas import (
    AgentId,
    AgentMessage,
    MessageType,
    Priority,
    TaskAssignmentPayload,
)


class _RecordingLLM:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def invoke(self, **kwargs: Any) -> LLMResponse:
        self.calls.append(kwargs)
        return LLMResponse(
            text="ok",
            session_id="s",
            tokens=TokensUsage(input=0, output=0, model="mock"),
            duration_ms=0,
        )

    async def reset_session(self, session_id: str) -> None:
        return None


class _DummyAgent(BaseAgent):
    role = AgentId.BACKEND_DEVELOPER
    system_prompt_path = Path("/dev/null")
    allowed_tools = ()

    def build_outputs(self, response, incoming):  # type: ignore[no-untyped-def]
        return []

    def system_prompt(self) -> str:
        return "system"


def _assignment(*, workspace: str | None = None) -> AgentMessage:
    metadata: dict[str, object] = {}
    if workspace is not None:
        metadata["target_repo_workspace"] = workspace
    return AgentMessage(
        correlation_id=uuid4(),
        sender=AgentId.TEAM_LEAD,
        recipient=AgentId.BACKEND_DEVELOPER,
        message_type=MessageType.TASK_ASSIGNMENT,
        priority=Priority.P2,
        payload=TaskAssignmentPayload(task_id=uuid4(), title="t", description="d"),
        metadata=metadata,
    )


def test_build_env_includes_repo_root_when_workspace_in_metadata() -> None:
    agent = _DummyAgent(llm=_RecordingLLM())
    env = agent._build_env(_assignment(workspace="/tmp/ws-X"))
    assert env["AI_TEAM_REPO_ROOT"] == "/tmp/ws-X"


def test_build_env_omits_repo_root_when_workspace_absent() -> None:
    agent = _DummyAgent(llm=_RecordingLLM())
    env = agent._build_env(_assignment(workspace=None))
    assert "AI_TEAM_REPO_ROOT" not in env


@pytest.mark.asyncio
async def test_invoke_passes_cwd_from_metadata() -> None:
    llm = _RecordingLLM()
    agent = _DummyAgent(llm=llm)
    await agent._invoke_with_retries(
        msg=_assignment(workspace="/tmp/ws-Y"),
        system_prompt="sp",
        user_message="um",
    )
    assert llm.calls[0]["cwd"] == "/tmp/ws-Y"
    assert llm.calls[0]["env"]["AI_TEAM_REPO_ROOT"] == "/tmp/ws-Y"


@pytest.mark.asyncio
async def test_invoke_cwd_is_none_when_metadata_absent() -> None:
    llm = _RecordingLLM()
    agent = _DummyAgent(llm=llm)
    await agent._invoke_with_retries(
        msg=_assignment(workspace=None),
        system_prompt="sp",
        user_message="um",
    )
    assert llm.calls[0]["cwd"] is None
    assert "AI_TEAM_REPO_ROOT" not in llm.calls[0]["env"]
```

- [ ] **Step A2.2: Run new tests — expect FAIL**

```bash
cd /Users/kirillterskih/ai_team && uv run pytest tests/unit/test_base_agent_workspace_env.py -v
```

Expected: 4 fails — `AI_TEAM_REPO_ROOT` key missing on env; `cwd` not present in kwargs.

- [ ] **Step A2.3: Inject `AI_TEAM_REPO_ROOT` in `_build_env`**

Edit `agents/_base/agent.py`. Replace the existing `_build_env` body:

```python
    def _build_env(self, msg: AgentMessage) -> dict[str, str]:
        env: dict[str, str] = {
            "AI_TEAM_AGENT_ROLE": self.role.value,
            "AI_TEAM_CORRELATION_ID": str(msg.correlation_id),
        }
        task_id = getattr(msg.payload, "task_id", None)
        if task_id is not None:
            env["AI_TEAM_TASK_ID"] = str(task_id)
        # iter-29c: cross-repo workspace path stashed by the dispatcher
        # on msg.metadata['target_repo_workspace']. Backend's tripwire +
        # the MCP server read AI_TEAM_REPO_ROOT as their scope root.
        workspace = msg.metadata.get("target_repo_workspace") if msg.metadata else None
        if isinstance(workspace, str) and workspace:
            env["AI_TEAM_REPO_ROOT"] = workspace
        env.update(self.mcp_env)
        return env
```

- [ ] **Step A2.4: Forward `cwd` from `_invoke_with_retries`**

Edit `agents/_base/agent.py`. Replace `_invoke_with_retries`:

```python
    async def _invoke_with_retries(
        self,
        *,
        msg: AgentMessage,
        system_prompt: str,
        user_message: str,
        session_key: str | None = None,
    ) -> LLMResponse:
        env = self._build_env(msg)
        workspace = msg.metadata.get("target_repo_workspace") if msg.metadata else None
        cwd: str | None = workspace if isinstance(workspace, str) and workspace else None
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(3),
            wait=wait_exponential_jitter(initial=1, max=20),
            retry=retry_if_exception_type(LLMTimeoutError),
            reraise=True,
        ):
            with attempt:
                return await self._llm.invoke(
                    system_prompt=system_prompt,
                    user_message=user_message,
                    model=self.model_tier,
                    allowed_tools=self.allowed_tools,
                    disallowed_tools=self.disallowed_tools,
                    session_id=session_key,
                    timeout_s=self.llm_timeout_s,
                    max_turns=self.max_turns,
                    env=env,
                    cwd=cwd,
                )
        raise RuntimeError("unreachable")
```

- [ ] **Step A2.5: Run new tests — expect PASS**

```bash
cd /Users/kirillterskih/ai_team && uv run pytest tests/unit/test_base_agent_workspace_env.py -v
```

Expected: 4 PASS.

- [ ] **Step A2.6: Run existing agent tests for regression**

```bash
cd /Users/kirillterskih/ai_team && uv run pytest tests/unit/test_base_agent.py tests/unit/test_backend_developer_agent.py tests/unit/test_team_lead_agent.py -q
```

Expected: all PASS — when `target_repo_workspace` is absent (existing tests), behavior is unchanged.

- [ ] **Step A2.7: Lint + typecheck**

```bash
cd /Users/kirillterskih/ai_team && uv run ruff check agents/_base/ tests/unit/test_base_agent_workspace_env.py && uv run mypy agents/_base/
```

Expected: clean.

- [ ] **Step A2.8: Commit**

```bash
cd /Users/kirillterskih/ai_team
git add agents/_base/agent.py tests/unit/test_base_agent_workspace_env.py
git commit -m "feat(agents): BaseAgent injects AI_TEAM_REPO_ROOT + cwd from msg.metadata (iter-29c step 2/6)"
```

### Task A3: Dispatcher resolves `target_repo` and stashes workspace metadata

**Files:**
- Modify: `core/dispatcher/dispatcher.py` — `__init__` gains `ai_team_root` kwarg; `_handle_one` resolves before `agent.handle`.
- Create: `tests/unit/test_dispatcher_target_repo_resolution.py`.

- [ ] **Step A3.1: Write failing tests**

Create `tests/unit/test_dispatcher_target_repo_resolution.py`:

```python
"""Dispatcher resolves payload.target_repo into a workspace path. iter-29c."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from core.dispatcher.dispatcher import AgentDispatcher
from core.messaging.schemas import (
    AgentId,
    AgentMessage,
    MessageType,
    Priority,
    TaskAssignmentPayload,
    TaskReportPayload,
    TaskStatus,
)


def _make_dispatcher(ai_team_root: Path) -> AgentDispatcher:
    """Dispatcher with all collaborators stubbed — only exercises the
    new _maybe_resolve_target_repo_workspace path."""
    return AgentDispatcher(
        bus=AsyncMock(),
        feed=AsyncMock(),
        audit=AsyncMock(),
        signer=AsyncMock(),
        agents={},
        ai_team_root=ai_team_root,
    )


def _assignment(*, target_repo: str | None) -> AgentMessage:
    return AgentMessage(
        correlation_id=uuid4(),
        sender=AgentId.USER,
        recipient=AgentId.TEAM_LEAD,
        message_type=MessageType.TASK_ASSIGNMENT,
        priority=Priority.P2,
        payload=TaskAssignmentPayload(
            task_id=uuid4(),
            title="t",
            description="d",
            target_repo=target_repo,
        ),
    )


def _report() -> AgentMessage:
    return AgentMessage(
        correlation_id=uuid4(),
        sender=AgentId.BACKEND_DEVELOPER,
        recipient=AgentId.TEAM_LEAD,
        message_type=MessageType.TASK_REPORT,
        priority=Priority.P2,
        payload=TaskReportPayload(
            task_id=uuid4(),
            status=TaskStatus.DONE,
            progress_pct=100,
            summary="ok",
        ),
    )


@pytest.mark.asyncio
async def test_resolves_and_stashes_workspace_for_assignment_with_target_repo(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()

    fake_repo = AsyncMock()
    fake_repo.ensure_local_clone = AsyncMock(return_value=workspace)

    dispatcher = _make_dispatcher(tmp_path)
    msg = _assignment(target_repo="owner/repo")

    with patch(
        "core.dispatcher.dispatcher.resolve_target_repo",
        return_value=fake_repo,
    ) as mock_resolve:
        await dispatcher._maybe_resolve_target_repo_workspace(msg)

    mock_resolve.assert_called_once_with("owner/repo", ai_team_root=tmp_path)
    assert msg.metadata.get("target_repo_workspace") == str(workspace)


@pytest.mark.asyncio
async def test_skips_resolution_when_payload_target_repo_is_none(tmp_path: Path) -> None:
    dispatcher = _make_dispatcher(tmp_path)
    msg = _assignment(target_repo=None)

    with patch(
        "core.dispatcher.dispatcher.resolve_target_repo",
        side_effect=AssertionError("should not be called"),
    ):
        await dispatcher._maybe_resolve_target_repo_workspace(msg)

    assert "target_repo_workspace" not in msg.metadata


@pytest.mark.asyncio
async def test_skips_resolution_for_non_assignment_messages(tmp_path: Path) -> None:
    dispatcher = _make_dispatcher(tmp_path)
    msg = _report()

    with patch(
        "core.dispatcher.dispatcher.resolve_target_repo",
        side_effect=AssertionError("should not be called"),
    ):
        await dispatcher._maybe_resolve_target_repo_workspace(msg)

    assert "target_repo_workspace" not in msg.metadata


@pytest.mark.asyncio
async def test_resolution_failure_propagates_for_synthesise_catch(tmp_path: Path) -> None:
    """Bad identifier raises; the dispatcher's outer try/except in
    _handle_one will catch and route via _synthesise_failed_report.
    Confirm the exception escapes the resolver helper unchanged."""
    dispatcher = _make_dispatcher(tmp_path)
    msg = _assignment(target_repo="bad-shape")

    with patch(
        "core.dispatcher.dispatcher.resolve_target_repo",
        side_effect=ValueError("unknown target_repo"),
    ), pytest.raises(ValueError, match="unknown target_repo"):
        await dispatcher._maybe_resolve_target_repo_workspace(msg)


@pytest.mark.asyncio
async def test_clone_failure_propagates_for_synthesise_catch(tmp_path: Path) -> None:
    fake_repo = AsyncMock()
    fake_repo.ensure_local_clone = AsyncMock(side_effect=RuntimeError("git clone failed"))

    dispatcher = _make_dispatcher(tmp_path)
    msg = _assignment(target_repo="owner/repo")

    with patch(
        "core.dispatcher.dispatcher.resolve_target_repo",
        return_value=fake_repo,
    ), pytest.raises(RuntimeError, match="git clone failed"):
        await dispatcher._maybe_resolve_target_repo_workspace(msg)
```

- [ ] **Step A3.2: Run tests — expect FAIL**

```bash
cd /Users/kirillterskih/ai_team && uv run pytest tests/unit/test_dispatcher_target_repo_resolution.py -v
```

Expected: 5 fails — `unexpected keyword argument 'ai_team_root'` or missing `_maybe_resolve_target_repo_workspace`.

- [ ] **Step A3.3: Wire the resolver into the dispatcher**

Edit `core/dispatcher/dispatcher.py`:

(a) Add imports near the top, after `from core.security.hmac_signer import HMACSigner, InvalidSignatureError`:

```python
from pathlib import Path

from core.target_repo.registry import resolve_target_repo
```

(b) Below `_log = structlog.get_logger(__name__)`, add the module-level default:

```python
_AI_TEAM_ROOT_DEFAULT = Path(__file__).resolve().parents[2]
```

(c) Add the `ai_team_root` kwarg to `AgentDispatcher.__init__`. After the existing `task_state: TaskStateReducer | None = None,` parameter, add:

```python
        ai_team_root: Path | None = None,
```

And store it in the body after `self._task_state = task_state`:

```python
        self._ai_team_root = ai_team_root or _AI_TEAM_ROOT_DEFAULT
```

(d) Add the resolver method just below `_handle_one` (above `_maybe_record_task_state`):

```python
    async def _maybe_resolve_target_repo_workspace(self, msg: AgentMessage) -> None:
        """Resolve payload.target_repo and stash workspace path on
        msg.metadata['target_repo_workspace'] for BaseAgent to read.

        No-op when:
        - msg is not a TaskAssignment;
        - payload.target_repo is None (self-hosting path).

        Raises whatever `resolve_target_repo` or `ensure_local_clone`
        raises (ValueError, GitCommandError, etc.). `_handle_one`'s
        outer try/except catches and synthesises a FAILED report via
        the existing iter-5 substrate.
        """
        if not isinstance(msg.payload, TaskAssignmentPayload):
            return
        identifier = msg.payload.target_repo
        if not identifier:
            return
        repo = resolve_target_repo(identifier, ai_team_root=self._ai_team_root)
        workspace = await repo.ensure_local_clone()
        msg.metadata["target_repo_workspace"] = str(workspace)
```

(e) Call the resolver in `_handle_one` inside the existing try/except that wraps `agent.handle(msg)`. Find:

```python
            outputs: list[AgentMessage] = []
            with agent_message_processing_duration.labels(
                agent=agent.role.value, message_type=msg.message_type.value
            ).time():
                try:
                    outputs = await agent.handle(msg)
                except Exception as exc:
```

Replace with:

```python
            outputs: list[AgentMessage] = []
            with agent_message_processing_duration.labels(
                agent=agent.role.value, message_type=msg.message_type.value
            ).time():
                try:
                    # iter-29c: resolve payload.target_repo into a
                    # workspace path and stash on msg.metadata so
                    # BaseAgent injects AI_TEAM_REPO_ROOT + cwd. Failures
                    # fall through to the existing _synthesise_failed_report.
                    await self._maybe_resolve_target_repo_workspace(msg)
                    outputs = await agent.handle(msg)
                except Exception as exc:
```

- [ ] **Step A3.4: Run new tests — expect PASS**

```bash
cd /Users/kirillterskih/ai_team && uv run pytest tests/unit/test_dispatcher_target_repo_resolution.py -v
```

Expected: 5 PASS.

- [ ] **Step A3.5: Run existing dispatcher tests for regression**

```bash
cd /Users/kirillterskih/ai_team && uv run pytest tests/unit/test_dispatcher.py tests/unit/test_dispatcher_hold_queue.py -v
```

Expected: all PASS — `ai_team_root` defaults via module-level constant; existing tests don't pass `target_repo`, so the new branch is a no-op.

- [ ] **Step A3.6: Lint + typecheck**

```bash
cd /Users/kirillterskih/ai_team && uv run ruff check core/dispatcher/dispatcher.py tests/unit/test_dispatcher_target_repo_resolution.py && uv run mypy core/dispatcher/
```

Expected: clean.

- [ ] **Step A3.7: Commit**

```bash
cd /Users/kirillterskih/ai_team
git add core/dispatcher/dispatcher.py tests/unit/test_dispatcher_target_repo_resolution.py
git commit -m "feat(dispatcher): resolve target_repo + stash workspace on msg.metadata (iter-29c step 3/6)"
```

### Task A4: Verify `ai_team_root` default resolves correctly

The dispatcher's module-relative default already resolves to the ai_team repo root for the API process. No production-code wiring change required for Phase A. This task only verifies.

- [ ] **Step A4.1: Verify default**

```bash
cd /Users/kirillterskih/ai_team
uv run python -c "from core.dispatcher.dispatcher import _AI_TEAM_ROOT_DEFAULT; print(_AI_TEAM_ROOT_DEFAULT); assert (_AI_TEAM_ROOT_DEFAULT / 'pyproject.toml').is_file(), 'wrong root'"
```

Expected: prints `/Users/kirillterskih/ai_team`; assertion holds. If it fails, the `parents[N]` math needs adjusting in `_AI_TEAM_ROOT_DEFAULT`.

No commit — verification only.

### Task A5: Integration test — end-to-end cross-repo dispatch with mocked LLM

**Files:**
- Create: `tests/integration/test_cross_repo_dispatch_e2e.py`.

- [ ] **Step A5.1: Write the integration test**

Create `tests/integration/test_cross_repo_dispatch_e2e.py`:

```python
"""End-to-end: TaskAssignment(target_repo=...) → dispatcher → BaseAgent →
recording LLM. iter-29c.

@pytest.mark.integration — stays out of the default unit run.
Pre-clones into tmp_path workspace (NOT ~/.ai_team/workspaces/).
Skips if `gh auth status` fails.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from agents._base import BaseAgent
from core.dispatcher.dispatcher import AgentDispatcher
from core.llm.base import LLMResponse, TokensUsage
from core.messaging.schemas import (
    AgentId,
    AgentMessage,
    MessageType,
    Priority,
    TaskAssignmentPayload,
)


def _gh_authed() -> bool:
    try:
        return subprocess.run(["gh", "auth", "status"], capture_output=True).returncode == 0
    except FileNotFoundError:
        return False


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not _gh_authed(), reason="requires `gh auth login`"),
    pytest.mark.skipif(shutil.which("git") is None, reason="requires git"),
]


class _RecordingLLM:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def invoke(self, **kwargs: Any) -> LLMResponse:
        self.calls.append(kwargs)
        return LLMResponse(
            text="ok",
            session_id="s",
            tokens=TokensUsage(input=0, output=0, model="mock"),
            duration_ms=0,
        )

    async def reset_session(self, session_id: str) -> None:
        return None


class _DummyAgent(BaseAgent):
    role = AgentId.BACKEND_DEVELOPER
    system_prompt_path = Path("/dev/null")
    allowed_tools = ()

    def build_outputs(self, response, incoming):  # type: ignore[no-untyped-def]
        return []

    def system_prompt(self) -> str:
        return "system"


@pytest.mark.asyncio
async def test_cross_repo_dispatch_threads_workspace_to_llm(tmp_path: Path) -> None:
    """Submit a TaskAssignment(target_repo=...) and confirm the
    dispatcher + BaseAgent threaded workspace cwd + AI_TEAM_REPO_ROOT
    down to the recording LLM."""
    from core.target_repo.github import GitHubTargetRepo

    # Pre-clone into tmp_path/workspaces/ to avoid touching ~/.ai_team/.
    workspaces = tmp_path / "workspaces"
    workspaces.mkdir()
    repo = GitHubTargetRepo(
        "girlsmakemedrink/telegram-tech-publisher", workspaces_dir=workspaces
    )
    workspace = await repo.ensure_local_clone()
    assert (workspace / ".git").is_dir()

    llm = _RecordingLLM()
    agent = _DummyAgent(llm=llm)

    dispatcher = AgentDispatcher(
        bus=AsyncMock(),
        feed=AsyncMock(),
        audit=AsyncMock(),
        signer=AsyncMock(),
        agents={AgentId.BACKEND_DEVELOPER: agent},
        ai_team_root=tmp_path,
    )

    msg = AgentMessage(
        correlation_id=uuid4(),
        sender=AgentId.USER,
        recipient=AgentId.BACKEND_DEVELOPER,
        message_type=MessageType.TASK_ASSIGNMENT,
        priority=Priority.P2,
        payload=TaskAssignmentPayload(
            task_id=uuid4(),
            title="probe",
            description="any",
            target_repo="girlsmakemedrink/telegram-tech-publisher",
        ),
    )

    # Stub the registry to return our pre-cloned repo so the test
    # doesn't re-clone under ~/.ai_team/.
    with patch(
        "core.dispatcher.dispatcher.resolve_target_repo",
        return_value=repo,
    ):
        await dispatcher._maybe_resolve_target_repo_workspace(msg)
        await agent._invoke_with_retries(
            msg=msg, system_prompt="sp", user_message="um"
        )

    assert len(llm.calls) == 1
    call = llm.calls[0]
    assert call["cwd"] == str(workspace)
    assert call["env"]["AI_TEAM_REPO_ROOT"] == str(workspace)
```

- [ ] **Step A5.2: Run integration test locally**

```bash
cd /Users/kirillterskih/ai_team && uv run pytest tests/integration/test_cross_repo_dispatch_e2e.py -v -m integration
```

Expected: 1 PASS (or SKIP if `gh auth status` fails — flag in PR body if skipped).

- [ ] **Step A5.3: Commit**

```bash
cd /Users/kirillterskih/ai_team
git add tests/integration/test_cross_repo_dispatch_e2e.py
git commit -m "test(iter-29c): integration test for cross-repo dispatch end-to-end (step 4/6)"
```

### Task A6: Smoke script + Makefile target

**Files:**
- Create: `scripts/smoke_cross_repo_dispatch.sh`.
- Modify: `Makefile`.

- [ ] **Step A6.1: Write the smoke script**

Create `scripts/smoke_cross_repo_dispatch.sh`:

```bash
#!/usr/bin/env bash
# iter-29c smoke: dispatcher → BaseAgent → recording LLM, against
# girlsmakemedrink/telegram-tech-publisher. Confirms the workspace
# path threads to cwd + AI_TEAM_REPO_ROOT. Real `claude -p` NOT
# invoked. Real `ensure_local_clone` IS invoked against
# ~/.ai_team/workspaces/.

set -euo pipefail

cd "$(dirname "$0")/.."

if ! gh auth status >/dev/null 2>&1; then
  echo "ERROR: gh auth status failed. Run 'gh auth login' first." >&2
  exit 1
fi

uv run python - <<'PY'
import asyncio
from pathlib import Path
from uuid import uuid4
from unittest.mock import AsyncMock

from agents._base import BaseAgent
from core.dispatcher.dispatcher import AgentDispatcher
from core.llm.base import LLMResponse, TokensUsage
from core.messaging.schemas import (
    AgentId, AgentMessage, MessageType, Priority, TaskAssignmentPayload,
)


class _RecordingLLM:
    def __init__(self):
        self.calls = []

    async def invoke(self, **kwargs):
        self.calls.append(kwargs)
        return LLMResponse(
            text='ok', session_id='s',
            tokens=TokensUsage(input=0, output=0, model='mock'),
            duration_ms=0,
        )

    async def reset_session(self, session_id):
        return None


class _DummyAgent(BaseAgent):
    role = AgentId.BACKEND_DEVELOPER
    system_prompt_path = Path('/dev/null')
    allowed_tools = ()
    def build_outputs(self, response, incoming): return []
    def system_prompt(self): return 'system'


async def main():
    llm = _RecordingLLM()
    agent = _DummyAgent(llm=llm)
    dispatcher = AgentDispatcher(
        bus=AsyncMock(), feed=AsyncMock(), audit=AsyncMock(), signer=AsyncMock(),
        agents={AgentId.BACKEND_DEVELOPER: agent},
    )
    msg = AgentMessage(
        correlation_id=uuid4(),
        sender=AgentId.USER,
        recipient=AgentId.BACKEND_DEVELOPER,
        message_type=MessageType.TASK_ASSIGNMENT,
        priority=Priority.P2,
        payload=TaskAssignmentPayload(
            task_id=uuid4(), title='probe', description='d',
            target_repo='girlsmakemedrink/telegram-tech-publisher',
        ),
    )
    await dispatcher._maybe_resolve_target_repo_workspace(msg)
    workspace = msg.metadata.get('target_repo_workspace', '<missing>')
    print(f'resolved workspace: {workspace}')
    await agent._invoke_with_retries(msg=msg, system_prompt='sp', user_message='um')
    call = llm.calls[0]
    print(f"llm.invoke cwd: {call['cwd']}")
    print(f"llm.invoke env.AI_TEAM_REPO_ROOT: {call['env'].get('AI_TEAM_REPO_ROOT')}")
    assert call['cwd'] == workspace, f"cwd mismatch: {call['cwd']!r} != {workspace!r}"
    assert call['env'].get('AI_TEAM_REPO_ROOT') == workspace, 'env mismatch'
    print('SMOKE OK')


asyncio.run(main())
PY
```

- [ ] **Step A6.2: Make it executable**

```bash
chmod +x /Users/kirillterskih/ai_team/scripts/smoke_cross_repo_dispatch.sh
```

- [ ] **Step A6.3: Add Makefile target**

Edit `Makefile`. Add (next to `smoke-github-target-repo`):

```makefile
smoke-cross-repo-dispatch:
	@bash scripts/smoke_cross_repo_dispatch.sh
```

If the file has a `make help` listing, add `smoke-cross-repo-dispatch` to it.

- [ ] **Step A6.4: Run the smoke locally**

```bash
cd /Users/kirillterskih/ai_team && make smoke-cross-repo-dispatch
```

Expected: prints `resolved workspace: /Users/<owner>/.ai_team/workspaces/girlsmakemedrink--telegram-tech-publisher`, two matching `cwd` + `AI_TEAM_REPO_ROOT` lines, and `SMOKE OK`. If the workspace isn't already cloned, `ensure_local_clone` clones it on first run (~10 s).

- [ ] **Step A6.5: Commit**

```bash
cd /Users/kirillterskih/ai_team
git add scripts/smoke_cross_repo_dispatch.sh Makefile
git commit -m "feat(iter-29c): smoke + Makefile target for cross-repo dispatch (step 5/6)"
```

### Task A7: Open PR 1, watch CI, merge

- [ ] **Step A7.1: Run full unit suite for regression check**

```bash
cd /Users/kirillterskih/ai_team && uv run pytest tests/unit/ -q
```

Expected: all PASS — no regressions to the existing baseline. Note baseline pass count for the PR body.

- [ ] **Step A7.2: Push + open PR 1**

```bash
cd /Users/kirillterskih/ai_team
git push -u origin feat/iter-29c-cross-repo-plumbing
gh pr create --title "feat(iter-29c): cross-repo plumbing — dispatcher resolves target_repo, BaseAgent threads cwd + AI_TEAM_REPO_ROOT" --body "$(cat <<'EOF'
## Summary

Closes the iter-28 hole: when a `TaskAssignment` carries
`payload.target_repo="<owner>/<repo>"`, the dispatcher resolves it via
`resolve_target_repo`, ensures the workspace is cloned, and stashes
the path on `msg.metadata['target_repo_workspace']`. `BaseAgent` reads
that key, injects `AI_TEAM_REPO_ROOT=<workspace>` into the subprocess
env, and forwards `cwd=<workspace>` to `LLMClient.invoke`.
`ClaudeCodeHeadlessClient` forwards `cwd` to
`asyncio.create_subprocess_exec`.

Mocked-LLM-only — the real `claude -p` chain against the product repo
is iter-29b. No new envelope fields, no agent prompt changes, no
schema bumps.

## What changed

- `core/llm/base.py` — `LLMClient` Protocol gains `cwd: str | None = None`.
- `core/llm/claude_code_headless.py` — forwards `cwd` to `_spawn_once`
  → `create_subprocess_exec`.
- `core/llm/mock.py` + `core/llm/agent_sdk_stub.py` — Protocol stubs
  accept `cwd`. Mock records it on `self._calls`.
- `agents/_base/agent.py` — `_build_env` adds `AI_TEAM_REPO_ROOT` from
  `msg.metadata['target_repo_workspace']`; `_invoke_with_retries`
  passes `cwd`.
- `core/dispatcher/dispatcher.py` — `__init__` gains `ai_team_root`
  kwarg (default = module-relative `parents[2]`). `_handle_one`
  calls `_maybe_resolve_target_repo_workspace` before `agent.handle`.
  Resolution failures route through the existing
  `_synthesise_failed_report` substrate.
- `tests/unit/test_claude_code_headless_cwd.py`,
  `tests/unit/test_base_agent_workspace_env.py`,
  `tests/unit/test_dispatcher_target_repo_resolution.py` — new units.
- `tests/integration/test_cross_repo_dispatch_e2e.py` — opt-in integration.
- `scripts/smoke_cross_repo_dispatch.sh` + `Makefile` target.

## Smoke evidence

\`\`\`
$ make smoke-cross-repo-dispatch
resolved workspace: /Users/<owner>/.ai_team/workspaces/girlsmakemedrink--telegram-tech-publisher
llm.invoke cwd: /Users/<owner>/.ai_team/workspaces/girlsmakemedrink--telegram-tech-publisher
llm.invoke env.AI_TEAM_REPO_ROOT: /Users/<owner>/.ai_team/workspaces/girlsmakemedrink--telegram-tech-publisher
SMOKE OK
\`\`\`

## Test plan

- [x] 11 new unit tests pass (2 cwd + 4 env + 5 resolution)
- [x] Existing unit suite — no regressions
- [x] Integration test passes locally (gated by gh auth)
- [x] Smoke prints SMOKE OK
- [x] ruff + mypy clean
- [ ] CI green
- [ ] Squash-merge when green

## Out of scope

- TL re-decompose depth cap — Phase B (PR 2).
- iter-29c wrap — Phase C (PR 3).
- Real claude -p against the product repo — iter-29b.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step A7.3: Watch CI; squash-merge when green**

```bash
gh pr checks <PR#>
gh pr merge <PR#> --squash --delete-branch
git checkout main && git pull --ff-only
```

---

## Phase B — TL re-decompose depth cap (PR 2) (~1-2 h)

End state of Phase B: when Backend's 1500-char tripwire fires repeatedly within one correlation, TL stops re-decomposing after the second self-assignment and emits `TASK_REPORT(FAILED)` with a clear cap-exceeded summary. Backend's behavior is unchanged.

### Task B1: In-process depth counter + cap branch in `TeamLeadAgent`

**Files:**
- Modify: `agents/team_lead/agent.py` — `MAX_REDECOMPOSE_DEPTH` constant, instance counter, cap branch in `_re_decompose_on_too_large`.
- Create: `tests/unit/test_team_lead_redecompose_depth_cap.py`.

- [ ] **Step B1.1: Branch from main**

```bash
cd /Users/kirillterskih/ai_team
git checkout main && git pull --ff-only
git checkout -b feat/iter-29c-redecompose-depth-cap
```

- [ ] **Step B1.2: Write failing tests**

Create `tests/unit/test_team_lead_redecompose_depth_cap.py`:

```python
"""TL re-decompose depth cap. iter-29c."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import uuid4

import pytest

from agents.team_lead import TeamLeadAgent
from agents.team_lead.agent import MAX_REDECOMPOSE_DEPTH
from core.messaging.schemas import (
    AgentId,
    AgentMessage,
    MessageType,
    Priority,
    TaskAssignmentPayload,
    TaskReportPayload,
    TaskStatus,
)

if TYPE_CHECKING:
    from uuid import UUID

    from core.llm.base import LLMResponse


class _StubLLM:
    async def invoke(self, **kwargs: object) -> "LLMResponse":  # pragma: no cover
        raise AssertionError("TL must not call LLM in re-decompose dispatch")

    async def reset_session(self, session_id: str) -> None:
        return None


def _blocked_too_large(*, correlation_id: "UUID | None" = None) -> AgentMessage:
    return AgentMessage(
        correlation_id=correlation_id or uuid4(),
        sender=AgentId.BACKEND_DEVELOPER,
        recipient=AgentId.TEAM_LEAD,
        message_type=MessageType.TASK_REPORT,
        priority=Priority.P2,
        payload=TaskReportPayload(
            task_id=uuid4(),
            status=TaskStatus.BLOCKED,
            progress_pct=0,
            summary="Scope pre-flight: task too large: description 2000 chars > 1500 threshold",
            blocked_on="task_too_large",
        ),
    )


@pytest.mark.asyncio
async def test_depth_zero_re_decomposes_as_before() -> None:
    """Regression guard: first BLOCKED(task_too_large) still produces
    a TL→TL self-assignment."""
    agent = TeamLeadAgent(llm=_StubLLM())
    outputs = await agent.handle(_blocked_too_large())

    assert len(outputs) == 1
    out = outputs[0]
    assert out.message_type == MessageType.TASK_ASSIGNMENT
    assert out.recipient == AgentId.TEAM_LEAD
    assert isinstance(out.payload, TaskAssignmentPayload)


@pytest.mark.asyncio
async def test_depth_at_cap_emits_failed_report() -> None:
    """After MAX_REDECOMPOSE_DEPTH successful re-decomposes within one
    correlation, the next BLOCKED(task_too_large) emits FAILED instead
    of another self-assignment."""
    agent = TeamLeadAgent(llm=_StubLLM())
    cid = uuid4()

    # First MAX_REDECOMPOSE_DEPTH re-decomposes succeed.
    for _ in range(MAX_REDECOMPOSE_DEPTH):
        out = await agent.handle(_blocked_too_large(correlation_id=cid))
        assert out[0].message_type == MessageType.TASK_ASSIGNMENT

    # Next hit on the same correlation must trip the cap.
    outputs = await agent.handle(_blocked_too_large(correlation_id=cid))

    assert len(outputs) == 1
    out = outputs[0]
    assert out.message_type == MessageType.TASK_REPORT
    payload = out.payload
    assert isinstance(payload, TaskReportPayload)
    assert payload.status == TaskStatus.FAILED
    assert "re-decompose" in payload.summary.lower()
    assert str(MAX_REDECOMPOSE_DEPTH) in payload.summary


@pytest.mark.asyncio
async def test_cap_isolated_per_correlation() -> None:
    """Two unrelated correlations don't share the counter."""
    agent = TeamLeadAgent(llm=_StubLLM())
    c1, c2 = uuid4(), uuid4()

    # Exhaust c1's quota.
    for _ in range(MAX_REDECOMPOSE_DEPTH):
        await agent.handle(_blocked_too_large(correlation_id=c1))
    cap_hit = await agent.handle(_blocked_too_large(correlation_id=c1))
    assert cap_hit[0].message_type == MessageType.TASK_REPORT

    # c2 still gets its first re-decompose.
    out = await agent.handle(_blocked_too_large(correlation_id=c2))
    assert out[0].message_type == MessageType.TASK_ASSIGNMENT


@pytest.mark.asyncio
async def test_cap_exceeded_summary_mentions_threshold() -> None:
    agent = TeamLeadAgent(llm=_StubLLM())
    cid = uuid4()
    for _ in range(MAX_REDECOMPOSE_DEPTH):
        await agent.handle(_blocked_too_large(correlation_id=cid))
    outputs = await agent.handle(_blocked_too_large(correlation_id=cid))

    payload = outputs[0].payload
    assert isinstance(payload, TaskReportPayload)
    assert "cap" in payload.summary.lower()
    assert str(MAX_REDECOMPOSE_DEPTH) in payload.summary
```

- [ ] **Step B1.3: Run tests — expect FAIL**

```bash
cd /Users/kirillterskih/ai_team && uv run pytest tests/unit/test_team_lead_redecompose_depth_cap.py -v
```

Expected: 4 fails — `ImportError: cannot import name 'MAX_REDECOMPOSE_DEPTH'`, plus cap branch missing.

- [ ] **Step B1.4: Add `MAX_REDECOMPOSE_DEPTH` constant**

Edit `agents/team_lead/agent.py`. Add near the top after the `_SCOPE_PREFLIGHT_SUMMARY_PREFIX` line:

```python
# iter-29c: cap TL self-targeted re-decompose chains so Backend's
# 1500-char tripwire can't drive a runaway. Counted per correlation_id
# on the TeamLeadAgent instance — see iter_29c.md Phase B.
MAX_REDECOMPOSE_DEPTH = 2
```

- [ ] **Step B1.5: Add `LLMClient` to TYPE_CHECKING imports**

Edit `agents/team_lead/agent.py`. Find:

```python
if TYPE_CHECKING:
    from uuid import UUID

    from core.llm.base import LLMResponse
```

Replace with:

```python
if TYPE_CHECKING:
    from uuid import UUID

    from core.llm.base import LLMClient, LLMResponse
```

- [ ] **Step B1.6: Add `__init__` with the in-process counter**

Edit `agents/team_lead/agent.py`. Insert before `build_outputs` (just after the `llm_timeout_s: ClassVar[int] = 300` line):

```python
    def __init__(self, *, llm: "LLMClient") -> None:
        super().__init__(llm=llm)
        # iter-29c: per-correlation re-decompose counter. Bumped each
        # time `_re_decompose_on_too_large` emits a TL→TL self-assignment;
        # cleared on cap-exceeded FAILED emit. Bounded by the number of
        # live correlations in flight (small in practice — one entry per
        # in-flight tripwire chain).
        self._redecompose_depth: dict["UUID", int] = {}
```

- [ ] **Step B1.7: Rewrite `_re_decompose_on_too_large` with the cap branch**

Edit `agents/team_lead/agent.py`. Replace the existing `_re_decompose_on_too_large` body:

```python
    def _re_decompose_on_too_large(self, msg: AgentMessage) -> list[AgentMessage]:
        """iter-21: self-targeted task_assignment that triggers a TL re-decomp.

        Backend's tripwire echoes the original task description (first
        800 chars) into the BLOCKED summary; we forward that into the
        new task_assignment. TL's standard handle() runs the
        decomposition LLM and emits smaller Backend subtasks.

        Anti-loop:
        - Existing: refuse if the BLOCKED summary already carries the
          'auto-routed already' marker.
        - iter-29c: cap re-decompose chain at MAX_REDECOMPOSE_DEPTH per
          correlation_id. On overflow, emit TASK_REPORT(FAILED) so the
          cascade-drops substrate fans out dependents.
        """
        assert isinstance(msg.payload, TaskReportPayload)
        summary = msg.payload.summary
        if _ALREADY_ROUTED_MARKER in summary.lower():
            self._log.info(
                "tl.task_too_large_anti_loop_refused",
                sender=msg.sender.value,
                correlation_id=str(msg.correlation_id),
            )
            return []

        # iter-29c: depth-cap check. depth = number of re-decompose
        # self-assignments already emitted for this correlation.
        depth = self._redecompose_depth.get(msg.correlation_id, 0)
        if depth >= MAX_REDECOMPOSE_DEPTH:
            self._log.warning(
                "tl.task_too_large_cap_exceeded",
                sender=msg.sender.value,
                correlation_id=str(msg.correlation_id),
                depth=depth,
                cap=MAX_REDECOMPOSE_DEPTH,
            )
            self._redecompose_depth.pop(msg.correlation_id, None)
            cap_summary = (
                f"re-decompose depth cap ({MAX_REDECOMPOSE_DEPTH}) exceeded. "
                f"Backend's tripwire fired {depth + 1}x within this "
                f"correlation. Last BLOCKED summary: {summary[:300]}"
            )[:2_000]
            return [
                AgentMessage(
                    correlation_id=msg.correlation_id,
                    sender=AgentId.TEAM_LEAD,
                    recipient=AgentId.USER,
                    message_type=MessageType.TASK_REPORT,
                    priority=Priority.P1,
                    payload=TaskReportPayload(
                        task_id=msg.payload.task_id,
                        status=TaskStatus.FAILED,
                        progress_pct=0,
                        summary=cap_summary,
                    ),
                )
            ]

        self._log.info(
            "tl.task_too_large_re_decompose",
            sender=msg.sender.value,
            correlation_id=str(msg.correlation_id),
            depth=depth,
        )
        self._redecompose_depth[msg.correlation_id] = depth + 1

        description = (
            f"[{_AUTO_ROUTED_MARKER} from {msg.sender.value}] "
            f"{msg.sender.value} reported BLOCKED(task_too_large). "
            "Re-decompose the original work into 2-3 smaller subtasks "
            "of <=100 LOC each (or fewer if that's still too large), "
            "and dispatch them to backend_developer with explicit "
            "depends_on slugs where needed. Backend's original BLOCKED "
            f"report follows:\n\n{summary}"
        )[:10_000]
        # iter-29a fix: reuse the BLOCKED Backend task_id as the
        # re-decompose anchor. The downstream children TL emits will
        # carry this as their parent_task_id; that row is already in
        # the `tasks` table (Backend was running it), so the FK
        # constraint on inserts holds.
        return [
            AgentMessage(
                correlation_id=msg.correlation_id,
                sender=AgentId.TEAM_LEAD,
                recipient=AgentId.TEAM_LEAD,
                message_type=MessageType.TASK_ASSIGNMENT,
                priority=msg.priority,
                payload=TaskAssignmentPayload(
                    task_id=msg.payload.task_id,
                    title=f"Re-decompose: {summary[:80]}",
                    description=description,
                ),
                metadata={"redecompose_depth": depth + 1},
            )
        ]
```

The `metadata={"redecompose_depth": depth + 1}` stamp is informational (audit-visible) — the in-process counter is the authoritative load-bearing state.

- [ ] **Step B1.8: Run new tests — expect PASS**

```bash
cd /Users/kirillterskih/ai_team && uv run pytest tests/unit/test_team_lead_redecompose_depth_cap.py -v
```

Expected: 4 PASS.

- [ ] **Step B1.9: Run existing TL tests for regression**

```bash
cd /Users/kirillterskih/ai_team && uv run pytest tests/unit/test_team_lead_agent.py tests/unit/test_team_lead_brainstorm_decomposition.py tests/unit/test_team_lead_validate_decomposition.py -q
```

Expected: all PASS — first re-decompose still emits self-assignment; cap is additive.

- [ ] **Step B1.10: Lint + typecheck**

```bash
cd /Users/kirillterskih/ai_team && uv run ruff check agents/team_lead/ tests/unit/test_team_lead_redecompose_depth_cap.py && uv run mypy agents/team_lead/
```

Expected: clean.

- [ ] **Step B1.11: Commit**

```bash
cd /Users/kirillterskih/ai_team
git add agents/team_lead/agent.py tests/unit/test_team_lead_redecompose_depth_cap.py
git commit -m "feat(team_lead): cap re-decompose chain at MAX_REDECOMPOSE_DEPTH=2 (iter-29c step 6/6)"
```

### Task B2: Open PR 2, watch CI, merge

- [ ] **Step B2.1: Push + open PR**

```bash
cd /Users/kirillterskih/ai_team
git push -u origin feat/iter-29c-redecompose-depth-cap
gh pr create --title "feat(iter-29c): cap TL re-decompose chain at depth 2" --body "$(cat <<'EOF'
## Summary

Adds a per-correlation re-decompose counter on `TeamLeadAgent`. When
Backend's 1500-char tripwire fires for the (MAX_REDECOMPOSE_DEPTH+1)th
time within the same correlation, TL emits `TASK_REPORT(FAILED)`
instead of another self-targeted re-decompose. Counter is in-process
state on the agent instance; cleared on cap-exceeded emit; bounded by
live correlation cardinality.

Single-file change to `agents/team_lead/agent.py`. Backend behavior
unchanged. New `MAX_REDECOMPOSE_DEPTH = 2` constant exposed for tests.

Surfaced live during iter-29a chain dispatch (correlation \`82e6dd62\`,
2026-05-22) hitting runaway re-decompose loops once PR #47's FK fix
unblocked the dispatcher. PR 1 of iter-29c routes \`cwd\` correctly so
the tripwire no longer false-positives on legitimate product-repo
files; this PR caps the truly-too-large case as a backstop.

## What changed

- \`agents/team_lead/agent.py\` — \`MAX_REDECOMPOSE_DEPTH\` constant,
  \`__init__\` adds \`_redecompose_depth: dict[UUID, int]\`, and
  \`_re_decompose_on_too_large\` checks/bumps it before emitting.
- \`tests/unit/test_team_lead_redecompose_depth_cap.py\` — 4 new units.

## Test plan

- [x] 4 new unit tests pass
- [x] Existing TL unit tests — no regressions
- [x] ruff + mypy clean
- [ ] CI green
- [ ] Squash-merge when green

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step B2.2: Watch CI, squash-merge when green**

```bash
gh pr checks <PR#>
gh pr merge <PR#> --squash --delete-branch
git checkout main && git pull --ff-only
```

---

## Phase C — iter-29c wrap (PR 3) (~1 h)

End state of Phase C: CLAUDE.md reflects iter-29c shipped; retro + handoff committed so the next session knows what iter-29c proved and what iter-29b should pick up.

### Task C1: CLAUDE.md updates

**Files:**
- Modify: `CLAUDE.md`.

- [ ] **Step C1.1: Branch from main**

```bash
cd /Users/kirillterskih/ai_team
git checkout main && git pull --ff-only
git checkout -b docs/iter-29c-wrap
```

- [ ] **Step C1.2: Update "Current phase" paragraph**

Edit `CLAUDE.md`. Append to the iter-28 paragraph in the "Current phase" section:

> **iter-29c (2026-05-NN, cross-repo plumbing shipped):** dispatcher resolves `payload.target_repo`, ensures workspace clone, and stashes the path on `msg.metadata["target_repo_workspace"]`. `BaseAgent._build_env` injects `AI_TEAM_REPO_ROOT=<workspace>`; `_invoke_with_retries` forwards `cwd=<workspace>` to `LLMClient.invoke`. `TeamLeadAgent` caps its re-decompose chain at `MAX_REDECOMPOSE_DEPTH = 2` per correlation_id to prevent Backend-tripwire-driven runaways. End state: ready for iter-29b to dispatch the agent chain (TL → Architect → Backend → QA) against `girlsmakemedrink/telegram-tech-publisher` end-to-end.

- [ ] **Step C1.3: Add a cross-repo dispatch line under "Operating principles"**

Edit `CLAUDE.md`. In the "Operating principles" section, after the existing iter-27 "branch BEFORE first commit" reminder, add:

> - **Cross-repo tasks run with cwd = workspace.** When a `TaskAssignment` carries `payload.target_repo="<owner>/<repo>"`, the dispatcher resolves to `~/.ai_team/workspaces/<owner>--<repo>/` and the agent's `claude -p` subprocess runs in that cwd with `AI_TEAM_REPO_ROOT` populated. Self-hosting tasks (no `target_repo`) keep their current behavior — `cwd` inherits the dispatcher's cwd. Added in iter-29c PR 1.

### Task C2: Write `iter_29c_retro.md`

**Files:**
- Create: `docs/iterations/iter_29c_retro.md`.

- [ ] **Step C2.1: Draft the retro**

Create `docs/iterations/iter_29c_retro.md` with sections matching `iter_28_retro.md`'s structure:

- **Outcome.** What shipped (link PRs 1/2/3); what's now possible (iter-29b real-LLM chain dispatch); what stays deferred to iter-29b (real `claude -p` against the product repo; MCP propagation of `AI_TEAM_REPO_ROOT` through the second-level subprocess).
- **What went well.**
  - Three-PR slicing landed independently — PR 1 and PR 2 are orthogonal and could land in either order.
  - In-process counter design (single-file scope) simpler than the spec's wire-encoded depth (Backend echo) and equally load-bearing.
  - Mocked-LLM smoke proved the dispatch path without burning any subscription quota.
- **What was harder than expected.** Capture any of:
  - `_AI_TEAM_ROOT_DEFAULT` parents-depth math gotcha (Task A4.1).
  - Pydantic `metadata` direct-mutation concerns relative to the HMAC audit chain.
  - mypy strictness on the new `cwd: str | None` plumb-through.
  - Test fixtures that were noisier than expected (integration test pre-clone latency in CI).
- **Lessons for iter-29b.**
  - The first real `claude -p` dispatch against the product repo will reveal the next gap (likely MCP-server related, since iter-29c only exercises non-MCP env injection).
  - Watch whether `AI_TEAM_REPO_ROOT` propagation into the MCP subprocess survives across the second nested subprocess. Backend's tripwire path is the canary.
  - The 1500-char tripwire is still the threshold — depth cap doesn't relax it. If iter-29b sees the cap hit on legitimate work, revisit `_MAX_DESCRIPTION_CHARS` itself.
- **Action items for iter-29b.** Numbered, concrete (file paths + PR numbers).

### Task C3: Write `iter_29c_handoff.md`

**Files:**
- Create: `docs/iterations/iter_29c_handoff.md`.

- [ ] **Step C3.1: Draft the handoff**

Create `docs/iterations/iter_29c_handoff.md` matching `iter_28_handoff.md`'s structure:

- **Where we are.** iter-29c shipped (link PRs). Cross-repo dispatch end-to-end mocked-LLM-proven. TL re-decompose chain bounded.
- **iter-29b priorities** ordered:
  1. **(STRATEGIC TOP)** First real-LLM `claude -p` chain against the product repo. Use a tiny, low-blast-radius task (README typo fix or a single-file doc edit). Validates TL decomposition → Architect spec → Backend file edit → QA → owner approval gate → `GitHubTargetRepo.open_pr` → owner merge.
  2. **(P2)** MCP-server propagation of `AI_TEAM_REPO_ROOT` — iter-29c smoke confirms env reaches BaseAgent, but doesn't exercise the MCP startup chain. If iter-29b's first real run trips, fix it here.
  3. **(P2)** Backend `_MAX_DESCRIPTION_CHARS = 1500` threshold review — if iter-29b sees the depth cap hit on tasks the owner judges legitimate, widen or replace the heuristic.
  4. **(Carry-overs ≥5)** unchanged (HoldQueue Postgres persistence, BaseAgent refactor, dispatcher per-role parallelism).
- **Inherited decisions.**
  - Workspace metadata key: `msg.metadata["target_repo_workspace"]`.
  - Default `ai_team_root` in dispatcher = module-relative `parents[2]`. API doesn't pass it explicitly.
  - In-process re-decompose counter on `TeamLeadAgent`. Wire-encoded depth on metadata is informational only.
  - `MAX_REDECOMPOSE_DEPTH = 2` (allows two re-decomposes before giving up).
- **Ready-to-paste prompt for iter-29b.** A short prompt the owner can paste to kick off iter-29b in a fresh session.

### Task C4: Open PR 3, owner approves, merge

- [ ] **Step C4.1: Commit + push + open PR**

```bash
cd /Users/kirillterskih/ai_team
git add CLAUDE.md docs/iterations/iter_29c_retro.md docs/iterations/iter_29c_handoff.md
git commit -m "docs(iter-29c): wrap — CLAUDE.md pointer + retro + handoff"
git push -u origin docs/iter-29c-wrap
gh pr create --title "docs(iter-29c): wrap iter-29c — CLAUDE.md + retro + handoff to iter-29b" --body "Closes iter-29c. Cross-repo execution path closed: dispatcher resolves target_repo, BaseAgent injects AI_TEAM_REPO_ROOT + cwd, TL caps re-decompose chain at depth 2. iter-29b queues the first real-LLM chain dispatch against the product repo."
```

- [ ] **Step C4.2: Owner reviews; squash-merge**

```bash
gh pr checks <PR#>
gh pr merge <PR#> --squash --delete-branch
git checkout main && git pull --ff-only
```

---

## iter-29c Done Criteria

iter-29c is **done** when all of the following are true:

- [ ] `core/llm/base.py` LLMClient Protocol has `cwd: str | None = None`.
- [ ] `core/llm/claude_code_headless.py` forwards `cwd` to `create_subprocess_exec`.
- [ ] `core/llm/mock.py` + `core/llm/agent_sdk_stub.py` accept `cwd`.
- [ ] `agents/_base/agent.py` injects `AI_TEAM_REPO_ROOT` and forwards `cwd` when `msg.metadata["target_repo_workspace"]` is present.
- [ ] `core/dispatcher/dispatcher.py` resolves `payload.target_repo` and stashes workspace metadata before `agent.handle`.
- [ ] `agents/team_lead/agent.py` caps re-decompose chain at `MAX_REDECOMPOSE_DEPTH = 2` per correlation.
- [ ] 11 new unit tests pass (2 cwd + 4 env + 5 resolution).
- [ ] 4 new TL depth-cap unit tests pass.
- [ ] `make test-unit` clean; no regressions on existing baseline.
- [ ] `tests/integration/test_cross_repo_dispatch_e2e.py` passes locally (gated by `gh auth`).
- [ ] `make smoke-cross-repo-dispatch` prints `SMOKE OK` against the live workspace.
- [ ] CI green on all 3 PRs.
- [ ] CLAUDE.md mentions iter-29c shipped.
- [ ] `docs/iterations/iter_29c_retro.md` + `iter_29c_handoff.md` exist.
- [ ] Owner approves the Phase C wrap PR.

---

## Cost / time estimate

- **Claude usage:** ~$0 of subscription quota — pure local Python + git + subprocess testing. No `claude -p` calls.
- **Wall-clock:** ~5-7 dev hours total (Phase A ~3-4 h, Phase B ~1-2 h, Phase C ~1 h).
- **Owner manual actions:** (a) one PR review on the Phase C wrap (PRs 1 and 2 are self-mergeable on green CI per the standing dev-PR autonomy rule); (b) optional spot-check of the smoke output in PR 1's body.

---

## Owner action items inherited from iter-29a + iter-28 carry-overs

None for iter-29c proper. iter-29c does not add new owner-side actions. Existing carry-overs (HoldQueue Postgres persistence, BaseAgent refactor, dispatcher per-role parallelism, etc.) remain deferred per [[project-ai-team]].

---

## Risks specific to iter-29c

1. **`_AI_TEAM_ROOT_DEFAULT` parents-depth math wrong.** If `Path(__file__).resolve().parents[2]` lands somewhere unexpected (e.g., on a packaged install), resolution fails. Mitigation: Task A4.1 verifies before any commit depends on it. If wrong, adjust the constant — only impacts the default since tests inject explicitly.
2. **`msg.metadata` direct mutation interacts with the audit chain.** The HMAC signature is verified before mutation, and outbound messages are re-signed, so in-place edits to incoming metadata don't break the audit. Existing iter-7+ hold-queue / cascade-drop code reads metadata; A3.5 regression sweep catches collateral.
3. **In-process re-decompose counter resets on dispatcher restart.** A malicious or unlucky chain could keep re-decomposing across restarts. In practice the counter is bounded by correlation cardinality and retry-blocked semantics already assume restart-tolerance. Escalate to wire-encoded depth only if iter-29b sees the problem.
4. **Workspace clone fails on hosts without SSH config or `gh auth`.** Same risk surface as iter-28; surfaced by `ensure_local_clone` raising → routed through `_synthesise_failed_report`. Owner sees the failure in feed, fixes auth, retries. No silent failure path.
5. **MCP server doesn't pick up `AI_TEAM_REPO_ROOT` updates per-call.** The MCP subprocess starts at `claude -p` spawn time and reads its env fresh; iter-29c's smoke verifies the env value at the LLM-invoke boundary, but doesn't exercise the MCP startup chain. If the MCP server caches the path module-level (e.g., from `os.environ` at import time), iter-29c is incomplete. iter-29b's first real run will surface any deeper coupling.

---

## Success criteria

1. `make test-unit` passes including the four new test files.
2. `make test-integration` passes including `test_cross_repo_dispatch_e2e.py`.
3. `make smoke-cross-repo-dispatch` prints a workspace path matching `~/.ai_team/workspaces/girlsmakemedrink--telegram-tech-publisher` and confirms cwd + env match.
4. A manual dispatch of a `TaskAssignment(target_repo="girlsmakemedrink/telegram-tech-publisher")` against a MockLLM completes without raising and the MockLLM records the expected workspace cwd.
5. TL receives `MAX_REDECOMPOSE_DEPTH+1` synthetic BLOCKED reports and emits FAILED instead of re-decomposing (covered by the depth-cap unit tests).
6. No regressions: existing self-hosting dispatch (no `target_repo` on payload) still works — current dispatcher unit tests stay green unchanged.

The iter-29b session will exercise the same path with real `claude -p` against the product repo; iter-29c stops at "plumbing proven to work mocked".
