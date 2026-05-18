"""Factory mapping a `target_repo` identifier to a concrete TargetRepo.

See ADR-009. The dispatcher resolves the optional
`TaskAssignmentPayload.target_repo` field via this factory before
forwarding the task to an agent. `GitHubTargetRepo` is intentionally
not implemented this iteration — the iter-2 scope is the self-bootstrap
and in-repo-example cases.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from core.target_repo.in_repo_example import InRepoExampleTargetRepo
from core.target_repo.self_bootstrap import SelfBootstrapTargetRepo

if TYPE_CHECKING:
    from pathlib import Path

# Recognised in-repo example identifiers. Keyed by the canonical string an
# agent passes; value = (sub-tree relative to ai_team root, target_repo name).
_IN_REPO_EXAMPLES: dict[str, tuple[str, str]] = {
    "examples/sandbox/idea-validator": (
        "examples/sandbox/idea-validator",
        "idea_validator",
    ),
}

# Matches `owner/repo` (no slashes inside parts) or any https?:// URL.
_GITHUB_RE = re.compile(r"^([a-zA-Z0-9._-]+/[a-zA-Z0-9._-]+|https?://.+)$")


def resolve_target_repo(identifier: str | None, *, ai_team_root: Path) -> SelfBootstrapTargetRepo:
    """Return a TargetRepo instance for the given identifier.

    - None → SelfBootstrapTargetRepo at `ai_team_root`.
    - A key in `_IN_REPO_EXAMPLES` → InRepoExampleTargetRepo.
    - `owner/repo` or a URL → NotImplementedError (deferred to first
      commercial product).
    - Anything else → ValueError.
    """
    if identifier is None:
        return SelfBootstrapTargetRepo(root=ai_team_root)

    if identifier in _IN_REPO_EXAMPLES:
        rel, name = _IN_REPO_EXAMPLES[identifier]
        return InRepoExampleTargetRepo(root=ai_team_root / rel, name=name)

    if _GITHUB_RE.match(identifier):
        raise NotImplementedError(
            "GitHubTargetRepo is deferred until the first commercial product. "
            f"Got identifier: {identifier!r}"
        )

    raise ValueError(
        f"unknown target_repo {identifier!r}; "
        f"allowed: None, {sorted(_IN_REPO_EXAMPLES)}, "
        "or owner/repo / URL (not yet supported)"
    )
