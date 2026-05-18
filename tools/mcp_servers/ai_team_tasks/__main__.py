"""MCP server: `ai_team_tasks` — task lifecycle ops for agents.

Iteration 0 STUB. Real implementation lands in Iteration 2.

Exposes (planned):
- mcp__ai_team_tasks__mark_task_done(task_id, summary, artifacts)
- mcp__ai_team_tasks__request_human_review(summary, target_artifact)
- mcp__ai_team_tasks__update_task_status(task_id, status, progress_pct)
"""

from __future__ import annotations

import asyncio
import json
import sys
from typing import Any

_TOOL_LIST: list[dict[str, Any]] = [
    {
        "name": "mark_task_done",
        "description": "Mark a task as done and emit a task_report. STUB.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": True},
    },
    {
        "name": "request_human_review",
        "description": "Create a pending_review row awaiting owner approval. STUB.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": True},
    },
    {
        "name": "update_task_status",
        "description": "Update a task's status/progress. STUB.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": True},
    },
]


async def _stdio_loop() -> None:  # pragma: no cover
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
        if method == "tools/list":
            sys.stdout.write(
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": msg.get("id"),
                        "result": {"tools": _TOOL_LIST},
                    }
                )
                + "\n"
            )
            sys.stdout.flush()
        elif method == "tools/call":
            tool = msg.get("params", {}).get("name", "")
            sys.stdout.write(
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": msg.get("id"),
                        "result": {
                            "content": [
                                {
                                    "type": "text",
                                    "text": f"[stub] {tool} not implemented until Iteration 2",
                                }
                            ],
                            "isError": False,
                        },
                    }
                )
                + "\n"
            )
            sys.stdout.flush()


def main() -> None:  # pragma: no cover
    asyncio.run(_stdio_loop())


if __name__ == "__main__":  # pragma: no cover
    main()
