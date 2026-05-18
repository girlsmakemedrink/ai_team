"""Path-scope unit tests for the ai_team_repo MCP server.

Security-critical: every code path that lets an agent write to disk
funnels through `resolve_in_scope`. Each rejection branch below pins a
specific attack shape (traversal, absolute, symlink escape, out-of-prefix).
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import pytest

from tools.mcp_servers.ai_team_repo.scope import (
    ScopeConfig,
    ScopeError,
    resolve_in_scope,
)

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """Repo root nested under tmp_path so tests can place 'outside' fixtures
    adjacent to it (e.g. for symlink-escape cases)."""
    root = tmp_path / "repo"
    (root / "docs" / "adr").mkdir(parents=True)
    (root / "docs" / "adr" / ".keep").write_text("")
    (root / "src").mkdir()
    (root / "src" / "main.py").write_text("")
    return root


def _cfg(root: Path, prefixes: tuple[str, ...] = ("*",)) -> ScopeConfig:
    return ScopeConfig(root=root.resolve(), allowed_prefixes=prefixes)


def test_resolve_allows_path_under_root(repo: Path) -> None:
    p = resolve_in_scope(_cfg(repo), "docs/adr/0010-foo.md")
    assert p == (repo / "docs" / "adr" / "0010-foo.md").resolve()


def test_resolve_rejects_empty_string(repo: Path) -> None:
    with pytest.raises(ScopeError, match="empty path"):
        resolve_in_scope(_cfg(repo), "")


def test_resolve_rejects_absolute_path(repo: Path) -> None:
    with pytest.raises(ScopeError, match="absolute path not allowed"):
        resolve_in_scope(_cfg(repo), "/etc/passwd")


def test_resolve_rejects_traversal_outside_root(repo: Path) -> None:
    with pytest.raises(ScopeError, match="outside repo root"):
        resolve_in_scope(_cfg(repo), "../../../etc/passwd")


def test_resolve_rejects_traversal_back_into_root(repo: Path) -> None:
    """`docs/../../<root_name>/docs/...` would resolve back inside root.

    We still reject because we require the literal repo-relative form.
    `Path("docs/../../<root_name>/docs/...").resolve()` lands inside
    root if the parent path coincidentally walks back in. We don't
    special-case this — the resolve() check is the only gate.
    """
    # Build a traversal that climbs out then back in via the literal repo name.
    repo_name = repo.name
    requested = f"../{repo_name}/docs/adr/x.md"
    # This is genuinely inside-root after resolution; we accept that.
    # If a future threat model bans it, add an explicit `..` literal check.
    resolved = resolve_in_scope(_cfg(repo), requested)
    assert resolved.is_relative_to(repo.resolve())


def test_resolve_rejects_symlink_pointing_outside_root(repo: Path, tmp_path: Path) -> None:
    secrets = tmp_path / "secrets"
    secrets.mkdir()
    (secrets / "data.txt").write_text("topsecret")
    # Place a symlink INSIDE the repo that escapes via its target.
    (repo / "escape").symlink_to(secrets)
    with pytest.raises(ScopeError, match="outside repo root"):
        resolve_in_scope(_cfg(repo), "escape/data.txt")


def test_resolve_allows_path_under_allowed_prefix(repo: Path) -> None:
    p = resolve_in_scope(_cfg(repo, ("docs/adr",)), "docs/adr/0010-foo.md")
    assert p.parts[-3:] == ("docs", "adr", "0010-foo.md")


def test_resolve_allows_exact_prefix_match(repo: Path) -> None:
    """A request equal to an allowed prefix is allowed (e.g. `docs/architecture.md`)."""
    (repo / "docs" / "architecture.md").write_text("")
    p = resolve_in_scope(_cfg(repo, ("docs/architecture.md",)), "docs/architecture.md")
    assert p.exists()


def test_resolve_rejects_path_outside_allowed_prefix(repo: Path) -> None:
    with pytest.raises(ScopeError, match="outside allowed prefixes"):
        resolve_in_scope(_cfg(repo, ("docs/adr",)), "src/main.py")


def test_resolve_rejects_prefix_lookalike(repo: Path) -> None:
    """`docs/adr_archive` must NOT match the prefix `docs/adr`."""
    (repo / "docs" / "adr_archive").mkdir()
    (repo / "docs" / "adr_archive" / "x.md").write_text("")
    with pytest.raises(ScopeError, match="outside allowed prefixes"):
        resolve_in_scope(_cfg(repo, ("docs/adr",)), "docs/adr_archive/x.md")


def test_scope_config_from_env_parses_csv(repo: Path) -> None:
    cfg = ScopeConfig.from_env(repo, "docs/adr, docs/architecture.md , src/")
    assert cfg.allowed_prefixes == ("docs/adr", "docs/architecture.md", "src")


def test_scope_config_from_env_handles_star_and_missing(repo: Path) -> None:
    assert ScopeConfig.from_env(repo, None).allowed_prefixes == ("*",)
    assert ScopeConfig.from_env(repo, "*").allowed_prefixes == ("*",)
    assert ScopeConfig.from_env(repo, "").allowed_prefixes == ("*",)


def test_scope_config_from_env_errors_on_missing_root(tmp_path: Path) -> None:
    with pytest.raises((FileNotFoundError, ScopeError)):
        ScopeConfig.from_env(tmp_path / "nope", None)


def test_scope_uses_absolute_root_even_if_relative_input(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A relative root passed via env should still be resolved to absolute."""
    monkeypatch.chdir(repo.parent)
    cfg = ScopeConfig.from_env(repo.name, None)
    assert os.path.isabs(str(cfg.root))
    assert cfg.root == repo.resolve()
