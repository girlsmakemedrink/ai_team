"""MCP server entry point — stdio JSON-RPC loop.

Wired the same way as `ai_team_bus` / `ai_team_tasks`: no `mcp` package
dependency, hand-rolled stdio loop, so it stays runnable from a fresh
`uv run` without extra installs. Handlers live in `handlers.py`.

Tools surface (per ADR-004's path-scoped repo ops):

- status()                              → {branch, is_dirty, modified, untracked_files}
- create_branch(branch, base?)          → {branch, base, created}
- write_file_in_scope(path, content, mode)
                                        → {path, absolute_path, bytes_written}
- run_shell(command_class, args)        → {argv, returncode, stdout, stderr, truncated}
- open_pr(head, base?, title, body)     → {head, base, url}
"""

from __future__ import annotations

import asyncio
import json
import sys
from typing import Any

from tools.mcp_servers.ai_team_repo.handlers import HANDLERS, Context

TOOL_LIST: list[dict[str, Any]] = [
    {
        "name": "status",
        "description": "Read repo status: branch, is_dirty, modified, untracked_files.",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    },
    {
        "name": "create_branch",
        "description": (
            "Create a new feature branch from base. Branch must match "
            "agent/<role>/<slug>; base is rejected if it matches the "
            "forbidden-branches regex."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "branch": {"type": "string"},
                "base": {"type": "string"},
            },
            "required": ["branch"],
            "additionalProperties": False,
        },
    },
    {
        "name": "write_file_in_scope",
        "description": (
            "Write a file at a path inside the per-role allowed prefixes. "
            "mode=create errors if the file exists; mode=overwrite replaces."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Repo-relative path"},
                "content": {"type": "string"},
                "mode": {"type": "string", "enum": ["create", "overwrite"]},
            },
            "required": ["path", "content", "mode"],
            "additionalProperties": False,
        },
    },
    {
        "name": "run_shell",
        "description": (
            "Run a shell command from a fixed enum of command classes. "
            "Each class has its own arg validator. There is no raw-Bash escape."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "command_class": {
                    "type": "string",
                    "enum": [
                        "pytest",
                        "ruff",
                        "mypy",
                        "git_status",
                        "git_diff",
                        "git_add",
                        "git_commit",
                        "git_push_feature",
                        "gh_pr_create",
                        "make_test",
                    ],
                },
                "args": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["command_class"],
            "additionalProperties": False,
        },
    },
    {
        "name": "open_pr",
        "description": (
            "Open a PR via `gh pr create`. Refuses head branches not matching "
            "agent/<role>/<slug> and bases matching the forbidden-branches regex."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "head": {"type": "string"},
                "base": {"type": "string"},
                "title": {"type": "string"},
                "body": {"type": "string"},
            },
            "required": ["head", "title", "body"],
            "additionalProperties": False,
        },
    },
]


async def _stdio_loop() -> None:  # pragma: no cover - smoke-tested via integration
    ctx = Context.from_env()
    loop = asyncio.get_event_loop()
    reader = asyncio.StreamReader()
    protocol = asyncio.StreamReaderProtocol(reader)
    await loop.connect_read_pipe(lambda: protocol, sys.stdin)
    while True:
        line = await reader.readline()
        if not line:
            return
        try:
            msg = json.loads(line.decode())
        except json.JSONDecodeError:
            continue
        method = msg.get("method")
        msg_id = msg.get("id")
        if method == "tools/list":
            sys.stdout.write(
                json.dumps({"jsonrpc": "2.0", "id": msg_id, "result": {"tools": TOOL_LIST}}) + "\n"
            )
            sys.stdout.flush()
        elif method == "tools/call":
            params = msg.get("params") or {}
            name = params.get("name", "")
            arguments = params.get("arguments") or {}
            handler = HANDLERS.get(name)
            if handler is None:
                result = {
                    "isError": True,
                    "content": [{"type": "text", "text": f"unknown tool: {name!r}"}],
                }
            else:
                result = await handler(ctx, arguments)
            sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": msg_id, "result": result}) + "\n")
            sys.stdout.flush()


def main() -> None:  # pragma: no cover
    asyncio.run(_stdio_loop())


if __name__ == "__main__":  # pragma: no cover
    main()
