"""CLI tests for `ai-team retry-blocked`. iter-11 Phase 1.4."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from apps.cli.main import cli


def _ok_resp(status_code: int = 200, data: object | None = None) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.json = MagicMock(return_value=data if data is not None else {})
    resp.text = ""
    return resp


def test_retry_blocked_in_help() -> None:
    result = CliRunner().invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "retry-blocked" in result.output


def test_retry_blocked_hits_endpoint_with_uuid() -> None:
    with patch("apps.cli.main.httpx.post") as mock_post:
        mock_post.return_value = _ok_resp(
            200,
            {
                "task_id": "11111111-1111-1111-1111-111111111111",
                "correlation_id": "22222222-2222-2222-2222-222222222222",
                "retry_attempt": 2,
                "status": "requeued",
            },
        )
        result = CliRunner().invoke(
            cli,
            [
                "--owner-token",
                "t",
                "retry-blocked",
                "11111111-1111-1111-1111-111111111111",
                "--comment",
                "test",
            ],
        )
    assert result.exit_code == 0, result.output
    assert "requeued" in result.output
    assert "retry_attempt" in result.output
    # Verify URL + body
    call_args = mock_post.call_args
    assert "/api/tasks/11111111-1111-1111-1111-111111111111/retry" in call_args.args[0]
    assert call_args.kwargs["json"] == {"comment": "test"}


def test_retry_blocked_surfaces_4xx_detail() -> None:
    with patch("apps.cli.main.httpx.post") as mock_post:
        bad = _ok_resp(429, None)
        bad.text = '{"detail":"task ... retry cap reached (5 attempts)"}'
        mock_post.return_value = bad
        result = CliRunner().invoke(
            cli,
            [
                "--owner-token",
                "t",
                "retry-blocked",
                "11111111-1111-1111-1111-111111111111",
            ],
        )
    assert result.exit_code != 0
    assert "429" in result.output or "retry cap" in result.output


def test_retry_blocked_requires_uuid() -> None:
    result = CliRunner().invoke(cli, ["retry-blocked", "not-a-uuid"])
    assert result.exit_code != 0
    assert "uuid" in result.output.lower() or "invalid" in result.output.lower()
