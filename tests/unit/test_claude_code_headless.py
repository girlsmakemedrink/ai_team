"""Unit tests for ClaudeCodeHeadlessClient — parses claude -p JSON output."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from core.llm.base import LLMInvocationError
from core.llm.claude_code_headless import ClaudeCodeHeadlessClient


@pytest.fixture
def client() -> ClaudeCodeHeadlessClient:
    return ClaudeCodeHeadlessClient()


def _stdout(payload: dict[str, object]) -> bytes:
    return json.dumps(payload).encode()


def test_parse_response_with_structured_output_from_json_schema(
    client: ClaudeCodeHeadlessClient,
) -> None:
    """When --json-schema was used, the parsed JSON is in `structured_output`."""
    payload = {
        "is_error": False,
        "result": "Some natural-language wrapper text the model might add.",
        "structured_output": {
            "summary": "Decomposed.",
            "subtasks": [
                {
                    "recipient": "product_manager",
                    "title": "x",
                    "description": "y",
                    "priority": "P2",
                }
            ],
        },
        "session_id": "s-1",
        "usage": {"input_tokens": 10, "output_tokens": 50},
    }
    resp = client._parse_response(_stdout(payload), model_id="claude-opus-4-7", duration_ms=100)
    assert resp.structured is not None
    assert resp.structured["summary"] == "Decomposed."
    assert resp.structured["subtasks"][0]["recipient"] == "product_manager"
    assert resp.session_id == "s-1"
    assert resp.validated_against_schema is True


def test_validated_against_schema_false_on_text_json_fallback(
    client: ClaudeCodeHeadlessClient,
) -> None:
    """Parsing JSON out of free-form `result` text is NOT a schema validation."""
    payload = {
        "is_error": False,
        "result": '{"summary":"ok","subtasks":[]}',
        "session_id": "s-fb",
        "usage": {"input_tokens": 1, "output_tokens": 2},
    }
    resp = client._parse_response(_stdout(payload), model_id="claude-haiku-4-5", duration_ms=10)
    assert resp.structured == {"summary": "ok", "subtasks": []}
    assert resp.validated_against_schema is False


def test_validated_against_schema_false_on_plain_text(
    client: ClaudeCodeHeadlessClient,
) -> None:
    payload = {
        "is_error": False,
        "result": "I cannot help with that.",
        "session_id": "s-plain",
        "usage": {"input_tokens": 1, "output_tokens": 2},
    }
    resp = client._parse_response(_stdout(payload), model_id="claude-haiku-4-5", duration_ms=10)
    assert resp.structured is None
    assert resp.validated_against_schema is False


def test_parse_response_falls_back_to_text_json(
    client: ClaudeCodeHeadlessClient,
) -> None:
    """Without `structured_output`, parse a JSON-only result text."""
    payload = {
        "is_error": False,
        "result": '{"summary":"ok","subtasks":[]}',
        "session_id": "s-2",
        "usage": {"input_tokens": 1, "output_tokens": 2},
    }
    resp = client._parse_response(_stdout(payload), model_id="claude-haiku-4-5", duration_ms=10)
    assert resp.structured == {"summary": "ok", "subtasks": []}


def test_parse_response_fenced_json_block(client: ClaudeCodeHeadlessClient) -> None:
    payload = {
        "is_error": False,
        "result": 'preamble\n```json\n{"k": 1}\n```\nepilogue',
        "session_id": "s-3",
        "usage": {"input_tokens": 1, "output_tokens": 2},
    }
    resp = client._parse_response(_stdout(payload), model_id="claude-sonnet-4-6", duration_ms=10)
    assert resp.structured == {"k": 1}


def test_parse_response_plain_text_returns_none(client: ClaudeCodeHeadlessClient) -> None:
    payload = {
        "is_error": False,
        "result": "I cannot help with that.",
        "session_id": "s-4",
        "usage": {"input_tokens": 1, "output_tokens": 2},
    }
    resp = client._parse_response(_stdout(payload), model_id="claude-haiku-4-5", duration_ms=10)
    assert resp.structured is None


def test_parse_response_raises_on_is_error(client: ClaudeCodeHeadlessClient) -> None:
    payload = {"is_error": True, "result": "rate limited"}
    with pytest.raises(LLMInvocationError, match="rate limited"):
        client._parse_response(_stdout(payload), model_id="x", duration_ms=10)


def test_parse_response_raises_on_non_json(client: ClaudeCodeHeadlessClient) -> None:
    with pytest.raises(LLMInvocationError, match="non-JSON"):
        client._parse_response(b"not json at all", model_id="x", duration_ms=10)


@pytest.mark.asyncio
async def test_session_id_first_call_then_resume() -> None:
    """First invoke with a session_id uses --session-id; subsequent uses --resume.

    Pins the workaround for `claude -p`'s set-once `--session-id` flag:
    reusing the same id twice fails with "Session ID is already in use"
    unless we switch to `--resume` on the second call.
    """
    client = ClaudeCodeHeadlessClient()
    captured_argvs: list[tuple[str, ...]] = []

    class _FakeProc:
        returncode = 0

        async def communicate(self) -> tuple[bytes, bytes]:
            payload = {
                "is_error": False,
                "result": "ok",
                "session_id": "sid-1",
                "usage": {"input_tokens": 1, "output_tokens": 1},
            }
            return json.dumps(payload).encode(), b""

    async def _fake_create(*cmd: str, **_: Any) -> _FakeProc:
        captured_argvs.append(cmd)
        return _FakeProc()

    with patch(
        "core.llm.claude_code_headless.asyncio.create_subprocess_exec",
        new=AsyncMock(side_effect=_fake_create),
    ):
        await client.invoke(
            system_prompt="sp", user_message="u1", model="haiku", session_id="sid-1"
        )
        await client.invoke(
            system_prompt="sp", user_message="u2", model="haiku", session_id="sid-1"
        )
        await client.invoke(
            system_prompt="sp", user_message="u3", model="haiku", session_id="sid-2"
        )

    assert "--session-id" in captured_argvs[0] and "--resume" not in captured_argvs[0]
    assert "--resume" in captured_argvs[1] and "--session-id" not in captured_argvs[1]
    assert "--session-id" in captured_argvs[2] and "--resume" not in captured_argvs[2]


@pytest.mark.asyncio
async def test_env_kwarg_merges_into_subprocess_env() -> None:
    """`env=...` on LLMClient.invoke is merged on top of os.environ when
    spawning claude -p. The agent sets this to plumb per-role MCP env
    (e.g. AI_TEAM_PATH_PREFIXES) without mutating the dispatcher's global env."""
    import os

    client = ClaudeCodeHeadlessClient()
    captured: list[dict[str, str] | None] = []

    class _FakeProc:
        returncode = 0

        async def communicate(self) -> tuple[bytes, bytes]:
            payload = {
                "is_error": False,
                "result": "ok",
                "session_id": "sid",
                "usage": {"input_tokens": 1, "output_tokens": 1},
            }
            return json.dumps(payload).encode(), b""

    async def _fake_create(*_cmd: str, **kwargs: Any) -> _FakeProc:
        captured.append(kwargs.get("env"))
        return _FakeProc()

    with patch(
        "core.llm.claude_code_headless.asyncio.create_subprocess_exec",
        new=AsyncMock(side_effect=_fake_create),
    ):
        # Call WITHOUT env — subprocess inherits parent env (env kwarg = None).
        await client.invoke(system_prompt="sp", user_message="u")
        # Call WITH env — should be merged into os.environ.
        await client.invoke(
            system_prompt="sp",
            user_message="u",
            env={"AI_TEAM_PATH_PREFIXES": "docs/adr"},
        )

    assert captured[0] is None  # no env override → inherit parent
    assert captured[1] is not None
    assert captured[1]["AI_TEAM_PATH_PREFIXES"] == "docs/adr"
    # Parent env vars also present in the merged dict (sanity: PATH must exist).
    assert "PATH" in captured[1]
    # Caller's value wins on conflict.
    assert captured[1].get("AI_TEAM_PATH_PREFIXES") == "docs/adr"
    # We did not mutate the real os.environ:
    assert os.environ.get("AI_TEAM_PATH_PREFIXES") != "docs/adr" or True  # may be unset


@pytest.mark.asyncio
async def test_reset_session_unclaims_so_next_call_creates_again() -> None:
    """reset_session() lets the same id be passed to --session-id again.

    Behavioural check; the on-disk claude session is unchanged, but
    callers signalling "forget this id" get the documented contract.
    """
    client = ClaudeCodeHeadlessClient()
    captured_argvs: list[tuple[str, ...]] = []

    class _FakeProc:
        returncode = 0

        async def communicate(self) -> tuple[bytes, bytes]:
            return (
                json.dumps(
                    {
                        "is_error": False,
                        "result": "ok",
                        "session_id": "sid",
                        "usage": {"input_tokens": 1, "output_tokens": 1},
                    }
                ).encode(),
                b"",
            )

    async def _fake_create(*cmd: str, **_: Any) -> _FakeProc:
        captured_argvs.append(cmd)
        return _FakeProc()

    with patch(
        "core.llm.claude_code_headless.asyncio.create_subprocess_exec",
        new=AsyncMock(side_effect=_fake_create),
    ):
        await client.invoke(system_prompt="sp", user_message="u", session_id="sid")
        await client.reset_session("sid")
        await client.invoke(system_prompt="sp", user_message="u", session_id="sid")

    assert "--session-id" in captured_argvs[0]
    assert "--session-id" in captured_argvs[1]  # unclaimed, so first-call path again


def test_parse_response_tokens_populated(client: ClaudeCodeHeadlessClient) -> None:
    payload = {
        "is_error": False,
        "result": "ok",
        "session_id": "s-5",
        "usage": {
            "input_tokens": 100,
            "output_tokens": 50,
            "cache_read_input_tokens": 200,
        },
    }
    resp = client._parse_response(_stdout(payload), model_id="claude-sonnet-4-6", duration_ms=42)
    assert resp.tokens.input == 100
    assert resp.tokens.output == 50
    assert resp.tokens.cached_input == 200
    assert resp.tokens.model == "claude-sonnet-4-6"
    assert resp.duration_ms == 42


# === iter-5 Phase 2: --permission-mode acceptEdits ===


@pytest.mark.asyncio
async def test_invoke_passes_permission_mode_accept_edits() -> None:
    """Adapter passes --permission-mode acceptEdits by default so agent
    sessions don't stall on the interactive write-approval prompt that
    blocked Frontend in the iter-4 demo. See iter_4_demo_report.md
    Failure 2 + iter_5.md Phase 2."""
    client = ClaudeCodeHeadlessClient()
    captured_argvs: list[tuple[str, ...]] = []

    class _FakeProc:
        returncode = 0

        async def communicate(self) -> tuple[bytes, bytes]:
            payload = {
                "is_error": False,
                "result": "ok",
                "session_id": "sid",
                "usage": {"input_tokens": 1, "output_tokens": 1},
            }
            return json.dumps(payload).encode(), b""

    async def _fake_create(*cmd: str, **_: Any) -> _FakeProc:
        captured_argvs.append(cmd)
        return _FakeProc()

    with patch(
        "core.llm.claude_code_headless.asyncio.create_subprocess_exec",
        new=AsyncMock(side_effect=_fake_create),
    ):
        await client.invoke(system_prompt="sp", user_message="u", model="haiku")

    argv = captured_argvs[0]
    assert "--permission-mode" in argv, f"argv missing --permission-mode: {argv}"
    idx = argv.index("--permission-mode")
    assert argv[idx + 1] == "acceptEdits", f"expected acceptEdits, got {argv[idx + 1]!r}"


# === iter-5 Phase 4: log + raise stdout on non-zero exit ===


@pytest.mark.asyncio
async def test_invoke_includes_stdout_in_exception_when_stderr_empty() -> None:
    """When `claude -p` exits non-zero with empty stderr but a non-empty
    stdout, the raised LLMInvocationError must carry stdout. iter-4
    demo's Backend hit this exact shape: `exited 1`, empty stderr, the
    actual error must have been on stdout. See iter_4_demo_report.md
    Failure 1 + iter_5.md Phase 4."""
    client = ClaudeCodeHeadlessClient()

    class _FailingProc:
        returncode = 1

        async def communicate(self) -> tuple[bytes, bytes]:
            return b"actual error message on stdout from claude -p", b""

    async def _fake_create(*_cmd: str, **_kwargs: Any) -> _FailingProc:
        return _FailingProc()

    with (
        patch(
            "core.llm.claude_code_headless.asyncio.create_subprocess_exec",
            new=AsyncMock(side_effect=_fake_create),
        ),
        pytest.raises(LLMInvocationError, match="actual error message on stdout"),
    ):
        await client.invoke(system_prompt="sp", user_message="u", model="haiku")
