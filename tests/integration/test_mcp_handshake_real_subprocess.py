"""End-to-end MCP handshake against the real Python subprocess spawn.

Closest possible reproduction of how claude -p talks to our MCP
servers: spawn `python -m tools.mcp_servers.<name>`, pipe JSON-RPC
messages via stdin, parse JSON-RPC responses on stdout.

iter-17: the 14-iteration latent MCP handshake bug went unnoticed
because the only tests exercising the MCP servers imported handler
functions directly OR exercised them via the iter-9 in-process
`check_mcp_servers` probe (which does `importlib.import_module()`
only). Neither path drives the stdio loop end-to-end. These
subprocess tests do — if the `initialize` handler regresses, they
fail.

No testcontainers needed; just a Python subprocess. Fast.
"""

from __future__ import annotations

import json
import subprocess
import sys

import pytest

_SERVERS = ("ai_team_repo", "ai_team_bus", "ai_team_tasks")


@pytest.mark.integration
@pytest.mark.parametrize("server_pkg", _SERVERS)
def test_real_subprocess_initialize_then_tools_list(server_pkg: str) -> None:
    """Spawn the MCP server, send the canonical claude -p handshake
    (`initialize` then `tools/list`), assert both responses arrive
    on stdout with spec-correct shape. Pre-iter-17 the initialize
    response was missing entirely — claude -p would mark the server
    as "still connecting" indefinitely."""
    payload = (
        b'{"jsonrpc":"2.0","id":1,"method":"initialize",'
        b'"params":{"protocolVersion":"2025-06-18","capabilities":{},'
        b'"clientInfo":{"name":"test","version":"0"}}}\n'
        b'{"jsonrpc":"2.0","id":2,"method":"tools/list"}\n'
    )
    proc = subprocess.Popen(
        [sys.executable, "-m", f"tools.mcp_servers.{server_pkg}"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        out, err = proc.communicate(input=payload, timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        pytest.fail(f"{server_pkg} hung — did not respond within 10s")

    lines = [ln for ln in out.decode().splitlines() if ln.strip()]
    assert len(lines) == 2, (
        f"expected 2 responses (initialize + tools/list), got {len(lines)}: "
        f"out={out.decode()!r} err={err.decode()!r}"
    )

    init_response = json.loads(lines[0])
    assert init_response["id"] == 1
    result = init_response["result"]
    assert result["protocolVersion"] == "2025-06-18"
    assert "tools" in result["capabilities"]
    assert result["serverInfo"]["name"] == server_pkg

    tools_response = json.loads(lines[1])
    assert tools_response["id"] == 2
    assert len(tools_response["result"]["tools"]) > 0


@pytest.mark.integration
@pytest.mark.parametrize("server_pkg", _SERVERS)
def test_real_subprocess_notification_does_not_emit_response(server_pkg: str) -> None:
    """`notifications/initialized` is a JSON-RPC notification (no id).
    Server MUST NOT respond. Verifies the stdio loop does not write
    anything on stdout for notifications — accidental responses to
    notifications confuse MCP clients."""
    payload = (
        b'{"jsonrpc":"2.0","method":"notifications/initialized"}\n'
        b'{"jsonrpc":"2.0","id":42,"method":"tools/list"}\n'
    )
    proc = subprocess.Popen(
        [sys.executable, "-m", f"tools.mcp_servers.{server_pkg}"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        out, _err = proc.communicate(input=payload, timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        pytest.fail(f"{server_pkg} hung — did not respond within 10s")

    lines = [ln for ln in out.decode().splitlines() if ln.strip()]
    # Exactly ONE response — for the `tools/list` request. Zero
    # responses for the notification.
    assert len(lines) == 1, f"expected 1 response (only for tools/list), got {len(lines)}"
    response = json.loads(lines[0])
    assert response["id"] == 42
