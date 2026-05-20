# Iteration 16 handoff

> Read **after** `CLAUDE.md`,
> `docs/iterations/iter_15_retro.md`, and
> `docs/iterations/iter_15_demo_report.md`. Replaces
> re-reading the prior conversation.

## Where we are (2026-05-20 EOD, iter-15 merged)

Iter-15 is on `main`. Same 10-agent roster. Two narrow
changes:
- `core/dispatcher/mcp_race_router.py` — replaced
  iter-10's `_MCP_RACE_PATTERNS` tuple-of-tuples with
  `_MCP_TOKEN_SET` × `_MCP_FAILURE_VERB_SET` cross-product
  matcher.
- `core/llm/claude_code_headless.py` — added
  `_is_quota_session_limit_stdout` detector; on
  `api_error_status=429` + "session limit" markers, raise
  `LLMBudgetExhaustedError` (existing iter-6 path)
  instead of `LLMInvocationError`.

iter-15 demo (`docs/iterations/iter_15_demo_report.md`):
**cross-product matcher fired in production on Backend's
first attempt** (row 214 BLOCKED mcp_unhealthy);
retry-blocked engaged; Backend's retry session did 413s
of real spec-compliance audit work + landed 2 concrete
code fixes (`report_writer.py` `## Files` section per
US-1 AC-7, updated `sample/report.md`, matching test
assertion in `tests/test_stages.py`). The retry's
terminal summary used TWO new failure verbs not in the
verb set: **"unreachable"** and **"unavailability"**.
Router didn't fire on retry → status FAILED →
`pending_review` not reached.

**iter-16's top priority is the trivial 2-verb set
extension** to finally close the loop iter-3..15 all
reached for.

## Carry-over items (priority order, from iter-15 retro + demo report)

1. **(top)** **Add `"unreachable"` and `"unavailability"`
   to `_MCP_FAILURE_VERB_SET`** in
   `core/dispatcher/mcp_race_router.py`. ~3 LOC + 1 unit
   test pinning iter-15 demo correlation
   `efbd0ccc-f607-4592-861a-aaa74973dace` row 218 summary
   verbatim. This is the design-as-intended path of the
   cross-product matcher: new phrasings are 1-line set
   additions, not new tuples. Diminishing-returns no
   longer applies.

2. **Re-run iter-15-shape demo after #1** to finally
   close the `pending_review` loop iter-3..15 all
   reached for. Backend's tree on disk
   (`examples/sandbox/idea-validator/`) has:
   - US-1 AC-7 `## Files` section in `report_writer.py`
   - Updated `sample/report.md` matching the new section
   - New matching assertion in `tests/test_stages.py`
   - All other v2 spec acceptance criteria verified
     present per iter-15 row 218 audit
   The third attempt only needs to commit + push + run
   pytest + open PR. If MCP is healthy during that
   window, chain closes; if MCP races again, the
   matcher catches it (now including "unreachable" /
   "unavailability"). Either way, recoverable.

3. **TL over-decomposition prompt hint** — Architect
   cost trajectory iter-12 $0.59 → iter-13 $0.84 →
   iter-14 $0.98 → iter-15 $0.98 (plateaued). Half the
   chain's spend goes to Architect re-deriving
   already-on-disk ADRs. Small prompt edit + 1 unit
   test: instruct TL to skip subtasks whose contracts
   are already on disk under `docs/adr/<scope>-*.md`.
   iter-16 can bundle with #1.

4. **TL Backend decomposition** — SIX-iteration carry-
   over now. Backend's iter-15 retry was 413s; if
   iter-16's third attempt needs to commit + push +
   run pytest + open PR, it could exceed the 600s
   timeout. Splitting into 2-3 chunks ("commit +
   push", "run pytest", "open PR") reduces per-chunk
   session length AND each chunk ships independently.
   Defer to iter-17 if iter-16's loop-close ships
   fast.

5. **HoldQueue persistence (Postgres-backed).**
   iter-15 demo lost QA's hold on Backend's retry-
   failure cascade again. The pattern's now 4
   iterations old (iter-12/13/14/15). Add
   `held_messages` table + startup-time hydration.
   iter-17 if iter-16 closes loop fast.

6. **`pytest-rerunfailures` plugin pin** — testcontainers
   port-mapping race flakes persist. Pin so CI
   auto-retries once.

7. **Startup-time MCP failure investigation** — the
   in-process pre-flight passes but claude -p's
   subprocess MCP fails. iter-15 saw mid-session race
   on first attempt + at-commit-time race on retry.
   Worth dedicated investigation iteration.

8. **Architect's spend watch** — plateaued at $0.98
   (iter-14 + iter-15). #3 above should drop it; check
   afterward.

9. **`audit_writer` restricted Postgres role enforcement.**
   Still deferred.

10. **Hash-chain alert job.** Still deferred.

11. **`GitHubTargetRepo` implementation.** Waiting on
    first commercial product (ADR-009).

12. **TL decomposition transactional insert.** Still
    deferred — a TL crash mid-batch leaves orphan
    child rows.

13. **`BaseAgent.handle()` template-method refactor.**
    Defer until the next agent rolls in.

## Hard constraints unchanged from iter-4..15

- **LLM substrate is `claude -p` via subscription.** Never
  set `ANTHROPIC_API_KEY`. Never use Agent SDK with an API
  key.
- **`--json-schema` validated output lives in
  `structured_output`**.
- **`--session-id` is set-once, `--resume` is resume.**
  iter-13 made the adapter restart-resilient.
- **iter-15: `api_error_status=429` → BLOCKED(budget)**
  routing in `ClaudeCodeHeadlessClient`. Recoverable via
  retry-blocked after the Max-5x reset window.
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
- HoldQueue is in-memory only (iter-17+ may change this).
- LLM metrics live in `metadata["llm"]` on the envelope;
  every agent stamps them (iter-5).
- **iter-11:** `build_retry_message` does `model_copy`
  preserving original `metadata["llm"]`. Audit readers
  should NOT double-count.
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
- **iter-13:** `ClaudeCodeHeadlessClient` extracts
  `_spawn_once(cmd, *, timeout_s, env, log)` and on
  `--session-id` collision swaps to `--resume` + caches
  the id.
- **iter-15:** `_MCP_RACE_PATTERNS` REPLACED with
  `_MCP_TOKEN_SET` × `_MCP_FAILURE_VERB_SET` cross-
  product matcher. Adding new phrasings = adding a
  set entry (not a new tuple). Three iterations of
  one-tuple-per-iteration empirically diminished
  returns; the cross-product covers the
  combinatorial space.
- **iter-15:** `api_error_status=429` + `"session
  limit"` markers in claude -p stdout → raise
  `LLMBudgetExhaustedError` → dispatcher emits
  `BLOCKED(blocked_on='budget')`.
- Demo wall-clock is 30 min initial chain + 15 min
  retry window = 45 min total.

## Ready-to-paste prompt for the new session

```
Starting Iteration 16 on the ai_team project.

First, read these in this order:

1. CLAUDE.md
2. docs/iterations/iter_15_retro.md (what just shipped:
   cross-product matcher works in production + 429 routing
   is unit-test-validated; the gap is now a trivial 2-verb
   set extension)
3. docs/iterations/iter_15_demo_report.md (real-LLM demo
   findings — cross-product fired on Backend's first
   attempt, retry-blocked engaged, retry did 413s of real
   code work, two new failure verbs "unreachable" +
   "unavailability" escape the verb set)
4. docs/iterations/iter_16_handoff.md (this file — full
   handoff context)
5. docs/adr/0001-orchestrator-choice.md,
   0008-llm-access-strategy.md

Iter-16 priority is **closing the `pending_review` loop
that iter-3..15 all reached for**. Add "unreachable" and
"unavailability" to `_MCP_FAILURE_VERB_SET` in
`core/dispatcher/mcp_race_router.py` + 1 unit test
pinning iter-15 demo row 218 verbatim (~3 LOC + 1 test),
then re-run the iter-15-shape demo. Backend's
implementation tree has US-1 AC-7 + updated sample +
test_stages.py assertion ready to commit; the third
attempt only needs to commit + push + run pytest + open
PR.

Optionally bundle TL over-decomposition prompt hint
(small) with #1: Architect cost plateaued at $0.98 and
re-derives already-on-disk ADRs.

After that: TL Backend decomposition (SIX-iteration
carry-over), HoldQueue persistence.

Workflow: plan-before-code. Draft docs/iterations/iter_16.md
first, surface for review, then code. Run validation
checks + PR merges yourself.

Constraints unchanged from iter-15 — see CLAUDE.md
gotchas + the "Hard constraints" section of
iter_16_handoff.md.

When ready, create the iter-16 task list and surface the plan.
```
