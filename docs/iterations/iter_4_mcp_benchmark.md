# MCP cold-start benchmark — iter-4

- **Date**: 2026-05-19 (iter-4 Phase 1)
- **Script**: `scripts/measure_mcp_coldstart.py`
- **Repetitions per cell**: 10
- **Servers measured**: `ai_team_bus`, `ai_team_tasks`, `ai_team_repo`
- **Repo root**: `/Users/kirillterskih/ai_team/.claude/worktrees/iter-2c`
- **Host**: darwin (Apple Silicon), Python 3.13.2, `.venv` from `uv sync`

## Numbers

Wall-clock from `asyncio.create_subprocess_exec` → first JSON-RPC
`tools/list` response containing `"tools"` on stdout.

| Server | Mode | Median (ms) | Max (ms) |
|--------|------|-------------|----------|
| ai_team_bus    | uv     |  58.6 |  67.6 |
| ai_team_bus    | direct |  42.4 |  42.8 |
| ai_team_tasks  | uv     |  57.8 |  63.0 |
| ai_team_tasks  | direct |  42.8 |  44.2 |
| ai_team_repo   | uv     |  62.1 |  71.0 |
| ai_team_repo   | direct |  45.9 |  47.9 |

**Headline**: direct-python (`.venv/bin/python -m tools.mcp_servers.<name>`)
shaves **~15–17 ms** off the median across all three servers vs
`uv run python -m …`, and **collapses the variance** (max in direct
mode is essentially the same as median; uv-run max can be 5–10 ms
above its median). The bus and tasks stubs land at **~42 ms** in
direct mode; the repo server adds a few ms for its handler imports.

## What this measures (and what it doesn't)

This benchmark times a **single sequential `tools/list` ping per fresh
subprocess**, on an otherwise idle laptop. It is a baseline, not a
production stress test. The iter-3 demo's "tools never connected"
failure ([iter_3_demo_report.md](iter_3_demo_report.md) Failure 2)
happened when `claude -p` was spawning MCP subprocesses concurrently
with the agent's own model call, on a contended machine, with the
agent's inner ToolSearch retries firing within seconds. We don't
reproduce that contention here.

What we *do* learn: even on the best-case path, `uv run` costs an
extra ~15 ms per startup. Under multi-agent load with five MCP
servers spinning up simultaneously the uv overhead compounds. Iter-4
removes that cost from the demo config; iter-5+ can layer a
long-lived MCP transport on top if cold-start still bites.

## Pass/fail gate

`scripts/measure_mcp_coldstart.py` exits **0** when every direct-mode
median is below 100 ms. Run today: **PASS** (worst direct median was
45.9 ms on `ai_team_repo`, well under the gate).

If a future change pushes any server's direct median over 100 ms the
script exits non-zero, and the failure shows up in any CI step that
runs the benchmark.

## How to re-run

```bash
uv run python scripts/measure_mcp_coldstart.py
```

No infra dependencies (Postgres / Redis not needed for the cold-start
loop; both stubs and the repo server respond to `tools/list` without
DB access). Reproducible from a clean `make dev`.

## Interpretation for iter-4 Phase 2

Direct-python median (~42–46 ms) is **comfortably inside any
reasonable `claude -p` MCP-server warmup budget**. Switching the
demo's `.iter*-mcp.json` heredoc from
`"command": "uv", "args": ["run", "python", "-m", …]` to
`"command": "${REPO_ROOT}/.venv/bin/python", "args": ["-m", …]`
removes the uv shim from the hot path without any other change. The
agents themselves remain unchanged.

## Caveats

- Numbers above are **single-machine, single-architecture**. CI
  (Linux x86_64) will have different absolute values; what should
  hold is the relative gap (`uv` slower than `direct` by a measurable
  margin, both well under 100 ms).
- The `tools/list` ping doesn't exercise tool-call handlers; a
  more thorough benchmark would call e.g. `mcp__ai_team_repo__status`
  and time the round-trip. Deferred — iter-3's failure was on
  *registration* (the inner `claude -p`'s ToolSearch didn't see the
  tools), so cold-start to first `tools/list` response is the right
  signal.
- We don't yet have a multi-process concurrent variant. If iter-4's
  demo still surfaces "tools never connected" with direct invocation
  in place, that's the next experiment.
