"""Tests for SelfBootstrapTargetRepo — the ai_team-improves-itself impl.

Per ADR-009: `push` refuses refs matching `^(main|master|release/.*)$`.
The MCP server's run_shell already enforces this at the tool boundary;
this test pins the same guarantee at the Python-call boundary so callers
that go through `TargetRepo` directly (e.g. the dispatcher when wiring
a task to an agent) get the same protection.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from core.target_repo.self_bootstrap import (
    ForbiddenBranchError,
    SelfBootstrapTargetRepo,
)

if TYPE_CHECKING:
    from pathlib import Path


@pytest.mark.asyncio
@pytest.mark.parametrize("branch", ["main", "master", "release/1.0", "release/2026-05"])
async def test_push_refuses_forbidden_branches(branch: str, tmp_path: Path) -> None:
    repo = SelfBootstrapTargetRepo(root=tmp_path)
    with pytest.raises(ForbiddenBranchError, match=branch):
        await repo.push(branch)


@pytest.mark.asyncio
@pytest.mark.parametrize("base", ["main", "master", "release/1.0"])
async def test_open_pr_refuses_forbidden_base(base: str, tmp_path: Path) -> None:
    """ADR-009: PRs target `develop` or a feature branch — never `main` etc.

    The ai_team self-repo exception (resolved decision: PRs may target
    `main` on ai_team only) is enforced at the agent-config layer, not
    here. `SelfBootstrapTargetRepo` keeps the strict rule by default;
    callers that want the exception construct with `default_branch='main'`
    AND must explicitly allow it via the upcoming registry, not here.
    """
    repo = SelfBootstrapTargetRepo(root=tmp_path)
    with pytest.raises(ForbiddenBranchError, match=base):
        await repo.open_pr(
            head="agent/architect/0010-foo",
            base=base,
            title="x",
            body="y",
        )


@pytest.mark.asyncio
async def test_stage_and_commit_rejects_path_outside_root(tmp_path: Path) -> None:
    """No agent shall stage `/etc/passwd` or `../sibling/file`."""
    root = tmp_path / "repo"
    root.mkdir()
    sibling = tmp_path / "outside.txt"
    sibling.write_text("nope")
    repo = SelfBootstrapTargetRepo(root=root)
    with pytest.raises(ValueError, match="outside repo root"):
        await repo.stage_and_commit(paths=[str(sibling)], message="oops", author="x")


@pytest.mark.asyncio
async def test_stage_and_commit_rejects_traversal_via_dotdot(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    repo = SelfBootstrapTargetRepo(root=root)
    with pytest.raises(ValueError, match="outside repo root"):
        await repo.stage_and_commit(paths=["../outside.txt"], message="oops", author="x")
