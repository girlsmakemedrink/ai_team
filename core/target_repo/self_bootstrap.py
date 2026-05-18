"""SelfBootstrapTargetRepo — the ai_team-improves-itself impl. See ADR-009.

iter-2 scope: the security-critical guards (push/PR branch refusal,
stage-and-commit path-scope) are implemented and tested. The actual
git subprocess calls (checkout, the rest of stage_and_commit, push,
open_pr, run_tests, run_linter, status) are deferred — agents reach
these operations via the `mcp__ai_team_repo__*` server, not via this
class's Python methods. The class exists so the dispatcher can pass a
typed handle (root, name, default_branch, remote_url) through to MCP
configuration and the agent context. The methods will fill in across
iter-2b and iter-3 as Python call-sites appear.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

from core.target_repo.base import (
    LintRunResult,
    PullRequest,
    RepoStatus,
    TargetRepo,
    TestRunResult,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

# Refs an agent must never push/PR-into. Same regex as the MCP server's
# command-class validators — duplicated rather than shared, because the
# `tools/mcp_servers` package and `core/` package don't otherwise depend
# on each other and a single regex isn't worth a coupling.
_FORBIDDEN_BRANCH_RE = re.compile(r"^(main|master|release/.*)$")


class ForbiddenBranchError(RuntimeError):
    """Raised when an agent tries to push/PR-target a protected branch."""


class SelfBootstrapTargetRepo(TargetRepo):
    name = "ai_team"

    def __init__(
        self,
        root: Path,
        *,
        remote_url: str | None = None,
        default_branch: str = "main",
    ) -> None:
        self.root = root
        self.remote_url = remote_url
        self.default_branch = default_branch

    async def ensure_local_clone(self) -> Path:
        return self.root

    async def checkout(self, branch: str, *, base: str | None = None) -> None:
        raise NotImplementedError(
            "Python TargetRepo.checkout is iter-2b; use mcp__ai_team_repo__create_branch"
        )

    async def stage_and_commit(self, paths: Sequence[str], message: str, author: str) -> str:
        # Path-scope guard runs BEFORE NotImplementedError so a malformed call
        # still gets the security failure, not the deferred-impl message.
        root_resolved = self.root.resolve()
        for p in paths:
            candidate = Path(p)
            abs_path = (candidate if candidate.is_absolute() else (self.root / candidate)).resolve()
            try:
                abs_path.relative_to(root_resolved)
            except ValueError as e:
                raise ValueError(f"path {p!r} resolves outside repo root {root_resolved}") from e
        raise NotImplementedError(
            "Python TargetRepo.stage_and_commit is iter-2b; "
            "use mcp__ai_team_repo__run_shell(git_add)+(git_commit)"
        )

    async def push(self, branch: str) -> None:
        if _FORBIDDEN_BRANCH_RE.match(branch):
            raise ForbiddenBranchError(f"refusing to push to protected branch {branch!r}")
        raise NotImplementedError(
            "Python TargetRepo.push is iter-2b; use mcp__ai_team_repo__run_shell(git_push_feature)"
        )

    async def open_pr(self, *, head: str, base: str, title: str, body: str) -> PullRequest:
        if _FORBIDDEN_BRANCH_RE.match(base):
            raise ForbiddenBranchError(f"refusing PR with forbidden base {base!r}")
        raise NotImplementedError(
            "Python TargetRepo.open_pr is iter-2b; use mcp__ai_team_repo__open_pr"
        )

    async def run_tests(self, command: str | None = None) -> TestRunResult:
        raise NotImplementedError(
            "Python TargetRepo.run_tests is iter-2b; use mcp__ai_team_repo__run_shell(pytest)"
        )

    async def run_linter(self) -> LintRunResult:
        raise NotImplementedError(
            "Python TargetRepo.run_linter is iter-2b; use mcp__ai_team_repo__run_shell(ruff)"
        )

    async def status(self) -> RepoStatus:
        raise NotImplementedError(
            "Python TargetRepo.status is iter-2b; use mcp__ai_team_repo__status"
        )
