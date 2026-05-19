"""Benchmark MCP server cold-start latency (uv run vs direct python).

Runs `tools/list` against each of ai_team_bus, ai_team_tasks,
ai_team_repo via both invocation modes. Reports median + p95.

Usage: uv run python scripts/measure_mcp_coldstart.py
"""

from __future__ import annotations

import asyncio
import json
import os
import statistics
import sys
import time
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
    if b'"tools"' not in stdout:
        raise RuntimeError(f"server didn't respond: {stdout!r}")
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
    print("# MCP cold-start benchmark\n")
    print(f"- Repetitions per cell: {N_REPETITIONS}")
    print(f"- Repo root: {REPO_ROOT}")
    print(f"- Servers: {', '.join(SERVERS)}\n")
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
