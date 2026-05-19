# Iteration 2c — Retrospective

**Closed**: 2026-05-19. 7 commits on `worktree-iter-2c` (plan + 6
phase commits). 268/268 unit tests green, 28/28 integration tests
green, ruff / mypy / format clean, bandit-high clean, diff-cover 92 %,
`make smoke-llm` green.

The headline deliverable — the real-LLM end-to-end demo — was finally
**run for real** rather than wired-and-deferred. The result was a
useful, structured partial-success: Architect produced a real 12 KB
ADR; Backend + QA did not complete inside the demo wall-clock for
diagnosable reasons. Full write-up in `iter_2_demo_report.md`.

## What shipped

Phase 1 — Real-LLM e2e demo (carry-over from iter-2 + iter-2b):
- **1A** pre-flight checks: `.env` copied into worktree, `claude --version`
  ok, `docker info` ok, `gh auth status` ok, `make smoke-llm` PASS
  (cold-haiku median 6.6 s, max 13.4 s, cache 100 % on `--resume`).
- **1B** `AI_TEAM_DEMO_NON_INTERACTIVE=1 bash scripts/demo_iter_2.sh`
  executed against the worktree's `main`-state code. Chain ran:
  user → TL Opus → Architect/Backend/QA in parallel → Architect DONE
  (ADR-0010, 12 335 chars) → Backend + QA did not report inside 600 s.
- **1C** `docs/iterations/iter_2_demo_report.md` captures the timeline,
  per-agent measurements, three concrete failures, and five action
  items for iter-3.

Phase 2 — Frontend Developer agent:
- Sonnet, path scope `apps/web,apps/cli` (target repos override
  per-task via `AI_TEAM_PATH_PREFIXES`).
- DevOps-shaped output schema (target_files, changes, rationale,
  validation_step, pr_url, branch). Branch pattern
  `agent/frontend/<slug>` enforced by JSON schema.
- 8 unit tests. Registered in dispatcher.

Phase 3 — SRE/Support agent:
- Sonnet, path scope `docs/runbooks,infra/monitoring`. No shell
  allowlist this iteration (deferred to iter-5).
- Designer-shaped schema (title, slug, kind, summary, steps, metrics,
  severity). Routes `kind in {alert,dashboard}` to `infra/monitoring/`,
  everything else to `docs/runbooks/`.
- 8 unit tests. Registered in dispatcher.

Phase 4 — TL BLOCKED routing:
- `TeamLeadAgent.handle()` now accepts `task_report` messages when
  `status == BLOCKED` and emits one follow-up `task_assignment` to
  the role indicated by `TaskReportPayload.blocked_on` (or, fallback,
  a `blocked: requires <role>` prefix in the summary).
- **Anti-loop**: if the BLOCKED report's summary already contains
  `auto-routed`, TL refuses to re-route a second time. Worst case
  the chain stops and the owner sees it in the digest.
- Pure dispatch — no LLM call on the routing hop.
- DevOps and Frontend agents populate
  `TaskReportPayload.blocked_on` when `validation_step` is
  `blocked: requires <role>`. Both `_parse_blocked_role` helpers
  resolve only to known `AgentId` enum values.
- 7 new TL unit tests; assertions added to DevOps + Frontend tests.

Phase 5 — Validation gates + retro + iter-3 handoff (this iteration's
closure). All gates green; this file + handoff.

## What went well

- **Plan-before-code held tightly.** The plan landed first as a single
  commit and the rest of the work tracked against it exactly. The
  three defaults the owner approved on plan submission carried through
  without renegotiation.
- **Demo gave real signal.** Running it produced more useful failure
  information than another round of mocked wiring would have. The
  three failures (parallel TL decomposition, demo wall-clock too
  short, CLI auth bug) are all small + fixable in iter-3 and were
  invisible from the unit tests.
- **Agent pattern keeps scaling.** Two more agents (Frontend, SRE)
  each landed in ~250 LOC + 8 tests, dropped into the dispatcher with
  one import line. Architect's TDD shape from iter-2 is now five
  iterations old and still fits.
- **TL BLOCKED routing is small and pure.** ~60 LOC + 7 unit tests,
  no LLM call on the hop, no `AgentMessage` schema bump. The
  summary-string anti-loop guard (default #3 from plan approval) is
  ugly but simple — pin a metadata counter only if it bites.
- **Diff-cover 92 %.** Solidly above the 80 % gate. None of the
  uncovered lines are load-bearing (defensive `_fail_report` branches
  + the `_parse_blocked_role` ValueError fallback).

## What didn't

- **The demo didn't fully close the PM → … → QA → owner-approval loop
  this session.** Architect produced. Backend + QA timed out / ran
  past the demo's 600 s wait. This is iter-3 work, not an iter-2c
  regression — but the headline of "iter-2c finally runs the demo
  end-to-end" should be read as "iter-2c finally exercises the real
  substrate; the chain stalls at a previously-unknown bottleneck."
- **TL's decomposition schema has no `depends_on` field.** Spotted
  via the demo run — Backend and QA were dispatched in parallel with
  Architect. The plan's non-goal list correctly excluded this, but
  it's now the single biggest blocker for "real" e2e flows.
- **`ai-team digest` CLI returns 401 in the demo.** Trivial fix
  (wire `OWNER_TOKEN` from `.env` into the CLI's HTTP client) but
  needs an iter-3 commit.

## Surprises

- **Architect produced strong output on the first real-LLM run.**
  ADR-0010 cites the right existing ADRs, proposes a concrete module
  layout that respects the spec's LOC ceiling, and reads like an
  intentional design rather than an LLM template. This is a
  reassuring signal that the prompt + JSON-schema shape work for
  real tasks.
- **The integration test suite occasionally races on testcontainers.**
  First full-suite run gave 28 errors with `Port mapping for
  container ...`; re-running them gave 28/28 passes. Not a regression,
  just docker startup jitter. Worth a `pytest-rerunfailures` plugin
  pin in iter-3 if it recurs.
- **`uv` didn't auto-install dev extras.** `uv sync` in the worktree
  installed runtime deps only; `uv sync --extra dev` was needed
  before `pytest` ran. Possibly a worktree-isolation thing; the main
  repo's `.venv` had dev deps from a prior `make dev`. Worth pinning
  in `make dev` or the project README so the next reader doesn't trip.

## Action items for iter-3

These overlap with the demo report's action items and are the
concrete iter-3 starting list:

- [ ] **TL dependency ordering** — add `depends_on` to
      `DECOMPOSITION_SCHEMA` and have the dispatcher hold sub-tasks
      until predecessors report DONE. (Failure 1 of the demo report;
      the biggest blocker.)
- [ ] **Demo wall-clock + sub-task sizing** — bump the demo wait to
      ~20 min and/or break the spec into smaller per-stage sub-tasks
      so a realistic Backend turn fits inside. (Failure 2.)
- [ ] **`ai-team digest` auth bug** — wire `OWNER_TOKEN` from `.env`
      into the CLI HTTP client. (Failure 3, trivial.)
- [ ] **Root-task state rollup** — `tasks.status` should transition
      pending → in_progress → done when sub-tasks' chain completes.
      (Failure 4, medium.)
- [ ] **Per-message `tokens` + `cost_cents` + `duration_ms` +
      `validated_against_schema` in audit-log payload or metadata**
      — so the next demo report doesn't have to grep structlog. Drop
      the column or extend the JSON; either works. (Failure 5,
      medium.)
- [ ] **Run the demo again** after the above land, against the full
      8-agent dispatcher (now 9 with SRE / Frontend) — exercise the
      Designer → Frontend → QA path for the first time.
- [ ] **`audit_writer` Postgres role enforcement** — still iter-3
      from the iter-2 retro action list. Untouched.
- [ ] **Hash-chain alert job** — still iter-3 from iter-2 retro.
- [ ] **`GitHubTargetRepo`** — when the first commercial product
      arrives. ADR-009's deferred decision.

## Stats

- **Commits on iter-2c branch**: 7 (plan + Frontend agent + Frontend
  registration + SRE agent + SRE registration + Phase-4 TL routing +
  demo report).
- **Tests added**: 23 unit (8 Frontend + 8 SRE + 7 TL BLOCKED-routing).
- **Total tests after iter-2c**: 268 unit + 28 integration
  (iter-2b left 244 unit + 10 integration — note the +18 integration
  is a count correction; iter-2b reported "10 new" but the suite total
  was actually 28).
- **Real-LLM spend this iteration**: ~$0.20 estimated (TL Opus
  decomposition + Architect Opus turn that completed; Backend Sonnet
  turn that didn't report back — partial cost). Well under the $2
  ceiling.
- **Diff-cover on iter-2c diff**: **92 %**.
- **LOC delta**: ~1 200 added (Frontend agent + SRE agent + TL
  routing changes + 23 tests + iter_2c plan + iter_2_demo_report +
  this retro).

## Ready-to-paste prompt for iter-3

In `docs/iterations/iter_3_handoff.md`.
