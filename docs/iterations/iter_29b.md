# Iter-29b Design Spec — first real `claude -p` chain (MVP gate)

> **Status:** design spec. iter-29b is primarily operational, not implementation — the path was wired by iter-29c (PRs #51/#52/#53). This iter exercises it end-to-end for the first time.
>
> **For agentic workers (later):** execution is owner-driven (kick off chain, observe, approve gates, recover). Code changes land only if a real bug surfaces during the run.

**Goal:** Ship the ai_team framework's first autonomously-produced PR to a real product repo. End state: a PR opened by ai_team's TL→Architect→Backend→QA chain on `girlsmakemedrink/telegram-tech-publisher`, owner-reviewed and merged. **This is the MVP gate** — once this loop closes once, the framework moves from "infrastructure complete, never proven" to "good enough to use."

**Architecture:** Operational, not implementation. iter-29c (squash-merged 2026-05-22) wired the cross-repo execution path. iter-29b runs real `claude -p` against that path for the first time. No new code surfaces unless a runtime bug requires it.

**Tech Stack:** Existing — Python 3.13, asyncio subprocess for `claude -p`, FastAPI+Postgres dispatcher, Click CLI, gh CLI for PR ops. Subscription-only LLM (never `ANTHROPIC_API_KEY`).

**Source spec inputs:**
- `CLAUDE.md` — cross-repo operating principle (iter-29c).
- `docs/iterations/iter_28.md` + `iter_28_handoff.md` — `GitHubTargetRepo` + workspace path convention.
- `docs/iterations/iter_29c.md` + `iter_29c_retro.md` + `iter_29c_handoff.md` — plumbing spec, lessons, strategic priorities.
- `apps/cli/main.py:207-252` — `ai-team submit` signature.
- `core/dispatcher/dispatcher.py`, `agents/_base/agent.py`, `core/llm/claude_code_headless.py` — code surfaces exercised.

---

## Strategic decision: the first task

**Add a `## Smoke pipelines` section to `telegram-tech-publisher/README.md`** — recommended by `iter_29c_handoff.md` (carried over from the iter-28 handoff).

Why this task:
- **Docs-only edit, single file, single repo.** No CI risk in the product repo.
- **Full pipeline exercise.** TL decomposes → Architect specs the README change → Backend edits the file (with `cwd = workspace`, `AI_TEAM_REPO_ROOT` populated) → QA verifies → owner approval gate → `GitHubTargetRepo.open_pr` → owner merge.
- **Low quota cost** (~$0.50–$1.50 subscription quota across all four agent turns).
- **Trivially reversible** if the content is wrong: revert the merge in the product repo.
- **Real signal on every layer** — cwd plumbing, env propagation, MCP toolchain, depth cap behaviour, owner-gate UX.

Exact submitted task description (kept short to test TL decomposition behaviour, not stress it):

```
Add a "## Smoke pipelines" section to README.md.

The section should document the two smoke pipelines run from the product
repo's Makefile (or equivalent) — one bullet per pipeline, with a short
description of what each one verifies. If the product repo has no
Makefile-level smoke pipelines yet, document the candidate pipelines that
SHOULD exist (CI on push to main, manual integration probe).

No code changes outside README.md.
```

---

## Pre-flight (all satisfied 2026-05-22)

- [x] `make smoke-cross-repo-dispatch` → `SMOKE OK`
- [x] `make smoke-github-target-repo` → workspace clean (`branch=main dirty=False`), lint passed
- [x] `gh auth status` → `girlsmakemedrink` token valid (scopes: gist, read:org, repo, workflow)
- [x] Working tree clean (PR #54 landed dev-dep pins on `main` as `72bc45c`)
- [x] MCP env propagation audit clean — `Context.from_env()` is per-stdio-loop entry (`tools/mcp_servers/ai_team_repo/__main__.py:182`, `tools/mcp_servers/ai_team_tasks/__main__.py:103`), not module-import. Per-claude-p-invocation lifetime confirmed via comments at `tools/mcp_servers/ai_team_repo/handlers.py:32-38`.

---

## Run plan

Six steps, owner-driven:

1. **Start dispatcher locally.** `make dev-up` (or equivalent). Confirm health endpoint responds.
2. **Submit task.**
   ```
   ai-team submit \
     --title "Document smoke pipelines in product README" \
     --description "$(cat docs/iterations/iter_29b_task_description.txt)" \
     --target-repo girlsmakemedrink/telegram-tech-publisher
   ```
   Capture `task_id` + `correlation_id` from output.
3. **Stream feed.** `ai-team feed --follow` in a second pane. Watch agent transitions.
4. **Owner-approve gates.** `ai-team list-pending` → `ai-team approve <review_id>` for each `pending_review`. Expected gates: at least one per agent role (TL decomp, Architect spec, Backend impl, QA verification).
5. **Observe PR URL** in the final TL/Backend `TASK_REPORT`. The PR opens on `girlsmakemedrink/telegram-tech-publisher`, head branch matches `agent/backend_developer/<slug>`.
6. **Owner reviews PR on GitHub.** If content is sensible: merge. If not: leave open, write up findings in retro, decide whether to iterate within iter-29b or close and ship as-is.

---

## Observability checklist (capture for retro)

For each agent turn, record:
- Role (team_lead / architect / backend_developer / qa)
- `correlation_id` (shared across the chain)
- Wall-clock duration
- Input task description length (chars) — watch for 1500-char tripwire
- Output `task_report.summary` (verbatim quote)
- Subscription quota consumed (approximate, from claude-code session)

At chain level:
- TL decomposition shape (how many subtasks, what role assignments)
- Total turns across the chain
- Any re-decompose events (`redecompose_depth` in audit log)
- Final PR URL + diff size (LOC, files)
- Owner gate latency (time from `pending_review` → approve)

---

## Success criteria

**Binary:** a PR opened on `girlsmakemedrink/telegram-tech-publisher` by the ai_team chain, with a README diff that adds a `## Smoke pipelines` section. **The framework shipped the PR.**

Content quality is **not** an MVP criterion. The owner can reject the README copy and we still call this MVP success — the framework's job is shipping the PR; content polish is iter-29d+'s concern (agent prompt iteration).

If the chain crashes mid-run, file the failure as an iter-29b implementation task (in this spec doc as Addendum A), fix it, and retry. Up to three retries before declaring iter-29b a partial-success and writing retro.

---

## Non-goals

- **No production deployment** of the dispatcher. Local-only.
- **No new agents or new framework features.** Single-task exercise.
- **No content-quality bar.** Any sensible README addition that lands as a PR counts.
- **No multi-task batches.** One task, one chain.
- **No CI changes** in either repo.
- **No prompt iteration mid-run.** If an agent prompt is wrong, capture the symptom, finish or abort, then iterate prompts in iter-29d+.
- **No retroactive iter-29c reopenings.** Bugs surfaced during iter-29b that trace to iter-29c plumbing land as new iter-29b implementation tasks (not as iter-29c amendments).
- **No `_MAX_DESCRIPTION_CHARS` retune** unless the depth cap fires on a decomposition the owner judges legitimate.

---

## Risk register

| Risk | Likelihood | Mitigation |
|---|---|---|
| TL emits structurally-invalid `TaskAssignment` envelope | Low | iter-29c unit + integration tests cover this; if it surfaces live, file as iter-29b impl task |
| Backend trips 1500-char tripwire on legitimate decomposition | Medium | depth cap (iter-29c) emits `TASK_REPORT(FAILED, P1)` at depth 2; widen `_MAX_DESCRIPTION_CHARS` only if owner judges decomp legitimate (handoff P3) |
| MCP env not reaching second-level subprocess (Backend's git/gh calls) | Low (audit clean) | MCP servers re-read `AI_TEAM_REPO_ROOT` per-startup; backstop is `ai_team_repo.status` probe mid-run |
| Quota burn from prompt-iteration loops | Medium | Cap experiment at 3 retries of any single agent stage; abort + retro |
| `GitHubTargetRepo.open_pr` races/fails | Low (iter-28 smoke green) | Manual `gh pr create` from workspace as fallback |
| Agent emits destructive shell command | Very low | `ai_team_repo.run_shell` has command-class allowlist (no raw bash); `create_branch` enforces `agent/<role>/<slug>` ref shape |
| `pending_review` UI confusing / owner rejects wrong review | Low | iter-29a exercised the gate; reviews are summarised in `ai-team list-pending` table |
| Workspace contains uncommitted state from a prior run | Medium | Run `git status` in workspace pre-flight; manually `git clean -fd && git checkout main` if dirty (NEVER destructive without owner consent — autonomy preference) |

---

## Quota budget

Hard ceiling: **$3.00** of subscription quota across the full run (4 agent turns × ~$0.50 expected + 2× retry headroom). Abort if exceeded.

Cap signal: claude-code session reports near `$3.00` or owner observes >6 minutes of agent turns without progress to `pending_review`.

---

## Inherited decisions (do not contradict without revisiting)

All iter-19..29c decisions hold. iter-29b adds:

- **First-real-LLM run is operational, not implementation.** Code changes only on demonstrated bugs.
- **Single task per run.** No batched submissions in iter-29b.
- **Owner-gate every report.** No auto-approve flag enabled.
- **Subscription LLM only.** `ANTHROPIC_API_KEY` is never set; `claude -p` runs via the owner's Claude Code subscription.
- **MVP definition.** A real PR opened by the ai_team chain on a real product repo. Content quality and reliability come after.

---

## Addendum A: implementation tasks (populated only if bugs surface)

Empty at spec time. Each entry, if added, is a follow-up issue with: symptom, agent role + correlation_id, observed vs. expected, fix scope.

---

## Out-of-spec carry-overs (deferred to iter-29d+)

Unchanged from iter-29c handoff §5:

- HoldQueue Postgres persistence
- `pytest-rerunfailures` plugin pin
- `audit_writer` restricted Postgres role
- Hash-chain alert job
- TL decomposition transactional insert
- `BaseAgent.handle()` template-method refactor
- `mark_task_done` / `update_task_status` real impls
- Substrate-level `--allowed-tools ""` fix
