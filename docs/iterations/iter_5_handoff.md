# Iteration 5 handoff

> Read **after** `CLAUDE.md`, `docs/iterations/iter_4_retro.md`, and
> `docs/iterations/iter_4_demo_report.md`. Replaces re-reading the
> prior conversation.

## Where we are (2026-05-19 EOD, iter-4 merged)

Iter-4 is on `main`. Same 10-agent roster as iter-3; what's new:

1. **MCP servers invoked via `${REPO_ROOT}/.venv/bin/python`** in the
   demo config (was `uv run python`). Cold-start drops ~58 ms → ~42
   ms median with tight variance. Validated by
   `scripts/measure_mcp_coldstart.py` + iter-4 demo
   (Backend reached its inner LLM turn this time; the "tools never
   connected" iter-3 failure is closed).
2. **TL emits a DAG-preview broadcast at index 0 of its outputs.**
   `BROADCAST(topic="tl.dag_preview", body=<Markdown plan>)` lands
   in audit + team_feed before any sub-task assignment hits the
   bus. `ai-team watch` surfaces it. Informational; not a gate.
3. **TL system prompt enforces conservative `depends_on`** —
   pinned by a snapshot unit test. The iter-3 demo's spurious
   `fe depends_on=[backend, design]` for a static HTML landing
   page **did not reproduce** under iter-4 Opus.
4. **Benchmark script `scripts/measure_mcp_coldstart.py`** lands as
   a regression hook. Direct-mode medians under 100 ms gate the
   exit code.

Iter-4 demo report at `docs/iterations/iter_4_demo_report.md` is the
single source of truth on cost / wall-clock / which-stage-ran.

## Carry-over items (priority order, from iter-4 demo report)

1. **Dispatcher exception → synthetic `TASK_REPORT(failed)`
   (TOP priority).** When an agent's `handle()` raises, the
   dispatcher logs the traceback but emits zero outbound messages.
   The chain hangs because HoldQueue never sees the failure.
   Iter-4 demo's Backend hit this: `claude -p exited 1` with empty
   stderr was caught by the `except Exception` in
   `core/dispatcher/dispatcher.py:127`, but no `TASK_REPORT(failed)`
   was synthesised. Fix: in the dispatcher's except block, build
   a failed `TASK_REPORT` from the failed agent and route it through
   the same outbound pipeline (audit + feed + `HoldQueue.mark_failed`
   + bus). ~30 LOC.
2. **`claude -p` agent permission policy.** Frontend's iter-4 run
   blocked on a `claude -p` interactive permissions gate for
   `apps/web/idea-validator/index.html`. The MCP path scope is
   wide open (`AI_TEAM_PATH_PREFIXES=*`); the block is one layer
   up, inside the agent's inner `claude -p` subprocess. Options:
   pass `--permission-mode acceptEdits` (or `bypassPermissions`)
   to the inner `claude -p`; or rewrite agent prompts to prefer
   the MCP `write_file_in_scope` tool which already bypasses the
   interactive gate. Pick one and document in ADR-008.
3. **Per-agent `metadata["llm"]` stamping** (pre-existing iter-3
   bug surfaced by iter-4). Only `TeamLeadAgent.handle()` and
   `BaseAgent.handle()`'s *default* code path call
   `_stamp_metrics`. Every agent that overrides `handle()` (PM,
   Architect, Backend, Designer, Frontend, QA, DevOps,
   MarketResearcher, SRE) skips it. iter-4's demo SQL query
   shows empty `{}` metadata for every non-TL row. Fix: refactor
   `BaseAgent.handle()` to invoke a template-method that
   subclasses fill in (so the stamping survives any override).
   Or: each subclass's handle() calls `_stamp_metrics(outputs,
   response)` explicitly. Choose the refactor.
4. **Investigate Backend's `claude -p exited 1` with empty
   stderr.** Add stderr-tee in `core/llm/claude_code_headless.py`
   so the next failure of this shape gives us the actual error.
   Could be a tool-call panic, an internal permissions denial, or
   a transient quota blip. Until #1 lands, this is invisible
   (the dispatcher catches the exception and moves on).
5. **Re-run the iter-3-shape demo** once #1 + #2 + #3 land so the
   chain finally reaches `pending_review` and the owner can
   approve. Closes the loop iter-3 + iter-4 both reached for but
   neither completed.
6. **HoldQueue persistence (Postgres-backed).** In-memory queue
   loses state on dispatcher restart. Add a `held_messages`
   table + a recovery path on startup. Document the contract in
   ADR-001 update.
7. **`audit_writer` Postgres role enforcement.** Still deferred
   from iter-2, iter-3, iter-4.
8. **Hash-chain alert job.** Scheduled `verify_chain()` with ALERT
   on tamper. Still deferred.
9. **`GitHubTargetRepo` impl.** Waiting on the first commercial
   product (ADR-009).
10. **TL decomposition transactional insert.** A TL crash mid-batch
    leaves orphan child rows; the parent stays `in_progress` forever.
    Wrap the whole TL output batch in one transaction.
11. **`pytest-rerunfailures` plugin pin** for the occasional
    testcontainers `Port mapping` race.
12. **TL `tokens_out=76` anomaly recalibration** — **no longer**
    a priority. iter-4 demo had TL Opus stamp `tokens_out=1992`,
    a normal value. Drop unless a future demo reproduces the
    anomaly.

## Hard constraints unchanged from iter-3 / iter-4

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
  (iter-3 Phase 2); declares `depends_on` **only when recipient
  literally cannot start without** (iter-4 Phase 3). No nested
  sub-decompositions; cycles are undefined behavior.
- TL emits a `BROADCAST(topic="tl.dag_preview")` alongside the
  sub-task assignments (iter-4 Phase 4 default).
- HoldQueue is in-memory only (iter-3 default, iter-4 deferred).
- LLM metrics live in `metadata["llm"]` on the envelope (iter-3
  default — but currently only stamped by TL; iter-5 #3 fixes).
- Per-stage demo task uses the v2 spec
  (`docs/sandbox/idea_validator_v2_spec.md`); iter-2 v1 spec stays
  intact as regression baseline.
- MCP servers in demo configs are invoked via
  `${REPO_ROOT}/.venv/bin/python -m tools.mcp_servers.<name>`
  (iter-4 Phase 2 default), not `uv run python -m …`.
- Anti-loop guard for TL routing is summary-string check, not a
  metadata counter (iter-2c).

## Ready-to-paste prompt for the new session

```
Starting Iteration 5 on the ai_team project.

First, read these in this order:

1. CLAUDE.md
2. docs/iterations/iter_4_retro.md (what just shipped, what's still open)
3. docs/iterations/iter_4_demo_report.md (real-LLM demo findings — five
   distinct failure modes captured)
4. docs/iterations/iter_5_handoff.md (this file — full handoff context)
5. docs/adr/0001-orchestrator-choice.md, 0004-agent-tool-allowlist.md,
   0008-llm-access-strategy.md

Iter-5 priority is the dispatcher exception → synthetic
TASK_REPORT(failed) gap that hung iter-4's chain. After that: claude -p
agent permissions, per-agent _stamp_metrics, then re-run the demo to
finally close the loop through pending_review → owner approve.

Workflow: plan-before-code. Draft docs/iterations/iter_5.md first,
surface for review, then code. Run validation checks + PR merges
yourself (autonomy preference in memory).

Constraints unchanged from iter-4 — see CLAUDE.md gotchas + the
"Hard constraints" section of iter_5_handoff.md.

When ready, create the iter-5 task list and surface the plan.
```
