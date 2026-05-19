# Iteration 4 handoff

> Read **after** `CLAUDE.md`, `docs/iterations/iter_3_retro.md`, and
> `docs/iterations/iter_3_demo_report.md`. Replaces re-reading the
> prior conversation.

## Where we are (2026-05-19 EOD, iter-3 merged)

Iter-3 is on `main`. Same 10-agent roster as iter-2c; what's new is
**dependency ordering**, **root-task rollup**, and **per-message
metrics in audit metadata** — so an Architect → Backend → QA chain
actually runs in order, `tasks.status` reflects chain completion, and
the demo report is a single SQL query (no structlog grep).

Specifically, since iter-2c:

1. **TL decomposition supports `depends_on`.** Per-subtask `id` slug +
   `depends_on: list[str]` in `DECOMPOSITION_SCHEMA`. TL resolves slugs
   to predecessor `task_id` UUIDs and stamps them onto
   `AgentMessage.metadata["depends_on"]`. Forward references work; the
   dispatcher's HoldQueue enforces ordering at runtime.
2. **`HoldQueue` in the dispatcher.** In-memory per-correlation_id
   gate (~120 LOC). Messages with unmet predecessors are audited +
   feed-published at intent time but held off the bus until released
   atomically when the last predecessor's `TASK_REPORT(done)` lands.
   `mark_failed` drops dependents whose predecessor failed.
3. **Root-task state rollup.** New `TaskStateReducer` in
   `core/persistence/task_state.py`. Dispatcher writes child `Task`
   rows when TL emits assignments with `metadata["parent_task_id"]`;
   marks each child `done`/`failed` on its `TASK_REPORT`; flips the
   parent to `done` when every child is `done`, or `failed` if any
   child failed.
4. **Per-message LLM metrics in `metadata["llm"]`.** `BaseAgent.handle()`
   (and `TeamLeadAgent.handle()`) stamp tokens_in, tokens_out,
   cached_input, cost_cents, duration_ms, model, and
   validated_against_schema onto every output. Audit row's
   `payload_json` carries them; one SQL query produces the demo
   report.
5. **`ai-team digest` 401 fixed.** CLI now loads `.env` from cwd
   before resolving `OWNER_TOKEN` (regression pin in
   `tests/unit/test_apps_cli.py`).
6. **Demo wall-clock bumped to 20 min** in `scripts/demo_iter_3.sh`,
   targeting a 6-stage DAG (pm_clarify → arch → {be, design} → fe →
   qa) per `docs/sandbox/idea_validator_v2_spec.md`. Exercises
   Designer → Frontend → QA for the first time in an e2e run.

Iter-3 demo report at `docs/iterations/iter_3_demo_report.md` is the
single source of truth on cost / wall-clock / which-stage-ran.

## Carry-over items (priority order, from iter-3 retro + demo report)

1. **MCP server cold-start race (TOP priority).** Backend reported
   `task_report(failed)` in the iter-3 demo because
   `mcp__ai_team_repo__*` tools didn't initialise in 3 ToolSearch
   retries. Options: pre-warm MCP servers on dispatcher startup
   (longer start, predictable agent calls); extend the agent's MCP
   retry budget in tooling/prompt; block agent invocation until MCP
   servers report healthy on a short ping. See
   `iter_3_demo_report.md` Failure 2.
2. **Tighten TL prompt against spurious `depends_on`.** Iter-3 demo
   had the TL emit Frontend with `depends_on=[backend, design]`
   despite the v2 spec saying the landing page is static (no
   Backend dep). When Backend failed, Frontend got dropped too. Fix
   options: rephrase TL prompt rule ("only depend on the artifact
   the recipient literally cannot start without"); surface the DAG
   to the owner in the digest before chain commits; let owner
   override a decomposition before publish. See
   `iter_3_demo_report.md` Failure 3.
3. **Re-run the iter-3-shape demo** after #1 + #2 land to close the
   PM → Architect → Backend → QA → `pending_review` → approve loop
   for the first time AND exercise Designer → Frontend → QA against
   the substrate. Iter-3 demo had QA + Frontend correctly dropped
   by `HoldQueue.mark_failed` after Backend failed; iter-4 should
   capture the green-path full chain.
3. **Investigate TL tokens_out=76 under-reporting** on the iter-3
   second-attempt run. A 6-subtask JSON decomposition shouldn't fit
   in 76 output tokens; either `claude -p` reports tokens_out for
   the structured_output field only, or pricing is drifting >20%
   and needs `PRICE_TABLE_CENTS_PER_MTOK` recalibration (see
   CLAUDE.md gotcha).
4. **HoldQueue persistence.** Currently in-memory; dispatcher restart
   drops every held message. Iter-4 lifts to a Postgres-backed
   `held_messages` table once a real outage hits or once we add the
   second dispatcher process. Until then, document the limit in the
   HoldQueue docstring (done).
5. **`audit_writer` Postgres role enforcement.** ADR-003 specifies
   only a restricted DB role can `INSERT` into `audit_log`. Still
   deferred from iter-2 and iter-3.
6. **Hash-chain alert job.** Scheduled `verify_chain()` with `ALERT`
   on tamper. Deferred from iter-2 and iter-3.
7. **`GitHubTargetRepo` impl.** Waiting on the first commercial
   product (ADR-009's deferred decision).
8. **TL decomposition transactional insert.** A TL crash mid-batch
   leaves orphan child rows; the parent stays `in_progress` forever.
   `TaskStateReducer.on_assignment` should wrap the TL's whole batch
   in one transaction.
9. **`pytest-rerunfailures` plugin pin** for the testcontainers race
   the iter-2c retro flagged (occasionally `Port mapping for
   container ...` on first run). Still occasional in iter-3.

## Hard constraints unchanged from iter-2c / iter-3

- **LLM substrate is `claude -p` via subscription.** Never set
  `ANTHROPIC_API_KEY`. Never use Agent SDK with an API key.
- **`--json-schema` validated output lives in `structured_output`**.
- **`--session-id` is set-once, `--resume` is resume.** Adapter
  switches automatically.
- **Boring stack only.** Re-read ADR-001 before considering any new
  framework.
- **Diff-cover gate is 80 %. Bandit gates on high only.**
- **Conventional commits, squash-merge, plan-before-code, owner
  approval on every agent task completion.**
- **Bash never raw on agents.** Use `mcp__ai_team_repo__run_shell`
  with its command-class enum.
- **`pending_review` rows are the owner-approval gate.** Even when
  CI is green, an agent's `task_report` waits for `ai-team approve <id>`.

## Inherited decisions (do not contradict without revisiting)

- Agent PRs target `main` on `ai_team` only (single-repo exception).
- Architect is **advisory**, not gating.
- TL auto-routes BLOCKED with one auto-hop max (iter-2c Phase 4).
- TL emits a flat list of subtasks with explicit `depends_on` slugs
  (iter-3 Phase 2). No nested sub-decompositions; cycles are
  undefined behavior.
- HoldQueue is in-memory only (iter-3 default #1 — Postgres-backed
  upgrade deferred to iter-4).
- LLM metrics live in `metadata["llm"]` on the envelope (iter-3
  default #2 — no schema bump).
- Per-stage demo task uses a v2 spec
  (`docs/sandbox/idea_validator_v2_spec.md`); iter-2 v1 spec stays
  intact as the regression baseline (iter-3 default #3).
- Anti-loop guard for TL routing is summary-string check, not a
  metadata counter (iter-2c).

## Ready-to-paste prompt for the new session

```
Starting Iteration 4 on the ai_team project.

First, read these in this order:

1. CLAUDE.md
2. docs/iterations/iter_3_retro.md (what just shipped, what's still open)
3. docs/iterations/iter_3_demo_report.md (real-LLM demo findings)
4. docs/iterations/iter_4_handoff.md (this file — full handoff context)
5. docs/adr/0001-orchestrator-choice.md, 0002-message-schema.md,
   0003-audit-log.md, 0008-llm-access-strategy.md

Iter-4 starts from the iter-3 demo report's action items + the
carry-overs in iter_4_handoff.md. Pick the highest-priority one and
draft a plan.

Workflow: plan-before-code. Draft docs/iterations/iter_4.md first,
surface for review, then code. Run validation checks + PR merges
yourself (autonomy preference in memory).

Constraints unchanged from iter-3 — see CLAUDE.md gotchas + the
"Hard constraints" section of iter_4_handoff.md.

When ready, create the iter-4 task list and surface the plan.
```
