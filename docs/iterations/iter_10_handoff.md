# Iteration 10 handoff

> Read **after** `CLAUDE.md`, `docs/iterations/iter_9_retro.md`,
> and `docs/iterations/iter_9_demo_report.md`. Replaces
> re-reading the prior conversation.

## Where we are (2026-05-19 EOD, iter-9 merged)

Iter-9 is on `main`. Same 10-agent roster as iter-8; three
targeted changes that lay the BLOCKED-routing groundwork for
MCP failures:

1. **`core/llm/mcp_health.py:check_mcp_servers`** — pre-flight
   probe that imports each declared `tools.mcp_servers.*`
   module and (for `ai_team_repo`) exercises
   `Context.from_env`. Returns list of unhealthy server names
   or `[]`. 7 unit tests pin the contract.
2. **`BaseAgent.handle()`** — calls `check_mcp_servers` at
   the top; raises `MCPUnhealthyError` if any unhealthy.
   Silent no-op when `AI_TEAM_MCP_CONFIG_PATH` is unset.
3. **Dispatcher** — `_synth_failed_report` extends iter-6's
   BLOCKED branch to catch `MCPUnhealthyError` →
   `status=BLOCKED, blocked_on='mcp_unhealthy', P2`.
   Dependents stay held in HoldQueue (mirrors the budget
   branch).

iter-9 demo report at `docs/iterations/iter_9_demo_report.md`
is the single source of truth. Headline: Designer + Frontend
completed for the second iteration in a row (4 of 6
terminal-good). Backend ran 347 s + 32 ¢ writing the full v2
implementation (21 K output tokens) but reported `failed`
because its `claude -p` session couldn't connect to the
`ai-team-repo` MCP server mid-run for the commit/push tools.
iter-9's pre-flight gate didn't fire because the failure
mode is mid-session, not deterministic-startup — the plan's
risk register predicted this exactly and named iter-10's
substring router as the load-bearing fix.

## Carry-over items (priority order, from iter-9 retro + demo report)

1. **(top)** **Dispatcher substring router on
   `task_report(failed)` summaries matching MCP-race
   patterns.** Upgraded from "defense-in-depth" to
   load-bearing. The LLM's own `task_report(failed)` summary
   names the failure verbatim in both demos:
   - iter-8: "all three ToolSearch retries returned 'still
     connecting'"
   - iter-9: "MCP server ai-team-repo never connected"
   Add a substring detector in
   `core/dispatcher/dispatcher.py` (or a sibling helper):
   when the incoming `task_report.payload.status == failed`
   AND its `summary` substring-matches one of the patterns
   above, re-emit as `BLOCKED(blocked_on='mcp_race_mid_session')`
   so HoldQueue holds dependents instead of cascade-dropping.
   The dispatcher already has the BLOCKED branch (iter-9
   Phase 3); iter-10 extends the detection. Test pattern
   mirrors iter-9 Phase 3 integration test.
2. **Re-run iter-9-shape demo** after #1 to finally close
   the `pending_review` loop iter-3/4/5/6/7/8/9 all reached
   for. Same 30-min wall-clock, same v2 task; iter-10 reuses
   `scripts/demo_iter_9.sh` or clones to
   `scripts/demo_iter_10.sh` per project convention.
3. **Backend's system prompt — forbid native Bash for git /
   uv / make; route through
   `mcp__ai_team_repo__run_shell`.** iter-9 demo Backend's own
   summary admits "the Bash tool requires manual approval
   for all git/uv/make commands in this session". The
   `run_shell` command-class enum (iter-2) covers exactly
   these operations: `git_status`, `git_add`, `git_commit`,
   `git_push_feature`, `make_test`, `pytest`, etc. One-file
   prompt fix in `prompts/backend_developer.md`. Pair with
   #1 — even after MCP-race routing improves, Backend should
   still prefer `run_shell` over Bash for hard-constraint
   reasons (least-privilege per ADR-004).
4. **`BaseAgent.llm_timeout_s` default 300 → 600 refactor**
   (deferred from iter-8 + iter-9). Five subclasses override
   (Architect, Backend, Frontend, DevOps, Designer); only
   PM, QA, SRE, MarketResearcher, TL inherit the 300 s
   default. Flip the default, drop the now-redundant
   per-subclass overrides. Touches 5 agent files.
5. **Add `^examples/` to `[tool.mypy].exclude` in
   `pyproject.toml`** (deferred from iter-9). One-line
   config fix; symmetric with the existing ruff exclusion
   (CLAUDE.md / ADR-009). iter-8 + iter-9 demos both left
   `examples/sandbox/idea-validator/tests/__init__.py`
   untracked, which collides with the project's
   `tests/__init__.py` and breaks bare `make typecheck`.
6. **HoldQueue persistence (Postgres-backed).** Still
   in-memory. Lift to `held_messages` table once a real
   outage hits or a second dispatcher process appears.
7. **`audit_writer` restricted Postgres role enforcement.**
   Still deferred from iter-2/3/4/5/6/7/8/9.
8. **Hash-chain alert job.** Still deferred.
9. **`GitHubTargetRepo` implementation.** Waiting on first
   commercial product (ADR-009).
10. **TL decomposition transactional insert.** A TL crash
    mid-batch leaves orphan child rows. Wrap the TL's whole
    batch in one transaction.
11. **`pytest-rerunfailures` plugin pin** for the
    testcontainers port-mapping race. iter-7 + iter-8 +
    iter-9 demos all saw the race once locally; promote to
    a real iteration if it bites CI.
12. **`BaseAgent.handle()` template-method refactor.** Defer
    until the next agent rolls in.
13. **TL decomposition of Backend task.** Backend's 5:47
    single-session in iter-9 is the longest in any demo —
    the prompt may be structurally too large for one agent.
    Consider splitting into "scaffold + tests" + "stages" +
    "pipeline + CLI" as separate subtasks. Has interaction
    with #1: smaller sessions = less mid-session race time.

## Hard constraints unchanged from iter-4..9

- **LLM substrate is `claude -p` via subscription.** Never set
  `ANTHROPIC_API_KEY`. Never use Agent SDK with an API key.
- **`--json-schema` validated output lives in `structured_output`**.
- **`--session-id` is set-once, `--resume` is resume.** Adapter
  switches automatically.
- **Boring stack only.** Re-read ADR-001 before considering any
  new framework.
- **Diff-cover gate is 80 %. Bandit gates on high only.**
- **Ruff `format --check` is also a gate.**
- **Conventional commits, squash-merge, plan-before-code,
  owner approval on every agent task completion.**
- **Bash never raw on agents.** Use
  `mcp__ai_team_repo__run_shell` with its command-class enum.
  (iter-10 #3 makes Backend's prompt enforce this more
  strongly.)
- **`pending_review` rows are the owner-approval gate.**
- **`examples/` is the agents' TARGET_REPO root** (ADR-009).
  Excluded from orchestrator ruff lint; iter-10 #5 adds the
  symmetric mypy exclusion.

## Inherited decisions (do not contradict without revisiting)

- Agent PRs target `main` on `ai_team` only (single-repo
  exception).
- Architect is **advisory**, not gating.
- TL auto-routes BLOCKED with one auto-hop max (iter-2c).
- TL emits a flat list of subtasks with explicit `depends_on`
  slugs (iter-3); declares `depends_on` only when recipient
  literally cannot start without (iter-4); emits a
  `BROADCAST(topic="tl.dag_preview")` (iter-4).
- HoldQueue is in-memory only.
- LLM metrics live in `metadata["llm"]` on the envelope;
  every agent stamps them (iter-5).
- Per-stage demo task uses the v2 spec.
- MCP servers in demo configs are invoked via
  `${REPO_ROOT}/.venv/bin/python -m tools.mcp_servers.<name>`
  (iter-4).
- `claude -p` agent sessions pass
  `--permission-mode acceptEdits` by default (iter-5).
- Dispatcher synthesises `TASK_REPORT(failed)` for any
  `handle()` exception (iter-5).
- **iter-6:** `LLMBudgetExhaustedError` →
  `TASK_REPORT(blocked, blocked_on='budget')` instead of
  `failed`.
- **iter-6:** When `HoldQueue.mark_failed` drops messages,
  the dispatcher calls `task_state.on_drop([task_ids])`.
- **iter-7:** Dispatcher cascades drops transitively via
  `_cascade_drops(correlation_id, failed_task_id)`.
- **iter-7:** `LLMTimeoutError` carries best-effort buffered
  stdout drained after kill.
- **iter-7:** Architect's `llm_timeout_s = 600`.
- **iter-8:** Designer's `llm_timeout_s = 600`.
- **iter-8:** `_is_budget_exhausted_stdout` is a
  substring-only match against `"error_max_budget_usd"`.
  Stdout cap on the non-zero-exit branch is 8 KB.
- **iter-8:** sonnet `--max-budget-usd` default is $2.50;
  haiku $0.30, opus $4.00.
- **iter-9:** `BaseAgent.handle()` pre-flight calls
  `check_mcp_servers` from `AI_TEAM_MCP_CONFIG_PATH`. Silent
  skip if env var unset.
- **iter-9:** `MCPUnhealthyError` → `BLOCKED(mcp_unhealthy,
  P2)`. Mirrors iter-6's `LLMBudgetExhaustedError → BLOCKED`
  pattern; dependents stay held in HoldQueue.
- Demo wall-clock is 30 min (iter-6, unchanged in
  iter-7/8/9).

## Ready-to-paste prompt for the new session

```
Starting Iteration 10 on the ai_team project.

First, read these in this order:

1. CLAUDE.md
2. docs/iterations/iter_9_retro.md (what just shipped, what's still open)
3. docs/iterations/iter_9_demo_report.md (real-LLM demo findings — MCP
   race is mid-session, not startup, so iter-9's pre-flight gate didn't
   fire; iter-10's substring router on the LLM's task_report(failed)
   summary is now load-bearing for the pending_review loop)
4. docs/iterations/iter_10_handoff.md (this file — full handoff context)
5. docs/adr/0001-orchestrator-choice.md, 0004-agent-tool-allowlist.md,
   0008-llm-access-strategy.md

Iter-10 priority is **adding a dispatcher substring router** on
`task_report(failed)` summaries matching the two MCP-race patterns
seen across iter-8 + iter-9 demos ("MCP server * never connected" +
"all * retries returned 'still connecting'"), routing matches to
BLOCKED(blocked_on='mcp_race_mid_session') so dependents stay held
instead of cascade-dropping. The dispatcher already has the BLOCKED
branch from iter-9 Phase 3; iter-10 extends the detection only.
After that: a Backend prompt fix forbidding native Bash for git/uv/
make (route through mcp__ai_team_repo__run_shell), then the
BaseAgent.llm_timeout_s default 300 → 600 refactor (5+ subclasses
now override), and the examples/ mypy exclude one-liner. See
`iter_9_demo_report.md` Failure 1 and Failure 2.

Workflow: plan-before-code. Draft docs/iterations/iter_10.md first,
surface for review, then code. Run validation checks + PR merges
yourself (autonomy preference in memory).

Constraints unchanged from iter-9 — see CLAUDE.md gotchas + the
"Hard constraints" section of iter_10_handoff.md.

When ready, create the iter-10 task list and surface the plan.
```
