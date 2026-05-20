# Iter-14 real-LLM end-to-end demo — report

- **Date**: 2026-05-20 (iter-14 session)
- **Run by**: Claude (Opus 4.7) per `docs/iterations/iter_14.md`
  Phase 2
- **Script**: `AI_TEAM_DEMO_NON_INTERACTIVE=1 bash
  scripts/demo_iter_14.sh` (run #1 stopped at Architect with
  HTTP 429 session-limit; run #2 after the 12:10 MSK reset
  completed the full chain shape but landed on outcome
  4c — a FOURTH distinct Backend MCP-race phrasing the
  router still doesn't catch.)
- **Task**: idea-validator v2 (`docs/sandbox/idea_validator_v2_spec.md`)
- **Correlation IDs**:
  - Run #1: `7568ee93-2fb5-4a06-b306-e7352f1f7a71` (Architect 429)
  - Run #2: `b6e21108-2f3e-41ef-b831-c2bda9087a58` (terminal,
    outcome 4c)
- **Outcome**: **4c — Backend hit a FOURTH distinct phrasing
  the router's 6 pattern tuples (3 from iter-10, 2 from
  iter-12, 1 from iter-14) don't match.** Backend's row 201
  summary says "MCP server `ai-team-repo` **failed to
  connect**" + "tools ... were **not available** after three
  ToolSearch retries" — neither "failed to connect" nor "not
  available" is in any current tuple. iter-14's new tuple
  `("mcp__ai_team_repo", "never connected")` is correctly
  in place + unit-test-pinned (`test_routes_iter13_demo_
  backend_summary_to_blocked` passes), but the LLM picked
  yet another wording in this run. Pattern-tuple approach
  is showing diminishing returns after 5 iterations of
  one-tuple-per-iteration; iter-15 needs a bigger move.

## Verdict in one line

iter-14's deliverable shipped (one new pattern tuple +
unit test pinning iter-13 demo Backend's row 180
verbatim), but the real-LLM demo's Backend invented a
FIFTH distinct phrasing — "**failed to connect**" +
"**not available**" — that none of the six current tuples
catch. The `pending_review` loop did not close. iter-15
should take a structural move (TL Backend decomposition
OR a more general matcher), not another tuple addition.

## Run #1 — session-limit halt (Architect 429)

First run hit Anthropic's Max-5x **session limit** at
Architect's task. Authoritative signal per CLAUDE.md
("`claude -p` returns a quota-exhausted error, that is
the only authoritative signal"). Specific payload:

```
LLMInvocationError: claude -p exited 1: stderr=''
stdout='{"type":"result","subtype":"success","is_error":true,
"api_error_status":429,"duration_ms":115347,...
"result":"You've hit your session limit · resets 12:10pm
(Europe/Moscow)","stop_reason":"stop_sequence",
"session_id":"7568ee93-2fb5-4a06-b306-e7352f1f7a71",
"total_cost_usd":0.587..."}'
```

Architect's failure cascaded all dependents → no Backend
run, no MCP race, no BLOCKED. Cost: $0.59 burned on the
truncated Architect session. Run #1's audit_log rows 181-
190; Architect row 190 was a dispatcher-synthesized
`task_report(failed)` per iter-5's exception path.

After the 12:10 MSK reset cleared the cap, re-running
`make smoke-llm` reported PASS (median 5.5s). Re-launched
the demo.

## Run #2 — terminal — outcome 4c

Full chain shape executed; six task_reports landed; no
BLOCKED Backend ran, so retry-blocked was never exercised
and QA never produced a `pending_review` row.

### Chain timeline

| id  | sender             | recipient          | type            | status | blocked_on | cents | dur_ms | cached |
|-----|--------------------|--------------------|-----------------|--------|------------|-------|--------|--------|
| 191 | user               | team_lead          | task_assignment |        |            |       |        |        |
| 192 | team_lead          | broadcast          | broadcast       |        |            | 14    | 32806  | 56562  |
| 193 | team_lead          | product_manager    | task_assignment |        |            | 14    | 32806  | 56562  |
| 194 | team_lead          | architect          | task_assignment |        |            | 14    | 32806  | 56562  |
| 195 | team_lead          | backend_developer  | task_assignment |        |            | 14    | 32806  | 56562  |
| 196 | team_lead          | designer           | task_assignment |        |            | 14    | 32806  | 56562  |
| 197 | team_lead          | frontend_developer | task_assignment |        |            | 14    | 32806  | 56562  |
| 198 | team_lead          | qa_engineer        | task_assignment |        |            | 14    | 32806  | 56562  |
| 199 | product_manager    | team_lead          | task_report     | done   |            | 15    | 200479 | 224586 |
| 200 | architect          | team_lead          | task_report     | done   |            | 98    | 178865 | 251009 |
| 201 | backend_developer  | team_lead          | task_report     | failed |            | 4     | 75386  | 523633 |
| 202 | designer           | team_lead          | task_report     | done   |            | 27    | 311543 | 299750 |
| 203 | frontend_developer | team_lead          | task_report     | done   |            | 31    | 356701 | 1210298 |

QA never ran — iter-7 cascade dropped its held assignment
when Backend's row 201 landed FAILED.

### Backend row 201 verbatim summary

> "Backend Developer: tests failed. **BLOCKED — MCP server
> `ai-team-repo` failed to connect.** Tools
> `mcp__ai_team_repo__write_file_in_scope`,
> `mcp__ai_team_repo__run_shell`,
> `mcp__ai_team_repo__create_branch`, and
> `mcp__ai_team_repo__open_pr` were **not available** after
> three ToolSearch retries. Role constraints prohibit
> falling back to native Bash/Write/Edit. No code written,
> no tests run, no branch created, no PR opened.
> Resolution: ensure the `ai-team-repo` MCP server process
> is running and the `.iter14-mcp.json` config is mounted
> correctly before re-dispatching this task."

### Why no router tuple matched

The six current tuples, vs Backend's row 201 summary:

| Tuple                                          | tok1 in summary | tok2 in summary | match |
|------------------------------------------------|-----------------|-----------------|-------|
| `("MCP server", "never connected")`            | ✓               | ✗ ("failed to connect")  | NO |
| `("MCP server", "never finished connecting")`  | ✓               | ✗               | NO |
| `("MCP server", "still connecting")`           | ✓               | ✗               | NO |
| `("mcp__ai_team_repo", "unavailable")`         | ✓               | ✗ ("not available") | NO |
| `("MCP tools", "unavailable")`                 | ✗ ("Tools")     | ✗               | NO |
| `("mcp__ai_team_repo", "never connected")` ← iter-14 | ✓         | ✗               | NO |

Backend literally wrote the word "BLOCKED" in the summary
text but emitted `status="failed"` in the payload — same
shape as every prior iteration's failure. The router's job
is to map summary text → blocked_on; the LLM's
near-infinite phrasing space means each iteration's added
tuple catches the last demo's wording but not the next
one's.

### Backend's tree state on disk

`examples/sandbox/idea-validator/src/idea_validator/` +
`tests/` are still present from iter-13's `--resume`
session — same files (test_cli.py 6236 bytes,
test_pipeline_end_to_end.py 1784 bytes, etc.). Backend
didn't get far enough to modify them; the failure was at
ToolSearch startup ("after three ToolSearch retries"), so
nothing on disk changed. This means iter-15's third
attempt CAN still resume from the iter-13 implementation
state.

## What worked

1. **iter-14 unit test pins iter-13 row 180 verbatim.** The
   new tuple `("mcp__ai_team_repo", "never connected")` is
   correctly in place at
   `core/dispatcher/mcp_race_router.py:60-69` and the
   `test_routes_iter13_demo_backend_summary_to_blocked`
   test verifies it. If iter-13's wording ever reappears
   in production, the router will route to BLOCKED.
2. **iter-13's session-id collision fallback is invisible
   because no collision happened** — but the cache path
   (`_claimed_sessions`) is exercised every Backend invoke.
   No regression.
3. **5 of 7 agents shipped clean.** PM ($0.15), Architect
   ($0.98 — added ADR-0021 again), Designer ($0.27),
   Frontend ($0.31) all produced clean artifacts. The
   iter-13 problem of "Backend's `--resume` lost its
   context" doesn't recur here — Backend simply couldn't
   start.
4. **Demo script's `docker exec` fix from iter-13 worked
   cleanly.** No host-psql auth-fails (iter-13's
   `1a24699` papercut stays fixed).
5. **Outcome 4c was explicitly planned for.** The iter-14
   plan's success criterion #4c covers this exact
   eventuality, and the pattern-tuple design from iter-10
   was explicitly built to accept this kind of incremental
   addition. The plan's risk section called this out:
   "MCP race fires with a fourth distinct phrasing.
   Possible if the LLM emits yet another shape... iter-15
   adds another tuple OR moves to a more general design."

## What didn't (action items for iter-15)

### Failure 1 — A FOURTH (counting from iter-10) distinct phrasing escapes the router

After five iterations of one-tuple-per-iteration, Backend
keeps inventing new wording. iter-15 needs a **bigger
move**, not another tuple. Two candidates, in priority
order:

1. **Generalise the matcher** to a two-set cross-product:
   - MCP-token set: `{"MCP server", "MCP tools",
     "mcp__ai_team_repo", "mcp__ai_team_repo__"}`
   - Failure-verb set: `{"never connected", "never
     finished connecting", "still connecting",
     "unavailable", "not available", "failed to connect",
     "could not connect"}`
   - Match if ANY MCP-token AND ANY failure-verb appear
     in the summary. Same near-zero false-positive
     property (both groups are narrow), but covers the
     full combinatorial space.
   - Migration: keep the current `_MCP_RACE_PATTERNS` as
     a compatibility seam; add a new
     `_MCP_TOKEN_SET` + `_MCP_FAILURE_VERB_SET` matcher
     alongside; have `_matches_any_pattern` OR them.
     Unit-tests pin each iter-8/9/11/13/14 verbatim
     summary against the cross-product matcher.
2. **TL Backend decomposition** (SIX-iteration carry-over).
   Backend's monolithic task is structurally the wrong
   shape for the LLM-substrate's reliability — 5-10 min
   sessions are well inside the MCP-race window. Split
   into 2-3 chunks: "models + pipeline core", "CLI +
   factories", "tests + refresh_sample.sh". Each chunk's
   session is shorter → smaller race window per chunk
   AND independent commit per chunk. Pairs naturally with
   #1 (matcher generalisation reduces false-negatives on
   any chunk that races).

iter-15 plan should do BOTH if scope allows; if not, #1
first (small + closes the immediate gap) then #2
(structural, opens the next phase).

### Failure 2 — Architect is now $0.98 (vs $0.84 iter-13, $0.59 iter-12)

Up two iterations in a row. The handoff doc said "no
action needed unless it spikes again" — it spiked. Worth
checking what Architect produced this run that pushed cost
up (likely re-derived ADR-0021 even though it's already on
disk; the TL over-decomposition prompt-hint carry-over
becomes more urgent).

### Failure 3 — Run #1's $0.59 burned on Architect's quota-truncated session

This is a real cost of running near the session-limit
edge. The dispatcher correctly synthesized
`task_report(failed)` per iter-5's exception path, cascade
correctly dropped dependents, no data corruption. But
$0.59 is irrecoverable spend per session-limit hit. Worth
considering whether the dispatcher should check
`api_error_status=429` specifically and emit
`BLOCKED(blocked_on='budget')` instead of failed — that
would let `retry-blocked` engage automatically after
quota reset, instead of cascading the entire chain. Small
iter-15+ tuple addition (route 429 to BLOCKED). Lower
priority than #1/#2 above.

## Cost / quota

Real metrics from `metadata.llm` (run #2):

| Agent                | Model         | cost_cents | duration_ms | cached_input |
|----------------------|---------------|------------|-------------|--------------|
| TL (broadcast count once) | opus-4-7  | 14         | 32806       | 56562        |
| PM                   | sonnet-4-6    | 15         | 200479      | 224586       |
| Architect            | opus-4-7      | 98         | 178865      | 251009       |
| Designer             | sonnet-4-6    | 27         | 311543      | 299750       |
| Backend (failed)     | sonnet-4-6    | 4          | 75386       | 523633       |
| Frontend             | sonnet-4-6    | 31         | 356701      | 1210298      |
| **Run #2 total**     |               | **$1.89**  |             |              |

Plus run #1's truncated Architect: **$0.59** burned
before the 429.

**Grand total: $2.48**. Under the $5 ceiling but
expensive for a non-closing demo. iter-13 was $1.86 (same
shape, one fewer run). The $0.59 quota-truncation is the
real cost of running at the session-limit edge.

## Artifacts produced this run

- 1 root `Task` row, **status: `failed`** (iter-7 any-failed
  cascade from Backend's row 201).
- 6 child Task rows:
  - 4 `done` (PM, Architect, Designer, Frontend — all
    produced their artifacts cleanly)
  - 1 `failed` (Backend's run-#2 attempt — no on-disk
    changes since it never started)
  - 1 `in_progress` (QA — HoldQueue dropped on cascade)
- 13 audit_log rows (run #2); chain intact, HMAC valid.
- Files written (some re-derived, some unchanged from
  iter-13):
  - `docs/adr/0021-...` (Architect — re-derived; same
    content as iter-13; iter-15 prompt hint should skip
    this)
  - `docs/design/idea-validator.md` (Designer — re-derived)
  - `apps/web/idea-validator/index.html` (Frontend — 192
    lines, same shape as iter-13's 180)
  - `examples/sandbox/idea-validator/` Backend tree
    **unchanged from iter-13's `--resume` session**
    (Backend never wrote anything in this run; the tree
    is still iter-13's near-complete state).
- QA artifacts: NONE (cascade-dropped).
- Pending reviews: NONE (chain didn't reach QA).

## What this demo did NOT confirm

❌ **End-to-end chain → `pending_review`.** Fourteen demos
   in a row now. The pattern-tuple design has reached its
   limits — the LLM's natural-language variation
   outpaces incremental tuple addition. iter-15's bigger
   move (matcher generalisation + TL Backend decomposition)
   is required.

❌ **iter-14's new tuple doesn't get exercised in
   production this run.** It catches iter-13's wording but
   the LLM picked different wording this run. The tuple is
   still defensive — it WILL catch iter-13's wording if it
   reappears. Unit test pins it.

## Why this demo is still a net win

- **iter-14's tactical deliverable shipped clean.** Code
  change is correct, test pins it, all gates green. The
  pattern-tuple is a strict-superset of iter-13's matcher;
  there's no regression risk.
- **The pattern-tuple approach is empirically validated as
  diminishing-returns after 5 iterations.** Three
  iterations in a row (iter-12/13/14) added tuples; three
  iterations in a row Backend invented new wording. The
  evidence is conclusive: iter-15 needs a bigger move.
  Without this demo we'd keep doing tuple-of-the-week.
- **The cross-product matcher candidate from "Failure 1"
  is fully designed in this report.** iter-15 picks up
  the design straight from here — no further analysis
  needed for the tactical layer.
- **All non-Backend agents shipped artifacts cleanly.**
  PM/Architect/Designer/Frontend all produced their
  expected outputs. The chain machinery (TL decomposition,
  depends_on holds, audit chain, HMAC, feed publishing) is
  solid.
- **iter-13's session-id collision fallback hasn't
  regressed.** The path exists, the cache is exercised on
  every invoke (no collision happened to trigger the
  retry-with-resume branch, but the prep work is sound).
- **Cost discipline holds despite a quota-truncation.**
  $2.48 total including the $0.59 burn — within the $5
  ceiling. Future iterations: consider 429 → BLOCKED
  routing so the run-#1-style burn becomes recoverable.

## Action items for iter-15

These overlap with `iter_14_retro.md` (TBD) and
`iter_15_handoff.md` (TBD). Highest priority first:

1. **(top)** **Cross-product matcher generalisation** in
   `core/dispatcher/mcp_race_router.py`. See "Failure 1
   →option 1" above for the full design. Estimated ~30
   LOC + ~5 new unit tests pinning the four previously
   observed phrasings (iter-9/iter-11/iter-13/iter-14)
   against the generalised matcher.
2. **TL Backend decomposition** — now SIX-iteration carry-
   over. Backend's monolithic shape is structurally
   wrong for the LLM-substrate. See "Failure 1 → option 2".
3. **`api_error_status=429` → BLOCKED(blocked_on='budget')**
   routing in `ClaudeCodeHeadlessClient` or the
   dispatcher. iter-15 if scope allows.
4. **TL over-decomposition prompt hint** — Architect re-
   derived ADR-0021 in this run despite the same content
   being on disk. Cost spiked $0.84 → $0.98. Small prompt
   edit + 1 unit test.
5. **HoldQueue persistence** (Postgres-backed). iter-15
   if not blocked by #1/#2.
6. **Carry-overs unchanged**: `pytest-rerunfailures`
   plugin pin, startup-time MCP investigation,
   `audit_writer` Postgres role, hash-chain alert,
   `GitHubTargetRepo`, transactional TL, `BaseAgent`
   template refactor.
