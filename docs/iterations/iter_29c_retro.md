# Iteration 29c retro

> Read **after** `CLAUDE.md`, `docs/iterations/iter_29c.md`, and
> `docs/iterations/iter_29a_retro.md`.

## Outcome (2026-05-22 EOD)

iter-29c shipped per spec. The cross-repo execution path is now wired
end-to-end (mocked-LLM): a `TaskAssignment` carrying
`payload.target_repo="<owner>/<repo>"` flows through dispatcher
→ `BaseAgent` → `LLMClient.invoke` with workspace `cwd` and
`AI_TEAM_REPO_ROOT` env populated. `TeamLeadAgent` caps its self-targeted
re-decompose chain at `MAX_REDECOMPOSE_DEPTH = 2` per `correlation_id`
to prevent Backend-tripwire-driven runaways.

Three PRs landed on 2026-05-22:

| PR  | Phase | Squash SHA  | What                                                       |
|-----|-------|-------------|------------------------------------------------------------|
| #50 | plan  | `1926a89`   | iter-29c design spec (cross-repo path + depth cap)         |
| #51 | A     | `8015123`   | LLMClient cwd + BaseAgent env injection + dispatcher resolver |
| #52 | B     | `3c8b8b7`   | TL `MAX_REDECOMPOSE_DEPTH=2` per-correlation cap           |

This wrap PR adds the CLAUDE.md pointer, this retro, and the handoff to
iter-29b.

### Verification

- `core/llm/base.py`, `core/llm/claude_code_headless.py`, `core/llm/mock.py`,
  `core/llm/agent_sdk_stub.py` — `LLMClient` Protocol gains
  `cwd: str | None = None`; subprocess client forwards to
  `create_subprocess_exec`.
- `agents/_base/agent.py` — `_build_env` reads
  `msg.metadata["target_repo_workspace"]` and injects
  `AI_TEAM_REPO_ROOT`; `_invoke_with_retries` forwards `cwd`.
- `core/dispatcher/dispatcher.py` — `__init__` gains `ai_team_root`
  kwarg with module-relative default; `_handle_one` calls
  `_maybe_resolve_target_repo_workspace` before `agent.handle`.
- `agents/team_lead/agent.py` — `MAX_REDECOMPOSE_DEPTH = 2`,
  `_redecompose_depth: dict[UUID, int]` instance counter, cap branch
  emits `TASK_REPORT(FAILED, P1)` to USER on overflow.
- 11 new unit tests on Phase A (2 cwd + 4 env + 5 resolution).
- 4 new unit tests on Phase B (depth cap).
- 1 integration test (`test_cross_repo_dispatch_e2e.py`) — real clone of
  `girlsmakemedrink/telegram-tech-publisher` into `tmp_path/workspaces/`,
  gated on `gh auth status`.
- `scripts/smoke_cross_repo_dispatch.sh` + `make smoke-cross-repo-dispatch` —
  live workspace probe, recording LLM. Prints `SMOKE OK`.
- Full unit suite: 554/554 pass, no regressions.

## What went well

- **Subagent-driven workflow held up over 7 implementer dispatches.**
  Each task: fresh implementer subagent + spec compliance reviewer +
  code quality reviewer. Reviewers caught real issues (intermediate
  assertion in A5, `@bash` Makefile inconsistency in A6, counter-cleanup
  semantics in B1) that the implementer self-review missed. Cost was
  ~3x the subagent invocations of a single-pass approach but the
  three-pass catches were genuine.
- **Mocked-LLM smoke proved the dispatch path without burning quota.**
  `make smoke-cross-repo-dispatch` exercises the full
  dispatcher→agent→LLM chain against a real cloned workspace using a
  recording stub. ~0¢ subscription quota consumed across all of
  iter-29c. The real `claude -p` chain is iter-29b's job — the right
  decoupling.
- **Single-file scope on Phase B was a clean win.** The in-process
  `_redecompose_depth: dict[UUID, int]` counter on `TeamLeadAgent` is
  one constant + one instance attr + a 30-line branch in
  `_re_decompose_on_too_large`. No envelope schema changes, no wire
  format, no migration. Easy to reason about, easy to revert. The
  alternative (wire-encoded depth in `msg.metadata`) was discarded
  for good reason.
- **Force-push to feature branches worked smoothly with explicit owner
  consent.** Phase A PR 1 (#51) needed history rewrite for two
  >100-char commit headers; controller asked, owner approved, fix
  landed cleanly via `git filter-branch --msg-filter` (non-interactive,
  no `-i` flag). Pattern is reusable when commitlint catches descriptive
  cleanup-commit titles that overshoot.

## What was harder than expected

- **CI parity is a one-way ratchet — local subset checks miss things.**
  Phase A's CI flagged three issues that local checks missed:
  - **`ruff format --check` ≠ `ruff check`.** Local was running `ruff
    check <files>` (lint). CI also runs `ruff format --check .`
    (whole-tree format). Caught two A3+A5 test files that linted clean
    but weren't `ruff format`-clean. Same gotcha as iter-28 PR #42.
  - **`mypy .` (whole-tree) ≠ `mypy <file>`.** Local was running
    file-scoped mypy. CI runs `mypy .`. The wider scope caught a
    `_Call | None` union-attr error in `test_claude_code_headless_cwd.py`
    that file-scoped mypy let through. Same gotcha as iter-28.
  - **Variable rebinding to incompatible types fails mypy strict.** In
    `test_team_lead_redecompose_depth_cap.py` the implementer's first
    pass reused the name `out` for both `list[AgentMessage]` (in a
    loop) and `AgentMessage` (after the loop). mypy strict refused.
    Fix: rename to `cap_msg = outputs[0]`. CI caught it.
  Lesson: **always run `make lint format-check typecheck` (whole-tree)
  before pushing**. The iter-28 retro called this out; we still ate
  one CI cycle on PR #51 and one on PR #52 by not following through.
- **Commit-message length budget is tight.** commitlint's
  `header-max-length: 100` interacts poorly with the descriptive
  cleanup-commit titles that implementer subagents produce after spec
  + code-quality review. Two A1/A2 cleanup commits overshot (101 and
  106 chars). The fix path is history rewrite + force-push, with
  explicit owner consent — not a routine action. Plan-level mitigation:
  **enforce a ≤90-char target on cleanup commit messages in the
  implementer prompt** (gives 10 chars of headroom for the trailer).
- **Dev-dep carry-overs accumulated quietly through all three PRs.**
  `pyproject.toml + uv.lock` gained `anyio>=4.13.0`, `pytest>=9.0.3`,
  `pytest-asyncio>=1.3.0` during Phase A (an implementer subagent ran
  `uv sync --extra dev` to unblock the testcontainers conftest). The
  changes are orthogonal to cross-repo plumbing and were intentionally
  excluded from PR 51/52 to keep scope clean. They sat unstaged
  through the entire iter and still do. **They need to land separately
  in iter-29b** — flagged in the handoff.
- **The em dash (—) is one character but three bytes.** When checking
  commit-header length locally, `awk '{print length, $0}'` reports
  bytes, not chars. The CI commitlint counts chars. Two of the
  reworded commit subjects had em dashes; under byte counts they read
  as "over"-by-2, under char counts they were comfortably under. Tip:
  use Python's `len()` or a regex-aware shell idiom, not byte-counting
  `awk length()`.

## Lessons for iter-29b

- **First real-LLM dispatch will surface MCP-server gaps.** iter-29c
  smoke verifies the env reaches the LLM-invoke boundary, but the
  smoke does not exercise the MCP startup chain. If MCP loads
  `AI_TEAM_REPO_ROOT` from `os.environ` at import time (module-level),
  it'll cache the dispatcher's process env, not the per-call workspace.
  Backend's tripwire path is the canary — if Backend reads the
  product-repo files but the MCP server still reports ai_team paths,
  that's the gap. Fix it in iter-29b via per-call MCP env passthrough.
- **`_redecompose_depth` counter is in-process state.** Restart resets
  it. Acceptable today (correlations don't survive restart anyway —
  the dispatcher rehydrates from `tasks` table; cardinality is bounded
  by live in-flight chains). Revisit only if iter-29b observes a
  pathological retry-after-restart loop.
- **The 1500-char tripwire is unchanged.** Depth cap doesn't relax it.
  If iter-29b sees the cap hit on tasks the owner judges legitimate,
  the right fix is widening `_MAX_DESCRIPTION_CHARS` in
  `agents/backend_developer/`, not relaxing the cap.
- **Subagent-driven dev workflow scales.** 7 tasks across 3 PRs with
  2-reviewer-per-task gating produced a clean shipping iter. Worth
  reusing for iter-29b's first real-LLM dispatch (where each agent's
  prompt may need iterating).

## Action items

1. **iter-29b P1**: first real `claude -p` chain against
   `girlsmakemedrink/telegram-tech-publisher`. Use a tiny, low-blast
   task (README typo fix or a single-file doc edit). Validates the
   full pipeline: TL decomposition → Architect spec → Backend file
   edit → QA → owner approval → `GitHubTargetRepo.open_pr` → owner
   merge in product repo. Detail in `iter_29c_handoff.md`.
2. **iter-29b P2**: MCP-server propagation of `AI_TEAM_REPO_ROOT` —
   audit `tools/mcp_servers/` for module-level `os.environ` reads;
   ensure per-call env passthrough survives the second nested subprocess.
3. **iter-29b P2**: Backend `_MAX_DESCRIPTION_CHARS = 1500` threshold
   review — if iter-29b sees the depth cap hit on legitimate tasks,
   widen or replace the heuristic.
4. **iter-29b housekeeping**: land the dev-dep carry-overs (`anyio`,
   `pytest`, `pytest-asyncio` pins in `pyproject.toml + uv.lock`)
   as a standalone build-deps PR before any real-LLM work.
5. **iter-29b plan-time mitigation**: target commit headers ≤ 90 chars
   in the implementer prompt; whole-tree `make lint format-check
   typecheck` in every Phase checklist before push. Don't repeat the
   PR 51/52 CI cycles.

## What iter-29c specifically did NOT do (re-stated)

- No real `claude -p` invocation against the product repo (iter-29b).
- No MCP-server env propagation (iter-29b P2).
- No `_MAX_DESCRIPTION_CHARS` retune (deferred pending iter-29b
  observation).
- No envelope schema / ADR / message-type changes.
- No dispatcher per-role parallelism, HoldQueue persistence, BaseAgent
  refactor (still on the iter-26+ carry-over list).
- No wire-encoded re-decompose depth (in-process counter judged
  sufficient; revisit only if restart-loop pathology surfaces).
- No `pyproject.toml + uv.lock` dev-dep pins landed (deliberately
  excluded from all 3 iter-29c PRs to keep scope clean — flagged as
  iter-29b housekeeping).
