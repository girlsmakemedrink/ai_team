"""Command-class enum for `run_shell` — the "Bash never raw" registry.

Per ADR-004: an agent receives `mcp__ai_team_repo__run_shell` instead of
the raw `Bash` tool. Every shell command name is one of a fixed enum;
the per-class validator below decides which arg shapes are permitted.

Anything not in this registry is refused with a structured error. To
add a class, add a registry entry — there is no "fall through to
arbitrary shell" path by design.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence


class CommandRejected(ValueError):
    """Raised when a command_class or its args violate the registry."""


@dataclass(slots=True, frozen=True)
class CommandSpec:
    argv0: tuple[str, ...]  # base argv that prefixes every invocation
    validate: Callable[[Sequence[str]], None]  # raises CommandRejected on bad args


def _no_extra_args_starting_with_dash_dash(args: Sequence[str]) -> None:
    """Allow flags but never bare `--` followed by arbitrary tokens — that
    is pytest's way of passing args to the program-under-test, which would
    let an agent smuggle arbitrary shell-like content into a test driver."""
    if any(a == "--" for a in args):
        raise CommandRejected("`--` separator not allowed (would bypass arg checks)")


_PYTEST_PLUGIN_PREFIX_LEN = 2  # length of "-p" itself; longer means "-p<value>"


def _validate_pytest(args: Sequence[str]) -> None:
    _no_extra_args_starting_with_dash_dash(args)
    # Disallow plugin auto-loading via -p / -P style hooks pointing at agent paths.
    for a in args:
        if a.startswith("-p") and len(a) > _PYTEST_PLUGIN_PREFIX_LEN and "/" in a:
            raise CommandRejected(f"pytest plugin path not allowed: {a!r}")


def _validate_simple_check(_: Sequence[str]) -> None:
    """ruff / mypy: any arg shape is fine, they have no shell-escape primitive."""


_BRANCH_ALLOWED_RE = re.compile(r"^agent/[a-z0-9_]+/[a-zA-Z0-9._\-/]+$")


def _validate_git_status(args: Sequence[str]) -> None:
    for a in args:
        if a in {"--exec", "-c"}:
            raise CommandRejected(f"git flag {a!r} not allowed (config injection)")


def _validate_git_diff(args: Sequence[str]) -> None:
    _validate_git_status(args)


_GIT_ADD_ALLOWED_FLAGS = frozenset({"-A", "--all", "-u", "--update"})


def _validate_git_add(args: Sequence[str]) -> None:
    if not args:
        raise CommandRejected("git_add requires at least one path")
    for a in args:
        # Flags get tighter scrutiny; only --all / --update are safe.
        if a.startswith("-") and a not in _GIT_ADD_ALLOWED_FLAGS:
            raise CommandRejected(f"git_add flag not allowed: {a!r}")


def _validate_git_commit(args: Sequence[str]) -> None:
    has_message = False
    for i, a in enumerate(args):
        if a in {"--amend", "--allow-empty"}:
            raise CommandRejected(f"git_commit flag not allowed: {a!r}")
        if a in {"-m", "--message"} or a.startswith("--message="):
            has_message = True
        if i > 0 and args[i - 1] in {"-m", "--message"}:
            has_message = True
    if not has_message:
        raise CommandRejected("git_commit requires -m '<message>'")


_GIT_PUSH_FEATURE_MIN_POSITIONALS = 2  # remote + branch


def _validate_git_push_feature(args: Sequence[str]) -> None:
    # We expect: [remote, branch] or [-u, remote, branch]. Branch must
    # match the agent/* whitelist regardless of position.
    branch_candidates = [a for a in args if not a.startswith("-")]
    if len(branch_candidates) < _GIT_PUSH_FEATURE_MIN_POSITIONALS:
        raise CommandRejected("git_push_feature requires <remote> <branch>")
    branch = branch_candidates[-1]
    if not _BRANCH_ALLOWED_RE.match(branch):
        raise CommandRejected(
            f"git_push_feature refuses branch {branch!r}; only matches agent/<role>/<slug>"
        )


# Mutable so per-target-repo configuration can override (see `set_forbidden_pr_base_re`).
# Default matches ADR-009: agents never PR-into main/master/release/*. The ai_team
# self-repo exception (PRs may target main) is set via the env at server startup,
# not by changing this default — keeps the safer behaviour for unknown targets.
_FORBIDDEN_PR_BASE_RE: re.Pattern[str] = re.compile(r"^(main|master|release/.*)$")


def set_forbidden_pr_base_re(pattern: str) -> None:
    """Replace the regex used by `gh_pr_create` to reject PR base branches.

    Called by `handlers.Context.from_env` so the MCP server reads
    `AI_TEAM_FORBID_PR_BASE_RE` once at startup. The ai_team self-repo
    spawn passes `^(master|release/.*)$` (drops `main` from the
    forbidden set); other targets keep the default.
    """
    global _FORBIDDEN_PR_BASE_RE  # noqa: PLW0603 - server-startup config; module-singleton is intentional
    _FORBIDDEN_PR_BASE_RE = re.compile(pattern)


def _validate_gh_pr_create(args: Sequence[str]) -> None:
    # Look for --base <value> or --base=value; refuse forbidden targets.
    it = iter(enumerate(args))
    for i, a in it:
        if a == "--base" and i + 1 < len(args):
            base = args[i + 1]
        elif a.startswith("--base="):
            base = a.split("=", 1)[1]
        else:
            continue
        if _FORBIDDEN_PR_BASE_RE.match(base):
            raise CommandRejected(
                f"gh_pr_create base {base!r} is forbidden; "
                "iter-2 expects develop or a feature branch"
            )


def _validate_make_test(args: Sequence[str]) -> None:
    # Only `test` / `test-unit` / `test-integration` targets; refuse arbitrary targets.
    allowed = {"test", "test-unit", "test-integration", "test-smoke"}
    if not args:
        return  # bare `make test` is fine (defaults applied in COMMANDS)
    for a in args:
        if a.startswith("-"):
            raise CommandRejected(f"make_test flag not allowed: {a!r}")
        if a not in allowed:
            raise CommandRejected(f"make_test target not allowed: {a!r}; allowed={sorted(allowed)}")


COMMANDS: dict[str, CommandSpec] = {
    "pytest": CommandSpec(("uv", "run", "pytest"), _validate_pytest),
    "ruff": CommandSpec(("uv", "run", "ruff"), _validate_simple_check),
    "mypy": CommandSpec(("uv", "run", "mypy"), _validate_simple_check),
    "git_status": CommandSpec(("git", "status"), _validate_git_status),
    "git_diff": CommandSpec(("git", "diff"), _validate_git_diff),
    "git_add": CommandSpec(("git", "add"), _validate_git_add),
    "git_commit": CommandSpec(("git", "commit"), _validate_git_commit),
    "git_push_feature": CommandSpec(("git", "push"), _validate_git_push_feature),
    "gh_pr_create": CommandSpec(("gh", "pr", "create"), _validate_gh_pr_create),
    "make_test": CommandSpec(("make",), _validate_make_test),
}


def resolve_command(command_class: str, args: Sequence[str]) -> tuple[str, ...]:
    """Validate (class, args) and return the full argv tuple to spawn.

    Raises CommandRejected on unknown class or invalid args. The returned
    argv is safe to pass to `asyncio.create_subprocess_exec` directly.
    """
    spec = COMMANDS.get(command_class)
    if spec is None:
        raise CommandRejected(
            f"unknown command_class {command_class!r}; allowed={sorted(COMMANDS)}"
        )
    spec.validate(args)
    return spec.argv0 + tuple(args)
