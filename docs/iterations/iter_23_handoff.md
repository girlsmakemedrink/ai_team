# Iteration 23 handoff

> Read **after** `CLAUDE.md`,
> `docs/iterations/iter_22_retro.md`, and
> `docs/iterations/iter_22_demo_report.md`.
> Replaces re-reading the prior conversation.

## Where we are (2026-05-21 EOD, iter-22 merged)

iter-22 is on `main`. iter-22 **landed the
prompt-edit bet** that iter-21's demo report
identified as the right next step: Backend's
"Scope pre-flight (turn 1)" prompt section
moves scope judgment from a Python regex to LLM
intent, and TL's mandatory Architect→Backend
`depends_on` rule forces Architect's ADR to
land before Backend's first LLM turn. Both
fired correctly in the iter-22 real-LLM demo:

- Backend self-ejected on turn 1 in **77s** (vs
  iter-21's 600s timeout) with
  `BLOCKED(blocked_on='task_too_large')`. Cost
  $0.06 vs iter-21's ~$0.50.
- TL's iter-21 Phase 2 re-decomposition handler
  picked up the BLOCKED report and emitted a
  **60%-smaller subtask** (`be_schema` ≤80 LOC
  vs original ≤200 LOC).
- Architect→Backend `depends_on` rule applied
  (audit row 332 metadata carries Architect's
  subtask UUID).
- Architect spend back at baseline ($0.93,
  within iter-19/21's $0.78-$0.80 range).
  iter-20's $2.88 was confirmed variance.

But **the QA-emitted `pending_reviews` row
remains unmet for the 4th iteration in a row**.
The cause has shifted fundamentally:
- iter-19/20/21: chain didn't reach QA because
  Backend timed out FATALLY (`status=failed`),
  cascade-dropping QA. The contract layer was
  the blocker.
- iter-22: chain auto-recovered (BLOCKED →
  re-decomp → smaller subtask) and was **in
  flight toward QA** when the demo's 30-min
  poll window expired. The **failure mode
  is now operational (wall-clock), not
  architectural**.

**iter-23's top priority is closing the
operational gap.** Two paths candidate: extend
demo poll window to 45 min (matches the
documented CLAUDE.md budget), AND/OR investigate
whether Backend's smaller scope is itself
still hitting 600s. Plus a small CLI fix
(`RECOVERABLE_BLOCKED_ON += task_too_large`)
and an optional TL prompt sharpening to USE
Architect's ADR decomposition when present.

## Carry-over items (priority order)

1. **(NEW TOP)** **Extend demo poll window to 45
   min AND/OR diagnose Backend smaller-scope
   wall-clock.** Quick path: bump the poll loop
   timeout in `scripts/demo_iter_22.sh` (clone
   to `demo_iter_23.sh`) from 30 to 45 min,
   matching CLAUDE.md's documented "30 min
   initial + 15 min retry = 45 min total"
   budget. Diagnostic path: re-run iter-22's
   demo manually with a longer window and
   capture whether audit row 344 (Backend on
   `be_schema`) eventually arrives DONE or
   FAILED.

   This is the primary blocker for the
   QA-emitted `pending_review` row criterion.

2. **(NEW)** **`core/retry/retry_blocked.py:34`:
   add `"task_too_large"` to
   `RECOVERABLE_BLOCKED_ON` frozenset.** iter-22
   demo's auto-retry step hit 422 "blocked_on='task_too_large'
   not recoverable". The value IS recoverable
   (TL auto-re-decomposes the same path), and
   the manual retry CLI should not refuse it.
   Trivial fix + pin test.

3. **(NEW, OPTIONAL)** **TL prompt: USE
   Architect's ADR decomposition when
   present.** In iter-22's demo, Architect's
   ADR-0030 defined a 5-subtask DAG with
   per-subtask LOC budgets, but TL emitted
   Backend as a single coarse `be_core` task.
   The Backend self-eject + TL re-decomp
   covered for this, but it cost ~$0.30 of
   agent turns. Sharpening TL to follow
   Architect's stated decomposition would
   prevent the self-eject loop in the common
   case. Soft prompt edit; measured by
   whether iter-23's demo shows Backend split
   along ADR-defined boundaries.

4. **Re-attempt the QA-emitted `pending_review`
   row criterion** — now **4-iteration
   deferred** (iter-19 → iter-20 → iter-21 →
   iter-22). With #1 (longer window) this
   should land in iter-23.

5. **HoldQueue persistence (Postgres-backed).**

6. **`pytest-rerunfailures` plugin pin.**

7. **TL auto-hop investigation.**

8. **TL over-decomposition prompt hint** —
   PARTIALLY addressed by iter-22 Phase 2; full
   hint (when to break work into many small
   pieces vs few large ones) still carries
   forward.

9. **`audit_writer` restricted Postgres role.**

10. **Hash-chain alert job.**

11. **`GitHubTargetRepo` implementation.**

12. **TL decomposition transactional insert.**

13. **`BaseAgent.handle()` template-method
    refactor.**

14. **`mark_task_done` / `update_task_status`
    real implementations** — iter-22 audit
    confirms no agent's prompt invokes either.
    Continue STUB.

15. **Substrate-level `--allowed-tools ""` fix.**

## Hard constraints unchanged from iter-4..22

- **LLM substrate is `claude -p` via
  subscription.** Never set
  `ANTHROPIC_API_KEY`. Never use Agent SDK with
  an API key.
- **`--json-schema` validated output lives in
  `structured_output`**.
- **`--session-id` is set-once, `--resume` is
  resume.**
- **iter-15: `api_error_status=429` →
  BLOCKED(budget)**.
- **iter-17: `--permission-mode bypassPermissions`**.
- **iter-17: All MCP servers MUST respond to
  `initialize`.**
- **iter-18:
  `mcp__ai_team_tasks__request_human_review` is
  a real handler.** `pending_reviews` rows are
  load-bearing.
- **iter-18: `tools/call` async dispatch in
  `ai_team_tasks/__main__.py` mirrors
  `ai_team_repo/__main__.py` shape.**
- **iter-19: `BaseAgent._build_env(msg)` is the
  canonical per-invocation env helper.** Sets
  `AI_TEAM_AGENT_ROLE`,
  `AI_TEAM_CORRELATION_ID`, `AI_TEAM_TASK_ID`.
- **iter-19: `ai_team_tasks.Context` has
  `default_correlation_id`** sourced from
  `AI_TEAM_CORRELATION_ID`.
- **iter-19: PM and TL `allowed_tools =
  ("Read", "Glob", "Grep")`**. Pin test
  enforces non-empty across all 10 concrete
  agents.
- **iter-19: PM `llm_timeout_s = 600`**.
- **iter-19: `_invoke_with_retries` signature
  has `msg: AgentMessage` param**.
- **iter-20: `handle_create_branch` uses
  `git worktree add`, NOT `git checkout -b`.**
  Per-MCP-server-process `_ACTIVE_WORKTREE`.
- **iter-20: TL prompt teaches Backend
  ≤200 LOC decomposition.**
- **iter-20: Demo script prunes + cleans up
  agent worktrees on entry/exit.**
- **iter-21: Backend `handle()` pre-flight
  tripwire** — defense-in-depth backstop only.
  Primary defense is now iter-22's Scope
  pre-flight prompt.
- **iter-21: TL re-decomposition handler** for
  `blocked_on='task_too_large'`. **Now
  load-bearing — iter-22 demo exercised it
  end-to-end.**
- **iter-21: Demo auto-approve uses `python3 -
  "$JSON" <<'PY' ... sys.argv[1]` pattern.**
- **iter-22: `BACKEND_REPORT_SCHEMA` has
  optional `status` + `blocked_on` fields.**
  `build_outputs` honors `status='blocked'`
  from the LLM (self-eject path); falls back
  to legacy `tests_passed` mapping for
  back-compat.
- **iter-22: `prompts/backend_developer.md`
  has a "Scope pre-flight (turn 1)" section
  near the top** instructing self-eject on
  >2 files OR >200 LOC. Pin test
  `test_backend_prompt_teaches_scope_preflight`.
- **iter-22: `prompts/team_lead.md` has a
  MANDATORY Architect→Backend `depends_on`
  rule when both roles co-occur** in the
  same decomposition. Pin test
  `test_tl_prompt_teaches_mandatory_architect_backend_depends_on`.
- **Boring stack only.**
- **Diff-cover gate is 80%. Bandit gates on
  high only.**
- **Ruff `format --check` is also a gate.
  Always run `ruff check .` (with explicit
  dot) — CI catches TC003 violations that
  `ruff check` without scope misses.**
- **Conventional commits, squash-merge,
  plan-before-code, owner approval on every
  agent task completion.**
- **Bash never raw on agents.**
- **`pending_review` rows are the
  owner-approval gate.**
- **`examples/` is the agents' TARGET_REPO
  root**.
- **PR merge: use `gh api -X PUT
  repos/.../pulls/<N>/merge -f merge_method=squash`**
  to bypass gh's local-checkout step that
  fails when main is checked out elsewhere.

## Inherited decisions (do not contradict without revisiting)

- Agent PRs target `main` on `ai_team` only
  (single-repo exception).
- Architect is **advisory**, not gating.
- TL auto-routes BLOCKED with one auto-hop max.
- TL emits a flat list of subtasks with
  explicit `depends_on` slugs.
- HoldQueue is in-memory only.
- LLM metrics live in `metadata["llm"]` on the
  envelope.
- **iter-11:** `build_retry_message` does
  `model_copy` preserving original
  `metadata["llm"]`.
- Per-stage demo task uses the v2 spec.
- MCP servers in demo configs are invoked via
  `${REPO_ROOT}/.venv/bin/python -m
  tools.mcp_servers.<name>`.
- Dispatcher synthesises `TASK_REPORT(failed)`
  for any `handle()` exception.
- **iter-6:** `LLMBudgetExhaustedError` →
  `TASK_REPORT(blocked, blocked_on='budget')`.
- **iter-6:** `HoldQueue.mark_failed` drops
  messages, the dispatcher calls
  `task_state.on_drop([task_ids])`.
- **iter-7:** Dispatcher cascades drops
  transitively.
- **iter-7:** `LLMTimeoutError` carries
  best-effort buffered stdout.
- **iter-8:** `_is_budget_exhausted_stdout` is
  substring-only.
- **iter-8:** sonnet `--max-budget-usd` default
  is $2.50; haiku $0.30, opus $4.00.
- **iter-9:** `BaseAgent.handle()` pre-flight
  calls `check_mcp_servers`.
- **iter-9:** `MCPUnhealthyError` exception →
  `BLOCKED(blocked_on='mcp_unhealthy', P2)`.
- **iter-10:** LLM-emitted
  `task_report(failed)` with MCP-race summary
  → rewritten to
  `BLOCKED(blocked_on='mcp_unhealthy')`.
- **iter-10:** Backend's prompt has an
  explicit lookup table of `command_class`
  values.
- **iter-11:** `ai-team retry-blocked
  <task_id>` CLI is the owner's recovery
  action. RECOVERABLE_BLOCKED_ON =
  {mcp_unhealthy, budget} — **iter-23 adds
  task_too_large**.
- **iter-11:** Backend's `disallowed_tools =
  ("Bash",)`.
- **iter-11:** `BaseAgent.llm_timeout_s`
  default = 600 s.
- **iter-13:** `ClaudeCodeHeadlessClient`
  extracts `_spawn_once` + retries with
  `--resume` on session-id collision.
- **iter-15:** `_MCP_RACE_PATTERNS` REPLACED
  with cross-product `_MCP_TOKEN_SET` x
  `_MCP_FAILURE_VERB_SET`.
- **iter-15:** `api_error_status=429` →
  BLOCKED(budget).
- **iter-16:** `_MCP_FAILURE_VERB_SET`
  extended with `"unreachable"` and
  `"unavailability"`.
- **iter-17:** MCP servers respond to
  `initialize` with spec-correct fields.
- **iter-17:** `--permission-mode
  bypassPermissions`.
- **iter-18:** `ai_team_tasks` MCP server has
  a real `request_human_review` handler.
- **iter-18:** `tools/call` async dispatch.
- **iter-18:** QA's prompt instructs an
  explicit `request_human_review` call.
- **iter-19:** `BaseAgent._build_env(msg)` is
  the canonical helper.
- **iter-19:** `Context.default_correlation_id`
  fallback.
- **iter-19:** PM and TL `allowed_tools =
  ("Read", "Glob", "Grep")`.
- **iter-19:** PM `llm_timeout_s = 600`.
- **iter-20:** `handle_create_branch` uses
  `git worktree add` + module-level
  `_ACTIVE_WORKTREE`.
- **iter-20:** TL prompt teaches Backend
  ≤200 LOC decomposition.
- **iter-20:** Demo script prunes + cleans up
  agent worktrees.
- **iter-21:** Backend `handle()` pre-flight
  tripwire (Python heuristic, defense-in-depth
  only).
- **iter-21:** TL re-decomp handler for
  `blocked_on='task_too_large'` is the
  recovery path. **Load-bearing as of
  iter-22 demo.**
- **iter-21:** Demo auto-approve bash pattern
  is `python3 - "$JSON" <<'PY' ... sys.argv[1]`.
- **iter-22:** `BACKEND_REPORT_SCHEMA` has
  optional `status` + `blocked_on` fields.
- **iter-22:** Backend prompt teaches "Scope
  pre-flight (turn 1)" self-eject.
- **iter-22:** TL prompt has MANDATORY
  Architect→Backend `depends_on` rule when
  both co-occur.
- Demo wall-clock budget is **45 min** per
  CLAUDE.md (30 min initial + 15 min retry).
  iter-22 demo script enforces 30 min only;
  iter-23 brings the script in line.

## What iter-22 specifically did NOT do

- **Did not produce a QA-emitted
  pending_review row**. **4-iteration
  deferred**. But the failure mode is now
  operational (poll window), not
  architectural.
- **Did not extend the demo poll window**.
  The 30-min poll cut off Backend's
  re-decomp turn before it could finish.
  iter-23 #1 addresses this.
- **Did not investigate Backend's
  smaller-scope wall-clock**. We don't know
  whether the be_schema turn (~80 LOC) would
  have completed in another 600s window or
  also timed out. iter-23 #1 addresses this.
- **Did not change TL's decomposition prompt
  to follow Architect's stated DAG**. ADR-0030
  in iter-22's demo had a 5-subtask DAG that
  TL ignored. iter-23 #3 (optional)
  addresses this.
- **Did not add `task_too_large` to
  RECOVERABLE_BLOCKED_ON**. iter-23 #2 fixes.
- **Did not remove the iter-21 Python
  tripwire.** Defense-in-depth.
- **Did not refactor `BaseAgent.handle()`
  template-method**. Backend's `handle()`
  override stayed; the refactor remains
  deferred.
- **Did not address HoldQueue persistence,
  pytest-rerunfailures, GitHubTargetRepo, or
  any other carry-over ≥ 5.**

## Ready-to-paste prompt for the new session

```
Starting Iteration 23 on the ai_team project.

First, read these in this order:

1. CLAUDE.md
2. docs/iterations/iter_22_retro.md (what just
   shipped: Backend self-eject prompt + TL
   Architect→Backend depends_on, both fired
   correctly under real LLM stress — Backend
   BLOCKED in 77s vs iter-21's 600s timeout,
   TL auto-re-decomposed to a 60%-smaller
   subtask, but the demo's 30-min poll
   expired with Backend's re-decomp turn in
   flight)
3. docs/iterations/iter_22_demo_report.md
   (real-LLM demo — contract layer fully
   validated, QA pending_review row deferred
   for the 4th iteration because of demo
   poll window length, not architectural
   failure)
4. docs/iterations/iter_23_handoff.md (this
   file — full handoff context)
5. scripts/demo_iter_22.sh + CLAUDE.md
   (for the demo poll window extension
   discussion in priority #1)
6. core/retry/retry_blocked.py (for the
   RECOVERABLE_BLOCKED_ON addition in
   priority #2)

Iter-23 priorities (in order):

1. (TOP) Extend demo poll window to 45 min
   AND/OR diagnose Backend smaller-scope
   wall-clock. Closes the operational gap
   that blocked iter-22's QA pending_review
   row criterion.

2. Add "task_too_large" to
   RECOVERABLE_BLOCKED_ON in
   core/retry/retry_blocked.py:34. Trivial
   fix + pin test. Stops the misleading
   422 in `ai-team retry-blocked`.

3. (Optional) TL prompt sharpening: USE
   Architect's stated decomposition when
   present in the ADR. Soft prompt edit.

4. Re-attempt QA-emitted pending_review row
   criterion (4-iteration deferred). With
   #1 (longer poll) this should land.

After 1+2: re-run iter-22-shape demo and
expect a QA-emitted pending_review row with
requesting_agent='qa_engineer' for the first
time across 22+ iterations.

Workflow: plan-before-code. Draft
docs/iterations/iter_23.md first, surface for
review, then code. Run validation + PR merges
yourself.

Constraints unchanged from iter-22 — see
CLAUDE.md gotchas + the "Hard constraints"
section of iter_23_handoff.md. PR merge
gotcha: use `gh api -X PUT
repos/.../pulls/<N>/merge -f
merge_method=squash` to bypass gh CLI's
local-checkout failure.

When ready, create the iter-23 task list and
surface the plan.
```
