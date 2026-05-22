"""Integration test: prepare_for_task against a real local bare repo.

Marked `@pytest.mark.integration` — skipped in the default unit run.
No network, no `gh` — just `git`. Tests the actual subprocess plumbing
end-to-end against real git state.
"""

from __future__ import annotations

import shutil
import subprocess
from typing import TYPE_CHECKING

import pytest

from core.target_repo.github import GitHubTargetRepo
from core.target_repo.self_bootstrap import GitCommandError

if TYPE_CHECKING:
    from pathlib import Path


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(shutil.which("git") is None, reason="requires git"),
]


def _git(cwd: Path, *args: str) -> str:
    """Run git synchronously, return stdout, raise on non-zero."""
    result = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git {args} failed: {result.stderr}")
    return result.stdout


def _setup_origin_with_main(origin_dir: Path) -> None:
    """Create a bare repo with one commit on main."""
    _git(origin_dir.parent, "init", "--bare", "--initial-branch=main", str(origin_dir))
    bootstrap = origin_dir.parent / "_bootstrap"
    _git(origin_dir.parent, "clone", str(origin_dir), str(bootstrap))
    _git(bootstrap, "config", "user.email", "test@test")
    _git(bootstrap, "config", "user.name", "Test")
    (bootstrap / "README.md").write_text("v1\n")
    _git(bootstrap, "add", "README.md")
    _git(bootstrap, "commit", "-m", "v1")
    _git(bootstrap, "branch", "-M", "main")
    _git(bootstrap, "push", "-u", "origin", "main")


def _make_workspace_clone(origin_dir: Path, workspace: Path) -> None:
    _git(workspace.parent, "clone", str(origin_dir), str(workspace))
    _git(workspace, "config", "user.email", "test@test")
    _git(workspace, "config", "user.name", "Test")


@pytest.mark.asyncio
async def test_prepare_for_task_resets_feature_branch_to_main(tmp_path: Path) -> None:
    origin = tmp_path / "origin.git"
    workspace = tmp_path / "ws"
    _setup_origin_with_main(origin)
    _make_workspace_clone(origin, workspace)
    _git(workspace, "checkout", "-b", "agent/devops/feat")
    (workspace / "file.txt").write_text("x\n")
    _git(workspace, "add", "file.txt")
    _git(workspace, "commit", "-m", "feat")

    repo = GitHubTargetRepo.__new__(GitHubTargetRepo)
    repo.root = workspace
    repo.default_branch = "main"

    await repo.prepare_for_task()

    branch = _git(workspace, "rev-parse", "--abbrev-ref", "HEAD").strip()
    assert branch == "main"


@pytest.mark.asyncio
async def test_prepare_for_task_raises_on_dirty_workspace_real_git(tmp_path: Path) -> None:
    origin = tmp_path / "origin.git"
    workspace = tmp_path / "ws"
    _setup_origin_with_main(origin)
    _make_workspace_clone(origin, workspace)
    (workspace / "dirty.txt").write_text("dirty\n")

    repo = GitHubTargetRepo.__new__(GitHubTargetRepo)
    repo.root = workspace
    repo.default_branch = "main"

    with pytest.raises(GitCommandError, match="uncommitted changes"):
        await repo.prepare_for_task()

    assert (workspace / "dirty.txt").exists()


@pytest.mark.asyncio
async def test_prepare_for_task_raises_on_diverged_local_main_real_git(
    tmp_path: Path,
) -> None:
    origin = tmp_path / "origin.git"
    workspace = tmp_path / "ws"
    _setup_origin_with_main(origin)
    _make_workspace_clone(origin, workspace)
    (workspace / "drift.txt").write_text("drift\n")
    _git(workspace, "add", "drift.txt")
    _git(workspace, "commit", "-m", "drift")
    bootstrap = tmp_path / "_bootstrap"
    (bootstrap / "origin-side.txt").write_text("origin\n")
    _git(bootstrap, "add", "origin-side.txt")
    _git(bootstrap, "commit", "-m", "origin-side")
    _git(bootstrap, "push", "origin", "main")

    repo = GitHubTargetRepo.__new__(GitHubTargetRepo)
    repo.root = workspace
    repo.default_branch = "main"

    with pytest.raises(GitCommandError, match="diverged from origin/main"):
        await repo.prepare_for_task()

    log = _git(workspace, "log", "--oneline", "-5")
    assert "drift" in log
