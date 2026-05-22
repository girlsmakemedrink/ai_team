# Iter-29d Design Spec — pre-flight bundle for iter-29e multi-role chain

> **Status:** design spec. Three small, related pre-flight items bundled in one PR. No live LLM spend — de-risks iter-29e, which will exercise the multi-role chain on a real product task.
>
> **For agentic workers (later):** this iter is implementation + documentation, not operation. No `claude -p` runs, no product-repo touch.

**Goal:** Land three pre-flight items so iter-29e can submit its multi-role-chain task on a clean substrate, with a documented gate-wiring story, and without re-discovering the `uv sync` dev-extras gotcha.

**Architecture:** One new method on the `TargetRepo` Protocol (`prepare_for_task()`, default no-op), one real implementation in `GitHubTargetRepo`, one dispatcher call site. Plus a write-up of the iter-29b gate-wiring finding and a one-liner in `CLAUDE.md` for the dev-deps install.

**Tech Stack:** Existing — Python 3.13, asyncio subprocess for `git`, pytest + testcontainers for integration. No new deps.

**Source spec inputs:**
- `docs/iterations/iter_29b_retro.md` — Surprise #2 ("no pending_review fired") + the workspace-cleanup follow-up.
- `agents/qa_engineer/agent.py:487` — the claimed-sole `pending_reviews` producer.
- `core/target_repo/base.py` — `TargetRepo` Protocol.
- `core/target_repo/github.py` — `GitHubTargetRepo` to gain `prepare_for_task()`.
- `core/dispatcher/dispatcher.py:208` — `_maybe_resolve_target_repo_workspace`, the call site.
- `core/persistence/task_state.py:182,254` — `task_state.parent_rolled_up*` emit sites, relevant to the audit.

---

## Scope

Three items, one bundle PR:

1. **Workspace cleanup hook** (code) — `TargetRepo.prepare_for_task()`.
2. **Gate wiring audit** (write-up; code only if a real hole surfaces).
3. **Dev-deps doc** (one-liner in `CLAUDE.md` + iter-29e handoff stub).

**Out of scope:**
- The multi-role chain exercise itself (→ iter-29e).
- Rewiring `pending_review` to cover non-QA chain shapes (separate iter if owner decides).
- Cross-repo product-Makefile changes for the dev-deps gotcha (doc only, here).
- Any persistent-cleanup features beyond the per-task hook (no `git clean`, no stale-branch pruning).

---

## Item 1 — Workspace cleanup hook

### Interface

Add `prepare_for_task()` to the `TargetRepo` Protocol (`core/target_repo/base.py`):

- Default implementation: **no-op**. `SelfBootstrapTargetRepo` and `InRepoExampleTargetRepo` inherit the no-op — neither has persistent agent-branch state across runs that needs cleanup.
- `GitHubTargetRepo.prepare_for_task()` is the only real implementation in this iter.

### Behavior in `GitHubTargetRepo`

Called against the workspace at `~/.ai_team/workspaces/<owner>--<repo>`:

1. `git -C <workspace> fetch origin main` — network failure raises `TargetRepoError("failed to fetch origin/main: <stderr>")`.
2. `git -C <workspace> status --porcelain` — if non-empty, raise `TargetRepoError("workspace has uncommitted changes: <files>; refusing to checkout main")`. **No destructive reset.** Agents shouldn't leave dirty state; this is a loud-fail signal for owner intervention.
3. `git -C <workspace> checkout main`.
4. `git -C <workspace> merge --ff-only origin/main` — non-fast-forward raises `TargetRepoError("local main diverged from origin/main; manual intervention required")`. Avoids `reset --hard`; preserves drift for inspection.

### Call site

In `core/dispatcher/dispatcher.py::_maybe_resolve_target_repo_workspace` (around line 208), immediately after `await repo.ensure_local_clone()`:

```python
await repo.ensure_local_clone()
await repo.prepare_for_task()
msg.metadata["target_repo_workspace"] = str(workspace)
```

Failure propagates as a task-level error (caught and recorded in `task_state`), not a dispatcher crash — a transient git failure on one task shouldn't take down the worker.

### Tests

Unit + integration, following the existing GitHubTargetRepo test pattern (local bare-repo fixture, no mocked subprocess calls):

- Clean workspace on a feature branch → ends on `main` at `origin/main`.
- Workspace already on `main`, up to date with origin → no error, no-op outcome.
- Dirty workspace (one staged file, one unstaged) → raises with both filenames in the message.
- Local `main` diverged from `origin/main` (one local commit not on origin) → raises with "diverged" message; workspace state preserved.
- Fetch failure (bad-remote-URL fixture) → raises with git stderr included.
- `SelfBootstrapTargetRepo.prepare_for_task()` → returns without error (no-op exercised).

---

## Item 2 — Gate wiring audit

### Claim under audit

From `agents/qa_engineer/agent.py:487` ("Safety net: write pending_reviews row if LLM forgot to call the tool"): `pending_reviews` rows are written **only** by the QA Engineer agent's safety-net path. If confirmed, iter-29b's missing review row is explained by chain shape (TL → DevOps, no QA), not by a wiring bug.

### Audit method

1. `grep -rn "PendingReview(" agents/ core/` — confirm QA agent is the sole producer call site.
2. Read `core/dispatcher/dispatcher.py::_handle_one` and `core/persistence/task_state.py:182,254` (the `parent_rolled_up*` emit sites) — confirm the dispatcher does not itself write `pending_reviews` on rollup.
3. Read `agents/team_lead/agent.py` decomposition path — confirm TL does not write `pending_reviews`.

### Possible outcomes

- **Confirmed QA-only-by-design.** Write up the finding in this spec's "Findings" addendum (Addendum A below, populated during impl). Add a one-liner to `CLAUDE.md` operating principles: *"pending_reviews are produced by QA Engineer only; chains that skip QA legitimately skip the review record."* Update [[project-ai-team]] memory to retire the "investigate gate wiring" backlog item and record the confirmed design rule. **No code change.**
- **Wiring hole found.** If `pending_reviews` was *supposed* to be produced elsewhere and isn't, scope the smallest fix that closes the hole. If the fix is ≤30 LOC plus tests, include in this bundle. Larger fixes carve out to iter-29e or a new iter, with a stub in iter-29e handoff.

### Acceptance

The findings section is concrete enough that a future Claude session won't re-litigate "is the gate wired?" — it cites file:line for the producer and the non-producer sites, and ends the question.

---

## Item 3 — Dev-deps doc + iter-29e handoff stub

### `CLAUDE.md` change

One line in the operating-principles section (or wherever env setup is anchored):

> Any repo with PEP 621 `[project.optional-dependencies].dev` (ai_team does; product repos may) needs `uv sync --extra dev --all-groups` — `uv sync` alone skips those extras and leaves `respx`, `pre-commit`, etc. uninstalled.

### iter-29e handoff stub

Create `docs/iterations/iter_29e_handoff.md` (stub form, fleshed out when iter-29e is specced) with a "Preflight" section listing:

- The workspace cleanup hook (`TargetRepo.prepare_for_task()`) as an active precondition.
- The dev-deps install incantation.
- A pointer to this iter's findings (gate-wiring audit).

---

## Run plan

Linear, owner-driven (Claude self-drives per autonomy contract):

1. **Audit pass** — run greps + reads from Item 2, populate Addendum A with file:line evidence. This is the cheapest first step and may reveal something that changes the rest of the iter.
2. **TDD the cleanup hook** — write the unit tests against the `TargetRepo` Protocol shape, then add `prepare_for_task()`, then add `GitHubTargetRepo` impl + dispatcher wiring. Integration test last.
3. **Run the full local suite** — `make test` (or equivalent) + `make smoke-github-target-repo` to confirm no regression on the existing happy path.
4. **Docs** — `CLAUDE.md` one-liner, iter-29e handoff stub, retro stub at `iter_29d_retro.md`.
5. **Push branch, open PR, self-merge on green CI.**

---

## Pre-flight

- [x] Working tree clean on `main` at `8faec1e` (iter-29b retro merge).
- [x] Branch `feat/iter-29d-preflight` created off `main`.
- [ ] `make smoke-github-target-repo` green pre-change (baseline; will re-run post-change).
- [ ] `git diff main...HEAD` empty before first impl commit.

---

## Success criteria

**Binary:**
1. `prepare_for_task()` exists on the Protocol with a tested no-op default and a tested `GitHubTargetRepo` implementation, called from the dispatcher.
2. Audit findings are in this spec doc as Addendum A, citing file:line.
3. `CLAUDE.md` carries the dev-deps one-liner.
4. `iter_29e_handoff.md` exists as a stub listing the three preconditions.
5. CI is green; PR is squash-merged into `main`.

**Quota:** $0.00 subscription spend (no `claude -p` runs in this iter).

---

## Non-goals

- **No live LLM run.** This iter is implementation + documentation only.
- **No new agent roles or framework features** beyond the one Protocol method.
- **No destructive workspace cleanup.** Dirty workspaces fail loudly; the owner decides.
- **No `git clean`, no stale-branch pruning** in the hook.
- **No retroactive iter-29b reopenings** — the gate-wiring finding lives here and propagates forward.
- **No cross-repo product PR** for the dev-deps gotcha. Doc only.

---

## Risk register

| Risk | Likelihood | Mitigation |
|---|---|---|
| Audit surfaces a real wiring hole larger than 30 LOC | Low | Carve out to a separate iter; this iter's bundle ships without the fix, with a clear stub for the carve-out |
| `prepare_for_task()` break-by-default on impls that need real behavior later | Low | Default no-op is explicit; future impls override with intent |
| Integration test infra (testcontainers + bare repo) drifts from iter-28 pattern | Low | Match the existing GitHubTargetRepo integration test setup; if it doesn't exist, write the minimal fixture and document inline |
| `merge --ff-only` rejects on a workspace someone manually patched | Low | Loud-fail is the desired behavior; owner intervention is the documented escape hatch |
| `fetch origin main` masks workspace-on-other-remote case | Very low | `GitHubTargetRepo.ensure_local_clone()` already pins `origin` to the product remote; the workspace cannot have a different `origin` without manual intervention |

---

## Quota budget

**$0.00** subscription quota. No `claude -p` invocations in this iter. Static-analysis tools and pytest only.

---

## Inherited decisions (do not contradict without revisiting)

All iter-19..29c decisions hold. iter-29b adds:

- **MVP gate is closed** (2026-05-22) — the framework is past "infrastructure complete, never proven."
- **Single-agent chain is sufficient** to count as a chain run; multi-role still unexercised.
- **AI-agent approval gates are auto-driven** by Claude post-2026-05-23 (autonomy contract).

iter-29d adds:

- **`pending_reviews` producer locus** is QA Engineer (claimed; confirmed in Addendum A). Chains skipping QA legitimately skip the review record.
- **Workspace cleanup is per-task, opt-in via Protocol method.** Default no-op; only `GitHubTargetRepo` implements real cleanup in this iter.
- **No destructive cleanup ever** without explicit owner action.

---

## Addendum A: gate-wiring audit findings

**Verdict: design rule, not a wiring hole.**

`pending_reviews` rows are written exclusively by the QA Engineer agent's safety-net path at `agents/qa_engineer/agent.py:523`. Confirmed via:

- `grep -rn "PendingReview(" agents/ core/` → two hits: `agents/qa_engineer/agent.py:523` (producer) and `core/persistence/models.py:111` (class definition). Single producer site.
- `core/dispatcher/dispatcher.py::_handle_one` (lines 117–206) — no `PendingReview` construction. The dispatcher exclusively handles HMAC-verify → agent dispatch → audit/feed-publish → task-state bookkeeping → bus-publish. No review rows written.
- `core/persistence/task_state.py:182` (`task_state.parent_rolled_up_on_drop`) and `task_state.py:254` (`task_state.parent_rolled_up`) — both are log-emit-only sites on parent Task row status updates. No `PendingReview` construction in the reducer.
- `agents/team_lead/agent.py` → no `PendingReview` import or review-creation call anywhere in the decomposition path. Only two `review`-adjacent occurrences are comment text at lines 225 and 239 (DAG-preview broadcast).

**Implication for iter-29b's "no pending_review fired" surprise.** The TL → DevOps single-agent chain skipped QA, so no producer ran. The missing review is a chain-shape consequence, not a wiring bug.

**Design rule** (added to `CLAUDE.md` in Item 8): `pending_reviews` are produced by QA Engineer only; chains that skip QA legitimately skip the review record.

**No code change in this iter.**

---

## Out-of-spec carry-overs (deferred to iter-29e+)

Unchanged from iter-29c handoff §5 + iter-29b carry-overs:

- HoldQueue Postgres persistence
- `pytest-rerunfailures` plugin pin
- `audit_writer` restricted Postgres role
- Hash-chain alert job
- TL decomposition transactional insert
- `BaseAgent.handle()` template-method refactor
- `mark_task_done` / `update_task_status` real impls
- Substrate-level `--allowed-tools ""` fix
- Multi-role chain exercise (iter-29e's headline task)
- `pending_reviews`-for-non-QA-chains decision (if Addendum A confirms QA-only-by-design, this becomes "explicit design rule; revisit only on owner request")
