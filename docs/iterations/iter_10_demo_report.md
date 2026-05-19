# Iter-10 real-LLM end-to-end demo — report

- **Date**: 2026-05-19 (iter-10 session)
- **Run by**: Claude (Opus 4.7) per `docs/iterations/iter_10.md` Phase 6
- **Script**: `AI_TEAM_DEMO_NON_INTERACTIVE=1 bash scripts/demo_iter_10.sh`
- **Task**: idea-validator v2 (`docs/sandbox/idea_validator_v2_spec.md`)
- **Correlation ID**: `a15cb0f1-4625-4d4c-aafe-b2c5ef2ae657`
- **Outcome**: **iter-10 Phase 1+2 (substring router + dispatcher
  wire-up) VALIDATED END-TO-END in production for the first
  time across ten demos. Backend's session hit the SAME
  mid-session MCP race iter-8 + iter-9 saw, emitted a real
  schema-valid `task_report(failed)` whose summary substring-
  matched ("MCP server" + "never connected"), and the iter-10
  router rewrote it to `status=BLOCKED, blocked_on='mcp_unhealthy'`
  before HMAC-sign. Audit row 136 reflects the rewritten BLOCKED
  payload directly. QA was held in the HoldQueue (not
  cascade-dropped). Root Task stayed `in_progress` (not rolled
  up to failed). This is the second-of-two valid terminal
  states success criterion #7 named: "if Backend trips the
  substring router, BLOCKED routes cleanly (no cascade-drop);
  QA stays held; owner can manually retry and the loop closes
  via the BLOCKED path." Phases 3 (Backend Bash prompt) and 4
  (mypy exclude) shipped behind earlier verification —
  Backend's prompt now lists every `command_class` value
  explicitly but Backend STILL reported the Bash gate as a
  secondary blocker (suggests the prompt fix needs further
  reinforcement, possibly removing Bash from
  `allowed_tools` entirely — iter-11 work). The
  `pending_review` → owner approve loop is still untouched
  end-to-end across ten demos; iter-11 needs a TL auto-hop on
  `BLOCKED(mcp_unhealthy)` or an `ai-team retry-blocked`
  command to actually close that loop after a BLOCKED
  outcome.**

## Verdict in one line

iter-10's substring router fired in production for the first
time, producing the exact recoverable terminal state success
criterion #7 named — root stays in_progress, QA held in
HoldQueue, owner has a clear "fix MCP and retry Backend"
path.

## What worked (iter-10 deliverables, all four landed)

1. **`core/dispatcher/mcp_race_router.py:maybe_route_mcp_race_to_blocked`**
   FIRED in production. Backend (audit row 136) emitted a
   schema-valid `task_report(failed)` whose summary contained
   both "MCP server" and "never connected" — exactly one of
   the three pattern tuples. Router rewrote
   `status=BLOCKED, blocked_on='mcp_unhealthy'` before
   HMAC-sign; the audit log shows the BLOCKED version
   directly with the LLM's verbatim summary preserved.
2. **Dispatcher wire-up in `_handle_one`'s outbound loop**
   validated end-to-end. The single new line
   `out = maybe_route_mcp_race_to_blocked(raw_out)` triggered
   correctly; HoldQueue's existing iter-6 BLOCKED handling
   held QA (not cascade-dropped); root Task stayed
   `in_progress` (not rolled up to failed via the iter-7
   any-failed cascade); QA's child Task row stayed
   `in_progress` (not `failed-via-cascade`).
3. **Backend Bash prompt fix** shipped (Phase 3). The Backend
   system prompt now lists every `command_class` value in a
   lookup table at the top of the prompt — `git_status`,
   `git_add`, `git_commit`, `git_push_feature`, `gh_pr_create`,
   `pytest`, `make_test`, `ruff`, `mypy`. Backend's report
   summary still mentions "Bash hooks blocked the pytest
   command" — suggests the LLM is still reaching for Bash even
   when the prompt explicitly forbids it. Discussed in
   "What didn't" below.
4. **`^examples/` mypy exclude** (Phase 4) validated. Bare
   `make typecheck` passes on the demo-polluted workspace
   without `--exclude '^examples/'` workaround. iter-8 +
   iter-9 retros both flagged this; iter-10 closed it.

## What didn't (failure modes for iter-11)

### Failure 1 — Bash gating still bit Backend despite the iter-10 prompt fix

Backend's audit row 136 summary names "Bash hooks blocked
the pytest command" as a secondary blocker, even though
iter-10's Phase 3 prompt edit explicitly added a 10-row
lookup table directing Backend to use
`mcp__ai_team_repo__run_shell(command_class="pytest", …)`
for pytest. The LLM understood the prompt — Backend's own
summary acknowledges trying pytest — but still hit a Bash
gate.

Two possible explanations:
- Backend tried `Bash("pytest ...")` first, got rejected
  (because Bash isn't in its `allowed_tools`), and reported
  the rejection as a gate.
- Backend tried
  `mcp__ai_team_repo__run_shell(command_class="pytest")`
  but that command_class invocation somehow routed through
  Bash internally and hit the same gate.

Either way: prompt-only enforcement isn't fully sufficient.
iter-11 fixes:
- (a) **Remove `Bash` from Backend's `allowed_tools`** entirely
  (currently it's already not in the tuple, but worth
  re-verifying claude -p's behavior — `--allowed-tools` is
  an explicit allowlist, so Bash should already be denied).
  If Bash is still reachable, there's a `--disallowed-tools`
  gap to close.
- (b) **Inspect `mcp__ai_team_repo__run_shell` for any subprocess
  routing that might still touch the host's shell-permission
  layer.** The MCP server runs subprocesses inside the
  agent's process (per `commands.py`), so this should be
  outside claude -p's permission system. But the LLM is
  perceiving SOMETHING as "Bash blocked".
- (c) **Reproduce in unit test**: have `_StubLLM` call Bash
  explicitly and verify claude -p's flag handling correctly
  blocks it without surfacing as "Bash hook approval needed".

### Failure 2 — `pending_review` loop still untouched end-to-end

Ten demos in a row (iter-2c..iter-10) have stopped short of
the full `pending_review` → owner approve loop. iter-10's
BLOCKED outcome is a major step toward making the chain
recoverable, but recovery requires owner action that the
current CLI doesn't provide cleanly:

- `ai-team list-pending` shows zero rows because BLOCKED
  reports don't create `pending_review` entries (those come
  from `mcp__ai_team_tasks__request_human_review` or QUESTION
  messages).
- The HoldQueue holds Backend's task assignment for QA's
  predecessor in memory; restarting the dispatcher loses it.
- There's no `ai-team retry-blocked <task_id>` command yet.

iter-11 options:
- (a) **TL auto-hop on `BLOCKED(mcp_unhealthy)`**: when TL
  receives a BLOCKED report with `blocked_on='mcp_unhealthy'`,
  emit a fresh task_assignment for the SAME task to the same
  recipient (mirrors iter-2c's BLOCKED auto-route but for
  this specific blocked_on value). Bounded by iter-2c's
  one-hop-max guard.
- (b) **`ai-team retry-blocked <task_id>` CLI**: explicit
  owner-initiated retry. Owner-in-the-loop is more aligned
  with ADR-001's "owner controls dangerous actions" posture.
- (c) **Combine**: auto-hop for MCP races (transient), owner
  CLI for budget exhaustion (needs owner judgment on whether
  to raise the cap).

Recommended: (b) first — simpler, owner stays in the loop.
(a) can land later if MCP races prove genuinely transient
and auto-retry is safe.

## Chain timeline

Single SQL paste (correlation `a15cb0f1-4625-4d4c-aafe-b2c5ef2ae657`):

| id  | t        | sender             | recipient          | type            | status  | blocked_on    | model            | cents | duration_ms |
|-----|----------|--------------------|--------------------|-----------------|---------|---------------|------------------|-------|-------------|
| 125 | 20:19:59 | user               | team_lead          | task_assignment |         |               |                  |       |             |
| 126 | 20:20:26 | team_lead          | broadcast          | broadcast       |         |               | claude-opus-4-7  | 12    | 27460       |
| 127 | 20:20:26 | team_lead          | product_manager    | task_assignment |         |               | claude-opus-4-7  | 12    | 27460       |
| 128 | 20:20:26 | team_lead          | architect          | task_assignment |         |               | claude-opus-4-7  | 12    | 27460       |
| 129 | 20:20:26 | team_lead          | backend_developer  | task_assignment |         |               | claude-opus-4-7  | 12    | 27460       |
| 130 | 20:20:26 | team_lead          | designer           | task_assignment |         |               | claude-opus-4-7  | 12    | 27460       |
| 131 | 20:20:26 | team_lead          | frontend_developer | task_assignment |         |               | claude-opus-4-7  | 12    | 27460       |
| 132 | 20:20:26 | team_lead          | qa_engineer        | task_assignment |         |               | claude-opus-4-7  | 12    | 27460       |
| 133 | 20:21:33 | product_manager    | team_lead          | task_report     | done    |               | claude-sonnet-4-6| 4     | 66808       |
| 134 | 20:23:34 | architect          | team_lead          | task_report     | done    |               | claude-opus-4-7  | 54    | 120355      |
| 135 | 20:27:24 | designer           | team_lead          | task_report     | done    |               | claude-sonnet-4-6| 16    | 229927      |
| 136 | 20:29:44 | backend_developer  | team_lead          | task_report     | blocked | mcp_unhealthy | claude-sonnet-4-6| 25    | 370037      |
| 137 | 20:30:19 | frontend_developer | team_lead          | task_report     | done    |               | claude-sonnet-4-6| 13    | 175786      |
| —   | (held)   | qa_engineer        | (depends_on=[be, fe]; be is BLOCKED, fe is done — HoldQueue holds qa until be terminal) | — | — | — | — | — |

The 7 TL rows (126–132) share one TL invocation (12 ¢
counted once). Backend's row 136 reflects the rewritten
BLOCKED payload — `status=blocked, blocked_on='mcp_unhealthy'`
visible directly in the audit_log without any post-processing.

## What this demo confirmed for iter-10

✅ **`maybe_route_mcp_race_to_blocked` fired correctly in
   production.** Backend's `task_report(failed)` summary
   matched the `("MCP server", "never connected")` pattern;
   router returned a model_copy with status=BLOCKED,
   blocked_on='mcp_unhealthy'. Audit row 136 reflects the
   rewrite directly — HMAC covers the BLOCKED payload.

✅ **Dispatcher's `_handle_one` outbound wire-up correct.**
   Single new line
   `out = maybe_route_mcp_race_to_blocked(raw_out)` triggered
   exactly once for Backend's report; pass-through for every
   other agent's outputs (PM, Architect, Designer, Frontend
   all status=done with no payload mutation).

✅ **HoldQueue holds dependents under BLOCKED.** QA
   (depends_on=[be, fe]) stayed in the HoldQueue at run end
   — not delivered to QA agent, not cascade-dropped. Task
   row 22482eb6 has status='in_progress'. This is the
   iter-6 budget BLOCKED contract being reused correctly.

✅ **Root Task stays in_progress under BLOCKED.** Root
   3695fbaa stayed `in_progress` — no any-failed rollup
   (iter-7), no any-blocked rollup (no such rule exists).
   This is the recoverable terminal state owner needs to
   intervene from.

✅ **Phase 4 mypy exclude** validated. Bare `make typecheck`
   passed on the demo-polluted workspace without
   `--exclude '^examples/'` workaround.

✅ **iter-7 transitive cascade still works** — though it
   didn't fire this run (no FAILED to cascade), the integration
   test for it still passes. No regression.

## What this demo did NOT confirm

❌ **End-to-end chain → `pending_review` → owner approve.**
   Ten demos in a row. iter-10's BLOCKED is a *recoverable*
   stop, not a full close. iter-11 needs a retry mechanism.

❌ **Backend reaching `done` via the full v2 implementation
   path.** Backend hit the same mid-session MCP race for the
   third run in a row. The pattern is reproducible: Backend's
   session has the longest cached_input fill (2.3 M tokens
   this run, after 3.3 M in iter-9) and apparently is most
   exposed to the race window.

❌ **Backend prompt fix fully preventing Bash use.** Backend
   still hit a "Bash hooks blocked the pytest command" gate
   even with the iter-10 lookup-table prompt edit. Defense
   in depth needed.

## Cost / quota

Real metrics from `metadata.llm`:

| Agent              | Model         | tokens_in | tokens_out | cached_input | cost_cents | duration_ms |
|--------------------|---------------|-----------|------------|--------------|------------|-------------|
| TL                 | opus-4-7      | 7         | 1706       | 37236        | 12         | 27460       |
| PM                 | sonnet-4-6    | 6         | 2712       | 82215        | 4          | 66808       |
| Architect          | opus-4-7      | 11        | 7299       | 258078       | 54         | 120355      |
| Designer           | sonnet-4-6    | 8         | 10812      | 278772       | 16         | 229927      |
| Backend (BLOCKED)  | sonnet-4-6    | 36        | 17292      | 2308954      | 25         | 370037      |
| Frontend           | sonnet-4-6    | 12        | 9045       | 699148       | 13         | 175786      |
| QA (held)          | —             | —         | —          | —            | $0         | —           |
| **Total**          |               |           |            |              | **$1.24**  | —           |

Within $0.01 of iter-9's $1.23. Cost remains stable
iteration-over-iteration as cache hit rates climb (Backend
2.3 M cached tokens). Well under $5 ceiling.

## Artifacts produced this run

- 1 root `Task` row, **status: `in_progress`** (NOT failed —
  the substring router prevented the any-failed cascade).
- 6 child Task rows:
  - 4 `done` (PM, Architect, Designer, Frontend)
  - 1 `blocked` (Backend — via iter-10 router rewrite)
  - 1 `in_progress` (QA — held in HoldQueue, not delivered)
- 13 audit_log rows; chain intact, HMAC valid (the router's
  rewrite happens BEFORE signing, so HMAC covers the
  rewritten BLOCKED payload — chain stays valid).
- Files written (per agent summaries):
  - `docs/adr/0018-…` (Architect — new system-design ADR)
  - `docs/design/idea-validator.md` (Designer — UX brief +
    wireframes; ~11 K tokens of substantive content)
  - `apps/web/idea-validator/index.html` (Frontend — 170-line
    landing page)
  - `examples/sandbox/idea-validator/sample/` — Backend's
    summary says it wrote "the committed sample/ directory
    (6 fixture files)" + `scripts/refresh_sample.sh` + bug
    fix to `make_search("quick")` + 3 new tests. Files are
    on disk in the worktree but not committed (the BLOCKED
    state is precisely about that).
- QA artifacts: NOT written (held).

## Action items for iter-11

These overlap with `iter_10_handoff.md` and
`iter_11_handoff.md`. Highest priority first:

1. **(top)** **`ai-team retry-blocked <task_id>` CLI** OR
   **TL auto-hop on `BLOCKED(mcp_unhealthy)` BLOCKED reports**.
   The substring router gives us a recoverable BLOCKED state;
   iter-11 needs a way to actually RECOVER from it. Owner-in-
   the-loop CLI is simpler, doesn't need a per-correlation
   retry counter, and aligns with ADR-001's posture. The
   auto-hop variant is faster for transient races but
   requires the retry counter.
2. **Re-run iter-10-shape demo with retry mechanism**: same
   30-min wall-clock, observe whether retried Backend
   completes (MCP race may be flaky enough that one retry
   succeeds).
3. **Backend Bash gating: defense-in-depth beyond prompt**.
   Verify `--allowed-tools` actually blocks Bash (it should);
   if Backend still hits a "Bash hooks blocked" surface,
   investigate whether `mcp__ai_team_repo__run_shell`'s
   subprocess invocation hits a separate permission layer.
4. **`BaseAgent.llm_timeout_s` default 300 → 600 refactor**
   (deferred since iter-8). Now three iterations overdue;
   touches 5 agent files.
5. **Carry-overs unchanged from iter-10 handoff** (items
   6–13): HoldQueue persistence, `audit_writer` Postgres
   role, hash-chain alert, `GitHubTargetRepo`, TL
   transactional decomposition, `pytest-rerunfailures`
   plugin pin, `BaseAgent` template-method refactor, TL
   Backend decomposition.

## Why this demo is a net win

- **iter-10 Phase 1+2 deliverables VALIDATED IN PRODUCTION
  for the first time across ten demos.** Previous iterations
  shipped contracts behind tests but didn't have a real-LLM
  event light them up. iter-10's router was exercised by a
  real Backend MCP-race failure — the rewrite happened, the
  audit row reflects BLOCKED, the HoldQueue held QA, the
  root stayed in_progress. End to end.
- **Pattern was correctly narrow.** The `("MCP server",
  "never connected")` tuple matched Backend's real summary;
  no false positives on PM / Architect / Designer / Frontend
  done reports. The "all substrings must co-occur" pattern
  rule is doing its job.
- **The recoverable state is genuinely useful.** Pre-iter-10:
  Backend FAILED → cascade-drop → root FAILED → chain dead.
  Post-iter-10: Backend BLOCKED → dependents held → root
  in_progress → chain recoverable. iter-11 just needs to add
  the recovery action.
- **HMAC chain held through the rewrite.** The router runs
  before signing, so the chain is internally consistent —
  no `audit chain broken` warnings, no double-row hacks.
  Clean architectural property.
- **Cost stable.** $1.24 vs. iter-9 $1.23. The substring
  router itself costs zero (pure function); the chain
  shapes are converging.
- **Phase 4 mypy exclude landed quietly.** Bare
  `make typecheck` now works on demo-polluted workspaces —
  a small papercut iter-8 + iter-9 retros both flagged,
  closed permanently.

iter-10 ships with these caveats documented; iter-11's
Phase 1 lands the retry mechanism. The chain is now one
recovery-action away from `pending_review`.
