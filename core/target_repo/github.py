"""GitHubTargetRepo — clones an external GitHub repo to a workspace
directory and operates on it via the SelfBootstrapTargetRepo subprocess
plumbing. See ADR-009.
"""

from __future__ import annotations

import re
from pathlib import Path

from core.target_repo.self_bootstrap import (
    GitCommandError,
    SelfBootstrapTargetRepo,
    _run,
)

# `owner/repo` (no slashes inside parts), or https?://github.com/owner/repo[.git],
# or git@github.com:owner/repo[.git]
_OWNER_REPO_RE = re.compile(r"^([a-zA-Z0-9._-]+)/([a-zA-Z0-9._-]+?)(?:\.git)?$")
_HTTPS_RE = re.compile(r"^https?://github\.com/([a-zA-Z0-9._-]+)/([a-zA-Z0-9._-]+?)(?:\.git)?/?$")
_SSH_RE = re.compile(r"^git@github\.com:([a-zA-Z0-9._-]+)/([a-zA-Z0-9._-]+?)(?:\.git)?$")


def parse_github_identifier(identifier: str) -> tuple[str, str, str]:
    """Parse identifier → (owner, repo, ssh_url).

    Accepts: `owner/repo`, `https://github.com/owner/repo[.git]`,
    `git@github.com:owner/repo[.git]`. Returns the canonical SSH URL so
    clone/push reuse the owner's local SSH credentials.
    """
    for pat in (_HTTPS_RE, _SSH_RE, _OWNER_REPO_RE):
        m = pat.match(identifier)
        if m:
            owner, repo = m.group(1), m.group(2)
            return owner, repo, f"git@github.com:{owner}/{repo}.git"
    raise ValueError(f"not a recognised GitHub identifier: {identifier!r}")


_DEFAULT_WORKSPACES_DIR = Path.home() / ".ai_team" / "workspaces"


class GitHubTargetRepo(SelfBootstrapTargetRepo):
    """`TargetRepo` for an external GitHub repository.

    Inherits commit/push/test/lint behavior from `SelfBootstrapTargetRepo`.
    Differs in:
    - `__init__` parses an identifier (owner/repo or URL) and computes a
      workspace path under `~/.ai_team/workspaces/<owner>--<repo>/`.
    - `ensure_local_clone` clones on first call, fetches on subsequent.

    Auth: `gh` CLI handles both clone and PR creation; clone protocol
    (https / ssh) follows `gh config get -h github.com git_protocol`.
    `push` uses whatever `origin` was set by `gh repo clone`, so it
    inherits the same credential helper.
    """

    def __init__(
        self,
        identifier: str,
        *,
        workspaces_dir: Path | None = None,
        default_branch: str = "main",
    ) -> None:
        owner, repo, ssh_url = parse_github_identifier(identifier)
        ws_dir = workspaces_dir if workspaces_dir is not None else _DEFAULT_WORKSPACES_DIR
        root = ws_dir / f"{owner}--{repo}"
        super().__init__(root=root, remote_url=ssh_url, default_branch=default_branch)
        # Override the class-level `name = "ai_team"` from the parent.
        self.name = f"{owner}/{repo}"
        self._owner_repo = f"{owner}/{repo}"

    async def ensure_local_clone(self) -> Path:
        if (self.root / ".git").is_dir():
            rc, _out, err = await _run("git", "fetch", "--all", cwd=self.root)
            if rc != 0:
                raise GitCommandError(f"git fetch failed: {err.strip()[:500]}")
            return self.root
        self.root.parent.mkdir(parents=True, exist_ok=True)
        # `gh repo clone` respects the user's gh auth + configured protocol
        # (https/ssh) — avoids requiring a separate SSH key when the owner
        # is already gh-authenticated. Falls back to the same credential
        # path as every other `gh` call in the codebase.
        rc, _out, err = await _run(
            "gh",
            "repo",
            "clone",
            self._owner_repo,
            str(self.root),
            cwd=self.root.parent,
            timeout_s=300,
        )
        if rc != 0:
            raise GitCommandError(f"gh repo clone failed: {err.strip()[:500]}")
        return self.root
