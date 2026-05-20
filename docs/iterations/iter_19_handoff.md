# Iteration 19 handoff

> Read **after** `CLAUDE.md`,
> `docs/iterations/iter_18_retro.md`, and
> `docs/iterations/iter_18_demo_report.md`. Replaces
> re-reading the prior conversation.

## Where we are (2026-05-20 EOD, iter-18 merged)

iter-18 is on `main`. iter-18 **closed the formal
owner-approval loop end-to-end for the first time in
18 iterations**: the `mcp__ai_team_tasks__request_human_review`
MCP tool now INSERTs real `pending_reviews` rows
(replacing the iter-0 stub) and the row was
successfully resolved via the existing
`/api/reviews/{id}/approve` endpoint during the
iter-18 demo.

iter-18 demo run #2 produced the **first
`pending_review` row across 18 iterations**
(`2b260721-c3eb-4144-aee4-7b636980a799`, written by
PM, resolved to `approved` via manual
`ai-team approve` after the demo's bash auto-approve
step crashed on a JSON parse issue).

**The deliverable is validated**, but five caveats
surfaced during the demo that iter-19 must address.
These are listed in priority order below.

## Carry-over items (priority order, from iter-18 retro)

1. **(top)** **PM allow-list hardening.**
   `ProductManagerAgent.allowed_tools = ()` triggers
   claude -p's permissive default — letting all
   configured MCP tools through. PM called
   `request_human_review` unprompted during the demo.
   Re-audit `TeamLeadAgent` (same `()` pattern). Two
   options:
   - Set explicit non-empty `allowed_tools` per agent
     (whitelist).
   - Special-case empty as "no tools" in
     `core/llm/claude_code_headless.py:199-200` (pass
     `--allowed-tools ""` rather than skip).

   The whitelist approach is safer (matches Architect/
   Backend/QA/etc).

2. **(top)** **Per-message env injection in
   `BaseAgent.handle()`.** The MCP server's
   `Context.from_env()` reads `AI_TEAM_AGENT_ROLE`
   from env to default the `requesting_agent` field
   when the LLM forgets to pass `agent` in args. The
   dispatcher does NOT set this per-invocation, so
   the demo row got `requesting_agent='unknown'`.

   Wire: in `agents/_base/agent.py:_invoke_with_retries`,
   construct an env dict merging:
   - `AI_TEAM_AGENT_ROLE`: `self.role.value`
   - `AI_TEAM_CORRELATION_ID`: `str(msg.correlation_id)`
   - `AI_TEAM_TASK_ID`: incoming task_id where
     available
   Pass into `self._llm.invoke(env={..., **self.mcp_env})`.
   Extend `ai_team_tasks/handlers.py:Context.from_env`
   to also read `AI_TEAM_CORRELATION_ID` if present
   (override-via-args still wins; this is fallback).

3. **`ProductManagerAgent.llm_timeout_s` 300 → 600.**
   iter-17 saw PM at 277s (92% of cap); iter-18 run
   #1 hit the 300s wall. Update both
   `agents/product_manager/agent.py:109` and the pin
   in `tests/unit/test_agent_timeouts.py:41`.
   Aligns with Backend/Architect/Designer/Frontend/
   DevOps.

4. **Demo poll-loop QA-specific.**
   `scripts/demo_iter_N.sh` polls for
   `review_count >= 1`. PM's row triggered exit
   mid-chain in iter-18 run #2. Filter on
   `requesting_agent='qa_engineer'` (when iter-19
   #1 lands, this works correctly).

5. **Demo auto-approve bash fallback.**
   `scripts/demo_iter_18.sh:212-228` crashed on
   `json.load(sys.stdin)` with empty input. Defensive
   fix: `R="${REVIEWS_JSON:-[]}"` belt-and-braces
   between the curl and the python pipeline.

6. **TL Backend decomposition** — now EIGHT-iteration
   carry-over. iter-17 Backend session = 462s (77%
   of 600s timeout). iter-18 demo's chain didn't
   reach Backend; defer to first iter that does.

7. **HoldQueue persistence (Postgres-backed)** —
   in-memory queue still loses held assignments on
   restart.

8. **`pytest-rerunfailures` plugin pin** — CI flake
   on `test_transitive_drops_cascade_through_hold_queue`
   carries over.

9. **Agents'-branch-isolation** (iter-17 retro #7).
   No recurrence in iter-18 (chain didn't reach
   Backend), but worth investigation when iter-19's
   chain reaches it.

10. **TL auto-hop investigation** — iter-17 handoff
    #3, still deferred. Confirm whether the iter-2c
    BLOCKED auto-hop is wired + firing.

11. **TL over-decomposition prompt hint** —
    Architect re-derives ADRs already on disk.
    Small prompt edit.

12. **Startup-time MCP failure investigation** —
    **closed by iter-17**. No further action.

13. **Architect's spend watch** — iter-17 run #3
    Architect: $0.87. Plateau. The TL over-
    decomposition hint (#11) addresses.

14. **`audit_writer` restricted Postgres role
    enforcement.** Still deferred.

15. **Hash-chain alert job.** Still deferred.

16. **`GitHubTargetRepo` implementation.** Waiting on
    first commercial product (ADR-009).

17. **TL decomposition transactional insert.** Still
    deferred.

18. **`BaseAgent.handle()` template-method
    refactor.** Defer until the next agent rolls in.

19. **`mark_task_done` + `update_task_status` real
    impl** — iter-18 left these as STUBS pending an
    agent-prompt audit. If iter-19 finds any agent's
    prompt actually calls one of these, implement;
    otherwise mark deprecated.

## Hard constraints unchanged from iter-4..18

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
  each `__main__.py`. 18 tests pin the handshake.
- **iter-18: `mcp__ai_team_tasks__request_human_review`
  is a real handler — `pending_reviews` rows are now
  load-bearing**, not theoretical. `mark_task_done` +
  `update_task_status` remain STUBS with regression
  tests pinning their stub envelopes.
- **iter-18: `tools/mcp_servers/ai_team_tasks/__main__.py`
  routes `tools/call` async via `HANDLERS` map** like
  `ai_team_repo/__main__.py`. Both servers share a
  structurally identical handler pattern.
- **iter-18: `request_human_review` inputSchema is
  tight**: `required: [summary, correlation_id]`,
  `additionalProperties: false`. Schema regression
  test pins the shape.
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
  INSERTs `PendingReview`. STUBS preserved (regression-
  tested) for the other two tools pending a prompt audit.
- **iter-18:** `tools/call` async dispatch in
  `ai_team_tasks/__main__.py` mirrors
  `ai_team_repo/__main__.py` shape. Both servers'
  `_build_response` returns None for `tools/call`
  (deferred to the async loop).
- **iter-18:** QA's prompt instructs an explicit
  `request_human_review` call before final JSON.
  Empirically untested for QA specifically — iter-18's
  demo row was written by PM (not QA) because PM's
  empty allow-list let it through. iter-19 #1 hardens
  this.
- Demo wall-clock is 30 min initial chain + 15 min
  retry window = 45 min total.

## Ready-to-paste prompt for the new session

```
Starting Iteration 19 on the ai_team project.

First, read these in this order:

1. CLAUDE.md
2. docs/iterations/iter_18_retro.md (what just
   shipped: real request_human_review handler,
   first pending_review row + manual close-the-loop
   across 18 iterations)
3. docs/iterations/iter_18_demo_report.md (real-LLM
   demo — two runs, $3.43 total, run #2 produced
   the historic first row)
4. docs/iterations/iter_19_handoff.md (this file —
   full handoff context)
5. docs/adr/0001-orchestrator-choice.md,
   0004-tool-inventory.md (for the PM allow-list
   hardening discussion)

Iter-19 priorities (in order):

1. PM allow-list hardening — PM (and TL — both
   have allowed_tools=() which claude -p treats
   as permissive default). Demo found this when
   PM unprompted-called the new MCP tool.
2. Per-message env injection in
   BaseAgent.handle() — set AI_TEAM_AGENT_ROLE +
   AI_TEAM_CORRELATION_ID so the iter-18 handler's
   fallback populates correctly.
3. ProductManagerAgent.llm_timeout_s 300 → 600
   (matches the LLM-bound majority).
4. Demo poll-loop QA-specific (filter on
   requesting_agent='qa_engineer').
5. Demo auto-approve bash fallback fix.

After 1+2+3: re-run iter-18-shape demo and expect
QA-emitted pending_review with
requesting_agent='qa_engineer' (not unknown / not
PM).

Workflow: plan-before-code. Draft
docs/iterations/iter_19.md first, surface for
review, then code. Run validation checks + PR
merges yourself.

Constraints unchanged from iter-18 — see CLAUDE.md
gotchas + the "Hard constraints" section of
iter_19_handoff.md.

When ready, create the iter-19 task list and
surface the plan.
```
