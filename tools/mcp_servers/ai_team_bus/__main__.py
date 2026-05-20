"""MCP server: `ai_team_bus` — bus + feed access for agents.

Iteration 0 STUB: tools are declared but return placeholder responses.
Real implementation lands in Iteration 2 with the first agents.

iter-17: added `initialize` handler. Pre-iter-17 this stub silently
dropped the MCP handshake request (the same bug that affected the
production `ai_team_repo` server). See
`docs/iterations/iter_17.md`.

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

_SERVER_NAME = "ai_team_bus"
_SERVER_VERSION = "0.1.0"
_DEFAULT_PROTOCOL_VERSION = "2025-06-18"


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


def _build_response(msg: dict[str, Any]) -> dict[str, Any] | None:
    """Build the JSON-RPC response for one client message.

    Returns None for notifications (no id) and unknown methods —
    the loop translates that into "do not write to stdout".
    Stub `tools/call` returns a placeholder text response sync.
    See `tools/mcp_servers/ai_team_repo/__main__.py` for the
    iter-17 rationale.
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
                "serverInfo": {
                    "name": _SERVER_NAME,
                    "version": _SERVER_VERSION,
                },
            },
        }

    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {"tools": _TOOL_LIST},
        }

    if method == "tools/call":
        tool = (msg.get("params") or {}).get("name", "")
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
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

    return None


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
        response = _build_response(msg)
        if response is None:
            continue
        sys.stdout.write(json.dumps(response) + "\n")
        sys.stdout.flush()


def main() -> None:  # pragma: no cover
    asyncio.run(_stdio_loop())


if __name__ == "__main__":  # pragma: no cover
    main()
