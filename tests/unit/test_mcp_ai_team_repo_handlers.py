"""Handler tests for ai_team_repo.

`handle_write_file_in_scope` + small helpers were the iter-2 coverage;
iter-20 adds `handle_create_branch` tests on a real tmp git repo to
pin the `git worktree add` isolation contract that closes iter-19
demo Caveat B. The subprocess-driven handlers (`handle_status`,
`handle_run_shell`, `handle_open_pr`) remain `# pragma: no cover`
and are exercised via the live JSON-RPC smoke + integration tests.
"""

from __future__ import annotations

import asyncio
import json
import re
import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest

from tools.mcp_servers.ai_team_repo.handlers import (
    Context,
    _err,
    _ok,
    handle_create_branch,
    handle_write_file_in_scope,
)
from tools.mcp_servers.ai_team_repo.scope import ScopeConfig


def _ctx(root: Path, prefixes: tuple[str, ...] = ("*",)) -> Context:
    return Context(
        scope=ScopeConfig(root=root.resolve(), allowed_prefixes=prefixes),
        forbid_branch_re=re.compile(r"^(main|master|release/.*)$"),
        default_pr_base="main",
    )


@pytest.fixture(autouse=True)
def _reset_active_worktree() -> Iterator[None]:
    """iter-20: _ACTIVE_WORKTREE is module-level (naturally scoped
    to one MCP server process, but pytest reuses the module across
    tests). Reset between tests so order doesn't matter."""
    from tools.mcp_servers.ai_team_repo import handlers

    handlers._ACTIVE_WORKTREE = None
    yield
    handlers._ACTIVE_WORKTREE = None


@pytest.fixture
def tmp_git_repo(tmp_path: Path) -> Path:
    """Initialise a real tmp git repo with one commit on `main`.
    Required by iter-20 worktree tests."""
    subprocess.run(
        ["git", "init", "-b", "main"], cwd=tmp_path, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "config", "user.email", "iter20@test.local"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "iter-20 test"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    (tmp_path / "README.md").write_text("# iter-20 test repo\n")
    subprocess.run(
        ["git", "add", "README.md"], cwd=tmp_path, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "commit", "-m", "initial"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    return tmp_path


def _orchestrator_head(repo: Path) -> str:
    """Return the symbolic-ref name of the repo's HEAD."""
    result = subprocess.run(
        ["git", "symbolic-ref", "--short", "HEAD"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    return result.stdout.decode().strip()


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


# === iter-20 Phase 1: handle_create_branch uses `git worktree add` ===


def test_create_branch_does_not_switch_orchestrator_head(
    tmp_git_repo: Path,
) -> None:
    """iter-20 Phase 1: handle_create_branch must use `git worktree
    add`, leaving the orchestrator's HEAD on its original branch.
    iter-19 demo's Backend used `git checkout -b` to switch the
    orchestrator's worktree to its own branch — surfaced in
    iter_19_demo_report.md Caveat B."""
    original_head = _orchestrator_head(tmp_git_repo)
    assert original_head == "main"

    ctx = _ctx(tmp_git_repo)
    result = asyncio.run(
        handle_create_branch(
            ctx,
            {
                "branch": "agent/backend_developer/iter-20-test",
                "base": "main",
            },
        )
    )

    assert result["isError"] is False, result
    # Orchestrator's HEAD unchanged
    assert _orchestrator_head(tmp_git_repo) == "main"
    # New worktree directory exists at the expected location
    expected_path = (
        tmp_git_repo
        / ".claude"
        / "agent-worktrees"
        / "agent_backend_developer_iter-20-test"
    )
    assert expected_path.is_dir()
    # And inside the worktree, HEAD is on the new branch
    inside_head = _orchestrator_head(expected_path)
    assert inside_head == "agent/backend_developer/iter-20-test"


def test_write_file_after_create_branch_lands_in_worktree(
    tmp_git_repo: Path,
) -> None:
    """After handle_create_branch sets the active worktree,
    write_file_in_scope's writes go INTO the worktree, not the
    orchestrator's tree."""
    ctx = _ctx(tmp_git_repo)
    cb_result = asyncio.run(
        handle_create_branch(
            ctx,
            {"branch": "agent/backend_developer/wf-test", "base": "main"},
        )
    )
    assert cb_result["isError"] is False, cb_result
    worktree = Path(cb_result["structuredContent"]["worktree_path"])

    wf_result = asyncio.run(
        handle_write_file_in_scope(
            ctx,
            {
                "path": "hello.txt",
                "content": "iter-20\n",
                "mode": "create",
            },
        )
    )
    assert wf_result["isError"] is False, wf_result
    # File exists in the worktree
    assert (worktree / "hello.txt").is_file()
    assert (worktree / "hello.txt").read_text() == "iter-20\n"
    # File does NOT exist in the orchestrator's tree
    assert not (tmp_git_repo / "hello.txt").exists()
