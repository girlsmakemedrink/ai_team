# Iteration 24 — close QA criterion via Backend stability

> **Status**: DRAFT — surfacing for owner review while
> Phase 1 A/B test runs in parallel (decisive empirical).
> **Branch**: `worktree-iter-24` (cut from `ae6023b`).
> **Predecessor**: `iter_23_retro.md` + `iter_24_handoff.md`.
> **Scope**: tightly focused — make the upstream chain
> reliable enough that QA's turn runs, so the
> already-shipped iter-23 safety net can land the
> 5-iteration-deferred criterion row in a real demo.

## TL;DR

iter-23 closed the **structural** side of the QA blocker
(safety net proven 3/3 in isolation: `tests/integration/
test_qa_request_human_review_real_llm.py`). Two full-chain
demo runs failed at Backend with two distinct upstream
defects. iter-24 closes both, plus the open A/B research
question, plus the demo log preservation gap.

**Ordered by impact**:

1. **TL summary-prefix scope detection** replaces the fragile
   `blocked_on` routing. Backend's prompt template guarantees
   "Scope pre-flight:" appears at the start of `summary` when
   the LLM self-ejects. That structural prefix is a more
   reliable signal than `blocked_on` (a semantic field the LLM
   keeps elaborating into).

2. **Backend prompt: create missing target dir, don't self-eject.**
   iter-23 R#1's Backend blocked partly because `examples/` was
   absent from main. Backend has write tools; missing target is
   not a scope problem, it's a "first commit creates the dir"
   problem. Prompt edit + pin test.

3. **A/B enum-vs-permissive `--json-schema` mini-test.**
   Verifies iter-23 R#2's enum-retry-loop budget-burn theory
   ($0.20, 10 min). Closes the open research question; result
   becomes a CLAUDE.md gotcha or ADR-008 update.

4. **Demo EXIT trap: preserve API log** to
   `docs/iterations/iter_24_demo_logs/${CORRELATION}.log` for
   forensic value (iter-23 lost both runs' logs).

5. **Re-attempt full real-LLM demo** with all above in place.
   Expect the QA-emitted `pending_reviews` row criterion to
   finally land (5-iter deferred).

## Goals

1. **(P0)** Land a `pending_reviews` row with
   `requesting_agent='qa_engineer'` in the iter-24 real-LLM
   demo — **5-iteration deferred** (iter-19 → 20 → 21 → 22 →
   23).
2. **(P0)** Backend self-eject's recovery path is robust to
   LLM elaboration (TL routes via summary prefix, not
   `blocked_on`).
3. **(P0)** Backend doesn't self-eject when the only "missing
   files" are the target directory it's supposed to create.
4. **(P1)** Confirm or deny the `--json-schema` enum-retry-loop
   theory empirically. Document outcome.
5. **(P1)** Demo API logs preserved for post-mortem.

## Non-goals

- Removing the iter-21 Python tripwire (defense-in-depth).
- Removing the iter-23 TL substring matcher (belt-and-suspenders
  alongside #1).
- Reworking the iter-23 safety net (proven correct).
- Touching any iter-22 contract layer.
- Carry-overs ≥5 in iter-24_handoff (HoldQueue persistence,
  GitHubTargetRepo, BaseAgent refactor, etc.) — explicitly
  deferred.

## Phases

### Phase 0 — Plan + branch ✅ (in flight)

- [x] Cut `worktree-iter-24` from `origin/main` (`ae6023b`).
- [ ] Write this plan.
- [ ] Surface to owner; proceed in parallel with Phase 1
  diagnostic.

### Phase 1 — A/B `--json-schema` enum-vs-permissive

**Hypothesis**: `claude -p` with `--json-schema` containing an
`enum` constraint, when fed a prompt where the LLM wants to
fill the field with an out-of-enum value, retries internally
until the per-call `max_budget_usd` cap fires
`LLMBudgetExhaustedError`. iter-23 R#2's Backend BLOCKED(budget)
(no `metadata.llm`, audit row 369/371) is the symptom.

**Method**: a real-LLM unit test running TWO `claude -p`
invocations with the same prompt but different schemas:
- A: `{"properties": {"category": {"type": "string", "enum":
  ["alpha","beta"]}}}`
- B: `{"properties": {"category": {"type": "string"}}}`

User prompt for both: "Fill `category` with a multi-word
descriptive label for: 'a complex hybrid edge case'."

Capture both responses' `cost_estimate_cents`, `duration_ms`,
`tokens_in`, `tokens_out`, `validated_against_schema`, and
whether `LLMBudgetExhaustedError` raised.

**Decision rule**:
- A's duration > 5× B's, or A's cost > 3× B's, or A raises
  `LLMBudgetExhaustedError` → **theory CONFIRMED**.
- Otherwise → **theory DENIED**; we have a different budget-burn
  cause to chase later.

**Files**: `tests/integration/test_json_schema_enum_retry_loop.py`
(real_llm, integration markers).

**Cost**: ~$0.20. **Wall-clock**: ~5-10 min.

### Phase 2 — TL summary-prefix scope detection

The iter-22 Backend prompt template (lines 22-31, line 25
specifically) guarantees BLOCKED responses start `summary`
with the literal string "Scope pre-flight:". This is
structurally enforced by the prompt and is a more reliable
routing signal than `blocked_on`.

**Change**: `_maybe_route_blocked` in `agents/team_lead/agent.py`:
- Detect `summary.startswith("Scope pre-flight")` as the
  canonical self-eject signal (regardless of `blocked_on`
  content).
- Keep the iter-23 substring match on `blocked_on` for legacy
  in-flight messages.
- Both paths feed into `_re_decompose_on_too_large(msg)`.

**TDD**:
- Test: Backend BLOCKED with `summary="Scope pre-flight: 4 files / 250 LOC estimated"`
  and `blocked_on="something else entirely"` → TL routes to
  re-decomposition.
- Test: Backend BLOCKED with `summary` not starting with the
  prefix and `blocked_on="legit_other_block"` → TL does NOT
  hit the re-decomposition path.
- Regression: existing iter-21 / iter-23 substring tests still
  pass.

**Files**:
- Modify: `agents/team_lead/agent.py`
- Modify: `tests/unit/test_team_lead_agent.py`

### Phase 3 — Backend prompt: handle missing target dir

**Problem (iter-23 R#1)**: Backend self-ejected mentioning
"examples/ is untracked in iter-2c and absent from main." It
treated a missing target directory as a scope problem. That's
incorrect — Backend has `mcp__ai_team_repo__write_file_in_scope`
and is supposed to CREATE the target structure as part of its
first commit.

**Change**: add a "Target directory handling" section to
`prompts/backend_developer.md` near the Scope pre-flight:
> "If your target directory is absent (e.g.,
> `examples/sandbox/<project>/` doesn't yet exist), this is
> NORMAL for a first task. CREATE the directory and its
> initial scaffolding as part of your work via
> `mcp__ai_team_repo__write_file_in_scope`. Do not self-eject
> just because the directory is empty or untracked. Self-eject
> only when the implied scope itself exceeds 2 files / 200 LOC."

**TDD**:
- Pin test: prompt contains the missing-dir guidance.

**Files**:
- Modify: `prompts/backend_developer.md`
- Modify: `tests/unit/test_backend_developer_agent.py` (1 pin test)

### Phase 4 — Demo script: preserve API log + clone

**Problem**: iter-23's `_cleanup_iter23` EXIT trap did
`rm -f "$API_LOG"`. Both demo runs lost the `claude -p`
substrate log; the BLOCKED(budget) theory couldn't be
empirically verified.

**Change**: clone `scripts/demo_iter_23.sh` →
`scripts/demo_iter_24.sh`. Update EXIT trap to MOVE the API
log to `docs/iterations/iter_24_demo_logs/${CORRELATION:0:8}.log`
instead of deleting it. Create the directory in the trap
(idempotent).

Also: Makefile `demo` target repointed to iter-24.

**Files**:
- Create: `scripts/demo_iter_24.sh`
- Modify: `Makefile`
- Comment-warn: `scripts/demo_iter_23.sh` as HISTORICAL

### Phase 5 — Validation gates

- `uv run pytest tests/unit -q` (target 443+ pass)
- `TESTCONTAINERS_RYUK_DISABLED=true uv run pytest
  tests/integration -q -m "integration and not real_llm"`
- `uv run ruff check . && uv run ruff format --check .`
- `uv run mypy .`
- `make sec` (bandit High=0 per ADR-005)
- `make smoke-llm`

### Phase 6 — Real-LLM demo

`AI_TEAM_DEMO_NON_INTERACTIVE=1 bash scripts/demo_iter_24.sh`.

**Acceptance** (in order of importance):
1. ≥1 row in `pending_reviews` with
   `requesting_agent='qa_engineer'`. **5-iter-deferred
   criterion finally met**.
2. Chain shape: PM/Architect/Designer/Frontend DONE, Backend
   either DONE or BLOCKED + re-decomp → DONE, QA → row.
3. Cost: under $5.
4. Wall-clock: under 45 min (the 15-min retry should not be
   needed with Phase 2's robust routing).

**Caveats expected, not blockers**:
- Frontend BLOCKED on architecturally-prohibited POST /analyze
  (iter-21/22/23 pattern, spec-correct refusal).
- Backend may self-eject once; iter-23 substring + iter-24
  prefix matching both fire, TL re-decomposes, Backend's
  smaller subtask runs and DONEs.

### Phase 7 — Retro + iter-25 handoff + PR

Standard: `iter_24_demo_report.md` + `iter_24_retro.md` +
`iter_25_handoff.md`. Commit, push, PR via `gh api -X PUT`
(iter-22 gotcha), CI green, merge.

## Risks + mitigations

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| TL summary-prefix detection false-positives | Low | Prefix is a literal-template artifact; only Backend's prompt produces it; check exact case (case-sensitive). |
| Backend prompt edit prompts LLM to skip self-eject for genuine scope problems | Low | Self-eject rule for >2 files / >200 LOC stays; only the "missing dir" exception is added. |
| A/B test inconclusive (both runs similar) | Medium | If neither path triggers budget burn or significant divergence, theory is denied; document and remove the iter-23 "enum suspected" caveat from CLAUDE.md note. Continue without the lesson. |
| Demo R#3 fails for a NEW reason | Medium | Forensic log now preserved; iter-25 has data to work with. The safety net is the gate; partial chain still demonstrates value. |
| Cost overrun | Low | A/B ~$0.20 + demo ~$2.50 = ~$2.70 expected. Budget $5. |

## Hard constraints (unchanged from iter-23)

All carry forward. iter-24 additions:
- TL `_maybe_route_blocked` checks summary-prefix AND
  blocked_on substring (layered).
- Backend prompt explicitly tells the LLM that missing target
  dir is not a scope problem.
- Demo EXIT trap moves API logs to
  `docs/iterations/iter_24_demo_logs/`.

## Cost / time

| Phase | Cost | Time |
|-------|-----:|-----:|
| 0 Plan | $0 | 20 min |
| 1 A/B | ~$0.20 | 10 min |
| 2 TL prefix | $0 | 25 min |
| 3 Backend prompt | $0 | 15 min |
| 4 Demo script | $0 | 15 min |
| 5 Gates | $0 | 10 min |
| 6 Demo | ~$2.50 | 45 min |
| 7 Retro + PR | $0 | 30 min |
| **Total** | **~$2.70** | **~2.8 h** |
