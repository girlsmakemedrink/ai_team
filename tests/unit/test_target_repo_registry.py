"""Tests for the TargetRepo factory. See ADR-009.

The factory resolves a string identifier from `TaskAssignmentPayload.target_repo`
to a concrete `TargetRepo` instance. Three input shapes are recognized:

- `None`                                      → SelfBootstrapTargetRepo
- `"examples/sandbox/idea-validator"`         → InRepoExampleTargetRepo
- `"<owner>/<repo>"` or `"https://github.com/…"`
                                              → NotImplementedError (deferred)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from core.target_repo.in_repo_example import InRepoExampleTargetRepo
from core.target_repo.registry import resolve_target_repo
from core.target_repo.self_bootstrap import SelfBootstrapTargetRepo

if TYPE_CHECKING:
    from pathlib import Path


def test_resolve_none_returns_self_bootstrap(tmp_path: Path) -> None:
    """`target_repo=None` defaults to the ai_team self-bootstrap repo."""
    repo = resolve_target_repo(None, ai_team_root=tmp_path)
    assert isinstance(repo, SelfBootstrapTargetRepo)
    assert repo.root == tmp_path
    assert repo.name == "ai_team"


def test_resolve_idea_validator_returns_in_repo_example(tmp_path: Path) -> None:
    subtree = tmp_path / "examples" / "sandbox" / "idea-validator"
    subtree.mkdir(parents=True)
    repo = resolve_target_repo("examples/sandbox/idea-validator", ai_team_root=tmp_path)
    assert isinstance(repo, InRepoExampleTargetRepo)
    assert repo.root == subtree
    assert repo.name == "idea_validator"
    assert repo.remote_url is None


def test_resolve_owner_slash_repo_not_yet_supported(tmp_path: Path) -> None:
    with pytest.raises(NotImplementedError, match="GitHubTargetRepo"):
        resolve_target_repo("girlsmakemedrink/some-product", ai_team_root=tmp_path)


def test_resolve_github_url_not_yet_supported(tmp_path: Path) -> None:
    with pytest.raises(NotImplementedError, match="GitHubTargetRepo"):
        resolve_target_repo("https://github.com/girlsmakemedrink/x", ai_team_root=tmp_path)


def test_resolve_unknown_in_repo_path_rejected(tmp_path: Path) -> None:
    """A repo-relative path that isn't a recognised example is an error,
    not a silent fallback to self-bootstrap."""
    with pytest.raises(ValueError, match="unknown target_repo"):
        resolve_target_repo("examples/whatever/else", ai_team_root=tmp_path)
