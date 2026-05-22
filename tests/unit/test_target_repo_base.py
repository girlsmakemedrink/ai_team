from pathlib import Path

import pytest

from core.target_repo.base import LintRunResult, PullRequest, RepoStatus, TargetRepo
from core.target_repo.base import (
    TestRunResult as _TestRunResult,  # rename to avoid pytest collection
)


def test_run_result_dataclass() -> None:
    r = _TestRunResult(passed=True, summary="all good", duration_s=1.2)
    assert r.passed is True
    assert r.failures == []


def test_lint_run_result_dataclass() -> None:
    r = LintRunResult(passed=False, issues_count=3, summary="ruff: 3")
    assert r.issues_count == 3


def test_pull_request_dataclass() -> None:
    pr = PullRequest(url="https://github.com/x/y/pull/1", number=1)
    assert pr.number == 1


def test_repo_status_default_untracked_empty() -> None:
    s = RepoStatus(branch="develop", is_dirty=False)
    assert s.untracked_files == []


def test_target_repo_cannot_be_instantiated() -> None:
    with pytest.raises(TypeError):
        TargetRepo()  # type: ignore[abstract]


def test_subclass_must_implement_abstract_methods() -> None:
    class Incomplete(TargetRepo):
        name = "x"
        root = Path("/tmp")

    with pytest.raises(TypeError):
        Incomplete()  # type: ignore[abstract]


class _MinimalRepo(TargetRepo):
    """Implements the abstract surface with placeholders; only here to
    instantiate TargetRepo for testing the concrete no-op method."""

    async def ensure_local_clone(self) -> Path:  # type: ignore[override]
        return self.root

    async def checkout(self, branch: str, *, base: str | None = None) -> None:  # type: ignore[override]
        return None

    async def stage_and_commit(self, paths, message, author):  # type: ignore[override]
        return "sha"

    async def push(self, branch: str) -> None:  # type: ignore[override]
        return None

    async def open_pr(self, *, head, base, title, body):  # type: ignore[override]
        raise NotImplementedError

    async def run_tests(self, command=None):  # type: ignore[override]
        raise NotImplementedError

    async def run_linter(self):  # type: ignore[override]
        raise NotImplementedError

    async def status(self):  # type: ignore[override]
        raise NotImplementedError


@pytest.mark.asyncio
async def test_prepare_for_task_default_is_noop(tmp_path: Path) -> None:
    repo = _MinimalRepo()
    repo.root = tmp_path
    # Should not raise, returns None.
    result = await repo.prepare_for_task()
    assert result is None


@pytest.mark.asyncio
async def test_self_bootstrap_inherits_default_prepare_for_task(tmp_path: Path) -> None:
    from core.target_repo.self_bootstrap import SelfBootstrapTargetRepo

    repo = SelfBootstrapTargetRepo(root=tmp_path)
    result = await repo.prepare_for_task()
    assert result is None


@pytest.mark.asyncio
async def test_in_repo_example_inherits_default_prepare_for_task(tmp_path: Path) -> None:
    from core.target_repo.in_repo_example import InRepoExampleTargetRepo

    # Use the same constructor shape as existing InRepoExample tests.
    repo = InRepoExampleTargetRepo(root=tmp_path, name="idea_validator")
    result = await repo.prepare_for_task()
    assert result is None
