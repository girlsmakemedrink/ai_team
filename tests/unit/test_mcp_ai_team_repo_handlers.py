"""Handler tests for ai_team_repo.

Only `handle_write_file_in_scope` and the small helpers are tested here;
the subprocess-driven handlers (`handle_status`, `handle_create_branch`,
`handle_run_shell`, `handle_open_pr`) are marked `# pragma: no cover`
and exercised via the live JSON-RPC smoke + iter-2b's integration
tests when a real tmp git repo lands. The same iter-0 convention
applies to `ai_team_bus/__main__.py` and `ai_team_tasks/__main__.py`.
"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING

import pytest

from tools.mcp_servers.ai_team_repo.handlers import (
    Context,
    _err,
    _ok,
    handle_write_file_in_scope,
)
from tools.mcp_servers.ai_team_repo.scope import ScopeConfig

if TYPE_CHECKING:
    from pathlib import Path


def _ctx(root: Path, prefixes: tuple[str, ...] = ("*",)) -> Context:
    return Context(
        scope=ScopeConfig(root=root.resolve(), allowed_prefixes=prefixes),
        forbid_branch_re=re.compile(r"^(main|master|release/.*)$"),
        default_pr_base="main",
    )


def test_err_envelope_shape() -> None:
    result = _err("scope rejected")
    assert result == {
        "isError": True,
        "content": [{"type": "text", "text": "scope rejected"}],
    }


def test_ok_envelope_shape_includes_structured_content() -> None:
    payload = {"path": "x", "bytes_written": 42}
    result = _ok(payload)
    assert result["isError"] is False
    assert result["structuredContent"] == payload
    # text field is the JSON-serialised payload so clients without
    # structured-content support still get the data.
    parsed = json.loads(result["content"][0]["text"])
    assert parsed == payload


def test_context_from_env_uses_defaults(tmp_path: Path) -> None:
    """Missing env vars fall back to: cwd as root, `*` prefix, `main` PR
    base, default forbid-regex."""
    ctx = Context.from_env({"AI_TEAM_REPO_ROOT": str(tmp_path)})
    assert ctx.scope.root == tmp_path.resolve()
    assert ctx.scope.allowed_prefixes == ("*",)
    assert ctx.default_pr_base == "main"
    assert ctx.forbid_branch_re.match("main")


def test_context_from_env_honours_overrides(tmp_path: Path) -> None:
    ctx = Context.from_env(
        {
            "AI_TEAM_REPO_ROOT": str(tmp_path),
            "AI_TEAM_PATH_PREFIXES": "docs/adr,docs/architecture.md",
            "AI_TEAM_PR_BASE": "develop",
            "AI_TEAM_FORBID_BRANCH_RE": "^never-merge$",
        }
    )
    assert ctx.scope.allowed_prefixes == ("docs/adr", "docs/architecture.md")
    assert ctx.default_pr_base == "develop"
    assert ctx.forbid_branch_re.match("never-merge")
    assert not ctx.forbid_branch_re.match("main")


@pytest.mark.asyncio
async def test_write_file_in_scope_creates_new_file(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    result = await handle_write_file_in_scope(
        ctx, {"path": "docs/adr/0042-foo.md", "content": "hello", "mode": "create"}
    )
    assert result["isError"] is False
    assert (tmp_path / "docs" / "adr" / "0042-foo.md").read_text() == "hello"
    assert result["structuredContent"]["bytes_written"] == 5


@pytest.mark.asyncio
async def test_write_file_in_scope_create_mode_refuses_existing_file(
    tmp_path: Path,
) -> None:
    (tmp_path / "x.md").write_text("old")
    ctx = _ctx(tmp_path)
    result = await handle_write_file_in_scope(
        ctx, {"path": "x.md", "content": "new", "mode": "create"}
    )
    assert result["isError"] is True
    assert "exists" in result["content"][0]["text"]
    assert (tmp_path / "x.md").read_text() == "old"


@pytest.mark.asyncio
async def test_write_file_in_scope_overwrite_replaces(tmp_path: Path) -> None:
    (tmp_path / "x.md").write_text("old")
    ctx = _ctx(tmp_path)
    result = await handle_write_file_in_scope(
        ctx, {"path": "x.md", "content": "new", "mode": "overwrite"}
    )
    assert result["isError"] is False
    assert (tmp_path / "x.md").read_text() == "new"


@pytest.mark.asyncio
async def test_write_file_in_scope_rejects_invalid_mode(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    result = await handle_write_file_in_scope(
        ctx, {"path": "x.md", "content": "hi", "mode": "append"}
    )
    assert result["isError"] is True
    assert "mode" in result["content"][0]["text"]


@pytest.mark.asyncio
async def test_write_file_in_scope_rejects_non_string_content(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    result = await handle_write_file_in_scope(
        ctx, {"path": "x.md", "content": 42, "mode": "create"}
    )
    assert result["isError"] is True
    assert "string" in result["content"][0]["text"]


@pytest.mark.asyncio
async def test_write_file_in_scope_refuses_traversal(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    result = await handle_write_file_in_scope(
        ctx,
        {"path": "../../../etc/passwd", "content": "oops", "mode": "overwrite"},
    )
    assert result["isError"] is True
    assert "scope rejected" in result["content"][0]["text"]


@pytest.mark.asyncio
async def test_write_file_in_scope_refuses_out_of_prefix(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path, prefixes=("docs/adr",))
    result = await handle_write_file_in_scope(
        ctx,
        {"path": "src/main.py", "content": "x", "mode": "create"},
    )
    assert result["isError"] is True
    assert "outside allowed prefixes" in result["content"][0]["text"]


@pytest.mark.asyncio
async def test_write_file_in_scope_creates_parent_dirs(tmp_path: Path) -> None:
    """mkdir(parents=True, exist_ok=True) — agents shouldn't need to
    create intermediate directories explicitly."""
    ctx = _ctx(tmp_path)
    result = await handle_write_file_in_scope(
        ctx,
        {"path": "a/b/c/file.md", "content": "x", "mode": "create"},
    )
    assert result["isError"] is False
    assert (tmp_path / "a" / "b" / "c" / "file.md").exists()
