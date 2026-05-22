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

## Open questions for the implementation plan

These are deferrable to writing-plans but flagged here so they don't surprise the implementer:

1. **Where does `ai_team_root` get sourced from in the dispatcher?** New kwarg on `AgentDispatcher.__init__` is cleanest; default could read from a known constant (e.g. `core.target_repo.self_bootstrap._REPO_ROOT` if one exists) for the production wiring in `apps/api/main.py`. Wiring change is one line in the API lifespan.
2. **TL re-decompose code shape.** Memory describes the function as `_re_decompose_on_too_large`, fixed by PR #47. Implementation plan should read the current TL agent.py to confirm the actual function name and exact emit shape (uuid4 anchor, etc.) before touching it.
3. **Integration test's clone fixture.** If `~/.ai_team/workspaces/girlsmakemedrink--telegram-tech-publisher/` isn't present in CI, the integration test should either skip-if-absent or pre-clone in `conftest.py`. Pre-clone is heavier but more reliable.
4. **Does `ensure_local_clone` need to be re-called per dispatch, or once-per-process cached?** Per-dispatch is simpler (the method is already idempotent), and `git fetch` is fast. Cache only if profiling shows it's expensive.

---

## Owner action items inherited from iter-29a + iter-28 carry-overs

None for iter-29c proper. iter-29c does not add new owner-side actions. Existing carry-overs (HoldQueue Postgres persistence, BaseAgent refactor, dispatcher per-role parallelism, etc.) remain deferred per [[project-ai-team]].

---

## Success criteria

1. `make test-unit` passes including the four new test files.
2. `make test-integration` passes including `test_cross_repo_dispatch_e2e.py`.
3. `make smoke-cross-repo-dispatch` prints a workspace path matching `~/.ai_team/workspaces/girlsmakemedrink--telegram-tech-publisher` and confirms cwd + env match.
4. A manual dispatch of a `TaskAssignment(target_repo="girlsmakemedrink/telegram-tech-publisher")` against a MockLLM completes without raising and the MockLLM records the expected workspace cwd.
5. TL receives a synthetic depth-2 BLOCKED report and emits FAILED instead of re-decomposing (covered by the depth-cap unit tests).
6. No regressions: existing self-hosting dispatch (no `target_repo` on payload) still works — current dispatcher unit tests stay green unchanged.

The iter-29b session will exercise the same path with real `claude -p` against the product repo; iter-29c stops at "plumbing proven to work mocked".
