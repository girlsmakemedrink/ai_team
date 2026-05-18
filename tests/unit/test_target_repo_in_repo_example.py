"""Tests for InRepoExampleTargetRepo — sub-tree training-task impl.

Per ADR-009: this target's `root` is a sub-tree of `ai_team` (e.g.
`examples/sandbox/idea-validator/`) and `remote_url` is None — the
sub-tree commits land on ai_team branches. The key safety property is
that `stage_and_commit` refuses paths outside the sub-tree EVEN IF
they would be inside the parent ai_team repo: an idea-validator agent
must not edit ai_team's own source.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from core.target_repo.in_repo_example import InRepoExampleTargetRepo

if TYPE_CHECKING:
    from pathlib import Path


@pytest.mark.asyncio
async def test_constructor_sets_root_and_no_remote(tmp_path: Path) -> None:
    parent = tmp_path / "ai_team"
    subtree = parent / "examples" / "sandbox" / "idea-validator"
    subtree.mkdir(parents=True)
    repo = InRepoExampleTargetRepo(root=subtree, name="idea_validator")
    assert repo.root == subtree
    assert repo.name == "idea_validator"
    assert repo.remote_url is None


@pytest.mark.asyncio
async def test_stage_and_commit_refuses_path_in_parent_repo(tmp_path: Path) -> None:
    """Paths inside ai_team but outside the sub-tree must be refused."""
    parent = tmp_path / "ai_team"
    subtree = parent / "examples" / "sandbox" / "idea-validator"
    subtree.mkdir(parents=True)
    (parent / "src").mkdir()
    (parent / "src" / "main.py").write_text("# ai_team's own code")

    repo = InRepoExampleTargetRepo(root=subtree, name="idea_validator")
    with pytest.raises(ValueError, match="outside repo root"):
        await repo.stage_and_commit(paths=["../../../src/main.py"], message="oops", author="x")
