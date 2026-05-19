# Iteration 3 handoff

> Read **after** `CLAUDE.md`, `docs/iterations/iter_2c_retro.md`, and
> `docs/iterations/iter_2_demo_report.md`. Together ~12 KB; replaces
> re-reading the prior conversation.

## Where we are (2026-05-19 EOD, iter-2c merged)

Iter-2, iter-2b, and iter-2c are all on `main`. **Nine agents are live
in the dispatcher**: TL (Opus), PM (Sonnet), Architect (Opus), Backend
(Sonnet), QA (Sonnet), Designer (Sonnet), DevOps (Sonnet), Frontend
(Sonnet), SRE/Support (Sonnet), Market Researcher (Sonnet). Per-role
MCP path-scope at spawn time (ADR-004 enforced via
`AI_TEAM_PATH_PREFIXES`).

TL auto-routes BLOCKED task reports to the role indicated by the
agent's populated `TaskReportPayload.blocked_on` (or a parseable
"blocked: requires <role>" prefix in the summary). One auto-hop max;
further BLOCKED reports surface to the owner.

**The real-LLM e2e demo finally ran for real** (iter-2c Phase 1). It
exposed three concrete bottlenecks that are now the iter-3 entry list.
Full write-up in `docs/iterations/iter_2_demo_report.md`.

## Carry-over items (priority order, from iter-2c retro + demo report)

1. **TL decomposition with dependency ordering** (blocker for any
   meaningful e2e flow). Add `depends_on: list[str]` to
   `DECOMPOSITION_SCHEMA` and have the dispatcher hold sub-tasks
   until their predecessors report DONE. Without this, parallel
   dispatch makes Architect → Backend → QA chains structurally
   impossible.
2. **Demo wall-clock + sub-task sizing.** Bump
   `scripts/demo_iter_2.sh`'s wait window past 10 min (~20 min is
   plenty) and break the idea-validator task into smaller per-stage
   sub-tasks so a realistic Backend turn fits inside. Pair this with
   #1.
3. **`ai-team digest` 401 bug.** The CLI is not passing `OWNER_TOKEN`
   from `.env` to the API. Single unit pin + fix in
   `apps/cli/main.py`.
4. **Root-task state rollup.** `tasks.status` should reflect the
   chain's progress, not stay `in_progress` after Architect has
   reported DONE. Touches `core/dispatcher.py` (the receive-side
   bookkeeping after `agent.handle()` returns) and the TL's final
   "everything is done" emission.
5. **Persist per-message `tokens` + `cost_cents` + `duration_ms` +
   `validated_against_schema`** to the audit-log payload (or
   metadata, or a sibling table). Currently these are only in
   structlog. Without this, every demo report is a grep job.
6. **Second real-LLM demo run after 1–5 land.** Exercise the
   Designer → Frontend → QA path for the first time (with #1's
   ordering this is finally possible).
7. **`audit_writer` Postgres role enforcement.** ADR-003 says only a
   restricted DB role can `INSERT` into `audit_log`. Still deferred.
8. **Hash-chain alert job.** Scheduled `verify_chain()` job with
   `ALERT` emission on tamper. Still deferred.
9. **`GitHubTargetRepo` impl.** When the first commercial product
   lands. ADR-009: "deferred to first commercial product."

## Hard constraints unchanged from iter-2 / 2b / 2c

- **LLM substrate is `claude -p` via subscription.** Never set
  `ANTHROPIC_API_KEY`. Never use Agent SDK with an API key.
- **`--json-schema` validated output lives in `structured_output`**.
- **`--session-id` is set-once, `--resume` is resume.** Adapter
  switches automatically.
- **Boring stack only.** Re-read ADR-001 before considering any new
  framework. LangGraph / CrewAI / OpenAI SDK are all rejected.
- **Diff-cover gate is 80 %. Bandit gates on high only.**
- **Conventional commits, squash-merge, plan-before-code, owner
  approval on every agent task completion.**
- **Bash never raw on agents.** Use `mcp__ai_team_repo__run_shell`
  with its command-class enum.
- **`pending_review` rows are the owner-approval gate.** Even when
  CI is green, an agent's `task_report` waits for `ai-team approve <id>`.

## Inherited decisions (do not contradict without revisiting)

- Agent PRs target `main` on `ai_team` only (single-repo exception,
  per iter-2b 1A `AI_TEAM_FORBID_PR_BASE_RE`).
- Architect is **advisory**, not gating. TL is the only gating router.
- TL auto-routes BLOCKED with one auto-hop max (iter-2c Phase 4).
- `idea-validator`'s LLM calls share owner quota.
- Backend's path-scope is `* allow + denylist` (`infra/,
  .github/workflows/`).
- Frontend's path-scope is `apps/web,apps/cli` for ai_team; target
  repos override via `AI_TEAM_PATH_PREFIXES` per-task.
- SRE ships read tools + `WebFetch` + path-scoped write only;
  `curl`/`promtool`/`journalctl` deferred to iter-5 server move.
- Anti-loop guard for TL routing is summary-string check, not a
  metadata counter. Revisit if it bites.

## Ready-to-paste prompt for the new session

```
Starting Iteration 3 on the ai_team project.

First, read these in this order:

1. CLAUDE.md
2. docs/iterations/iter_2c_retro.md (what just shipped, what's still open)
3. docs/iterations/iter_2_demo_report.md (real-LLM demo findings)
4. docs/iterations/iter_3_handoff.md (this file — full handoff context)
5. docs/adr/0001-orchestrator-choice.md, 0002-message-schema.md,
   0003-audit-log.md, 0008-llm-access-strategy.md

Iter-3 goal: close the three demo-blocker fixes (TL dependency ordering,
demo wall-clock + sub-task sizing, ai-team digest auth bug), then add
root-task state rollup and per-message cost/token persistence so the
next demo report is a single SQL query. Re-run the real-LLM e2e demo
after they land — this time exercising Designer → Frontend → QA for
the first time.

Workflow: plan-before-code. Draft docs/iterations/iter_3.md first,
surface for review, then code. Run validation checks + PR merges
yourself (autonomy preference in memory).

Constraints unchanged from iter-2c — see CLAUDE.md gotchas + the
"Hard constraints" section of iter_3_handoff.md.

When ready, create the iter-3 task list and surface the plan.
```
