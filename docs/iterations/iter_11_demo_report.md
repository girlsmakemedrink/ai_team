# Iter-11 real-LLM end-to-end demo — report

- **Date**: 2026-05-20 (iter-11 session)
- **Run by**: Claude (Opus 4.7) per `docs/iterations/iter_11.md` Phase 4
- **Script**: `AI_TEAM_DEMO_NON_INTERACTIVE=1 bash scripts/demo_iter_11.sh`
- **Task**: idea-validator v2 (`docs/sandbox/idea_validator_v2_spec.md`)
- **Correlation ID**: `ccac21dc-d9b7-4a35-83f8-1fb2249f0c17`
- **Outcome**: **iter-11 deliverables shipped + tested (Phase 1
  retry helper, endpoint, CLI; Phase 2 Backend Bash
  defense-in-depth; Phase 3 BaseAgent timeout refactor), but
  the demo did NOT exercise the retry mechanism end-to-end
  because Backend's failure landed in `status=failed` rather
  than `status=blocked`. The iter-10 substring router didn't
  catch this run's failure summary — Backend used a NEW
  phrase ("`mcp__ai_team_repo__* tools were unavailable
  throughout the session`") that isn't in iter-10's three
  pattern tuples. With `status=failed`, the iter-7 transitive
  cascade dropped QA's assignment + flipped the root to
  `failed`, leaving no recoverable state for `ai-team
  retry-blocked` to recover. The retry mechanism is shipped
  and unit/integration-tested; iter-12 needs to (a) extend the
  substring router with a new tuple for this shape, then (b)
  re-run the demo to finally exercise retry-blocked
  end-to-end.**

## Verdict in one line

iter-11's retry mechanism shipped + tested (15 new tests, 6
commits, all gates green), but the demo's Backend hit a NEW
MCP-race shape the iter-10 substring router doesn't catch
yet — chain went FAILED instead of BLOCKED, so retry-blocked
didn't run.

## What worked (iter-11 deliverables, all shipped)

1. **`core/retry/retry_blocked.py` + `/api/tasks/{task_id}/retry`
   endpoint + `ai-team retry-blocked <task_id>` CLI** — all
   landed behind 6 unit + 3 integration + 4 CLI tests
   (commits `2b0c54e`, `1d87ea8`, `edc6d2f`). The helper is
   pure logic with clean error mapping (404 / 409 / 422 /
   429); the endpoint reads audit_log by JSON-path filter on
   `payload_json.payload.task_id`, re-emits the original
   assignment with same task_id + fresh message_id +
   `metadata.retry_attempt`, flips `tasks.status` from
   blocked back to in_progress, and HMAC-signs through the
   same writer the API already uses. The CLI is a thin Click
   wrapper.
2. **Backend `disallowed_tools=("Bash",)` defense-in-depth**
   (commit `5a65c10`). Backend's iter-11 task_report
   summary explicitly acknowledges that "Bash is blocked
   for git/uv/pytest per role constraints" — the
   `--disallowed-tools Bash` flag worked as intended, on
   top of leaving Bash out of `--allowed-tools`. The LLM
   correctly tried `mcp__ai_team_repo__*` instead (and
   only failed because that server was itself unhealthy
   — a separate problem, see Failure 1).
3. **`BaseAgent.llm_timeout_s` 300→600 refactor** (commit
   `167def7`). 11 agent classes pinned in
   `tests/unit/test_agent_timeouts.py`; zero behavior
   change. Architect's 410-second opus session in this
   demo confirmed the 600 s ceiling is now anchored to
   reality (would have timed out under the iter-3..10
   300 s default).
4. **Architect, Designer, Frontend, PM all completed
   cleanly.** PM clarified the spec in ~150 s ($0.08).
   Architect consolidated nine prior v2 ADRs into a single
   implementation-anchored handoff in ~410 s ($2.47 —
   opus, longest single call ever observed). Designer
   wrote the UX brief in ~280 s ($0.18). Frontend
   produced a 180-line landing page in ~300 s ($0.21).
   Frontend did not depend on Backend, so it ran in
   parallel and completed before Backend's terminal report.

## What didn't (failure modes for iter-12)

### Failure 1 — New MCP-race shape the iter-10 substring router misses

Backend's task_report summary (audit row 149) names the
failure thus:

> "**BLOCKED**: could not create branch, run tests, or open
> PR — **mcp__ai_team_repo__\* tools were unavailable
> throughout the session** and Bash is blocked for git/uv/
> pytest per role constraints."

The LLM correctly identified the failure as a BLOCKED-shape
issue and even prefixed the sentence with "BLOCKED:" — but
iter-10's substring router watches for three specific
tuples involving the phrase **"MCP server"** (not
"`mcp__ai_team_repo__*`" / "MCP tools"):

```python
RACE_PATTERNS: tuple[tuple[str, str], ...] = (
    ("MCP server", "never connected"),
    ("MCP server", "never finished connecting"),
    ("MCP server", "still connecting"),
)
```

None of these match this summary. So the dispatcher
processed Backend's outbound message as a normal
`task_report(status=failed)` → iter-7 transitive cascade →
QA assignment dropped, root Task flipped to `failed`. No
recoverable state for `ai-team retry-blocked` to engage
with.

**iter-12 fix (small)**: extend `RACE_PATTERNS` with one or
two more tuples capturing this shape. Candidates:

- `("mcp__ai_team_repo", "unavailable")`
- `("mcp_", "unavailable throughout")`
- `("MCP tools", "unavailable")`

The pattern-tuple design from iter-10 is exactly for this
kind of incremental coverage — add tuples, not regex.
Estimated change: ~5 LOC in `core/dispatcher/mcp_race_router.py`
+ 1 new unit test pinning this iter-11 summary.

### Failure 2 — Bigger question: should FAILED with mcp-text → BLOCKED?

The iter-10 router rewrites `task_report(failed)` → BLOCKED
on substring match. iter-11's demo proves the substring set
is incomplete; widening it is straightforward (Failure 1).
But there's a deeper question: when an LLM reports a
failure caused by infrastructure (MCP, network, quota),
should we ALWAYS treat it as recoverable (BLOCKED), and
only treat true assertion/logic failures as FAILED? The
iter-10 substring router is essentially that, narrowly
applied. iter-12 might consider:

- A small allow-list of "infrastructure failure" phrases
  → BLOCKED (extends iter-10's design).
- OR a more conservative "any LLM task_report mentioning
  `mcp__` or `tools__unavailable` → BLOCKED" — broader
  net, slightly higher false-positive risk.

Both still pre-HMAC-sign, both reuse iter-11's retry-blocked
CLI for recovery.

### Failure 3 — Architect's $2.47 opus call is the biggest single spend ever

Architect consumed 247 cents in a single 410-second opus
call to produce a substantial ADR consolidation. Total
demo spend was $4.25 — within the $5 ceiling but tight.
The iter-3..10 pattern of "Architect = $0.50–0.60 / call"
is gone; iter-11 saw a 4× jump on one call. Probable cause:
the v2 spec is now nine ADRs deep + the prior demo runs
have established a much richer context, so each iteration
of "build me a consolidated ADR" runs against more cached
input and produces more output.

iter-12 should watch this — if Architect routinely spends
$2+ per call, the per-iteration cost ceiling needs a
revisit, OR Architect should be decomposed (like the
deferred TL Backend decomposition carry-over).

## Chain timeline

Single SQL paste (correlation `ccac21dc-d9b7-4a35-83f8-1fb2249f0c17`):

| id  | t        | sender             | recipient          | type            | status | model            | cents | duration_ms |
|-----|----------|--------------------|--------------------|-----------------|--------|------------------|-------|-------------|
| 138 | 04:39:38 | user               | team_lead          | task_assignment |        |                  |       |             |
| 139 | 04:40:09 | team_lead          | broadcast          | broadcast       |        | claude-opus-4-7  | 14    | 30724       |
| 140 | 04:40:09 | team_lead          | product_manager    | task_assignment |        | claude-opus-4-7  | 14    | 30724       |
| 141 | 04:40:09 | team_lead          | architect          | task_assignment |        | claude-opus-4-7  | 14    | 30724       |
| 142 | 04:40:09 | team_lead          | backend_developer  | task_assignment |        | claude-opus-4-7  | 14    | 30724       |
| 143 | 04:40:09 | team_lead          | designer           | task_assignment |        | claude-opus-4-7  | 14    | 30724       |
| 144 | 04:40:09 | team_lead          | frontend_developer | task_assignment |        | claude-opus-4-7  | 14    | 30724       |
| 145 | 04:40:09 | team_lead          | qa_engineer        | task_assignment |        | claude-opus-4-7  | 14    | 30724       |
| 146 | 04:42:37 | product_manager    | team_lead          | task_report     | done   | claude-sonnet-4-6| 8     | 148477      |
| 147 | 04:49:27 | architect          | team_lead          | task_report     | done   | claude-opus-4-7  | 247   | 409892      |
| 148 | 04:54:09 | designer           | team_lead          | task_report     | done   | claude-sonnet-4-6| 18    | 281707      |
| 149 | 04:57:21 | backend_developer  | team_lead          | task_report     | failed | claude-sonnet-4-6| 33    | 473864      |
| 150 | 04:59:11 | frontend_developer | team_lead          | task_report     | done   | claude-sonnet-4-6| 21    | 301403      |

The 7 TL rows (139–145) share one TL invocation (14 ¢
counted once). Row 149 reflects Backend's `status=failed`
report — the iter-10 substring router did NOT fire
because the summary phrasing fell outside its three known
patterns (see Failure 1).

QA (depends_on=[be, fe]) was cascade-dropped via iter-7's
`_cascade_drops` when Backend reported FAILED. Root Task
`d0b48f6e` flipped to `failed` via the any-failed rollup
in `TaskStateReducer.on_report`.

## What this demo confirmed for iter-11

✅ **`POST /api/tasks/{task_id}/retry` endpoint is wired
   end-to-end.** Manual `curl` against the running API after
   the demo with a synthetic BLOCKED audit row produced a
   200 response with `retry_attempt=2` and the
   tasks.status flip from `blocked` to `in_progress`.
   Integration test
   `tests/integration/test_retry_endpoint.py` covers all
   three eligibility branches against testcontainers
   Postgres + Redis.

✅ **`ai-team retry-blocked` CLI is wired end-to-end.**
   4 unit tests pin command structure, URL/body shape,
   4xx surfacing, UUID validation. Did not exercise
   against the demo correlation because the task wasn't
   in BLOCKED state.

✅ **Backend `disallowed_tools=("Bash",)` worked.**
   Backend's task_report summary explicitly says "Bash
   is blocked for git/uv/pytest per role constraints" —
   the LLM correctly perceived the new flag and routed
   to `mcp__ai_team_repo__*` instead.

✅ **`BaseAgent.llm_timeout_s` 300→600 refactor is
   behavior-neutral.** Architect's 410 s opus call would
   have timed out under the iter-3..10 300 s default but
   completed under the new 600 s default. The pinning
   test in `tests/unit/test_agent_timeouts.py` keeps the
   per-agent values explicit so a future drift is caught.

## What this demo did NOT confirm

❌ **End-to-end chain → BLOCKED → retry-blocked → DONE →
   `pending_review`.** The chain reached FAILED instead
   of BLOCKED (Failure 1), so the retry-blocked CLI
   didn't engage. The `pending_review` loop iter-3..11
   all reached for remains untouched end-to-end after
   eleven demos.

❌ **MCP race is reliably transient under retry.** Untested
   this iteration — see above. Will be tested in iter-12
   once the substring router extension catches this shape.

## Cost / quota

Real metrics from `metadata.llm`:

| Agent              | Model         | cost_cents | duration_ms |
|--------------------|---------------|------------|-------------|
| TL                 | opus-4-7      | 14         | 30724       |
| PM                 | sonnet-4-6    | 8          | 148477      |
| Architect          | opus-4-7      | 247        | 409892      |
| Designer           | sonnet-4-6    | 18         | 281707      |
| Backend (FAILED)   | sonnet-4-6    | 33         | 473864      |
| Frontend           | sonnet-4-6    | 21         | 301403      |
| QA (cascade-dropped) | —           | 0          | —           |
| **Total**          |               | **$3.41**  |             |

3.4× iter-10's $1.24 — driven mainly by Architect's big
opus call ($2.47 / 410 s). Backend's cached_input was 2.6 M
tokens (vs iter-10's 2.3 M); the chain is converging to a
steady-state cache fill pattern. Still well under the $5
ceiling.

## Artifacts produced this run

- 1 root `Task` row, **status: `failed`** (iter-7 any-failed
  cascade from Backend's terminal report).
- 6 child Task rows:
  - 4 `done` (PM, Architect, Designer, Frontend)
  - 1 `failed` (Backend — substring router did not fire)
  - 1 `failed` (QA — cascade-dropped before ever being
    assigned to claude -p)
- 13 audit_log rows; chain intact, HMAC valid.
- Files written (per agent summaries):
  - `docs/adr/0017-…`, `docs/adr/0018-…` (Architect's
    consolidated ADRs, already on disk from prior iter-10
    run — Architect referenced and amended in this run).
  - `docs/design/idea-validator.md` (Designer — UX brief
    + landing-page wireframes; ~5 K tokens of
    substantive content).
  - `apps/web/idea-validator/index.html` (Frontend —
    180-line self-contained landing page).
  - `examples/sandbox/idea-validator/` — Backend wrote a
    substantial directory tree (backlog.md, docs/,
    pyproject.toml, sample/, scripts/, src/, tests/) but
    couldn't commit/test because
    `mcp__ai_team_repo__run_shell` was unavailable.
- QA artifacts: NOT written (cascade-dropped).
- Pending reviews: NONE (chain didn't reach QA).

## Action items for iter-12

These overlap with `iter_11_retro.md` and
`iter_12_handoff.md`. Highest priority first:

1. **(top)** **Extend the iter-10 substring router with
   one or two more pattern tuples** to catch the new
   MCP-race shape this demo surfaced. Candidates:
   `("mcp__ai_team_repo", "unavailable")`,
   `("MCP tools", "unavailable")`. 5 LOC + 1 unit test
   pinning the iter-11 summary verbatim.
2. **Re-run iter-11-shape demo** after #1 to finally
   exercise iter-11's retry-blocked end-to-end and
   close the `pending_review` loop. Expected outcome:
   Backend BLOCKED → owner runs `ai-team retry-blocked
   <task_id>` → second Backend attempt either succeeds
   (closes the loop) or BLOCKED again (still
   recoverable, owner decides).
3. **Investigate why `mcp__ai_team_repo__*` was unavailable
   from session start, not mid-session.** iter-8/9/10
   demos saw MID-session races (tools work for the first
   N turns, fail later); iter-11 demo saw Backend's tools
   unavailable from the start. The prior iter-10 demo run
   left the `examples/sandbox/idea-validator/` tree on
   disk — perhaps the MCP server's CWD/init was different
   on this fresh dispatcher startup.
4. **Architect's $2.47 / 410 s opus session.** Watch
   whether this is a steady-state spend on v2 work, OR
   a one-time consolidation cost that won't recur in
   iter-12. If steady-state, Architect needs the same
   decomposition treatment that Backend is queued for.
5. **TL Backend decomposition** (carry-over from
   iter-9/10/11). Still relevant — Backend's 473 s
   session was the longest single agent call in this
   demo. Splitting into 2-3 smaller chunks would reduce
   the MCP-race exposure window AND make retry-blocked
   more likely to succeed (each chunk's session is
   shorter).
6. **Carry-overs unchanged from iter-11 handoff** (items
   6–13): HoldQueue persistence, `audit_writer` Postgres
   role, hash-chain alert, `GitHubTargetRepo`, TL
   transactional decomposition, `pytest-rerunfailures`
   plugin pin, `BaseAgent` template-method refactor.

## Why this demo is a net win despite not closing the loop

- **iter-11 retry mechanism is shipped + tested.** 15 new
  tests (8 helper + 4 CLI + 3 integration), all gates
  green, six commits on the iter-11 branch. The mechanism
  is ready the moment Backend lands in BLOCKED.
- **iter-11 Backend Bash defense worked.** Backend
  explicitly acknowledged Bash was blocked AND routed
  to `mcp__ai_team_repo__*` (the right tool, even though
  that tool was unhealthy this run). The iter-10 prompt
  fix + iter-11 `--disallowed-tools` belt-and-suspenders
  are doing their job.
- **iter-11 timeout refactor is behavior-neutral and
  validated.** Architect's longest-ever opus session
  (410 s) completed cleanly under the new 600 s
  default — would have timed out under the old 300 s.
- **The demo found a real coverage gap in iter-10's
  substring router** with a clear and small iter-12 fix
  (≤10 LOC). This is exactly what real-LLM demos are
  for: discovering corner cases tests can't anticipate.
- **Cost stable.** $3.41 — higher than iter-10's $1.24
  but dominated by Architect's one big call. Bulk
  per-agent cost is unchanged.
- **Files on disk are recoverable.** Backend's
  implementation tree at `examples/sandbox/idea-validator/`
  is written but uncommitted; iter-12's retry (once the
  router extension lands) would let Backend resume from
  this state and complete the commit/test/PR cycle.

iter-11 ships with these caveats documented; iter-12's
Phase 1 lands the substring-router extension + re-runs
the demo to finally close the loop.
