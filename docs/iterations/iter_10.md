# Iteration 10 — Plan

- **Status**: Draft (awaiting owner approval)
- **Plan author**: Claude (Opus 4.7)
- **Date drafted**: 2026-05-19
- **Base commit**: `442216f` on `main` (iter-9 squash)
- **Branch**: `worktree-iter-10` (cut from `origin/main` at plan commit)
- **Anchors (do not contradict)**: ADR-001 (orchestrator),
  ADR-002 (message schema), ADR-008 (LLM access), iter-9 retro
  + demo report
- **Carry-overs addressed**: items 1–3 + 5 of
  `docs/iterations/iter_10_handoff.md` — dispatcher MCP-race
  substring router (load-bearing), Backend prompt fix
  (forbid native Bash for git/uv/make), `^examples/` mypy
  exclude, and the re-run that should finally close the
  `pending_review` loop iter-3/4/5/6/7/8/9 all reached for.
- **Deferred unchanged** (carry-over items 4 + 6–13 from
  iter-10 handoff): `BaseAgent.llm_timeout_s` default 300 →
  600 refactor, HoldQueue persistence, `audit_writer`
  Postgres role, hash-chain alert, `GitHubTargetRepo`, TL
  transactional decomposition, `pytest-rerunfailures` plugin
  pin, `BaseAgent` template-method refactor, TL Backend
  decomposition.

## Goal — one sentence

Catch the LLM's own MCP-race `task_report(failed)` summaries
in the dispatcher's outbound path, rewrite to
`BLOCKED(mcp_unhealthy)` before HMAC-sign so dependents stay
held instead of cascade-dropping, plus a Backend prompt fix
forbidding native Bash for git/uv/make commands, then re-run
the demo to finally close the `pending_review` loop.

## Success criteria (binary, measurable)

1. **`core/dispatcher/mcp_race_router.py` lands** with one
   public function:
   ```python
   def maybe_route_mcp_race_to_blocked(msg: AgentMessage) -> AgentMessage
   ```
   Returns a `model_copy` with `payload.status=BLOCKED,
   payload.blocked_on='mcp_unhealthy'` IF the message is a
   `task_report(failed)` AND its `summary` matches one of two
   known MCP-race patterns (derived verbatim from iter-8 +
   iter-9 demo Backend reports). Otherwise returns `msg`
   unchanged. 5 unit tests pin the contract.
2. **Patterns are observable + narrow.** Two literal
   substring matches, each requiring the co-occurrence of
   "MCP server" plus either "never connected" /
   "never finished connecting" / "still connecting" in the
   same summary. False-positive risk near-zero because the
   patterns name a structured infrastructure failure, not
   natural-language text. Documented in `mcp_race_router.py`'s
   module docstring with the two real-LLM examples it covers.
3. **Dispatcher wire-up is one line.** `_handle_one`'s
   `for out in outputs:` loop calls
   `out = maybe_route_mcp_race_to_blocked(out)` before
   `self._signer.with_signature(out)`. HMAC covers the
   rewritten payload; audit / feed / task_state / HoldQueue
   all see the BLOCKED version consistently — no per-callsite
   special-casing. One new integration test pins the
   end-to-end behavior: real `task_report(failed)` from a
   stub Backend with a matching summary → audit row shows
   `status=blocked, blocked_on='mcp_unhealthy'`; QA
   (depends_on=[be]) stays held in HoldQueue; root Task
   stays `in_progress`. Mirrors iter-9 Phase 3's integration
   test exactly.
4. **`prompts/backend_developer.md` updated** with an
   explicit "Critical: tool routing for git/uv/make commands"
   section directing Backend to use
   `mcp__ai_team_repo__run_shell` with its command-class enum
   for git/uv/make/pytest commands and NEVER the native
   `Bash` tool for them. One-file prompt edit; addresses the
   iter-9 demo Backend's verbatim self-admission that "the
   Bash tool requires manual approval for all git/uv/make
   commands in this session".
5. **`pyproject.toml` extends `[tool.mypy].exclude`** with
   `"^examples/"`. Symmetric with the existing ruff exclude
   per CLAUDE.md / ADR-009. Bare `make typecheck` works again
   on demo-polluted workspaces (iter-8 + iter-9 demos both
   tripped on it). One-line config edit.
6. **`scripts/demo_iter_10.sh` lands.** Clone of
   `demo_iter_9.sh` with iter-10 header (substring router +
   Backend Bash prompt fix). Same 30-min wall-clock.
   `make demo` aliases to `demo-iter-10`; iter-9/8/7/6/5/4/3/2
   stay as regression baselines. `.iter10-mcp.json` is the
   config filename.
7. **Real-LLM e2e demo reaches `pending_review` → owner
   approve.** Chain runs PM → Architect → Backend → Designer
   → Frontend → QA; QA produces a `pending_review`;
   `uv run ai-team approve <id>` completes the loop; root
   `Task` flips terminal via the iter-3 rollup. Captured in
   `docs/iterations/iter_10_demo_report.md`. **OR**: if
   Backend trips the substring router, BLOCKED routes cleanly
   (no cascade-drop); QA stays held; owner can manually
   retry and the loop closes via the BLOCKED path. **OR**:
   if a NEW failure mode appears past Backend (e.g. QA hits
   its first real-LLM failure across all ten demos), the
   report captures it and informs iter-11. Same posture as
   iter-3/4/5/6/7/8/9.
8. **All gates green**: `make lint typecheck sec test
   test-integration smoke-llm`. Bare `make typecheck` works
   without workarounds after Phase 4. Diff-cover ≥ 80 % on
   the iter-10 diff vs `origin/main`. Ruff format clean.
9. **`docs/iterations/iter_10_retro.md` + `iter_11_handoff.md`**.

## Non-goals (explicitly deferred)

- **`BaseAgent.llm_timeout_s` default 300 → 600 refactor**
  (carry-over #4). Twice deferred (iter-8, iter-9); deferred
  again to keep iter-10 narrow on the load-bearing fix. Five
  subclasses override; iter-11 work.
- **Removing `Bash` from Backend's `allowed_tools`.** Defense
  in depth on top of the prompt fix. Skipped because the
  prompt fix alone may be sufficient, and removing Bash
  entirely loses an escape hatch when the LLM legitimately
  needs to inspect environment state. iter-11 if the prompt
  fix proves insufficient.
- **Auto-retry on `BLOCKED(mcp_unhealthy)` in dispatcher.**
  Same posture as iter-6/7/8/9 budget non-goal — surface to
  owner, don't auto-retry. A per-correlation retry counter
  would need to land first.
- **Per-correlation retry counter** for any BLOCKED →
  auto-retry future work.
- **Broader MCP race patterns or regex matching.** Two
  literal substrings cover the two real-LLM observations.
  When a third shape appears, iter-N extends. Don't try to
  pre-anticipate phrasing the LLM hasn't produced.
- **Spawn-and-handshake MCP probe** (iter-9 deferred non-goal,
  still deferred).
- **HoldQueue persistence, `audit_writer` Postgres role,
  hash-chain alert, `GitHubTargetRepo`, TL transactional
  decomposition, `pytest-rerunfailures` plugin pin,
  `BaseAgent` template-method refactor, TL Backend
  decomposition.** All deferred unchanged from iter-9
  handoff.

## Decisions to confirm with owner (defaults below in **bold**)

All four pre-decided in brainstorming; recording for
plan-doc completeness.

1. **Scope?**
   - (a) Narrow — just router + demo re-run
   - (b) **Standard — router + Backend prompt + mypy exclude (recommended)**
   - (c) Bundled — above + BaseAgent timeout default refactor

   **Default: (b).** Decided in brainstorming.

2. **Router placement?**
   - (a) **Dispatcher's outbound handling, between
        `agent.handle()` and `bus.publish` (recommended)**
   - (b) BaseAgent.handle() — per-agent hook
   - (c) HoldQueue / TaskStateReducer only — don't rewrite

   **Default: (a).** Decided in brainstorming.

3. **Transform shape?**
   - (a) **Rewrite-in-place: status failed → blocked,
        blocked_on='mcp_unhealthy', keep summary verbatim (recommended)**
   - (b) Re-emit: publish failed as-is, then publish blocked
        for the same task_id
   - (c) Wrap-in-metadata: leave status=failed,
        metadata['mcp_race_detected']=true

   **Default: (a).** Decided in brainstorming.

4. **`blocked_on` value?**
   - (a) **Reuse 'mcp_unhealthy' (recommended)**: same value
        as iter-9's pre-flight gate. One MCP bucket for the
        owner.
   - (b) Introduce 'mcp_race_mid_session' — distinct value
        for analytics.

   **Default: (a).** Decided in brainstorming.

## Plan — eight phases

### Phase 0 — Branch + plan commit

`git checkout -b worktree-iter-10 origin/main` (already done).
Commit this plan as `docs(iter-10): plan`. Surface for owner
review **before** any code changes. Phase 1+ starts only
after approval. Cost: $0.

### Phase 1 — `core/dispatcher/mcp_race_router.py` + tests

**Files:**
- New: `core/dispatcher/mcp_race_router.py` (~50 LOC)
- New: `tests/unit/test_mcp_race_router.py` (~100 LOC, 5 tests)

#### 1A — Failing tests

```python
# tests/unit/test_mcp_race_router.py — new file
"""Unit tests for maybe_route_mcp_race_to_blocked.

iter-10: the LLM emits task_report(failed) when its claude -p
session's MCP subprocess fails mid-run (vs at startup, which
iter-9's pre-flight gate catches). The substring patterns
here are derived verbatim from iter-8 + iter-9 demo Backend
summaries — see iter_8_demo_report.md Failure 1 +
iter_9_demo_report.md Failure 1."""

from uuid import uuid4
import pytest

from core.dispatcher.mcp_race_router import maybe_route_mcp_race_to_blocked
from core.messaging.schemas import (
    AgentId, AgentMessage, MessageType, Priority,
    TaskAssignmentPayload, TaskReportPayload, TaskStatus,
)


def _failed_report(summary: str) -> AgentMessage:
    return AgentMessage(
        correlation_id=uuid4(),
        sender=AgentId.BACKEND_DEVELOPER,
        recipient=AgentId.TEAM_LEAD,
        message_type=MessageType.TASK_REPORT,
        priority=Priority.P1,
        payload=TaskReportPayload(
            task_id=uuid4(), status=TaskStatus.FAILED,
            progress_pct=0, summary=summary,
        ),
    )


def test_routes_iter9_demo_summary_to_blocked() -> None:
    """iter-9 demo Backend: 'MCP server ai-team-repo never
    connected, and the Bash tool requires manual approval'."""
    summary = (
        "Backend Developer: tests failed. Implemented the full "
        "pipeline. MCP server ai-team-repo never connected, "
        "and the Bash tool requires manual approval for all "
        "git/uv/make commands in this session."
    )
    out = maybe_route_mcp_race_to_blocked(_failed_report(summary))
    assert out.payload.status == TaskStatus.BLOCKED
    assert out.payload.blocked_on == "mcp_unhealthy"
    assert out.payload.summary == summary  # verbatim


def test_routes_iter8_demo_summary_to_blocked() -> None:
    """iter-8 demo Backend: 'all three ToolSearch retries
    returned still connecting'."""
    summary = (
        "Backend Developer: tests failed. Blocked: the "
        "`ai-team-repo` MCP server never finished connecting "
        "(all three ToolSearch retries returned \"still "
        "connecting\")."
    )
    out = maybe_route_mcp_race_to_blocked(_failed_report(summary))
    assert out.payload.status == TaskStatus.BLOCKED
    assert out.payload.blocked_on == "mcp_unhealthy"


def test_leaves_non_matching_failed_report_unchanged() -> None:
    """A real test failure (pytest assertion) must NOT route
    to BLOCKED — that would mask code bugs as infrastructure
    problems."""
    summary = "Backend Developer: tests failed. AssertionError in test_models.py: expected 7, got 5."
    msg = _failed_report(summary)
    out = maybe_route_mcp_race_to_blocked(msg)
    assert out is msg or (
        out.payload.status == TaskStatus.FAILED
        and out.payload.blocked_on is None
    )


def test_leaves_done_report_unchanged() -> None:
    """DONE / BLOCKED reports are not subject to rewriting,
    even if their summary happens to mention 'MCP server' in
    passing."""
    msg = _failed_report("ok")
    msg = msg.model_copy(update={
        "payload": msg.payload.model_copy(
            update={"status": TaskStatus.DONE, "summary": "MCP server connected; task done."}
        )
    })
    out = maybe_route_mcp_race_to_blocked(msg)
    assert out.payload.status == TaskStatus.DONE


def test_leaves_non_task_report_unchanged() -> None:
    """Task assignments, broadcasts, etc. pass through
    untouched even if their payload happens to contain
    matching strings."""
    msg = AgentMessage(
        correlation_id=uuid4(),
        sender=AgentId.TEAM_LEAD,
        recipient=AgentId.BACKEND_DEVELOPER,
        message_type=MessageType.TASK_ASSIGNMENT,
        priority=Priority.P2,
        payload=TaskAssignmentPayload(
            task_id=uuid4(), title="t",
            description="Implement X. MCP server should never connect.",
        ),
    )
    out = maybe_route_mcp_race_to_blocked(msg)
    assert out is msg
```

Run: expected FAIL — module doesn't exist yet.

#### 1B — Implement

```python
# core/dispatcher/mcp_race_router.py — new file
"""Substring router for LLM-emitted MCP-race task_reports.

iter-10: the iter-9 pre-flight gate catches deterministic
startup failures (module imports, env validation). But the
iter-8 + iter-9 demos showed the actual race surface is
mid-session: claude -p's MCP subprocess spawn fails AFTER
the gate's in-process probe passes. The LLM detects this
and emits a schema-valid task_report(failed) whose summary
names the failure verbatim:

  - iter-9 demo: "MCP server ai-team-repo never connected"
  - iter-8 demo: "all three ToolSearch retries returned
                  'still connecting'"

This module substring-matches those patterns and rewrites
to BLOCKED(mcp_unhealthy) so dependents stay held in the
HoldQueue (mirrors iter-6's LLMBudgetExhaustedError →
BLOCKED contract). The rewrite happens BEFORE HMAC-sign in
the dispatcher's outbound loop — audit / feed / task_state
all see one consistent BLOCKED version.

False-positive risk is near-zero because each pattern
requires the co-occurrence of "MCP server" plus a specific
failure verb — wording the LLM only produces when actually
reporting an MCP outage.
"""
from __future__ import annotations

from core.messaging.schemas import AgentMessage, TaskReportPayload, TaskStatus

# Each pattern is a tuple of substrings that must ALL appear
# in the summary for a match. Derived from iter-8 + iter-9
# demo Backend reports verbatim.
_MCP_RACE_PATTERNS: tuple[tuple[str, ...], ...] = (
    ("MCP server", "never connected"),
    ("MCP server", "never finished connecting"),
    ("MCP server", "still connecting"),
)


def maybe_route_mcp_race_to_blocked(msg: AgentMessage) -> AgentMessage:
    """If `msg` is a `task_report(failed)` whose summary
    matches an MCP-race pattern, return a copy with
    `status=BLOCKED, blocked_on='mcp_unhealthy'`. Otherwise
    return `msg` unchanged.

    Summary is preserved verbatim — the LLM's exact wording
    is the most useful diagnostic for the owner.
    """
    payload = msg.payload
    if not isinstance(payload, TaskReportPayload):
        return msg
    if payload.status != TaskStatus.FAILED:
        return msg
    summary = payload.summary or ""
    if not _matches_any_pattern(summary):
        return msg
    return msg.model_copy(
        update={
            "payload": payload.model_copy(
                update={
                    "status": TaskStatus.BLOCKED,
                    "blocked_on": "mcp_unhealthy",
                }
            )
        }
    )


def _matches_any_pattern(summary: str) -> bool:
    return any(all(tok in summary for tok in pat) for pat in _MCP_RACE_PATTERNS)
```

Run: 5 tests pass.

#### 1C — Commit

`feat(dispatcher): substring router for MCP-race task_reports`

### Phase 2 — Dispatcher wire-up + integration test

**Files:**
- Modify: `core/dispatcher/dispatcher.py` (one new line + import)
- Modify: `tests/integration/test_dispatcher_e2e.py` (1 new test)

#### 2A — Failing integration test

Mirror iter-9 Phase 3's
`test_mcp_unhealthy_emits_blocked_does_not_cascade_drop`
shape: stub Backend that returns a real
`task_report(failed)` (not raises) with a matching summary;
assert that the audit row shows BLOCKED, QA stays held, root
stays in_progress.

```python
# tests/integration/test_dispatcher_e2e.py — append after the
# iter-9 MCPUnhealthy test:

class _LLMReportsMCPRaceBackend(BaseAgent):
    """Stub Backend that returns (does not raise) a real
    task_report(failed) whose summary matches the iter-10
    MCP-race substring pattern. The dispatcher's substring
    router (iter-10 Phase 2) must rewrite to BLOCKED before
    HMAC-sign so HoldQueue holds dependents instead of
    cascade-dropping."""

    role: ClassVar[AgentId] = AgentId.BACKEND_DEVELOPER
    system_prompt_path: ClassVar[Path] = Path("/dev/null")

    def __init__(self) -> None:
        self._cached_prompt: str | None = None

    def system_prompt(self) -> str:
        return "# stub\n"

    async def handle(self, msg: AgentMessage) -> list[AgentMessage]:
        return [
            AgentMessage(
                correlation_id=msg.correlation_id,
                sender=self.role,
                recipient=AgentId.TEAM_LEAD,
                message_type=MessageType.TASK_REPORT,
                priority=Priority.P1,
                payload=TaskReportPayload(
                    task_id=msg.payload.task_id,
                    status=TaskStatus.FAILED,
                    progress_pct=0,
                    summary=(
                        "Backend Developer: tests failed. "
                        "MCP server ai-team-repo never "
                        "connected. Owner action needed."
                    ),
                ),
            )
        ]

    def build_outputs(self, response: LLMResponse, incoming: AgentMessage) -> list[AgentMessage]:
        del response, incoming
        return []


async def test_mcp_race_summary_rewrites_to_blocked_does_not_cascade(
    redis_url, session_factory, db_session,
) -> None:
    """Real task_report(failed) with MCP-race summary → router
    rewrites to BLOCKED → HoldQueue holds QA → root stays
    in_progress. Same outcome shape as the iter-9
    MCPUnhealthyError → BLOCKED test, exercising the
    substring-router code path instead of the exception path.
    See iter_10.md success criterion #3."""
    # ... (mirror iter-9 Phase 3 test setup using
    #      _LLMReportsMCPRaceBackend instead of
    #      _MCPUnhealthyBackend)
    # Assertions:
    #   - audit row 1 (Backend's report) has status=blocked,
    #     blocked_on='mcp_unhealthy'
    #   - HoldQueue still holds QA
    #   - root Task stays in_progress
```

Run: expected FAIL — dispatcher publishes the LLM's
`task_report(failed)` as-is, which cascade-drops QA.

#### 2B — Implement

```python
# core/dispatcher/dispatcher.py — add import
from core.dispatcher.mcp_race_router import maybe_route_mcp_race_to_blocked

# in _handle_one, inside `for out in outputs:` loop, BEFORE
# self._signer.with_signature(out):
            for out in outputs:
                # iter-10: route LLM-emitted MCP-race failures
                # to BLOCKED so dependents stay held instead of
                # cascade-dropping. Pure pass-through for
                # non-matching messages. See
                # iter_9_demo_report.md Failure 1 +
                # iter_10.md success criterion #3.
                out = maybe_route_mcp_race_to_blocked(out)
                signed = self._signer.with_signature(out)
                # ... rest unchanged
```

Run: new integration test passes; iter-9's
`test_mcp_unhealthy_emits_blocked_does_not_cascade_drop`
stays green (different code path); all existing dispatcher
tests stay green.

#### 2C — Commit

`feat(dispatcher): rewrite MCP-race task_reports to BLOCKED before HMAC-sign`

### Phase 3 — Backend prompt: forbid native Bash for git/uv/make

**Files:**
- Modify: `prompts/backend_developer.md` (prepend one section)

No tests — prompt edits are behavior changes the LLM
interprets; the real-LLM demo is the test.

#### 3A — Edit

Prepend at the top of the system prompt (or just after the
role banner — pick the highest-visibility location):

```markdown
## Critical: tool routing for git / uv / make / pytest commands

You have access to `mcp__ai_team_repo__run_shell` which
accepts a `command_class` enum covering exactly the operations
you need: `git_status`, `git_add`, `git_commit`,
`git_push_feature`, `gh_pr_create`, `make_test`, `pytest`,
`ruff`, `mypy`. **Use this tool for ALL git / uv / make /
pytest commands**. Do NOT use the native `Bash` tool for
them — it requires manual approval that won't be granted in
autonomous sessions, so the work will silently stall.

If you need a shell operation outside this enum, surface that
gap in your `task_report.summary` and report `blocked` rather
than reaching for raw Bash.
```

(Final wording may adjust during implementation for tone
parity with the rest of the prompt.)

#### 3B — Commit

`feat(prompts): backend — forbid native Bash for git/uv/make`

### Phase 4 — `^examples/` mypy exclude

**Files:**
- Modify: `pyproject.toml` (one list element)
- Modify: existing `make typecheck` may need verification
  (currently `mypy .`; after the exclude, `mypy .` should
  work without `--exclude '^examples/'`)

#### 4A — Edit

```toml
# pyproject.toml — extend the existing exclude list
[tool.mypy]
python_version = "3.11"
strict = true
plugins = ["pydantic.mypy"]
exclude = ["^alembic/versions/", "^build/", "^dist/", "^examples/"]
```

#### 4B — Verify

`make typecheck` (the bare form, no `--exclude` workaround)
should pass on a demo-polluted workspace. The verification is
mechanical — no new test file.

#### 4C — Commit

`build(mypy): exclude examples/ to match the ruff exclusion`

### Phase 5 — Demo wall + `scripts/demo_iter_10.sh`

**Files:**
- Create: `scripts/demo_iter_10.sh` (clone of iter-9)
- Modify: `Makefile`

#### 5A — Clone and re-header

Fork `scripts/demo_iter_9.sh`. Differences:
- Header rewritten for iter-10 (substring router + Backend
  prompt fix)
- Same `deadline=$((SECONDS + 1800))` (30 min)
- Config filename: `.iter10-mcp.json`
- Task title: "iter-10 demo: idea-validator v2 …"

#### 5B — Makefile alias

```makefile
demo: demo-iter-10 ## Alias for the current iteration's demo
demo-iter-10: ## Run iter-10 e2e (substring router + Backend Bash prompt fix)
	bash scripts/demo_iter_10.sh
demo-iter-9: ## Run iter-9 e2e — regression baseline
	bash scripts/demo_iter_9.sh
# (iter-8..2 stay unchanged.)
```

Add `demo-iter-10` to the `.PHONY` list.

#### 5C — Commit

`chore(demo): demo_iter_10.sh — substring router + Backend Bash prompt fix`

### Phase 6 — Real-LLM e2e demo

Cost budget: ~$1.50 expected (cache hot from iter-9; Backend
should now succeed if MCP cooperates, or BLOCKED cleanly if
not), $5 ceiling.

| # | Task | Output |
|---|------|--------|
| 6A | Pre-flight: `.env`, `docker info`, `claude --version`, `gh auth status`, `make smoke-llm` PASS | terminal capture |
| 6B | `AI_TEAM_DEMO_NON_INTERACTIVE=1 bash scripts/demo_iter_10.sh` | chain runs PM → Architect → Backend → Designer → Frontend → QA; pending_review row appears |
| 6C | `uv run ai-team list-pending` → capture review row; `uv run ai-team approve <id> --comment "iter-10 demo close-out"` | review approved |
| 6D | Single SQL query → per-agent table with metrics | per-agent table |
| 6E | Write `docs/iterations/iter_10_demo_report.md` | committed report |

**If Backend trips the substring router** (MCP race
happens again), QA stays held under BLOCKED; owner manually
retries or fixes; loop closes via the BLOCKED path. This is
the second valid terminal state per success criterion #7.

**If a NEW failure mode appears past Backend** (QA hits
its first real-LLM failure across ten demos), capture in
report and inform iter-11. Same posture as iter-3/4/5/6/7/8/9.

### Phase 7 — Validation gates + retro + iter-11 handoff

| # | Task | Output |
|---|------|--------|
| 7A | `make lint typecheck sec test test-integration smoke-llm` all green (typecheck WITHOUT `--exclude` workaround thanks to Phase 4) | terminal |
| 7B | `uv run ruff format --check .` clean | terminal |
| 7C | Diff-cover ≥ 80 % on iter-10 diff vs `origin/main` | coverage report |
| 7D | `docs/iterations/iter_10_retro.md` | committed retro |
| 7E | `docs/iterations/iter_11_handoff.md` | committed handoff |
| 7F | Open PR; squash-merge once CI green via `gh api -X PUT .../merge -f merge_method=squash` | merged PR; main at iter-10 squash |

## Risk register

- **False positive: a legitimate failure summary contains
  one of the patterns.** Mitigated by requiring co-occurrence
  of "MCP server" plus a specific failure verb. The patterns
  are derived from two real-LLM observations; pre-anticipating
  phrasing the LLM hasn't produced would balloon scope. If a
  false positive appears in a future demo, iter-11 tightens
  the patterns or moves to a regex.
- **Pattern brittleness: future LLM updates phrase failures
  differently.** Acceptable — when a new shape appears,
  demo report captures it and iter-11 extends the patterns.
  Same posture as iter-8's "BLOCKED detector substring match
  derived from real-LLM stdout" decision.
- **Backend prompt fix doesn't fully prevent Bash use.**
  Prompts are advisory; the LLM may still reach for Bash on
  edge cases. Defense in depth (removing Bash from
  `allowed_tools`) is iter-11 if needed.
- **Mypy exclude could mask real type errors in shared code
  agents touch.** The `examples/sandbox/idea-validator/`
  workspace is owned by Backend agent; we don't run its mypy.
  Acceptable per ADR-009 (`examples/` is TARGET_REPO scope).
- **NEW failure mode in QA.** QA hasn't run to completion
  across nine demos. iter-10's success criterion #7 explicitly
  allows the demo report capturing a QA-side failure.
- **`make typecheck` mid-flight on Phase 1-3 may still fail**
  if Phase 4 hasn't landed yet. Mitigation: use
  `uv run mypy --exclude '^examples/' .` for inter-phase
  verification, switch back to bare `make typecheck` after
  Phase 4.

## Cost projection

| Phase | Type | Estimate |
|-------|------|----------|
| 0     | docs | $0 |
| 1     | code + 5 unit tests | $0 |
| 2     | code + 1 integration test | $0 |
| 3     | prompt edit | $0 |
| 4     | config one-liner | $0 |
| 5     | shell + Makefile | $0 |
| 6     | real-LLM demo | ~$1.50 expected, $5 ceiling |
| 7     | docs + CI | $0 |
| **Total** | | **~$1.50 expected, $5 ceiling** |

Quota check before Phase 6. iter-8 spent $1.13, iter-9 $1.23;
iter-10 may come in lower if cache stays hot AND chain
completes faster (BLOCKED path is cheap), or land near $2-3
if Backend's full v2 implementation finally runs to completion.

## Workflow

- Plan-before-code: this file lands as commit 1; no Phase-1+
  code until owner approves.
- Conventional commits; squash-merge on the iter-10 PR.
- Each phase's "Commit" row is one (and only one) commit.
- Run `make lint sec test` **and** `uv run ruff format
  --check .` after each phase. For typecheck before Phase 4:
  `uv run mypy --exclude '^examples/' .`; from Phase 4
  onwards: `make typecheck`.
- Final demo report goes in the same PR.

## Ready-to-paste prompt for iter-11

Lives in `docs/iterations/iter_11_handoff.md` (Phase 7E).
