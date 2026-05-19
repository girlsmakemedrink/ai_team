# Iteration 8 — Plan

- **Status**: Draft (awaiting owner approval)
- **Plan author**: Claude (Opus 4.7)
- **Date drafted**: 2026-05-19
- **Base commit**: `4f0971e` on `main` (iter-7 squash)
- **Branch**: `worktree-iter-8` (cut from `origin/main` at plan commit)
- **Anchors (do not contradict)**: ADR-001 (orchestrator), ADR-006
  (model tier per agent), ADR-008 (LLM access), iter-7 retro +
  demo report
- **Carry-overs addressed**: items 1–4 of
  `docs/iterations/iter_8_handoff.md` — bump Designer's
  `llm_timeout_s`, fix `_is_budget_exhausted_stdout` against
  truncated JSON, modest sonnet budget bump, and the re-run that
  should finally close the `pending_review` → owner approve loop
  iter-3/4/5/6/7 all reached for.
- **Deferred unchanged** (carry-over items 5–13 from iter-8
  handoff): HoldQueue persistence, `audit_writer` Postgres role,
  hash-chain alert, `GitHubTargetRepo`, TL transactional
  decomposition, `pytest-rerunfailures` pin, `BaseAgent`
  template-method refactor, pre-flight MCP health-gate. Plus the
  optional `BaseAgent.llm_timeout_s` default 300→600 structural
  refactor — see decision #2 below.

## Goal — one sentence

Close the iter-7 demo's two narrow failure modes — Designer's
300 s timeout and the `LLMBudgetExhaustedError` BLOCKED detector
defeated by the adapter's 2 KB stdout cap — then re-run end-to-
end through `pending_review` → owner approve, the loop
iter-3/4/5/6/7 all reached for.

## Success criteria (binary, measurable)

1. **Designer's per-call `llm_timeout_s` raised to 600 s.** New
   `ClassVar[int] = 600` override in `agents/designer/agent.py`
   matching Architect / Backend / Frontend / DevOps. Unit test
   pins the value.
2. **`_is_budget_exhausted_stdout` uses substring-only match.**
   Detector returns True when the marker substring
   `error_max_budget_usd` appears in stdout, regardless of
   whether the surrounding JSON parses. False-positive risk is
   near-zero because the marker is a structured response field,
   not natural-language text. Flips the iter-6
   `test_is_budget_exhausted_stdout_robust_against_truncated_json`
   contract from "False on truncated JSON" to "True on truncated
   JSON when marker present". Adds a regression test for the
   "no marker → False" path.
3. **Adapter stdout cap raised from 2 KB → 8 KB.** Memory cost
   trivial; defense-in-depth on top of #2 + better structlog
   diagnostics. One-line change in
   `core/llm/claude_code_headless.py`. Unit test pins the new cap
   (longest plausible `claude -p` response JSON is ~3-4 KB, so
   8 KB has comfortable headroom).
4. **Sonnet `--max-budget-usd` default raised $1.50 → $2.50.**
   Backend hit $1.50 cap at 11 turns in iter-7 demo; $2.50
   provides ~18 turns of headroom. Haiku + opus unchanged. Unit
   test pin updated.
5. **`scripts/demo_iter_8.sh` lands.** Clone of `demo_iter_7.sh`
   with iter-8 header (Designer 600 s + BLOCKED detector fix +
   sonnet $2.50). Same 30-min wall-clock. `make demo` aliases to
   `demo-iter-8`; iter-7/6/5/4/3/2 demos stay as regression
   baselines.
6. **Real-LLM e2e demo reaches `pending_review` → owner approve.**
   Chain runs PM → Architect → Backend → Designer → Frontend →
   QA; QA produces a `pending_review`; `uv run ai-team approve
   <id>` completes the loop; root `Task` flips terminal via the
   iter-3 rollup. Captured in
   `docs/iterations/iter_8_demo_report.md`. **OR**: if a NEW
   failure mode appears, the report captures it and informs
   iter-9. Same posture as iter-3/4/5/6/7.
7. **All gates green**: `make lint typecheck sec test
   test-integration smoke-llm`. Diff-cover ≥ 80 % on the iter-8
   diff vs `origin/main`. Ruff format clean.
8. **`docs/iterations/iter_8_retro.md` + `iter_9_handoff.md`**.

## Non-goals (explicitly deferred)

- **In-adapter auto-retry on budget exhaustion.** Same posture
  as iter-6/7 non-goal. iter-8 still surfaces BLOCKED to the
  owner. Now that the detector finally works, this becomes a
  more attractive iter-9+ project — but auto-retry doubles
  worst-case spend on a stuck loop, so it stays deferred until
  a per-correlation retry counter exists.
- **TL auto-router for `BLOCKED(budget_exhausted)`.** Same
  posture as iter-6/7.
- **HoldQueue persistence to Postgres.** Still iter-9+.
- **`audit_writer` restricted Postgres role.** Still deferred
  from iter-2/3/4/5/6/7.
- **Hash-chain alert job.** Still deferred.
- **`GitHubTargetRepo` implementation.** Waiting on first
  commercial product.
- **TL transactional decomposition.** Still deferred.
- **`pytest-rerunfailures` plugin pin.** iter-7 saw the
  testcontainers race once; one retry passed. Defer pinning
  until it bites in CI, not just local.
- **`BaseAgent.handle()` template-method refactor.** Defer until
  a new agent rolls in.
- **Pre-flight MCP health-gate.** Iter-4's direct-python is
  enough; defer until a future demo trips on it.

## Decisions to confirm with owner (defaults below in **bold**)

1. **Designer timeout value?**
   - (a) **600 s (recommended)**: matches Architect / Backend /
        Frontend / DevOps. iter-7 demo Designer timed out at
        300 s. 600 s gives 2× headroom while still bounding
        worst-case wall-clock.
   - (b) 900 s: bigger margin, but Designer's work is
        comparable to Architect's (5:18 in iter-7) — 600 s
        already covers it.

   **Default: (a).**

2. **`BaseAgent.llm_timeout_s` default — bump 300 → 600 now, or
   defer?**
   - (a) **Defer to iter-9 (recommended)**: keep iter-8 narrow
        on Designer alone. Five subclasses already explicitly
        override (Architect, Backend, Frontend, DevOps, plus
        Designer after #1); only PM, QA, SRE, MarketResearcher,
        TL inherit. iter-9 can refactor structurally once the
        loop is closed.
   - (b) Bump now + remove redundant per-subclass overrides:
        cleaner end state but touches 5 agent files in iter-8.

   **Default: (a).** Closes the loop faster; structural fix is
   iter-9 work.

3. **`_is_budget_exhausted_stdout` strategy?**
   - (a) **Substring-only match (recommended)**: return True
        iff `"error_max_budget_usd" in out`. Robust to
        truncation, the load-bearing fix. False-positive risk
        near-zero (the marker is a structured response field).
   - (b) Try JSON parse first, fall back to substring on
        decode error: belt + suspenders. Same observable
        behavior as (a) when the parse fails; slightly more
        code.

   **Default: (a).** Simpler, observable behavior is identical
   for the failure mode iter-8 is targeting.

4. **Sonnet `--max-budget-usd` value?**
   - (a) **$2.50 (recommended)**: modest bump from iter-6's
        $1.50. Backend hit $1.50 at 11 turns; $2.50 gives
        ~18 turns of headroom, which should comfortably cover a
        full v2 implementation + commit + open PR.
   - (b) $3.00: bigger margin, but the iter-7 Backend was 22 KB
        into output at $1.50 — $2.50 should be enough; $3.00
        opens a larger runaway-loop blast radius.
   - (c) $2.00: tighter, safer. Risk: Backend may hit it again
        if v2 implementation is longer than the iter-7 trace
        suggests.

   **Default: (a).** Pairs with the BLOCKED detector fix: even
   if Backend exhausts $2.50, the failure now routes to BLOCKED
   + owner manual retry, not FAILED + cascade-drop. Defense in
   depth.

## Plan — seven phases

### Phase 0 — Branch + plan commit

`git checkout -b worktree-iter-8 origin/main` (already done).
Commit this plan as `docs(iter-8): plan`. Surface for owner
review **before** any code changes. Phase 1+ starts only after
approval. Cost: $0.

### Phase 1 — Designer `llm_timeout_s` = 600 s

**Files:**
- Modify: `agents/designer/agent.py` (add ClassVar override)
- Test: `tests/unit/test_designer_agent.py` (new test)

#### 1A — Failing pin test

```python
# tests/unit/test_designer_agent.py — append
def test_llm_timeout_s_is_600_for_designer() -> None:
    """Designer's per-call timeout must be 600 s (matches
    Architect / Backend / Frontend / DevOps). iter-7 demo Designer
    timed out at the 300 s BaseAgent default on the v2 UX brief +
    landing-page wireframe task. See iter_7_demo_report.md
    Failure 1 + iter_8.md decision #1."""
    from agents.designer import DesignerAgent
    assert DesignerAgent.llm_timeout_s == 600
```

Run: expected FAIL — Designer currently inherits the 300 s default.

#### 1B — Implement

```python
# agents/designer/agent.py — add ClassVar near the other ClassVars
# (next to allowed_tools / model_tier):
    # iter-8: UX brief + wireframe drafting on the v2 task
    # reliably takes 3-5 min on Sonnet; the 300 s BaseAgent
    # default timed out in the iter-7 demo. Match Architect /
    # Backend / Frontend / DevOps.
    llm_timeout_s: ClassVar[int] = 600
```

Run: test passes.

#### 1C — Commit

`feat(designer): raise llm_timeout_s to 600s`

### Phase 2 — `_is_budget_exhausted_stdout` substring-only + stdout cap

The detector fix + cap bump ride together because they're
defense-in-depth for the same failure mode.

**Files:**
- Modify: `core/llm/claude_code_headless.py` (substring match +
  cap)
- Test: `tests/unit/test_claude_code_headless.py` (flip
  truncation test + add no-marker pin)

#### 2A — Flip existing truncation test + add no-marker pin

The iter-6 test `test_is_budget_exhausted_stdout_robust_against_truncated_json`
currently pins "False on truncated JSON" — iter-8 flips this to
"True on truncated JSON when marker present" and adds a no-marker
regression test.

```python
# tests/unit/test_claude_code_headless.py — REPLACE existing
# test_is_budget_exhausted_stdout_robust_against_truncated_json:
def test_is_budget_exhausted_stdout_matches_truncated_marker() -> None:
    """The 2 KB stdout cap (or any future smaller cap) can leave
    the response JSON incomplete; iter-8 detects budget
    exhaustion by substring match alone so a truncated body
    still routes to BLOCKED. iter-6 demo Failure 2 / iter-7
    demo Failure 2 (the BLOCKED branch failed its first
    real-LLM test because the JSON was truncated). See
    iter_8.md Phase 2."""
    from core.llm.claude_code_headless import _is_budget_exhausted_stdout

    truncated = '{"type":"result","subtype":"error_max_budget_usd","usage":{"input'
    assert _is_budget_exhausted_stdout(truncated) is True

    # Substring without surrounding JSON also matches — the marker
    # is the load-bearing signal.
    assert _is_budget_exhausted_stdout("garbled output: error_max_budget_usd") is True


def test_is_budget_exhausted_stdout_returns_false_without_marker() -> None:
    """No marker → never True. Guards against widening the
    detector to false positives on unrelated subtypes."""
    from core.llm.claude_code_headless import _is_budget_exhausted_stdout

    assert _is_budget_exhausted_stdout("plain stdout, no marker") is False
    assert _is_budget_exhausted_stdout('{"subtype":"rate_limited"}') is False
    assert _is_budget_exhausted_stdout("") is False
```

Run: expected FAIL — current implementation requires a
successful `json.loads(out)` and returns False on the truncated
body.

#### 2B — Cap-bump test

```python
# tests/unit/test_claude_code_headless.py — append
@pytest.mark.asyncio
async def test_invoke_captures_up_to_8kb_of_stdout_on_non_zero_exit() -> None:
    """iter-8 bumps the stdout cap from 2 KB → 8 KB so real-LLM
    error JSONs (up to ~3-4 KB in practice) fit without
    truncation. See iter_8.md Phase 2."""
    client = ClaudeCodeHeadlessClient()
    big_stdout = b"x" * 4096 + b"error_max_budget_usd in here at byte 4096"

    class _FailingProc:
        returncode = 1
        async def communicate(self) -> tuple[bytes, bytes]:
            return big_stdout, b""

    async def _fake_create(*_cmd: str, **_kwargs: Any) -> _FailingProc:
        return _FailingProc()

    with (
        patch(
            "core.llm.claude_code_headless.asyncio.create_subprocess_exec",
            new=AsyncMock(side_effect=_fake_create),
        ),
        pytest.raises(LLMBudgetExhaustedError),
    ):
        await client.invoke(system_prompt="sp", user_message="u", model="sonnet")
```

Run: expected FAIL — 2 KB cap drops the marker at byte 4096.

#### 2C — Implement

```python
# core/llm/claude_code_headless.py — replace
# _is_budget_exhausted_stdout:
def _is_budget_exhausted_stdout(out: str) -> bool:
    """Return True iff `out` contains the
    `subtype=error_max_budget_usd` marker from `claude -p`.

    iter-8: substring-only match. The 2-8 KB stdout cap can
    leave the response JSON incomplete; iter-6's
    JSON-parse-required version returned False on truncation,
    which defeated the BLOCKED branch in the iter-7 demo
    (Failure 2). The marker is a structured response field —
    not natural-language text — so false-positive risk is
    near-zero.
    """
    return "error_max_budget_usd" in out
```

```python
# core/llm/claude_code_headless.py — bump cap from [:2000] to
# [:8000] in the non-zero-exit branch:
            out = stdout.decode(errors="replace")[:8000]
```

Run: 3 new tests pass; existing tests still pass.

#### 2D — Commit

`fix(llm): substring-match error_max_budget_usd + 8KB stdout cap`

### Phase 3 — Sonnet `--max-budget-usd` $1.50 → $2.50

**Files:**
- Modify: `core/llm/base.py` (one value in the dict)
- Test: `tests/unit/test_llm_base.py` (update pin)

#### 3A — Update pin test

```python
# tests/unit/test_llm_base.py — REPLACE the iter-6 pin:
def test_default_budget_per_tier_matches_iter8_values() -> None:
    """Pin the iter-8 budget caps so a future tightening surfaces
    in review with reasoning. Sonnet raised $1.50 → $2.50 after
    iter-7 demo Backend hit $1.50 at 11 turns. See
    iter_7_demo_report.md Failure 3 + iter_8.md decision #4."""
    assert DEFAULT_MAX_BUDGET_USD_PER_TIER == {
        "haiku": 0.30,
        "sonnet": 2.50,
        "opus": 4.00,
    }
```

Rename: drop the old `test_default_budget_per_tier_matches_iter6_values`
function (its contract is superseded). Keep the test name
clean — single iter-N pin per iteration.

Run: expected FAIL — current value is `sonnet: 1.50`.

#### 3B — Implement

```python
# core/llm/base.py — bump sonnet in DEFAULT_MAX_BUDGET_USD_PER_TIER:
DEFAULT_MAX_BUDGET_USD_PER_TIER: dict[ModelTier, float] = {
    "haiku": 0.30,
    "sonnet": 2.50,
    "opus": 4.00,
}
```

Run: test passes.

#### 3C — Commit

`feat(llm): raise sonnet --max-budget-usd $1.50 → $2.50`

### Phase 4 — Demo wall + `scripts/demo_iter_8.sh`

**Files:**
- Create: `scripts/demo_iter_8.sh` (clone of iter-7)
- Modify: `Makefile`

#### 4A — Clone and re-header

Fork `scripts/demo_iter_7.sh`. Differences:
- Header rewritten for iter-8 (Designer 600 s + BLOCKED detector
  substring + sonnet $2.50)
- Same `deadline=$((SECONDS + 1800))` (30 min)
- Config filename: `.iter8-mcp.json`
- Task title: "iter-8 demo: idea-validator v2 …"

#### 4B — Makefile alias

```makefile
demo: demo-iter-8 ## Alias for the current iteration's demo
demo-iter-8: ## Run iter-8 e2e (Designer 600s + substring BLOCKED detector + sonnet $2.50)
	bash scripts/demo_iter_8.sh
demo-iter-7: ## Run iter-7 e2e — regression baseline
	bash scripts/demo_iter_7.sh
# (iter-6 / iter-5 / iter-4 / iter-3 / iter-2 stay unchanged.)
```

Add `demo-iter-8` to the `.PHONY` list.

#### 4C — Commit

`chore(demo): demo_iter_8.sh — Designer 600s + BLOCKED detector + sonnet $2.50`

### Phase 5 — Real-LLM e2e demo

Cost budget: ~$3.50 expected (Backend now actually completes
under $2.50; Designer completes under 600 s; Frontend completes;
QA reports), $5.00 ceiling. Higher than iter-7 because the chain
runs all the way.

| # | Task | Output |
|---|------|--------|
| 5A | Pre-flight: `.env`, `docker info`, `claude --version`, `gh auth status`, `make smoke-llm` PASS, quota check | terminal capture |
| 5B | `AI_TEAM_DEMO_NON_INTERACTIVE=1 bash scripts/demo_iter_8.sh` | chain runs PM → Architect → Backend → Designer → Frontend → QA; pending_review row appears |
| 5C | `uv run ai-team list-pending` → capture review row; `uv run ai-team approve <id> --comment "iter-8 demo close-out"` | review approved |
| 5D | Single SQL query → per-agent table with metrics for every row | per-agent table |
| 5E | Write `docs/iterations/iter_8_demo_report.md` | committed report |

**If the chain still breaks** mid-run (a NEW failure mode under
iter-8's fixes), the report captures it and informs iter-9. Same
posture as iter-3/4/5/6/7: don't paper over.

### Phase 6 — Validation gates + retro + iter-9 handoff

| # | Task | Output |
|---|------|--------|
| 6A | `make lint typecheck sec test test-integration smoke-llm` all green | terminal |
| 6B | `uv run ruff format --check .` clean | terminal |
| 6C | Diff-cover ≥ 80 % on iter-8 diff vs `origin/main` | coverage report |
| 6D | `docs/iterations/iter_8_retro.md` — what shipped, what didn't, surprises, stats | committed retro |
| 6E | `docs/iterations/iter_9_handoff.md` — carry-overs, hard constraints, ready-to-paste prompt | committed handoff |
| 6F | Open PR; squash-merge once CI green via `gh api -X PUT .../merge -f merge_method=squash` (worktree can't `gh pr merge`) | merged PR; main at iter-8 squash |

## Risk register

- **Sonnet $2.50 lets a runaway loop burn more quota.** Worst-
  case pre-iter-8: $1.50 × stuck call. Post-iter-8: $2.50.
  Acceptable. Per-agent `llm_timeout_s` (now 600 s on Backend /
  Frontend / DevOps / Architect / Designer) bounds wall-clock,
  and the BLOCKED-on-exhaustion routing (now actually working
  per Phase 2) surfaces stuck loops to the owner instead of
  cascading drops.
- **Substring-only detector false-positives** on unrelated stdout
  that happens to contain "error_max_budget_usd". Mitigated by
  the marker being a structured response field. If a future
  agent's prompt or tool output ever includes the literal
  string, the detector would misfire — at which point we'd
  switch to a regex on `"subtype":"error_max_budget_usd"`.
- **8 KB stdout cap still too small** if a future `claude -p`
  release adds verbose fields. Acceptable — substring detector
  doesn't depend on the cap; the cap only affects diagnostic
  richness in structlog + exception messages.
- **NEW failure mode emerges past Designer + Backend**.
  Frontend, QA haven't run to completion across six demos —
  may surface their own timeout or budget gaps. Captured in
  the demo report; iter-9 picks them up.
- **Test name churn** in `test_default_budget_per_tier_matches_iter6_values`
  → `_iter8_values`. Pre-existing iter-6 → iter-7 pattern (the
  iter-6 test would be misnamed if kept). One-time rename;
  iter-9+ should renumber freely.

## Cost projection

| Phase | Type | Estimate |
|-------|------|----------|
| 0     | docs | $0 |
| 1     | code + 1 unit test | $0 |
| 2     | code + 3 unit tests | $0 |
| 3     | code + 1 unit test | $0 |
| 4     | shell + Makefile | $0 |
| 5     | real-LLM demo | ~$3.50 expected, $5.00 ceiling |
| 6     | docs + CI | $0 |
| **Total** | | **~$3.50 expected, $5.00 ceiling** |

Quota check before Phase 5. iter-6 demo spent $0.21, iter-7
$3.60; iter-8 may spend close to the ceiling if the full chain
runs.

## Workflow

- Plan-before-code: this file lands as commit 1; no Phase-1+
  code until owner approves the plan.
- Conventional commits; squash-merge on the iter-8 PR.
- Each phase's "Commit" row is one (and only one) commit.
- Run `make lint typecheck sec test` **and** `uv run ruff format
  --check .` after each phase to keep the branch shippable.
- Final demo report goes in the same PR.

## Ready-to-paste prompt for iter-9

Lives in `docs/iterations/iter_9_handoff.md` (Phase 6E).
