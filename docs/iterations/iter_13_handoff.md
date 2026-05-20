# Iteration 13 handoff

> Read **after** `CLAUDE.md`,
> `docs/iterations/iter_12_retro.md`, and
> `docs/iterations/iter_12_demo_report.md`. Replaces re-reading
> the prior conversation.

## Where we are (2026-05-20 EOD, iter-12 merged)

Iter-12 is on `main`. Same 10-agent roster as iter-11; one
narrow change to `core/dispatcher/mcp_race_router.py` added
two new pattern tuples to catch iter-11 demo's Backend
phrasing:

```python
_MCP_RACE_PATTERNS: tuple[tuple[str, ...], ...] = (
    ("MCP server", "never connected"),               # iter-10
    ("MCP server", "never finished connecting"),     # iter-10
    ("MCP server", "still connecting"),              # iter-10
    ("mcp__ai_team_repo", "unavailable"),            # iter-12
    ("MCP tools", "unavailable"),                    # iter-12
)
```

iter-12 demo report at
`docs/iterations/iter_12_demo_report.md` is the single
source of truth. **Headline**: the two new tuples FIRED in
production on first run after merge; iter-11's
`ai-team retry-blocked` engaged END-TO-END at the
orchestrator level for the first time across twelve
iterations. The chain reached the most advanced state ever
observed. **Failure mode discovered**: `claude -p`
session-id collision under dispatcher restart — the demo's
exit-trap killed uvicorn between Backend's first attempt
and the retry; restarting the dispatcher lost the
in-memory cache of "which session_ids have been claimed";
the retry tried `--session-id` instead of `--resume`;
claude -p errored "already in use"; LLMInvocationError →
synth_failed_report → root failed.

iter-13's top priority: fix the session-id durability bug,
re-run the demo.

## Carry-over items (priority order, from iter-12 retro + demo report)

1. **(top)** **Fix `ClaudeCodeHeadlessClient` session-id
   durability under dispatcher restart.** The current
   adapter tracks `_seen_sessions` in-memory; it picks
   `--session-id` on first call and `--resume` on
   subsequent calls. The cache doesn't survive a
   dispatcher process restart, so a retry-blocked
   after-restart scenario hits `claude -p exited 1: Session
   ID is already in use`.

   **Recommended fix** (smallest layer): make the adapter
   try `--resume` first and fall back to `--session-id`
   on the "no such session" error pattern. ~5 LOC in
   `core/llm/claude_code_headless.py` + 1 unit test
   mocking both stderr paths.

   **Alternative** (cleaner long-term): track session_ids
   in Postgres (small new table or reuse `audit_log`'s
   metadata). Durable across restarts, decoupled from
   claude CLI internals. Slightly larger change but no
   extra spawn cost.

   Plan iter-13 around (a) for speed; defer (b) to a
   later iteration if (a) proves fragile.

2. **Re-run iter-12-shape demo after #1** to finally
   exercise iter-11's retry-blocked end-to-end through
   Backend's claude -p call. Expected path:
   - Backend hits MCP race (or doesn't — race is
     intermittent).
   - If BLOCKED: router rewrites correctly (iter-12
     tuples are on `main`).
   - Owner runs `ai-team retry-blocked <task_id>`.
   - Dispatcher restart not required — but the iter-13
     fix means restart-resilient anyway.
   - Backend's retry session resumes cleanly, completes
     the implementation work (write tests, run pytest,
     commit, open PR).
   - QA picks up, runs the v2-spec smoke + regression
     suite, emits `request_human_review`.
   - `pending_review` row appears; owner runs
     `ai-team approve <id>`; chain closes.

   This is the long-awaited end-to-end close.

3. **TL over-decomposition awareness.** Architect's
   iter-12 row 160 explicitly flagged that TL
   re-decomposed v2 from scratch despite ADR-0019 from
   iter-11 already covering the five concerns. TL's
   prompt needs a hint: "before decomposing, read any
   ADR matching the spec's slug + skip subtasks whose
   contracts are already on disk". Small prompt edit
   + 1 unit test verifying TL skips already-shipped
   contracts.

4. **HoldQueue persistence (Postgres-backed).** Now
   actively relevant — iter-12 surfaced the loss-on-
   restart scenario. When the dispatcher dies between
   a BLOCKED report and the retry, in-memory
   HoldQueue entries are gone; dependents like QA
   become orphaned `in_progress` rows. Lift to
   `held_messages` table.

5. **TL Backend decomposition** (now four-iteration
   carry-over: iter-9/10/11/12). Backend's 349 s
   first-attempt session in iter-12 was again the
   longest. Splitting into 2-3 chunks reduces MCP race
   exposure window AND per-retry burn under the
   5-attempt cap.

6. **`pytest-rerunfailures` plugin pin** — iter-12's
   combined-suite run hit the testcontainers race
   that iter-7..11 also saw. The flaky test passed
   when isolated. Pin the plugin so CI auto-retries
   transient infra-test failures once.

7. **Startup-time MCP failure investigation.** Why did
   iter-11's Backend report MCP tools unavailable
   THROUGHOUT the session (not mid-session like
   iter-8/9/10)? Possibly correlated with prior demo
   runs leaving `examples/sandbox/idea-validator/` on
   disk. iter-13 can re-test with a clean working
   tree.

8. **Architect's iter-11 $2.47 call** — iter-12 saw it
   drop to $0.59. Probably one-time consolidation cost,
   not steady-state. Continue to watch but no action
   needed unless it spikes again.

9. **`audit_writer` restricted Postgres role
   enforcement.** Still deferred.

10. **Hash-chain alert job.** Still deferred.

11. **`GitHubTargetRepo` implementation.** Waiting on
    first commercial product (ADR-009).

12. **TL decomposition transactional insert.** Still
    deferred — a TL crash mid-batch leaves orphan
    child rows.

13. **`BaseAgent.handle()` template-method refactor.**
    Defer until the next agent rolls in.

## Hard constraints unchanged from iter-4..12

- **LLM substrate is `claude -p` via subscription.** Never
  set `ANTHROPIC_API_KEY`. Never use Agent SDK with an API
  key.
- **`--json-schema` validated output lives in
  `structured_output`**.
- **`--session-id` is set-once, `--resume` is resume.**
  iter-13 will make the adapter restart-resilient (try
  `--resume` first, fall back to `--session-id`).
- **Boring stack only.** Re-read ADR-001 before considering
  any new framework.
- **Diff-cover gate is 80%. Bandit gates on high only.**
- **Ruff `format --check` is also a gate.**
- **Conventional commits, squash-merge, plan-before-code,
  owner approval on every agent task completion.**
- **Bash never raw on agents.** Use
  `mcp__ai_team_repo__run_shell` with its command-class
  enum. iter-10 strengthened this in Backend's prompt;
  iter-11 added `--disallowed-tools "Bash"` defense-in-
  depth.
- **`pending_review` rows are the owner-approval gate.**
- **`examples/` is the agents' TARGET_REPO root** (ADR-009).
  Excluded from orchestrator ruff lint AND mypy.

## Inherited decisions (do not contradict without revisiting)

- Agent PRs target `main` on `ai_team` only (single-repo
  exception).
- Architect is **advisory**, not gating.
- TL auto-routes BLOCKED with one auto-hop max (iter-2c).
- TL emits a flat list of subtasks with explicit
  `depends_on` slugs (iter-3); declares `depends_on` only
  when recipient literally cannot start without (iter-4);
  emits a `BROADCAST(topic="tl.dag_preview")` (iter-4).
- HoldQueue is in-memory only (iter-13 may change this).
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
- **iter-10:** Backend's prompt has an explicit lookup
  table of `command_class` values for git / uv / make /
  pytest.
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
- **iter-12:** `_MCP_RACE_PATTERNS` extended with two
  more tuples (`("mcp__ai_team_repo", "unavailable")`,
  `("MCP tools", "unavailable")`) catching iter-11
  demo's Backend phrasing.
- Demo wall-clock is 30 min (iter-6, unchanged through
  iter-12).

## Ready-to-paste prompt for the new session

```
Starting Iteration 13 on the ai_team project.

First, read these in this order:

1. CLAUDE.md
2. docs/iterations/iter_12_retro.md (what just shipped, what's
   still open)
3. docs/iterations/iter_12_demo_report.md (real-LLM demo
   findings — substring router + retry-blocked both fired,
   but Backend's retry hit a claude -p session-id collision
   under dispatcher restart)
4. docs/iterations/iter_13_handoff.md (this file — full
   handoff context)
5. docs/adr/0001-orchestrator-choice.md,
   0008-llm-access-strategy.md

Iter-13 priority is **fixing the claude -p session-id
collision under dispatcher restart**. ClaudeCodeHeadlessClient
should try --resume first and fall back to --session-id on
"no such session" error. ~5 LOC + 1 unit test. Then re-run
the iter-12-shape demo so iter-11's retry-blocked finally
runs Backend's claude -p call to completion, the chain
reaches QA, QA emits request_human_review, and the
pending_review loop iter-3..12 all reached for finally
closes.

After that: TL over-decomposition prompt hint, HoldQueue
persistence (now actively relevant from iter-12 demo), TL
Backend decomposition (4-iteration carry-over),
pytest-rerunfailures plugin pin.

Workflow: plan-before-code. Draft docs/iterations/iter_13.md
first, surface for review, then code. Run validation checks
+ PR merges yourself.

Constraints unchanged from iter-12 — see CLAUDE.md gotchas +
the "Hard constraints" section of iter_13_handoff.md.

When ready, create the iter-13 task list and surface the plan.
```
