"""Command-class enum tests for the ai_team_repo MCP server.

Each test pins a specific rejection in the `run_shell` registry — the
ADR-004 "Bash never raw" contract. Adding a class without a test here
is a security review failure.
"""

from __future__ import annotations

import pytest

from tools.mcp_servers.ai_team_repo.commands import (
    COMMANDS,
    CommandRejected,
    resolve_command,
    set_forbidden_pr_base_re,
)


def test_unknown_command_class_rejected() -> None:
    with pytest.raises(CommandRejected, match="unknown command_class"):
        resolve_command("rm", ["-rf", "/"])


def test_registry_covers_planned_classes() -> None:
    """Every class named in the ADR-004 Backend allowlist must exist."""
    expected = {
        "pytest",
        "ruff",
        "mypy",
        "git_status",
        "git_diff",
        "git_add",
        "git_commit",
        "git_push_feature",
        "gh_pr_create",
        "make_test",
    }
    assert expected.issubset(COMMANDS.keys())


def test_pytest_allows_marker_selectors() -> None:
    argv = resolve_command("pytest", ["-m", "unit", "tests/unit"])
    assert argv[:3] == ("uv", "run", "pytest")
    assert "-m" in argv and "tests/unit" in argv


def test_pytest_rejects_dash_dash_separator() -> None:
    with pytest.raises(CommandRejected, match=r"`--` separator"):
        resolve_command("pytest", ["tests/unit", "--", "; rm -rf /"])


def test_pytest_rejects_plugin_path_with_slash() -> None:
    with pytest.raises(CommandRejected, match="plugin path"):
        resolve_command("pytest", ["-p/etc/evil_plugin.py"])


def test_git_add_requires_paths() -> None:
    with pytest.raises(CommandRejected, match="at least one path"):
        resolve_command("git_add", [])


def test_git_add_allows_dot_paths_and_files() -> None:
    argv = resolve_command("git_add", ["docs/adr/foo.md", "tests/test_foo.py"])
    assert argv == (
        "git",
        "add",
        "docs/adr/foo.md",
        "tests/test_foo.py",
    )


def test_git_add_rejects_unknown_flag() -> None:
    with pytest.raises(CommandRejected, match="not allowed"):
        resolve_command("git_add", ["--exec", "evil"])


def test_git_commit_requires_message() -> None:
    with pytest.raises(CommandRejected, match="requires -m"):
        resolve_command("git_commit", [])


def test_git_commit_accepts_dash_m_message() -> None:
    argv = resolve_command("git_commit", ["-m", "feat: x"])
    assert argv == ("git", "commit", "-m", "feat: x")


def test_git_commit_rejects_amend() -> None:
    with pytest.raises(CommandRejected, match="--amend"):
        resolve_command("git_commit", ["--amend", "-m", "rewrite history"])


@pytest.mark.parametrize(
    "branch",
    ["main", "master", "develop", "release/1.0", "feature/foo"],
)
def test_git_push_feature_refuses_non_agent_branch(branch: str) -> None:
    with pytest.raises(CommandRejected, match="agent/"):
        resolve_command("git_push_feature", ["origin", branch])


@pytest.mark.parametrize(
    "branch",
    [
        "agent/backend_developer/iter2-foo",
        "agent/architect/0010-validator",
    ],
)
def test_git_push_feature_accepts_agent_branch(branch: str) -> None:
    argv = resolve_command("git_push_feature", ["-u", "origin", branch])
    assert branch in argv


@pytest.mark.parametrize(
    "base",
    ["main", "master", "release/1.0", "release/2026-05"],
)
def test_gh_pr_create_refuses_forbidden_base(base: str) -> None:
    with pytest.raises(CommandRejected, match="forbidden"):
        resolve_command(
            "gh_pr_create",
            ["--head", "agent/be/foo", "--base", base, "--title", "x", "--body", "y"],
        )


def test_gh_pr_create_handles_equals_form_for_base() -> None:
    with pytest.raises(CommandRejected, match="forbidden"):
        resolve_command(
            "gh_pr_create",
            ["--head", "agent/be/foo", "--base=main", "--title", "x", "--body", "y"],
        )


def test_make_test_only_allowed_targets() -> None:
    assert resolve_command("make_test", []) == ("make",)
    assert resolve_command("make_test", ["test-unit"]) == ("make", "test-unit")
    with pytest.raises(CommandRejected, match="not allowed"):
        resolve_command("make_test", ["clean"])


def test_make_test_rejects_flags() -> None:
    with pytest.raises(CommandRejected, match="flag not allowed"):
        resolve_command("make_test", ["-j", "4"])


def test_git_status_blocks_config_injection() -> None:
    with pytest.raises(CommandRejected, match="config injection"):
        resolve_command("git_status", ["-c", "alias.x=!rm -rf /"])


def test_forbidden_pr_base_default_refuses_main_master_release() -> None:
    """Default regex is unchanged from iter-2 — main/master/release/* refused."""
    for base in ["main", "master", "release/1.0"]:
        with pytest.raises(CommandRejected, match="forbidden"):
            resolve_command(
                "gh_pr_create",
                ["--head", "agent/be/foo", "--base", base, "--title", "x", "--body", "y"],
            )


def test_forbidden_pr_base_env_override_allows_main_for_ai_team_self_repo() -> None:
    """ai_team self-repo exception: setting the env to only refuse master/release
    lets main through as a valid PR base."""
    try:
        set_forbidden_pr_base_re(r"^(master|release/.*)$")
        # main is now allowed (ai_team self-repo case)
        argv = resolve_command(
            "gh_pr_create",
            ["--head", "agent/be/foo", "--base", "main", "--title", "x", "--body", "y"],
        )
        assert "main" in argv
        # master still refused
        with pytest.raises(CommandRejected, match="forbidden"):
            resolve_command(
                "gh_pr_create",
                ["--head", "agent/be/foo", "--base", "master", "--title", "x", "--body", "y"],
            )
    finally:
        set_forbidden_pr_base_re(r"^(main|master|release/.*)$")  # restore default


def test_forbidden_pr_base_set_then_reset_does_not_leak() -> None:
    """Setter is idempotent — last-write-wins; default behaviour restored after reset."""
    set_forbidden_pr_base_re(r"^never-merge$")
    try:
        # main is no longer forbidden under this override
        argv = resolve_command(
            "gh_pr_create",
            ["--head", "agent/be/foo", "--base", "main", "--title", "x", "--body", "y"],
        )
        assert "main" in argv
    finally:
        set_forbidden_pr_base_re(r"^(main|master|release/.*)$")
    # After reset, default applies again
    with pytest.raises(CommandRejected, match="forbidden"):
        resolve_command(
            "gh_pr_create",
            ["--head", "agent/be/foo", "--base", "main", "--title", "x", "--body", "y"],
        )
