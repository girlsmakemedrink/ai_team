# Iter-29b Retro — first real `claude -p` chain (MVP gate)

**Status:** MVP gate **CLOSED** 2026-05-22 21:07 UTC.

**Result:** [telegram-tech-publisher PR #6](https://github.com/girlsmakemedrink/telegram-tech-publisher/pull/6) — opened by the ai_team chain, CI green, mergeable. Owner reviews on GitHub.

## Numbers

| Metric | Value |
|---|---|
| Submit → done | 1m 56s (21:05:10 → 21:07:06 UTC) |
| LLM invocations | 2 (TL Opus, DevOps Sonnet) |
| Quota burn | **$0.16** (vs $3.00 ceiling) |
| Tokens out | 5,498 (1,344 TL + 4,154 DevOps) |
| Agent chain depth | 1 (TL → DevOps, no further decomposition) |
| Pending reviews fired | **0** (see Surprise #2 below) |
| Wall clock incl. CI | ~2m 30s (PR opened ≈21:07:10, CI green by 21:07:23) |
| Diff | 5 lines added in `README.md`, 0 deletions |

## What worked

- **Cross-repo workspace plumbing** (iter-29c). Workspace at `~/.ai_team/workspaces/girlsmakemedrink--telegram-tech-publisher` was reused cleanly. `AI_TEAM_REPO_ROOT` propagated. DevOps ran with `cwd=workspace` and committed against the product repo's git history.
- **Branch shape.** Agent branch `agent/devops/smoke-pipelines-readme` matches the `agent/<role>/<slug>` allowlist.
- **Conventional commit.** DevOps emitted `docs: add Smoke pipelines section to README` — commitlint passed on product-repo CI.
- **Content quality.** DevOps correctly identified the *existing* `smoke-github` / `smoke-telegram` Make targets (not the candidate-only fallback path the spec described) and wrote accurate one-line descriptions. Not the MVP bar — but good signal that the prompt + tool surface are coherent.

## Surprises

**1. TL routed to DevOps, not Backend/Architect/QA.** Spec called the path "TL → Architect → Backend → QA". Actual: TL one-shot decomposed into a single DevOps assignment. TL's call was reasonable — "smoke pipelines documentation" reads as ops/CI work — but it means the iter-29c depth cap, Architect spec stage, and QA verification were untouched on this run. Multi-role chain remains unexercised end-to-end.

**2. No `pending_review` was created.** `task_state.parent_rolled_up new_status=done child_count=1` fired directly off the DevOps `task_report`. The owner-approval gate (workflow rule #5 as of 2026-05-18) is **not actually wired** in the dispatcher's task-completion path for this task shape. The pre-existing autonomy contract assumption ("Claude approves agent gates") was moot here — there was nothing to approve. **This is a separate finding to track** independent of the 2026-05-23 contract change.

**3. TL chose `claude-opus-4-7` automatically.** Sonnet 4.6 was used for DevOps. Model selection is internal to the LLM client; quota budget held without intervention.

## Architectural follow-ups (defer to iter-29d+)

- **Wire the `pending_review` gate** for single-child rollups. Decide whether docs-only task_reports auto-complete or always require a review record. (Lower priority now that autonomy contract auto-approves.)
- **Exercise the full chain.** Submit a task that forces TL to decompose across roles (e.g. a small code change + test + deploy step). Validates Architect/Backend/QA wiring, not just DevOps.
- **Workspace cleanup hook.** Workspace stays on `agent/devops/smoke-pipelines-readme` post-run. Next submit should branch from `main` again, but a workspace `git checkout main` between runs is safer.
- **Retro the gate-skip with intent.** Was it a feature (TL judgement: "no review needed for a 5-line docs PR") or a hole? Read `core/dispatcher/dispatcher.py::_handle_one` and `agents/team_lead/agent.py` to confirm.

## Carry-over status (from iter-29c handoff §5)

Unchanged — none addressed in 29b. Still queued:

- HoldQueue Postgres persistence
- `pytest-rerunfailures` plugin pin
- `audit_writer` restricted Postgres role
- Hash-chain alert job
- TL decomposition transactional insert
- `BaseAgent.handle()` template-method refactor
- `mark_task_done` / `update_task_status` real impls
- Substrate-level `--allowed-tools ""` fix

## Demo replay

```bash
# Infra already up (postgres + redis healthy)
cd /Users/kirillterskih/ai_team
uv run uvicorn apps.api.main:app --host 127.0.0.1 --port 8000 &
until curl -sf http://127.0.0.1:8000/health > /dev/null; do sleep 1; done

uv run ai-team submit \
  --title "Document smoke pipelines in product README" \
  --description "Add a '## Smoke pipelines' section to README.md ..." \
  --target-repo girlsmakemedrink/telegram-tech-publisher

# Capture task_id from output, watch via:
uv run ai-team watch
```

## Closure

iter-29b is **shipped**. The framework moves from "infrastructure complete, never proven" to "**proven on a real product repo, single-agent chain**". Next iter-29d brief: exercise the multi-role chain on a non-trivial task.
