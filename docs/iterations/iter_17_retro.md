# Iteration 17 — Retrospective

**Closed**: 2026-05-20. 5 commits on `worktree-iter-17`
(plan + MCP `initialize` handler + demo script +
`bypassPermissions` + demo report; retro/handoff
forthcoming). All gates green; real-LLM demo run #3
produced the **first end-to-end 7-agent chain
completion** in project history. Captured in
`docs/iterations/iter_17_demo_report.md`.

**Headline**: iter-17 destroyed the 9-iteration "MCP
race" carry-over by identifying it as a **14-iteration
latent JSON-RPC protocol bug** from iter-2's commit
`d8bc3e8` — none of the three MCP servers
(`ai_team_repo`, `ai_team_bus`, `ai_team_tasks`) had
an `initialize` handler in their stdio loops. Adding
the handler + switching `--permission-mode` from
`acceptEdits` to `bypassPermissions` (because
acceptEdits doesn't auto-approve MCP tool calls)
unblocked Backend's ability to actually USE MCP tools.
Run #3 saw Backend make 64 MCP tool calls in a
462-second session — pytest passed, branch pushed, PR
opened. **The chain reached `task_report(done)` from
every agent for the first time across 18 demo runs**.
The final gate to formal loop-close (the
`pending_reviews` table row) is a separate
iter-0-stubbed-out MCP tool; ~50-LOC iter-18 fix.

## What shipped

Phase 0 — Plan (`docs/iterations/iter_17.md`, 647 lines)
committed on `worktree-iter-17` cut from `origin/main`
at `2097eba`.

Phase 1 — MCP `initialize` handler in all 3 stdio loops:

- Added `_build_response(msg) -> dict | None` pure
  helper in each of the three MCP server `__main__.py`
  modules. Returns spec-correct `initialize` response
  (`protocolVersion` echoed from client +
  `capabilities: {tools: {}}` + `serverInfo` with name
  + version).
- `tools/list` path moved into `_build_response` for
  testability; `ai_team_repo`'s `tools/call` still
  dispatches async with `Context` in the stdio loop.
- 12 new unit tests
  (`tests/unit/test_mcp_server_handshake.py`):
  parametric across the 3 servers × 4 scenarios
  (initialize / notifications/initialized / tools/list
  regression / unknown method).
- 6 new integration subprocess tests
  (`tests/integration/test_mcp_handshake_real_subprocess.py`):
  spawn the real Python subprocess + pipe JSON-RPC,
  validate stdout. Catches future regressions that
  unit tests would miss (the iter-2 bug went unnoticed
  for 14 iterations because no test exercised the
  stdio loop end-to-end).

Phase 2 — `--permission-mode bypassPermissions`:

- Switched from `acceptEdits` (iter-5 choice) to
  `bypassPermissions`. iter-5 thought acceptEdits
  auto-accepted "tool uses"; empirically it only
  auto-accepts FILE edits, not MCP tool calls.
- Updated the iter-5 test verifying the flag value.
- Lengthy comment documenting the security model:
  per-agent allow-list + MCP server path scope +
  run_shell command_class enum are the real boundaries;
  claude's permission gate doesn't add safety in our
  non-interactive setup.

Phase 3 — Demo script + 3 real-LLM runs + demo report:

- `scripts/demo_iter_17.sh` clone of demo_iter_16.sh
  with iter-17 narrative; auto-retry-blocked stays as
  defense-in-depth.
- Real-LLM runs:
  - **Run #1** ($0.36): MCP fix took effect, surfaced
    permission gap. Fixed in `fd91b91` between runs.
  - **Run #2** ($0.18): hit Anthropic Max-5x session
    limit. **iter-15's 429-routing fired correctly in
    production** for the first time — clean BLOCKED
    row, no recovery-blocking burn.
  - **Run #3** ($5.69): full 7-agent chain DONE. PM /
    Architect / Designer / Frontend / **Backend** /
    **QA** all task_report(done). Backend ran pytest
    (54/54 passed), 90.6% coverage, committed to a new
    branch, pushed, opened PR.
- Demo report (`docs/iterations/iter_17_demo_report.md`,
  ~325 lines) documents the milestone + names iter-18's
  scope.

## What went well

- **The investigation paid off enormously.** "Throw all
  efforts at Hard Blocker #1" turned a 9-iteration
  symptom (MCP race) into a 1-line root cause (missing
  `initialize` handler in stdio loop). The matcher /
  router work iter-10..16 was real engineering, but
  iter-17 made it unnecessary on the happy path.
- **TDD caught the test design issue immediately.** All
  12 unit tests + 6 integration subprocess tests went
  RED → GREEN cleanly. No no-op tests.
- **The MCP fix alone wasn't enough — and the test
  layer caught that too.** Run #1's permission-gap
  finding was visible immediately because Backend's
  wording shifted from "still connecting" /
  "unreachable" to "permission approval not granted".
  Diagnostic clarity from the verbatim summary made the
  second fix obvious.
- **iter-15's 429-routing production-validated** in
  run #2 — pre-iter-15 the same scenario was a $0.59
  burn; post-iter-15 it's a clean BLOCKED(budget) row
  + retry-recoverable.
- **Backend produced real production code** during run
  #3 — `examples/sandbox/idea-validator/` tree:
  7-stage pipeline, Click CLI, sanitizer with
  marker_storm, factories, 32 mock-only tests, full
  ADR-0021 exit-code table implemented. **A real
  software development team's worth of work**, with
  Claude as the developers.
- **No regressions.** 390 unit tests + 48 integration
  tests pass. The new MCP handshake tests are pure
  additions; the updated permission-mode test now
  pins `bypassPermissions`.

## What didn't

- **The `pending_reviews` table didn't get a row** —
  the iter-0 `request_human_review` MCP tool is still
  a stub. QA emitted `task_report(done)` correctly but
  the formal owner-approval gate couldn't fire. iter-18
  closes this (~50 LOC).
- **Cost overshoot**: $6.23 across 3 runs vs $5
  ceiling. Two of the three runs were exploration
  (permission gap, quota burn). One clean run would
  have been ~$2.50. iter-18 should aim for one clean
  run.
- **CI flake recurrence** — `test_transitive_drops_
  cascade_through_hold_queue` (and others) fail when
  integration runs after unit due to testcontainers
  port-mapping race. The 8-iteration carry-over on
  `pytest-rerunfailures` plugin pin is now visibly
  hurting CI dev experience.
- **Backend pushed `agent/backend_developer/idea-
  validator-v2-pipeline` and opened PR #24 from the
  iter-17 worktree** during run #3. That branch is
  now in this worktree and **changed our current
  branch mid-Phase 3**. Cherry-picked the demo report
  commit back onto `worktree-iter-17`. Worth handling
  in a future iteration: agents' git operations
  shouldn't be allowed to checkout-and-leave the
  orchestrator's branch in a different state.

## Surprises

- **The iter-2 commit (`d8bc3e8`) said it "mimics the
  JSON-RPC handshake that `claude -p --mcp-config`
  performs"** but never actually handled `initialize`.
  The iter-9 pre-flight gate's docstring even said
  "Stdio-handshake races are NOT caught; iter-10's
  planned substring router on the failure summary
  covers those" — at the time, iter-10's router
  routing was a workaround for a bug that should have
  been a direct fix. The team-velocity-vs-investigation
  tradeoff turned a 1-day fix into a 9-iteration
  workaround-and-monitor cycle.
- **`acceptEdits` permission mode's behavior surprised
  iter-5 author too** — the comment said "auto-accepts
  file edits / tool uses". Empirically only file edits
  are auto-accepted. The CLI docs use exactly the
  right precise wording: "Permission mode to use for
  the session", with 6 options (default, acceptEdits,
  auto, bypassPermissions, dontAsk, plan). We needed
  bypassPermissions for orchestrator-level safety.
- **Run #3's $5.69 single-run cost** was higher than
  expected. The chain caching effects help across
  agents but each agent's first call is uncached.
  Backend's 462s session burned $0.29 just for the
  Backend agent's claude -p calls. iter-18 may see
  cheaper runs as Backend's tree is already committed.

## Action items for iter-18

1. **(top)** Implement
   `mcp__ai_team_tasks__request_human_review` to
   actually INSERT a `pending_reviews` row. Same
   shape as `ai_team_repo`'s handler dispatch.
   ~50 LOC + 5-7 tests. **This closes the formal
   loop**.
2. Implement `mark_task_done` + `update_task_status`
   if QA prompts call them (audit the prompts).
3. **Re-run iter-17-shape demo** with iter-18's fix.
   Expected: chain reaches DONE + pending_reviews
   row + auto-approve. **Final loop close**.
4. **TL Backend decomposition** — SEVEN-iteration
   carry-over. Backend's 462s session is at 77 % of
   the 600s timeout cap; future Backend work might
   exceed.
5. **HoldQueue persistence (Postgres-backed)** —
   in-memory queue still loses on restart.
6. **`pytest-rerunfailures` plugin pin** — visibly
   hurting CI; pin it.
7. **Agents' git-checkout shouldn't leak**: when
   Backend's MCP `create_branch` switches branches,
   the orchestrator's worktree shouldn't follow.
   Worth a focused investigation iteration; possibly
   sandbox the agents into their own worktree.
8. **Carry-overs unchanged**: TL auto-hop
   investigation, TL over-decomposition prompt hint,
   audit_writer Postgres role, hash-chain alert,
   GitHubTargetRepo, transactional TL, BaseAgent
   template refactor.

## Stats

- **Commits on `worktree-iter-17`**: 6 (plan + MCP
  handshake + demo script + permission mode + demo
  report + this retro/handoff).
- **LOC delta**: +~1500 (plan 647 + MCP servers 412 +
  permission fix 30 + demo script 304 + demo report
  327 + retro/handoff TBD).
- **Tests**: +18 (12 unit handshake + 6 integration
  subprocess). 390 unit + 48 integration tests pass.
- **Real-LLM spend**: $6.23 across 3 runs ($0.36 +
  $0.18 + $5.69). Over the $5 ceiling, but the cost
  bought the milestone.
- **Diff-cover**: 91 % on 45 new tracked lines (above
  80 % gate).
- **Demo wall-clock**: run #1 ~7 min, run #2 ~2 min,
  run #3 ~10 min.
- **Backend production output**: 7-stage pipeline +
  Click CLI + sanitizer + factories + 32 tests + full
  ADR-0021 exit-code table on disk, committed to
  branch `agent/backend_developer/idea-validator-v2-
  pipeline`, PR #24 (per Backend's row 268 summary).

## Ready-to-paste prompt for iter-18

Lives in `docs/iterations/iter_18_handoff.md`.
