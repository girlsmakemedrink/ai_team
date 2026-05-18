"""Integration tests for SelfBootstrapTargetRepo's active methods.

Each test spins up a real local git repo + a bare "remote" repo so we
can exercise the subprocess wrappers (`checkout`, `stage_and_commit`,
`push`, `run_tests`, `run_linter`, `status`) end-to-end without
touching GitHub. `open_pr` requires `gh` + a real GitHub remote and is
out of scope for unit-test layer; covered by the end-to-end demo.

Marked @pytest.mark.integration so they don't run in the pre-push hook
or `make test-unit`.
"""

# ruff: noqa: ASYNC221 - blocking subprocess.run is fine in async-test
# setup/verification; the production code under test uses async exec.

from __future__ import annotations

import os
import subprocess
from typing import TYPE_CHECKING

import pytest

from core.target_repo.self_bootstrap import (
    ForbiddenBranchError,
    SelfBootstrapTargetRepo,
)

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.integration


def _git(cwd: Path, *args: str) -> None:
    """Run a git command synchronously in `cwd`; fail loudly on non-zero.

    Used only inside async-test setup; the production code under test
    uses asyncio.create_subprocess_exec.
    """
    subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        env={
            **os.environ,
            "GIT_AUTHOR_NAME": "ci",
            "GIT_AUTHOR_EMAIL": "ci@x",
            "GIT_COMMITTER_NAME": "ci",
            "GIT_COMMITTER_EMAIL": "ci@x",
        },
    )


@pytest.fixture
def repo_with_remote(tmp_path: Path) -> tuple[Path, Path]:
    """A working repo on `main` with `origin` pointing at a tmp bare remote.

    Returns (working_tree, bare_remote_path).
    """
    remote = tmp_path / "remote.git"
    _git(tmp_path, "init", "--bare", str(remote))

    work = tmp_path / "work"
    work.mkdir()
    _git(work, "init", "--initial-branch=main")
    _git(work, "config", "user.email", "ci@x")
    _git(work, "config", "user.name", "ci")
    (work / "README.md").write_text("seed\n")
    _git(work, "add", "README.md")
    _git(work, "commit", "-m", "chore: seed")
    _git(work, "remote", "add", "origin", str(remote))
    _git(work, "push", "origin", "main")

    return work, remote


@pytest.mark.asyncio
async def test_checkout_creates_branch_off_base(repo_with_remote: tuple[Path, Path]) -> None:
    work, _ = repo_with_remote
    repo = SelfBootstrapTargetRepo(root=work)
    await repo.checkout("agent/backend_developer/iter2b-foo", base="main")
    head = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=work,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert head == "agent/backend_developer/iter2b-foo"


@pytest.mark.asyncio
async def test_checkout_refuses_protected_branch(repo_with_remote: tuple[Path, Path]) -> None:
    """The same forbidden-branch regex that guards push also guards
    checkout creation — we don't let an agent recreate `main` on a
    different SHA via TargetRepo.checkout."""
    work, _ = repo_with_remote
    repo = SelfBootstrapTargetRepo(root=work)
    with pytest.raises(ForbiddenBranchError, match="main"):
        await repo.checkout("main", base="main")


@pytest.mark.asyncio
async def test_stage_and_commit_returns_sha_and_persists_change(
    repo_with_remote: tuple[Path, Path],
) -> None:
    work, _ = repo_with_remote
    repo = SelfBootstrapTargetRepo(root=work)
    await repo.checkout("agent/backend_developer/iter2b-foo", base="main")
    (work / "src.py").write_text("print('hi')\n")
    sha = await repo.stage_and_commit(paths=["src.py"], message="feat: add src", author="ci <ci@x>")
    assert len(sha) == 40
    log = subprocess.run(
        ["git", "log", "-1", "--pretty=%H %s"],
        cwd=work,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert sha in log and "feat: add src" in log


@pytest.mark.asyncio
async def test_stage_and_commit_still_rejects_path_outside_root(tmp_path: Path) -> None:
    """The iter-2 safety guard stays in front of the active impl."""
    root = tmp_path / "repo"
    root.mkdir()
    (tmp_path / "outside.txt").write_text("x")
    repo = SelfBootstrapTargetRepo(root=root)
    with pytest.raises(ValueError, match="outside repo root"):
        await repo.stage_and_commit(paths=["../outside.txt"], message="oops", author="ci")


@pytest.mark.asyncio
async def test_push_pushes_agent_branch_to_remote(repo_with_remote: tuple[Path, Path]) -> None:
    work, remote = repo_with_remote
    repo = SelfBootstrapTargetRepo(root=work, remote_url=str(remote))
    await repo.checkout("agent/backend_developer/iter2b-pushtest", base="main")
    (work / "x.txt").write_text("y")
    await repo.stage_and_commit(paths=["x.txt"], message="feat: x", author="ci")
    await repo.push("agent/backend_developer/iter2b-pushtest")
    # Remote now has the branch.
    out = subprocess.run(
        ["git", "branch", "--list"],
        cwd=remote,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert "agent/backend_developer/iter2b-pushtest" in out


@pytest.mark.asyncio
async def test_push_refuses_main_master_release(
    repo_with_remote: tuple[Path, Path],
) -> None:
    """Guard from iter-2 still works against the active impl."""
    work, _ = repo_with_remote
    repo = SelfBootstrapTargetRepo(root=work)
    for branch in ["main", "master", "release/1.0"]:
        with pytest.raises(ForbiddenBranchError, match=branch):
            await repo.push(branch)


@pytest.mark.asyncio
async def test_run_tests_reports_passed_when_pytest_succeeds(
    tmp_path: Path,
) -> None:
    """We don't need a full git repo to run pytest — give the repo
    root a tiny test that passes, run, expect a passed result."""
    root = tmp_path / "tinyrepo"
    root.mkdir()
    (root / "test_smoke.py").write_text("def test_ok():\n    assert True\n")
    repo = SelfBootstrapTargetRepo(root=root)
    # Use a minimal pytest invocation that doesn't import the real project.
    result = await repo.run_tests(command="pytest -q test_smoke.py --no-header")
    assert result.passed is True
    assert result.duration_s >= 0


@pytest.mark.asyncio
async def test_run_tests_reports_failed_when_pytest_fails(tmp_path: Path) -> None:
    root = tmp_path / "tinyrepo"
    root.mkdir()
    (root / "test_smoke.py").write_text("def test_bad():\n    assert False\n")
    repo = SelfBootstrapTargetRepo(root=root)
    # `-v` so the FAILED <node> lines appear and `--tb=no` to avoid the
    # noisy traceback in the summary parse.
    result = await repo.run_tests(command="pytest -v --tb=no test_smoke.py --no-header")
    assert result.passed is False
    # Either the summary mentions "failed" or we extracted a failing node.
    assert "fail" in result.summary.lower() or result.failures


@pytest.mark.asyncio
async def test_status_returns_branch_and_dirty_flag(
    repo_with_remote: tuple[Path, Path],
) -> None:
    work, _ = repo_with_remote
    repo = SelfBootstrapTargetRepo(root=work)
    s = await repo.status()
    assert s.branch == "main"
    assert s.is_dirty is False

    (work / "untracked.txt").write_text("hi")
    s2 = await repo.status()
    assert s2.is_dirty is True
    assert "untracked.txt" in s2.untracked_files


@pytest.mark.asyncio
async def test_ensure_local_clone_is_noop_returning_root(tmp_path: Path) -> None:
    """For self-bootstrap, there's nothing to clone; the method just
    confirms the working tree exists. iter-2b shouldn't regress this."""
    root = tmp_path / "repo"
    root.mkdir()
    repo = SelfBootstrapTargetRepo(root=root)
    assert await repo.ensure_local_clone() == root
