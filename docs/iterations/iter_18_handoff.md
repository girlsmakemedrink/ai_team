# Iteration 18 handoff

> Read **after** `CLAUDE.md`,
> `docs/iterations/iter_17_retro.md`, and
> `docs/iterations/iter_17_demo_report.md`. Replaces
> re-reading the prior conversation.

## Where we are (2026-05-20 EOD, iter-17 merged)

Iter-17 is on `main`. iter-17 **destroyed the
9-iteration MCP race carry-over** by identifying it as
a 14-iteration latent JSON-RPC protocol bug from
iter-2: the three MCP servers had no `initialize`
handler in their stdio loops. Adding the handler +
switching `--permission-mode` from `acceptEdits` to
`bypassPermissions` (acceptEdits only auto-accepts file
edits, not MCP tool calls) unblocked Backend's ability
to USE MCP tools.

iter-17 demo run #3 produced the **first end-to-end
7-agent chain completion in project history**:
PM/Architect/Designer/Frontend/**Backend**/**QA** all
`task_report(done)`. Backend made 64 MCP tool calls in
a 462-second session — pytest 54/54 passed, 90.6%
coverage, branch pushed, PR #24 opened.

**The chain didn't reach `pending_review` because**
the `mcp__ai_team_tasks__request_human_review` tool is
still the iter-0 STUB. `ai_team_tasks` server returns
`"[stub] request_human_review not implemented until
Iteration 2"`. QA called it correctly; the row was
never written to `pending_reviews`.

**iter-18's top priority is the ~50-LOC implementation
of `request_human_review`** to insert the row and
finally close the formal loop.

## Carry-over items (priority order, from iter-17 retro + demo report)

1. **(top)** **Implement
   `mcp__ai_team_tasks__request_human_review`** to
   actually INSERT a `pending_reviews` row. Same shape
   as `ai_team_repo`'s handler dispatch — needs
   `Context.from_env()` for DB URL, SQLAlchemy session,
   INSERT into `pending_reviews` table. Tools the
   server declares:
   - `mark_task_done(task_id, summary, artifacts)`
   - `request_human_review(summary, target_artifact)` ← TOP
   - `update_task_status(task_id, status, progress_pct)`

   `request_human_review` is load-bearing (closes the
   loop). The others may be auditable via agent prompts
   to see if they're called.

2. **Re-run iter-17-shape demo after #1**. Expected:
   chain reaches `task_report(done)` + a
   `pending_reviews` row + demo auto-approves → **the
   formal loop closes end-to-end for the first time
   in 18 iterations**.

3. **TL Backend decomposition** — now SEVEN-iteration
   carry-over. iter-17 Backend session = 462s (77% of
   the 600s timeout). Future Backend work (e.g., real
   feature additions) could exceed. Split into 2-3
   chunks (commit/push, pytest, open PR). Pull forward
   if iter-18's demo's Backend hits timeout; defer to
   iter-19 otherwise.

4. **HoldQueue persistence (Postgres-backed)** —
   in-memory queue still loses held assignments on
   restart. Less urgent now that Backend isn't
   restarting mid-session, but still a latent risk.

5. **`pytest-rerunfailures` plugin pin** — iter-17 CI
   flaked again on `test_transitive_drops_cascade_
   through_hold_queue` when combined unit+integration
   runs. Re-running passes. Pin the plugin to auto-
   retry once.

6. **Agents' git-checkout shouldn't leak into the
   orchestrator's worktree.** iter-17 run #3:
   Backend's `mcp__ai_team_repo__create_branch`
   switched the orchestrator's current branch to
   `agent/backend_developer/idea-validator-v2-
   pipeline`. The retro had to cherry-pick a commit
   back. Possible fix: spawn each agent's MCP server
   in an isolated worktree.

7. **TL auto-hop investigation** — iter-17 handoff #3,
   still deferred. Confirm whether the iter-2c
   BLOCKED auto-hop is wired + firing.

8. **TL over-decomposition prompt hint** — Architect
   re-derives ADRs already on disk. Small prompt edit.

9. **Startup-time MCP failure investigation** —
   **closed by iter-17**. The "MCP race" was actually
   the missing `initialize` handler. No further action.

10. **Architect's spend watch** — iter-17 run #3
    Architect: $0.87. Plateau. The TL over-
    decomposition hint (#8) would address.

11. **`audit_writer` restricted Postgres role
    enforcement.** Still deferred.

12. **Hash-chain alert job.** Still deferred.

13. **`GitHubTargetRepo` implementation.** Waiting on
    first commercial product (ADR-009).

14. **TL decomposition transactional insert.** Still
    deferred.

15. **`BaseAgent.handle()` template-method refactor.**
    Defer until the next agent rolls in.

## Hard constraints unchanged from iter-4..17

- **LLM substrate is `claude -p` via subscription.** Never
  set `ANTHROPIC_API_KEY`. Never use Agent SDK with an API
  key.
- **`--json-schema` validated output lives in
  `structured_output`**.
- **`--session-id` is set-once, `--resume` is resume.**
- **iter-15: `api_error_status=429` → BLOCKED(budget)** —
  production-validated in iter-17 run #2.
- **iter-17: `--permission-mode bypassPermissions`** —
  security boundary is orchestrator-level (allow-list +
  MCP path scope + run_shell command_class enum).
- **iter-17: All MCP servers MUST respond to
  `initialize`.** `_build_response(msg)` pure helper in
  each `__main__.py`. The 12 unit + 6 integration
  subprocess tests pin this against regression.
- **Boring stack only.** Re-read ADR-001 before
  considering any new framework.
- **Diff-cover gate is 80%. Bandit gates on high only.**
- **Ruff `format --check` is also a gate.**
- **Conventional commits, squash-merge, plan-before-code,
  owner approval on every agent task completion.**
- **Bash never raw on agents.** iter-10 prompt + iter-11
  `--disallowed-tools "Bash"` defense-in-depth.
- **`pending_review` rows are the owner-approval gate.**
- **`examples/` is the agents' TARGET_REPO root** (ADR-
  009). Excluded from orchestrator ruff + mypy.

## Inherited decisions (do not contradict without revisiting)

- Agent PRs target `main` on `ai_team` only (single-repo
  exception).
- Architect is **advisory**, not gating.
- TL auto-routes BLOCKED with one auto-hop max (iter-2c).
- TL emits a flat list of subtasks with explicit
  `depends_on` slugs (iter-3); declares `depends_on` only
  when recipient literally cannot start without (iter-4);
  emits a `BROADCAST(topic="tl.dag_preview")` (iter-4).
- HoldQueue is in-memory only.
- LLM metrics live in `metadata["llm"]` on the envelope;
  every agent stamps them (iter-5).
- **iter-11:** `build_retry_message` does `model_copy`
  preserving original `metadata["llm"]`. Audit readers
  should NOT double-count.
- Per-stage demo task uses the v2 spec.
- MCP servers in demo configs are invoked via
  `${REPO_ROOT}/.venv/bin/python -m tools.mcp_servers.<name>`
  (iter-4).
- Dispatcher synthesises `TASK_REPORT(failed)` for any
  `handle()` exception (iter-5).
- **iter-6:** `LLMBudgetExhaustedError` →
  `TASK_REPORT(blocked, blocked_on='budget')`.
- **iter-6:** When `HoldQueue.mark_failed` drops messages,
  the dispatcher calls `task_state.on_drop([task_ids])`.
- **iter-7:** Dispatcher cascades drops transitively via
  `_cascade_drops(correlation_id, failed_task_id)`.
- **iter-7:** `LLMTimeoutError` carries best-effort
  buffered stdout drained after kill.
- **iter-8:** `_is_budget_exhausted_stdout` is a
  substring-only match against `"error_max_budget_usd"`.
- **iter-8:** sonnet `--max-budget-usd` default is $2.50;
  haiku $0.30, opus $4.00.
- **iter-9:** `BaseAgent.handle()` pre-flight calls
  `check_mcp_servers` from `AI_TEAM_MCP_CONFIG_PATH`.
- **iter-9:** `MCPUnhealthyError` exception →
  `BLOCKED(blocked_on='mcp_unhealthy', P2)`.
- **iter-10:** LLM-emitted `task_report(failed)` with MCP-
  race summary → rewritten to
  `BLOCKED(blocked_on='mcp_unhealthy')` by
  `maybe_route_mcp_race_to_blocked` BEFORE HMAC-sign.
- **iter-10:** Backend's prompt has an explicit lookup
  table of `command_class` values for git / uv / make /
  pytest.
- **iter-11:** `ai-team retry-blocked <task_id>` CLI is
  the owner's recovery action for BLOCKED tasks.
  Capped at 5 attempts.
- **iter-11:** Backend's `disallowed_tools = ("Bash",)`.
- **iter-11:** `BaseAgent.llm_timeout_s` default = 600 s.
- **iter-13:** `ClaudeCodeHeadlessClient` extracts
  `_spawn_once` + retries with `--resume` on session-id
  collision.
- **iter-15:** `_MCP_RACE_PATTERNS` REPLACED with
  cross-product `_MCP_TOKEN_SET` x `_MCP_FAILURE_VERB_SET`.
- **iter-15:** `api_error_status=429` → BLOCKED(budget).
  Production-validated in iter-17.
- **iter-16:** `_MCP_FAILURE_VERB_SET` extended with
  `"unreachable"` and `"unavailability"`.
- **iter-17:** MCP servers respond to `initialize` with
  spec-correct `protocolVersion` + `capabilities` +
  `serverInfo`. `_build_response(msg)` is the pure
  helper.
- **iter-17:** `--permission-mode bypassPermissions`.
- Demo wall-clock is 30 min initial chain + 15 min
  retry window = 45 min total.

## Ready-to-paste prompt for the new session

```
Starting Iteration 18 on the ai_team project.

First, read these in this order:

1. CLAUDE.md
2. docs/iterations/iter_17_retro.md (what just
   shipped: MCP race destroyed at root, 7-agent
   chain completed for the first time)
3. docs/iterations/iter_17_demo_report.md (real-LLM
   demo across 3 runs — milestone run #3 with all 7
   agents done)
4. docs/iterations/iter_18_handoff.md (this file —
   full handoff context)
5. docs/adr/0001-orchestrator-choice.md,
   0008-llm-access-strategy.md

Iter-18 priority is **implementing
mcp__ai_team_tasks__request_human_review** to actually
INSERT a pending_reviews row. The 7-agent chain
completes cleanly now; only the formal owner-approval
gate is missing because the MCP tool is still the
iter-0 stub.

Implementation shape: mirror ai_team_repo's handler
dispatch — Context.from_env() for DB URL, SQLAlchemy
session, INSERT into pending_reviews. ~50 LOC + 5-7
unit/integration tests.

After that: TL Backend decomposition (SEVEN-iteration
carry-over), HoldQueue persistence,
pytest-rerunfailures plugin pin, agents'-branch-
isolation investigation.

Workflow: plan-before-code. Draft
docs/iterations/iter_18.md first, surface for review,
then code. Run validation checks + PR merges yourself.

Constraints unchanged from iter-17 — see CLAUDE.md
gotchas + the "Hard constraints" section of
iter_18_handoff.md.

When ready, create the iter-18 task list and surface
the plan.
```
