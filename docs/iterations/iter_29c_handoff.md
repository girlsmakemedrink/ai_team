# Iteration 29c handoff

> Read **after** `CLAUDE.md`, `docs/iterations/iter_29c.md`, and
> `docs/iterations/iter_29c_retro.md`.

## Where we are (2026-05-22 EOD, iter-29c merged)

🛠️ **Cross-repo execution path shipped (mocked).** When a `TaskAssignment`
carries `payload.target_repo="<owner>/<repo>"`, the dispatcher resolves
to `~/.ai_team/workspaces/<owner>--<repo>/` via
`resolve_target_repo(identifier, ai_team_root=...)`, awaits
`ensure_local_clone()`, and stashes the path on
`msg.metadata["target_repo_workspace"]`. `BaseAgent._build_env` reads
that key and injects `AI_TEAM_REPO_ROOT=<workspace>` into the subprocess
env. `_invoke_with_retries` forwards `cwd=<workspace>` to
`LLMClient.invoke`. `ClaudeCodeHeadlessClient` forwards `cwd` to
`asyncio.create_subprocess_exec`. PR #51 (`8015123`).

🛡️ **TL re-decompose chain bounded.** `TeamLeadAgent` maintains an
in-process `_redecompose_depth: dict[UUID, int]` counter. On the
`(MAX_REDECOMPOSE_DEPTH + 1)`th BLOCKED(task_too_large) for a given
correlation, TL emits `TASK_REPORT(FAILED, P1)` to USER instead of
another self-targeted re-decompose. Backstop for Backend's 1500-char
tripwire. PR #52 (`3c8b8b7`).

🧪 **Plumbing proven mocked, not real.** `tests/integration/test_cross_repo_dispatch_e2e.py`
exercises the dispatcher → BaseAgent → recording-LLM chain against a
real clone of `girlsmakemedrink/telegram-tech-publisher` into a tmp
workspace. `make smoke-cross-repo-dispatch` does the same against the
live `~/.ai_team/workspaces/` clone. **Real `claude -p` against the
product repo is NOT yet run.** That's iter-29b's first move.

📚 **Doc footprint:**
- `core/llm/base.py`, `claude_code_headless.py`, `mock.py`,
  `agent_sdk_stub.py` — `cwd` plumbing through the `LLMClient` Protocol.
- `agents/_base/agent.py` — env + cwd injection from metadata.
- `core/dispatcher/dispatcher.py` — workspace resolver + `ai_team_root`
  kwarg.
- `agents/team_lead/agent.py` — `MAX_REDECOMPOSE_DEPTH`, counter, cap
  branch.
- 15 new unit tests (11 Phase A + 4 Phase B), 1 new integration test,
  1 new smoke script + Makefile target.
- `CLAUDE.md` — iter-29c paragraph + "Cross-repo tasks run with
  `cwd = workspace`" operating principle added.

⚠️ **Dev-dep carry-overs unstaged.** `pyproject.toml + uv.lock` have
pending additions: `anyio>=4.13.0`, `pytest>=9.0.3`,
`pytest-asyncio>=1.3.0`. Added during Phase A locally to unblock
testcontainers conftest loading. Intentionally excluded from PRs 51/52/53
to keep scope clean. **Land these as the first iter-29b PR** (build-deps
only, low review cost).

## iter-29b priorities (in order)

### 1. (STRATEGIC TOP) First real `claude -p` chain against the product repo

The infrastructure is ready. iter-29b's fork is picking the first real
exercise.

**Recommended candidate**: TL decomposes a tiny doc edit on
`telegram-tech-publisher` into a Backend → QA chain that opens a PR via
`GitHubTargetRepo.open_pr`. Owner approves the `pending_review`, then
merges manually in the product repo.

Why this candidate:
- **Low blast radius**: docs-only edit to a single file. No code, no
  CI risk in the product repo.
- **Full pipeline coverage**: TL decomposition (real claude -p, opus
  tier) → Architect spec → Backend file edit (with `cwd = workspace`
  and `AI_TEAM_REPO_ROOT` populated) → QA verification → owner
  approval gate → `GitHubTargetRepo.open_pr` → owner merge.
- **Tiny quota cost**: ~1 TL turn + 1 Architect turn + 1 Backend turn
  + 1 QA turn ≈ $0.50-1.50 of subscription quota.
- **Validates the iter-28 + iter-29c integration**: this is the first
  time the cross-repo path runs end-to-end with a real LLM.

Concrete suggestion: "add a `## Smoke pipelines` section to
`telegram-tech-publisher/README.md`" (the same task the iter-28 handoff
proposed; deferred to iter-29 then iter-29b).

**Pre-flight checks** before kicking off the dispatch:
- `make smoke-cross-repo-dispatch` prints `SMOKE OK` (regression guard
  on the plumbing).
- `make smoke-github-target-repo` prints all-green (iter-28 baseline).
- `gh auth status` shows the owner's token still valid for both repos.

### 2. (P2) MCP-server `AI_TEAM_REPO_ROOT` propagation

iter-29c smoke verifies the env reaches the LLM-invoke boundary, but
does **not** exercise the MCP startup chain. If `tools/mcp_servers/`
modules read `os.environ["AI_TEAM_REPO_ROOT"]` at import time (rather
than per-call), the cached value will be the dispatcher's process env
(usually the ai_team repo root), not the per-task workspace. Backend's
tripwire path is the canary in iter-29b's first real run — if Backend
reads the product-repo files but the MCP-rooted tools still report
ai_team paths, this is the gap.

Audit targets: `tools/mcp_servers/bus/` and `tools/mcp_servers/tasks/`.

### 3. (P2) Backend `_MAX_DESCRIPTION_CHARS` review

If iter-29b's first real chain trips the 1500-char tripwire on tasks
the owner judges legitimate, the right fix is widening the threshold
in `agents/backend_developer/`, not relaxing the depth cap. If it
DOESN'T trip on legitimate work, leave the threshold alone — it's load-
bearing.

### 4. (Housekeeping) Land dev-dep carry-overs

Open a small PR landing `pyproject.toml + uv.lock` additions: `anyio`,
`pytest`, `pytest-asyncio` pins. Build-deps only, no agent or runtime
code. Do this first in iter-29b so the working tree starts clean.

### 5. (Carry-overs ≥4, unchanged)

All still pending — none blocked iter-29c and none block iter-29b's
strategic top. From iter-27/28 carry list:

- HoldQueue persistence (Postgres).
- `pytest-rerunfailures` plugin pin.
- `audit_writer` restricted Postgres role.
- Hash-chain alert job.
- TL decomposition transactional insert.
- `BaseAgent.handle()` template-method refactor.
- `mark_task_done` / `update_task_status` real impls.
- Substrate-level `--allowed-tools ""` fix.

## Hard constraints (unchanged from iter-28/29c)

All iter-4..29a constraints hold. iter-29c-specific:

- **`payload.target_repo` is the trigger.** Self-hosting (no
  `target_repo`) keeps current behavior — `cwd` inherits the
  dispatcher's cwd, no `AI_TEAM_REPO_ROOT` set. Cross-repo path
  activates only when `target_repo` is a non-empty string.
- **Workspace metadata key is `msg.metadata["target_repo_workspace"]`.**
  The dispatcher stashes `str(workspace_path)` here. `BaseAgent` reads
  the same key. Outbound messages do NOT re-emit this key; it's
  inbound-only context. Do not promote to an envelope-level field
  without revisiting the audit chain.
- **`MAX_REDECOMPOSE_DEPTH = 2`.** Allows two re-decomposes before
  giving up. Counter is per-`correlation_id`, in-process, resets on
  dispatcher restart. Cap-exceeded path emits `TASK_REPORT(FAILED, P1)`
  to USER.
- **Resolution failures route through `_synthesise_failed_report`.**
  Both `resolve_target_repo` and `ensure_local_clone` exceptions
  escape the resolver helper unchanged; `_handle_one`'s outer
  try/except catches them and synthesises a FAILED report via the
  iter-5 substrate. No silent swallow.

## What iter-29c specifically did NOT do

See `iter_29c_retro.md` "What iter-29c specifically did NOT do" for the
full list. Headlines:

- No real `claude -p` invocation against the product repo (iter-29b P1).
- No MCP-server env propagation (iter-29b P2).
- No `_MAX_DESCRIPTION_CHARS` change.
- No envelope schema / ADR / message-type changes.
- No wire-encoded re-decompose depth.
- No dev-dep pins landed (iter-29b housekeeping #4).

## Inherited decisions (do not contradict without revisiting)

All iter-19..29a decisions hold. New iter-29c decisions, owner-approved
implicitly via the iter_29c.md plan + Phase reviews:

- **Workspace metadata key**: `msg.metadata["target_repo_workspace"]`.
  String, not `Path`. Dispatcher writes; BaseAgent reads.
- **Dispatcher `ai_team_root` default**: module-relative
  `Path(__file__).resolve().parents[2]`. API doesn't pass it explicitly;
  the constructor falls back to the default. Override only in tests.
- **In-process re-decompose counter** on `TeamLeadAgent`. Wire-encoded
  depth on `msg.metadata["redecompose_depth"]` is informational only
  (audit-visible). The dict is authoritative.
- **`MAX_REDECOMPOSE_DEPTH = 2`**. Two re-decomposes allowed, third hit
  emits FAILED. Bump only if iter-29b shows the cap fires on
  legitimate work AND `_MAX_DESCRIPTION_CHARS` widening alone doesn't
  fix it.
- **Mocked-LLM smoke is the iter-29c stop point.** Real `claude -p`
  against the product repo is intentionally iter-29b. Don't backport
  real-LLM runs into iter-29c retroactively.

## Ready-to-paste prompt for iter-29b

```
Starting Iteration 29b on the ai_team project.

First, read these in this order:

1. CLAUDE.md (note iter-29c paragraph + "Cross-repo tasks run with cwd=workspace" operating principle)
2. docs/iterations/iter_28.md (the GitHubTargetRepo spec — workspace path convention)
3. docs/iterations/iter_29c.md (cross-repo plumbing + depth cap spec)
4. docs/iterations/iter_29c_retro.md (what shipped + lessons from iter-29c CI cycles)
5. docs/iterations/iter_29c_handoff.md (this file — iter-29b priorities)

iter-29b priorities (in order):

1. (STRATEGIC TOP) First real `claude -p` chain against
   girlsmakemedrink/telegram-tech-publisher. Use a tiny, low-blast task
   (recommended: add a "## Smoke pipelines" section to the product
   repo's README). Full pipeline: TL decompose → Architect spec →
   Backend file edit (workspace cwd + AI_TEAM_REPO_ROOT) → QA → owner
   approval gate → GitHubTargetRepo.open_pr → owner merge in product
   repo. ~$0.50-1.50 of subscription quota.

2. (P2) Audit tools/mcp_servers/ for module-level os.environ reads of
   AI_TEAM_REPO_ROOT. The iter-29c smoke verifies env at LLM-invoke,
   but not through MCP startup. Backend's tripwire path is the canary.

3. (P2) Backend _MAX_DESCRIPTION_CHARS=1500 threshold review IF
   iter-29b sees the depth cap fire on legitimate work. If it doesn't,
   leave the threshold alone.

4. (Housekeeping) Land the dev-dep carry-overs first: pyproject.toml +
   uv.lock additions for anyio + pytest + pytest-asyncio pins. Build-
   deps only, low review cost. Get the working tree clean before any
   real-LLM work.

5. (Carry-overs ≥4, unchanged) — see iter_29c_handoff.md.

Workflow: plan-before-code. Draft docs/iterations/iter_29b.md AFTER
the strategic decision in #1 (which exact task to use as the first
real-LLM exercise). Surface the plan, then code.

Run validation + routine PR merges yourself. The full subagent-driven
workflow (implementer + spec reviewer + code quality reviewer per task)
is recommended for iter-29b's agent-prompt-iteration phases; it earned
its keep across iter-29c's 7 tasks.

Pre-flight before the real-LLM dispatch:
- make smoke-cross-repo-dispatch  → SMOKE OK
- make smoke-github-target-repo   → all green
- gh auth status                  → token valid

Constraints unchanged from iter-29c — see CLAUDE.md gotchas + the
"Hard constraints" section of iter_29c_handoff.md. Subscription-only
LLM access (never set ANTHROPIC_API_KEY).

When ready, create the iter-29b task list and surface the strategic
decision first.
```
