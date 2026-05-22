"""GitHubTargetRepo — clones an external GitHub repo to a workspace
directory and operates on it via the SelfBootstrapTargetRepo subprocess
plumbing. See ADR-009.
"""

from __future__ import annotations

import re

# `owner/repo` (no slashes inside parts), or https?://github.com/owner/repo[.git],
# or git@github.com:owner/repo[.git]
_OWNER_REPO_RE = re.compile(r"^([a-zA-Z0-9._-]+)/([a-zA-Z0-9._-]+?)(?:\.git)?$")
_HTTPS_RE = re.compile(
    r"^https?://github\.com/([a-zA-Z0-9._-]+)/([a-zA-Z0-9._-]+?)(?:\.git)?/?$"
)
_SSH_RE = re.compile(
    r"^git@github\.com:([a-zA-Z0-9._-]+)/([a-zA-Z0-9._-]+?)(?:\.git)?$"
)


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
