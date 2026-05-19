"""Pre-flight health check for ai-team MCP servers.

iter-9: the iter-8 demo surfaced an MCP-server connect race
inside Backend's `claude -p` session (all three ToolSearch
retries returned "still connecting"). This module catches the
deterministic startup failures — module import errors and
`Context.from_env` env-validation failures — in-process before
claude -p ever spawns the MCP subprocess, so failures route
to BLOCKED(mcp_unhealthy) + owner manual retry instead of
FAILED + cascade-drop. Stdio-handshake races are NOT caught;
iter-10's planned substring router on the failure summary
covers those.

Constraint on future MCP server modules: their top-level import
must be pure (no I/O, no connection opens, no side effects).
The three modules we ship today are pure imports; this gate
relies on that property to remain cheap and side-effect-free.
"""

from __future__ import annotations

import importlib
import json
import os
from pathlib import Path

_OUR_PACKAGE = "tools.mcp_servers"


def check_mcp_servers(config_path: str | None) -> list[str]:
    """Return list of unhealthy server entries (one string per
    bad server, formatted "<name>: <ExceptionType>: <message>"),
    or [] when all known servers are healthy / config missing /
    no known servers in config.

    Only probes servers whose module path starts with
    `tools.mcp_servers.*` (our code). Third-party servers
    (context7, etc.) are silently skipped — we don't own their
    health and can't meaningfully probe them.
    """
    if not config_path:
        return []
    path = Path(config_path)
    if not path.is_file():
        return []
    try:
        config = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return []
    servers = config.get("mcpServers") or {}
    unhealthy: list[str] = []
    for name, cfg in servers.items():
        module = _module_from_args(cfg.get("args") or [])
        if module is None or not module.startswith(_OUR_PACKAGE + "."):
            continue
        try:
            _probe(module, cfg.get("env") or {})
        except Exception as exc:
            unhealthy.append(f"{name}: {type(exc).__name__}: {exc}")
    return unhealthy


def _module_from_args(args: list[str]) -> str | None:
    """Extract the module name from a `python -m <module>` argv."""
    for i, a in enumerate(args):
        if a == "-m" and i + 1 < len(args):
            return args[i + 1]
    return None


def _probe(module: str, cfg_env: dict[str, str]) -> None:
    """Import the module and, for `ai_team_repo`, also exercise
    `Context.from_env` so AI_TEAM_REPO_ROOT misconfiguration
    surfaces as a clear error (FileNotFoundError, ScopeError, …)
    rather than as an opaque claude -p MCP-connect timeout."""
    importlib.import_module(module)
    if module.endswith(".ai_team_repo"):
        # Local (lazy) import: if `ai_team_repo.handlers` itself
        # fails to import, that must surface as an unhealthy
        # server here, NOT as a load-time failure that breaks
        # `core.llm.mcp_health`'s own importability and takes the
        # whole LLM stack down with it.
        from tools.mcp_servers.ai_team_repo.handlers import Context  # noqa: PLC0415

        Context.from_env({**os.environ, **cfg_env})
