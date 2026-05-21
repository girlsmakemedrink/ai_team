# Iteration 24 handoff

> Read **after** `CLAUDE.md`,
> `docs/iterations/iter_23_retro.md`, and
> `docs/iterations/iter_23_demo_report.md`.
> Replaces re-reading the prior conversation.

## Where we are (2026-05-21 EOD, iter-23 merged)

iter-23 shipped the **QA Python safety net** (decisively
proven 3/3 in
`tests/integration/test_qa_request_human_review_real_llm.py`)
plus `RECOVERABLE_BLOCKED_ON += task_too_large` and the demo
poll-window bump (30 → 45 min).

The two real-LLM demo runs did NOT reach the QA-emitted
`pending_reviews` row criterion. Each run failed at Backend
with a different defect:

- **Run #1**: TL's exact-match check on `blocked_on ==
  "task_too_large"` rejected the LLM's verbose free-form
  blocked_on. Chain stalled at Backend BLOCKED.
- **Hot-fix attempt #1**: schema enum on `blocked_on`. Looked
  clean.
- **Run #2**: Backend BLOCKED(budget) before producing any
  structured output. Most likely: enum-constraint-induced
  `--json-schema` retry loop in `claude -p` until $2.50 cap.
- **Reverted enum** (commit `88402b8`). Shipped iter-23 with
  TL substring matcher + prompt-side literal-token
  instruction instead.

**The QA criterion is closed in isolation but not via the full
chain.** It's now **5-iteration deferred** (iter-19 → 20 → 21
→ 22 → 23), but the failure mode has shifted from "QA-specific"
to **upstream Backend stability**. The iter-23 safety net is
proven to land the row when QA runs; iter-24's job is making
Backend reliable enough for the chain to get there.

## iter-24 priorities (in order)

### 1. (TOP) Backend stability — Round 2

Two upstream Backend failure modes surfaced in iter-23 demos.
Diagnose both:

**1a. `--json-schema` enum-retry-loop theory.** Hypothesis: when
`claude -p` is run with `--json-schema` containing an `enum`
constraint, and the LLM produces values outside the enum, the
substrate retries internally instead of returning a validation
error. Retries consume tokens; eventually the per-call
`max_budget_usd` cap (sonnet default $2.50) fires
`LLMBudgetExhaustedError`. Audit shape: dispatcher-synth
`task_report(blocked, blocked_on=budget)` with empty
`metadata.llm` (no per-turn metrics).

Concrete A/B test (~$0.15, 10 min):
- Run same prompt with `--json-schema` having strict enum vs
  permissive `type: string`. Observe `validated_against_schema`,
  total tokens, total duration, and whether
  `LLMBudgetExhaustedError` fires on either side.
- Use a fixture-shape prompt that asks the LLM to fill a
  field with a value outside the enum (or describe why it's
  too large).
- If enum-side burns budget while permissive-side doesn't:
  theory confirmed; document the pitfall in CLAUDE.md
  "Gotchas" and ADR-008.

**1b. Free-form `blocked_on` problem.** iter-23 demo Run #1's
Backend LLM emitted ~200-char free-form `blocked_on` describing
the scope problem. Even with iter-23's prompt update telling it
to use the literal token, future LLMs may drift. Proposed
structural fix: **TL should detect `"Scope pre-flight:"` as a
summary prefix and treat it as the canonical self-eject
signal**, regardless of `blocked_on` content. The summary
template in `prompts/backend_developer.md:25` already starts
with that prefix.

### 2. Preserve API logs in demo EXIT trap

Both iter-23 demo runs lost their `claude -p` API logs to the
EXIT trap's `rm -f "$API_LOG"`. Modify `_cleanup_iter23` (and
clone for iter-24) to MOVE the log to
`docs/iterations/iter_24_demo_logs/${CORRELATION}.log` instead
of deleting it. Forensic value for any future BLOCKED(budget)
mystery.

### 3. Commit `examples/sandbox/idea-validator/` scaffold to main

iter-23 demo Run #1's Backend correctly observed that the
`examples/` directory was untracked in the orchestrator and
absent from main — therefore not available to a fresh
`git worktree add` from main. Commit a minimal scaffold
(`__init__.py`, `README.md`, empty `src/` and `tests/`
subdirs) so Backend has a valid working tree to extend.

Or alternatively: teach Backend that "missing target
directory" means it should WRITE the scaffold itself. This is
a prompt edit. Cheaper than committing scaffolds, but more
fragile.

### 4. Re-attempt QA-emitted `pending_review` row in full demo

5-iteration deferred. With #1 and #3 closed, the iter-23
safety net (already shipped) should land the row. Demo
expected to:
- PM/Architect/Designer/Frontend all DONE (consistent across
  iter-19→23).
- Backend reaches DONE on a small subtask (be_schema or
  be_cli, ≤80 LOC).
- QA picks up Backend's report → safety net fires (or LLM
  surprises us and calls the tool) → row lands.

### 5. (Carry-overs from iter-23 handoff items 5-15 unchanged)

5. HoldQueue persistence (Postgres-backed).
6. `pytest-rerunfailures` plugin pin.
7. TL auto-hop investigation.
8. TL over-decomposition prompt hint (full version).
9. `audit_writer` restricted Postgres role.
10. Hash-chain alert job.
11. `GitHubTargetRepo` implementation.
12. TL decomposition transactional insert.
13. `BaseAgent.handle()` template-method refactor.
14. `mark_task_done` / `update_task_status` real implementations.
15. Substrate-level `--allowed-tools ""` fix.

## Hard constraints unchanged from iter-4..23

All hard constraints from prior iterations hold. iter-23
additions:

- **iter-23: `QAEngineerAgent.__init__` accepts
  `session_factory: async_sessionmaker[AsyncSession] | None`**.
  Plumbed by the dispatcher at `apps/api/main.py:93`.
- **iter-23: `_ensure_pending_review_row(response, msg)` is
  the QA safety net.** Inspects `response.tools_used`; if
  `mcp__ai_team_tasks__request_human_review` is absent and
  session_factory is set, INSERTs a `PendingReview` row
  directly. Defense-in-depth — the LLM tool-call path remains
  the primary intent (the prompt still mandates it).
- **iter-23: `core/retry/retry_blocked.py:RECOVERABLE_BLOCKED_ON`
  contains `"task_too_large"`** in addition to `mcp_unhealthy`
  and `budget`. `ai-team retry-blocked` CLI accepts it.
- **iter-23: TL's `_maybe_route_blocked` uses substring match
  for `"task_too_large"`** (`"task_too_large" in
  bo.lower()`) — not exact equality. iter-22's exact match
  was the root cause of iter-23 demo Run #1's stall.
- **iter-23: Backend prompt mandates `blocked_on` MUST be
  the literal `"task_too_large"`**. Pin test
  `test_backend_prompt_mandates_literal_blocked_on_token`.
- **iter-23: Demo poll window is 45 min** (was 30 in
  iter-22). Matches CLAUDE.md-documented budget.
- **iter-23 lesson (carry to ADR-008)**:
  `--json-schema` enum constraints suspected of causing
  `claude -p` internal retry loops that exhaust per-call
  budget. iter-24 #1a verifies. Until then, prefer
  `type: string` + Python-side validation over schema enum
  for fields the LLM tends to elaborate on.
- **iter-23: `BACKEND_REPORT_SCHEMA["blocked_on"]` is
  `{"type": ["string", "null"]}`** — NO enum. Hot-fix
  attempt's enum was reverted in commit `88402b8`.
- **All iter-22 constraints (Backend self-eject prompt,
  Architect→Backend depends_on)** still hold.
- **All iter-21 constraints (Python tripwire, TL re-decomp
  handler, bash heredoc fix)** still hold.

## What iter-23 specifically did NOT do

- **Did not produce a QA-emitted pending_review row in the
  full real-LLM demo.** 5-iteration deferred. But proved
  the safety net works 3/3 in isolation.
- **Did not investigate the BLOCKED(budget) substrate
  cause empirically.** Theory (enum retry-loop) is the
  most likely but not directly verified. iter-24 #1a.
- **Did not preserve demo API logs.** Both runs' logs were
  wiped by EXIT trap. iter-24 #2.
- **Did not commit an `examples/sandbox/idea-validator/`
  scaffold to main.** Backend kept observing "untracked
  examples/ in orchestrator, absent from main". iter-24 #3.
- **Did not change TL's routing to use summary-prefix
  detection.** Continues to route on `blocked_on`
  field. iter-24 #1b.
- **Did not address HoldQueue persistence, pytest-rerunfailures,
  GitHubTargetRepo, BaseAgent refactor, or any other
  carry-over ≥ 5.**

## Inherited decisions (do not contradict without revisiting)

- All inheriting decisions from iter-23 handoff hold (unchanged
  by iter-23). New decisions:
- **iter-23**: QA safety net via direct `PendingReview` INSERT
  (option A from iter-23 plan). Layer separation preserved —
  agents/ does not import from tools/mcp_servers/.
- **iter-23**: Backend `blocked_on` is permissive `string |
  null` at the schema level; routing strictness comes from
  TL substring matching + prompt instruction.
- **iter-23**: TL's `_maybe_route_blocked` uses substring
  match for `task_too_large`, not exact equality.
- **iter-23 anti-pattern recorded**: `--json-schema` enum
  constraints on LLM-elaborated fields. Verify A/B before
  use in iter-24+.

## Ready-to-paste prompt for the new session

```
Starting Iteration 24 on the ai_team project.

First, read these in this order:

1. CLAUDE.md
2. docs/iterations/iter_23_retro.md (what just shipped:
   QA Python safety net, decisively proven 3/3 in e2e
   test; two demo runs failed upstream with different
   Backend failure modes; enum hot-fix backfired and
   was reverted)
3. docs/iterations/iter_23_demo_report.md (detailed
   two-run autopsy — Run #1 TL exact-match stall, Run #2
   suspected schema-enum-induced budget burn)
4. docs/iterations/iter_24_handoff.md (this file —
   full handoff context)
5. agents/qa_engineer/agent.py + apps/api/main.py:93
   (the safety net + plumbing)
6. agents/team_lead/agent.py + agents/backend_developer/
   agent.py + prompts/backend_developer.md (the
   routing defense layers)

Iter-24 priorities (in order):

1. (TOP) Backend stability Round 2 — A/B test of
   --json-schema enum vs permissive (does enum cause
   budget burns?) AND structural scope-detection in
   TL via summary prefix instead of blocked_on routing.

2. Preserve API logs in demo EXIT trap.

3. Commit examples/sandbox/idea-validator/ scaffold
   to main OR teach Backend to scaffold itself.

4. Re-attempt QA-emitted pending_review row criterion
   (5-iteration deferred — should land with #1 and #3
   closed since the safety net is already proven).

After 1-3: re-run iter-23-shape demo and expect the
QA pending_review row finally lands.

Workflow: plan-before-code. Draft
docs/iterations/iter_24.md first, surface for review,
then code. Run validation + PR merges yourself.

Constraints unchanged from iter-23 — see CLAUDE.md
gotchas + the "Hard constraints" section of
iter_24_handoff.md. New iter-23 gotcha to keep in mind:
--json-schema enum constraints suspected of triggering
claude -p retry loops that exhaust budget. Verify
empirically before re-introducing strict validation.

PR merge gotcha: use `gh api -X PUT
repos/.../pulls/<N>/merge -f merge_method=squash` to
bypass gh CLI's local-checkout failure.

When ready, create the iter-24 task list and surface
the plan.
```
