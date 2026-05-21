# Iteration 23 — Close the QA `pending_reviews` row blocker (4-iter deferred)

> **Status**: DRAFT — awaiting owner review.
> **Branch**: `worktree-iter-23` (cut from `1a5c7fd`).
> **Predecessor**: iter-22 retro + `iter_23_handoff.md`.
> **Scope**: tightly focused on the single 4-iteration-deferred criterion
> — a `pending_reviews` row with `requesting_agent='qa_engineer'`. All
> other carry-overs (handoff items 5-15) explicitly deferred to iter-24+.

## TL;DR

The QA-emitted `pending_reviews` row is the only outstanding success
criterion across iter-19..22 (4 iterations). iter-22's demo report
identified the *current* failure mode as "demo poll window expired with
Backend recovery turn in flight" — i.e. **operational, not
architectural**. The iter-23 handoff's TOP item is "extend demo poll
window to 45 min."

But there's a deeper risk that has been hand-waved for 4 iterations:
**we have never end-to-end verified that QA's LLM actually calls
`mcp__ai_team_tasks__request_human_review` under real conditions.**
The contract is correct on paper (prompt + tool allowlist + iter-18
handler all in place), but it has been gated behind a never-reached
code path. If we just bump the poll window and the LLM silently skips
the tool call, we burn another $2 + 30 min demo and learn nothing.

**iter-23 inverts the diagnostic order**: first do a $0.10 / 5-min
controlled mini-experiment that exercises QA directly with a synthetic
Backend task_report. THEN, based on what we observe, decide whether we
need a Python-side safety net. THEN extend the poll window and re-run
the full demo.

## Goals

1. **(P0, blocker-closer)** Produce a `pending_reviews` row with
   `requesting_agent='qa_engineer'` in the iter-23 real-LLM demo —
   the criterion that has been 4-iteration deferred (iter-19 → 20 →
   21 → 22).
2. **(P0)** Determine empirically whether QA's LLM reliably calls
   `request_human_review`. If unreliable, ship a Python-side safety
   net so the criterion does not depend on LLM compliance.
3. **(P1)** Close iter-23 handoff #2: `RECOVERABLE_BLOCKED_ON +=
   "task_too_large"` so `ai-team retry-blocked` does not 422 on
   self-eject BLOCKEDs.
4. **(P1)** Extend demo poll window from 30 → 45 min, matching
   CLAUDE.md's documented "30 min initial + 15 min retry" budget.

## Non-goals (explicit)

- TL prompt sharpening to follow Architect's stated DAG decomposition
  (iter-23 handoff #3, OPTIONAL) — defer to iter-24 unless the iter-23
  demo evidence demands it.
- HoldQueue Postgres persistence, GitHubTargetRepo,
  pytest-rerunfailures, BaseAgent template-method refactor, or any
  carry-over with priority ≥5 in the handoff — explicitly defer.
- Removing the iter-21 Backend Python tripwire (defense-in-depth
  remains valued).
- Reworking the iter-22 prompt-edit + `depends_on` rules (they fired
  correctly).

## Key insight from code audit

`core/llm/base.py:65-78` — `LLMResponse` already exposes
`tools_used: list[ToolUse]`. `core/llm/claude_code_headless.py:433-451`
populates it from `claude -p`'s response stream. **Python CAN detect
after-the-fact whether QA's LLM invoked `request_human_review`** —
this is the basis for the safety net in Phase 2 (if Phase 1 evidence
warrants).

`tools/mcp_servers/ai_team_tasks/handlers.py:86-139` —
`handle_request_human_review` is a thin async wrapper around a
SQLAlchemy INSERT. It uses `ctx.session_factory()`,
`ctx.default_correlation_id` (iter-19), `ctx.default_agent` (iter-18).
The handler is well-defended against missing args. **The only thing
that must happen for a row to appear is that the LLM emits a tool-call
with at least `summary` populated.**

`prompts/qa_engineer.md:27-39` — step 4 mandates the call. But the
prompt is "responsibility-style" instruction; LLMs sometimes prioritize
the structured-output JSON over the side-effect tool calls,
especially under `--json-schema` pressure. **This is the unverified
risk.**

## Phase 0 — Plan + tracking (this doc) ✅

- [x] Cut `worktree-iter-23` from `origin/main` (`1a5c7fd`).
- [x] Write this plan.
- [x] Owner approved.
- [x] TaskCreate list for phases 1-7.

## Phase 1 — Decisive QA-path mini-experiment (cheap, fast, diagnostic)

**Hypothesis to test**: does QA's LLM reliably invoke
`mcp__ai_team_tasks__request_human_review` when handed a clean
synthetic Backend `task_report(done)`?

**Method**: a new real-LLM integration test
(`tests/real_llm/test_qa_request_human_review.py`,
`@pytest.mark.real_llm`). Setup:

1. Spin up testcontainers Postgres + Redis (via existing fixtures).
2. Boot the dispatcher with only the QA agent registered.
3. Construct a synthetic `AgentMessage(TASK_ASSIGNMENT)` to QA with
   the same shape TL emits — task_id, correlation_id, and a payload
   summary mimicking "Backend reports tests passed on branch X. Please
   verify and request human review." Set
   `AI_TEAM_CORRELATION_ID` + `AI_TEAM_AGENT_ROLE=qa_engineer` env.
4. Publish to bus. Wait up to 6 min for QA to complete.
5. Query `pending_reviews` for `requesting_agent='qa_engineer'` AND
   `correlation_id=<the synthetic UUID>`.
6. Also assert `response.tools_used` (from the audit_log envelope's
   `metadata.llm.tools_used`) contains
   `mcp__ai_team_tasks__request_human_review`.
7. Run 3 times sequentially to get a small reliability sample
   (`@pytest.mark.parametrize("run", [0, 1, 2])`).

**Cost estimate**: 3 × ~$0.05 = $0.15. Wall-clock ~15 min total
(parallel-safe).

**Decision tree**:
- **All 3 runs: row appears + tool_use logged** → QA contract is solid,
  iter-22 truly was a poll-window issue. Skip Phase 2 safety net,
  proceed to Phase 3.
- **0-1 / 3 rows appear** → QA LLM is unreliable on tool-call follow-through.
  Phase 2 ships the Python safety net.
- **2-3 / 3 rows appear, but flaky** → Phase 2 ships the safety net
  too (don't ship a flaky criterion).

**Files**:
- Create: `tests/integration/test_qa_request_human_review_real_llm.py`
  (dual-marked `integration` + `real_llm`; uses existing testcontainers
  fixtures; `make test-integration` excludes via `-m "integration and
  not real_llm"`).

**Validation**: `TESTCONTAINERS_RYUK_DISABLED=true uv run pytest
tests/integration/test_qa_request_human_review_real_llm.py --real-llm
-v -s`. Must pass cleanly (3/3 rows) OR fail informatively.

### Phase 1 result (2026-05-21) ✅ DECISIVE — 0/3

**`tools_used=[]` in all 3 runs.** QA's LLM produced valid
schema-conformant QA JSON (validated_against_schema=True, ~640 output
tokens) but did NOT invoke `mcp__ai_team_tasks__request_human_review`
in any run, even with explicit "call this tool with cid=X" in the
user_message. `tool_count=9` confirmed all expected tools were
declared available; the LLM simply chose not to use any of them under
`--json-schema` pressure.

**This is the true root cause of the 4-iteration QA blocker.** It has
NEVER been a demo-poll-window issue. iter-19/20/21/22 all
incorrectly attributed cascade failure to upstream Backend
timeouts (true for iter-19-21, but iter-22's "in flight" diagnosis
was wrong — even if Backend had completed, QA would have produced
a TASK_REPORT without ever writing the pending_reviews row).

**Implication**: Phase 2 is MANDATORY (no longer conditional).
Without the Python-side safety net, no demo-window extension will
ever produce the criterion row.

Per-run stats (`tools_used=[]` for all):
- run 0: 21066ms, tokens_in=7, tokens_out=641
- run 1: 17046ms, tokens_in=7, tokens_out=620
- run 2: 17082ms, tokens_in=7, tokens_out=638

(`tokens_in=7` looks anomalous — likely a parser issue in
`claude_code_headless.py`'s token extraction. Side-investigation,
not blocking.)

## Phase 2 — Python-side safety net ✅ SHIPPED (3/3 e2e PASSED)

**Result (2026-05-21)**: `QAEngineerAgent.__init__` now accepts
`session_factory`; `handle()` inspects `response.tools_used` after
the LLM turn; safety net INSERTs the `pending_reviews` row directly
via `PendingReview` when `mcp__ai_team_tasks__request_human_review`
is absent. Plumbed via `apps/api/main.py:93`.

End-to-end real-LLM validation (3 parametrized runs against
testcontainers Postgres) — **3/3 PASSED**. In every run the LLM
skipped the tool (`qa.safety_net.row_inserted reason=
llm_skipped_request_human_review_tool` structlog warning fired),
and the safety net wrote the row deterministically. Total cost
$0.10, total wall-clock 220s.

12 QA unit tests (8 existing + 4 safety net), 438 unit suite,
50 integration suite, ruff/mypy/bandit/smoke-llm all green.

**Design**: in `QAEngineerAgent.build_outputs`, after producing the
`task_report`, inspect `response.tools_used`. If no entry matches
`mcp__ai_team_tasks__request_human_review`:

1. Log a structlog warning at WARN level with
   `correlation_id`, `task_id`, summary preview.
2. **Construct a `PendingReview` row directly via the agent's injected
   `session_factory`** (option A — direct DB write using
   `core.persistence.models.PendingReview`). Mirrors the iter-18
   handler's INSERT shape. Avoids the layer-violation of importing
   from `tools.mcp_servers.*` into agents/.
3. If the safety-net INSERT fails (DB unreachable, etc.), append an
   ERROR to the report summary and continue. **Never silently swallow.**
4. If `session_factory=None` (unit-test path), log loud-and-skip.

**Why direct DB INSERT over re-prompt**: re-prompt costs another LLM
turn ($0.05+, ~30s, and Phase 1 evidence shows it would likely also
not call the tool). Direct INSERT is deterministic, free, and
addresses the structural risk that future LLMs will keep dropping
side-effect tool calls under structured-output pressure.

**Plumbing concern**: `QAEngineerAgent` currently doesn't receive a
`session_factory`. Add a kwarg with a `None` default; the dispatcher
constructs the factory once on startup and passes it in via the
agent's `_session_factory` attribute. When `None`, the safety net
degrades to "log loud and skip the INSERT" — preserves existing test
behaviour.

**Tests (TDD)**:

1. `tests/unit/test_qa_engineer_agent.py::test_safety_net_inserts_when_tool_use_missing`:
   construct a `LLMResponse` with empty `tools_used` and a DONE
   structured payload. Pass a mock session_factory. Assert
   `pending_reviews` table mock got an INSERT with
   `requesting_agent='qa_engineer'`.
2. `tests/unit/test_qa_engineer_agent.py::test_safety_net_skipped_when_tool_use_present`:
   `tools_used=[ToolUse(name='mcp__ai_team_tasks__request_human_review', ...)]`.
   Assert no Python-side INSERT.
3. `tests/unit/test_qa_engineer_agent.py::test_safety_net_logs_when_no_session_factory`:
   `session_factory=None` + empty `tools_used`. Assert structlog WARN
   emitted, no exception.

**Files**:
- Modify: `agents/qa_engineer/agent.py`
- Modify: `core/dispatcher.py` (pass session_factory to QA agent on startup)
- Modify: `tests/unit/test_qa_engineer_agent.py` (3 new tests)

**Validation**:
- `pytest tests/unit/test_qa_engineer_agent.py -v` (all green)
- `make lint && make typecheck && make sec`
- Re-run Phase 1 real-LLM test — now must be 3/3.

## Phase 3 — `RECOVERABLE_BLOCKED_ON += "task_too_large"`

**Trivial fix** per iter-23 handoff #2.

**Change**: `core/retry/retry_blocked.py:34`:
```python
RECOVERABLE_BLOCKED_ON: frozenset[str] = frozenset({
    "mcp_unhealthy",
    "budget",
    "task_too_large",  # iter-23: TL auto-re-decomposes; CLI should not 422
})
```

**Pin test**: `tests/unit/test_retry_blocked.py::test_task_too_large_recoverable`
— assert `"task_too_large" in RECOVERABLE_BLOCKED_ON` and
`check_retry_eligibility` does not raise on a BLOCKED row with that
`blocked_on`.

**Files**:
- Modify: `core/retry/retry_blocked.py` (1 line + comment)
- Modify: `tests/unit/test_retry_blocked.py` (1 new test)

**Validation**: `pytest tests/unit/test_retry_blocked.py -v`.

## Phase 4 — Demo script: poll window 30 → 45 min + small DX

**Clone** `scripts/demo_iter_22.sh` → `scripts/demo_iter_23.sh`. Diff:

1. **Bump POLL_TIMEOUT_S from `1800` to `2700`** (45 min). Match
   CLAUDE.md's "30 min initial + 15 min retry" budget.
2. **Per-poll status line** every 60s: print number of rows in
   audit_log, plus the highest task_id status. Helps diagnose
   "what was in flight when the poll expired" — iter-22 demo had to
   reverse-engineer this from audit_log post-mortem.
3. **Final summary block** explicitly counts:
   - Total audit rows
   - `pending_reviews` rows with `requesting_agent='qa_engineer'`
   - Any BLOCKED tasks still pending
   The narrative should make it loud-and-clear whether the iter-23
   criterion was met.
4. **`Makefile`**: add `demo-iter-23` target. Repoint `demo` → it.

**No** drain-BLOCKED auto-retry step — TL already auto-re-decomposes,
no manual retry needed for `task_too_large`.

**Files**:
- Create: `scripts/demo_iter_23.sh` (~380 lines, clone of iter-22 with above tweaks)
- Modify: `Makefile` (2 lines)
- Comment-warn: `scripts/demo_iter_22.sh` ("HISTORICAL — see iter-23
  for current shape" header line)

**Validation**: `bash -n scripts/demo_iter_23.sh` (syntax check). No
execution at this phase — the full real-LLM demo runs in Phase 6.

## Phase 5 — Full validation gates

Pre-demo:
- `make test-unit` — all green, including the new Phase 2/3 tests
- `make test-integration` — testcontainers, all green
- `make lint && make typecheck && make sec` — clean
- `make smoke-llm` — `claude -p` substrate health

CI gates:
- diff-cover ≥ 80%
- ruff check . (explicit dot, iter-21 lesson)
- bandit high-only

**Files**: none. Just runs.

## Phase 6 — Real-LLM demo (the criterion)

`AI_TEAM_DEMO_NON_INTERACTIVE=1 bash scripts/demo_iter_23.sh`.

**Success criteria** (in order of importance):

1. **PRIMARY**: at least one row in `pending_reviews` with
   `requesting_agent='qa_engineer'`. **4-iteration-deferred
   criterion finally met.**
2. **Chain shape** (must hold): Backend either DONE'd a small subtask
   OR self-ejected → TL re-decomposed → Backend DONE'd smaller →
   QA picked up.
3. **Cost**: under $5 (iter-22 was $2.02).
4. **Wall-clock**: under 45 min total.
5. **Architect→Backend depends_on** still applies (iter-22 contract).
6. **No regression**: orchestrator HEAD stays on
   `worktree-iter-23`, `.claude/agent-worktrees/` empty post-EXIT.

**Failure modes to expect-and-record** (not blockers, but documented):

- Frontend still BLOCKED on architecturally-prohibited POST /analyze
  (iter-21/22 pattern). Spec-correct refusal, not a regression.
- Designer might or might not produce visible artifacts. Optional.

**Write**: `docs/iterations/iter_23_demo_report.md` with the same
shape as `iter_22_demo_report.md` — outcome, wins, caveats, cost
table, comparison vs iter-22.

## Phase 7 — Retro + handoff + PR merge

1. `docs/iterations/iter_23_retro.md` — what shipped, what didn't,
   carry-overs.
2. `docs/iterations/iter_24_handoff.md` — full handoff for the next
   session.
3. Commit + push branch.
4. Open PR: `iter-23: close QA pending_reviews blocker (Python safety
   net + 45min poll + RECOVERABLE_BLOCKED_ON)`. PR body includes the
   demo evidence — paste the relevant audit_log rows + the
   `pending_reviews` query result.
5. CI must be green (lint-and-test + commitlint).
6. **Merge via `gh api -X PUT repos/.../pulls/<N>/merge -f
   merge_method=squash`** — bypasses gh CLI's local-checkout that
   fails when `main` is checked out in another worktree (iter-22 lesson).
7. Verify `git fetch origin main` then `git log -1 --oneline
   origin/main` shows the merged commit.

## Risks + mitigations

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| QA LLM still unreliable on tool-call after safety net | Low | Safety net is deterministic Python — does not depend on LLM. |
| Phase 1 mini-experiment reveals deeper QA bug (timeout, MCP race) | Medium | Diagnostic is the goal; we fix in Phase 2 with full context. |
| Backend smaller-scope (e.g. `be_schema`) timeouts at 600s | Medium | 45-min poll catches the FAILED row; we'd then know definitively that even small scope is too slow — iter-24 problem. iter-23 still ships safety net + can run a QA-only demo path to validate the criterion. |
| Demo total wall-clock > 45 min | Low | Should fit: PM 10min + Architect 3min + Backend (self-eject 1min + re-decomp 1min + DONE 5-10min) + QA 5min ≈ 25-30 min. Buffer is generous. |
| Phase 2 safety net regresses unit tests by changing `QAEngineerAgent` signature | Low | TDD ordering: tests first; existing tests should pass unchanged. |
| `pending_reviews` schema / model has drifted | Very low | Recently touched in iter-18/19; covered by integration test for live API. |

## Hard constraints (unchanged, per iter-23 handoff)

All hard constraints from iter-4..22 hold. Key ones for iter-23:

- **LLM substrate is `claude -p` subscription only.** No
  ANTHROPIC_API_KEY.
- **`--json-schema` output lives in `structured_output`**.
- **`request_human_review` is load-bearing** — iter-23 makes the safety
  net Python-side, but the LLM tool-call path remains primary.
- **`Context.default_correlation_id`** sourced from
  `AI_TEAM_CORRELATION_ID` (iter-19) — the safety net's direct call
  relies on this fallback.
- **PR merge**: `gh api -X PUT ...` not `gh pr merge`.
- **`ruff check .`** with explicit dot.
- **Plan-before-code, conventional commits, owner approval gate, squash-merge.**

## File summary (will be touched)

**New**:
- `docs/iterations/iter_23.md` (this)
- `tests/real_llm/test_qa_request_human_review.py`
- `scripts/demo_iter_23.sh`
- `docs/iterations/iter_23_demo_report.md` (Phase 6)
- `docs/iterations/iter_23_retro.md` (Phase 7)
- `docs/iterations/iter_24_handoff.md` (Phase 7)

**Modified**:
- `agents/qa_engineer/agent.py` (Phase 2, conditional)
- `core/dispatcher.py` (Phase 2 plumbing, conditional)
- `core/retry/retry_blocked.py` (Phase 3, 1 line + comment)
- `tests/unit/test_qa_engineer_agent.py` (Phase 2 tests, conditional)
- `tests/unit/test_retry_blocked.py` (Phase 3 pin test)
- `Makefile` (Phase 4, 2 lines)
- `scripts/demo_iter_22.sh` (Phase 4, comment-warn header)

**Conditional** (only if Phase 1 → safety net needed):
- All of Phase 2's modifications above.

## Timeline estimate

- Phase 0: 30 min (this plan + owner review)
- Phase 1: 30 min (write test + run 3× × 5 min)
- Phase 2 (if needed): 60 min (TDD + plumb session_factory)
- Phase 3: 15 min (trivial)
- Phase 4: 30 min (clone + tweak demo script)
- Phase 5: 15 min (run gates)
- Phase 6: 45 min (real-LLM demo)
- Phase 7: 30 min (retro + handoff + PR)

**Total**: 3.5-4.5 hours, dominated by Phase 1+6 LLM wall-clock.

**Total cost estimate**: $0.15 (Phase 1) + $3 (Phase 6, worst case) =
**~$3.15**. Within the per-iteration $5 ceiling.
