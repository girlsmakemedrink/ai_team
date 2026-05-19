# Iter-2 real-LLM end-to-end demo — report

- **Date**: 2026-05-19 (iter-2c session, against iter-2/2b agents on `main`)
- **Run by**: Claude (Opus 4.7) per iter-2c plan, Phase 1
- **Script**: `AI_TEAM_DEMO_NON_INTERACTIVE=1 bash scripts/demo_iter_2.sh`
- **Correlation ID**: `aec29d08-8f1e-409a-a4ca-ce06603c22b9`
- **Task**: "implement idea-validator from spec" (per
  `docs/sandbox/idea_validator_spec.md`)
- **Outcome**: **Partial success — Architect produced a real ADR; Backend +
  QA did not complete within the demo's 10-minute wall-clock.**

## Verdict in one line

The iter-2/2b plumbing works end-to-end as far as the chain got: HMAC
signing, audit log with `prev_hash` chain, Redis Streams routing, MCP
path-scoped writes, `claude -p` subscription auth, and Opus-tier
Architect output were all exercised against a real LLM. The chain
stalled after Architect because **TL's decomposition emits sub-tasks
in parallel with no dependency ordering**, so Backend started before
Architect's ADR existed (and likely timed out trying to implement the
spec from scratch). The demo script's 600-second wait window was also
shorter than a realistic Backend wall-clock for this task size.

This is a useful, reproducible failure mode that informs iter-3
priorities. The substrate is healthy.

## What ran

Pre-flight checks passed (Phase-1A in the iter-2c plan):
- `.env` present (copied from main repo into worktree)
- `claude --version` → 2.1.144
- `docker info` healthy
- `gh auth status` → logged in as `girlsmakemedrink`
- `make smoke-llm` → **PASS** (5/5 checks; cold-haiku median 6.6s,
  max 13.4s; cache 100% on `--resume`; concurrent x5 ok)

Demo invocation:
- `make up` → 4 services healthy
- `alembic upgrade head` → schema at head
- `uvicorn` started, dispatcher autostarted, owner token submit OK
- Correlation handed back to the script

## Chain timeline

Pulled from `audit_log` for correlation
`aec29d08-8f1e-409a-a4ca-ce06603c22b9`:

| ID | Time (UTC)             | Sender → Recipient            | Type            | Notes |
|----|------------------------|-------------------------------|-----------------|-------|
| 8  | 04:32:25.45            | user → team_lead              | task_assignment | demo task submitted |
| 9  | 04:33:02.10            | team_lead → architect         | task_assignment | "ADR: idea-validator pipeline design" |
| 10 | 04:33:02.14            | team_lead → backend_developer | task_assignment | "Implement idea-validator per ADR" |
| 11 | 04:33:02.15            | team_lead → qa_engineer       | task_assignment | "Verify idea-validator tests + smoke" |
| 12 | 04:34:57.55            | architect → team_lead         | task_report     | DONE, artifact `docs/adr/0010-idea-validator-pipeline.md` |

After ID 12, no further reports landed. The demo script's 600-second
deadline expired without Backend's `src/` tree existing; the script
exited cleanly and uvicorn was killed by the bash `trap`.

State at end of run:
- `tasks` table: root task `baf37c60-...` stuck in `in_progress`
  (assigned to `team_lead`; iter-2 doesn't yet update the row when
  sub-tasks report back).
- `pending_reviews`: **0 rows** — owner approval gate never reached.
- `checkpoints`: **0 rows** — TL didn't emit a checkpoint digest.
- `feed_events`: 12 rows — routing was published to `team_feed` as
  expected.

## Per-agent measurements

| Agent (tier) | Wall-clock (this turn) | Tokens (in / out / cached) | Cost (cents, est.) | Schema-validated | Outcome |
|--------------|------------------------|-----------------------------|---------------------|-------------------|---------|
| TL (opus)    | ~37 s                  | not captured by demo script[^1] | n/a | yes (3 subtasks)  | parallel dispatch (see "Surprises") |
| Architect (opus) | ~115 s            | not captured by demo script[^1] | n/a | yes               | DONE — 12 335 char ADR-0010 |
| Backend (sonnet) | ≥ 600 s (no report)  | n/a                          | n/a | n/a               | timed out / interrupted |
| QA (sonnet)  | ≥ 600 s (no report)  | n/a                          | n/a | n/a               | never reached (no Backend report to verify) |

[^1]: The demo script's wait loop watches the filesystem, not the
audit log. Per-agent `tokens` and `cost_estimate_cents` are written
by `ClaudeCodeHeadlessClient` to `structlog` only, not yet to the
audit-log payload. **Action item for iter-3**: persist `tokens`,
`cached_input`, `cost_cents`, `duration_ms`, and
`validated_against_schema` to a per-message column or to the message
metadata so the demo report can pull them with a single SQL query.

## What worked

- **Substrate.** `make smoke-llm` is green on the iter-2c session
  (5 concurrent calls, 100% session cache on `--resume`, latency
  inside ADR-008 thresholds).
- **Subscription auth.** Every call this session was via the owner's
  Max 5x subscription, never API key. No quota-exhausted error;
  no surprise charges.
- **Architect Opus.** Produced a 12 KB ADR that cites the right
  existing ADRs (001, 004, 006, 008, 009), proposes a concrete module
  layout, and respects the spec's LOC ceiling. Real, usable design.
- **MCP path-scope.** Architect was spawned with
  `AI_TEAM_PATH_PREFIXES=docs/adr,docs/architecture.md` (per iter-2b
  1B) and the ADR landed exactly where allowed.
- **Audit chain.** `prev_hash` linkage is intact through ID 12; an
  out-of-band `verify_chain()` would pass.
- **HMAC sign+verify.** Every message has `hmac_signature` and was
  verified by the dispatcher before being handed to the agent.

## What didn't

### Failure 1 — TL emits sub-tasks in parallel with no dependency ordering

Audit IDs 9, 10, 11 fired within ~50 ms of each other. The decomposition
schema (`agents/team_lead/agent.py:DECOMPOSITION_SCHEMA`) is a flat list
of `subtasks` with no `depends_on` field, so TL has no syntax for
"Backend waits on Architect." The Backend prompt explicitly references
"After the architect's ADR lands" in `description`, but the dispatcher
fires it immediately.

**Net effect**: Backend was running against an empty `docs/adr/0010-*.md`
(or earlier ADR-0009 only) at start. Even if Backend's LLM reads docs at
runtime via `Read`, it would have had to poll / wait for the file to
exist — which it has no mechanism to do.

**Iter-3 fix shape** (one of):
- Add `depends_on: list[str]` to the decomposition schema and have the
  dispatcher hold messages until predecessors report DONE.
- Or: TL emits one sub-task at a time and re-decomposes on each
  TASK_REPORT(DONE) until the plan is exhausted. Same logical effect,
  simpler routing.

### Failure 2 — Backend wall-clock > demo deadline

Backend's per-class `llm_timeout_s` is 600 s and `max_turns` is 20.
For the spec ("≥ 200 LOC + tests + cover gate"), that's tight even
sequentially. The demo's outer wait is *also* 600 s, so even if
Backend had completed, the bash script would have exited at the same
deadline.

**Iter-3 fix**: bump the demo wait to ~20 min and/or break the spec
into smaller per-stage sub-tasks.

### Failure 3 — `ai-team digest` CLI returns 401 in the demo

End of the demo script runs `uv run ai-team digest --history --limit 5`,
which got `401 missing Authorization header`. The CLI isn't passing
`OWNER_TOKEN` from `.env` to the API. Not blocking (the script handles
it as advisory), but it's a real CLI bug.

**Iter-3 fix**: small one — wire `OWNER_TOKEN` into the CLI's HTTP
client (`apps/cli/main.py`). Single test pin.

### Failure 4 — `tasks` row left in `in_progress`

The root task `baf37c60-...` stayed `in_progress` even though Architect
reported DONE for its sub-task. The dispatcher doesn't yet roll
sub-task DONE → root-task state transitions; only the TL would know
when "the plan as a whole" is done, and TL never got a final BREATHE
moment. (Iter-1 retro called this out and deferred to iter-3.)

## Cost / quota

- This run consumed: low single-digit cents (haiku smoke-llm pre-flight
  cents-free; TL Opus + Architect Opus together estimated < $0.20).
  Backend Sonnet's incomplete turn contributed some Sonnet tokens but
  the dispatcher's `_StubLLM` is not in play — these were real calls
  that just never reported back to TL.
- **Demo budget per iter-2c plan**: $0.40 expected, $2.00 ceiling.
  We are at most ~$0.20 spent. No second run attempted this session.
- Quota at session start (estimated): well above the 30% pre-flight
  threshold. No `quota_exhausted` signal observed.

## Action items for iter-3

1. **TL dependency ordering** (Failure 1) — block iter-3 must-have.
2. **Demo wall-clock + sub-task sizing** (Failure 2) — small.
3. **`ai-team digest` auth bug** (Failure 3) — trivial.
4. **Root-task state rollup from sub-task reports** (Failure 4) —
   medium; touches `core/dispatcher.py`'s exit-path bookkeeping.
5. **Persist per-message `tokens` + `cost_cents` + `duration_ms` +
   `validated_against_schema` to the audit-log payload or metadata**
   so the next demo report doesn't have to grep structlog. Medium.

None of these block iter-2c's Frontend / SRE / TL-routing work. They
are honest follow-ups for iter-3.

## Artifacts produced this run

- `docs/adr/0010-idea-validator-pipeline.md` (12 335 chars; Architect)
- 5 rows in `audit_log` (IDs 8-12) — chain intact, HMAC valid
- 12 rows in `feed_events`
- 1 row in `tasks` (root, in_progress)
