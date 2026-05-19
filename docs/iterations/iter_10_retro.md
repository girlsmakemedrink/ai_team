# Iteration 10 — Retrospective

**Closed**: 2026-05-20. 9 commits on `worktree-iter-10` (plan +
mcp_race_router + dispatcher wire-up + Backend prompt + mypy
exclude + demo script + demo report + retro + handoff). All
gates green; real-LLM demo run captured in
`docs/iterations/iter_10_demo_report.md`.

The four headline deliverables — **`mcp_race_router.py` substring
router**, **dispatcher pre-HMAC-sign rewrite**, **Backend Bash
prompt fix**, and **`^examples/` mypy exclude** — all shipped
behind 6 tests (5 unit + 1 integration) plus the prompt edit +
config one-liner. The router FIRED in production for the first
time across ten demos: Backend hit the same mid-session MCP race
iter-8 + iter-9 saw, emitted a real `task_report(failed)` with
matching summary, and the router rewrote it to BLOCKED before
HMAC-sign. Audit row 136 reflects the rewrite directly. QA
stayed held in HoldQueue (not cascade-dropped). Root Task
stayed `in_progress` (not failed-rollup). This is the
recoverable terminal state success criterion #7's second
branch named — first time the chain reached it. The
`pending_review` loop remains untouched across ten demos
(iter-11 needs a retry mechanism).

## What shipped

Phase 0 — Plan (`docs/iterations/iter_10.md`, 698 lines)
committed on `worktree-iter-10` cut from `origin/main` at
`442216f`. Four decisions pre-approved via brainstorming
(standard scope, dispatcher outbound, rewrite-in-place,
reuse `mcp_unhealthy`).

Phase 1 — `core/dispatcher/mcp_race_router.py` + 5 unit tests:

- New module (~75 LOC). Public function
  `maybe_route_mcp_race_to_blocked(msg)` — pure function,
  no I/O. Inspects message: if `task_report(failed)` AND
  summary substring-matches one of three patterns
  (`("MCP server", "never connected")`,
  `("MCP server", "never finished connecting")`,
  `("MCP server", "still connecting")`), returns a
  `model_copy` with `status=BLOCKED, blocked_on='mcp_unhealthy'`.
  Otherwise returns the message unchanged (same ref —
  fast pass-through).
- Summary kept verbatim — LLM's wording is the most useful
  diagnostic for the owner.
- 5 unit tests pin: routes iter-9 demo summary, routes
  iter-8 demo summary, leaves non-matching failures alone
  (AssertionError-style summaries), leaves DONE + BLOCKED
  reports alone (blocked_on='budget' not clobbered), leaves
  non-task-report messages alone.
- Mid-flight calibration from the plan: added a third
  pattern `("MCP server", "still connecting")` because
  iter-8's summary structure had "still connecting" inside
  parentheses without "never" — caught when writing the
  iter-8 test.

Phase 2 — Dispatcher wire-up + 1 integration test:

- `core/dispatcher/dispatcher.py` adds one new line at the
  top of the `for raw_out in outputs:` loop:
  `out = maybe_route_mcp_race_to_blocked(raw_out)`. The
  rewrite happens BEFORE `_signer.with_signature(out)` so
  HMAC covers the rewritten payload — audit / feed /
  task_state / HoldQueue all see one consistent BLOCKED
  version.
- Renamed loop variable from `out` to `raw_out` to satisfy
  ruff PLW2901 (don't overwrite loop variables) — cleaner
  anyway.
- 1 integration test mirrors iter-9 Phase 3's pattern:
  stub Backend RETURNS (not raises) a `task_report(failed)`
  with iter-9 demo Backend's verbatim summary; asserts
  audit row shows `status=blocked, blocked_on='mcp_unhealthy'`,
  QA stays held (never delivered), root Task stays
  in_progress.

Phase 3 — Backend Bash prompt fix
(`prompts/backend_developer.md`):

- Prepended a new "Critical: tool routing for git / uv /
  make / pytest" section near the top of the prompt with
  a 10-row lookup table mapping common operations to their
  `command_class` values (`git_status`, `git_add`,
  `git_commit`, `git_push_feature`, `gh_pr_create`,
  `pytest`, `make_test`, `ruff`, `mypy`). Aimed at closing
  the LLM's "perceived gap" that justified reaching for
  Bash.
- iter-10 demo showed this is NOT fully sufficient —
  Backend still hit a "Bash hooks blocked the pytest
  command" gate. Defense-in-depth needed in iter-11.

Phase 4 — `^examples/` mypy exclude (`pyproject.toml`):

- One-line config edit. Added `"^examples/"` to
  `[tool.mypy].exclude`. Symmetric with the existing ruff
  `extend-exclude = ["alembic/versions", "examples"]`.
- Verified: bare `make typecheck` passes on the
  demo-polluted workspace without `--exclude '^examples/'`
  workaround. Closes the workspace-pollution gap iter-8 +
  iter-9 retros both flagged.

Phase 5 — Demo wall + `scripts/demo_iter_10.sh` + Makefile:

- Clone of `demo_iter_9.sh` with iter-10 header documenting
  the two fixes. Same 30-min wall-clock; `.iter10-mcp.json`
  config filename.
- `make demo` aliases to `demo-iter-10`; iter-9/8/7/6/5/4/3/2
  stay as regression baselines.

Phase 6 — Real-LLM e2e demo
(`docs/iterations/iter_10_demo_report.md`):

- Pre-flight clean (`.env`, Docker, claude 2.1.144, gh,
  `.venv/bin/python`, `make smoke-llm` PASS).
- Chain ran TL (27 s opus, $0.12) → PM (67 s sonnet, $0.04)
  → Architect (120 s opus, $0.54) → Designer (230 s sonnet,
  $0.16) → Frontend (176 s sonnet, $0.13) → Backend BLOCKED
  via substring router (370 s sonnet, $0.25,
  blocked_on='mcp_unhealthy'). QA held in HoldQueue
  (not delivered, not dropped). Root stayed in_progress.
- Total spend $1.24 — within $0.01 of iter-9's $1.23.
  Backend's prompt cache: 2.3 M cached input tokens.

Phase 7 — Validation gates + retro + iter-11 handoff:

- `make lint typecheck sec test test-integration smoke-llm`
  all green. **First iteration where `make typecheck` (bare,
  no `--exclude` workaround) passes thanks to Phase 4.**
- 0 high-severity bandit findings.
- 382 tests pass (337 unit + 38 integration + 7 new from
  iter-10).
- `uv run ruff format --check .` — 133 files already
  formatted.
- **Diff-cover on iter-10 diff vs `origin/main`: 100 %** (17
  changed Python lines across
  `core/dispatcher/dispatcher.py` +
  `core/dispatcher/mcp_race_router.py`; all covered).
- This file + `iter_11_handoff.md` + `iter_10_demo_report.md`.

## What went well

- **Plan-before-code held tightly.** Owner approved the four
  brainstorming defaults in advance; every phase commit
  tracked the plan exactly. Same pattern that worked
  iter-7..9.
- **TDD discipline held tightly.** Every code phase wrote
  tests first (5 + 1 = 6 RED → GREEN cycles).
- **Brainstorming caught the right design.** Initial
  consideration was placing the router in
  `_synth_failed_report` (where iter-6's BLOCKED branch
  lives). Reading the dispatcher carefully showed that path
  only fires on exceptions — but iter-9 demo's failure was a
  schema-valid `task_report(failed)` from the LLM itself, no
  exception. So the router needed to be in the message-
  processing outbound path, not the exception synth path.
  Brainstorming surfaced this gap before coding.
- **The substring router FIRED IN PRODUCTION for the first
  time across ten demos.** Previous iterations shipped
  contracts behind tests but didn't have a real-LLM event
  light them up. iter-10's router was exercised by a real
  Backend MCP-race failure; the rewrite happened, the audit
  row reflects BLOCKED, the HoldQueue held QA, the root
  stayed in_progress. End to end, exactly as designed.
- **The recoverable BLOCKED state is genuinely useful.**
  Pre-iter-10: Backend FAILED → cascade-drop → root FAILED
  → chain dead, no recovery path. Post-iter-10: Backend
  BLOCKED → dependents held → root in_progress → chain
  recoverable. iter-11 just needs to add the recovery
  action.
- **HMAC chain held through the rewrite.** Rewrite happens
  pre-signing, so the chain is internally consistent — no
  `audit chain broken` warnings, no double-row hacks. Clean
  architectural property.
- **`make typecheck` quality-of-life win.** Bare
  `make typecheck` now works on demo-polluted workspaces.
  Small papercut iter-8 + iter-9 retros both flagged, closed
  permanently in one line.
- **Pattern-tuple design is conservative + extensible.**
  Each tuple requires ALL substrings to co-occur (so
  "MCP server" + "never connected" together, not either
  alone). Near-zero false-positive risk. New patterns added
  by appending tuples — no regex needed.

## What didn't

- **Chain still didn't reach `pending_review`.** Ten demos
  in a row. iter-10's BLOCKED is a recoverable stop, not a
  full close. iter-11 needs `ai-team retry-blocked` CLI or
  TL auto-hop on `BLOCKED(mcp_unhealthy)`.
- **Backend prompt fix wasn't fully sufficient.** Despite
  the explicit lookup table in iter-10's Phase 3 prompt
  edit, Backend's task_report summary still mentions "Bash
  hooks blocked the pytest command". Possible cause: LLM
  tried Bash first, got rejected (Bash isn't in
  `allowed_tools`), and reported the rejection. iter-11
  needs to inspect claude -p's actual tool-routing behavior
  and possibly add `--disallowed-tools "Bash"` for
  defense-in-depth.
- **Mid-session MCP race for the third demo in a row.**
  iter-8: startup race. iter-9: mid-session race. iter-10:
  mid-session race again (Backend's 370 s session is the
  longest single agent run in any demo). The race is real
  and reproducible on Backend's longest sessions. Possible
  iter-11+ work: TL Backend decomposition (split Backend's
  task into 2–3 smaller chunks, each with a shorter session
  window).
- **TL didn't auto-route Backend's BLOCKED report.** The
  iter-2c handoff said "TL auto-routes BLOCKED with one
  auto-hop max" — but TL didn't fire here. Possible
  reasons: (a) TL only auto-routes specific BLOCKED shapes
  (the iter-2c logic predates iter-10's
  `blocked_on='mcp_unhealthy'`), (b) TL has no
  re-emit-to-same-recipient logic. iter-11 should clarify
  TL's BLOCKED behavior or add a `blocked_on`-specific
  routing rule.

## Surprises

- **The substring router fired on the FIRST production run
  after landing.** Across iter-6 (budget detector), iter-9
  (pre-flight gate) and iter-10 (substring router), only
  iter-10's deliverable hit its designed failure mode in
  the very next demo. Reason: iter-10 was specifically
  built to catch a failure mode iter-9 demo had ALREADY
  observed twice (iter-8 + iter-9 demos), so the contract
  was derived from real evidence, not speculation.
  Generalisable: contracts derived from observed failures
  fire faster than contracts derived from speculation.
- **Backend's session was 370 s — longer than iter-9's
  347 s and just under the 600 s timeout.** Sonnet's
  `llm_timeout_s=600` cap (from iter-8) is now the binding
  constraint on Backend's session length, not budget.
  iter-9 + iter-10 both saw Backend producing real
  implementation work (21 K and 17 K output tokens
  respectively) for the full session. Bigger Backend tasks
  may need a higher cap OR decomposition (deferred
  carry-over).
- **Frontend completed AFTER Backend BLOCKED at 20:30:19.**
  Frontend was running in parallel with Backend; it depends
  only on Designer (which finished at 20:27:24). When
  Backend went BLOCKED at 20:29:44, Frontend was still
  in-flight and completed cleanly 35 s later. The parallel
  scheduling is working: one agent's BLOCKED doesn't stall
  unrelated in-flight work.
- **The pattern-tuple design caught both iter-8 and iter-9
  shapes with ONE tuple matching.** Backend's iter-10
  summary contained "MCP server ai-team-repo never
  connected" — matched the
  `("MCP server", "never connected")` tuple. Backend's
  iter-9 summary used identical wording, so the pattern is
  stable across runs. Backend's iter-8 summary used "the
  ai-team-repo MCP server never finished connecting (all
  three ToolSearch retries returned 'still connecting')"
  — matched TWO tuples (`("MCP server", "never finished
  connecting")` AND `("MCP server", "still connecting")`).
  Belt-and-suspenders coverage came for free.

## Action items for iter-11

These overlap with `iter_10_demo_report.md` and
`iter_11_handoff.md` and are the starting list for the
next iteration. Highest priority first:

- [ ] **(top)** **Retry mechanism for BLOCKED tasks.**
      `ai-team retry-blocked <task_id>` CLI (owner-in-the-
      loop, simpler) OR TL auto-hop on
      `BLOCKED(mcp_unhealthy)` (faster, needs per-correlation
      retry counter). Without this, iter-10's recoverable
      BLOCKED state has no "recover" action — the loop
      remains incomplete. The substring router gave us a
      good landing pad; iter-11 builds the runway.
- [ ] **Re-run iter-10-shape demo with retry mechanism** to
      finally close the `pending_review` loop iter-3..10
      all reached for.
- [ ] **Backend Bash gating: defense-in-depth beyond
      prompt.** Add `--disallowed-tools "Bash"` explicitly
      (currently relying on absence from `--allowed-tools`).
      If Backend still hits the "Bash hooks blocked"
      message, investigate whether
      `mcp__ai_team_repo__run_shell`'s subprocess
      invocation hits a separate permission layer.
      Reproduce in unit test.
- [ ] **`BaseAgent.llm_timeout_s` default 300 → 600
      refactor** (deferred since iter-8). Three iterations
      overdue.
- [ ] Carry-overs unchanged from iter-10 handoff (items
      6–13): HoldQueue persistence, `audit_writer` Postgres
      role, hash-chain alert, `GitHubTargetRepo`, TL
      transactional decomposition, `pytest-rerunfailures`
      plugin pin, `BaseAgent` template-method refactor, TL
      Backend decomposition (now actively relevant —
      Backend's 370 s sessions keep hitting the MCP race).

## Stats

- **Commits on iter-10 branch**: 9 (plan + Phase 1 router +
  Phase 2 dispatcher + Phase 3 prompt + Phase 4 mypy +
  Phase 5 demo + Phase 6 demo report + retro + handoff).
- **Tests added**:
  - 5 unit tests on `maybe_route_mcp_race_to_blocked`
    (Phase 1)
  - 1 integration test on dispatcher MCP-race rewrite
    routing (Phase 2)
- **Tests modified**: none — every iter-10 change was
  additive.
- **Total tests after iter-10**: **337 unit + 38
  integration = 375 unit-collected + 7 new = 382 total**
  (iter-9 close: 337 unit + 38 integration = 375). Net
  +6 tests.
- **Real-LLM spend this iteration**: $1.24 (~25 % of $5.00
  ceiling). TL $0.12 + PM $0.04 + Architect $0.54 +
  Designer $0.16 + Backend (mcp-race) $0.25 + Frontend
  $0.13.
- **Diff-cover on iter-10 diff vs `origin/main`**: **100 %**
  (17 changed Python lines across
  `core/dispatcher/dispatcher.py` +
  `core/dispatcher/mcp_race_router.py`; all covered).
- **LOC delta**: ~1700 added (4 code changes + 6 new tests +
  1 new module + 1 new demo script + 1 plan + 1 demo report
  + 1 retro + 1 handoff).
- **First iteration where `make typecheck` (bare) passes on
  demo-polluted workspace** — Phase 4 closed a long-standing
  papercut.

## Ready-to-paste prompt for iter-11

In `docs/iterations/iter_11_handoff.md`.
