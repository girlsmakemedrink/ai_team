"""Path-scope resolver for ai_team_repo.

The single point at which an agent-supplied path becomes a real
filesystem path. Every code path that writes inside the repo MUST go
through `resolve_in_scope` so traversal (`..`), symlink escape, and
out-of-role writes are all rejected before any I/O.

Threat model assumptions:
- The repo root is trusted (we never put untrusted files into it that
  could be malicious symlinks).
- The caller is the LLM agent — assumed semi-trusted, may be confused
  or prompt-injected.
- The agent has no way to bypass this resolver: it's only reachable via
  the MCP tools, and `--allowed-tools` blocks raw `Write`/`Edit`/`Bash`.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence


class ScopeError(ValueError):
    """Raised when a requested path violates the path-scope contract."""


@dataclass(slots=True, frozen=True)
class ScopeConfig:
    root: Path  # absolute, resolved
    allowed_prefixes: tuple[str, ...]  # repo-relative; ("*",) means "anywhere under root"

    @classmethod
    def from_env(cls, root: str | Path, prefixes_csv: str | None) -> ScopeConfig:
        resolved_root = Path(root).expanduser().resolve(strict=True)
        if not resolved_root.is_dir():
            raise ScopeError(f"AI_TEAM_REPO_ROOT is not a directory: {resolved_root}")
        if not prefixes_csv or prefixes_csv.strip() == "*":
            allowed: tuple[str, ...] = ("*",)
        else:
            allowed = tuple(p.strip().strip("/") for p in prefixes_csv.split(",") if p.strip())
        return cls(root=resolved_root, allowed_prefixes=allowed)


def resolve_in_scope(cfg: ScopeConfig, requested: str) -> Path:
    """Map an agent-supplied repo-relative path to a safe absolute Path.

    Raises ScopeError on any of:
    - empty string
    - absolute path
    - path that resolves outside the repo root (e.g. `..`, symlink escape)
    - path that lies outside the configured allowed prefixes
    """
    if not requested or not requested.strip():
        raise ScopeError("empty path")
    candidate = Path(requested)
    if candidate.is_absolute():
        raise ScopeError(f"absolute path not allowed: {requested!r}")

    abs_candidate = (cfg.root / candidate).resolve()
    try:
        rel = abs_candidate.relative_to(cfg.root)
    except ValueError as e:
        raise ScopeError(f"path resolves outside repo root: {requested!r} → {abs_candidate}") from e

    if cfg.allowed_prefixes != ("*",):
        rel_posix = rel.as_posix()
        if not _matches_any_prefix(rel_posix, cfg.allowed_prefixes):
            raise ScopeError(f"path outside allowed prefixes {cfg.allowed_prefixes}: {rel_posix!r}")
    return abs_candidate


def _matches_any_prefix(rel_posix: str, prefixes: Sequence[str]) -> bool:
    """True iff rel_posix equals one of `prefixes`, or sits under one as a directory."""
    for p in prefixes:
        normalized = p.strip("/")
        if not normalized:
            continue
        if rel_posix == normalized:
            return True
        if rel_posix.startswith(normalized + "/"):
            return True
    return False
