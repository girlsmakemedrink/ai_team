# Iteration 12 handoff

> Read **after** `CLAUDE.md`,
> `docs/iterations/iter_11_retro.md`, and
> `docs/iterations/iter_11_demo_report.md`. Replaces re-reading
> the prior conversation.

## Where we are (2026-05-20 EOD, iter-11 merged)

Iter-11 is on `main`. Same 10-agent roster as iter-10; three
targeted changes that shipped the retry mechanism + defense-
in-depth around Backend + the overdue timeout refactor:

1. **`ai-team retry-blocked <task_id>` CLI +
   `POST /api/tasks/{task_id}/retry` endpoint +
   `core/retry/retry_blocked.py` pure-function helper.**
   Owner-initiated retry: read audit_log for the task, check
   eligibility (status=BLOCKED, blocked_on in {mcp_unhealthy,
   budget}, retry_attempt < 5), build a `model_copy` of the
   original assignment with **same task_id +
   correlation_id** (load-bearing — HoldQueue dependents key
   off task_id), fresh message_id + `metadata.retry_attempt`,
   sign, write to audit/feed/bus. Flip `tasks.status` from
   `blocked` back to `in_progress`. HTTP error mapping:
   404 / 409 / 422 / 429.
2. **`BackendDeveloperAgent.disallowed_tools = ("Bash",)`**
   defense-in-depth on top of iter-10's prompt edit.
   Belt-and-suspenders against Backend reaching for native
   Bash. iter-11 demo confirmed the LLM correctly perceives
   the new flag and routes to `mcp__ai_team_repo__*` instead.
3. **`BaseAgent.llm_timeout_s` default 300 → 600.** Five
   subclasses dropped the redundant override (Architect,
   Backend, Designer, DevOps, Frontend); three subclasses
   got explicit 300 (ProductManager, SRESupport, TeamLead).
   Zero behavior change; pinned by
   `tests/unit/test_agent_timeouts.py`. iter-11 demo
   confirmed Architect's 410 s opus call ran under the new
   600 s ceiling (would have timed out at 300).

iter-11 demo report at
`docs/iterations/iter_11_demo_report.md` is the single
source of truth. Headline: **retry mechanism shipped +
tested + wired end-to-end, but the demo did NOT exercise it
because Backend's failure landed in `status=failed` instead
of `status=blocked`.** Backend's summary used a NEW phrase
("`mcp__ai_team_repo__* tools were unavailable throughout
the session`") that iter-10's three substring-router pattern
tuples don't catch. iter-12's top priority is extending
those tuples then re-running the demo.

## Carry-over items (priority order, from iter-11 retro + demo report)

1. **(top)** **Extend iter-10 substring router with new
   pattern tuples** to catch the iter-11 demo's Backend
   phrasing. Candidates (pick one or two):
   - `("mcp__ai_team_repo", "unavailable")`
   - `("MCP tools", "unavailable")`
   - `("mcp_", "unavailable throughout")`

   The pattern-tuple design from iter-10 was specifically
   built to take new shapes incrementally. ≤10 LOC in
   `core/dispatcher/mcp_race_router.py` + 1 new unit test
   pinning the iter-11 demo summary verbatim. After this
   lands, run a demo.
2. **Re-run iter-11-shape demo** with #1 in place. Expected
   path:
   - Backend hits MCP race → emits `task_report(failed)` with
     the "`mcp__ai_team_repo__* unavailable`" phrase.
   - Substring router rewrites to BLOCKED before HMAC-sign.
   - Owner runs `ai-team retry-blocked <backend_task_id>`.
   - Endpoint re-emits the original assignment with fresh
     message_id + `metadata.retry_attempt=2`.
   - Backend retries; second attempt either DONE (closes
     loop → QA runs → pending_review) or BLOCKED again
     (still recoverable, owner decides).
3. **Investigate startup-time MCP failure.** iter-11
   demo's Backend reported MCP tools unavailable
   THROUGHOUT the session (different shape from iter-8/9/10
   mid-session races). Worth understanding whether the
   MCP server died before claude -p reconnected, or
   whether the in-process probe passed but the subprocess
   spawn failed. Possibly correlated with prior demo runs
   leaving `examples/sandbox/idea-validator/` on disk.
4. **Architect's $2.47 / 410 s opus call.** iter-11 saw a
   4.5× jump in Architect's per-call spend vs iter-9/10.
   Likely caused by the v2 ADR depth (nine prior ADRs +
   rich cached input). Watch whether this is steady-state
   on v2 work or a one-time consolidation cost. If
   steady-state, Architect needs decomposition.
5. **TL Backend decomposition** (now three-iteration
   carry-over from iter-9/10/11). Splitting Backend's
   task into 2-3 smaller subtasks reduces:
   - session length (iter-11 saw 473 s Backend session)
   - mid-session MCP-race exposure window
   - per-task retry burn under the 5-attempt cap
6. **HoldQueue persistence (Postgres-backed).** Still
   in-memory. iter-11's retry path doesn't make this
   worse — a restart still drops the queue. But once
   retry-blocked is actually exercised, the queue
   becomes load-bearing for the recovery story.
7. **`audit_writer` restricted Postgres role
   enforcement.** Still deferred.
8. **Hash-chain alert job.** Still deferred.
9. **`GitHubTargetRepo` implementation.** Waiting on
   first commercial product (ADR-009).
10. **TL decomposition transactional insert.** Still
    deferred — a TL crash mid-batch leaves orphan child
    rows.
11. **`pytest-rerunfailures` plugin pin** for the
    testcontainers port-mapping race. iter-7..11 local
    runs all saw it; iter-11 saw integration tests error
    on collection during one rapid double-invocation.
12. **`BaseAgent.handle()` template-method refactor.**
    Defer until the next agent rolls in.

## Hard constraints unchanged from iter-4..11

- **LLM substrate is `claude -p` via subscription.** Never
  set `ANTHROPIC_API_KEY`. Never use Agent SDK with an API
  key.
- **`--json-schema` validated output lives in
  `structured_output`**.
- **`--session-id` is set-once, `--resume` is resume.**
  Adapter switches automatically.
- **Boring stack only.** Re-read ADR-001 before considering
  any new framework.
- **Diff-cover gate is 80%. Bandit gates on high only.**
- **Ruff `format --check` is also a gate.**
- **Conventional commits, squash-merge, plan-before-code,
  owner approval on every agent task completion.**
- **Bash never raw on agents.** Use
  `mcp__ai_team_repo__run_shell` with its command-class
  enum. iter-10 strengthened this in Backend's prompt
  with an explicit command_class lookup table; iter-11
  added defense-in-depth via `--disallowed-tools "Bash"`.
- **`pending_review` rows are the owner-approval gate.**
- **`examples/` is the agents' TARGET_REPO root** (ADR-009).
  Excluded from orchestrator ruff lint AND mypy (iter-10
  Phase 4).
- **`make typecheck` works on demo-polluted workspaces**
  (iter-10 Phase 4) — no `--exclude '^examples/'`
  workaround needed.

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
- Per-stage demo task uses the v2 spec.
- MCP servers in demo configs are invoked via
  `${REPO_ROOT}/.venv/bin/python -m tools.mcp_servers.<name>`
  (iter-4).
- `claude -p` agent sessions pass
  `--permission-mode acceptEdits` by default (iter-5).
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
  Stdout cap on the non-zero-exit branch is 8 KB.
- **iter-8:** sonnet `--max-budget-usd` default is $2.50;
  haiku $0.30, opus $4.00.
- **iter-9:** `BaseAgent.handle()` pre-flight calls
  `check_mcp_servers` from `AI_TEAM_MCP_CONFIG_PATH`.
  Silent skip if env var unset.
- **iter-9:** `MCPUnhealthyError` exception →
  `BLOCKED(blocked_on='mcp_unhealthy', P2)`.
- **iter-10:** LLM-emitted `task_report(failed)` with MCP-
  race summary → rewritten to `BLOCKED(blocked_on='mcp_unhealthy')`
  by `maybe_route_mcp_race_to_blocked` in the dispatcher's
  outbound loop, BEFORE HMAC-sign. Three pattern tuples;
  add new tuples (not regex) when new shapes appear.
  **iter-12 expected to add one or two more tuples per
  carry-over item #1.**
- **iter-10:** Backend's prompt has an explicit lookup
  table of `command_class` values for git / uv / make /
  pytest. Future agents that use `run_shell` should follow
  the same pattern.
- **iter-11:** `ai-team retry-blocked <task_id>` CLI is
  the owner's recovery action for BLOCKED tasks.
  `/api/tasks/{task_id}/retry` endpoint re-emits the
  original assignment with **same task_id + correlation_id**
  + fresh `message_id` + bumped
  `metadata["retry_attempt"]`. Capped at 5 attempts.
  Eligibility: status=BLOCKED, blocked_on in
  `{"mcp_unhealthy", "budget"}`.
- **iter-11:** Backend's `disallowed_tools = ("Bash",)`.
  Forwarded by `BaseAgent._invoke_with_retries` to
  `claude -p --disallowed-tools Bash`. Defense-in-depth
  on top of iter-10's prompt lookup table.
- **iter-11:** `BaseAgent.llm_timeout_s` default = 600 s.
  Five subclasses inherit (Architect, Backend, Designer,
  DevOps, Frontend); five override to 300 (PM, QA, SRE,
  Market, TL). Pinned in `tests/unit/test_agent_timeouts.py`.
- Demo wall-clock is 30 min (iter-6, unchanged in
  iter-7/8/9/10/11).

## Ready-to-paste prompt for the new session

```
Starting Iteration 12 on the ai_team project.

First, read these in this order:

1. CLAUDE.md
2. docs/iterations/iter_11_retro.md (what just shipped, what's
   still open)
3. docs/iterations/iter_11_demo_report.md (real-LLM demo
   findings — retry mechanism shipped but didn't exercise
   end-to-end because Backend's failure phrase didn't match
   iter-10's substring router)
4. docs/iterations/iter_12_handoff.md (this file — full
   handoff context)
5. docs/adr/0001-orchestrator-choice.md,
   0004-tool-inventory.md, 0008-llm-access-strategy.md

Iter-12 priority is **extending iter-10's substring router
with new pattern tuples** to catch the iter-11 demo's
Backend phrasing ("mcp__ai_team_repo__* tools were
unavailable throughout the session"). Then re-running the
demo to finally exercise iter-11's retry-blocked end-to-end
and close the `pending_review` loop iter-3..11 all reached
for. After that: investigation of the startup-time MCP
failure (different shape from iter-8/9/10 mid-session races),
Architect's $2.47/call spend, and possibly TL Backend
decomposition (three-iteration carry-over).

Workflow: plan-before-code. Draft docs/iterations/iter_12.md
first, surface for review, then code. Run validation checks
+ PR merges yourself.

Constraints unchanged from iter-11 — see CLAUDE.md gotchas +
the "Hard constraints" section of iter_12_handoff.md.

When ready, create the iter-12 task list and surface the plan.
```
