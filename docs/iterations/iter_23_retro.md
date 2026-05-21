# Iteration 23 retrospective

> **Status**: closed — iter-23 shipped the QA Python safety net
> and a small set of supporting changes. Full chain demo did not
> reach the QA-emitted `pending_reviews` row criterion (now
> 5-iteration deferred), but Phase 2's isolated e2e test proves
> the safety net works deterministically when QA's turn runs.

## Headline outcomes

✅ **Phase 1 diagnostic inverted the prescribed plan.** The
iter-23 handoff's TOP item was "extend demo poll window to
45 min — should land QA row." A $0.15 / 15-min mini-experiment
(`tests/integration/test_qa_request_human_review_real_llm.py`,
run before any safety-net code existed) showed **0/3 LLM
tool-call invocations**. The 4-iteration "demo timing" diagnosis
was wrong; the actual root cause was LLM compliance with the
side-effect MCP tool-call instruction under `--json-schema`
pressure.

✅ **Phase 2 safety net shipped + proven 3/3.** Adding
`session_factory` injection to `QAEngineerAgent` and a
`_ensure_pending_review_row` helper that inspects
`response.tools_used` and INSERTs directly when the LLM skipped
the tool. End-to-end e2e test (3 parametrized runs against real
Postgres + real `claude -p`) passed cleanly — in every run the
LLM skipped the tool and the safety net wrote the row.

✅ **Phase 3 trivial fix.** `RECOVERABLE_BLOCKED_ON +=
"task_too_large"` closes iter-22 demo Caveat C's misleading 422.

✅ **Phase 4 demo script.** 30 → 45 min poll window, per-minute
audit_row status line for easier post-mortem diagnostics.

⚠️ **Phase 6 full chain demo: PARTIAL.** Two runs:
- Run #1: chain stalled at Backend BLOCKED — LLM emitted a
  verbose free-form `blocked_on` string; TL's exact-match
  `_TASK_TOO_LARGE_BLOCKED_ON` check missed it.
- Hot-fix #1: schema enum constraint on `blocked_on` — looked
  cleanest. TL substring matcher + prompt tightening shipped
  alongside.
- Run #2: Backend BLOCKED(budget) — likely enum-induced
  `--json-schema` retry-loop until $2.50 per-call cap hit
  (unverified — API log was wiped by demo EXIT trap).
- Decision: revert enum (commit `88402b8`), ship as-is, write
  honest demo report. A third demo run wasn't going to add
  evidence beyond the e2e test's 3/3 proof.

## What went well

1. **Diagnostic discipline.** Inverting the handoff plan
   (mini-experiment first, then real demo) saved budget and
   produced a more confident architectural decision.
2. **TDD for the safety net.** RED (4 tests fail), GREEN
   (implementation), VERIFY (3/3 e2e against real LLM + Postgres).
3. **Layer separation.** Resisted the temptation to
   `import handle_request_human_review` from
   `tools/mcp_servers/` into `agents/`. Used direct
   `PendingReview` INSERT instead. agents/ → tools/ direction
   stays clean.
4. **Honest demo report.** Two failed runs, two distinct root
   causes, clear diagnosis, no overstatement of what was
   shipped.

## What didn't go well

1. **The enum hot-fix was too clever.** Schema enum on
   `blocked_on` looked tidy on paper but likely triggered
   `claude -p` retry loops that burned Backend's budget cap.
   The clean theory ("force LLM to use canonical token via
   schema") has a hidden cost ("LLM keeps trying invalid tokens
   until budget fires"). **Lesson: when adding strict
   `--json-schema` constraints, A/B test against a baseline
   first** — the budget-burn failure mode is opaque (no error
   message, just BLOCKED(budget) from the dispatcher).
2. **Chain demo still doesn't deliver QA a Backend DONE.** Five
   iterations now. Each iter has found a different upstream
   Backend failure mode. The criterion is now blocked by
   "Backend stability," not by anything QA-specific.
3. **API log lost on EXIT trap.** Both demo runs' API logs
   (`/var/folders/.../tmp.*.log`) were removed by the cleanup
   trap, denying forensic analysis of the BLOCKED(budget)
   theory. iter-24 needs to preserve these.
4. **Ran out of demo budget.** Two runs at ~$2 each consumed
   the planned budget. A third run might have caught a working
   chain but couldn't be justified without first understanding
   the BLOCKED(budget) cause.

## Lessons learned

- **Inverting prescribed plans is sometimes the right call.**
  If a $0.15 experiment can decide between two implementation
  paths, run the experiment first.
- **`--json-schema` enum constraints can backfire silently.**
  Validation failures don't propagate as clean errors — they
  manifest as budget exhaustion via internal retries.
  Document this in CLAUDE.md or ADR-008.
- **Direct DB writes from agents are OK** when the alternative
  is a layer-violating import or an unreliable LLM tool-call.
  The `pending_reviews` table is the owner-approval gate; the
  agent owns ensuring it lands.
- **Forensic logs matter.** Demo EXIT traps should preserve
  the API log + the audit_log slice for the demo's
  correlation_id, not delete them.

## Iteration stats

- **Wall-clock**: ~3 hours session time.
- **Cost**: ~$4.00 observable LLM spend (Phase 1 diag + Phase 2
  e2e + 2 demo runs).
- **Commits to `worktree-iter-23`**:
  - `399e8b8` — feat(qa): Python safety net (Phases 0-5)
  - `82ba755` — fix(backend,team_lead): canonical blocked_on
    token (hot-fix attempt)
  - `88402b8` — revert(backend): drop blocked_on enum
- **Tests**: 441 unit (+8 vs iter-22), 50 integration, 3
  real_llm (dual-marked).
- **Files touched (production)**: `agents/qa_engineer/agent.py`,
  `agents/backend_developer/agent.py`,
  `agents/team_lead/agent.py`, `apps/api/main.py`,
  `core/retry/retry_blocked.py`,
  `prompts/backend_developer.md`, `Makefile`.
- **New files**: `scripts/demo_iter_23.sh`,
  `tests/integration/test_qa_request_human_review_real_llm.py`,
  `docs/iterations/iter_23{.md, _demo_report.md, _retro.md}`,
  `docs/iterations/iter_24_handoff.md`.
- **PR**: TBD (PR #30 expected after this commit).

## Action items for iter-24

See `docs/iterations/iter_24_handoff.md`. Top items:

1. Backend stability investigation: A/B test
   `--json-schema` enum vs no-enum to confirm or deny the
   retry-loop theory.
2. Preserve API logs in demo EXIT trap.
3. Structural scope-detection in TL via summary prefix instead
   of `blocked_on` routing.
4. Commit `examples/sandbox/idea-validator/` scaffold to main.
5. Re-attempt QA criterion in full demo once upstream Backend
   reaches DONE.

## Carry-over (unchanged from iter-23 handoff)

Items 5-15 from `iter_23_handoff.md` remain deferred. None
addressed in iter-23 (out of scope — iter-23 was QA-blocker
focused).
