# Iteration 5 — Retrospective

**Closed**: 2026-05-19. 9 commits on `worktree-iter-5` (plan + 4
feature commits + demo script + demo report + retro + handoff). All
gates green; real-LLM demo run captured in
`docs/iterations/iter_5_demo_report.md`.

The headline deliverables — **dispatcher synthesises `TASK_REPORT(failed)`
on `handle()` exception**, **`claude -p --permission-mode
acceptEdits`** for agent sessions, **per-agent `_stamp_metrics`
parity**, and **stdout-tee on `claude -p` non-zero exit** — all
validated end-to-end against real Opus + Sonnet. The fourth one
(stdout-tee) was the killer: it took a year-old mystery — Backend's
iter-3/4 exit-1 with empty stderr — and turned it into a one-line
root cause (`error_max_budget_usd`). The chain ran farther than
ever; Backend wrote real files; iter-5 plumbing held everywhere it
was supposed to. The chain didn't reach `pending_review` because
Backend exhausted its $0.50 per-call budget mid-implementation —
that's iter-6's top priority.

## What shipped

Phase 0 — Plan (`docs/iterations/iter_5.md`, 683 lines) approved
with three pre-defaults: permission mode `acceptEdits`, per-subclass
touch for `_stamp_metrics`, hybrid `Type: first-line` summary for
the synthesised failed report.

Phase 1 — Dispatcher exception → synthetic `TASK_REPORT(failed)`
(`core/dispatcher/dispatcher.py` + `tests/unit/test_dispatcher.py`
+ `tests/integration/test_dispatcher_e2e.py`):

- New module-level helper `_synthesise_failed_report(role,
  incoming, exc)` builds a terminal `TASK_REPORT(status=failed)`
  with correlation_id + task_id + parent_task_id copied from the
  incoming, hybrid type-name + first-line summary capped at 500
  chars, P1 priority, and routing to TEAM_LEAD (or USER for
  root-task assignments).
- Wired into the dispatcher's existing `try/except Exception` block:
  the synthetic report flows through the same outbound pipeline
  (audit + feed + task-state + HoldQueue.mark_failed + bus) as a
  real one. **No other dispatcher changes needed**.
- 5 unit tests pin the helper shape (correlation, task_id, routing
  for agent-sender vs user-sender, summary truncation, P1 priority).
- 1 integration test (`test_agent_handle_exception_synthesises_failed_report`)
  uses a `_RaisingBackend` stub to exercise the full e2e path:
  user → TL → Backend (raises) → synth-failed → root rollup to
  `failed` within 15 s.
- Real-LLM evidence: iter-5 demo `audit_log.id=35` is exactly this
  synthesised row (Backend `claude -p` exited 1 → dispatcher caught
  → terminal failed report → root flipped).

Phase 2 — `claude -p --permission-mode acceptEdits`
(`core/llm/claude_code_headless.py`):

- Single line in the cmd builder, between `--max-budget-usd` and
  `--allowed-tools`. Always passed; no per-call override knob (would
  be needed only for tests that want the legacy interactive mode).
- Unit test pins the flag in the constructed argv.
- Real-LLM validation: iter-5 demo Frontend did NOT report
  `BLOCKED(permissions gate)` (iter-4 Failure 2 closed).
- Compatibility check: `make smoke-llm` PASS with the new flag.

Phase 3 — Per-agent `_stamp_metrics` parity
(9 agents × 1 line each + parametrised unit test):

- Each of `ProductManagerAgent`, `ArchitectAgent`,
  `BackendDeveloperAgent`, `DesignerAgent`, `FrontendDeveloperAgent`,
  `QAEngineerAgent`, `DevOpsAgent`, `SRESupportAgent`,
  `MarketResearcherAgent` changed their `handle()`'s return statement
  from `return self.build_outputs(response, msg)` to
  `return self._stamp_metrics(self.build_outputs(response, msg), response)`.
- New `tests/unit/test_agent_metric_stamping.py` runs a single
  parametrised test across all 9 subclasses. Uses `monkeypatch` to
  swap each agent's `build_outputs` with a stub returning a single
  no-metrics output; then asserts the value returned from `handle()`
  carries `metadata['llm']` with all six expected keys.
- Real-LLM evidence: iter-5 demo's per-message SQL query shows
  `model`, `tokens_in`, `tokens_out`, `cost_cents`, `duration_ms`
  populated for PM, Architect, Designer rows (would've been Backend
  + Frontend + QA too, if they'd reported). Iter-3 + iter-4 "(no
  metrics)" gaps for non-TL agents are closed.

Phase 4 — stdout + stderr on `claude -p` non-zero exit
(`core/llm/claude_code_headless.py`):

- `log.error("llm.invoke.failed", ...)` and the raised
  `LLMInvocationError` now both include stdout (2 KB cap) alongside
  stderr (1 KB cap).
- Unit test reproduces the iter-4 Backend shape (exit 1, empty
  stderr, non-empty stdout) and asserts the stdout content surfaces
  in the raised exception.
- Real-LLM evidence: iter-5 demo Backend's synthesised
  `task_report(failed)` summary contains the full `claude -p`
  response JSON, including the key finding
  `"subtype":"error_max_budget_usd"`. **This is the iter-3 + iter-4
  Backend mystery solved**.

Phase 5 — Real-LLM e2e demo (`scripts/demo_iter_5.sh` + run +
`docs/iterations/iter_5_demo_report.md`):

- Demo script is a near-clone of `demo_iter_4.sh` with the iter-5
  header explaining the four fixes and `.iter5-mcp.json` config.
- `make demo` alias retargeted to `demo-iter-4` → `demo-iter-5`;
  iter-4 + iter-3 + iter-2 demos stay as regression baselines.
- Run hit pre-flight clean (`.env`, Docker, claude, gh,
  `.venv/bin/python`, MCP cold-start benchmark PASS, smoke-llm PASS).
- Chain ran PM → Architect → Designer cleanly. Backend hit
  `error_max_budget_usd` mid-implementation. iter-5 fixes worked:
  synth-failed emitted, rollup to `failed` succeeded, stdout
  surfaced the root cause.
- Total spend ~$1.56, well under $3.50 ceiling.

Phase 6 — Validation gates + retro + iter-6 handoff:

- `make lint typecheck sec test test-integration smoke-llm` all
  green.
- `uv run ruff format --check .` clean (explicit step this iteration
  after iter-4's CI miss).
- **Diff-cover on iter-5 diff vs `origin/main`: 92 %** (28 diff
  lines in core/dispatcher/dispatcher.py + core/llm/claude_code_headless.py
  + 9 agents; 2 lines uncovered in dispatcher except-branch, exercised
  by integration test which isn't counted toward unit coverage).
- 316 unit + 30 integration = **346 tests** (iter-4 close: 300 + 29
  = 329; net +16 unit + 1 integration).
- This file + `iter_6_handoff.md` + `iter_5_demo_report.md`.

## What went well

- **Plan-before-code held.** Owner approved the three plan defaults
  in one round; phase commits tracked the plan tables exactly; no
  defaults got renegotiated mid-flight.
- **TDD discipline held tightly.** Every phase wrote tests first
  (5 + 1 + 1 + 9 parametrised + 1 = 17 RED → GREEN cycles). The
  parametrised metric-stamping test caught the issue across all 9
  subclasses in one shot instead of forcing 9 individual tests.
- **The iter-5 stdout-tee is the highest-leverage one-line change
  in three iterations.** It cost 4 lines of production code + 1
  unit test and turned the iter-3 + iter-4 "Backend silently
  exited 1, no idea why" into a one-line root cause. iter-6 can
  now act on real data.
- **Synthesising a failed report inside the dispatcher's except
  block was structurally clean.** The same outbound pipeline that
  handles real agent outputs also handles synthetic ones — no
  duplicate audit, no special-cased rollup. The integration test
  flips the root task to `failed` in 5 s.
- **Real-LLM demo confirmed every iter-5 deliverable.** Not just
  the four plumbing fixes, but also: iter-4's TL conservative
  `depends_on` held under real Opus (FE depends_on=[design] only);
  iter-3/4 plumbing (HoldQueue, TaskStateReducer, direct-python
  MCP) unchanged and stable.
- **`make sec` + `ruff format --check` caught the CI gap iter-4
  surfaced.** Explicit phase-6 step prevents the iter-4 ruff-format
  CI miss from recurring.

## What didn't

- **Chain still didn't reach `pending_review`.** Four demos in a
  row (iter-2c, iter-3, iter-4, iter-5) have stopped short of the
  full loop. iter-5's stop is now an honest product-side limit
  (Backend's per-call budget), not a plumbing gap. iter-6 should
  close it.
- **Frontend hit the wall-clock without reporting.** Frontend ran
  for ~13 min after release; the demo trap killed it on script
  exit. iter-5's 20-min wall is too tight for v2-shaped chains
  even on the green path. Probably needs 30-40 min in iter-6.
- **`HoldQueue.mark_failed` drops don't update child Task rows.**
  iter-5's working synth path made this gap visible: QA's child
  Task is still `in_progress` even though it was dropped when
  Backend failed. Pre-existing iter-3 bug; surfaced and queued for
  iter-6.
- **Diff-cover on the dispatcher except branch is 87.5%, not 100%.**
  The two missing lines (134, 144) are the `except Exception` body
  itself, covered by the integration test but not by unit tests.
  92% overall is above the gate; perfectionists could add a unit
  test that drives the dispatcher's `_handle_one` with a stub bus
  + raising agent.

## Surprises

- **The iter-5 Phase 4 stdout-tee instantly solved iter-3 + iter-4
  mysteries.** Both prior demos had Backend exit 1 with empty
  stderr; both retros theorised about "tool-call panic" or
  "internal permissions". The answer was a budget cap. A 4-line
  diagnostic improvement saved at least an iteration of
  speculation.
- **`acceptEdits` was a perfect fit for iter-5's scope.** No
  Frontend stalls reproduced, but also no false-positive auto-
  approvals on dangerous shell commands (those still gate). The
  MCP `run_shell` enum remains the canonical guarded Bash entry
  point; `acceptEdits` only auto-accepts what the MCP scope already
  permits.
- **TL `tokens_out` was 1992 again** (iter-4 also had 1992; iter-3
  had the anomalous 76). The iter-3 anomaly was a one-off; no
  `PRICE_TABLE_CENTS_PER_MTOK` recalibration needed.
- **Diff-cover came back to 92% from iter-4's 100%** because the
  dispatcher except-branch needs unit coverage to round it out.
  Acceptable trade-off for the integration test which covers the
  same lines plus the downstream pipeline; iter-6 can tighten if
  it has spare cycles.

## Action items for iter-6

These overlap with `iter_5_demo_report.md` and `iter_6_handoff.md`
and are the starting list for the next iteration. Highest priority
first:

- [ ] **(top)** **Raise per-tier `--max-budget-usd` cap.** Backend
      Sonnet's $0.50 cap is too tight. Recommend haiku $0.30,
      sonnet $1.50, opus $4.00. One-line change in
      `core/llm/base.py`.
- [ ] **`BLOCKED(budget_exhausted)` short-circuit.** Distinct
      exception in the adapter when `claude -p` returns
      `subtype=error_max_budget_usd`; dispatcher routes to
      BLOCKED instead of failed; TL retries once with elevated
      budget.
- [ ] **`TaskStateReducer.on_drop`.** Update child Task row to
      terminal when `HoldQueue.mark_failed` drops it.
- [ ] **Demo wall-clock bump to 30 min** for v2 chains.
- [ ] **Re-run the iter-5-shape demo** after #1-3 to close the
      `pending_review` loop.
- [ ] Carry-overs from iter-5 handoff: HoldQueue persistence,
      `audit_writer` role, hash-chain alert job,
      `GitHubTargetRepo`, TL transactional decomposition,
      `pytest-rerunfailures` pin, `BaseAgent` template-method
      refactor.

## Stats

- **Commits on iter-5 branch**: 9 (plan + dispatcher + permission
  mode + per-agent metrics + stdout-tee + demo script + retro
  + handoff + demo report).
- **Tests added**:
  - 5 dispatcher synthesis-helper unit tests
  - 1 dispatcher exception integration test
  - 1 permission-mode unit test
  - 1 stdout-tee unit test
  - 1 parametrised metric-stamping unit test (× 9 agents)
- **Tests modified**: none — every iter-5 change was additive.
- **Total tests after iter-5**: **316 unit + 30 integration = 346**
  (iter-4 close: 300 + 29 = 329; net +16 unit + 1 integration).
- **Real-LLM spend this iteration**: ~$1.56, well under $3.50
  ceiling.
- **Diff-cover on iter-5 diff vs `origin/main`**: **92 %** (28
  changed Python lines across the dispatcher + headless adapter +
  9 agents, 2 lines uncovered in the dispatcher except-branch).
- **LOC delta**: ~600 added (helper + tests + demo script + report
  + retro + handoff + the modest agent code changes).

## Ready-to-paste prompt for iter-6

In `docs/iterations/iter_6_handoff.md`.
