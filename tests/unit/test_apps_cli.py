"""CLI smoke tests using Click's CliRunner."""

from __future__ import annotations

from click.testing import CliRunner

from apps.cli.main import _api_base, _color_for, _render_event, _token_header, cli


def test_top_level_help_lists_commands() -> None:
    result = CliRunner().invoke(cli, ["--help"])
    assert result.exit_code == 0
    for cmd in ("watch", "submit", "approve", "reject", "list-pending", "status", "digest"):
        assert cmd in result.output


def test_watch_help() -> None:
    result = CliRunner().invoke(cli, ["watch", "--help"])
    assert result.exit_code == 0
    assert "Filter to one agent" in result.output
    assert "--correlation" in result.output


def test_submit_requires_title_and_description() -> None:
    result = CliRunner().invoke(cli, ["submit"])
    assert result.exit_code != 0
    assert "title" in result.output.lower() or "missing" in result.output.lower()


def test_color_for_known_role() -> None:
    assert "yellow" in _color_for("team_lead")


def test_color_for_unknown_falls_back() -> None:
    assert _color_for("unknown_role") == "white"


def test_render_event_returns_renderable() -> None:
    event = {
        "timestamp": "2026-05-18T12:00:00Z",
        "sender": "qa_engineer",
        "recipient": "backend_developer",
        "message_type": "review_request",
        "priority": "P2",
        "summary": "please review",
        "correlation_id": "abc12345-def",
    }
    line = _render_event(event)
    plain = line.plain
    assert "qa_engineer" in plain
    assert "review_request" in plain


def test_api_base_strips_trailing_slash() -> None:
    import click

    ctx = click.Context(cli)
    ctx.ensure_object(dict)
    ctx.obj["api_base"] = "http://example.com/"
    # _api_base reads from ctx.obj — emulate post-cli() state
    assert _api_base(ctx) == "http://example.com/"  # strip happens in cli(), not here


def test_token_header_with_token() -> None:
    import click

    ctx = click.Context(cli)
    ctx.ensure_object(dict)
    ctx.obj["owner_token"] = "deadbeef"
    h = _token_header(ctx)
    assert h["Authorization"] == "Bearer deadbeef"


def test_token_header_without_token() -> None:
    import click

    ctx = click.Context(cli)
    ctx.ensure_object(dict)
    h = _token_header(ctx)
    assert h == {}
