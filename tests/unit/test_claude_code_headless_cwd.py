"""Tests for cwd forwarding through ClaudeCodeHeadlessClient. See iter-29c."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from core.llm.claude_code_headless import ClaudeCodeHeadlessClient


def _fake_proc(stdout: bytes = b'{"result":"hi","session_id":"s","usage":{}}') -> MagicMock:
    proc = MagicMock()
    proc.returncode = 0
    proc.communicate = AsyncMock(return_value=(stdout, b""))
    return proc


async def test_invoke_forwards_cwd_to_subprocess() -> None:
    client = ClaudeCodeHeadlessClient(binary="claude")
    with patch(
        "core.llm.claude_code_headless.asyncio.create_subprocess_exec",
        new=AsyncMock(return_value=_fake_proc()),
    ) as mock_spawn:
        await client.invoke(system_prompt="sp", user_message="um", cwd="/tmp/ws-X")
    assert mock_spawn.await_args is not None
    assert mock_spawn.await_args.kwargs.get("cwd") == "/tmp/ws-X"


async def test_invoke_default_cwd_is_none() -> None:
    """Self-hosting regression guard: omitted cwd → subprocess inherits parent cwd."""
    client = ClaudeCodeHeadlessClient(binary="claude")
    with patch(
        "core.llm.claude_code_headless.asyncio.create_subprocess_exec",
        new=AsyncMock(return_value=_fake_proc()),
    ) as mock_spawn:
        await client.invoke(system_prompt="sp", user_message="um")
    assert mock_spawn.await_args is not None
    assert mock_spawn.await_args.kwargs.get("cwd") is None
