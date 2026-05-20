# Iteration 14 handoff

> Read **after** `CLAUDE.md`,
> `docs/iterations/iter_13_retro.md`, and
> `docs/iterations/iter_13_demo_report.md`. Replaces re-reading
> the prior conversation.

## Where we are (2026-05-20 EOD, iter-13 merged)

Iter-13 is on `main`. Same 10-agent roster as iter-12; one
narrow change to `core/llm/claude_code_headless.py` made the
`ClaudeCodeHeadlessClient` adapter restart-resilient.

`ClaudeCodeHeadlessClient.invoke()` now:
1. Builds cmd (with `--session-id` if first claim of the
   id in this process, `--resume` otherwise).
2. Calls `_spawn_once(cmd, ...)` — a new helper that spawns
   claude -p once and returns `(returncode, stdout, stderr)`.
3. If returncode != 0 AND session_id was passed AND
   `--session-id` is in cmd AND stderr matches both
   `"Session ID"` + `"already in use"`: swaps
   `--session-id` for `--resume`, adds the id to
   `_claimed_sessions` cache, calls `_spawn_once` again.
4. Any other non-zero exit raises `LLMInvocationError`
   exactly as before (regression-safe).

iter-13 demo report at
`docs/iterations/iter_13_demo_report.md` is the single
source of truth. **Headline**: the fix FIRED IN
PRODUCTION with conclusive evidence — dispatcher
structlog line `llm.invoke.session_collision.retry_with_resume`
captured at 08:08:07 UTC, `session_id=1e7bb0db-...`. Backend's
`--resume` session preserved 2.1 M cached tokens and wrote
7 source/test files including ADR-0021's exit-code table.
**But** Backend's retry session hit a NEW MCP-race
phrasing mid-session that escapes the current substring
router tuples — "mcp__ai_team_repo server never
connected" (mixes iter-12's prefix with iter-10's
suffix). iter-14's top priority is one more tuple.

## Carry-over items (priority order, from iter-13 retro + demo report)

1. **(top)** **Add `("mcp__ai_team_repo", "never connected")`
   to `_MCP_RACE_PATTERNS`** in
   `core/dispatcher/mcp_race_router.py:39-58`. Catches the
   iter-13 demo's exact phrasing where Backend mixed
   iter-12's mcp__-prefixed tool name with iter-10's
   "never connected" failure verb. ~3 LOC + 1 unit test
   pinning iter-13 demo correlation
   `1e7bb0db-a109-4521-ad03-175e9fdd3d67` row 180
   summary verbatim. Same pattern as iter-12's tuple
   extension; see commit `f5bd44b` as the template.

2. **Re-run iter-13-shape demo after #1** to finally
   close the `pending_review` loop iter-3..13 all
   reached for. The chain's third attempt should benefit
   from:
   - Substring router now catching the iter-13 phrasing
     → Backend BLOCKED rather than FAILED.
   - iter-13 fallback handling any post-restart
     --session-id collision automatically.
   - Backend's implementation tree on disk
     (`examples/sandbox/idea-validator/`) from iter-13's
     `--resume` session — the third attempt resumes from
     ~95% complete.
   Expected outcome:
   - Backend BLOCKED → retry → DONE (writes the
     remaining few files + commits + opens PR).
   - QA picks up the held assignment, runs the v2
     smoke + regression suite, emits
     `request_human_review`.
   - `pending_review` row appears, demo auto-approves,
     chain closes. **The long-awaited end-to-end close.**

3. **TL Backend decomposition** — now FIVE-iteration
   carry-over (iter-9/10/11/12/13). Backend's monolithic
   sessions (iter-13: 544 s first + 157 s retry = 701 s
   total) keep hitting the mid-session MCP race. TL
   should split Backend's task into 2-3 chunks (e.g.,
   "models + pipeline core", "CLI + factories", "tests +
   refresh_sample.sh") so each individual session is
   shorter AND ships independently. Real iter-14 scope
   if time allows after #1+#2.

4. **HoldQueue persistence (Postgres-backed).** iter-13
   demo's restart between BLOCKED and retry lost QA's
   held assignment; QA's `tasks` row is orphaned at
   `in_progress`. Add a `held_messages` table; on hold:
   INSERT; on release: DELETE; on startup: SELECT all
   and rebuild the in-memory `HoldQueue`. iter-14 if
   #3 ships separately.

5. **TL over-decomposition prompt hint.** Architect's
   iter-12 row 160 + iter-13 row 175 BOTH self-flagged
   that TL re-decomposes v2 from scratch despite ADR-
   0019/0020/0021 already covering the contracts. Add
   a prompt hint to TL: "before decomposing, read any
   ADR matching the spec's slug + skip subtasks whose
   contracts are already on disk". Small prompt edit +
   1 unit test.

6. **`pytest-rerunfailures` plugin pin** — iter-12 +
   iter-13 saw integration suite flakes from
   testcontainers port-mapping race. Pin the plugin so
   CI auto-retries once.

7. **Startup-time MCP failure investigation** — iter-11
   demo had Backend's MCP tools unavailable THROUGHOUT
   the session; iter-12+13 saw mid-session races.
   Possibly distinct failure modes; useful to
   understand.

8. **Architect's spend watch** — iter-11 $2.47, iter-12
   $0.59, iter-13 $0.84. Correlates with "did Architect
   add a new ADR this run?" rather than cache warmth.
   No action needed unless it spikes again.

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

## Hard constraints unchanged from iter-4..13

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
- HoldQueue is in-memory only (iter-14 may change this).
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
  Three pattern tuples. Add new tuples (not regex) when
  new shapes appear.
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
- Demo wall-clock is 30 min (iter-6, unchanged through
  iter-13).

## Ready-to-paste prompt for the new session

```
Starting Iteration 14 on the ai_team project.

First, read these in this order:

1. CLAUDE.md
2. docs/iterations/iter_13_retro.md (what just shipped,
   what's still open)
3. docs/iterations/iter_13_demo_report.md (real-LLM demo
   findings — session-id fallback fired in production
   with proof, Backend's retry session resumed cleanly,
   but hit a NEW MCP-race phrasing iter-10/12 tuples
   don't catch)
4. docs/iterations/iter_14_handoff.md (this file — full
   handoff context)
5. docs/adr/0001-orchestrator-choice.md,
   0008-llm-access-strategy.md

Iter-14 priority is **adding one more pattern tuple to
_MCP_RACE_PATTERNS** catching iter-13 demo's Backend
phrasing: ("mcp__ai_team_repo", "never connected"). ~3
LOC + 1 unit test pinning iter-13 correlation
1e7bb0db-... row 180 summary. Then re-run the iter-13
demo to finally close the `pending_review` loop
iter-3..13 all reached for. Backend's implementation
tree is on disk from iter-13's --resume session, so the
third attempt resumes from ~95% complete.

After that: TL Backend decomposition (FIVE-iteration
carry-over now; structural fix to pair with the
tactical tuple addition), HoldQueue persistence,
TL over-decomposition prompt hint.

Workflow: plan-before-code. Draft docs/iterations/iter_14.md
first, surface for review, then code. Run validation
checks + PR merges yourself.

Constraints unchanged from iter-13 — see CLAUDE.md
gotchas + the "Hard constraints" section of
iter_14_handoff.md.

When ready, create the iter-14 task list and surface the plan.
```
