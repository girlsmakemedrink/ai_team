# Iteration 28 handoff

> Read **after** `CLAUDE.md`, `docs/iterations/iter_28.md`, and
> `docs/iterations/iter_28_retro.md`.

## Where we are (2026-05-22 EOD, iter-28 merged)

🛠️ **`GitHubTargetRepo` shipped.** `core/target_repo/github.py` is the
third concrete `TargetRepo` impl per ADR-009 — closes a carry-over
deferred since iter-2. Inherits from `SelfBootstrapTargetRepo`; only
`__init__` (identifier parse + workspace path computation) and
`ensure_local_clone` (clone-or-fetch via `gh repo clone`) are new.
Registry's `NotImplementedError` branch is gone.

🧪 **Live smoke is green.** `make smoke-github-target-repo` clones
`girlsmakemedrink/telegram-tech-publisher` into
`~/.ai_team/workspaces/girlsmakemedrink--telegram-tech-publisher/` and
runs status + ruff + `uv run pytest -q` against it via the abstraction.
All three pass. Integration test (`@pytest.mark.integration`, gated on
`gh auth status`) verifies the same path in a tmp workspace.

🔌 **Agent invocations against the new repo are unblocked but unused.**
Any `TaskAssignmentPayload.target_repo = "girlsmakemedrink/<slug>"` will
resolve correctly — but no agent chain has actually been pointed at the
new repo yet. iter-29 is where that lands.

📚 **Doc footprint:**
- `core/target_repo/github.py` — 86 lines (impl).
- `tests/unit/test_target_repo_github.py` — 11 unit tests.
- `tests/integration/test_target_repo_github_clone.py` — 1 integration test.
- `scripts/smoke_github_target_repo.sh` — live smoke (Makefile `smoke-github-target-repo`).
- `CLAUDE.md` — iter-28 paragraph + "branch BEFORE first commit" reminder added.

## iter-29 priorities (in order)

### 1. (STRATEGIC TOP) First agent task against the product repo

This is the iter-29 fork. The infrastructure is ready; pick the first
real exercise of agents-against-external-repo before opening
`iter_29.md`.

**Concrete proposal**: TL decomposes "add a `## Smoke pipelines` section
to `telegram-tech-publisher/README.md`" into a Backend → QA chain that
opens a PR via `GitHubTargetRepo.open_pr`. Owner approves the
`pending_review`, then merges the PR in the product repo.

Why this candidate:
- **Low blast radius**: docs-only edit to a single file. No code, no
  CI risk, no surprises if the agents botch it.
- **Full pipeline coverage**: exercises every link — `target_repo`
  resolution → `ensure_local_clone` → `checkout` (forbidden-branch
  guards) → `stage_and_commit` (path-scope) → `push` → `open_pr` (gh
  CLI) → owner manual approve.
- **Addresses the iter-27 P2 deferred item**: README "Run smoke locally"
  section that the owner asked for during iter-27 smoke setup.
- **Tiny cost**: ~1 TL turn + 1 Backend turn + 1 QA turn = ~$0.50-1.00
  of subscription quota.

Alternative if owner prefers: skip the README task, jump straight to
"LLM voice drafter" (product ADR-0004). That's a higher-value but
higher-risk first exercise — the failure mode is harder to debug
because it's a code change inside multi-file scope. Recommend the
README task first to derisk the cross-repo pipeline.

### 2. (P2) Promote `_run` to a public module-level helper

`core/target_repo/github.py` imports `_run` from
`core/target_repo/self_bootstrap.py`. The leading underscore is a
correctness/style smell — any fourth `TargetRepo` impl would inherit
the same coupling. Move to `core/target_repo/_subprocess.py` (or
similar) and re-export. Cheap (~30 min), reduces future drift.

### 3. (P2) Investigate dispatcher cascade test flake

`tests/integration/test_dispatcher_e2e.py::test_transitive_drops_cascade_through_hold_queue`
failed once in CI during iter-28 PR #42 with
`'in_progress' != 'failed'`. Passed on local re-run + CI retry. Same
test was flagged in iter-26b carry-overs (HoldQueue Postgres
persistence + 2-pending_reviews-per-QA-turn anomaly cluster). Either
stabilize the race or quarantine it with a skip + ticket; don't keep
absorbing the re-run cost on every iter.

### 4. (P3) Workspace GC policy

ADR-009 mentions "GC workspaces unused > 14 days". Not needed with one
external repo; revisit when a second product repo accumulates. Manual
`rm -rf ~/.ai_team/workspaces/<owner>--<slug>` is fine for now.

### 5. (Carry-overs ≥4, unchanged from iter-27)

All still pending — none blocked iter-28 and none block iter-29.

- HoldQueue persistence (Postgres).
- `pytest-rerunfailures` plugin pin.
- TL auto-hop investigation.
- `audit_writer` restricted Postgres role.
- Hash-chain alert job.
- TL decomposition transactional insert.
- `BaseAgent.handle()` template-method refactor.
- `mark_task_done` / `update_task_status` real impls.
- Substrate-level `--allowed-tools ""` fix.

## Hard constraints (unchanged from iter-27 + new in iter-28)

All iter-4..27 constraints hold. New in iter-28:

- **`GitHubTargetRepo` cloning uses `gh repo clone`**, not raw
  `git clone <ssh_url>`. The owner's gh CLI auth is the single source
  of truth for cross-repo access; no separate SSH key required.
  Subsequent fetches use `git fetch --all` inside the gh-configured
  remote (HTTPS by default).
- **Workspaces under `~/.ai_team/workspaces/<owner>--<repo>/`**. Slug
  uses `--` (double-dash) to encode the `/`. Manual cleanup OK; no
  automated GC yet.
- **Default branch for the product repo is `main`** (no `develop` flow).
  `GitHubTargetRepo(..., default_branch="<other>")` overrides; the
  registry currently passes `default_branch="main"` implicitly via the
  class default.

## What iter-28 specifically did NOT do

See `iter_28_retro.md` "What iter-28 specifically did NOT do" for the
full list. Headlines:

- No agent invocations against the new repo (iter-29).
- No workspace GC.
- No PAT-based auth (gh CLI is the only auth substrate).
- No ADR changes (ADR-009 stands).
- No dispatcher / message-schema / agent code changed.
- No closing of any other iter-26/27 carry-overs.

## Inherited decisions (do not contradict without revisiting)

All iter-19..27 decisions hold. New iter-28 decisions, all owner-approved
implicitly via the iter_28.md plan + Phase B pivot:

- **`GitHubTargetRepo` inherits from `SelfBootstrapTargetRepo`**. No
  GH-specific `commit` / `push` / `open_pr` overrides; the parent's
  forbidden-branch guards + path-scope validation apply unchanged.
- **`gh` CLI is the single auth substrate** for both clone and PR
  creation. Phase A's `git clone <ssh_url>` was pivoted to `gh repo clone`
  during Phase B smoke once `Permission denied (publickey)` surfaced;
  the owner's gh protocol config (https here) determines the actual
  protocol used. See `iter_28_retro.md` "What was harder than expected".
- **Workspaces are owned by `ai_team`, not the user.** The path
  `~/.ai_team/workspaces/` makes the ownership explicit; cross-checkout
  reuse is by design (the workspace persists across `ai_team`
  invocations).
- **`remote_url` is informational**, not auth-bearing. It's set to the
  canonical SSH URL for display, but no subprocess call consumes it for
  authentication (`gh repo clone` uses the gh token; `git push origin`
  uses the gh-configured remote).

## Ready-to-paste prompt for the new session

```
Starting Iteration 29 on the ai_team project.

First, read these in this order:

1. CLAUDE.md (note iter-28 paragraph + "branch BEFORE first commit" reminder)
2. docs/iterations/iter_28.md (the GitHubTargetRepo spec)
3. docs/iterations/iter_28_retro.md (what happened + lessons)
4. docs/iterations/iter_28_handoff.md (this file — iter-29 priorities)

iter-29 priorities (in order):

1. (STRATEGIC TOP) First agent task against the product repo —
   TL → Backend → QA chain that adds a "## Smoke pipelines" section
   to telegram-tech-publisher/README.md, opened via
   `GitHubTargetRepo.open_pr` and approved by owner manually. Validates
   the full cross-repo pipeline at low blast radius.

2. (P2) Promote `_run` from core/target_repo/self_bootstrap.py to a
   public module-level helper (`core/target_repo/_subprocess.py`).
   Reduces coupling for the next `TargetRepo` impl.

3. (P2) Investigate `test_transitive_drops_cascade_through_hold_queue`
   flake (saw one false-failure in iter-28 PR #42; passed on rerun).
   Stabilize or quarantine.

4. (P3) Workspace GC policy — defer until a second product repo lands.

5. (Carry-overs ≥4, unchanged) — see iter_28_handoff.md.

Workflow: plan-before-code. Draft docs/iterations/iter_29.md AFTER
the strategic decision in #1. Surface the plan, then code. Run
validation + PR merges yourself.

Constraints unchanged from iter-27 — see CLAUDE.md gotchas + the
"Hard constraints" section of iter_28_handoff.md. New iter-28
constraints: clone via `gh repo clone` (not SSH);
workspaces under ~/.ai_team/workspaces/<owner>--<repo>/.

When ready, create the iter-29 task list and surface the strategic
decision first.
```
