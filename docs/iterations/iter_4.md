# Iteration 4 — Plan

- **Status**: Draft (awaiting owner approval)
- **Plan author**: Claude (Opus 4.7)
- **Date drafted**: 2026-05-19
- **Base commit**: `8de6a0a` on `main` (iter-3 squash)
- **Branch**: `worktree-iter-4` (cut from `origin/main` at plan commit)
- **Anchors (do not contradict)**: ADR-001 (orchestrator), ADR-004
  (per-agent tool allowlist), ADR-008 (LLM access), iter-3 retro +
  demo report
- **Carry-overs addressed**: items 1–3 of
  `docs/iterations/iter_4_handoff.md` (MCP cold-start, TL spurious
  `depends_on`, demo re-run)
- **Deferred unchanged**: HoldQueue persistence (#4),
  `audit_writer` Postgres role (#5), hash-chain alert (#6),
  `GitHubTargetRepo` (#7), TL transactional decomposition (#8),
  pytest-rerunfailures pin (#9), TL `tokens_out` under-reporting
  investigation (iter-3 demo action #4 — defer to iter-5 unless cost
  drift > 20 %)

## Goal — one sentence

Close the iter-3 demo's two failure modes — Backend's MCP "tools
never connected" abort and the TL's spurious `depends_on=[backend,
design]` on Frontend — and re-run the full chain through to
`pending_review`, owner approval, and a green-path
`docs/iterations/iter_4_demo_report.md`.

## Success criteria (binary, measurable)

1. **MCP server invocation no longer goes through `uv run`.** All
   MCP server entries in demo configs and any in-code defaults use
   `$(pwd)/.venv/bin/python -m tools.mcp_servers.<name>` (or
   equivalent absolute Python path). Verified by `make demo` output
   and by `scripts/measure_mcp_coldstart.py` showing < 100 ms median
   cold-start.
2. **`scripts/measure_mcp_coldstart.py` lands** as a small standalone
   measurement script and runs in CI (or at least is invokable
   locally), so the regression iter-3 demo surfaced is now
   inspectable on demand. Generates a markdown table identical in
   shape to `docs/iterations/iter_0_smoke_report.md`.
3. **TL system prompt teaches conservative `depends_on`.** Updated
   text explicitly forbids "speculative" dependencies and adds a
   self-check sentence. A unit test pins the rule wording (snapshot
   test) so future edits don't silently revert it.
4. **TL emits a per-decomposition DAG preview to the team_feed.**
   When TL build_outputs runs, it publishes one `BROADCAST`-typed
   message with a Markdown rendering of the planned DAG, **before**
   the per-subtask assignments hit the bus. Owner can see in
   `ai-team watch` what the plan looks like seconds before agents
   start. Not a gate — informational. (Iter-4 default #1 — see below.)
5. **`scripts/demo_iter_4.sh` lands** as a near-clone of
   `demo_iter_3.sh` but pointing at the same v2 spec (no further
   spec changes). Wall-clock stays at 20 min.
6. **Real-LLM e2e demo runs through to a `pending_review` row**
   created by QA, with the per-message SQL query showing rows for
   every recipient (PM, Architect, Backend, Designer, Frontend, QA).
   `tasks.status` for the root flips from `in_progress` to `done`
   via the iter-3 rollup. Owner approves the QA review via
   `uv run ai-team approve <id>`. Captured in
   `docs/iterations/iter_4_demo_report.md`.
7. **All gates green**: `make lint typecheck sec test
   test-integration smoke-llm`. Diff-cover ≥ 80 %.
8. **`docs/iterations/iter_4_retro.md` + `iter_5_handoff.md`**.

## Non-goals (explicitly deferred)

- **Long-lived MCP server processes** (Unix sockets / SSE
  transport). Stays as iter-5+ work. The direct-python invocation
  in iter-4 is enough to drop cold start from ~400 ms to ~50 ms.
- **Pre-flight MCP health-gate in the dispatcher.** Skip unless the
  iter-4 demo still surfaces "tools never connected" — measurement
  data + direct python should obviate it.
- **HoldQueue persistence.** Still iter-5.
- **`audit_writer` Postgres role.** Still iter-5.
- **Hash-chain alert job.** Still iter-5.
- **`GitHubTargetRepo`** — waiting on first commercial product.
- **TL `tokens_out` under-reporting recalibration.** Iter-3 demo
  flagged TL Opus reporting `tokens_out=76` (anomalously low). Defer
  until either the next demo shows the same pattern or quota drift
  > 20 % (CLAUDE.md guidance).
- **`pytest-rerunfailures` plugin pin.** The testcontainers race
  hasn't bitten in iter-3; defer.

## Decisions to confirm with owner (defaults below in **bold**)

1. **DAG preview to team_feed: in iter-4 or defer?** A small
   `CheckpointDigestPayload` or `BroadcastPayload` emitted by TL
   alongside the sub-task assignments gives the owner a one-glance
   plan view. Cheap to ship (~30 LOC). **Default: ship in iter-4 as
   a BROADCAST message; owner sees it in `ai-team watch`.** The
   alternative (defer) leaves the iter-3 spurious-depends_on failure
   mode invisible until after agents start working.
2. **Direct-python invocation: hardcode `.venv/bin/python` or
   resolve dynamically?** The demo scripts write the MCP config
   from a heredoc; we can expand `$(pwd)/.venv/bin/python` at
   script time. **Default: hardcode `$(pwd)/.venv/bin/python` in
   demo scripts.** No core-code change; per-platform alternatives
   live in the script. The dispatcher itself doesn't generate MCP
   configs.
3. **TL prompt rule wording — "literally cannot start without"?**
   Phrase candidates:
     (a) "ONLY when the recipient literally cannot start without the
        predecessor's artifact"
     (b) "ONLY for hard data dependencies; use [] when in doubt"
     (c) "ONLY when the predecessor produces an artifact the
        recipient must read; otherwise []"
   **Default: (a)** — most concrete. Self-check sentence appended:
   "Before emitting, audit each `depends_on` entry: would the
   recipient genuinely fail without this predecessor? If unsure,
   delete it."

## Plan — six phases

### Phase 0 — Branch + plan commit

`git checkout -b worktree-iter-4 origin/main` (already done as part
of plan drafting). Commit this plan as `docs(iter-4): plan`.
Surface for owner review **before** any code changes. Phase 1+
starts only after approval. Cost: $0.

### Phase 1 — MCP cold-start measurement (data first)

Lands a small benchmark script + a one-pager report. **Goal: make
the iter-3 demo's "tools never connected" failure measurable on
demand**, so iter-4's fix has data to compare against and iter-5+
has a regression baseline.

**Files:**
- Create: `scripts/measure_mcp_coldstart.py`
- Create: `docs/iterations/iter_4_mcp_benchmark.md`

```python
# scripts/measure_mcp_coldstart.py — ~80 LOC
"""Benchmark MCP server cold-start latency (uv run vs direct python).

Runs `tools/list` against each of ai_team_bus, ai_team_tasks,
ai_team_repo via both invocation modes. Reports median + p95.

Usage: uv run python scripts/measure_mcp_coldstart.py
"""
from __future__ import annotations
import asyncio, json, os, statistics, subprocess, sys, time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SERVERS = ("ai_team_bus", "ai_team_tasks", "ai_team_repo")
N_REPETITIONS = 10
PING_LINE = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}) + "\n"


async def _run_one(cmd: list[str], env: dict[str, str]) -> float:
    start = time.perf_counter()
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
        env=env,
    )
    stdout, _ = await proc.communicate(PING_LINE.encode())
    duration = time.perf_counter() - start
    assert b'"tools"' in stdout, f"server didn't respond: {stdout!r}"
    return duration * 1000  # ms


async def _bench(mode: str, server: str) -> tuple[float, float]:
    if mode == "uv":
        cmd = ["uv", "run", "python", "-m", f"tools.mcp_servers.{server}"]
    elif mode == "direct":
        cmd = [str(REPO_ROOT / ".venv" / "bin" / "python"), "-m", f"tools.mcp_servers.{server}"]
    else:
        raise ValueError(mode)
    env = {**os.environ, "AI_TEAM_REPO_ROOT": str(REPO_ROOT), "AI_TEAM_PATH_PREFIXES": "*"}
    times = [await _run_one(cmd, env) for _ in range(N_REPETITIONS)]
    return statistics.median(times), max(times)


async def main() -> int:
    print(f"# MCP cold-start benchmark\n")
    print("| Server | Mode | Median (ms) | Max (ms) |")
    print("|--------|------|-------------|----------|")
    fail = False
    for server in SERVERS:
        for mode in ("uv", "direct"):
            med, mx = await _bench(mode, server)
            print(f"| {server} | {mode} | {med:.1f} | {mx:.1f} |")
            if mode == "direct" and med > 100:
                fail = True
    if fail:
        print("\n**FAIL**: direct-python median > 100 ms.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
```

| # | Task | Files | Cost |
|---|------|-------|------|
| 1A | Write `scripts/measure_mcp_coldstart.py` (code above) | `scripts/measure_mcp_coldstart.py` | $0 |
| 1B | Run it; capture output into `docs/iterations/iter_4_mcp_benchmark.md` | docs | $0 |
| 1C | Commit `feat(scripts): MCP cold-start benchmark` | git | $0 |

### Phase 2 — Switch MCP configs to direct-python invocation

Each MCP config heredoc in `scripts/demo_iter_*.sh` uses `uv run
python`. Replace with `$(pwd)/.venv/bin/python` for the three
servers. Single commit; touches only demo scripts.

**Files:**
- Modify: `scripts/demo_iter_3.sh` (the iter-3 script we forked)
- Create: `scripts/demo_iter_4.sh` (clone of demo_iter_3.sh with the
  config diff applied)
- Modify: `Makefile` (alias `demo` → `demo-iter-4`)

#### 2A — Pre-flight check

Run `./.venv/bin/python --version` and confirm the binary exists.
Skip the phase if not.

#### 2B — Write `scripts/demo_iter_4.sh`

Fork `demo_iter_3.sh` verbatim, then in the heredoc that writes
`.iter4-mcp.json`, replace each entry:

```bash
# BEFORE (demo_iter_3.sh):
"ai-team-bus": {
  "command": "uv",
  "args": ["run", "python", "-m", "tools.mcp_servers.ai_team_bus"]
}

# AFTER (demo_iter_4.sh):
"ai-team-bus": {
  "command": "${REPO_ROOT}/.venv/bin/python",
  "args": ["-m", "tools.mcp_servers.ai_team_bus"]
}
```

Apply the same swap for `ai-team-tasks` and `ai-team-repo`. Rename
the config file from `.iter3-mcp.json` → `.iter4-mcp.json` (and
the env var name from `AI_TEAM_MCP_CONFIG_PATH` stays unchanged —
just the on-disk file name changes).

#### 2C — Makefile update

```makefile
demo: demo-iter-4 ## Alias for the current iteration's demo

demo-iter-4: ## Run iter-4 e2e (direct-python MCP, depends_on DAG preview)
	bash scripts/demo_iter_4.sh

demo-iter-3: ## Run iter-3 e2e — regression baseline (uv-run MCP)
	bash scripts/demo_iter_3.sh
```

`demo-iter-3` and `demo-iter-2` stay for regression.

#### 2D — Commit

`chore(demo): direct-python MCP invocation; demo_iter_4.sh`

### Phase 3 — TL `depends_on` discipline

Tighten the TL system prompt + pin the rule in a unit test.

**Files:**
- Modify: `prompts/team_lead.md`
- Modify: `tests/unit/test_team_lead_agent.py` (add snapshot test)

#### 3A — Failing snapshot test

```python
# tests/unit/test_team_lead_agent.py — append
def test_tl_prompt_includes_conservative_depends_on_rule() -> None:
    """Pin the iter-4 rule wording so a future prompt edit doesn't
    silently revert the discipline. See iter_3_demo_report.md Failure 3."""
    prompt_path = TeamLeadAgent.system_prompt_path
    text = prompt_path.read_text()
    # Concrete phrases the iter-4 wording must contain.
    assert "literally cannot start without" in text, (
        "TL prompt must teach conservative depends_on — see iter_4.md Phase 3"
    )
    assert "Before emitting, audit each `depends_on` entry" in text
```

Run: `pytest tests/unit/test_team_lead_agent.py::test_tl_prompt_includes_conservative_depends_on_rule -v`
Expected: FAIL with `AssertionError`.

#### 3B — Update `prompts/team_lead.md`

Replace the existing `depends_on` section (currently encouraging
"liberal" use) with:

```markdown
- `depends_on` lists the slugs of other subtasks in **this same
  decomposition** that must finish (TASK_REPORT status=`done`) before
  the recipient may start. The orchestrator holds dependent
  assignments off the bus until their predecessors report done — you
  do **not** need to add "wait for X" to descriptions.
- Declare a predecessor in `depends_on` **ONLY when the recipient
  literally cannot start without the predecessor's artifact** —
  e.g. "Backend depends_on Architect" because Backend reads the ADR;
  "QA depends_on Backend" because QA tests the implementation. If
  the recipient can produce something useful without that artifact,
  leave `depends_on=[]`.
- An incorrect `depends_on` causes the recipient to be needlessly
  delayed or **dropped** on a failure cascade (any failed predecessor
  drops the dependent). When in doubt, omit.
- **Before emitting, audit each `depends_on` entry**: would the
  recipient genuinely fail without this predecessor? If unsure,
  delete it.
- **Cycles and forward references**: a slug in `depends_on` must
  exist somewhere in the same `subtasks` array, but list order
  doesn't matter. Cycles produce undefined behavior — don't emit
  them.
```

#### 3C — Test passes; full suite still green

Run: `make test-unit` + `make typecheck`.
Expected: 298 + 1 = 299 unit tests pass; mypy clean.

#### 3D — Commit

`feat(tl): tighten depends_on prompt — only declare hard dependencies`

### Phase 4 — TL decomposition DAG preview to team_feed

Owner sees the plan in `ai-team watch` seconds before agents start
working. Catches a wrong DAG before it commits resources.

**Files:**
- Modify: `agents/team_lead/agent.py`
- Modify: `tests/unit/test_team_lead_agent.py`

#### 4A — Failing unit test

```python
# tests/unit/test_team_lead_agent.py — append
def test_build_outputs_emits_dag_preview_broadcast() -> None:
    """TL's outputs include exactly one BROADCAST message describing
    the planned DAG, alongside the per-subtask assignments."""
    agent = TeamLeadAgent(llm=_StubLLM())
    incoming = _incoming_task()
    plan = {
        "summary": "test plan",
        "subtasks": [
            {"id": "arch", "recipient": "architect", "title": "T",
             "description": "D", "priority": "P2", "depends_on": []},
            {"id": "be", "recipient": "backend_developer", "title": "T",
             "description": "D", "priority": "P2", "depends_on": ["arch"]},
        ],
    }
    outputs = agent.build_outputs(_stub_llm_response(plan), incoming)

    # Exactly one BROADCAST + N task_assignments.
    broadcasts = [o for o in outputs if o.message_type == MessageType.BROADCAST]
    assignments = [o for o in outputs if o.message_type == MessageType.TASK_ASSIGNMENT]
    assert len(broadcasts) == 1
    assert len(assignments) == 2

    preview = broadcasts[0].payload
    assert isinstance(preview, BroadcastPayload)
    assert preview.topic == "tl.dag_preview"
    # The DAG renders arch and be with the dependency relationship.
    assert "arch" in preview.body
    assert "be" in preview.body
    assert "depends_on" in preview.body or "→" in preview.body
```

Run: `pytest tests/unit/test_team_lead_agent.py::test_build_outputs_emits_dag_preview_broadcast -v`
Expected: FAIL (no broadcast output).

#### 4B — Implement DAG preview emission

```python
# agents/team_lead/agent.py — after the build_outputs loop, before return:
def _render_dag_markdown(self, subtasks: list[dict[str, object]]) -> str:
    """Render a one-paragraph plan summary + per-subtask depends_on lines."""
    lines: list[str] = ["## Decomposition plan"]
    for sub in subtasks:
        slug = sub.get("id", "?")
        recipient = sub.get("recipient", "?")
        deps = sub.get("depends_on") or []
        deps_str = f" depends_on=[{', '.join(deps)}]" if deps else ""
        title = str(sub.get("title", ""))[:80]
        lines.append(f"- **{slug}** → `{recipient}`{deps_str}: {title}")
    return "\n".join(lines)


# In build_outputs, after the per-subtask AgentMessage loop:
outputs.insert(0, AgentMessage(
    correlation_id=incoming.correlation_id,
    sender=AgentId.TEAM_LEAD,
    recipient=AgentId.BROADCAST,
    message_type=MessageType.BROADCAST,
    priority=Priority.P3,
    payload=BroadcastPayload(
        topic="tl.dag_preview",
        body=self._render_dag_markdown(subtasks),
    ),
    metadata={"parent_task_id": str(incoming.payload.task_id)},
))
```

Need to import `BroadcastPayload` in `agents/team_lead/agent.py`.

#### 4C — Re-run the existing test + new test; both pass

The existing `test_build_outputs_emits_one_message_per_subtask` test
needs an update — it currently asserts `len(outputs) == 2` for two
subtasks. With the preview, length is 3. Update the assertion:

```python
# Update assertion in the existing test:
# Before:
assert len(outputs) == 2
# After:
task_assignments = [o for o in outputs if o.message_type == MessageType.TASK_ASSIGNMENT]
assert len(task_assignments) == 2
```

Run: `pytest tests/unit/test_team_lead_agent.py -v`. Expected:
all 15 tests pass (14 existing + 1 new).

#### 4D — Commit

`feat(tl): emit DAG preview broadcast alongside sub-task assignments`

### Phase 5 — Real-LLM e2e demo run

Cost budget: ~$1.20 expected (six agents + TL + cleared earlier
failures should let the chain run); $3.00 ceiling for one debug
retry. Higher than iter-3 because the chain runs to completion
this time.

| # | Task | Output |
|---|------|--------|
| 5A | Pre-flight: `.env`, `docker info`, `claude --version`, `gh auth status`, `make smoke-llm` green, `uv run python scripts/measure_mcp_coldstart.py` PASS | terminal capture in report appendix |
| 5B | `AI_TEAM_DEMO_NON_INTERACTIVE=1 bash scripts/demo_iter_4.sh` | chain runs PM → Architect → Backend → Designer → Frontend → QA; pending_review row appears |
| 5C | `uv run ai-team list-pending` → capture review row; `uv run ai-team approve <id> --comment "iter-4 demo close-out"` | review approved |
| 5D | Single SQL query → per-agent table for the report | per-agent table |
| 5E | Write `docs/iterations/iter_4_demo_report.md` | committed report |

**If the chain breaks** mid-run, the report captures the failure
mode and informs iter-5 priorities — same posture as iter-3. Do not
paper over real failures.

### Phase 6 — Validation gates + retro + iter-5 handoff

| # | Task | Output |
|---|------|--------|
| 6A | `make lint typecheck sec test test-integration smoke-llm` all green | local terminal |
| 6B | Diff-cover ≥ 80 % on the iter-4 diff vs `origin/main` | coverage report |
| 6C | `docs/iterations/iter_4_retro.md` — what shipped, what didn't, surprises, action items, stats | committed retro |
| 6D | `docs/iterations/iter_5_handoff.md` — carry-overs, hard constraints, ready-to-paste prompt | committed handoff |
| 6E | Open PR; squash-merge once CI green (self-approve per CLAUDE.md "dev-PR" layer) | merged PR; main at iter-4 squash |

## Risk register

- **Direct-python invocation breaks on CI** if `.venv/bin/python`
  isn't at the expected path. Mitigation: demo scripts run locally
  only; CI exercises unit + integration tests, not the demo
  scripts.
- **Backend's "tools never connected" reproduces even with
  direct-python**. Then we don't yet understand the failure mode.
  Fall-back: capture the demo failure in the report and bump
  pre-flight MCP health-gate into iter-4 scope (Phase 5 contingency
  task).
- **TL still emits spurious depends_on under the new prompt.** Real
  LLMs sometimes ignore explicit rules. Fall-back: surface the DAG
  preview (Phase 4) which gives the owner a chance to abort before
  agents commit resources. Iter-5 might add an "owner override"
  knob.
- **DAG preview broadcast confuses the existing feed consumers.**
  `ai-team watch` already handles `BROADCAST` messages (renders
  generic). No code change needed in watch. Worst case the message
  is ignored by older consumers.
- **Diff-cover dips below 80 %.** The TL prompt snapshot test
  contributes coverage; the DAG-preview tests add more. If we drop
  below the gate, add a test for the `_render_dag_markdown` helper
  directly.

## Cost projection

| Phase | Type | Estimate |
|-------|------|----------|
| 0     | docs | $0 |
| 1     | benchmark script + report | $0 (no LLM calls) |
| 2     | shell scripts + Makefile | $0 |
| 3     | prompt + unit test | $0 |
| 4     | code + unit tests | $0 |
| 5     | real-LLM demo | ~$1.20 expected, $3.00 ceiling |
| 6     | docs + CI | $0 |
| **Total** | | **~$1.20 expected, $3.00 ceiling** |

Well under monthly quota budgets (cost is in subscription dollars,
not API dollars). Quota check before Phase 5 same as iter-3.

## Workflow

- Plan-before-code: this file lands as commit 1; no Phase-1+ code
  until owner approves the plan.
- Conventional commits; squash-merge on the iter-4 PR.
- Each phase's "Commit" row in tables above is one (and only one)
  commit.
- Run `make lint typecheck sec test` after each phase to keep the
  branch shippable mid-flight.
- Final demo report goes in the same PR.

## Ready-to-paste prompt for iter-5

Lives in `docs/iterations/iter_5_handoff.md` (Phase 6D).
