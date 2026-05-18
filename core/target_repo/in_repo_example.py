"""InRepoExampleTargetRepo — sub-tree of ai_team treated as its own target.

Used for the iter-2 training task (`examples/sandbox/idea-validator/`).
Identical safety semantics to `SelfBootstrapTargetRepo` — push/PR-base
guards, path-scope guard on commits — but `root` is the sub-tree and
`remote_url` is None (commits land on ai_team branches).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from core.target_repo.self_bootstrap import SelfBootstrapTargetRepo

if TYPE_CHECKING:
    from pathlib import Path


class InRepoExampleTargetRepo(SelfBootstrapTargetRepo):
    """Target repo backed by a sub-tree of ai_team. See ADR-009."""

    def __init__(self, root: Path, *, name: str, default_branch: str = "main") -> None:
        super().__init__(root=root, remote_url=None, default_branch=default_branch)
        self.name = name
