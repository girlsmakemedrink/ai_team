# Iter-28 Implementation Plan — `GitHubTargetRepo` (close ADR-009 carry-over)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement `GitHubTargetRepo` in `core/target_repo/`, completing the third concrete implementation of `TargetRepo` (per ADR-009). After this iter, ai_team agents can be pointed at an external GitHub product repo (initially `girlsmakemedrink/telegram-tech-publisher`) via the same `TargetRepo` interface they already use for self-bootstrap and the sandbox idea-validator. End-state: `make smoke-github-target-repo` clones the product repo, runs `status() / run_linter() / run_tests()` against it, and prints all three results successfully. Agent invocations against the new repo are out of scope (queued for iter-29).

**Architecture:** Inherit `GitHubTargetRepo` from `SelfBootstrapTargetRepo` so all subprocess plumbing (`_run`, `_git_check`, forbidden-branch guards, path-scope validation) is reused as-is. The only behavioral differences are: (a) `__init__` parses an `owner/repo` or URL identifier and constructs a workspace path under `~/.ai_team/workspaces/<owner>--<repo>/`, and (b) `ensure_local_clone` performs a real `git clone` on first call and a `git fetch --all` on subsequent calls. Registry's `NotImplementedError` branch becomes a `GitHubTargetRepo` constructor call. No changes to dispatcher, agents, or message schemas.

**Tech Stack:** Existing ai_team stack — Python 3.11, `asyncio.create_subprocess_exec`, `git` + `gh` CLI for repo ops, owner's SSH key for clone/push, pytest + pytest-asyncio for tests. No new dependencies.

**Source spec inputs:**
- `docs/adr/0009-target-repo-abstraction.md` — interface contract (locked).
- `docs/iterations/iter_27_retro.md` — recommended option (a): build `GitHubTargetRepo` first.
- `docs/iterations/iter_27_handoff.md` — iter-28 priorities (this iter = priority #1).
- `core/target_repo/self_bootstrap.py` — pattern to inherit from.
- `core/target_repo/registry.py:50–54` — the `NotImplementedError` branch to replace.

**Owner action items inherited from iter-27 retro:**
1. Token rotation — owner reports done (2026-05-22 EOD).
2. README "Run smoke locally" section on product repo — P2, deferred to iter-29.
3. Backport "branch BEFORE first commit" reminder to ai_team CLAUDE.md — P3, ship in Phase C of this iter.

---

## Non-Goals (out of scope for iter-28)

- **Agent invocations against the product repo.** No `TL`, `Backend`, etc. chains — that's iter-29. iter-28 just makes the impl available; no end-to-end agent demo.
- **PR auto-merge from agents.** Agents can `open_pr()` but owner approval gate still applies per existing rules.
- **Workspace GC.** ADR-009 mentions "GC workspaces unused > 14 days" — defer. Manual cleanup (`rm -rf ~/.ai_team/workspaces/<slug>`) is fine for one repo.
- **PAT-based auth.** Rely on owner's `gh` CLI auth + SSH key for `git@github.com:`. PATs come when we have multi-tenant or CI use.
- **`develop` branch enforcement on the product repo.** The product repo (`telegram-tech-publisher`) has only `main` — ADR-009 says "PRs target `develop` (or the repo's configured default working branch)". Use `main` as the configured default for this repo; revisit if a `develop` flow is added later.
- **`core/config.py` changes.** The default `workspaces_dir` is hardcoded to `~/.ai_team/workspaces/`; constructor accepts an override arg for tests. No env var, no settings field — YAGNI.
- **Closing other iter-26b carry-overs** (HoldQueue persistence, BaseAgent refactor, audit_writer role, etc.). Single-focus iter.
- **Product-repo README "Run smoke locally" section.** P2, deferred to iter-29.

---

## File Structure

### Created

- `core/target_repo/github.py` — `GitHubTargetRepo` class + identifier parser. Inherits from `SelfBootstrapTargetRepo`; overrides `__init__` and `ensure_local_clone`. Exports `parse_github_identifier()` helper (returns `(owner, repo, ssh_url)` tuple) for the registry to reuse.
- `tests/unit/test_target_repo_github.py` — unit tests for identifier parsing + workspace path computation + `ensure_local_clone` with mocked subprocess.
- `tests/integration/test_target_repo_github_clone.py` — `@pytest.mark.integration`; real clone of `girlsmakemedrink/telegram-tech-publisher` + `status()` + `run_linter()` calls. Skips if `gh auth status` fails.
- `scripts/smoke_github_target_repo.sh` — end-to-end smoke against the product repo; prints clone path + status + lint + tests results.
- `docs/iterations/iter_28_retro.md` — written in Phase C.
- `docs/iterations/iter_28_handoff.md` — written in Phase C.

### Modified

- `core/target_repo/registry.py` — replace `NotImplementedError` branch (lines 50–54) with `GitHubTargetRepo(identifier)`. Add `default_branch` kwarg (defaults to `"main"`) so the product repo's single-branch model is explicit at call site.
- `core/target_repo/__init__.py` — re-export `GitHubTargetRepo`.
- `tests/unit/test_target_repo_registry.py` — update `test_resolve_owner_slash_repo_not_yet_supported` and `test_resolve_github_url_not_yet_supported` to assert success (return `GitHubTargetRepo`) instead of `NotImplementedError`. Add a test that the workspace path is computed correctly.
- `Makefile` — add `smoke-github-target-repo: scripts/smoke_github_target_repo.sh && bash $<` target. Add to `make help` listing.
- `CLAUDE.md` — under "Operating principles", add the "branch BEFORE first commit on a fresh-cloned repo" reminder (P3 from iter-27 retro). Update the "Current phase" paragraph to reflect iter-28 in Phase C.

---

## Phase A — `GitHubTargetRepo` impl + tests + registry wiring (Day 1, ~3-5h)

### Task A1: Identifier parser

**Files:**
- Create: `core/target_repo/github.py` (just the parser for now; class lands in A2)
- Create: `tests/unit/test_target_repo_github.py`

- [ ] **Step A1.1: Write the failing test for `parse_github_identifier`**

Add to `tests/unit/test_target_repo_github.py`:

```python
"""Tests for GitHubTargetRepo identifier parsing + clone + ops."""

from __future__ import annotations

import pytest

from core.target_repo.github import parse_github_identifier


def test_parse_owner_slash_repo() -> None:
    owner, repo, ssh_url = parse_github_identifier("girlsmakemedrink/telegram-tech-publisher")
    assert owner == "girlsmakemedrink"
    assert repo == "telegram-tech-publisher"
    assert ssh_url == "git@github.com:girlsmakemedrink/telegram-tech-publisher.git"


def test_parse_https_url() -> None:
    owner, repo, ssh_url = parse_github_identifier(
        "https://github.com/girlsmakemedrink/telegram-tech-publisher"
    )
    assert owner == "girlsmakemedrink"
    assert repo == "telegram-tech-publisher"
    assert ssh_url == "git@github.com:girlsmakemedrink/telegram-tech-publisher.git"


def test_parse_https_url_with_dot_git_suffix() -> None:
    _, repo, ssh_url = parse_github_identifier(
        "https://github.com/girlsmakemedrink/telegram-tech-publisher.git"
    )
    assert repo == "telegram-tech-publisher"
    assert ssh_url == "git@github.com:girlsmakemedrink/telegram-tech-publisher.git"


def test_parse_ssh_url_passthrough() -> None:
    owner, repo, ssh_url = parse_github_identifier(
        "git@github.com:girlsmakemedrink/telegram-tech-publisher.git"
    )
    assert owner == "girlsmakemedrink"
    assert repo == "telegram-tech-publisher"
    assert ssh_url == "git@github.com:girlsmakemedrink/telegram-tech-publisher.git"


def test_parse_garbage_raises() -> None:
    with pytest.raises(ValueError, match="not a recognised GitHub identifier"):
        parse_github_identifier("not a repo")
```

- [ ] **Step A1.2: Run tests, expect ImportError**

Run: `cd /Users/kirillterskih/ai_team && uv run pytest tests/unit/test_target_repo_github.py -v`

Expected: collection error — `ModuleNotFoundError: No module named 'core.target_repo.github'`.

- [ ] **Step A1.3: Implement `parse_github_identifier`**

Write `core/target_repo/github.py`:

```python
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
```

- [ ] **Step A1.4: Run tests, expect PASS**

Run: `cd /Users/kirillterskih/ai_team && uv run pytest tests/unit/test_target_repo_github.py -v`

Expected: 5 PASS.

- [ ] **Step A1.5: Lint + typecheck**

Run: `cd /Users/kirillterskih/ai_team && uv run ruff check core/target_repo/github.py tests/unit/test_target_repo_github.py && uv run mypy core/target_repo/github.py`

Expected: both clean.

- [ ] **Step A1.6: Commit**

```bash
cd /Users/kirillterskih/ai_team
git checkout -b feat/iter-28-github-target-repo
git add core/target_repo/github.py tests/unit/test_target_repo_github.py
git commit -m "feat(target-repo): add parse_github_identifier helper (iter-28 step 1/3)"
```

### Task A2: `GitHubTargetRepo` class + clone behavior

**Files:**
- Modify: `core/target_repo/github.py`
- Modify: `tests/unit/test_target_repo_github.py`

- [ ] **Step A2.1: Write the failing tests for the class**

Append to `tests/unit/test_target_repo_github.py`:

```python
from pathlib import Path
from unittest.mock import AsyncMock, patch

from core.target_repo.github import GitHubTargetRepo
from core.target_repo.self_bootstrap import SelfBootstrapTargetRepo


def test_github_target_repo_is_a_self_bootstrap_subclass(tmp_path: Path) -> None:
    """Subclass relationship keeps subprocess + guards reused."""
    repo = GitHubTargetRepo("girlsmakemedrink/telegram-tech-publisher", workspaces_dir=tmp_path)
    assert isinstance(repo, SelfBootstrapTargetRepo)


def test_workspace_path_uses_double_dash_slug(tmp_path: Path) -> None:
    """`/` in owner/repo becomes `--` in the workspace dir name."""
    repo = GitHubTargetRepo("girlsmakemedrink/telegram-tech-publisher", workspaces_dir=tmp_path)
    assert repo.root == tmp_path / "girlsmakemedrink--telegram-tech-publisher"
    assert repo.name == "girlsmakemedrink/telegram-tech-publisher"
    assert repo.remote_url == "git@github.com:girlsmakemedrink/telegram-tech-publisher.git"
    assert repo.default_branch == "main"


def test_default_branch_can_be_overridden(tmp_path: Path) -> None:
    repo = GitHubTargetRepo(
        "girlsmakemedrink/telegram-tech-publisher",
        workspaces_dir=tmp_path,
        default_branch="develop",
    )
    assert repo.default_branch == "develop"


@pytest.mark.asyncio
async def test_ensure_local_clone_clones_when_missing(tmp_path: Path) -> None:
    """First call clones; workspace dir gets created."""
    repo = GitHubTargetRepo("girlsmakemedrink/telegram-tech-publisher", workspaces_dir=tmp_path)
    with patch("core.target_repo.github._run", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = (0, "", "")
        # Simulate clone creating the directory.
        def fake_clone(*args: object, **kwargs: object) -> tuple[int, str, str]:
            repo.root.mkdir(parents=True, exist_ok=True)
            (repo.root / ".git").mkdir()
            return (0, "", "")

        mock_run.side_effect = fake_clone
        result = await repo.ensure_local_clone()
    assert result == repo.root
    assert (repo.root / ".git").is_dir()
    # First call invokes `git clone <ssh_url> <dest>`.
    args = mock_run.await_args.args
    assert args[0] == "git"
    assert args[1] == "clone"
    assert args[2] == "git@github.com:girlsmakemedrink/telegram-tech-publisher.git"


@pytest.mark.asyncio
async def test_ensure_local_clone_fetches_when_already_cloned(tmp_path: Path) -> None:
    """Second call fetches instead of re-cloning."""
    repo = GitHubTargetRepo("girlsmakemedrink/telegram-tech-publisher", workspaces_dir=tmp_path)
    repo.root.mkdir(parents=True)
    (repo.root / ".git").mkdir()
    with patch("core.target_repo.github._run", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = (0, "", "")
        result = await repo.ensure_local_clone()
    assert result == repo.root
    args = mock_run.await_args.args
    assert args[0] == "git"
    assert args[1] == "fetch"
    assert args[2] == "--all"


@pytest.mark.asyncio
async def test_ensure_local_clone_raises_on_clone_failure(tmp_path: Path) -> None:
    from core.target_repo.self_bootstrap import GitCommandError

    repo = GitHubTargetRepo("girlsmakemedrink/telegram-tech-publisher", workspaces_dir=tmp_path)
    with patch("core.target_repo.github._run", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = (128, "", "fatal: repo not found")
        with pytest.raises(GitCommandError, match="git clone failed"):
            await repo.ensure_local_clone()
```

- [ ] **Step A2.2: Run tests, expect FAIL**

Run: `cd /Users/kirillterskih/ai_team && uv run pytest tests/unit/test_target_repo_github.py -v`

Expected: 6 fails — `AttributeError: module 'core.target_repo.github' has no attribute 'GitHubTargetRepo'` (or similar) + `_run` import errors.

- [ ] **Step A2.3: Implement `GitHubTargetRepo`**

Append to `core/target_repo/github.py` (after the parser):

```python
from pathlib import Path

from core.target_repo.self_bootstrap import (
    GitCommandError,
    SelfBootstrapTargetRepo,
    _run,
)


_DEFAULT_WORKSPACES_DIR = Path.home() / ".ai_team" / "workspaces"


class GitHubTargetRepo(SelfBootstrapTargetRepo):
    """`TargetRepo` for an external GitHub repository.

    Inherits commit/push/test/lint behavior from `SelfBootstrapTargetRepo`.
    Differs in:
    - `__init__` parses an identifier (owner/repo or URL) and computes a
      workspace path under `~/.ai_team/workspaces/<owner>--<repo>/`.
    - `ensure_local_clone` clones on first call, fetches on subsequent.

    Auth: owner's SSH key for clone/push; owner's `gh` CLI for `open_pr`
    (inherited from parent).
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

    async def ensure_local_clone(self) -> Path:
        if (self.root / ".git").is_dir():
            rc, _out, err = await _run("git", "fetch", "--all", cwd=self.root)
            if rc != 0:
                raise GitCommandError(f"git fetch failed: {err.strip()[:500]}")
            return self.root
        # Workspace parent must exist before clone.
        self.root.parent.mkdir(parents=True, exist_ok=True)
        rc, _out, err = await _run(
            "git",
            "clone",
            str(self.remote_url),
            str(self.root),
            cwd=self.root.parent,
            timeout_s=300,
        )
        if rc != 0:
            raise GitCommandError(f"git clone failed: {err.strip()[:500]}")
        return self.root
```

- [ ] **Step A2.4: Run tests, expect PASS**

Run: `cd /Users/kirillterskih/ai_team && uv run pytest tests/unit/test_target_repo_github.py -v`

Expected: 11 PASS (5 from A1 + 6 from A2).

- [ ] **Step A2.5: Lint + typecheck**

Run: `cd /Users/kirillterskih/ai_team && uv run ruff check core/target_repo/github.py tests/unit/test_target_repo_github.py && uv run mypy core/target_repo/github.py`

Expected: both clean.

- [ ] **Step A2.6: Commit**

```bash
cd /Users/kirillterskih/ai_team
git add core/target_repo/github.py tests/unit/test_target_repo_github.py
git commit -m "feat(target-repo): add GitHubTargetRepo class (iter-28 step 2/3)"
```

### Task A3: Wire registry + re-export + update existing tests

**Files:**
- Modify: `core/target_repo/registry.py`
- Modify: `core/target_repo/__init__.py`
- Modify: `tests/unit/test_target_repo_registry.py`

- [ ] **Step A3.1: Update existing registry tests RED-first**

Edit `tests/unit/test_target_repo_registry.py`:

Replace `test_resolve_owner_slash_repo_not_yet_supported` and `test_resolve_github_url_not_yet_supported` with:

```python
from core.target_repo.github import GitHubTargetRepo


def test_resolve_owner_slash_repo_returns_github_target_repo(tmp_path: Path) -> None:
    repo = resolve_target_repo("girlsmakemedrink/telegram-tech-publisher", ai_team_root=tmp_path)
    assert isinstance(repo, GitHubTargetRepo)
    assert repo.name == "girlsmakemedrink/telegram-tech-publisher"
    assert repo.remote_url == "git@github.com:girlsmakemedrink/telegram-tech-publisher.git"


def test_resolve_github_url_returns_github_target_repo(tmp_path: Path) -> None:
    repo = resolve_target_repo(
        "https://github.com/girlsmakemedrink/telegram-tech-publisher", ai_team_root=tmp_path
    )
    assert isinstance(repo, GitHubTargetRepo)
    assert repo.name == "girlsmakemedrink/telegram-tech-publisher"
```

- [ ] **Step A3.2: Run registry tests, expect FAIL**

Run: `cd /Users/kirillterskih/ai_team && uv run pytest tests/unit/test_target_repo_registry.py -v`

Expected: 2 fails — `NotImplementedError: GitHubTargetRepo is deferred...`.

- [ ] **Step A3.3: Update the registry factory**

Edit `core/target_repo/registry.py` — replace lines 50–54:

```python
    if _GITHUB_RE.match(identifier):
        from core.target_repo.github import GitHubTargetRepo

        return GitHubTargetRepo(identifier)
```

The import is inside the branch (not module-level) so loading the registry doesn't pull in `github.py`'s `Path.home()` resolution at import time. The pattern matches how the registry already does lazy imports for impls. Also update `resolve_target_repo`'s return type annotation:

Find: `def resolve_target_repo(identifier: str | None, *, ai_team_root: Path) -> SelfBootstrapTargetRepo:`

Replace with: `def resolve_target_repo(identifier: str | None, *, ai_team_root: Path) -> SelfBootstrapTargetRepo | "GitHubTargetRepo":`

Add at top under `if TYPE_CHECKING:`:
```python
    from core.target_repo.github import GitHubTargetRepo
```

Update the docstring's third bullet from "deferred" to:
```
- `owner/repo` or a URL → GitHubTargetRepo (workspaces under
  ~/.ai_team/workspaces/<owner>--<repo>/).
```

- [ ] **Step A3.4: Re-export from package**

Edit `core/target_repo/__init__.py` to add `GitHubTargetRepo`:

Find the existing re-export block and add:
```python
from core.target_repo.github import GitHubTargetRepo
```

Add `"GitHubTargetRepo"` to the `__all__` list if one exists.

- [ ] **Step A3.5: Run all target_repo tests, expect PASS**

Run: `cd /Users/kirillterskih/ai_team && uv run pytest tests/unit/test_target_repo*.py -v`

Expected: all PASS (existing 5 self_bootstrap tests + 5 in_repo_example tests + 5 registry tests (3 unchanged + 2 updated) + 11 github tests = ~26 pass).

- [ ] **Step A3.6: Run full unit suite to catch regressions**

Run: `cd /Users/kirillterskih/ai_team && uv run pytest tests/unit/ -q`

Expected: 527+ pass (no regressions from existing baseline).

- [ ] **Step A3.7: Lint + typecheck the full diff**

Run: `cd /Users/kirillterskih/ai_team && uv run ruff check core/target_repo/ tests/unit/test_target_repo*.py && uv run mypy core/target_repo/`

Expected: clean.

- [ ] **Step A3.8: Commit**

```bash
cd /Users/kirillterskih/ai_team
git add core/target_repo/registry.py core/target_repo/__init__.py tests/unit/test_target_repo_registry.py
git commit -m "feat(target-repo): wire GitHubTargetRepo into registry + re-export (iter-28 step 3/3)"
```

### Task A4: PR + CI

- [ ] **Step A4.1: Push + open PR**

```bash
cd /Users/kirillterskih/ai_team
git push -u origin feat/iter-28-github-target-repo
gh pr create --title "feat(iter-28): GitHubTargetRepo — close ADR-009 carry-over" --body "$(cat <<'EOF'
## Summary

Implements `GitHubTargetRepo` per ADR-009. Inherits from
`SelfBootstrapTargetRepo` (all subprocess + guards reused); overrides
`__init__` and `ensure_local_clone`. Registry's `NotImplementedError`
branch becomes a real constructor call.

No agent code, dispatcher, or message schema changed.

## What's new

- `core/target_repo/github.py` — `GitHubTargetRepo` + `parse_github_identifier`.
- `tests/unit/test_target_repo_github.py` — 11 unit tests (parsing + class + clone behavior with mocked subprocess).
- `core/target_repo/registry.py` — wires `owner/repo` and URL identifiers to `GitHubTargetRepo`.
- `core/target_repo/__init__.py` — re-exports `GitHubTargetRepo`.
- `tests/unit/test_target_repo_registry.py` — updated 2 tests (deferred → success).

## Out of scope

- Agent invocations against the new repo (iter-29).
- Workspace GC (ADR-009 mentions; deferred).
- PAT-based auth (rely on owner's `gh` CLI + SSH key).
- Live smoke against the product repo (Phase B PR).

## Test plan

- [x] 11 new unit tests pass
- [x] No regressions on full unit suite (527+ pass)
- [x] ruff + mypy clean
- [ ] CI green
- [ ] Squash-merge when green

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step A4.2: Watch CI, squash-merge when green**

```bash
gh pr checks <PR#>          # wait for both lint+test and commitlint
gh pr merge <PR#> --squash --delete-branch
git checkout main && git pull --ff-only
```

---

## Phase B — Live smoke against `telegram-tech-publisher` (Day 2, ~1-2h)

### Task B1: Smoke script

**Files:**
- Create: `scripts/smoke_github_target_repo.sh`
- Modify: `Makefile`
- Create: `tests/integration/test_target_repo_github_clone.py`

- [ ] **Step B1.1: Branch from updated main**

```bash
cd /Users/kirillterskih/ai_team
git checkout main && git pull --ff-only
git checkout -b feat/iter-28-smoke-github-target-repo
```

- [ ] **Step B1.2: Write the smoke script**

Create `scripts/smoke_github_target_repo.sh`:

```bash
#!/usr/bin/env bash
# iter-28 smoke: clone girlsmakemedrink/telegram-tech-publisher via
# GitHubTargetRepo, then run status() / run_linter() / run_tests().
# Does not push. Prints all three results.

set -euo pipefail

cd "$(dirname "$0")/.."

# `gh auth status` must pass — clone uses SSH but we also need gh for any
# follow-up open_pr() (not exercised here, but the smoke validates the
# auth substrate).
if ! gh auth status >/dev/null 2>&1; then
  echo "ERROR: gh auth status failed. Run 'gh auth login' first." >&2
  exit 1
fi

uv run python -c "
import asyncio
from core.target_repo.github import GitHubTargetRepo


async def main() -> None:
    repo = GitHubTargetRepo('girlsmakemedrink/telegram-tech-publisher')
    print(f'workspace: {repo.root}')
    root = await repo.ensure_local_clone()
    print(f'cloned/fetched at: {root}')
    st = await repo.status()
    print(f'status: branch={st.branch} dirty={st.is_dirty} untracked={len(st.untracked_files)}')
    lint = await repo.run_linter()
    print(f'linter: passed={lint.passed} issues={lint.issues_count} -- {lint.summary}')
    # Use uv run pytest since the product repo is uv-managed.
    tests = await repo.run_tests('uv run pytest -q')
    print(f'tests: passed={tests.passed} duration={tests.duration_s}s -- {tests.summary}')


asyncio.run(main())
"
```

- [ ] **Step B1.3: Make it executable + add Makefile target**

```bash
chmod +x scripts/smoke_github_target_repo.sh
```

Edit `Makefile` — add to the targets block:

```makefile
smoke-github-target-repo:
	@bash scripts/smoke_github_target_repo.sh
```

Add `smoke-github-target-repo` to the `make help` listing if there's one.

- [ ] **Step B1.4: Run the smoke locally**

Run: `cd /Users/kirillterskih/ai_team && make smoke-github-target-repo`

Expected: prints workspace path, "cloned/fetched at: …", a status line with `branch=main dirty=False untracked=0`, a linter line (likely `passed=True issues=0`), and a tests line (likely `passed=True` with the product repo's pytest summary). The product repo has its own coverage + tests; we just exercise the substrate.

If any of the three operations fails, capture the error in the iter-28 retro under "What was harder than expected". Don't auto-merge until smoke succeeds.

- [ ] **Step B1.5: Write the integration test**

Create `tests/integration/test_target_repo_github_clone.py`:

```python
"""Integration test: real clone of the product repo + status() probe.

Marked `@pytest.mark.integration` — skipped in the default unit run.
Requires `gh auth status` and SSH access to GitHub. Clones into a tmp
workspace so it doesn't touch `~/.ai_team/workspaces/`.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from core.target_repo.github import GitHubTargetRepo

if TYPE_CHECKING:
    pass


def _gh_authed() -> bool:
    try:
        return subprocess.run(["gh", "auth", "status"], capture_output=True).returncode == 0
    except FileNotFoundError:
        return False


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not _gh_authed(), reason="requires `gh auth login`"),
    pytest.mark.skipif(shutil.which("git") is None, reason="requires git"),
]


@pytest.mark.asyncio
async def test_clone_and_status_against_real_product_repo(tmp_path: Path) -> None:
    repo = GitHubTargetRepo(
        "girlsmakemedrink/telegram-tech-publisher", workspaces_dir=tmp_path
    )
    root = await repo.ensure_local_clone()
    assert root.is_dir()
    assert (root / ".git").is_dir()
    assert (root / "pyproject.toml").is_file()
    st = await repo.status()
    assert st.branch == "main"
    assert st.is_dirty is False
```

- [ ] **Step B1.6: Run the integration test locally**

Run: `cd /Users/kirillterskih/ai_team && uv run pytest tests/integration/test_target_repo_github_clone.py -v -m integration`

Expected: 1 PASS (or SKIP if `gh auth status` fails — flag in PR body if skipped).

- [ ] **Step B1.7: Lint**

Run: `cd /Users/kirillterskih/ai_team && uv run ruff check scripts/smoke_github_target_repo.sh tests/integration/test_target_repo_github_clone.py`

Expected: clean (shellcheck if installed; otherwise ruff just skips the .sh).

- [ ] **Step B1.8: Commit**

```bash
cd /Users/kirillterskih/ai_team
git add scripts/smoke_github_target_repo.sh Makefile tests/integration/test_target_repo_github_clone.py
git commit -m "feat(iter-28): live smoke + integration test for GitHubTargetRepo"
```

### Task B2: PR + CI

- [ ] **Step B2.1: Push + open PR**

```bash
cd /Users/kirillterskih/ai_team
git push -u origin feat/iter-28-smoke-github-target-repo
gh pr create --title "feat(iter-28): live smoke + integration test for GitHubTargetRepo" --body "$(cat <<'EOF'
## Summary

Phase B of iter-28. Adds the end-to-end smoke pipeline against
`girlsmakemedrink/telegram-tech-publisher` and a `@pytest.mark.integration`
test that exercises a real clone.

## Smoke evidence (paste actual output here)

```
workspace: /Users/<owner>/.ai_team/workspaces/girlsmakemedrink--telegram-tech-publisher
cloned/fetched at: …
status: branch=main dirty=False untracked=0
linter: passed=True issues=0 -- …
tests: passed=True duration=…s -- …
```

## Test plan

- [x] `make smoke-github-target-repo` succeeds locally (see above)
- [x] Integration test passes locally
- [ ] CI green on lint+typecheck+unit (integration is opt-in, won't run in CI)
- [ ] Squash-merge when green

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step B2.2: Watch CI, squash-merge when green**

```bash
gh pr checks <PR#>
gh pr merge <PR#> --squash --delete-branch
git checkout main && git pull --ff-only
```

---

## Phase C — Wire-back: CLAUDE.md + retro + handoff (Day 2 EOD, ~1-2h)

### Task C1: CLAUDE.md updates

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step C1.1: Update "Current phase" paragraph**

Append to the iter-27 paragraph (added in iter-27 wrap):

> **iter-28 (2026-05-NN, GitHubTargetRepo shipped):** `core/target_repo/github.py` closes the ADR-009 carry-over. `make smoke-github-target-repo` clones and probes `girlsmakemedrink/telegram-tech-publisher` end-to-end. ai_team can now be pointed at any external GitHub repo via `target_repo: "<owner>/<repo>"` on a task assignment. Agent invocations against the new repo queue for iter-29.

- [ ] **Step C1.2: Add the iter-27 P3 "branch BEFORE first commit" reminder**

In the "Operating principles for this Claude" section, after the "Use TaskCreate" bullet, add:

> - **Branch BEFORE the first commit on a fresh-cloned repo.** Default to a feature branch even when "I'll branch after this commit" feels obvious — local-main divergence is harder to undo than to prevent. The auto-classifier (correctly) blocks `git reset --hard` as a recovery shortcut. Lesson from iter-27 Phase A.

- [ ] **Step C1.3: Add `GitHubTargetRepo` to the carry-over closure note**

In the "Carry-overs deferred" / "iter-26 priorities" cross-references, add (or update an existing list) to note:

> - ~~`GitHubTargetRepo` implementation~~ — **closed in iter-28** (PR #<A4>, PR #<B2>).

### Task C2: iter_28 retro

**Files:**
- Create: `docs/iterations/iter_28_retro.md`

- [ ] **Step C2.1: Draft retro** with sections: "Outcome", "What went well", "What was harder than expected", "Lessons for iter-29", "Action items".

Specific items to capture:
- Whether the inherit-from-SelfBootstrap pattern caused any leaky-abstraction surprises (class-level `name = "ai_team"` had to be instance-overridden — note any others).
- Whether the workspace-path slug strategy (`<owner>--<repo>`) survived contact with real paths.
- Whether `gh auth status` precondition was reliable in the smoke script.
- Whether the product repo's `uv run pytest` worked from the ai_team subprocess context (Python env / `PATH` gotchas).
- Whether the `_run` import from `self_bootstrap` (which leads with `_`) is an unfortunate coupling — should we promote it to module-level (`core/target_repo/_subprocess.py`) in iter-29?

### Task C3: iter_28 handoff

**Files:**
- Create: `docs/iterations/iter_28_handoff.md`

- [ ] **Step C3.1: Draft handoff** following the iter_27_handoff.md structure:
- Where we are at end of iter-28 (GitHubTargetRepo shipped, agents not yet pointed at it).
- iter-29 priorities ordered:
  1. **(STRATEGIC TOP)** First agent task against the product repo. Concrete proposal: TL decomposes "add Run smoke locally section to telegram-tech-publisher/README.md" (a tiny doc task) as the first agent-driven product-repo PR. Validates the full chain: TL → Backend (file edit) → QA → owner approval → PR open via `GitHubTargetRepo.open_pr` → owner-merge. Low blast radius (docs only) but full pipeline coverage.
  2. **(P2)** Product repo `README.md` "Run smoke locally" section (now becomes the iter-29 #1 deliverable if agents do it).
  3. **(P2)** Workspace GC policy (ADR-009 mention) — implement only if multiple repos accumulate; not blocking with 1 repo.
  4. **(P3)** Promote `_run` from `self_bootstrap.py` to a public module-level helper if iter-28 retro flagged it.
  5. **(Carry-overs ≥5)** unchanged (HoldQueue persistence, BaseAgent refactor, etc.).
- Inherited decisions:
  - SSH-only auth for clone/push; `gh` CLI auth for PRs. No PATs in MVP.
  - Workspaces under `~/.ai_team/workspaces/<owner>--<repo>/`. Manual cleanup OK.
  - `GitHubTargetRepo` inherits from `SelfBootstrapTargetRepo`. No GH-specific `commit` / `push` / `open_pr` overrides.
- Ready-to-paste prompt for iter-29.

### Task C4: PR + merge

- [ ] **Step C4.1: Branch + commit + PR**

```bash
cd /Users/kirillterskih/ai_team
git checkout main && git pull --ff-only
git checkout -b docs/iter-28-wrap
git add CLAUDE.md docs/iterations/iter_28_retro.md docs/iterations/iter_28_handoff.md
git commit -m "docs(iter-28): wrap — CLAUDE.md pointer + retro + handoff"
git push -u origin docs/iter-28-wrap
gh pr create --title "docs(iter-28): wrap iter-28 — CLAUDE.md + retro + handoff to iter-29" \
  --body "Closes iter-28. ADR-009 carry-over closed: GitHubTargetRepo + live smoke shipped in PRs #<A4> and #<B2>. iter-29 queues first agent-driven product-repo task."
```

- [ ] **Step C4.2: Watch CI, squash-merge when green.**

---

## iter-28 Done Criteria

iter-28 is **done** when all of the following are true:

- [ ] `core/target_repo/github.py` exists with `GitHubTargetRepo` + `parse_github_identifier`.
- [ ] `core/target_repo/registry.py` constructs `GitHubTargetRepo` for `owner/repo` and URL identifiers (no `NotImplementedError`).
- [ ] `core/target_repo/__init__.py` re-exports `GitHubTargetRepo`.
- [ ] Unit tests: 11 new tests in `test_target_repo_github.py` pass; 2 updated tests in `test_target_repo_registry.py` pass; full unit suite unchanged baseline (no regressions).
- [ ] Integration test in `tests/integration/test_target_repo_github_clone.py` passes locally (gated by `gh auth status`).
- [ ] `scripts/smoke_github_target_repo.sh` + `make smoke-github-target-repo` work end-to-end against the live product repo.
- [ ] CI green on all PRs (lint + typecheck + bandit + pytest + commitlint).
- [ ] `CLAUDE.md` references iter-28 + has the "branch BEFORE first commit" reminder.
- [ ] `docs/iterations/iter_28_retro.md` + `iter_28_handoff.md` exist.
- [ ] Owner approves the wrap PR (Phase C).

---

## Cost / time estimate

- **Claude usage**: ~$0 of subscription quota — pure local Python + git + gh + subprocess testing. No `claude -p` calls.
- **Wall-clock**: ~1-2 dev days (Phase A ~3-5h, Phase B ~1-2h, Phase C ~1-2h).
- **Owner manual actions required**: (a) one PR review on the Phase C wrap (Phases A and B are self-mergeable on green CI per the standing dev-PR autonomy rule); (b) optional spot-check of the smoke run output in PR #B2 body.

---

## Risks specific to iter-28

1. **SSH key not configured for GitHub on the smoke host.** Mitigation: `scripts/smoke_github_target_repo.sh` checks `gh auth status` upfront; if SSH clone fails inside, raise `GitCommandError` with the underlying `fatal:` line. Owner runs `gh auth login` + adds SSH key if needed.
2. **`uv run pytest` inside the cloned product repo fails because the workspace dir doesn't have its deps synced.** The smoke script's `run_tests` call would fail with `ModuleNotFoundError`. Mitigation: smoke script `run_tests` step is informational — if it fails, log and move on rather than aborting; the architectural validation is the clone + status + lint. Note in retro if this happens.
3. **Workspace dir collisions** if owner manually clones the same repo elsewhere. Low probability; `<owner>--<repo>` is unique-enough and isolated to `~/.ai_team/workspaces/`.
4. **Lazy import of `github.py` in registry.py** if `github.py` raises at import time (e.g., `Path.home()` failure in sandboxed envs). Mitigation: the `_DEFAULT_WORKSPACES_DIR` constant uses `Path.home()` which is cheap and reliable on macOS/Linux. The lazy import inside `resolve_target_repo` still amortizes the cost.
5. **Test pollution if `_DEFAULT_WORKSPACES_DIR` is accidentally used in a unit test.** Mitigation: every unit test passes `workspaces_dir=tmp_path` explicitly. The default-arg test is omitted — that path is exercised in the integration test (which also overrides `workspaces_dir=tmp_path` to avoid touching `~/`).

---

## What iter-28 explicitly does NOT do (re-stated for clarity)

- No ai_team agent invocations against the new repo. iter-29.
- No new ADR (ADR-009 stands; we're filling in the third impl it specified).
- No changes to dispatcher, message schemas, or agent code.
- No workspace GC.
- No PAT-based auth.
- No `core/config.py` settings additions.
- No closing of any iter-26/27 carry-over other than `GitHubTargetRepo` itself.

---

## Approval ask

Owner approves this spec by responding "approved" (or with redlines). Once approved, I:
1. Open PR for this `iter_28.md` doc on `docs/iter-28-plan` branch.
2. Merge once CI green.
3. Begin Phase A immediately (no further approval needed for individual Phase A/B PRs — standing dev-PR autonomy).
4. Surface for approval again at iter-28 wrap (Phase C PR), where the owner reviews retro + handoff before merge.
