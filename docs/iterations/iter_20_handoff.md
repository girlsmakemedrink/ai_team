# Iteration 20 handoff

> Read **after** `CLAUDE.md`,
> `docs/iterations/iter_19_retro.md`, and
> `docs/iterations/iter_19_demo_report.md`.
> Replaces re-reading the prior conversation.

## Where we are (2026-05-21 EOD, iter-19 merged)

iter-19 is on `main`. iter-19 **closed iter-18's
five demo caveats by code change** (per-message env
injection, ai_team_tasks correlation_id fallback,
PM/TL explicit allow-list, PM 600s timeout, demo
poll/auto-approve fixes) and **passed all static
gates** (418 unit + 50 integration + smoke-llm +
ruff + mypy strict + bandit High:0). 18 new unit
tests pin the contracts.

The real-LLM end-to-end demo did **NOT** close the
formal owner-approval loop through QA. Backend
timed out at 600s (9-iteration carry-over → now
10), dependents cascade-dropped, no QA-emitted
`pending_reviews` row was written. The demo also
surfaced the **first concrete materialisation of
the iter-17 retro #7 carry-over** — the Backend
agent ran `git checkout agent/backend_developer/...`
on the orchestrator's own worktree mid-chain.

iter-19 demo cost ~$2 (under $5 ceiling). All
iter-19 commits intact on `main` post-recovery.

**iter-20's two top priorities are agent-branch-
isolation and TL Backend decomposition. Both are
prerequisites for the iter-19 demo's QA-row
criterion to actually validate end-to-end.**

## Carry-over items (priority order, from iter-19 retro)

1. **(NEW TOP)** **Agent-branch-isolation in
   `mcp__ai_team_repo__run_shell`.** Backend's
   `git checkout agent/backend_developer/...`
   switched the orchestrator's HEAD mid-chain
   (iter-19 demo). My iter-19 commits stayed
   intact on `worktree-iter-19` but the next demo
   run would silently use iter-2 era MCP code
   from disk for any newly spawned subprocess.
   Two fix options:
   - (a) **Forbid `git checkout` / `git reset` /
     `git switch` against the orchestrator's
     worktree** in `tools/mcp_servers/ai_team_repo/`'s
     `command_class` allow-list. Detect via comparing
     the cwd path prefix; reject if not under the
     agent's TARGET_REPO scope.
   - (b) **Per-agent `git worktree add`**: spawn
     each agent's `claude -p` with `cwd=<per-branch-checkout>`
     so its git operations target an isolated tree.
     Requires `BaseAgent.handle()` to call
     `target_repo.checkout_branch(agent_branch)`
     before `_llm.invoke`. Largest durable change.

   **Recommended**: (a) as the iter-20 fix
   ("forbid the dangerous verbs"); (b) tracked as
   iter-21+ work.

2. **(NEW)** **TL Backend decomposition** — now
   10-iteration carry-over. iter-19 demo's Backend
   timeout at 600s is THE failure mode per demo.
   Concrete approach to ship in iter-20:
   - Add to TL's system prompt: "Backend tasks
     must be scoped to ≤200 LOC of new/modified
     code; if larger, decompose into 2+ Backend
     subtasks linked via `depends_on` slugs."
   - Add a `BackendDeveloperAgent` runtime
     tripwire that aborts (BLOCKED with
     `blocked_on='task_too_large'`) when the
     incoming description's estimate exceeds a
     threshold.
   - Validate by re-running the iter-19 demo and
     confirming Backend reports `done` within 600s.

3. **(NEW)** **Re-run iter-19 demo under iter-20
   fixes**. The demo's specific success criterion
   (QA-emitted pending_review with
   `requesting_agent='qa_engineer'`) was deferred
   from iter-19. Once iter-20 #1 + #2 land,
   re-attempt the demo. Expected outcome: full
   7-agent chain completes, QA writes the row,
   demo's auto-approve closes it.

4. **HoldQueue persistence (Postgres-backed)** —
   in-memory queue still loses held assignments
   on restart.

5. **`pytest-rerunfailures` plugin pin** — CI flake
   on `test_transitive_drops_cascade_through_hold_queue`.

6. **TL auto-hop investigation** — iter-17 handoff
   #3, still deferred.

7. **TL over-decomposition prompt hint** —
   Architect re-derives ADRs already on disk.
   Small prompt edit.

8. **Architect's spend watch** — iter-19 run #1
   Architect: $0.78. Plateau. The TL
   over-decomposition hint (#7) addresses.

9. **`audit_writer` restricted Postgres role
   enforcement.** Still deferred.

10. **Hash-chain alert job.** Still deferred.

11. **`GitHubTargetRepo` implementation.** Waiting
    on first commercial product (ADR-009).

12. **TL decomposition transactional insert.**
    Still deferred.

13. **`BaseAgent.handle()` template-method
    refactor.** Defer until next agent rolls in.

14. **`mark_task_done` / `update_task_status` real
    implementations** — iter-19 audited prompts,
    confirmed no agent invokes either. Continue to
    leave as STUBS with regression tests pinning
    the stub envelopes.

15. **Substrate-level `--allowed-tools ""` fix**
    in `core/llm/claude_code_headless.py:199-200`
    (special-case empty tuple as
    `--disallowed-tools "*"` or equivalent).
    iter-19 deferred in favor of the explicit
    pin-test approach; iter-20 could revisit if a
    new agent regressed.

## Hard constraints unchanged from iter-4..19

- **LLM substrate is `claude -p` via subscription.** Never
  set `ANTHROPIC_API_KEY`. Never use Agent SDK with an API
  key.
- **`--json-schema` validated output lives in
  `structured_output`**.
- **`--session-id` is set-once, `--resume` is resume.**
- **iter-15: `api_error_status=429` → BLOCKED(budget)** —
  production-validated in iter-17.
- **iter-17: `--permission-mode bypassPermissions`** —
  security boundary is orchestrator-level (allow-list +
  MCP path scope + run_shell command_class enum).
- **iter-17: All MCP servers MUST respond to
  `initialize`.** `_build_response(msg)` pure helper in
  each `__main__.py`. 18 tests pin the handshake.
- **iter-18: `mcp__ai_team_tasks__request_human_review`
  is a real handler — `pending_reviews` rows are now
  load-bearing**, not theoretical. `mark_task_done` +
  `update_task_status` remain STUBS with regression
  tests.
- **iter-18: `tools/mcp_servers/ai_team_tasks/__main__.py`
  routes `tools/call` async via `HANDLERS` map** like
  `ai_team_repo/__main__.py`.
- **iter-18: `request_human_review` inputSchema is
  tight**: `required: [summary, correlation_id]`,
  `additionalProperties: false`. Schema regression
  test pins the shape.
- **iter-19: `BaseAgent._build_env(msg)` is the
  canonical helper for per-invocation env
  injection.** Sets `AI_TEAM_AGENT_ROLE`,
  `AI_TEAM_CORRELATION_ID`, and (when present)
  `AI_TEAM_TASK_ID`, merging `mcp_env` on top.
  Both the default `handle()` path (via
  `_invoke_with_retries`) and the custom PM / TL
  `handle()` paths consume it.
- **iter-19: `ai_team_tasks` `Context` has a
  `default_correlation_id: str | None` field**
  sourced from `AI_TEAM_CORRELATION_ID`.
  `handle_request_human_review` falls back to it
  when args omit `correlation_id`. Same
  defense-in-depth pattern as iter-18's
  `default_agent`.
- **iter-19: PM and TL `allowed_tools = ("Read",
  "Glob", "Grep")`** — explicit non-empty
  whitelist replacing the iter-1/iter-3 `()`
  permissive-default leak. Pin test
  (`tests/unit/test_agent_allowed_tools_pin.py`)
  prevents regression across all 10 concrete
  agents.
- **iter-19: PM `llm_timeout_s = 600`** (was 300).
- **iter-19: `scripts/demo_iter_19.sh` poll filters
  on `requesting_agent='qa_engineer'`**;
  auto-approve uses `${REVIEWS_JSON:-[]}` +
  `printf '%s'` belt-and-braces fallback.
- **Boring stack only.** Re-read ADR-001 before
  considering any new framework.
- **Diff-cover gate is 80%. Bandit gates on high only.**
- **Ruff `format --check` is also a gate.**
- **Conventional commits, squash-merge, plan-before-code,
  owner approval on every agent task completion.**
- **Bash never raw on agents.** iter-10 prompt + iter-11
  `--disallowed-tools "Bash"` defense-in-depth.
- **`pending_review` rows are the owner-approval gate.**
  As of iter-18 this is real infrastructure, not a
  documented contract.
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
- **iter-18:** `ai_team_tasks` MCP server has a real
  `request_human_review` handler — `Context` dataclass
  + `HANDLERS` map + `handle_request_human_review`
  INSERTs `PendingReview`. STUBS preserved for the
  other two tools pending a prompt audit.
- **iter-18:** `tools/call` async dispatch in
  `ai_team_tasks/__main__.py` mirrors
  `ai_team_repo/__main__.py` shape.
- **iter-18:** QA's prompt instructs an explicit
  `request_human_review` call before final JSON.
- **iter-19:** `BaseAgent._build_env(msg)` returns the
  canonical per-invocation env dict. PM and TL custom
  `handle()`s consume it; `_invoke_with_retries`
  threads it for the other 8 agents.
- **iter-19:** `Context.default_correlation_id`
  defense-in-depth fallback.
- **iter-19:** PM and TL `allowed_tools = ("Read",
  "Glob", "Grep")`. Pin test
  `test_agent_allowed_tools_pin.py` enforces
  non-empty on all 10 concrete agents.
- **iter-19:** PM `llm_timeout_s = 600`.
- **iter-19:** `_invoke_with_retries` signature
  added `msg: AgentMessage` param.
- Demo wall-clock is 30 min initial chain + 15 min
  retry window = 45 min total (iter-19's run
  fail-fast'd at ~25 min on Backend timeout).

## What iter-19 specifically did NOT do

- **Did not change ADR-0004's tool matrix.** The
  matrix remains the source of truth for what each
  agent *may* have. iter-19 closed the gap between
  the matrix and what each agent *actually has*
  for PM and TL specifically.
- **Did not implement substrate-level `()` →
  `--disallowed-tools "*"` translation.**
- **Did not address the iter-17 retro #7 carry-over
  agents'-branch-isolation.** The iter-19 demo
  surfaced its first concrete manifestation;
  iter-20 must close it (this handoff #1).
- **Did not produce a QA-emitted pending_review
  row** in the demo — Backend timeout cascade-
  dropped QA. Deferred to iter-20 #3 once #1 + #2
  are in.

## Ready-to-paste prompt for the new session

```
Starting Iteration 20 on the ai_team project.

First, read these in this order:

1. CLAUDE.md
2. docs/iterations/iter_19_retro.md (what just
   shipped: 5-caveat closure for iter-18,
   18 new pin tests, partial demo)
3. docs/iterations/iter_19_demo_report.md (real-LLM
   demo — partial success + branch-isolation
   surprise: Backend ran `git checkout` on the
   orchestrator's worktree)
4. docs/iterations/iter_20_handoff.md (this file —
   full handoff context)
5. docs/adr/0004-tool-inventory.md (for the
   command_class run_shell allow-list hardening
   discussion in priority #1)

Iter-20 priorities (in order):

1. (TOP) Agent-branch-isolation in run_shell —
   forbid `git checkout` / `git reset` / `git
   switch` against the orchestrator's worktree.
   Backend ran `git checkout agent/.../...` on
   our HEAD mid-chain in iter-19 demo. First
   concrete materialisation of iter-17 retro #7.
2. TL Backend decomposition — 10-iteration
   carry-over. Backend's 600s timeout has now
   taken out 4+ demo runs across iter-15..19.
   Stop deferring. Add a "≤200 LOC" rule to TL's
   prompt + a Backend runtime tripwire.
3. Re-run iter-19 demo under iter-20's fixes —
   same QA-emitted pending_review criterion
   that iter-19 deferred.

After 1+2: re-run iter-19-shape demo and expect
a QA-emitted pending_review row with
requesting_agent='qa_engineer' for the first time
in 19 iterations.

Workflow: plan-before-code. Draft
docs/iterations/iter_20.md first, surface for
review, then code. Run validation checks + PR
merges yourself.

Constraints unchanged from iter-19 — see CLAUDE.md
gotchas + the "Hard constraints" section of
iter_20_handoff.md.

When ready, create the iter-20 task list and
surface the plan.
```
