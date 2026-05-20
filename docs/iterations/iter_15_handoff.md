# Iteration 15 handoff

> Read **after** `CLAUDE.md`,
> `docs/iterations/iter_14_retro.md`, and
> `docs/iterations/iter_14_demo_report.md`. Replaces re-
> reading the prior conversation.

## Where we are (2026-05-20 EOD, iter-14 merged)

Iter-14 is on `main`. Same 10-agent roster as iter-13;
one narrow change to `core/dispatcher/mcp_race_router.py`
added a sixth pattern tuple `("mcp__ai_team_repo",
"never connected")`. iter-14 demo's Backend invented a
FIFTH distinct MCP-race phrasing that doesn't match any
of the six current tuples — "MCP server `ai-team-repo`
**failed to connect**" + "tools ... were **not
available**".

**Five iterations** of one-tuple-per-iteration after
iter-10 (iter-11/12/13/14) and the LLM has produced FOUR
distinct phrasings (iter-9 baseline + iter-11 + iter-13
+ iter-14 startup-race + iter-14 not-available pattern).
The pattern-tuple approach is empirically
diminishing-returns. **iter-15's top priority is a
structural shift**, not another tuple.

## Carry-over items (priority order, from iter-14 retro + demo report)

1. **(top)** **Cross-product MCP-race matcher** in
   `core/dispatcher/mcp_race_router.py`. Generalise the
   current tuple-of-tuples into a small product of two
   narrow token sets:

   ```python
   _MCP_TOKEN_SET: frozenset[str] = frozenset({
       "MCP server",
       "MCP tools",
       "mcp__ai_team_repo",
       "mcp__ai_team_repo__",
   })

   _MCP_FAILURE_VERB_SET: frozenset[str] = frozenset({
       "never connected",
       "never finished connecting",
       "still connecting",
       "unavailable",
       "not available",
       "failed to connect",
       "could not connect",
   })
   ```

   Match if ANY token AND ANY failure verb appear in the
   summary. Same near-zero false-positive property as
   tuples (both sets are narrow + domain-specific), but
   covers the full combinatorial space. Keep
   `_MCP_RACE_PATTERNS` as a compatibility seam so the
   five existing verbatim-summary tests stay green, then
   add 2-3 new tests pinning iter-14 run #2's row 201
   summary + 2 cross-set combinations not yet seen
   in production. ~30 LOC + 5 new unit tests. Same
   ship-shape as iter-12/iter-13/iter-14 router work.

2. **Re-run iter-14-shape demo after #1** to finally
   close the `pending_review` loop iter-3..14 all
   reached for. Generalised matcher should catch any
   Backend phrasing referencing the MCP race; Backend
   gets BLOCKED instead of FAILED; retry-blocked engages;
   on second attempt Backend ideally succeeds (or hits
   another BLOCK that retries again). With `examples/
   sandbox/idea-validator/` still on disk from iter-13's
   `--resume` session, Backend's first successful attempt
   should resume from ~95% complete and emit a usable
   `task_report(done)` quickly.

3. **`api_error_status=429` → BLOCKED(blocked_on='budget')**
   in `ClaudeCodeHeadlessClient`. iter-14 run #1 burned
   $0.59 on Architect's quota-truncated session that
   could have been routed to BLOCKED + retried after
   12:10 MSK reset. ~20 LOC: in `_parse_response` (or the
   invoke method), detect `api_error_status=429` in the
   `result` JSON's stdout payload OR the explicit
   `LLMBudgetExhaustedError` path; raise a distinct
   exception the dispatcher routes to BLOCKED instead of
   FAILED. 2 unit tests pinning the iter-14 run #1
   stdout shape verbatim + 1 regression for non-429
   errors (still LLMInvocationError).

4. **TL Backend decomposition** — SIX-iteration
   carry-over (iter-9/10/11/12/13/14). Backend's
   monolithic shape keeps exposing it to the MCP race
   regardless of session length (iter-14 saw a 75s
   startup-time race + iter-13 saw a 544s mid-session
   race; both forms). Splitting into 2-3 chunks reduces
   the per-chunk MCP exposure window AND ships
   independently. Real iter-16 if scope allows after #1
   closes the loop tactically.

5. **TL over-decomposition prompt hint.** Architect cost
   trajectory iter-12 $0.59 → iter-13 $0.84 → iter-14
   $0.98 confirms re-derivation. Small prompt edit + 1
   unit test verifying TL passes a "skip subtasks whose
   contracts are already on disk under
   `docs/adr/<scope>-*.md`" instruction.

6. **HoldQueue persistence (Postgres-backed).** Still
   in-memory; iter-13/14 demos both lost QA's held
   assignment on cascade. Add `held_messages` table +
   startup-time hydration. Defer until #1+#3 ship.

7. **`pytest-rerunfailures` plugin pin** — iter-12 +
   iter-13 saw integration suite flakes from
   testcontainers port-mapping race. Pin so CI
   auto-retries once.

8. **Startup-time MCP failure investigation** —
   iter-14 demo run #2 reproduced this cleanly:
   Backend's 75s session ended with three failed
   ToolSearch retries. The iter-9 pre-flight gate's
   in-process probe passes (it's an HTTP-style call to
   the registered MCP server), but claude -p's spawned
   MCP subprocess fails. Hypothesis: a difference between
   how the orchestrator spawns the MCP and how `claude -p`
   spawns it. Worth a focused investigation iteration —
   the structural fix may obviate generalised matchers
   entirely.

9. **Architect's spend watch** — iter-12 $0.59 →
   iter-13 $0.84 → iter-14 $0.98. Consistent +$0.15/it
   trajectory. Likely correlates with re-deriving
   already-on-disk ADRs (see #5). Worth confirming with
   a one-line script that diffs Architect's `task_report`
   summary vs disk state.

10. **`audit_writer` restricted Postgres role enforcement.**
    Still deferred.

11. **Hash-chain alert job.** Still deferred.

12. **`GitHubTargetRepo` implementation.** Waiting on
    first commercial product (ADR-009).

13. **TL decomposition transactional insert.** Still
    deferred — a TL crash mid-batch leaves orphan
    child rows.

14. **`BaseAgent.handle()` template-method refactor.**
    Defer until the next agent rolls in.

## Hard constraints unchanged from iter-4..14

- **LLM substrate is `claude -p` via subscription.** Never
  set `ANTHROPIC_API_KEY`. Never use Agent SDK with an API
  key.
- **`--json-schema` validated output lives in
  `structured_output`**.
- **`--session-id` is set-once, `--resume` is resume.**
  iter-13 made the adapter restart-resilient: on
  `--session-id` collision it falls back to `--resume`
  + caches the id for subsequent invokes.
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
- HoldQueue is in-memory only (iter-15+ may change this).
- LLM metrics live in `metadata["llm"]` on the envelope;
  every agent stamps them (iter-5).
- **iter-11:** `build_retry_message` does `model_copy`
  preserving original `metadata["llm"]`. The retry
  audit row inherits the original assignment's LLM
  metrics; audit readers should NOT double-count.
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
  Tuple-of-tuples pattern; **iter-15 likely
  generalises this to a cross-product of two narrow
  token sets** (see carry-over #1).
- **iter-10:** Backend's prompt has an explicit lookup
  table of `command_class` values for git / uv / make /
  pytest.
- **iter-11:** `ai-team retry-blocked <task_id>` CLI is
  the owner's recovery action for BLOCKED tasks.
  `/api/tasks/{task_id}/retry` endpoint re-emits with
  **same task_id + correlation_id** + fresh
  `message_id` + bumped `metadata["retry_attempt"]`.
  Capped at 5 attempts. Eligibility: status=BLOCKED,
  blocked_on in `{"mcp_unhealthy", "budget"}`.
- **iter-11:** Backend's `disallowed_tools = ("Bash",)`.
- **iter-11:** `BaseAgent.llm_timeout_s` default = 600 s.
- **iter-12:** `_MCP_RACE_PATTERNS` extended with
  `("mcp__ai_team_repo", "unavailable")` +
  `("MCP tools", "unavailable")`.
- **iter-13:** `ClaudeCodeHeadlessClient` extracts
  `_spawn_once(cmd, *, timeout_s, env, log) ->
  (returncode, stdout, stderr)` and on `--session-id`
  collision (stderr matches `"Session ID"` +
  `"already in use"`) swaps to `--resume` + caches the
  id. Restart-resilient.
- **iter-14:** `_MCP_RACE_PATTERNS` extended with
  `("mcp__ai_team_repo", "never connected")`. iter-15
  may replace the tuple-of-tuples wholesale with a
  cross-product matcher (carry-over #1).
- Demo wall-clock is 30 min initial chain + 15 min
  retry window = 45 min total (iter-6/13/14, unchanged).
- **iter-14 demo finding:** quota session-limit hit
  ($0.59 burn) is currently a hard fail. iter-15
  carry-over #3 routes `api_error_status=429` to
  BLOCKED so it's recoverable via retry-blocked.

## Ready-to-paste prompt for the new session

```
Starting Iteration 15 on the ai_team project.

First, read these in this order:

1. CLAUDE.md
2. docs/iterations/iter_14_retro.md (what just shipped,
   what's still open — including the empirical
   diminishing-returns of pattern-tuple approach)
3. docs/iterations/iter_14_demo_report.md (real-LLM demo
   findings — outcome 4c, fifth distinct Backend MCP-race
   phrasing escapes router, full cross-product matcher
   design under "Failure 1 → option 1")
4. docs/iterations/iter_15_handoff.md (this file — full
   handoff context)
5. docs/adr/0001-orchestrator-choice.md,
   0008-llm-access-strategy.md

Iter-15 priority is **a structural shift in the MCP-race
matcher**, not another tuple. Replace (or co-exist with)
the tuple-of-tuples `_MCP_RACE_PATTERNS` with a
cross-product of two narrow token sets:
`_MCP_TOKEN_SET` ({"MCP server", "MCP tools",
"mcp__ai_team_repo", "mcp__ai_team_repo__"}) ×
`_MCP_FAILURE_VERB_SET` ({"never connected", "never
finished connecting", "still connecting", "unavailable",
"not available", "failed to connect", "could not
connect"}). Match if ANY token AND ANY failure verb
co-occur. ~30 LOC + 5 new unit tests pinning all 5
previously observed phrasings + 2 unseen-but-plausible
combinations.

After that: re-run iter-14-shape demo (Backend's tree on
disk from iter-13's --resume session should let the chain
finally close end-to-end), 429→BLOCKED routing, TL Backend
decomposition (SIX-iteration carry-over).

Workflow: plan-before-code. Draft docs/iterations/iter_15.md
first, surface for review, then code. Run validation
checks + PR merges yourself.

Constraints unchanged from iter-14 — see CLAUDE.md
gotchas + the "Hard constraints" section of
iter_15_handoff.md.

When ready, create the iter-15 task list and surface the plan.
```
