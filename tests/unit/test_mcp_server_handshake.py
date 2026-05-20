"""iter-17: MCP `initialize` handshake tests.

Pre-iter-17 the three MCP servers (`ai_team_repo`, `ai_team_bus`,
`ai_team_tasks`) had no `initialize` handler in their stdio loops.
claude -p's REQUIRED JSON-RPC handshake silently dropped → claude
marked the server as "still connecting" → ToolSearch retries
returned "still-connecting" → eventually "never connected" /
"unreachable" / "unavailable". The 9-iteration "MCP race"
carry-over (iter-9..16) was actually a 14-iteration latent
protocol bug from iter-2 (commit d8bc3e8).

These tests exercise the new pure `_build_response(msg)` helper
in each server module:

- `initialize` → spec-correct response (protocolVersion +
  capabilities + serverInfo).
- `notifications/initialized` → None (notifications must not
  receive responses per MCP spec).
- `tools/list` → existing tool list (regression guard against
  the refactor breaking the established path).
- Unknown REQUEST method → None (forward-compatible behavior
  that preserves the pre-iter-17 silent-drop).

See `docs/iterations/iter_17.md` Phase 1 for the investigation
evidence + reproduction.
"""

from __future__ import annotations

import importlib

import pytest

_SERVERS = ("ai_team_repo", "ai_team_bus", "ai_team_tasks")


@pytest.mark.parametrize("server_pkg", _SERVERS)
def test_initialize_returns_spec_correct_response(server_pkg: str) -> None:
    module = importlib.import_module(f"tools.mcp_servers.{server_pkg}.__main__")
    msg = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "test", "version": "0"},
        },
    }
    response = module._build_response(msg)
    assert response is not None, "initialize MUST produce a response per MCP spec"
    assert response["jsonrpc"] == "2.0"
    assert response["id"] == 1
    result = response["result"]
    # Echo client's protocolVersion — we support whatever the client speaks.
    assert result["protocolVersion"] == "2025-06-18"
    # We expose tools (no resources / prompts / sampling).
    assert "tools" in result["capabilities"]
    # serverInfo names this specific server.
    assert result["serverInfo"]["name"] == server_pkg
    assert "version" in result["serverInfo"]


@pytest.mark.parametrize("server_pkg", _SERVERS)
def test_initialized_notification_returns_no_response(server_pkg: str) -> None:
    """`notifications/initialized` is a JSON-RPC notification (no id).
    Per MCP spec the server MUST NOT respond to notifications."""
    module = importlib.import_module(f"tools.mcp_servers.{server_pkg}.__main__")
    msg = {"jsonrpc": "2.0", "method": "notifications/initialized"}
    assert module._build_response(msg) is None


@pytest.mark.parametrize("server_pkg", _SERVERS)
def test_tools_list_returns_existing_tool_list(server_pkg: str) -> None:
    """Regression guard: the refactor extracts `_build_response` from
    the stdio loop, but `tools/list` MUST still return the existing
    tool list verbatim — agents reference these tool names in prompts."""
    module = importlib.import_module(f"tools.mcp_servers.{server_pkg}.__main__")
    msg = {"jsonrpc": "2.0", "id": 5, "method": "tools/list"}
    response = module._build_response(msg)
    assert response is not None
    assert response["id"] == 5
    tools = response["result"]["tools"]
    assert isinstance(tools, list)
    assert len(tools) > 0
    # Every tool entry has a name + description + inputSchema (MCP
    # ToolDefinition shape).
    for tool in tools:
        assert "name" in tool
        assert "description" in tool
        assert "inputSchema" in tool


@pytest.mark.parametrize("server_pkg", _SERVERS)
def test_unknown_request_method_returns_none(server_pkg: str) -> None:
    """Forward-compat: an unknown REQUEST (with id) returns None — the
    stdio loop translates that into "do not write anything to stdout",
    preserving the pre-iter-17 silent-drop for unknown methods. The
    `tools/call` path is handled DIRECTLY in the stdio loop (it
    dispatches to async handlers for `ai_team_repo`), so it is also
    not in `_build_response`."""
    module = importlib.import_module(f"tools.mcp_servers.{server_pkg}.__main__")
    msg = {"jsonrpc": "2.0", "id": 99, "method": "resources/list"}
    assert module._build_response(msg) is None
