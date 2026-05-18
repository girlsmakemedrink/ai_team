"""TargetRepo ABC. See ADR-009.

Concrete implementations (SelfBootstrap, InRepoExample, GitHub) land in
Iteration 2 alongside the first repo-touching agent. Here we keep just
the contract so dependent code can be developed against it.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path


@dataclass(slots=True)
class TestRunResult:
    passed: bool
    summary: str
    duration_s: float
    failures: list[str] = field(default_factory=list)


@dataclass(slots=True)
class LintRunResult:
    passed: bool
    issues_count: int
    summary: str


@dataclass(slots=True)
class PullRequest:
    url: str
    number: int


@dataclass(slots=True)
class RepoStatus:
    branch: str
    is_dirty: bool
    untracked_files: list[str] = field(default_factory=list)


class TargetRepo(ABC):
    """Anything an agent might want to do to a code repository, abstracted."""

    name: str
    root: Path
    default_branch: str = "main"
    remote_url: str | None = None

    @abstractmethod
    async def ensure_local_clone(self) -> Path: ...

    @abstractmethod
    async def checkout(self, branch: str, *, base: str | None = None) -> None: ...

    @abstractmethod
    async def stage_and_commit(self, paths: Sequence[str], message: str, author: str) -> str:
        """Returns commit SHA."""

    @abstractmethod
    async def push(self, branch: str) -> None: ...

    @abstractmethod
    async def open_pr(self, *, head: str, base: str, title: str, body: str) -> PullRequest: ...

    @abstractmethod
    async def run_tests(self, command: str | None = None) -> TestRunResult: ...

    @abstractmethod
    async def run_linter(self) -> LintRunResult: ...

    @abstractmethod
    async def status(self) -> RepoStatus: ...
