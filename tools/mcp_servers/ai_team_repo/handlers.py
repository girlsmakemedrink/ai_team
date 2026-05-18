"""Tool implementations for ai_team_repo.

Each handler takes a `Context` (the per-process scope/config) and a dict
of MCP tool arguments, returns a `ToolResult` (dict shaped for the MCP
`tools/call` response). Handlers do NOT raise; they return
`{"isError": True, "text": ...}` so the agent gets a structured rejection.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from dataclasses import dataclass
from typing import Any

from tools.mcp_servers.ai_team_repo.commands import (
    CommandRejected,
    resolve_command,
)
from tools.mcp_servers.ai_team_repo.scope import ScopeConfig, ScopeError, resolve_in_scope

_BRANCH_ALLOWED_RE = re.compile(r"^agent/[a-z0-9_]+/[a-zA-Z0-9._\-/]+$")
_DEFAULT_FORBID_BRANCH_RE = re.compile(r"^(main|master|release/.*)$")
_RUN_SHELL_OUTPUT_LIMIT = 8000  # bytes per stdout/stderr returned; truncate beyond


@dataclass(slots=True, frozen=True)
class Context:
    scope: ScopeConfig
    forbid_branch_re: re.Pattern[str]
    default_pr_base: str

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> Context:
        e = env if env is not None else dict(os.environ)
        root = e.get("AI_TEAM_REPO_ROOT") or os.getcwd()
        prefixes = e.get("AI_TEAM_PATH_PREFIXES")
        scope = ScopeConfig.from_env(root, prefixes)
        forbid = e.get("AI_TEAM_FORBID_BRANCH_RE") or _DEFAULT_FORBID_BRANCH_RE.pattern
        return cls(
            scope=scope,
            forbid_branch_re=re.compile(forbid),
            default_pr_base=e.get("AI_TEAM_PR_BASE", "main"),
        )


def _err(text: str) -> dict[str, Any]:
    return {"isError": True, "content": [{"type": "text", "text": text}]}


def _ok(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "isError": False,
        "content": [{"type": "text", "text": json.dumps(payload, default=str)}],
        "structuredContent": payload,
    }


async def handle_status(ctx: Context, _: dict[str, Any]) -> dict[str, Any]:
    proc = await asyncio.create_subprocess_exec(
        "git",
        "status",
        "--short",
        "--branch",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=str(ctx.scope.root),
    )
    out, err = await proc.communicate()
    if proc.returncode != 0:
        return _err(f"git status failed: {err.decode(errors='replace')[:500]}")
    text = out.decode(errors="replace")
    lines = [ln for ln in text.splitlines() if ln]
    branch = ""
    untracked: list[str] = []
    modified: list[str] = []
    for ln in lines:
        if ln.startswith("## "):
            # `## branch...origin/branch [ahead 1]` → branch is the first segment.
            branch = ln[3:].split("...", 1)[0].split()[0]
        elif ln.startswith("?? "):
            untracked.append(ln[3:])
        else:
            modified.append(ln[3:].strip())
    return _ok(
        {
            "branch": branch,
            "is_dirty": bool(modified or untracked),
            "modified": modified,
            "untracked_files": untracked,
        }
    )


async def handle_create_branch(ctx: Context, args: dict[str, Any]) -> dict[str, Any]:
    branch = str(args.get("branch", ""))
    base = str(args.get("base") or ctx.default_pr_base)
    if not _BRANCH_ALLOWED_RE.match(branch):
        return _err(f"branch {branch!r} not allowed; must match agent/<role>/<slug>")
    if ctx.forbid_branch_re.match(branch):
        return _err(f"branch {branch!r} is forbidden by AI_TEAM_FORBID_BRANCH_RE")
    proc = await asyncio.create_subprocess_exec(
        "git",
        "checkout",
        "-b",
        branch,
        base,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=str(ctx.scope.root),
    )
    _, err = await proc.communicate()
    if proc.returncode != 0:
        return _err(f"git checkout -b failed: {err.decode(errors='replace')[:500]}")
    return _ok({"branch": branch, "base": base, "created": True})


async def handle_write_file_in_scope(ctx: Context, args: dict[str, Any]) -> dict[str, Any]:
    path = str(args.get("path", ""))
    content = args.get("content", "")
    mode = str(args.get("mode", "create"))
    if mode not in {"create", "overwrite"}:
        return _err(f"mode must be 'create' or 'overwrite', got {mode!r}")
    if not isinstance(content, str):
        return _err(f"content must be a string, got {type(content).__name__}")
    try:
        resolved = resolve_in_scope(ctx.scope, path)
    except ScopeError as e:
        return _err(f"scope rejected: {e}")
    if mode == "create" and resolved.exists():
        return _err(f"file exists and mode=create: {path}")
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(content)
    return _ok({"path": path, "absolute_path": str(resolved), "bytes_written": len(content)})


async def handle_run_shell(ctx: Context, args: dict[str, Any]) -> dict[str, Any]:
    command_class = str(args.get("command_class", ""))
    raw_args = args.get("args", [])
    if not isinstance(raw_args, list) or not all(isinstance(a, str) for a in raw_args):
        return _err("args must be a list of strings")
    try:
        argv = resolve_command(command_class, raw_args)
    except CommandRejected as e:
        return _err(f"run_shell rejected: {e}")
    proc = await asyncio.create_subprocess_exec(
        *argv,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=str(ctx.scope.root),
    )
    out, err = await proc.communicate()
    return _ok(
        {
            "command_class": command_class,
            "argv": list(argv),
            "returncode": proc.returncode,
            "stdout": out.decode(errors="replace")[:_RUN_SHELL_OUTPUT_LIMIT],
            "stderr": err.decode(errors="replace")[:_RUN_SHELL_OUTPUT_LIMIT],
            "truncated": (len(out) > _RUN_SHELL_OUTPUT_LIMIT or len(err) > _RUN_SHELL_OUTPUT_LIMIT),
        }
    )


async def handle_open_pr(ctx: Context, args: dict[str, Any]) -> dict[str, Any]:
    head = str(args.get("head", ""))
    base = str(args.get("base") or ctx.default_pr_base)
    title = str(args.get("title", ""))
    body = str(args.get("body", ""))
    if not _BRANCH_ALLOWED_RE.match(head):
        return _err(f"head {head!r} not allowed; must match agent/<role>/<slug>")
    if ctx.forbid_branch_re.match(base):
        return _err(f"PR base {base!r} is forbidden by AI_TEAM_FORBID_BRANCH_RE")
    if not title.strip():
        return _err("PR title is required")
    proc = await asyncio.create_subprocess_exec(
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
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=str(ctx.scope.root),
    )
    out, err = await proc.communicate()
    if proc.returncode != 0:
        return _err(f"gh pr create failed: {err.decode(errors='replace')[:500]}")
    url = out.decode(errors="replace").strip()
    return _ok({"head": head, "base": base, "url": url})


HANDLERS = {
    "status": handle_status,
    "create_branch": handle_create_branch,
    "write_file_in_scope": handle_write_file_in_scope,
    "run_shell": handle_run_shell,
    "open_pr": handle_open_pr,
}
