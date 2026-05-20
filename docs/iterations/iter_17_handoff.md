# Iteration 17 handoff

> Read **after** `CLAUDE.md`,
> `docs/iterations/iter_16_retro.md`, and
> `docs/iterations/iter_16_demo_report.md`. Replaces
> re-reading the prior conversation.

## Where we are (2026-05-20 EOD, iter-16 merged)

Iter-16 is on `main`. Same 10-agent roster. One narrow
change to `core/dispatcher/mcp_race_router.py`:
`_MCP_FAILURE_VERB_SET` extended with `"unreachable"` +
`"unavailability"`. Cross-product space is now 3 x 9 =
27 combinations.

iter-16 demo (`docs/iterations/iter_16_demo_report.md`,
correlation `4b74be45-e13c-441a-a5a6-9aac249beba8`):
**cross-product matcher caught BOTH Backend attempts**
(row 230 startup-race + row 233 startup-race-again).
**Zero FAILED rows in the chain** — the cleanest router
behavior across 17 iterations. Backend's retry reports
the v2 implementation tree as spec-complete on disk
(7-stage pipeline + models + factories + sanitizer +
exit-code table + 5 test modules). The chain didn't
reach `pending_review` because (a) demo's auto-retry
tail loops only once, and (b) MCP server keeps racing
every Backend session.

**The matcher layer is decisively closed; iter-17 must
move to the structural issues**: MCP startup-time
reliability, demo automation loop, or TL Backend
decomposition.

## Carry-over items (priority order, from iter-16 retro + demo report)

1. **(top)** **Demo auto-retry loop** — `scripts/
   demo_iter_16.sh` step 6.5/7 currently calls
   `ai-team retry-blocked` once and then waits 15 min
   for pending_review. If the retry session ALSO
   blocks (as in iter-16), the wait times out. Change:
   loop the retry-blocked + watch cycle until either
   (a) `pending_review` appears, (b) Backend ends
   non-BLOCKED, or (c) retry_attempt cap (5) is hit.
   ~20-30 LOC of bash; or factor into a new
   `ai-team retry-loop --correlation <id>
   --max-attempts 5` CLI command for owner re-use.
   Pairs with #2 below.

2. **Startup-time MCP failure investigation** — now
   9-iteration carry-over. Empirically the matcher
   catches every race so the dispatcher routes
   correctly, BUT the race itself remains the
   actual blocker for end-to-end closure. The
   iter-9 pre-flight gate's in-process probe
   passes; claude -p's spawned MCP subprocess
   then fails. Hypotheses:
   - `claude -p` spawns the MCP child with different
     env / cwd / args than the orchestrator's probe.
   - Startup-time race: claude -p reads
     `mcp_servers` config before the MCP server's
     `serve()` event loop is ready to accept
     connections.
   - Permission sandbox interaction: macOS / macOS-
     equivalent permission prompts denying the
     spawn silently.
   Investigation path: enable claude -p
   `--mcp-debug` logs; diff against the
   orchestrator's MCP spawn. Add an MCP-health
   retry loop inside the agent's `claude -p`
   invocation if the race is timing-driven. This is
   blocking the loop close that 17 iterations have
   chased.

3. **TL auto-hop investigation** — per CLAUDE.md
   iter-2c "TL auto-routes BLOCKED with one
   auto-hop max". Inspection of iter-16 audit_log
   shows row 232 has the retry-blocked endpoint
   signature, no TL "BLOCKED analysis" pre-row.
   Either the auto-hop isn't wired or the demo's
   retry-blocked CLI silently overrides it. ~30 min
   reading `agents/team_lead/agent.py` +
   `core/dispatcher.py`. If broken, integrate fix
   into the demo path.

4. **TL Backend decomposition** — SEVEN-iteration
   carry-over (iter-9..16). Backend's iter-16
   retry was 234s; if the third attempt actually
   commits + pushes + runs pytest + opens PR,
   session could exceed the 600s `llm_timeout_s`.
   Splitting into 2-3 chunks reduces per-chunk
   exposure AND ships independently. Defer to
   iter-18 if #1/#2 close the loop fast OR pull
   forward if iter-17's outcome shows the timeout
   binding.

5. **TL over-decomposition prompt hint** — Architect
   cost was $0.63 in iter-16 (cache-driven savings
   from ADR-0021 on main). Without the prompt hint,
   new-ADR iterations will spike Architect again.
   Small prompt edit + 1 unit test verifying TL
   passes "skip subtasks whose contracts are
   already on disk under `docs/adr/<scope>-*.md`"
   to Architect's task assignment.

6. **HoldQueue persistence (Postgres-backed)** —
   iter-16 demo lost QA's hold on the terminal
   BLOCKED. Add `held_messages` table +
   startup-time hydration. iter-18 if iter-17
   closes the loop.

7. **`pytest-rerunfailures` plugin pin** — iter-16
   reproduced the testcontainers port-mapping
   race when integration runs after unit. Pin so
   CI auto-retries once.

8. **Architect spend watch** — $0.63 iter-16 was
   great but it correlates with no-new-ADR
   iterations. Worth a one-line check that flags
   when Architect's `task_report` summary is
   substantially identical to disk.

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

## Hard constraints unchanged from iter-4..16

- **LLM substrate is `claude -p` via subscription.** Never
  set `ANTHROPIC_API_KEY`. Never use Agent SDK with an API
  key.
- **`--json-schema` validated output lives in
  `structured_output`**.
- **`--session-id` is set-once, `--resume` is resume.**
  iter-13 made the adapter restart-resilient.
- **iter-15: `api_error_status=429` → BLOCKED(budget)**
  routing.
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
- TL auto-routes BLOCKED with one auto-hop max (iter-2c) —
  iter-17 investigates whether it's actually firing.
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
  `_MCP_TOKEN_SET` x `_MCP_FAILURE_VERB_SET` cross-
  product matcher. Adding new phrasings = adding a
  set entry.
- **iter-15:** `api_error_status=429` + `"session
  limit"` markers → `LLMBudgetExhaustedError`.
- **iter-16:** `_MCP_FAILURE_VERB_SET` extended with
  `"unreachable"` and `"unavailability"`. Note:
  `"unavailable"` is NOT a substring of
  `"unavailability"`; both needed as separate
  entries.
- Demo wall-clock is 30 min initial chain + 15 min
  retry window = 45 min total.

## Ready-to-paste prompt for the new session

```
Starting Iteration 17 on the ai_team project.

First, read these in this order:

1. CLAUDE.md
2. docs/iterations/iter_16_retro.md (what just shipped:
   matcher is empirically robust + cost dropped 32 %;
   the gap is now structural — MCP keeps racing + demo
   only retries once)
3. docs/iterations/iter_16_demo_report.md (real-LLM
   demo findings — BOTH Backend attempts BLOCKED via
   matcher, zero FAILED rows, but chain stalls because
   demo doesn't loop retry-blocked)
4. docs/iterations/iter_17_handoff.md (this file —
   full handoff context)
5. docs/adr/0001-orchestrator-choice.md,
   0008-llm-access-strategy.md

Iter-17 priority is **closing the loop iter-3..16 all
reached for** via two structural moves:

1. **Demo auto-retry loop** — make step 6.5/7 of the
   demo script iterate retry-blocked up to the
   5-attempt cap on every BLOCKED Backend row in the
   wait window. ~20-30 LOC of bash, OR a new
   `ai-team retry-loop` CLI command.

2. **Startup-time MCP failure investigation** —
   9-iteration carry-over now blocking. The matcher
   catches every race; the race itself keeps firing.
   Diff orchestrator MCP spawn vs claude -p's;
   investigate with `--mcp-debug`. The hypothesis to
   verify: is claude -p reading mcp_servers config
   before MCP server is ready to accept connections?

After that: TL auto-hop investigation, TL Backend
decomposition, TL over-decomposition prompt hint.

Workflow: plan-before-code. Draft docs/iterations/
iter_17.md first, surface for review, then code.
Run validation checks + PR merges yourself.

Constraints unchanged from iter-16 — see CLAUDE.md
gotchas + the "Hard constraints" section of
iter_17_handoff.md.

When ready, create the iter-17 task list and surface
the plan.
```
