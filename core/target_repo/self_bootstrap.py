"""SelfBootstrapTargetRepo — the ai_team-improves-itself impl. See ADR-009.

iter-2 shipped the security guards (push/PR-base refusal, stage-and-commit
path-scope). iter-2b fills in the subprocess wrappers behind those guards
so Python callers (dispatcher, tests, future tooling) can use the methods
directly. Agents still reach the same operations via the MCP server —
both paths share the same regex constants and refuse the same branches.
"""

from __future__ import annotations

import asyncio
import os
import re
import shlex
import time
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


class GitCommandError(RuntimeError):
    """Raised when a subprocess git/gh/pytest invocation returns non-zero."""


async def _run(
    *cmd: str,
    cwd: Path,
    timeout_s: int = 120,
    env: dict[str, str] | None = None,
) -> tuple[int, str, str]:
    """Run a subprocess and return (returncode, stdout, stderr).

    Inherits parent env unless caller supplies an override.
    """
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=str(cwd),
        env={**os.environ, **(env or {})} if env else None,
    )
    out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
    return proc.returncode or 0, out.decode(errors="replace"), err.decode(errors="replace")


async def _git_check(cwd: Path, *args: str) -> str:
    """Run git, raise on non-zero, return stdout."""
    rc, out, err = await _run("git", *args, cwd=cwd)
    if rc != 0:
        raise GitCommandError(f"git {args!r} failed (rc={rc}): {err.strip()[:500]}")
    return out


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
        # Self-bootstrap is always-local: the working tree already exists.
        # Caller is responsible for ensuring it's a valid git repo.
        return self.root

    async def checkout(self, branch: str, *, base: str | None = None) -> None:
        if _FORBIDDEN_BRANCH_RE.match(branch):
            raise ForbiddenBranchError(f"refusing to create protected branch {branch!r}")
        base_ref = base or self.default_branch
        await _git_check(self.root, "checkout", "-b", branch, base_ref)

    async def stage_and_commit(self, paths: Sequence[str], message: str, author: str) -> str:
        # Path-scope guard runs BEFORE the subprocess so a malformed call
        # still gets the security failure, not a less specific git error.
        root_resolved = self.root.resolve()
        for p in paths:
            candidate = Path(p)
            abs_path = (candidate if candidate.is_absolute() else (self.root / candidate)).resolve()
            try:
                abs_path.relative_to(root_resolved)
            except ValueError as e:
                raise ValueError(f"path {p!r} resolves outside repo root {root_resolved}") from e
        await _git_check(self.root, "add", "--", *paths)
        # `--author` for traceability; the dispatcher passes "<Role Name>
        # via ai_team <role@ai-team.local>" per ADR-009's branch model.
        await _git_check(self.root, "commit", "-m", message, "--author", author)
        sha = (await _git_check(self.root, "rev-parse", "HEAD")).strip()
        return sha

    async def push(self, branch: str) -> None:
        if _FORBIDDEN_BRANCH_RE.match(branch):
            raise ForbiddenBranchError(f"refusing to push to protected branch {branch!r}")
        await _git_check(self.root, "push", "origin", branch)

    async def open_pr(self, *, head: str, base: str, title: str, body: str) -> PullRequest:
        if _FORBIDDEN_BRANCH_RE.match(base):
            raise ForbiddenBranchError(f"refusing PR with forbidden base {base!r}")
        # `gh pr create` needs a real GitHub remote; for the ai_team
        # self-repo this is the owner's gh-authenticated session.
        rc, out, err = await _run(
            "gh",
            "pr",
            "create",
            "--head",
            head,
            "--base",
            base,
            "--title",
            title,
            "--body",
            body,
            cwd=self.root,
        )
        if rc != 0:
            raise GitCommandError(f"gh pr create failed: {err.strip()[:500]}")
        url = out.strip()
        # The URL is the last line of stdout; extract the PR number from it.
        try:
            number = int(url.rsplit("/", 1)[-1])
        except ValueError:
            number = 0
        return PullRequest(url=url, number=number)

    async def run_tests(self, command: str | None = None) -> TestRunResult:
        # Default to a quick pytest pass; callers can pass a tighter selector.
        argv = shlex.split(command) if command else ["pytest", "-q"]
        start = time.perf_counter()
        rc, out, err = await _run(*argv, cwd=self.root, timeout_s=600)
        duration = round(time.perf_counter() - start, 2)
        # Crude failure parse: pytest's bare summary line lists failing nodes.
        failures = [line for line in (out + "\n" + err).splitlines() if line.startswith("FAILED ")][
            :50
        ]
        return TestRunResult(
            passed=(rc == 0),
            summary=(out.strip().splitlines()[-1] if out.strip() else err.strip()[:500]),
            duration_s=duration,
            failures=failures,
        )

    async def run_linter(self) -> LintRunResult:
        rc, out, err = await _run("ruff", "check", ".", cwd=self.root)
        # ruff returns 0 when clean, 1 with issues found, 2 on its own errors.
        # We count non-empty stdout lines as the issues count (rough).
        issues = [line for line in out.splitlines() if line and not line.startswith(" ")]
        return LintRunResult(
            passed=(rc == 0),
            issues_count=len(issues) if rc != 0 else 0,
            summary=(out.strip().splitlines()[-1] if out.strip() else err.strip()[:500]),
        )

    async def status(self) -> RepoStatus:
        out = await _git_check(self.root, "status", "--short", "--branch")
        lines = out.splitlines()
        branch = ""
        untracked: list[str] = []
        is_dirty = False
        for ln in lines:
            if ln.startswith("## "):
                branch = ln[3:].split("...", 1)[0].split()[0]
            elif ln.startswith("?? "):
                untracked.append(ln[3:])
                is_dirty = True
            else:
                is_dirty = True
        return RepoStatus(branch=branch, is_dirty=is_dirty, untracked_files=untracked)
