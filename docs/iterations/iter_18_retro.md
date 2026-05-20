# Iteration 18 — Retrospective

**Closed**: 2026-05-20. 8 commits on `worktree-iter-18`
(plan + handlers + __main__ wire + QA prompt +
integration test + lint/typecheck fixes + demo script +
demo report; retro/handoff forthcoming). All gates
green; real-LLM demo run #2 produced the **first
`pending_review` row across 18 iterations** + the row
was resolved to `approved` via the existing
`/api/reviews/{id}/approve` endpoint.
**The formal owner-approval loop closes end-to-end for
the first time in project history.**

**Headline**: iter-17 destroyed the 9-iteration "MCP
race" carry-over and produced the first end-to-end
7-agent `task_report(done)` chain. iter-18 closes the
one remaining piece — the iter-0 stub
`mcp__ai_team_tasks__request_human_review` — with
~140 LOC of handler code (mirror of
`ai_team_repo/handlers.py` shape) + 12 new tests
(9 unit sqlite + 2 integration Postgres + 1 schema
regression). The row that's been theoretical since
ADR-001 is now physically in the table.

## What shipped

Phase 0 — Plan (`docs/iterations/iter_18.md`, 1210
lines) committed on `worktree-iter-18` cut from
`origin/main` at `2045515` (iter-17 squash).

Phase 1 — `handlers.py` with TDD:
- New module `tools/mcp_servers/ai_team_tasks/handlers.py`:
  `Context` frozen dataclass (session_factory +
  `default_agent` sourced from `AI_TEAM_AGENT_ROLE`),
  `Context.from_env()` reading `POSTGRES_DSN`,
  `handle_request_human_review` async (INSERT
  `PendingReview` via SQLAlchemy session), STUBS for
  `mark_task_done` + `update_task_status` (deferred —
  audit prompts first), `HANDLERS` map.
- `aiosqlite` added as dev-dep for in-memory async
  test DB.
- 9 unit tests (`tests/unit/test_mcp_ai_team_tasks_handlers.py`):
  happy path, missing summary, missing correlation_id,
  malformed correlation_id, default-agent fallback,
  `Context.from_env` defaults + overrides, stub
  regression for the other two tools.

Phase 2 — `__main__.py` wired:
- Server version bumped 0.1.0 → 0.2.0.
- `tools/call` async dispatch via `HANDLERS` map
  in stdio loop (mirrors `ai_team_repo/__main__.py`).
- Tightened `request_human_review` inputSchema:
  `required: [summary, correlation_id]`,
  `additionalProperties: false`, typed fields
  (`summary` minLength=1 maxLength=2000,
  `target_artifact` maxLength=500).
- 1 schema regression test
  (`tests/unit/test_mcp_ai_team_tasks_main.py`).

Phase 3 — QA prompt:
- `prompts/qa_engineer.md` step 4 inserted between
  "run tests" and "respond with JSON": instructs an
  explicit `request_human_review` call with
  correlation_id copied verbatim from the message
  header.
- Discipline block reinforces "REQUIRED on every QA
  run, passing or failing".

Phase 4 — Integration test:
- `tests/integration/test_mcp_ai_team_tasks_pending_review.py`:
  2 testcontainers-Postgres tests (single row
  end-to-end + two-rows-two-defaults).

Phase 5 — Validation gates (all green):
- ruff check: `All checks passed!` (after adding
  `# noqa: TC002/TC003` for runtime fixture types and
  one long-line docstring wrap).
- ruff format: `146 files already formatted`.
- mypy: `Success: no issues found in 146 source files`
  (after `cast("Table", PendingReview.__table__)`
  for `create_all(tables=...)`).
- bandit: `High: 0` (Low/Medium advisory).
- 400 unit tests pass; 50 integration tests pass.
- `make smoke-llm`: `Overall: PASS`.

Phase 6 — Demo (`scripts/demo_iter_18.sh` + Makefile
alias; cost $3.43 across two runs):
- **Run #1**: PM LLMTimeoutError at 300s (carry-over
  brittleness from pre-iter-18).
- **Run #2**: row `2b260721-c3eb-4144-aee4-7b636980a799`
  written by PM (caveat — see retro Failure 1) at
  `2026-05-20 16:16:35 UTC`; row resolved to
  `approved` via manual `ai-team approve` at
  `16:20:00 UTC` with comment "iter-18 demo manual
  approve — close-the-loop validation".
- Full report:
  `docs/iterations/iter_18_demo_report.md`.

## What went well

- **TDD caught the design issue immediately.** All 12
  new tests went RED → GREEN cleanly. Schema test
  caught my initial `additionalProperties: true` →
  forced the tighten.
- **Mirroring `ai_team_repo/handlers.py` paid off
  enormously.** The Context/HANDLERS/`tools/call`
  dispatch shape was lifted near-verbatim; no
  bikeshedding on structure. Two MCP servers now
  share a structurally identical handler pattern,
  which makes the next one (Bus, when it gets real
  handlers) obvious.
- **sqlite-backed unit tests vs testcontainers
  integration tests** — clean tier. Unit tests run
  in 0.25s (10/10); integration tests boot
  Postgres in ~10s and validate the real path.
  Diff-cover gate easily met (the handler is fully
  exercised by the unit tier alone).
- **Defense-in-depth fallback (`ctx.default_agent`)
  fired correctly in production** during the demo —
  PM didn't pass `agent` in args, handler defaulted
  to `"unknown"` (env unset). Row inserted cleanly
  rather than crashing.
- **No regressions.** 400 unit + 50 integration
  tests stay green. ADR-008 substrate smoke passes.
- **Cost discipline.** $3.43 across two runs (Run #1
  exploration + Run #2 close-the-loop) vs the $5
  ceiling. iter-17 was $6.23 across three runs.
- **First end-to-end formal owner-approval loop
  close.** The `pending_reviews` table + the
  `/api/reviews` endpoint + the `ai-team approve`
  CLI were all built iter-0..2 and have sat idle for
  18 iterations. Now they're live.

## What didn't

- **PM (not QA) wrote the row.** PM's
  `allowed_tools = ()` triggers claude -p's
  permissive default (no `--allowed-tools` flag →
  all tools allowed). PM saw the new MCP tool in
  its tools/list and invoked it during the
  clarification task. **Real surface-area leak**;
  the iter-18 plan's QA-prompt approach would have
  been validated cleanly if QA had completed first.
  Carry-over to iter-19.
- **`requesting_agent='unknown'`.** The LLM didn't
  pass `agent` in args. The plan deliberately
  deferred per-message env injection — empirical
  answer: LLMs DO forget. Carry-over to iter-19:
  set `AI_TEAM_AGENT_ROLE` (and probably
  `AI_TEAM_CORRELATION_ID`) per-invocation in
  `BaseAgent.handle()`.
- **Demo poll-loop too eager.** Exits the moment ANY
  `review_count >= 1`. PM's row triggered the exit
  at ~16 min, killing the still-running
  Architect/Backend/Designer/Frontend/QA via EXIT
  trap. Carry-over to iter-19: poll for a specific
  QA-emitted review (`requesting_agent='qa_engineer'`
  filter).
- **Demo auto-approve bash step crashes** with
  `JSONDecodeError: Expecting value: line 1 column 1`
  — empty curl output in the `$(... || echo '[]')`
  pipeline. The close-the-loop validation worked
  manually via `ai-team approve <id> --comment`
  against a brought-back-up API; the bash bug is
  isolable. Carry-over to iter-19.
- **PM `llm_timeout_s=300` still brittle.** iter-17
  saw PM at 277s (92% cap); iter-18 run #1 hit the
  wall. Carry-over to iter-19: bump to 600 (matches
  Backend/Architect/Designer/Frontend/DevOps).
- **Run #1 burned $1.75 on a known-brittle path.**
  PM timeout retries fired 3× per tenacity config.
  iter-19's PM-timeout bump would have prevented
  this.

## Surprises

- **PM's `allowed_tools = ()` is silently permissive,
  not silently restrictive.** Reading
  `core/llm/claude_code_headless.py:199-200`, when
  `allowed_tools` is empty the `--allowed-tools`
  flag is OMITTED from claude -p invocation, and
  claude -p's default is "all configured MCP tools
  + native tools allowed". Looking at agent
  declarations: PM and Team Lead both have
  `allowed_tools = ()` — meaning TL and PM have been
  wide-open the entire time. Architect, Backend,
  QA, etc all declare explicit non-empty tuples
  and are correctly scoped. **iter-19 may be
  bigger than just PM** — TL's silent open-access
  is a latent finding.
- **iter-18's primary deliverable was validated
  through the WRONG agent.** The intended path was
  QA → `request_human_review` (per the prompt
  update) → row. The actual path was PM →
  `request_human_review` (unprompted) → row. The
  HANDLER behavior is the same in both cases; the
  AGENT IDENTIFICATION is the bug. The plan's
  defense-in-depth (env fallback) caught the worst
  case (`requesting_agent='unknown'` instead of
  crash), but the prompt update is empirically
  untested for QA specifically.
- **Two consecutive demo runs in a row pre-cache
  better than I expected.** Run #2's TL
  decomposition was 49s vs Run #1's 47s — and Run
  #2 had ~80% cache hit on the system prompt across
  sessions. The chain-level caching iter-15
  introduced is paying off.

## Action items for iter-19

1. **(top)** **PM allow-list hardening** — Caveat 1.
   Either set explicit `allowed_tools` on
   `ProductManagerAgent` (whitelist of tools PM
   legitimately needs: Read, Glob,
   `mcp__ai_team_bus__publish_message`,
   `mcp__ai_team_tasks__request_human_review` if
   we DO want PM to flag legitimately ambiguous
   stories) or special-case "() = no tools" in
   `claude_code_headless.py`. Re-audit TL the
   same way.
2. **(top)** **Per-message env injection in
   `BaseAgent.handle()`** — Caveat 2. Set
   `AI_TEAM_AGENT_ROLE`,
   `AI_TEAM_CORRELATION_ID`, and possibly
   `AI_TEAM_TASK_ID` in the env merged into
   `LLMClient.invoke(env=...)`. ai_team_tasks
   handler's `Context.from_env()` fallback already
   reads `AI_TEAM_AGENT_ROLE`; just needs the
   orchestrator to set it.
3. **PM timeout 300 → 600** — Caveat 5. Update
   `agents/product_manager/agent.py:109` and
   `tests/unit/test_agent_timeouts.py:41`. Iter-17
   ran PM at 277s; iter-18 run #1 hit 300s.
4. **Demo poll-loop QA-specific** — Caveat 3.
   `scripts/demo_iter_N.sh` polling should filter
   on `requesting_agent='qa_engineer'`.
5. **Demo auto-approve bash fallback** — Caveat 4.
   `R="${REVIEWS_JSON:-[]}"` belt-and-braces.
6. **TL Backend decomposition** (EIGHT-iteration
   carry-over). Defer until next chain hits a
   600s+ Backend session.
7. **HoldQueue persistence (Postgres-backed)** —
   in-memory still loses on restart.
8. **`pytest-rerunfailures` plugin pin** — CI flake
   carry-over.
9. **Agents'-branch-isolation** — iter-17 retro #7;
   no recurrence in iter-18 (chain didn't reach
   Backend), but still worth investigating.
10. **Carry-overs unchanged**: TL auto-hop
    investigation, TL over-decomposition prompt
    hint, audit_writer Postgres role, hash-chain
    alert, GitHubTargetRepo, transactional TL,
    BaseAgent template refactor.

## Stats

- **Commits on `worktree-iter-18`**: 8 (plan +
  handlers + __main__ wire + QA prompt +
  integration test + lint/typecheck fixes + demo
  script/Makefile + demo report; retro/handoff
  forthcoming).
- **LOC delta**: code +~360 (handlers 145 +
  __main__ 30 net + tests 270 + prompt 18); docs
  +~1700 (plan 1210 + demo report 337 + retro +
  handoff TBD); demo script 306 (clone of iter-17
  with iter-18 narrative). Total: ~2370 LOC
  including docs.
- **Tests**: +12 (9 unit handlers + 1 unit schema +
  2 integration Postgres). 400 unit + 50
  integration tests pass.
- **Real-LLM spend**: $3.43 across two runs
  ($1.75 + $1.68). Under the $5 ceiling; below
  iter-17's $6.23.
- **Diff-cover**: handler module has 100% on the
  hot paths (everything except the
  `# pragma: no cover` stdio loop).
- **Demo wall-clock**: run #1 ~5 min (PM
  timeout-fail-fast), run #2 ~16 min to first row
  + ~4 min for manual close-the-loop = 20 min
  total.
- **`pending_reviews` table state at iter-18 close**:
  1 row total in project history, status
  `approved`, written by PM, resolved by manual
  `ai-team approve`.

## Ready-to-paste prompt for iter-19

Lives in `docs/iterations/iter_19_handoff.md`.
