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
