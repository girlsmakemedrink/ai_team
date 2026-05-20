"""MCP server: `ai_team_tasks` — task lifecycle ops for agents.

iter-18: `request_human_review` is now a real handler — it
INSERTs a `pending_reviews` row that the owner approves
via `POST /api/reviews/{id}/approve`. `mark_task_done` and
`update_task_status` remain STUBS pending an agent-prompt
audit (handoff §2).

iter-17: added `initialize` handler (commit `8022b9e`).

Exposes:
- mcp__ai_team_tasks__mark_task_done(task_id, summary, artifacts)  STUB
- mcp__ai_team_tasks__request_human_review(summary, correlation_id, agent?, task_id?, target_artifact?)
- mcp__ai_team_tasks__update_task_status(task_id, status, progress_pct)  STUB
"""

from __future__ import annotations

import asyncio
import json
import sys
from typing import Any

from tools.mcp_servers.ai_team_tasks.handlers import HANDLERS, Context

_SERVER_NAME = "ai_team_tasks"
_SERVER_VERSION = "0.2.0"
_DEFAULT_PROTOCOL_VERSION = "2025-06-18"

_TOOL_LIST: list[dict[str, Any]] = [
    {
        "name": "mark_task_done",
        "description": "Mark a task as done and emit a task_report. STUB (iter-18 deferred).",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": True},
    },
    {
        "name": "request_human_review",
        "description": (
            "Create a pending_review row awaiting owner approval. "
            "Required: summary (1-2000 chars), correlation_id (UUID string). "
            "Optional: agent (defaults to AI_TEAM_AGENT_ROLE env), "
            "task_id (UUID), target_artifact (path/branch/PR URL, ≤500 chars)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "summary": {"type": "string", "minLength": 1, "maxLength": 2000},
                "correlation_id": {"type": "string"},
                "agent": {"type": "string"},
                "task_id": {"type": "string"},
                "target_artifact": {"type": "string", "maxLength": 500},
            },
            "required": ["summary", "correlation_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "update_task_status",
        "description": "Update a task's status/progress. STUB (iter-18 deferred).",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": True},
    },
]


def _build_response(msg: dict[str, Any]) -> dict[str, Any] | None:
    """Build the JSON-RPC response for one client message.

    Same shape as `ai_team_repo/__main__.py:_build_response`.
    Returns None for notifications, unknown methods, AND
    `tools/call` (which dispatches async with Context in the
    stdio loop). See iter-17 rationale.
    """
    method = msg.get("method")
    msg_id = msg.get("id")

    if method == "initialize":
        params = msg.get("params") or {}
        client_version = params.get("protocolVersion") or _DEFAULT_PROTOCOL_VERSION
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "protocolVersion": client_version,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": _SERVER_NAME, "version": _SERVER_VERSION},
            },
        }

    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {"tools": _TOOL_LIST},
        }

    # tools/call + notifications + unknown methods → None.
    return None


async def _stdio_loop() -> None:  # pragma: no cover - integration-tested
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

        response = _build_response(msg)
        if response is not None:
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()
            continue

        if msg.get("method") == "tools/call":
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
            sys.stdout.write(
                json.dumps({"jsonrpc": "2.0", "id": msg.get("id"), "result": result}) + "\n"
            )
            sys.stdout.flush()


def main() -> None:  # pragma: no cover
    asyncio.run(_stdio_loop())


if __name__ == "__main__":  # pragma: no cover
    main()
