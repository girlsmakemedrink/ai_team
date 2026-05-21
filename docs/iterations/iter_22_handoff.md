# Iteration 22 handoff

> Read **after** `CLAUDE.md`,
> `docs/iterations/iter_21_retro.md`, and
> `docs/iterations/iter_21_demo_report.md`.
> Replaces re-reading the prior conversation.

## Where we are (2026-05-21 EOD, iter-21 merged)

iter-21 is on `main`. iter-21 **shipped the
Backend runtime tripwire and the TL
re-decomposition handler with full TDD
coverage** — the contract layer is correct, 7
new unit tests pin the behavior, and all 428
unit + 50 integration tests pass. iter-21 also
**finally closed the 3-iteration heredoc-vs-pipe
auto-approve bash bug** — the new
`python3 - "$JSON" <<'PY' ... sys.argv[1]`
pattern is validated empirically (non-empty
list, empty list, OLD-pattern bug reproduced).

But the iter-21 real-LLM demo **uncovered a
deeper issue with the tripwire approach**: TL's
natural Backend `task_assignment` descriptions
are SHORT and ABSTRACT (~440 chars, no
file-path tokens) even when the underlying
scope exceeds 200 LOC of code. The heuristic
(char count >1500 OR ≥3 file-path tokens not on
disk) returned `(False, "")` and the tripwire
didn't fire. Backend then timed out at 600s and
reported FAILED (not BLOCKED), so the TL
re-decomp handler — correct as shipped — never
got the input shape it handles.

**Net effect**: iter-21's CONTRACT layer is in
place, but the heuristic was the wrong defense
for the empirical TL output shape. iter-22 must
move the scope judgment from Python regex to
the LLM — Backend's prompt should self-eject as
BLOCKED(task_too_large) when the LLM reads the
description and recognizes a >200 LOC scope.

**Architect spend escalation closed**: $0.78
(iter-19) → $2.88 (iter-20) → $0.80 (iter-21).
iter-20 was the outlier, not a trend.

**iter-22's top priorities are the Backend
self-eject prompt edit and a TL
Architect→Backend `depends_on` rule.** Both are
prerequisites for the QA-row criterion to
finally close (now 3-iteration deferred).

## Carry-over items (priority order)

1. **(NEW TOP)** **Backend self-eject prompt
   edit.** Add a "Scope pre-flight" section to
   `prompts/backend_developer.md`:

   > "Before writing any code, enumerate the
   > files you'd create or modify. If total
   > >2 files OR estimated >200 LOC of code,
   > emit `task_report(status=blocked,
   > blocked_on='task_too_large')` immediately
   > with summary echoing the original
   > description (first 800 chars). Do not
   > partially implement. Do not produce a
   > stub-then-bail report; emit the BLOCKED
   > shape and stop."

   Pair with a unit test pinning the rule in
   the prompt (mirror
   `test_tl_prompt_teaches_backend_decomposition`).

   The Python tripwire shipped in iter-21
   stays as a defense-in-depth backstop for
   obviously-too-large descriptions (>1500
   chars), but is no longer the primary
   defense. The LLM reads INTENT; the regex
   reads only TEXT.

2. **(NEW)** **TL Architect→Backend
   `depends_on` rule.** When TL's
   decomposition includes BOTH Architect AND
   Backend in the same plan, TL MUST emit
   Backend with
   `depends_on=[architect_subtask_id]`. This
   forces Backend to wait for Architect's ADR,
   which carries the scope decomposition.
   Without this rule, Backend's task gets
   dispatched in the same broadcast turn as
   Architect's (iter-21 demo audit rows
   316-321 all emitted from a single TL
   turn) and runs in parallel — Architect's
   ADR lands too late to influence Backend's
   scope.

   Edit `prompts/team_lead.md` to add the
   rule explicitly. Pin test:
   "if subtasks contain both architect and
   backend_developer, all backend_developer
   subtasks have depends_on referencing at
   least one architect subtask".

3. **(NEW, optional)** **Tripwire heuristic
   tightening**. Only do this if #1 + #2 don't
   close the 600s timeout in the iter-22
   demo. Candidates: lower description
   threshold to 400 chars, broaden file-path
   regex to match directory mentions
   (`examples/sandbox/idea-validator/` should
   count), lower file-path trigger from 3 to
   2. False-positive rate goes up; needs
   testing.

4. **Re-attempt the iter-19/20/21 QA-emitted
   `pending_review` row criterion** — now
   3-iteration deferred. Run the same demo
   shape after iter-22 #1 + #2 land. This is
   the highest-priority demo-side objective.

5. **HoldQueue persistence (Postgres-backed).**

6. **`pytest-rerunfailures` plugin pin.**

7. **TL auto-hop investigation.**

8. **TL over-decomposition prompt hint** —
   PARTIALLY addressed by carry-over #2
   above. The full hint (whole-iteration
   guidance on how much to decompose) still
   carries forward.

9. **`audit_writer` restricted Postgres role.**

10. **Hash-chain alert job.**

11. **`GitHubTargetRepo` implementation.**

12. **TL decomposition transactional insert.**

13. **`BaseAgent.handle()` template-method
    refactor.**

14. **`mark_task_done` / `update_task_status`
    real implementations** — iter-21 audit
    confirms no agent's prompt invokes
    either. Continue STUB.

15. **Substrate-level `--allowed-tools ""` fix.**

## Hard constraints unchanged from iter-4..21

- **LLM substrate is `claude -p` via subscription.**
  Never set `ANTHROPIC_API_KEY`. Never use Agent
  SDK with an API key.
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
  `mcp__ai_team_tasks__request_human_review` is a
  real handler.** `pending_reviews` rows are
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
  calls (status, run_shell,
  write_file_in_scope, open_pr) use it as cwd
  via `_effective_cwd(ctx)`.
- **iter-20: `_ACTIVE_WORKTREE` is
  per-MCP-server-process state.** Naturally
  scoped to one agent's session.
- **iter-20: TL prompt teaches Backend
  decomposition.** Backend subtasks must be
  ≤200 LOC scope; if larger, decompose into
  multiple with `depends_on` slugs. Pin test
  `tests/unit/test_team_lead_agent.py:test_tl_prompt_teaches_backend_decomposition`.
- **iter-20: `scripts/demo_iter_*.sh` prunes
  agent worktrees on entry and removes them
  on exit.** The orchestrator's
  `.claude/agent-worktrees/` directory is
  always-clean between demo runs.
- **iter-21: Backend `handle()` pre-flight
  tripwire** — `_is_task_too_large(description,
  target_repo_root)` returns
  `(True, diagnostic)` when description >1500
  chars OR ≥3 file-path tokens (regex
  `[A-Za-z][A-Za-z0-9_/.-]+\.[a-z]+`) not on
  disk. On True, emits
  `BLOCKED(blocked_on='task_too_large')`
  BEFORE LLM invocation. Backstop only —
  iter-22 #1 makes Backend's prompt the
  primary defense.
- **iter-21: TL re-decomposition handler**
  for `blocked_on='task_too_large'`. Emits
  self-targeted `TASK_ASSIGNMENT(recipient=
  TEAM_LEAD)` with original description echoed
  in the BLOCKED summary (first 800 chars) +
  `[auto-routed from <sender>]` marker +
  "re-decompose into 2-3 smaller subtasks of
  ≤100 LOC each" instruction. Anti-loop: BLOCKED
  summary with `auto-routed already` marker →
  return [].
- **iter-21: Backend `_report_to_tl(blocked_on=
  None)`** kwarg. Used by the tripwire path.
- **iter-21: Demo auto-approve uses `python3 -
  "$JSON" <<'PY' ... sys.argv[1]` pattern.**
  Do NOT re-introduce `printf | python3
  <<'PY'` — heredoc-vs-pipe conflict.
- **Boring stack only.**
- **Diff-cover gate is 80%. Bandit gates on
  high only.**
- **Ruff `format --check` is also a gate.**
- **Conventional commits, squash-merge,
  plan-before-code, owner approval on every
  agent task completion.**
- **Bash never raw on agents.**
- **`pending_review` rows are the
  owner-approval gate.**
- **`examples/` is the agents' TARGET_REPO
  root**.

## Inherited decisions (do not contradict without revisiting)

- Agent PRs target `main` on `ai_team` only
  (single-repo exception).
- Architect is **advisory**, not gating.
- TL auto-routes BLOCKED with one auto-hop
  max.
- TL emits a flat list of subtasks with
  explicit `depends_on` slugs; declares
  `depends_on` only when recipient literally
  cannot start without; emits a
  `BROADCAST(topic="tl.dag_preview")`.
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
- **iter-8:** sonnet `--max-budget-usd`
  default is $2.50; haiku $0.30, opus $4.00.
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
  action.
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
  `_ACTIVE_WORKTREE`. All other ai_team_repo
  handlers consult `_effective_cwd(ctx)`.
- **iter-20:** TL prompt teaches Backend
  ≤200 LOC decomposition rule.
- **iter-20:** Demo script prunes + cleans up
  agent worktrees on entry/exit.
- **iter-21:** Backend `handle()` pre-flight
  tripwire (Python heuristic, backstop only;
  iter-22 #1 demotes this to defense-in-depth).
- **iter-21:** TL re-decomp handler for
  `blocked_on='task_too_large'` is the
  recovery path.
- **iter-21:** Demo auto-approve bash pattern
  is `python3 - "$JSON" <<'PY' ... sys.argv[1]`.
- Demo wall-clock is 30 min initial chain +
  15 min retry window = 45 min total.

## What iter-21 specifically did NOT do

- **Did not produce a QA-emitted
  pending_review row**. 3-iteration deferred
  now (iter-19 → iter-20 → iter-21).
- **Did not change Backend's prompt**.
  iter-21 took the runtime-Python-tripwire
  bet; iter-22's #1 is the prompt-edit bet.
  Both layers can coexist (defense in depth).
- **Did not change TL's decomposition
  prompt**. iter-20's "≤200 LOC Backend"
  prompt stays. iter-22 #2 adds the
  Architect→Backend `depends_on` rule.
- **Did not refactor `BaseAgent.handle()`
  template-method**. Backend's
  `handle()` override grew during iter-21
  (pre-flight); the refactor remains
  deferred.
- **Did not investigate why Backend's coarse
  single subtask had no `depends_on`
  pointer** (it's because TL emitted all 6
  sub-assignments from one decomposition
  turn before Architect's ADR returned).
  iter-22 #2 addresses this.

## Ready-to-paste prompt for the new session

```
Starting Iteration 22 on the ai_team project.

First, read these in this order:

1. CLAUDE.md
2. docs/iterations/iter_21_retro.md (what just
   shipped: tripwire + re-decomp handler land
   cleanly with 7 new tests, but the heuristic
   didn't match TL's natural Backend description
   shape — Backend timed out at 600s anyway and
   reported FAILED not BLOCKED, so re-decomp
   didn't trigger)
3. docs/iterations/iter_21_demo_report.md
   (real-LLM demo — chain reached 5 of 6 agents,
   Backend timeout, no QA, but Architect spend
   dropped to $0.80 and Architect cited iter-21
   commit SHAs in ADR-0029)
4. docs/iterations/iter_22_handoff.md (this file
   — full handoff context)
5. agents/backend_developer/agent.py +
   prompts/backend_developer.md (for the
   self-eject prompt edit + pin test
   discussion)

Iter-22 priorities (in order):

1. (TOP) Backend self-eject prompt edit. Add
   "Scope pre-flight" section to
   prompts/backend_developer.md instructing the
   LLM to emit BLOCKED(task_too_large) on turn
   1 when the task scope >2 files OR >200 LOC.
   Pin test on the prompt rule. iter-21's
   Python tripwire stays as defense-in-depth
   backstop.

2. TL Architect→Backend depends_on rule.
   When TL decomposes a brief that includes
   both Architect AND Backend, Backend MUST
   carry depends_on=[architect_subtask_id].
   prompts/team_lead.md edit + pin test.

3. Optional: tripwire heuristic tightening.
   Only if #1 + #2 don't close the 600s timeout
   in the iter-22 demo.

4. Re-attempt QA-emitted pending_review row
   criterion (3-iteration deferred). Highest
   demo-side priority.

After 1+2: re-run iter-19/20/21-shape demo and
expect a QA-emitted pending_review row with
requesting_agent='qa_engineer' for the first
time across 21+ iterations.

Workflow: plan-before-code. Draft
docs/iterations/iter_22.md first, surface for
review, then code. Run validation checks + PR
merges yourself.

Constraints unchanged from iter-21 — see
CLAUDE.md gotchas + the "Hard constraints"
section of iter_22_handoff.md.

When ready, create the iter-22 task list and
surface the plan.
```
