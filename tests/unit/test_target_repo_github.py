"""Tests for GitHubTargetRepo identifier parsing + clone + ops."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

import pytest

from core.target_repo.github import GitHubTargetRepo, parse_github_identifier
from core.target_repo.self_bootstrap import GitCommandError, SelfBootstrapTargetRepo

if TYPE_CHECKING:
    from pathlib import Path


def test_parse_owner_slash_repo() -> None:
    owner, repo, ssh_url = parse_github_identifier("girlsmakemedrink/telegram-tech-publisher")
    assert owner == "girlsmakemedrink"
    assert repo == "telegram-tech-publisher"
    assert ssh_url == "git@github.com:girlsmakemedrink/telegram-tech-publisher.git"


def test_parse_https_url() -> None:
    owner, repo, ssh_url = parse_github_identifier(
        "https://github.com/girlsmakemedrink/telegram-tech-publisher"
    )
    assert owner == "girlsmakemedrink"
    assert repo == "telegram-tech-publisher"
    assert ssh_url == "git@github.com:girlsmakemedrink/telegram-tech-publisher.git"


def test_parse_https_url_with_dot_git_suffix() -> None:
    _, repo, ssh_url = parse_github_identifier(
        "https://github.com/girlsmakemedrink/telegram-tech-publisher.git"
    )
    assert repo == "telegram-tech-publisher"
    assert ssh_url == "git@github.com:girlsmakemedrink/telegram-tech-publisher.git"


def test_parse_ssh_url_passthrough() -> None:
    owner, repo, ssh_url = parse_github_identifier(
        "git@github.com:girlsmakemedrink/telegram-tech-publisher.git"
    )
    assert owner == "girlsmakemedrink"
    assert repo == "telegram-tech-publisher"
    assert ssh_url == "git@github.com:girlsmakemedrink/telegram-tech-publisher.git"


def test_parse_garbage_raises() -> None:
    with pytest.raises(ValueError, match="not a recognised GitHub identifier"):
        parse_github_identifier("not a repo")


def test_github_target_repo_is_a_self_bootstrap_subclass(tmp_path: Path) -> None:
    """Subclass relationship keeps subprocess + guards reused."""
    repo = GitHubTargetRepo("girlsmakemedrink/telegram-tech-publisher", workspaces_dir=tmp_path)
    assert isinstance(repo, SelfBootstrapTargetRepo)


def test_workspace_path_uses_double_dash_slug(tmp_path: Path) -> None:
    """`/` in owner/repo becomes `--` in the workspace dir name."""
    repo = GitHubTargetRepo("girlsmakemedrink/telegram-tech-publisher", workspaces_dir=tmp_path)
    assert repo.root == tmp_path / "girlsmakemedrink--telegram-tech-publisher"
    assert repo.name == "girlsmakemedrink/telegram-tech-publisher"
    assert repo.remote_url == "git@github.com:girlsmakemedrink/telegram-tech-publisher.git"
    assert repo.default_branch == "main"


def test_default_branch_can_be_overridden(tmp_path: Path) -> None:
    repo = GitHubTargetRepo(
        "girlsmakemedrink/telegram-tech-publisher",
        workspaces_dir=tmp_path,
        default_branch="develop",
    )
    assert repo.default_branch == "develop"


@pytest.mark.asyncio
async def test_ensure_local_clone_clones_when_missing(tmp_path: Path) -> None:
    """First call clones; workspace dir gets created."""
    repo = GitHubTargetRepo("girlsmakemedrink/telegram-tech-publisher", workspaces_dir=tmp_path)
    with patch("core.target_repo.github._run", new_callable=AsyncMock) as mock_run:

        def fake_clone(*args: object, **kwargs: object) -> tuple[int, str, str]:
            repo.root.mkdir(parents=True, exist_ok=True)
            (repo.root / ".git").mkdir()
            return (0, "", "")

        mock_run.side_effect = fake_clone
        result = await repo.ensure_local_clone()
    assert result == repo.root
    assert (repo.root / ".git").is_dir()
    # First call invokes `git clone <ssh_url> <dest>`.
    assert mock_run.await_args is not None
    args = mock_run.await_args.args
    assert args[0] == "git"
    assert args[1] == "clone"
    assert args[2] == "git@github.com:girlsmakemedrink/telegram-tech-publisher.git"


@pytest.mark.asyncio
async def test_ensure_local_clone_fetches_when_already_cloned(tmp_path: Path) -> None:
    """Second call fetches instead of re-cloning."""
    repo = GitHubTargetRepo("girlsmakemedrink/telegram-tech-publisher", workspaces_dir=tmp_path)
    repo.root.mkdir(parents=True)
    (repo.root / ".git").mkdir()
    with patch("core.target_repo.github._run", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = (0, "", "")
        result = await repo.ensure_local_clone()
    assert result == repo.root
    assert mock_run.await_args is not None
    args = mock_run.await_args.args
    assert args[0] == "git"
    assert args[1] == "fetch"
    assert args[2] == "--all"


@pytest.mark.asyncio
async def test_ensure_local_clone_raises_on_clone_failure(tmp_path: Path) -> None:
    repo = GitHubTargetRepo("girlsmakemedrink/telegram-tech-publisher", workspaces_dir=tmp_path)
    with patch("core.target_repo.github._run", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = (128, "", "fatal: repo not found")
        with pytest.raises(GitCommandError, match="git clone failed"):
            await repo.ensure_local_clone()
