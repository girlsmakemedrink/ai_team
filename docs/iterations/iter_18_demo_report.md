# Iter-18 real-LLM end-to-end demo — report

- **Date**: 2026-05-20 (iter-18 session, two runs)
- **Run by**: Claude (Opus 4.7) per `docs/iterations/iter_18.md`
  Phase 6
- **Script**: `AI_TEAM_DEMO_NON_INTERACTIVE=1 bash scripts/demo_iter_18.sh`
- **Task**: idea-validator v2 (clone of iter-17 demo task)
- **Correlation IDs**:
  - Run #1: `2b751729-ea76-4fab-b3a9-317a861688f0` — PM
    LLMTimeoutError at 300s, chain stalled
  - Run #2: `1d0c06f9-83c5-4b74-b307-e0e95335dab5` —
    **first `pending_review` row across 18 iterations**
    + manual `ai-team approve` close-the-loop validation
- **Outcome**: **HISTORIC FIRST — the formal owner-
  approval loop closed end-to-end**. iter-18's
  `request_human_review` MCP handler INSERTed a real
  `pending_reviews` row in run #2 (visible via
  `GET /api/reviews`); the row was then resolved to
  `approved` via `uv run ai-team approve <id>` →
  `POST /api/reviews/{id}/approve` with timestamp +
  comment persisted. **Across iter-3..17, eighteen demo
  runs reached `task_report(done)` but none ever wrote
  a `pending_reviews` row. iter-18 closes that gap.**

## Verdict in one line

**iter-18 replaces the iter-0 `request_human_review`
stub with a real handler; run #2 produced the first
formal owner-approval row across 18 iterations and the
row was successfully resolved via the existing
`/api/reviews/{id}/approve` endpoint.** Two run-quality
caveats surfaced (PM rather than QA wrote the row;
`requesting_agent='unknown'` because env-var
propagation isn't wired) but both are isolable and the
core deliverable (real row → API → approve) is
validated.

## Run #1 — PM LLMTimeoutError (no row)

Chain stalled after PM hit `LLMTimeoutError: claude -p
timed out after 300s; stdout=''`. PM's
`llm_timeout_s=300` (pinned by `test_agent_timeouts.py`
per iter-11) has been a recurring pressure point —
iter-17 run #3 saw PM at 277110ms (92% of cap). Real-
LLM variability pushed run #1 over.

Cost: **$1.75**. Audit log:

```
 270 | user            | team_lead          | task_assignment
 271 | team_lead       | broadcast          | broadcast        opus  $0.25  47s
 272 | team_lead       | product_manager    | task_assignment  opus  $0.25  47s
 273 | team_lead       | architect          | task_assignment  opus  $0.25  47s
 274 | team_lead       | backend_developer  | task_assignment  opus  $0.25  47s
 275 | team_lead       | designer           | task_assignment  opus  $0.25  47s
 276 | team_lead       | frontend_developer | task_assignment  opus  $0.25  47s
 277 | team_lead       | qa_engineer        | task_assignment  opus  $0.25  47s
 278 | product_manager | team_lead          | task_report      (failed: LLMTimeoutError 300s)
```

Cascade-drop logic correctly held all dependents
(architect/backend/designer/frontend/qa) in
`HoldQueue` since PM failed; nothing else burned LLM
quota. iter-11's `LLMTimeoutError` retry
(tenacity 3 attempts) ran through 3 timeouts.

**iter-19 candidate**: bump PM `llm_timeout_s` from
300 → 600 (matches Backend; iter-17 saw PM at 92% of
the 300s cap, this run saw it at 100%+).

## Run #2 — first `pending_review` row ever written

After PM's 17:10 MSK session window reset, restarted.
Run #2 produced the historic first.

Cost: **$1.68**. Audit log shows TL's decomposition
firing all 7 assignments (rows 279–286, all
$0.24/49s on opus); no agent task_reports captured
before the chain was killed.

**Pending_reviews row** (written during PM's
clarification work, captured via Postgres direct
query):

```
 id              | 2b260721-c3eb-4144-aee4-7b636980a799
 correlation_id  | 1d0c06f9-83c5-4b74-b307-e0e95335dab5
 task_id         | b27501fb-b783-43eb-9cb6-349c6644070e   (= PM's task_id)
 requesting_agent| unknown
 status          | pending → approved (after manual close-the-loop)
 created_at      | 2026-05-20 16:16:35.431 UTC
 resolved_at     | 2026-05-20 16:20:00.762 UTC
 resolution_comment | iter-18 demo manual approve — close-the-loop validation
 summary         | "PM clarification pass (iter-2c) for idea-validator v2:
                   task b27501fb. Stories US-1..US-6 are stable and
                   confirmed against all binding ADRs (0010..0021).
                   US-1/2/6 are Backend-executable now; ..."
```

**The MCP handler works.** The data path is end-to-end:

1. PM (running under `claude -p`) called
   `mcp__ai_team_tasks__request_human_review` via
   stdio JSON-RPC.
2. The MCP server (`tools/mcp_servers/ai_team_tasks/__main__.py`)
   dispatched to `handle_request_human_review` from
   `handlers.py`.
3. The handler INSERTed a `PendingReview` row via the
   async SQLAlchemy session.
4. `GET /api/reviews` surfaced the row (validated by
   the demo's inline `ai-team list` rich-table dump at
   step 7).
5. Manual `uv run ai-team approve 2b260721-...
   --comment "iter-18 demo manual approve …"`
   resolved the row via
   `POST /api/reviews/{id}/approve`. Row updated to
   `status='approved'` with `resolved_at` +
   `resolution_comment` persisted (verified via
   Postgres direct query above).

**This is the formal owner-approval loop closing for
the first time across 18 iterations.**

## What worked

1. **MCP handler INSERTs real rows.** Validated under
   real `claude -p` MCP stdio call — not just the 9
   sqlite unit tests + 2 Postgres testcontainers
   integration tests we wrote.
2. **API surfacing works.** `GET /api/reviews` returned
   the row; `ai-team list` rich-table dump rendered
   it; `ai-team approve <id>` resolved it.
3. **Close-the-loop path complete.** Row created →
   queried → resolved with audit trail
   (`resolved_at`/`resolution_comment`) — every step
   in ADR-001's "Human-in-the-loop checkpoints
   (`pending_review` queue) on every task
   completion" is now live infrastructure, not
   stub.
4. **Defense-in-depth fallback fired.** When the LLM
   didn't pass `agent` in args, the handler fell back
   to `ctx.default_agent` (env-sourced, default
   `"unknown"`). The row's `requesting_agent` is
   `"unknown"`, not crash. As designed.
5. **iter-17's MCP `initialize` handshake is durable.**
   PM made enough MCP calls to write the row across a
   fresh session — no "still connecting" / "never
   connected" / "unreachable" symptoms.
6. **iter-15's 429 routing didn't fire.** No quota
   burns this iteration.
7. **No regressions.** 400 unit + 50 integration
   tests still pass.

## What didn't (iter-19 carry-overs)

### Caveat 1 — PM (not QA) wrote the row

PM has `allowed_tools: ClassVar = ()`. When the
`--allowed-tools` flag is empty,
`claude_code_headless.py:199-200` skips the flag,
and `claude -p` falls back to its **permissive
default** — letting any MCP-listed tool through. PM
saw `mcp__ai_team_tasks__request_human_review`
appear in its tools/list (after iter-17 + iter-18's
schema work) and called it on its own initiative
during the clarification task.

This is structurally consistent with PM's "no
business writing files outside `docs/backlog/`"
intent but it leaks tool surface area
unintentionally. **iter-19**: harden PM allow-list
— either set an explicit non-empty `allowed_tools`
(includes the specific tools PM legitimately needs:
`Read`, `Glob`, `mcp__ai_team_bus__publish_message`)
or special-case empty as "no tools" in
`claude_code_headless.py`.

### Caveat 2 — `requesting_agent='unknown'`

The LLM didn't pass `agent="product_manager"` in the
tool args. The handler's `ctx.default_agent` is
sourced from `AI_TEAM_AGENT_ROLE` env var; the
dispatcher does NOT set this per-invocation, so it
defaults to `"unknown"`.

The plan explicitly considered this and chose the
LLM-passes-it-in-args design (deferring env
injection to iter-19). The empirical answer: LLMs
**do** forget. **iter-19**: inject
`AI_TEAM_AGENT_ROLE` (and probably
`AI_TEAM_CORRELATION_ID`) per-message in
`BaseAgent.handle()` so the handler's fallback
populates correctly.

### Caveat 3 — demo poll loop is too eager

`scripts/demo_iter_18.sh:139-149` polls every 10s
for `review_count >= 1` and breaks. This fired the
moment PM wrote its row, ~16 min into the chain —
before Architect/Backend/Designer/Frontend/QA ran.
The EXIT trap then killed the API + dispatcher
before any of them completed.

**iter-19**: poll for a SPECIFIC QA review (filter on
`requesting_agent='qa_engineer'`), or for the QA
agent's `task_report(done)` row in audit_log. The
"any pending_review" check is too coarse.

### Caveat 4 — demo's auto-approve step crashes

`scripts/demo_iter_18.sh:212-228` runs:

```bash
REVIEWS_JSON=$(curl -sf -H "Authorization: Bearer $OWNER_TOKEN" \
    http://127.0.0.1:8000/api/reviews 2>/dev/null || echo '[]')
echo "$REVIEWS_JSON" | python3 <<'PY' || true
import json, subprocess, sys
data = json.load(sys.stdin)
...
```

Run #2's actual error was
`json.decoder.JSONDecodeError: Expecting value: line 1
column 1 (char 0)` — empty stdin. The curl somehow
produced an empty string even though we know
`/api/reviews` was responding (the demo script's later
step 7 displayed the row via `ai-team list`).

The bash precedence is suspect: `$(curl ... 2>/dev/null
|| echo '[]')`. Under `set -u -o pipefail`, the
exit-code propagation might be eating the `||` branch
in some edge case. The close-the-loop validation
worked manually via
`ai-team approve <id> --comment "..."` against the
brought-back-up API. **iter-19**: tighten the
auto-approve fallback (e.g. always echo `[]` as last
resort: `R="${REVIEWS_JSON:-[]}"`).

### Caveat 5 — PM timeout at 300s remains brittle

iter-17 PM ran 277s (92% of cap). iter-18 run #1 hit
the 300s wall. **iter-19**: bump
`ProductManagerAgent.llm_timeout_s` to 600 (and
`test_agent_timeouts.py` accordingly) — matches the
LLM-bound majority. The 300s value was a pre-iter-11
optimization for the old hypothetical "PM finishes
in 150s" scenario.

## Cost / quota

| Run | Outcome                          | Cost  |
|-----|----------------------------------|-------|
| #1  | PM LLMTimeoutError 300s          | $1.75 |
| #2  | **first pending_review row ever** | $1.68 |
| **Total iter-18** |                    | **$3.43** |

**Under the $5 ceiling** despite hitting two
exploratory caveats. Below iter-17's $6.23.

## Artifacts produced this iteration

- **`tools/mcp_servers/ai_team_tasks/handlers.py`**
  (NEW, ~140 LOC): `Context` dataclass +
  `handle_request_human_review` (real INSERT) +
  stubs for `mark_task_done` / `update_task_status`
  + `HANDLERS` map.
- **`tools/mcp_servers/ai_team_tasks/__main__.py`**
  (MODIFIED, server version 0.1.0 → 0.2.0): wired
  `tools/call` async dispatch like `ai_team_repo`;
  tightened `request_human_review` inputSchema
  (`required: [summary, correlation_id]`,
  `additionalProperties: false`, typed fields).
- **`tests/unit/test_mcp_ai_team_tasks_handlers.py`**
  (NEW): 9 sqlite-backed unit tests covering happy
  path, validation errors, env-default fallback, stub
  regression.
- **`tests/unit/test_mcp_ai_team_tasks_main.py`**
  (NEW): 1 schema regression guard.
- **`tests/integration/test_mcp_ai_team_tasks_pending_review.py`**
  (NEW): 2 testcontainers-Postgres integration tests.
- **`prompts/qa_engineer.md`** (MODIFIED): added
  workflow step 4 instructing QA to call
  `request_human_review` before final JSON.
- **`scripts/demo_iter_18.sh`** (NEW, clone of
  iter-17 with iter-18 narrative) + Makefile alias.
- **`pending_reviews` row** `2b260721-c3eb-4144-aee4-7b636980a799`:
  the first formal owner-approval gate row in
  project history, written by real `claude -p` →
  MCP → SQLAlchemy → Postgres, then resolved via
  `ai-team approve`.

## Why this demo is the milestone

**Eighteen iterations chasing this**. Every iter-3..17
chain reached agent `task_report(done)` for at least
one agent (often more), but the `pending_reviews`
table stayed empty across all 18 runs because the
`mcp__ai_team_tasks__request_human_review` tool was
the iter-0 stub returning text only — never writing a
row.

iter-18 implements that handler. Run #2 wrote the
first real row; manual `ai-team approve` resolved it.
The end-to-end formal owner-approval loop — the
gate ADR-001 names as a first-class deliverable —
**is now live infrastructure rather than a stub
notebook entry**.

The remaining caveats (PM-not-QA, env-not-set, demo-
poll-eager, auto-approve-bash-bug, PM-timeout) are
real but isolable. None changes the core fact: the
INSERT works, the API surfaces it, the approve
endpoint resolves it.

## Action items for iter-19

1. **(top)** PM allow-list hardening — explicit
   `allowed_tools` so PM can't surprise-call MCP tools
   it shouldn't (Caveat 1).
2. **(top)** `AI_TEAM_AGENT_ROLE` + `AI_TEAM_CORRELATION_ID`
   per-message env injection in `BaseAgent.handle()`
   so the handler's fallback works (Caveat 2).
3. Demo poll-loop: filter on
   `requesting_agent='qa_engineer'` rather than "any
   review" (Caveat 3).
4. Demo auto-approve bash fallback fix (Caveat 4).
5. `ProductManagerAgent.llm_timeout_s` 300 → 600
   (Caveat 5; aligns with Backend / Architect /
   Designer / Frontend / DevOps).
6. **Carry-overs unchanged**: TL Backend
   decomposition (8-iter), HoldQueue persistence,
   `pytest-rerunfailures` plugin pin, agents'-branch-
   isolation investigation, TL auto-hop investigation,
   TL over-decomposition prompt hint, Architect spend
   watch, `audit_writer` Postgres role, hash-chain
   alert, `GitHubTargetRepo`, transactional TL,
   `BaseAgent` template refactor.
