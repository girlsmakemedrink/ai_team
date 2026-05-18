"""More CLI tests covering subcommands via CliRunner with mocked httpx."""

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


def test_submit_prints_panel_on_success() -> None:
    with patch("apps.cli.main.httpx.post") as mock_post:
        mock_post.return_value = _ok_resp(
            200,
            {
                "task_id": "11111111-1111-1111-1111-111111111111",
                "correlation_id": "22222222-2222-2222-2222-222222222222",
                "status": "queued",
            },
        )
        result = CliRunner().invoke(
            cli,
            ["--owner-token", "t", "submit", "--title", "x", "--description", "y"],
        )
    assert result.exit_code == 0, result.output
    assert "queued" in result.output
    assert "task_id" in result.output


def test_list_pending_empty() -> None:
    with patch("apps.cli.main.httpx.get") as mock_get:
        mock_get.return_value = _ok_resp(200, [])
        result = CliRunner().invoke(cli, ["--owner-token", "t", "list-pending"])
    assert result.exit_code == 0
    assert "No pending" in result.output


def test_list_pending_with_rows() -> None:
    with patch("apps.cli.main.httpx.get") as mock_get:
        mock_get.return_value = _ok_resp(
            200,
            [
                {
                    "id": "33333333-3333-3333-3333-333333333333",
                    "requesting_agent": "product_manager",
                    "summary": "review my work",
                    "created_at": "2026-05-18T18:00:00Z",
                }
            ],
        )
        result = CliRunner().invoke(cli, ["--owner-token", "t", "list-pending"])
    assert result.exit_code == 0
    assert "product_manager" in result.output
    assert "review my work" in result.output


def test_approve_command_hits_endpoint() -> None:
    with patch("apps.cli.main.httpx.post") as mock_post:
        mock_post.return_value = _ok_resp(200, {"status": "approved"})
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
    assert result.exit_code == 0
    assert "approved" in result.output


def test_reject_requires_comment() -> None:
    result = CliRunner().invoke(cli, ["reject", "33333333-3333-3333-3333-333333333333"])
    assert result.exit_code != 0
    assert "comment" in result.output.lower() or "missing" in result.output.lower()


def test_reject_command_hits_endpoint() -> None:
    with patch("apps.cli.main.httpx.post") as mock_post:
        mock_post.return_value = _ok_resp(200, {"status": "rejected"})
        result = CliRunner().invoke(
            cli,
            [
                "--owner-token",
                "t",
                "reject",
                "33333333-3333-3333-3333-333333333333",
                "--comment",
                "no",
            ],
        )
    assert result.exit_code == 0
    assert "rejected" in result.output


def test_status_command() -> None:
    with patch("apps.cli.main.httpx.get") as mock_get:
        mock_get.return_value = _ok_resp(200, {"status": "ok"})
        result = CliRunner().invoke(cli, ["status"])
    assert result.exit_code == 0
    assert "ok" in result.output


def test_digest_latest() -> None:
    with patch("apps.cli.main.httpx.get") as mock_get:
        mock_get.return_value = _ok_resp(
            200,
            {
                "id": None,
                "created_at": None,
                "trigger": "manual",
                "correlation_id": None,
                "iteration": 1,
                "digest_markdown": "### Done\n- demo",
                "quota_used_pct": 5.0,
            },
        )
        result = CliRunner().invoke(cli, ["--owner-token", "t", "digest"])
    assert result.exit_code == 0
    assert "Done" in result.output
    assert "demo" in result.output


def test_digest_history() -> None:
    with patch("apps.cli.main.httpx.get") as mock_get:
        mock_get.return_value = _ok_resp(
            200,
            [
                {
                    "id": None,
                    "created_at": "2026-05-18T18:00:00Z",
                    "trigger": "scheduled",
                    "correlation_id": None,
                    "iteration": 1,
                    "digest_markdown": "snapshot text",
                    "quota_used_pct": 10.0,
                }
            ],
        )
        result = CliRunner().invoke(
            cli, ["--owner-token", "t", "digest", "--history", "--limit", "3"]
        )
    assert result.exit_code == 0
    assert "snapshot text" in result.output
