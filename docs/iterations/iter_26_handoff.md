# Iteration 26 handoff

> Read **after** `CLAUDE.md`,
> `docs/iterations/iter_25_retro.md`, and
> `docs/iterations/iter_25_demo_report.md`.

## Where we are (2026-05-21 EOD, iter-25 merged)

🎯 **Reproducibility confirmed**: 2/2 demos with available
quota produced the criterion (Backend DONE → QA row).
iter-24's clean chain wasn't a lucky one-off; the
iter-19..24 cumulative architecture is stable.

🔬 **Diagnostic infrastructure paid off**: iter-25 Run 2/2's
BLOCKED(budget) was solved within minutes via the iter-24
preserved API log:
`api_error_status=429, total_cost_usd=$0.10, "session limit · resets 10:10pm"`.
**Same root cause as iter-23 R#2** (previously labelled
"unknown"). Both events: Claude Max 5x subscription session
quota, not architectural budget burn. The 2-iteration
mystery is closed.

📐 **Framework is ready** for a different shape of work.
The sandbox idea-validator demo has served its purpose.

## iter-26 priorities (in order)

### 1. (STRATEGIC) Pick (a) / (b) / (c)

The owner now has evidence to decide. iter-25 retro
recommends (b).

- **(a) Keep iterating on the sandbox** — add features.
  Risk: framework stays in self-test mode indefinitely;
  sandbox is essentially "done".
- **(b) Pivot to a real product** ⭐ — pick a monetizable
  idea (from `docs/sandbox/idea_validator_*.md` or
  fresh), draft PRD, let the team build. Architecture
  is reliable; this is the productive direction.
- **(c) Stabilization phase** — close ≥5 carry-overs
  (HoldQueue persistence, GitHubTargetRepo, BaseAgent
  refactor, etc.) before product work.

iter-26's first task is the owner's pick + a draft of
the corresponding plan-doc.

### 2. (P1) CLAUDE.md gotcha: 429 vs budget cap

Add a sentence under "LLM access" gotchas:

> **Backend BLOCKED(budget) with `total_cost_usd` << per-call
> cap = subscription Max-5x session 429, NOT a real budget
> exhaustion.** The error message includes the reset time
> ("resets HH:MM Europe/Moscow"). Wait for reset and re-run
> manually via `ai-team retry-blocked`. iter-15's adapter
> correctly maps 429 → `LLMBudgetExhaustedError` → BLOCKED(budget)
> for transparent observability; do not "tune" the per-call
> max_budget_usd to work around it.

This codifies the iter-23..25 lesson.

### 3. (P2) Pre-demo quota check

Add to the start of `scripts/demo_iter_26.sh` (or as a
make target) a sanity step that pings `claude -p` with
a trivial prompt and checks the response. If 429: warn
loudly and abort the demo (don't waste 15 min on a chain
that's doomed). Trivial to implement.

### 4. (P3) Investigate "2 pending_reviews per QA turn"

iter-25 R#1 produced 2 rows from a single QA `handle()`
invocation. Likely the LLM called
`mcp__ai_team_tasks__request_human_review` more than
once in the same turn. Minor — doesn't break anything —
but worth understanding:
- Is the QA prompt ambiguous about "call this tool ONCE"?
- Should `handle_request_human_review` dedupe by
  `correlation_id` + `requesting_agent`?
- Or accept it as benign LLM behavior?

Cheap diagnostic: check the audit_log for the tool-call
count in `metadata.llm.tools_used`. If it's 2 per QA
turn consistently, the LLM is being thorough; if it's
1, the dedupe is via two different MCP invocations
somehow.

### 5. (P3) iter-23 R#2 / iter-25 R#2 retroactive cleanup

`docs/iterations/iter_23_retro.md` and
`docs/iterations/iter_24_retro.md` both speculate about
the BLOCKED(budget) cause. iter-26 could add a
short "Update (iter-25): root cause was subscription
session 429, see iter_25_demo_report.md" note to both
files so future readers don't re-chase the wrong
theory.

Optional polish; not blocking.

### 6. (Carry-overs ≥5) unchanged

- HoldQueue persistence (Postgres).
- `pytest-rerunfailures` plugin pin.
- TL auto-hop investigation.
- `audit_writer` restricted Postgres role.
- Hash-chain alert job.
- `GitHubTargetRepo` implementation.
- TL decomposition transactional insert.
- `BaseAgent.handle()` template-method refactor.
- `mark_task_done` / `update_task_status` real impls.
- Substrate-level `--allowed-tools ""` fix.
- `examples/sandbox/idea-validator/` scaffold to main
  (only relevant if strategic decision = (a)).

## Hard constraints (unchanged from iter-25)

All iter-4..25 constraints hold. iter-25 has no new
architectural constraints — it was a reproducibility
iteration with one operational improvement (60s
post-success drain in the demo).

**iter-25 lesson added (per iter-26 #2)**:
`api_error_status=429` from `claude -p` is the
subscription session limit, not a per-call budget cap.
`total_cost_usd` in the error response is far below the
$2.50 default. Wait for the printed reset time and
re-run via `ai-team retry-blocked`.

## What iter-25 specifically did NOT do

- Did not change any agent code or schema.
- Did not change any prompt.
- Did not commit an `examples/sandbox/idea-validator/`
  scaffold to main.
- Did not address any carry-over ≥5.
- Did not pick (a)/(b)/(c). iter-26 surfaces the
  decision.
- Did not investigate the "2 pending_reviews per QA
  turn" anomaly (iter-26 #4).

## Inherited decisions (do not contradict without revisiting)

All iter-19..25 decisions hold. New iter-25 decisions:

- **iter-25 (operational)**: demo poll loop drains for
  60s after success-detection to let QA's outbound
  task_report reach the audit_writer. Don't shorten
  below 60s.
- **iter-25 (recorded lesson)**: BLOCKED(budget) with
  low `total_cost_usd` = subscription session 429, not
  a per-call budget cap event. iter-23 R#2 and iter-25
  R#2 share this root cause.

## Ready-to-paste prompt for the new session

```
Starting Iteration 26 on the ai_team project.

First, read these in this order:

1. CLAUDE.md
2. docs/iterations/iter_25_retro.md (reproducibility
   confirmed: 2/2 architecture-success demos, 1
   quota-exhausted environmental failure)
3. docs/iterations/iter_25_demo_report.md (full
   evidence including the iter-23 R#2 mystery
   retroactively solved via preserved API log)
4. docs/iterations/iter_26_handoff.md (this file —
   strategic options + small operational items)

Iter-26 priorities (in order):

1. (STRATEGIC TOP) Pick the iteration direction:
   (a) keep iterating on sandbox, (b) pivot to a real
   product, or (c) stabilization phase. Recommend
   (b) per iter-25 retro evidence. Draft iter_26.md
   based on the choice.

2. (P1) Add CLAUDE.md gotcha for 429 vs budget cap.

3. (P2) Pre-demo quota check.

4. (P3) "2 pending_reviews per QA turn" investigation.

5. (P3) Retroactive cleanup of iter-23/24 retro notes.

6. (Carry-overs ≥5) unchanged.

Workflow: plan-before-code. Draft docs/iterations/iter_26.md
first AFTER the strategic decision in #1. Surface the
plan, then code. Run validation + PR merges yourself.

Constraints unchanged from iter-25 — see CLAUDE.md
gotchas + the "Hard constraints" section of
iter_26_handoff.md.

PR merge gotcha: use `gh api -X PUT
repos/.../pulls/<N>/merge -f merge_method=squash`.

When ready, create the iter-26 task list and surface
the plan (or surface the strategic decision first).
```
