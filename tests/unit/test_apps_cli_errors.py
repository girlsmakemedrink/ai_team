"""Error-path tests for the CLI subcommands."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from apps.cli.main import cli


def _err_resp(status_code: int = 500, text: str = "boom") -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = text
    resp.json = MagicMock(return_value={})
    return resp


def test_submit_handles_server_error() -> None:
    with patch("apps.cli.main.httpx.post") as mock_post:
        mock_post.return_value = _err_resp(500, "internal error")
        result = CliRunner().invoke(
            cli,
            ["--owner-token", "t", "submit", "--title", "x", "--description", "y"],
        )
    assert result.exit_code != 0
    assert "Failed" in result.output


def test_approve_handles_404() -> None:
    with patch("apps.cli.main.httpx.post") as mock_post:
        mock_post.return_value = _err_resp(404, "not found")
        result = CliRunner().invoke(
            cli,
            [
                "--owner-token",
                "t",
                "approve",
                "33333333-3333-3333-3333-333333333333",
                "--comment",
                "ok",
            ],
        )
    assert result.exit_code != 0
    assert "Failed" in result.output


def test_list_pending_handles_error() -> None:
    with patch("apps.cli.main.httpx.get") as mock_get:
        mock_get.return_value = _err_resp(500)
        result = CliRunner().invoke(cli, ["--owner-token", "t", "list-pending"])
    assert result.exit_code != 0
    assert "Failed" in result.output


def test_digest_handles_error() -> None:
    with patch("apps.cli.main.httpx.get") as mock_get:
        mock_get.return_value = _err_resp(500, "no digest")
        result = CliRunner().invoke(cli, ["--owner-token", "t", "digest"])
    assert result.exit_code != 0
    assert "Failed" in result.output


def test_digest_history_handles_error() -> None:
    with patch("apps.cli.main.httpx.get") as mock_get:
        mock_get.return_value = _err_resp(500, "no history")
        result = CliRunner().invoke(cli, ["--owner-token", "t", "digest", "--history"])
    assert result.exit_code != 0


def test_digest_history_empty() -> None:
    with patch("apps.cli.main.httpx.get") as mock_get:
        mock_get.return_value = MagicMock(status_code=200, json=MagicMock(return_value=[]))
        result = CliRunner().invoke(cli, ["--owner-token", "t", "digest", "--history"])
    assert result.exit_code == 0
    assert "No checkpoints" in result.output
