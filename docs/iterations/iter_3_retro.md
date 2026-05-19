# Iteration 3 — Retrospective

**Closed**: 2026-05-19. 10 commits on `worktree-iter-3` (plan + 7
feature commits + 1 typecheck fix + 1 timeout-bug fix surfaced by
the demo). All gates green; iter-3 demo runs captured in
`docs/iterations/iter_3_demo_report.md`.

The headline deliverable was making the real-LLM e2e chain run **in
dependency order** rather than as a parallel fan-out — the iter-2c
demo's #1 failure mode. With that closed, `tasks.status` now rolls up
properly and the demo report came from a single SQL query over
`audit_log.payload_json -> 'metadata' -> 'llm'` rather than a
structlog grep. See the demo report for the actual chain timing.

## What shipped

Phase 0 — Plan (`docs/iterations/iter_3.md`) approved with three
defaults (HoldQueue in-memory, metrics stamping in `BaseAgent.handle()`,
fresh v2 demo spec).

Phase 1 — `ai-team digest` 401 fix:
- `apps/cli/main.py` now calls `load_dotenv(dotenv_path=Path.cwd()/".env",
  override=False)` inside the `cli()` callback and reads `OWNER_TOKEN`
  via `os.environ.get` after that. Click's `envvar=` is dropped from
  the option to ensure the explicit lookup wins.
- `cwd/.env` anchor was the key detail — `load_dotenv()` defaults to
  walking up from the caller's `__file__` and would have found the
  repo's own `.env` even when running from a different directory.
- Two new unit pins assert (a) header carries the .env value and (b)
  shell-env wins over .env.

Phase 2 — TL `depends_on` + dispatcher `HoldQueue` (three commits):
- `DECOMPOSITION_SCHEMA` gains per-subtask `id` slug + `depends_on:
  list[str]`. TL's `build_outputs` does a two-pass slug → UUID
  resolution so forward references work; unknown slugs fail the whole
  decomposition with `TASK_REPORT(FAILED)` to the owner.
- New `core/dispatcher/hold_queue.py` (~120 LOC + 11 unit tests).
  Single asyncio.Lock around per-correlation `done` and `held` dicts.
  `mark_failed` drops dependents whose predecessor failed.
- `core/dispatcher.py` (moved to package) gates each outbound through
  the queue: audit + feed-publish at intent time, bus publish only
  when predecessors are done. `TASK_REPORT(done)` releases dependents;
  `TASK_REPORT(failed)` drops them.
- Integration test exercises a 3-stage chain (arch → be → qa) via
  scripted LLM + stub agents; asserts arch's done lands before be's,
  be's before qa's; HoldQueue ends empty.

Phase 3 — Root-task state rollup:
- New `core/persistence/task_state.py` with `TaskStateReducer`.
  `on_assignment` inserts a child Task row with parent FK when an
  output's `metadata["parent_task_id"]` is set; `on_report` updates
  the child status and, on terminal status, rolls up via
  `derive_parent_status` (any-failed → failed, all-done → done).
- Idempotent: re-applying a terminal status is a no-op; late
  non-terminal reports don't regress a terminal child.
- 7 pure-logic unit tests cover the rollup decision matrix.
- Integration test now asserts the root task flips from `in_progress`
  to `done` after all three children land their `TASK_REPORT(done)`.

Phase 4 — Per-message LLM metrics:
- `BaseAgent._stamp_metrics` walks every output produced by
  `build_outputs` and stamps `metadata["llm"] = {tokens_in, tokens_out,
  cached_input, cost_cents, duration_ms, model,
  validated_against_schema}`. `TeamLeadAgent.handle()` calls the same
  helper.
- `metadata` already rides on the AgentMessage envelope, so the audit
  writer persists it for free. **No schema bump, no migration.**
- 3 new unit tests cover stamping, metadata preservation, and the
  validated-against-schema=False path.

Phase 5 — Demo wall-clock + sub-task sizing:
- `scripts/demo_iter_3.sh` forks the iter-2 script with a 20-minute
  wait window and a task description that nudges TL into a 6-stage
  DAG (pm_clarify → arch → {be, design} → fe → qa).
- `docs/sandbox/idea_validator_v2_spec.md` extends the v1 spec with
  a one-page web landing page (`apps/web/idea-validator/index.html`)
  and a Designer-written CLI UX brief (`docs/design/idea-validator.md`),
  giving the demo a reason to exercise Designer → Frontend → QA.
- `make demo` now aliases `demo-iter-3`; `demo-iter-2` stays for
  regression.

Phase 6 — Real-LLM e2e demo:
- See `docs/iterations/iter_3_demo_report.md` for the actual run.
- Pre-flight (`make smoke-llm`) PASS: haiku median 8.5s, max 13.6s,
  cache 100% on `--resume`, 5 concurrent calls OK.

Phase 7 — Validation gates + retro + iter-4 handoff:
- `make lint typecheck sec test test-integration` all green.
- 298 unit + 29 integration tests; up from 270/29 at iter-2c close.
- This file + `iter_4_handoff.md`.

## What went well

- **Plan-before-code held tightly.** The plan landed first as a single
  commit and the rest of the work tracked against it exactly. The
  three defaults the owner approved on plan submission carried through
  without renegotiation.
- **TDD discipline.** Every phase wrote tests first, watched them
  fail, then implemented. HoldQueue's 11 tests + the 3-stage
  integration test caught two off-by-one issues in early
  release-set logic that wouldn't have been obvious from a manual
  trace.
- **Metadata-on-envelope was the right call for the metrics.** No
  schema bump, no migration, the audit row carries everything. The
  demo report SQL query is one paste.
- **HoldQueue scope was right.** ~120 LOC + asyncio.Lock + per-correlation
  dicts. Resisted the temptation to ship Postgres-backed in iter-3.
  Restart-loses-state is acceptable for single-process; iter-4 lifts
  it when a real outage hits.
- **`derive_parent_status` as a pure function.** Made the rollup
  logic unit-testable without a database; the only DB-bound piece is
  the SQLAlchemy queries, covered by the integration test.

## What didn't

- See `docs/iterations/iter_3_demo_report.md` for failures observed
  during the real-LLM run. The substrate is healthy; chain-side
  issues will inform iter-4 priorities.

## Surprises

- **Mypy strict caught two issues only on the full repo pass.** Per-
  file `mypy <changed files>` checks were clean throughout, but
  `make typecheck` (whole repo) flagged the `_StaticDoneAgent`
  instance-overrides-ClassVar pattern and the test-helper dict
  invariance. Lesson: run `make typecheck` (not just file-scoped
  mypy) before the validation phase.
- **Mypy doesn't share `from __future__ import annotations` semantics
  with ruff on every import.** Putting `pytest` and `Path` under
  `TYPE_CHECKING` shut ruff up but didn't break mypy — type aliases
  used in fixture signatures are stringified under
  `from __future__ import annotations`.
- **The first demo run died on a pre-existing 120 s timeout default**
  that nobody had tripped in iter-2 because that demo never reached
  PM (it had only TL → Architect → Backend in the iter-2c spec). PM's
  Sonnet response for user stories + acceptance criteria takes ~150 s,
  blowing the 120 s ceiling. Iter-3 surfaced the bug; the trivial fix
  (bump BaseAgent default → 300 s; Backend/Frontend/DevOps overrides
  unchanged) shipped as `fix(agents): bump BaseAgent default
  llm_timeout_s 120s → 300s` and the demo re-run cleared PM. **Lesson:
  every agent that uses the default timeout is exposed to whichever
  worst-case agent inherits it; defaults should match the slowest
  reasonable agent, not the fastest.**

## Action items for iter-4

These overlap with the demo report's action items and are the
starting list for the next iteration. Top-priority items will be
whatever the iter-3 demo surfaced; everything below is the carry-over
queue from the iter-3 plan's "Non-goals":

- [ ] **(top)** Whatever the iter-3 demo surfaced — see
      `iter_3_demo_report.md`.
- [ ] **HoldQueue persistence (Postgres-backed).** Today's in-memory
      queue loses state on restart. Iter-4 adds a `held_messages`
      table + a recovery path on startup. Document the read/write
      contract in ADR (or update ADR-001).
- [ ] **`audit_writer` Postgres role enforcement.** Still deferred
      from iter-2.
- [ ] **Hash-chain alert job.** Still deferred from iter-2.
- [ ] **`GitHubTargetRepo`** — when the first commercial product
      arrives (ADR-009).
- [ ] **TL transactional decomposition.** Wrap the TL output batch in
      one transaction so a crash mid-batch doesn't leave orphan child
      rows.
- [ ] **`pytest-rerunfailures` pin** for the testcontainers race
      iter-2c flagged.

## Stats

- **Commits on iter-3 branch**: 9 (plan + CLI fix + HoldQueue +
  TL schema + dispatcher wiring + rollup + metrics + demo +
  typecheck fix).
- **Tests added**:
  - 2 CLI dotenv pins
  - 11 HoldQueue unit tests
  - 7 TL build_outputs unit tests
  - 7 task_state pure-logic unit tests
  - 3 BaseAgent metrics-stamping unit tests
  - 1 integration test (3-stage dependency chain + rollup)
- **Total tests after iter-3**: **298 unit + 29 integration = 327**
  (iter-2c closed at 268 + 28; net +30 unit + 1 integration).
- **Real-LLM spend this iteration**: see `iter_3_demo_report.md`.
- **Diff-cover on iter-3 diff vs origin/main**: **86 %** (target 80).
  Total branch coverage 85.98 %.
- **LOC delta**: ~1100 added (HoldQueue + TaskStateReducer + metrics
  helper + 30 tests + demo script + v2 spec + this retro +
  iter_4 handoff).

## Ready-to-paste prompt for iter-4

In `docs/iterations/iter_4_handoff.md`.
