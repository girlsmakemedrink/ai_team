"""MCP server: `ai_team_bus` — bus + feed access for agents.

Iteration 0 STUB: tools are declared but return placeholder responses.
Real implementation lands in Iteration 2 with the first agents.

Exposes (planned):
- mcp__ai_team_bus__publish_message(message: AgentMessage)
- mcp__ai_team_bus__read_team_feed(filters: dict)
- mcp__ai_team_bus__read_audit_log_summary(correlation_id: str, since: str)
"""

from __future__ import annotations

import asyncio
import json
import sys
from typing import Any

# NOTE: We avoid importing the `mcp` package here so the stub remains
# runnable without that dependency installed yet. Iteration 2 wires the
# real MCP SDK in. The shape below mimics the JSON-RPC handshake that
# `claude -p --mcp-config` performs so the stub registers cleanly.


_TOOL_LIST: list[dict[str, Any]] = [
    {
        "name": "publish_message",
        "description": "Publish an AgentMessage on the bus. STUB.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": True},
    },
    {
        "name": "read_team_feed",
        "description": "Read recent team_feed events. STUB.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": True},
    },
    {
        "name": "read_audit_log_summary",
        "description": "Get a Haiku-summarised digest of audit log entries. STUB.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": True},
    },
]


async def _stdio_loop() -> None:  # pragma: no cover - integration tested separately
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
