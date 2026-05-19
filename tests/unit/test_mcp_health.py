"""Unit tests for `core.llm.mcp_health.check_mcp_servers`.

iter-9: the gate catches deterministic startup failures (module
import errors, env validation failures via Context.from_env) for
our own MCP servers before claude -p spawns them. See
iter_9.md success criterion #1 + iter_8_demo_report.md Failure 1.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from core.llm.mcp_health import check_mcp_servers

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def _write_config(tmp_path: Path, servers: dict[str, object]) -> str:
    path = tmp_path / "mcp.json"
    path.write_text(json.dumps({"mcpServers": servers}))
    return str(path)


def test_check_returns_empty_for_three_healthy_servers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Happy path: all three of our servers import + (for repo)
    Context.from_env validates. Mirrors the .iter9-mcp.json the
    demo script writes."""
    monkeypatch.setenv("AI_TEAM_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("AI_TEAM_PATH_PREFIXES", "*")
    config = _write_config(
        tmp_path,
        {
            "ai-team-bus": {
                "command": "python",
                "args": ["-m", "tools.mcp_servers.ai_team_bus"],
            },
            "ai-team-tasks": {
                "command": "python",
                "args": ["-m", "tools.mcp_servers.ai_team_tasks"],
            },
            "ai-team-repo": {
                "command": "python",
                "args": ["-m", "tools.mcp_servers.ai_team_repo"],
                "env": {
                    "AI_TEAM_REPO_ROOT": str(tmp_path),
                    "AI_TEAM_PATH_PREFIXES": "*",
                },
            },
        },
    )
    assert check_mcp_servers(config) == []


def test_check_returns_empty_when_config_path_none() -> None:
    """No config = nothing to probe = silent skip. Preserves
    every existing mocked-LLM unit test where no MCP is wired."""
    assert check_mcp_servers(None) == []


def test_check_returns_empty_when_config_file_missing(tmp_path: Path) -> None:
    """If the config path points to a nonexistent file, treat as
    'no config' rather than raising. The adapter does the same:
    AI_TEAM_MCP_CONFIG_PATH=<missing> means no --mcp-config flag."""
    bogus = str(tmp_path / "does_not_exist.json")
    assert check_mcp_servers(bogus) == []


def test_check_surfaces_import_error_by_name(tmp_path: Path) -> None:
    """If a server's module fails to import, the result names it.
    Reproduces the iter-8 demo failure mode in unit form."""
    config = _write_config(
        tmp_path,
        {
            "ai-team-broken": {
                "command": "python",
                "args": [
                    "-m",
                    "tools.mcp_servers.nonexistent_module_xyz",
                ],
            },
        },
    )
    result = check_mcp_servers(config)
    assert len(result) == 1
    assert "ai-team-broken" in result[0]
    # Either ModuleNotFoundError or ImportError, depending on Python version
    assert "Error" in result[0]


def test_check_surfaces_repo_root_pointing_to_nonexistent_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Context.from_env → ScopeConfig.from_env does
    Path(root).resolve(strict=True), which raises
    FileNotFoundError if AI_TEAM_REPO_ROOT doesn't exist. Catch
    that as an unhealthy server so the owner gets a clear
    error instead of an opaque claude -p MCP-connect failure."""
    monkeypatch.delenv("AI_TEAM_REPO_ROOT", raising=False)
    config = _write_config(
        tmp_path,
        {
            "ai-team-repo": {
                "command": "python",
                "args": ["-m", "tools.mcp_servers.ai_team_repo"],
                "env": {
                    "AI_TEAM_REPO_ROOT": "/nonexistent/iter9/xyz",
                    "AI_TEAM_PATH_PREFIXES": "*",
                },
            },
        },
    )
    result = check_mcp_servers(config)
    assert len(result) == 1
    assert "ai-team-repo" in result[0]


def test_check_skips_third_party_servers_silently(tmp_path: Path) -> None:
    """Unknown modules (context7, etc.) are not ours to probe.
    See iter_9.md decision #1(a) — narrowest fix to the observed
    failure mode."""
    config = _write_config(
        tmp_path,
        {
            "context7": {
                "command": "npx",
                "args": ["-y", "@upstash/context7-mcp"],
            },
            "some-third-party": {
                "command": "python",
                "args": ["-m", "other.package.not.ours"],
            },
        },
    )
    assert check_mcp_servers(config) == []
