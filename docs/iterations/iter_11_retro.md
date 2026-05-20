# Iteration 11 — Retrospective

**Closed**: 2026-05-20. 9 commits on `worktree-iter-11`
(plan + retry helper + endpoint + CLI + Backend Bash defense
+ timeout refactor + demo script + demo report + type cleanup
+ retro + handoff). All gates green; real-LLM demo run
captured in `docs/iterations/iter_11_demo_report.md`.

**Three headline deliverables landed**: `ai-team retry-blocked
<task_id>` CLI + `POST /api/tasks/{task_id}/retry` endpoint
backed by a pure-function helper, `BackendDeveloperAgent`
`disallowed_tools=("Bash",)` defense-in-depth, and the
overdue `BaseAgent.llm_timeout_s` 300→600 refactor. **Demo
caveat**: the retry mechanism did NOT exercise end-to-end
because Backend's failure summary used a NEW phrase
("`mcp__ai_team_repo__* tools were unavailable throughout
the session`") that iter-10's substring router doesn't
catch yet — chain went FAILED instead of BLOCKED. iter-12's
top priority is one or two new pattern tuples in
`core/dispatcher/mcp_race_router.py` (≤10 LOC + 1 test) +
a re-run.

## What shipped

Phase 0 — Plan (`docs/iterations/iter_11.md`, 770 lines)
committed on `worktree-iter-11` cut from `origin/main` at
`9d02160`. Plan was approved inline.

Phase 1 — `core/retry/retry_blocked.py` + endpoint + CLI:

- New module `core/retry/retry_blocked.py` (~100 LOC):
  pure-function `check_retry_eligibility(task_id, rows)`
  inspects audit_log AgentMessage rows, raises
  `RetryNotEligible` with a descriptive message on each
  ineligibility branch (no such task, no report yet, not
  blocked, blocked_on not recoverable, retry cap reached).
  `build_retry_message(original, retry_attempt)` returns a
  `model_copy` with fresh `message_id`,
  `hmac_signature=None`, and `metadata["retry_attempt"]=N`.
  Same task_id + correlation_id (load-bearing for HoldQueue).
- `POST /api/tasks/{task_id}/retry` endpoint in
  `apps/api/main.py`. Reads audit_log by JSON-path filter
  (`payload_json["payload"]["task_id"].astext == task_id`),
  validates eligibility, builds + HMAC-signs + writes
  to audit/feed/bus. Flips `tasks.status` from `blocked`
  back to `in_progress`. HTTP error mapping: 404 / 409 /
  422 / 429. Auth: same `require_owner_token` gate as
  /api/tasks.
- `ai-team retry-blocked <task_id> [--comment "..."]` CLI:
  thin Click wrapper, prints Rich panel on success +
  `ai-team watch` hint.
- 8 unit tests on the helper (each ineligibility branch +
  2 happy paths + build-retry copy semantics). 4 CLI unit
  tests. 3 integration tests with testcontainers
  (happy path with same task_id + retry_attempt + tasks.
  status flip; 409 on DONE; 404 on bogus UUID).

Phase 2 — Backend Bash defense-in-depth:

- One-line ClassVar addition:
  `disallowed_tools: ClassVar[tuple[str, ...]] = ("Bash",)`
  on `BackendDeveloperAgent`. The dispatcher's
  `_invoke_with_retries` already forwards the kwarg to
  `LLMClient.invoke()` → `claude -p --disallowed-tools Bash`.
- 2 unit tests pin: Bash in disallowed_tools + tuple shape.
- iter-11 demo validated the change: Backend's task_report
  explicitly says "Bash is blocked for git/uv/pytest per
  role constraints" and the LLM correctly routed to
  `mcp__ai_team_repo__*` instead.

Phase 3 — `BaseAgent.llm_timeout_s` 300→600 refactor:

- Flipped the default in `agents/_base/agent.py:67`.
- Dropped the redundant `= 600` override from Architect,
  Backend, Designer, DevOps, Frontend (5 agents).
- Added explicit `= 300` to ProductManager, SRESupport,
  TeamLead (3 agents that were relying on the old default).
- QAEngineer + MarketResearcher already had explicit 300.
- New `tests/unit/test_agent_timeouts.py` is a parametric
  pin across all 11 (BaseAgent + 10 agents).
- Net behavior change: zero. iter-11 demo confirmed
  Architect's 410 s opus call completed cleanly under the
  new 600 s default.

Phase 4 — Demo script + real-LLM run + report:

- `scripts/demo_iter_11.sh` clones `demo_iter_10.sh` with
  iter-11 header, `.iter11-mcp.json` config filename, and
  a new section after the chain-wait that surfaces BLOCKED
  rows + prints the `ai-team retry-blocked` invocation
  for the owner to copy/paste. `make demo` aliases to
  `demo-iter-11`.
- Real-LLM run on 2026-05-20, correlation `ccac21dc-…`.
  PM ($0.08 / 148 s), Architect ($2.47 / 410 s — longest
  opus call ever observed), Designer ($0.18 / 282 s),
  Frontend ($0.21 / 301 s) all DONE. Backend reported
  **FAILED** (not BLOCKED) — the iter-10 substring router
  didn't catch this run's failure phrase. QA cascade-
  dropped. Root flipped to `failed`.
- Total spend: **$3.41** — within $5 ceiling but driven
  by Architect's $2.47 single call.

Phase 5 — Final gates + retro + iter-12 handoff:

- `make lint typecheck sec` all green. 0 high-severity
  bandit findings.
- `make test test-integration smoke-llm` all green. 410
  total tests (368 unit + 42 integration).
- `uv run ruff format --check .` clean (140 files).
- **Diff-cover on iter-11 diff vs `origin/main`: 94%**
  (94 changed lines, 5 missing — both in
  `apps/api/main.py`'s error-handling tails that aren't
  exercised by integration tests yet).
- This file + `iter_12_handoff.md` + `iter_11_demo_report.md`.

## What went well

- **Plan-before-code held tightly.** Owner approved the
  plan inline; every phase commit tracked the plan exactly.
  Same pattern that worked iter-7..10.
- **TDD discipline held tightly.** Every code phase wrote
  tests first (8 RED→GREEN cycles for the helper, 3 for
  the endpoint integration, 4 for the CLI, 2 for Backend
  Bash, 11 for timeout pin = 28 cycles).
- **The retry mechanism is small + composable.** Pure
  helper in `core/retry/retry_blocked.py`, FastAPI
  endpoint as a thin I/O shell, CLI as an httpx call.
  Each layer is independently testable. The helper's
  six eligibility branches each have a dedicated unit
  test.
- **`metadata["retry_attempt"]` is a clean carrier.** The
  AgentMessage envelope already has a metadata bag; we
  ride the retry counter on it without a schema bump. The
  retry endpoint counts prior task_assignment audit rows
  to derive the next attempt number — no in-memory
  state required.
- **`disallowed_tools` was already plumbed.** The
  `_invoke_with_retries` machinery on `BaseAgent` already
  forwarded `disallowed_tools` to `LLMClient.invoke()`,
  which already forwarded to `claude -p --disallowed-tools`.
  Phase 2 was a one-tuple ClassVar — defense in depth
  came for free.
- **Timeout refactor was behavior-neutral by design.** The
  parametric pinning test caught the off-by-one risk
  (PM/SRE/TL silently jumping to 600) before any agent
  code touched it. Demo confirmed Architect now has
  headroom for its big opus call.
- **HMAC chain held through the retry.** The retry-blocked
  endpoint signs after eligibility check; audit/feed/bus
  all see one consistent retry message. Same architectural
  property iter-10's pre-sign router established.

## What didn't

- **Demo did not exercise retry-blocked end-to-end.**
  Backend's failure summary used a NEW phrase
  ("`mcp__ai_team_repo__* tools were unavailable
  throughout the session`") that iter-10's three pattern
  tuples don't match. The dispatcher saw a normal
  `task_report(failed)` → cascade-dropped QA → root
  FAILED → no recoverable state for retry-blocked.
  iter-12 fix: extend the pattern tuples (≤10 LOC + 1
  test).
- **Architect's $2.47 / 410 s single call is the biggest
  single spend ever.** Probably the v2 spec is now nine
  ADRs deep + cache fill is rich → consolidation work
  takes more output tokens. Might be a steady-state cost;
  iter-12 should watch.
- **iter-11 didn't catch the substring router coverage
  gap before the demo.** The demo report's pattern tuples
  were derived from iter-8/9 demo summaries. iter-10
  added a third tuple mid-flight when iter-8's wording
  surfaced. iter-11 should have run a small unit test
  enumerating "what other phrases might an LLM use to
  describe MCP unavailability?" — adding tuples
  preemptively. Iter-12 should do this.
- **Backend wrote a substantial implementation tree
  but couldn't commit/test.** `examples/sandbox/idea-
  validator/` has src/, tests/, sample/, scripts/,
  pyproject.toml on disk — but uncommitted. If retry
  had engaged, Backend's second attempt could have
  resumed from this state. iter-12 will validate this
  recovery path.

## Surprises

- **Backend's Bash defense-in-depth worked perfectly.**
  Backend's task_report explicitly acknowledged "Bash is
  blocked for git/uv/pytest per role constraints" — the
  LLM read the `--disallowed-tools Bash` flag and routed
  to `mcp__ai_team_repo__*`. No "Bash hooks blocked the
  pytest command" surface this run. The Phase 2 fix did
  exactly what it was designed to do. Just unfortunate
  that the MCP tools were ALSO unhealthy — those are two
  independent problems.
- **Architect's single call cost more than iter-9 + iter-10
  total Architect spend combined.** iter-9 Architect:
  $0.55. iter-10 Architect: $0.54. iter-11 Architect:
  $2.47 (4.5× jump). The v2 ADR consolidation prompt
  produced a comprehensive 7K-token contract document.
  Useful artifact, but the per-call cost is now in the
  same league as Backend's full implementation pass.
- **The retry endpoint's JSON-path query is fast enough.**
  `payload_json["payload"]["task_id"].astext` filter
  against ~150 audit rows runs in <10 ms in
  testcontainers Postgres. No GIN index needed at this
  scale. iter-15+ if the table grows past 10K rows.
- **Backend's failure landed at session start, not
  mid-session.** iter-8/9/10 all saw MID-session MCP
  races (tools work for the first N turns, fail later).
  iter-11 saw Backend's MCP tools unavailable
  THROUGHOUT — probably a startup-time problem this
  demo. Possibly correlated with the prior demo runs
  leaving `examples/sandbox/idea-validator/` on disk.

## Action items for iter-12

These overlap with `iter_11_demo_report.md` and
`iter_12_handoff.md` and are the starting list for the
next iteration. Highest priority first:

- [ ] **(top)** **Extend the iter-10 substring router with
      new pattern tuples** to catch the iter-11 demo's
      Backend phrasing. Candidates:
      `("mcp__ai_team_repo", "unavailable")`,
      `("MCP tools", "unavailable")`. Possibly also
      `("mcp_", "unavailable throughout")`. ≤10 LOC in
      `core/dispatcher/mcp_race_router.py` + 1 unit test
      pinning the iter-11 verbatim summary.
- [ ] **Re-run iter-11-shape demo** after #1 to finally
      exercise iter-11's retry-blocked end-to-end and
      close the `pending_review` loop iter-3..11 all
      reached for.
- [ ] **Investigate startup-time MCP failure.** iter-11
      demo's Backend reported MCP tools unavailable from
      session start, not mid-session. iter-8/9/10 all
      saw mid-session. Worth understanding whether the
      MCP server died before claude -p reconnected, or
      whether the in-process probe passed but the
      subprocess spawn failed.
- [ ] **Architect's $2.47 spend watch.** Track whether
      this is steady-state on v2 work, or a one-time
      consolidation cost. If steady-state, Architect
      needs the same decomposition treatment Backend is
      queued for.
- [ ] **TL Backend decomposition** (carry-over from
      iter-9/10). Now actively relevant — Backend's
      473 s session in this demo was the longest single
      agent call, and the MCP-race exposure window
      scales with session length.
- [ ] Carry-overs unchanged from iter-11 handoff (items
      6–13): HoldQueue persistence, `audit_writer`
      Postgres role, hash-chain alert, `GitHubTargetRepo`,
      TL transactional decomposition,
      `pytest-rerunfailures` plugin pin, `BaseAgent`
      template-method refactor.

## Stats

- **Commits on iter-11 branch**: 9 (plan + retry helper +
  endpoint + CLI + Backend Bash + timeout refactor +
  demo script + demo report + type cleanup + retro/
  handoff).
- **Tests added**:
  - 8 unit tests on `core/retry/retry_blocked.py`
  - 4 unit tests on `ai-team retry-blocked` CLI
  - 2 unit tests on Backend `disallowed_tools`
  - 11 parametric unit tests on agent `llm_timeout_s`
  - 3 integration tests on `/api/tasks/{id}/retry`
- **Tests modified**: 1 (the integration fixture
  signatures got proper type annotations in the cleanup
  commit).
- **Total tests after iter-11**: **368 unit + 42
  integration = 410 collected** (iter-10 close: 337
  unit + 38 integration = 375). Net +35 tests.
- **Real-LLM spend this iteration**: $3.41 (~68% of $5
  ceiling). TL $0.14 + PM $0.08 + Architect $2.47 +
  Designer $0.18 + Backend $0.33 + Frontend $0.21.
- **Diff-cover on iter-11 diff vs `origin/main`**: **94%**
  (94 changed lines across `apps/api/main.py`,
  `apps/cli/main.py`, `core/retry/retry_blocked.py`,
  `agents/_base/agent.py`, `agents/backend_developer/agent.py`,
  `agents/product_manager/agent.py`,
  `agents/sre_support/agent.py`,
  `agents/team_lead/agent.py`; 5 missing lines in
  `apps/api/main.py` error-handling tails).
- **LOC delta**: ~2000 added (Phase 1 module + endpoint +
  CLI + 4 new test modules + Phase 2-3 small edits +
  demo script + plan + demo report + retro + handoff).

## Ready-to-paste prompt for iter-12

In `docs/iterations/iter_12_handoff.md`.
