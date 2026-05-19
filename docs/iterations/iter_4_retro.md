# Iteration 4 — Retrospective

**Closed**: 2026-05-19. 7 commits on `worktree-iter-4` (plan + 5
feature commits + 1 lint cleanup). All non-demo gates green; the
real-LLM demo surfaced two new failure modes captured in
`docs/iterations/iter_4_demo_report.md`.

The headline deliverables — **MCP direct-python invocation**,
**DAG-preview broadcast**, **conservative `depends_on` prompt** — all
validated end-to-end against real Opus + Sonnet. The iter-3 demo's
two failure modes (MCP cold-start, spurious Frontend `depends_on`) are
both closed. The chain ran further than ever before (Designer ran
twice, Frontend ran for the first time in a demo). It then stalled on
two layers of inherited bugs neither this iteration nor iter-3
addressed: a silent `claude -p` exit-1 from Backend that the
dispatcher catches but doesn't translate into a `TASK_REPORT(failed)`,
and a `claude -p` interactive-permissions gate that holds Frontend's
file write. Both are iter-5 priorities; the iter-4 deliverables
themselves are complete.

## What shipped

Phase 0 — Plan (`docs/iterations/iter_4.md`) committed pre-code with
three defaults the owner approved before the session resumed:
DAG-preview broadcast in Phase 4, hardcoded `$(pwd)/.venv/bin/python`
in demo scripts in Phase 2, and "literally cannot start without"
wording in Phase 3.

Phase 1 — MCP cold-start benchmark
(`scripts/measure_mcp_coldstart.py` + `iter_4_mcp_benchmark.md`):

- Runs `tools/list` against each of `ai_team_bus`, `ai_team_tasks`,
  `ai_team_repo` via both `uv run python -m …` and direct
  `.venv/bin/python -m …`, 10 reps per cell.
- Direct mode: ~42–46 ms median across all three servers, with max
  ≈ median (tight variance). `uv run` mode: ~58–62 ms median, max
  5–10 ms above. Direct is consistently ~15 ms faster.
- Exit-1 gate: any direct-mode median over 100 ms triggers failure.
  Today: PASS.
- Regression hook for iter-5+ work on long-lived MCP transport.

Phase 2 — Direct-python MCP invocation in demo configs
(`scripts/demo_iter_4.sh` + `Makefile`):

- `scripts/demo_iter_4.sh` is a near-clone of `demo_iter_3.sh` with
  the MCP heredoc rewritten so `ai-team-bus`, `ai-team-tasks`,
  `ai-team-repo` all spawn via `${REPO_ROOT}/.venv/bin/python -m …`.
  Config file renamed `.iter3-mcp.json` → `.iter4-mcp.json`. Added
  `.venv/bin/python` existence pre-flight check.
- `make demo` alias retargeted from `demo-iter-3` to `demo-iter-4`.
  `demo-iter-2` and `demo-iter-3` stay as regression baselines.

Phase 3 — TL conservative `depends_on` prompt
(`prompts/team_lead.md` + `tests/unit/test_team_lead_agent.py`):

- Replaced "use `depends_on` liberally" guidance with: "ONLY when the
  recipient literally cannot start without the predecessor's
  artifact" + an explicit self-check ("audit each `depends_on`
  entry: would the recipient genuinely fail without this
  predecessor? If unsure, delete it") + a warning about failure
  cascade drops.
- Snapshot unit test pins both key phrases so a future prompt edit
  can't silently revert the discipline.
- Real-LLM validation: iter-4 demo's TL emitted
  `fe depends_on=[design]` — **not** the iter-3
  `[backend, design]` failure mode.

Phase 4 — TL DAG-preview broadcast
(`agents/team_lead/agent.py` + tests):

- `TeamLeadAgent.build_outputs` now prepends a `BROADCAST(topic=
  "tl.dag_preview")` message to its outputs list. Body is a Markdown
  bullet list rendering each subtask with `slug → recipient
  [depends_on=[…]]: title`.
- Inserted at index 0 so it audits + feed-publishes before any
  per-subtask assignment. Owner sees it in `ai-team watch` seconds
  before agents start working. Informational; not a gate.
- Only emitted on the successful decomposition path; the
  unknown-slug fail-report path stays clean.
- Unit + integration tests updated to filter outputs by
  `message_type` instead of indexing — the broadcast at position 0
  broke 5 unit tests + 1 integration test that previously assumed
  `outputs[0]` was the first task assignment.
- Real-LLM validation: iter-4 demo's `audit_log.id=13` is the
  broadcast row, body verbatim in `iter_4_demo_report.md`.

Phase 5 — Real-LLM e2e demo run:

- See `docs/iterations/iter_4_demo_report.md`. Pre-flight (`.env`,
  Docker, claude, gh, `.venv/bin/python`, `measure_mcp_coldstart.py`
  PASS, `make smoke-llm` PASS) all green.
- Chain produced 13 audit rows: user → TL → broadcast +
  6 sub-task assignments → PM done → Architect done → Designer done
  → Frontend BLOCKED on a `claude -p` permissions gate. Backend's
  `claude -p exited 1` with empty stderr was caught by the
  dispatcher but not converted into a `TASK_REPORT(failed)`, so the
  chain hung until the 20-min wall-clock.
- iter-4 deliverables: all confirmed. iter-3 failure modes: closed.
  New failure modes for iter-5: 5 distinct issues catalogued.

Phase 6 — Validation gates + retro + iter-5 handoff:

- `make lint typecheck sec` green. `make test` + `make
  test-integration`: 300 unit + 29 integration tests pass (was
  299 + 29 at iter-3 close; net +1 unit test from the prompt-
  snapshot pin and the DAG-preview test).
- **Diff-cover on iter-4 diff vs `origin/main`: 100 %** (14 lines
  added in `agents/team_lead/agent.py`, all covered). Well over the
  80 % gate.
- This file + `iter_5_handoff.md`.

## What went well

- **Plan-before-code stayed tight.** The plan landed first as a
  single commit (`d2c6909`), each phase's work followed exactly the
  table in `iter_4.md`, the three pre-approved defaults didn't get
  renegotiated mid-flight.
- **TDD discipline held.** Both new tests (the prompt snapshot and
  the DAG-preview broadcast) failed first with the right error
  before implementation, then passed without test edits. The 5+1
  follow-on test breakages from the broadcast-at-index-0 change
  were caught immediately by the full suite.
- **The "filter by `message_type`" refactor** of unit + integration
  tests is more robust than the old positional indexing — the next
  agent/output-order change won't break a half-dozen tests.
- **`scripts/measure_mcp_coldstart.py` exit-1 gate** turned the
  iter-3 cold-start failure mode into a number we can watch over
  time. The 100 ms threshold gives generous headroom; the actual
  numbers are 2× under it.
- **Real-LLM validation surfaced exactly the regressions iter-4
  promised to fix** and **none of the regressions it didn't claim
  to touch**. The two new failure modes (Backend exit-1, Frontend
  permissions gate) are independent of iter-4's deliverables.
- **TL `tokens_out` anomaly didn't reproduce.** iter-3 demo's
  `tokens_out=76` carry-over to "investigate or recalibrate"
  collapsed to "no action" — iter-4's TL Opus stamped a normal
  `1992`. Saved iter-5 a price-table audit.

## What didn't

- **Chain still didn't reach `pending_review`.** Three demos in a
  row (iter-2c, iter-3, iter-4) reached for the full
  PM → Architect → Backend → QA → review → approve loop and
  stopped short, each on a different failure mode. The
  iter-4 demo report's Failure 1 (dispatcher exception → no
  terminal task_report) and Failure 2 (claude -p permissions
  gate) are the iter-5 path to finally close it.
- **Pre-existing metadata-stamping gap surfaced.** Only TL stamps
  `metadata["llm"]` on its outputs; every other agent overrides
  `handle()` and skips the helper. The iter-3 demo report's
  table claimed per-agent metrics that don't actually live in
  audit metadata — iter-4 demo's identical SQL query shows empty
  `{}` for non-TL rows. This is iter-5 cleanup.
- **The 5 integration/unit test breakages from the broadcast at
  index 0** could've been avoided with a more upfront test
  refactor in the plan. The plan called out exactly one test edit
  ("`test_build_outputs_emits_one_message_per_subtask` length
  assertion"); reality was 5 unit + 1 integration. Small
  underestimate — the test-update list in
  `iter_4.md` Phase 4 was incomplete. Easy enough to fix mid-
  phase but a planning miss.

## Surprises

- **Backend's `claude -p exited 1` with empty stderr.** A genuinely
  new failure mode. The MCP cold-start fix in Phase 2 worked — the
  agent's inner LLM call started and ran for ~6 min before
  crashing with no diagnostic output. Until we add stderr-tee in
  the headless adapter, the actual failure is invisible.
- **Frontend's permissions gate is one layer up from the MCP
  scope.** We had `AI_TEAM_PATH_PREFIXES="*"` on the MCP server,
  so the path scope was wide open — yet the inner `claude -p`'s
  own permissions layer held the write at an approval gate. The
  MCP wrapper doesn't see this; it never gets called. The fix
  belongs in the `claude -p` invocation (`--permission-mode
  acceptEdits` or similar), not in the MCP layer.
- **`mark_failed` cascade was the right call after all.** iter-3
  retro questioned whether "any-failed → root failed" was too
  aggressive; iter-4 demo proves it was the right shape — the
  problem wasn't the cascade, it was that we never *had* a
  `failed` to cascade from (Backend's silent crash). Fix the
  emission and the cascade does its job.
- **DAG preview rendered cleanly without any escaping.** TL Opus
  produced a Markdown body that's directly usable in
  `ai-team watch` and in the demo report. No surprise truncation
  or weird whitespace. The 80-char title clamp held.

## Action items for iter-5

These overlap with `iter_4_demo_report.md` and `iter_5_handoff.md`
and are the starting list for the next iteration. Highest priority
first:

- [ ] **(top)** **Dispatcher exception → synthetic
      `TASK_REPORT(failed)`.** Most impactful: closes the "agent
      crashed → chain hangs" pattern that hit iter-4 demo Backend.
- [ ] **`claude -p` agent permissions policy.** Pick:
      `--permission-mode acceptEdits` / `bypassPermissions` on
      inner sessions, or rewrite agent prompts to use MCP
      `write_file_in_scope` instead of `Write`. Document the
      choice in ADR-008.
- [ ] **Per-agent `_stamp_metrics` parity.** Refactor `BaseAgent`
      so every override of `handle()` still stamps metrics — or
      audit each subclass and add the call. iter-4's demo report
      had to flag "(no metrics)" for 5 agent rows.
- [ ] **Stderr-tee in the headless adapter** so the next silent
      `claude -p exited 1` gives us a diagnostic.
- [ ] **Re-run the demo** after #1 + #2 + #3 land — close the
      pending_review loop iter-3 + iter-4 both reached for.
- [ ] **HoldQueue persistence** (Postgres-backed). Deferred from
      iter-3 and iter-4.
- [ ] **`audit_writer` Postgres role enforcement.** Deferred.
- [ ] **Hash-chain alert job.** Deferred.
- [ ] **`GitHubTargetRepo`** — first commercial product.
- [ ] **TL transactional decomposition.**
- [ ] **`pytest-rerunfailures` pin.**

## Stats

- **Commits on iter-4 branch**: 7 (plan + benchmark + demo +
  prompt + broadcast + lint cleanup + final retro/handoff/demo
  report).
- **Tests added**:
  - 1 TL prompt snapshot test
  - 1 TL DAG-preview broadcast test
- **Tests updated**:
  - 5 unit tests in `test_team_lead_agent.py` switched from
    positional indexing to `message_type`-based filtering
  - 1 integration test in `test_dispatcher_e2e.py` updated
    to expect 4 audit rows (was 3) and assert exactly one
    `broadcast` row
- **Total tests after iter-4**: **300 unit + 29 integration =
  329** (iter-3 close: 298 + 29; net +2 unit).
- **Real-LLM spend this iteration**: ~$1.00–$1.20 estimated
  (gap from Failure 3 — most agents don't stamp metrics). Well
  under the $3.00 ceiling.
- **Diff-cover on iter-4 diff vs `origin/main`**: **100 %** (14
  changed lines in `agents/team_lead/agent.py`, all covered;
  other diff hunks are docs / shell / config / tests, not
  in coverage scope).
- **LOC delta**: ~1100 added (plan + benchmark + script + report
  + retro + handoff + the modest TL/agent code changes).

## Ready-to-paste prompt for iter-5

In `docs/iterations/iter_5_handoff.md`.
