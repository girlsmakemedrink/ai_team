# Iteration 21 handoff

> Read **after** `CLAUDE.md`,
> `docs/iterations/iter_20_retro.md`, and
> `docs/iterations/iter_20_demo_report.md`.
> Replaces re-reading the prior conversation.

## Where we are (2026-05-21 EOD, iter-20 merged)

iter-20 is on `main`. iter-20 **closed iter-19
demo's #1 priority (branch-isolation) end-to-end
via `git worktree add`** and **structurally
addressed iter-19's #2 priority (Backend
decomposition) via a TL prompt edit** — the TL
agent in the iter-20 demo successfully emitted
TWO Backend subtasks instead of one. The
Architect's ADR-0027 even cited the iter-20
Phase 2 commit SHA verbatim.

But **the prompt-only Backend decomposition isn't
sufficient under real-LLM stress**: one of the 2
Backend subtasks still hit the 600s timeout in
the iter-20 demo, cascade-dropping QA. The
QA-emitted `pending_review` row criterion that
iter-19 deferred remains UNMET (now 2-iteration
deferred).

iter-20 also surfaced the **true root cause of
the demo auto-approve bash bug** (3-iteration
"fix attempted, didn't work" carry-over): the
`printf '%s' "$X" | python3 <<'PY' ... PY`
pattern is a heredoc-vs-pipe conflict — python's
stdin gets the heredoc (source code), not the
piped JSON. iter-18 and iter-19 both fixed the
wrong layer.

**iter-21's top two priorities are the Backend
runtime tripwire and the demo auto-approve bash
fix done right. Both are prerequisites for the
QA-row criterion to finally close.**

## Carry-over items (priority order)

1. **(NEW TOP)** **Backend runtime tripwire.**
   `BackendDeveloperAgent.handle()` rejects an
   incoming `task_assignment` whose description
   estimates a too-large scope. On reject,
   return `TASK_REPORT(status=BLOCKED,
   blocked_on='task_too_large')`. The
   dispatcher's iter-6 BLOCKED path keeps
   dependents in the HoldQueue; TL can then
   route an "unblock: re-decompose" message
   per the iter-2c auto-hop logic.

   Concrete heuristic for "too-large":
   - Description character count > 1500 chars.
   - OR description mentions ≥ 3 distinct
     file-path-shaped tokens (regex
     `[A-Za-z][A-Za-z0-9_/.-]+\.[a-z]+`) that
     don't already exist on disk (within
     TARGET_REPO scope).
   - OR description contains both "new module"
     and "test suite" markers (indicates a
     scope that includes both production code
     AND tests, typically > 200 LOC).

   The exact heuristic can be tuned; the
   important contract is "Backend recognizes
   too-large work BEFORE burning 600s on it."

2. **(NEW)** **Demo auto-approve bash fix done
   right.** 3-iteration carry-over (iter-18 →
   iter-19 → iter-20). Real root cause:
   `command | python3 <<'PY' ... PY` routes
   python's stdin to the HEREDOC source code,
   not the piped JSON. iter-21's fix:

   ```bash
   REVIEWS_JSON=$(curl -sf -H "..." \
       http://127.0.0.1:8000/api/reviews 2>/dev/null || true)
   REVIEWS_JSON="${REVIEWS_JSON:-[]}"
   python3 - "$REVIEWS_JSON" <<'PY' || true
   import json, subprocess, sys
   data = json.loads(sys.argv[1])
   ...
   PY
   ```

   The `python3 - "..."` form reads code from
   the heredoc and the JSON arrives via
   `sys.argv[1]`. Apply to iter-21's demo
   script.

3. **(NEW)** **Architect spend watch
   escalating.** iter-19 $0.78 → iter-20 $2.88
   (3.7×). Backend timeout cascade-dropped QA
   so iter-20's cost was dominated by
   Architect's $2.88 + Architect's 473s
   wall-clock. Investigate what Architect's
   session does:
   - Reads many existing ADRs (`Read`/`Glob`/`Grep`
     in its allow-list — fine).
   - Possibly re-derives content from prior
     ADRs (the carry-over "TL
     over-decomposition prompt hint" addresses).
   - Possibly is the new
     ADR-0027-style "iter-N pointer ADR"
     pattern adding unnecessary depth.

4. **Re-attempt the iter-19/20 QA-emitted
   pending_review row criterion** — now
   2-iteration deferred. Run the same demo
   shape after iter-21 #1 lands.

5. **HoldQueue persistence (Postgres-backed).**

6. **`pytest-rerunfailures` plugin pin.**

7. **TL auto-hop investigation.**

8. **TL over-decomposition prompt hint** —
   partially addresses carry-over #3 above.

9. **`audit_writer` restricted Postgres role.**

10. **Hash-chain alert job.**

11. **`GitHubTargetRepo` implementation.**

12. **TL decomposition transactional insert.**

13. **`BaseAgent.handle()` template-method
    refactor.**

14. **`mark_task_done` / `update_task_status`
    real implementations** — iter-20 audit
    confirms no agent's prompt invokes either.
    Continue STUB.

15. **Substrate-level `--allowed-tools ""` fix.**

## Hard constraints unchanged from iter-4..20

- **LLM substrate is `claude -p` via subscription.** Never
  set `ANTHROPIC_API_KEY`. Never use Agent SDK with an API
  key.
- **`--json-schema` validated output lives in
  `structured_output`**.
- **`--session-id` is set-once, `--resume` is resume.**
- **iter-15: `api_error_status=429` → BLOCKED(budget)**.
- **iter-17: `--permission-mode bypassPermissions`**.
- **iter-17: All MCP servers MUST respond to
  `initialize`.**
- **iter-18: `mcp__ai_team_tasks__request_human_review`
  is a real handler.** `pending_reviews` rows are
  load-bearing.
- **iter-18: `tools/call` async dispatch in
  `ai_team_tasks/__main__.py` mirrors
  `ai_team_repo/__main__.py` shape.**
- **iter-19: `BaseAgent._build_env(msg)` is the
  canonical per-invocation env helper.** Sets
  `AI_TEAM_AGENT_ROLE`, `AI_TEAM_CORRELATION_ID`,
  `AI_TEAM_TASK_ID`.
- **iter-19: `ai_team_tasks.Context` has
  `default_correlation_id`** sourced from
  `AI_TEAM_CORRELATION_ID`.
- **iter-19: PM and TL `allowed_tools = ("Read",
  "Glob", "Grep")`**. Pin test
  `tests/unit/test_agent_allowed_tools_pin.py`
  enforces non-empty across all 10 concrete
  agents.
- **iter-19: PM `llm_timeout_s = 600`**.
- **iter-19: `_invoke_with_retries` signature
  has `msg: AgentMessage` param**.
- **iter-20: `handle_create_branch` uses
  `git worktree add`, NOT `git checkout -b`.**
  Worktree path:
  `<scope_root>/.claude/agent-worktrees/<slug>/`.
  Module-level `_ACTIVE_WORKTREE` tracks the
  per-session worktree; subsequent handler
  calls (status, run_shell, write_file_in_scope,
  open_pr) use it as cwd via
  `_effective_cwd(ctx)`.
- **iter-20: `_ACTIVE_WORKTREE` is per-MCP-server-
  process state.** Naturally scoped to one
  agent's session since `claude -p` spawns a
  fresh MCP server per invocation. Autouse pytest
  fixture
  (`tests/unit/test_mcp_ai_team_repo_handlers.py:_reset_active_worktree`)
  resets it between tests.
- **iter-20: TL prompt teaches Backend
  decomposition.** Backend subtasks must be
  ≤200 LOC scope; if larger, decompose into
  multiple with `depends_on` slugs. Pin test
  `tests/unit/test_team_lead_agent.py:test_tl_prompt_teaches_backend_decomposition`.
- **iter-20: `scripts/demo_iter_20.sh` prunes
  agent worktrees on entry and removes them on
  exit.** The orchestrator's
  `.claude/agent-worktrees/` directory is
  always-clean between demo runs.
- **Boring stack only.**
- **Diff-cover gate is 80%. Bandit gates on high only.**
- **Ruff `format --check` is also a gate.**
- **Conventional commits, squash-merge, plan-before-code,
  owner approval on every agent task completion.**
- **Bash never raw on agents.**
- **`pending_review` rows are the owner-approval gate.**
- **`examples/` is the agents' TARGET_REPO root**.

## Inherited decisions (do not contradict without revisiting)

- Agent PRs target `main` on `ai_team` only (single-repo
  exception).
- Architect is **advisory**, not gating.
- TL auto-routes BLOCKED with one auto-hop max.
- TL emits a flat list of subtasks with explicit
  `depends_on` slugs; declares `depends_on` only when
  recipient literally cannot start without; emits a
  `BROADCAST(topic="tl.dag_preview")`.
- HoldQueue is in-memory only.
- LLM metrics live in `metadata["llm"]` on the envelope.
- **iter-11:** `build_retry_message` does `model_copy`
  preserving original `metadata["llm"]`.
- Per-stage demo task uses the v2 spec.
- MCP servers in demo configs are invoked via
  `${REPO_ROOT}/.venv/bin/python -m tools.mcp_servers.<name>`.
- Dispatcher synthesises `TASK_REPORT(failed)` for any
  `handle()` exception.
- **iter-6:** `LLMBudgetExhaustedError` →
  `TASK_REPORT(blocked, blocked_on='budget')`.
- **iter-6:** `HoldQueue.mark_failed` drops messages, the
  dispatcher calls `task_state.on_drop([task_ids])`.
- **iter-7:** Dispatcher cascades drops transitively.
- **iter-7:** `LLMTimeoutError` carries best-effort
  buffered stdout.
- **iter-8:** `_is_budget_exhausted_stdout` is
  substring-only.
- **iter-8:** sonnet `--max-budget-usd` default is $2.50;
  haiku $0.30, opus $4.00.
- **iter-9:** `BaseAgent.handle()` pre-flight calls
  `check_mcp_servers`.
- **iter-9:** `MCPUnhealthyError` exception →
  `BLOCKED(blocked_on='mcp_unhealthy', P2)`.
- **iter-10:** LLM-emitted `task_report(failed)` with
  MCP-race summary → rewritten to
  `BLOCKED(blocked_on='mcp_unhealthy')`.
- **iter-10:** Backend's prompt has an explicit lookup
  table of `command_class` values.
- **iter-11:** `ai-team retry-blocked <task_id>` CLI is
  the owner's recovery action.
- **iter-11:** Backend's `disallowed_tools = ("Bash",)`.
- **iter-11:** `BaseAgent.llm_timeout_s` default = 600 s.
- **iter-13:** `ClaudeCodeHeadlessClient` extracts
  `_spawn_once` + retries with `--resume` on
  session-id collision.
- **iter-15:** `_MCP_RACE_PATTERNS` REPLACED with
  cross-product `_MCP_TOKEN_SET` x
  `_MCP_FAILURE_VERB_SET`.
- **iter-15:** `api_error_status=429` → BLOCKED(budget).
- **iter-16:** `_MCP_FAILURE_VERB_SET` extended with
  `"unreachable"` and `"unavailability"`.
- **iter-17:** MCP servers respond to `initialize` with
  spec-correct fields.
- **iter-17:** `--permission-mode bypassPermissions`.
- **iter-18:** `ai_team_tasks` MCP server has a real
  `request_human_review` handler.
- **iter-18:** `tools/call` async dispatch.
- **iter-18:** QA's prompt instructs an explicit
  `request_human_review` call.
- **iter-19:** `BaseAgent._build_env(msg)` is the
  canonical helper.
- **iter-19:** `Context.default_correlation_id` fallback.
- **iter-19:** PM and TL `allowed_tools = ("Read",
  "Glob", "Grep")`.
- **iter-19:** PM `llm_timeout_s = 600`.
- **iter-20:** `handle_create_branch` uses `git
  worktree add` + module-level `_ACTIVE_WORKTREE`.
  All other ai_team_repo handlers consult
  `_effective_cwd(ctx)`.
- **iter-20:** TL prompt teaches Backend ≤200 LOC
  decomposition rule.
- **iter-20:** Demo script prunes + cleans up
  agent worktrees on entry/exit.
- Demo wall-clock is 30 min initial chain + 15 min
  retry window = 45 min total.

## What iter-20 specifically did NOT do

- **Did not add a Backend runtime tripwire**. iter-20
  shipped only the TL prompt edit. The iter-20 demo
  showed the prompt alone isn't enough — iter-21
  must ship the tripwire.
- **Did not produce a QA-emitted pending_review row**.
  Same outcome as iter-19's Phase 7. Deferred to
  iter-21.
- **Did not fix the demo auto-approve bash bug at
  the right layer**. iter-20 inherited iter-19's
  patch (which was wrong); the real root cause
  (heredoc-vs-pipe conflict) was discovered
  POST-demo and is now an iter-21 action item.
- **Did not implement per-agent worktrees managed
  by the dispatcher** (Option B from
  iter_20_handoff.md §1). The surgical fix
  (handler-side `git worktree add`) was sufficient
  for branch-isolation; the architectural
  refactor remains optional future work.
- **Did not investigate Architect spend escalation
  ($0.78 → $2.88)** — surfaced in iter-20 demo,
  promoted to iter-21 action item.

## Ready-to-paste prompt for the new session

```
Starting Iteration 21 on the ai_team project.

First, read these in this order:

1. CLAUDE.md
2. docs/iterations/iter_20_retro.md (what just
   shipped: branch-isolation closed end-to-end via
   git worktree add; Backend decomposition prompt
   edit working structurally but Backend STILL
   hit 600s on one of 2 subtasks)
3. docs/iterations/iter_20_demo_report.md (real-LLM
   demo — orchestrator HEAD intact, TL emitted 2
   Backend subtasks, Backend timeout, no QA row,
   bash auto-approve root cause finally identified)
4. docs/iterations/iter_21_handoff.md (this file —
   full handoff context)
5. agents/backend_developer/agent.py +
   agents/_base/agent.py (for the runtime
   tripwire implementation discussion)

Iter-21 priorities (in order):

1. (TOP) Backend runtime tripwire — reject too-large
   task_assignments before burning 600s on them.
   BLOCKED(blocked_on='task_too_large') routing so
   TL can re-decompose. Heuristic: description char
   count > 1500 OR ≥3 file-path tokens not on disk.
2. Demo auto-approve bash fix DONE RIGHT —
   3-iteration carry-over. Real bug: `command |
   python3 <<'PY' ... PY` heredoc-vs-pipe conflict.
   Use `python3 - "$JSON" <<'PY' ... sys.argv[1]`
   instead.
3. Architect spend watch escalating ($0.78 →
   $2.88). Investigate.
4. Re-attempt QA-emitted pending_review row
   criterion (2-iteration deferred).

After 1+2: re-run iter-19/20-shape demo and expect
a QA-emitted pending_review row with
requesting_agent='qa_engineer' for the first time
across 20+ iterations.

Workflow: plan-before-code. Draft
docs/iterations/iter_21.md first, surface for
review, then code. Run validation checks + PR
merges yourself.

Constraints unchanged from iter-20 — see CLAUDE.md
gotchas + the "Hard constraints" section of
iter_21_handoff.md.

When ready, create the iter-21 task list and
surface the plan.
```
