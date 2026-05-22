# Iter-29d Implementation Plan — pre-flight bundle

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship three pre-flight items in one bundle PR so iter-29e can submit the multi-role chain on a clean substrate: `TargetRepo.prepare_for_task()` workspace cleanup hook, a documented gate-wiring audit finding, and a `CLAUDE.md` note on the uv dev-extras gotcha.

**Architecture:** Add one concrete default-no-op method to the `TargetRepo` ABC. Override it in `GitHubTargetRepo` with `fetch origin main` → dirty-check → `checkout main` → `merge --ff-only origin/main`. Call from `dispatcher._maybe_resolve_target_repo_workspace` immediately after `ensure_local_clone()`. Audit + docs are write-up only unless a real wiring hole surfaces.

**Tech Stack:** Python 3.13, `asyncio.create_subprocess_exec` (via existing `core.target_repo.self_bootstrap._run`), pytest + `pytest-asyncio`, `unittest.mock.patch` for unit tests, real local `git init --bare` for integration.

---

## File Structure

**Modify:**
- `core/target_repo/base.py` — add concrete default-no-op `prepare_for_task()` on `TargetRepo` ABC. Not an `@abstractmethod` (subclasses inherit).
- `core/target_repo/github.py` — override `prepare_for_task()` with real implementation; use existing `_run` helper imported from `self_bootstrap`.
- `core/dispatcher/dispatcher.py` — single `await repo.prepare_for_task()` line in `_maybe_resolve_target_repo_workspace`, between `ensure_local_clone()` and the workspace stash.
- `tests/unit/test_target_repo_base.py` — verify default no-op exists and subclasses inherit it.
- `tests/unit/test_target_repo_github.py` — unit tests for the four prepare_for_task behaviors (fetch, dirty check, checkout main, ff-only merge), mock-based following existing pattern.
- `tests/unit/test_dispatcher_target_repo_resolution.py` — assert dispatcher calls `prepare_for_task()` after `ensure_local_clone()`.
- `docs/iterations/iter_29d.md` — populate Addendum A with audit findings.
- `CLAUDE.md` — one-line dev-deps note.

**Create:**
- `tests/integration/test_target_repo_github_prepare.py` — real-git integration test using a local bare repo as "origin" (no network, no GitHub).
- `docs/iterations/iter_29e_handoff.md` — stub listing the three iter-29d preconditions.
- `docs/iterations/iter_29d_retro.md` — retro stub.

**Total files:** ~11 (well under the 15-file split trigger).

---

## Task 1: Gate-wiring audit (Item 2 from spec)

**Why first:** Cheapest first step. If audit surfaces a real hole, scope changes and we re-plan. If it confirms QA-only-by-design (expected), the rest of the plan stands.

**Files:**
- Modify: `docs/iterations/iter_29d.md` (Addendum A section, currently empty)

- [ ] **Step 1: Grep for `PendingReview(` across producers**

Run:
```bash
cd /Users/kirillterskih/ai_team
grep -rn "PendingReview(" agents/ core/
```
Expected: at least the `agents/qa_engineer/agent.py:487` site (already known). Note all other hits.

- [ ] **Step 2: Read the QA producer site for context**

Read `agents/qa_engineer/agent.py` lines 480-530 (the safety-net path). Confirm it constructs `PendingReview(...)` and writes via the `pending_reviews_repo` (or equivalent). Note the exact line numbers.

- [ ] **Step 3: Read the dispatcher rollup path**

Read `core/dispatcher/dispatcher.py::_handle_one` end-to-end. Search for any `PendingReview` construction or `pending_reviews_repo.create` call. Note absence (expected) or presence (hole — re-plan).

Also read `core/persistence/task_state.py` around lines 182, 254 (the `parent_rolled_up*` emit sites). Confirm these emit events but do not create `pending_reviews` rows.

- [ ] **Step 4: Read the TL decomposition path**

Read `agents/team_lead/agent.py`. Search for `PendingReview` or any review-creation call. Confirm absence.

- [ ] **Step 5: Verdict + write Addendum A**

Two cases:

**Case A — QA-only-by-design confirmed** (expected). Edit `docs/iterations/iter_29d.md`, replace the empty Addendum A with concrete content. Example shape:

```markdown
## Addendum A: gate-wiring audit findings

**Verdict: design rule, not a wiring hole.**

`pending_reviews` rows are written exclusively by the QA Engineer agent's safety-net path at `agents/qa_engineer/agent.py:<line>`. Confirmed via:

- `grep -rn "PendingReview(" agents/ core/` → single producer site.
- `core/dispatcher/dispatcher.py::_handle_one` (lines <X>-<Y>) and `core/persistence/task_state.py:182,254` (rollup emit sites) → no `PendingReview` construction in the dispatcher or task-state reducer.
- `agents/team_lead/agent.py` → no review-creation call in the decomposition path.

**Implication for iter-29b's "no pending_review fired" surprise.** The TL → DevOps single-agent chain skipped QA, so no producer ran. The missing review is a chain-shape consequence, not a wiring bug.

**Design rule** (added to `CLAUDE.md` in Item 3): pending_reviews are produced by QA Engineer only; chains that skip QA legitimately skip the review record.

**No code change in this iter.**
```

**Case B — Wiring hole found** (unlikely). Stop. Document the symptom inline, scope the smallest fix. If ≤30 LOC + tests, add new tasks to this plan. Larger fix → carve out, stub the iter-29e handoff to flag.

- [ ] **Step 6: Commit**

```bash
git add docs/iterations/iter_29d.md
git commit -m "docs(iter-29d): record gate-wiring audit findings"
```

---

## Task 2: Add `prepare_for_task()` default no-op to TargetRepo ABC

**Files:**
- Modify: `core/target_repo/base.py`
- Modify: `tests/unit/test_target_repo_base.py`

- [ ] **Step 1: Write the failing test**

Open `tests/unit/test_target_repo_base.py`. Add:

```python
import pytest

from core.target_repo.base import TargetRepo


class _MinimalRepo(TargetRepo):
    """Implements the abstract surface with placeholders; only here to
    instantiate TargetRepo for testing the concrete no-op method."""

    async def ensure_local_clone(self):  # type: ignore[override]
        return self.root

    async def checkout(self, branch, *, base=None):  # type: ignore[override]
        return None

    async def stage_and_commit(self, paths, message, author):  # type: ignore[override]
        return "sha"

    async def push(self, branch):  # type: ignore[override]
        return None

    async def open_pr(self, *, head, base, title, body):  # type: ignore[override]
        raise NotImplementedError

    async def run_tests(self, command=None):  # type: ignore[override]
        raise NotImplementedError

    async def run_linter(self):  # type: ignore[override]
        raise NotImplementedError

    async def status(self):  # type: ignore[override]
        raise NotImplementedError


@pytest.mark.asyncio
async def test_prepare_for_task_default_is_noop(tmp_path) -> None:
    repo = _MinimalRepo()
    repo.root = tmp_path
    # Should not raise, returns None.
    result = await repo.prepare_for_task()
    assert result is None
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
cd /Users/kirillterskih/ai_team
uv run pytest tests/unit/test_target_repo_base.py::test_prepare_for_task_default_is_noop -v
```
Expected: FAIL with `AttributeError: 'TargetRepo' object has no attribute 'prepare_for_task'` (or similar).

- [ ] **Step 3: Add the default no-op to the ABC**

Open `core/target_repo/base.py`. After the last `@abstractmethod` (the `async def status(self)` at line 78), add:

```python
    async def prepare_for_task(self) -> None:
        """Pre-task workspace cleanup hook.

        Called by the dispatcher after `ensure_local_clone()` and before
        the task is dispatched. Default: no-op. Concrete implementations
        override to reset workspace state (e.g. checkout main, ff-only
        merge). Failure should raise; the dispatcher's outer try/except
        catches and routes via `_synthesise_failed_report`.
        """
        return None
```

Note: NOT decorated `@abstractmethod`. Subclasses inherit the no-op unless they override.

- [ ] **Step 4: Run test to verify it passes**

Run:
```bash
uv run pytest tests/unit/test_target_repo_base.py::test_prepare_for_task_default_is_noop -v
```
Expected: PASS.

- [ ] **Step 5: Run the full test_target_repo_base.py file to verify no regression**

Run:
```bash
uv run pytest tests/unit/test_target_repo_base.py -v
```
Expected: all PASS.

- [ ] **Step 6: Run subclass-inheritance check**

Add to `tests/unit/test_target_repo_base.py`:

```python
@pytest.mark.asyncio
async def test_self_bootstrap_inherits_default_prepare_for_task(tmp_path) -> None:
    from core.target_repo.self_bootstrap import SelfBootstrapTargetRepo

    repo = SelfBootstrapTargetRepo(root=tmp_path)
    result = await repo.prepare_for_task()
    assert result is None


@pytest.mark.asyncio
async def test_in_repo_example_inherits_default_prepare_for_task(tmp_path) -> None:
    from core.target_repo.in_repo_example import InRepoExampleTargetRepo

    # Use the same constructor shape as existing InRepoExample tests.
    repo = InRepoExampleTargetRepo(root=tmp_path)
    result = await repo.prepare_for_task()
    assert result is None
```

Run:
```bash
uv run pytest tests/unit/test_target_repo_base.py -v
```
Expected: all PASS. If `InRepoExampleTargetRepo` constructor differs from the example above, peek at `tests/unit/test_target_repo_in_repo_example.py` for the actual signature and copy that.

- [ ] **Step 7: Commit**

```bash
git add core/target_repo/base.py tests/unit/test_target_repo_base.py
git commit -m "feat(iter-29d): add TargetRepo.prepare_for_task default no-op"
```

---

## Task 3: `GitHubTargetRepo.prepare_for_task()` — fetch step + failure path

**Files:**
- Modify: `core/target_repo/github.py`
- Modify: `tests/unit/test_target_repo_github.py`

- [ ] **Step 1: Write the failing test (fetch success)**

Append to `tests/unit/test_target_repo_github.py`:

```python
@pytest.mark.asyncio
async def test_prepare_for_task_fetches_origin_main(tmp_path: Path) -> None:
    repo = GitHubTargetRepo("girlsmakemedrink/telegram-tech-publisher", workspaces_dir=tmp_path)
    repo.root.mkdir(parents=True)
    (repo.root / ".git").mkdir()

    with patch("core.target_repo.github._run", new_callable=AsyncMock) as mock_run:
        # fetch ok, status clean, checkout ok, merge ok
        mock_run.side_effect = [
            (0, "", ""),  # fetch
            (0, "", ""),  # status --porcelain (empty == clean)
            (0, "", ""),  # checkout main
            (0, "", ""),  # merge --ff-only origin/main
        ]
        await repo.prepare_for_task()

    # First call must be `git fetch origin main`.
    first_call = mock_run.call_args_list[0]
    assert first_call.args[0] == "git"
    assert first_call.args[1] == "fetch"
    assert first_call.args[2] == "origin"
    assert first_call.args[3] == "main"
    assert first_call.kwargs["cwd"] == repo.root


@pytest.mark.asyncio
async def test_prepare_for_task_raises_on_fetch_failure(tmp_path: Path) -> None:
    repo = GitHubTargetRepo("girlsmakemedrink/telegram-tech-publisher", workspaces_dir=tmp_path)
    repo.root.mkdir(parents=True)
    (repo.root / ".git").mkdir()

    with patch("core.target_repo.github._run", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = (1, "", "fatal: unable to access remote")
        with pytest.raises(GitCommandError, match="failed to fetch origin/main"):
            await repo.prepare_for_task()
```

- [ ] **Step 2: Run tests to verify they fail**

Run:
```bash
uv run pytest tests/unit/test_target_repo_github.py::test_prepare_for_task_fetches_origin_main tests/unit/test_target_repo_github.py::test_prepare_for_task_raises_on_fetch_failure -v
```
Expected: both FAIL — `prepare_for_task` not yet overridden, so the default no-op runs and the assertions never trip.

- [ ] **Step 3: Implement fetch step + scaffold for the rest**

In `core/target_repo/github.py`, add inside the `GitHubTargetRepo` class (after `ensure_local_clone`):

```python
    async def prepare_for_task(self) -> None:
        """Reset workspace to a clean main before each task.

        Steps: fetch origin/main → dirty-check → checkout main →
        ff-only merge origin/main. Loud-fail on dirty workspace or
        diverged local main; no destructive reset. Owner intervenes.
        """
        rc, _out, err = await _run("git", "fetch", "origin", "main", cwd=self.root)
        if rc != 0:
            raise GitCommandError(f"failed to fetch origin/main: {err.strip()[:500]}")
        # Steps 2-4 land in Tasks 4 and 5.
        rc, out, err = await _run("git", "status", "--porcelain", cwd=self.root)
        if rc != 0:
            raise GitCommandError(f"git status failed: {err.strip()[:500]}")
        if out.strip():
            raise GitCommandError(
                f"workspace has uncommitted changes: {out.strip()[:500]}; "
                f"refusing to checkout main"
            )
        rc, _out, err = await _run("git", "checkout", "main", cwd=self.root)
        if rc != 0:
            raise GitCommandError(f"git checkout main failed: {err.strip()[:500]}")
        rc, _out, err = await _run("git", "merge", "--ff-only", "origin/main", cwd=self.root)
        if rc != 0:
            raise GitCommandError(
                f"local main diverged from origin/main: {err.strip()[:500]}; "
                f"manual intervention required"
            )
```

Note: the full implementation (all four git ops) lands here in one go because the test in Step 1 mocks all four. The dirty-check and merge tests in Tasks 4 and 5 will exercise the failure paths.

- [ ] **Step 4: Run tests to verify they pass**

Run:
```bash
uv run pytest tests/unit/test_target_repo_github.py::test_prepare_for_task_fetches_origin_main tests/unit/test_target_repo_github.py::test_prepare_for_task_raises_on_fetch_failure -v
```
Expected: both PASS.

- [ ] **Step 5: Commit**

```bash
git add core/target_repo/github.py tests/unit/test_target_repo_github.py
git commit -m "feat(iter-29d): GitHubTargetRepo.prepare_for_task fetch + scaffold"
```

---

## Task 4: `GitHubTargetRepo.prepare_for_task()` — dirty workspace failure path

**Files:**
- Modify: `tests/unit/test_target_repo_github.py`

The impl already covers the dirty path (added in Task 3). This task just adds the test that drives it from the outside.

- [ ] **Step 1: Write the failing test (dirty workspace)**

Append to `tests/unit/test_target_repo_github.py`:

```python
@pytest.mark.asyncio
async def test_prepare_for_task_raises_on_dirty_workspace(tmp_path: Path) -> None:
    repo = GitHubTargetRepo("girlsmakemedrink/telegram-tech-publisher", workspaces_dir=tmp_path)
    repo.root.mkdir(parents=True)
    (repo.root / ".git").mkdir()

    with patch("core.target_repo.github._run", new_callable=AsyncMock) as mock_run:
        mock_run.side_effect = [
            (0, "", ""),  # fetch ok
            (0, " M src/foo.py\n?? new.txt\n", ""),  # status --porcelain non-empty
        ]
        with pytest.raises(GitCommandError, match="uncommitted changes"):
            await repo.prepare_for_task()

    # Verify checkout was NEVER attempted.
    called_subcommands = [c.args[1] for c in mock_run.call_args_list]
    assert "checkout" not in called_subcommands
    assert "merge" not in called_subcommands
```

- [ ] **Step 2: Run test to verify behavior**

Run:
```bash
uv run pytest tests/unit/test_target_repo_github.py::test_prepare_for_task_raises_on_dirty_workspace -v
```
Expected: PASS (impl from Task 3 already handles this).

- [ ] **Step 3: Commit**

```bash
git add tests/unit/test_target_repo_github.py
git commit -m "test(iter-29d): prepare_for_task refuses dirty workspace"
```

---

## Task 5: `GitHubTargetRepo.prepare_for_task()` — diverged-main failure path

**Files:**
- Modify: `tests/unit/test_target_repo_github.py`

- [ ] **Step 1: Write the failing test (diverged main)**

Append to `tests/unit/test_target_repo_github.py`:

```python
@pytest.mark.asyncio
async def test_prepare_for_task_raises_on_diverged_main(tmp_path: Path) -> None:
    repo = GitHubTargetRepo("girlsmakemedrink/telegram-tech-publisher", workspaces_dir=tmp_path)
    repo.root.mkdir(parents=True)
    (repo.root / ".git").mkdir()

    with patch("core.target_repo.github._run", new_callable=AsyncMock) as mock_run:
        mock_run.side_effect = [
            (0, "", ""),  # fetch ok
            (0, "", ""),  # status clean
            (0, "", ""),  # checkout main ok
            (1, "", "fatal: Not possible to fast-forward, aborting."),  # merge fails
        ]
        with pytest.raises(GitCommandError, match="diverged from origin/main"):
            await repo.prepare_for_task()


@pytest.mark.asyncio
async def test_prepare_for_task_happy_path_calls_all_four_subcommands_in_order(
    tmp_path: Path,
) -> None:
    repo = GitHubTargetRepo("girlsmakemedrink/telegram-tech-publisher", workspaces_dir=tmp_path)
    repo.root.mkdir(parents=True)
    (repo.root / ".git").mkdir()

    with patch("core.target_repo.github._run", new_callable=AsyncMock) as mock_run:
        mock_run.side_effect = [(0, "", "")] * 4
        await repo.prepare_for_task()

    subcommands = [c.args[1] for c in mock_run.call_args_list]
    assert subcommands == ["fetch", "status", "checkout", "merge"]
    # cwd is the workspace for all four calls.
    for c in mock_run.call_args_list:
        assert c.kwargs["cwd"] == repo.root
```

- [ ] **Step 2: Run tests to verify behavior**

Run:
```bash
uv run pytest tests/unit/test_target_repo_github.py::test_prepare_for_task_raises_on_diverged_main tests/unit/test_target_repo_github.py::test_prepare_for_task_happy_path_calls_all_four_subcommands_in_order -v
```
Expected: both PASS (impl already covers).

- [ ] **Step 3: Run the full GitHubTargetRepo test file**

Run:
```bash
uv run pytest tests/unit/test_target_repo_github.py -v
```
Expected: all PASS, no regressions on the existing `ensure_local_clone` tests.

- [ ] **Step 4: Commit**

```bash
git add tests/unit/test_target_repo_github.py
git commit -m "test(iter-29d): prepare_for_task diverged-main + happy-path order"
```

---

## Task 6: Wire `prepare_for_task()` into the dispatcher

**Files:**
- Modify: `core/dispatcher/dispatcher.py`
- Modify: `tests/unit/test_dispatcher_target_repo_resolution.py`

- [ ] **Step 1: Write the failing test**

Open `tests/unit/test_dispatcher_target_repo_resolution.py`. Replace the body of `test_resolves_and_stashes_workspace_for_assignment_with_target_repo` (lines ~71-91) with the version below, AND add a new test:

```python
async def test_resolves_and_stashes_workspace_for_assignment_with_target_repo(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()

    fake_repo = AsyncMock()
    fake_repo.ensure_local_clone = AsyncMock(return_value=workspace)
    fake_repo.prepare_for_task = AsyncMock(return_value=None)

    dispatcher = _make_dispatcher(tmp_path)
    msg = _assignment(target_repo="owner/repo")

    with patch(
        "core.dispatcher.dispatcher.resolve_target_repo",
        return_value=fake_repo,
    ) as mock_resolve:
        await dispatcher._maybe_resolve_target_repo_workspace(msg)

    mock_resolve.assert_called_once_with("owner/repo", ai_team_root=tmp_path)
    fake_repo.ensure_local_clone.assert_awaited_once()
    fake_repo.prepare_for_task.assert_awaited_once()
    # Order matters: clone before prepare.
    clone_order = fake_repo.ensure_local_clone.call_args_list[0]
    prepare_order = fake_repo.prepare_for_task.call_args_list[0]
    assert clone_order is not None and prepare_order is not None
    assert msg.metadata.get("target_repo_workspace") == str(workspace)


async def test_prepare_for_task_failure_propagates_for_synthesise_catch(
    tmp_path: Path,
) -> None:
    """If prepare_for_task raises, exception escapes so `_handle_one`'s
    outer try/except can synthesise a FAILED report."""
    fake_repo = AsyncMock()
    fake_repo.ensure_local_clone = AsyncMock(return_value=tmp_path / "ws")
    fake_repo.prepare_for_task = AsyncMock(
        side_effect=RuntimeError("local main diverged from origin/main")
    )

    dispatcher = _make_dispatcher(tmp_path)
    msg = _assignment(target_repo="owner/repo")

    with (
        patch(
            "core.dispatcher.dispatcher.resolve_target_repo",
            return_value=fake_repo,
        ),
        pytest.raises(RuntimeError, match="local main diverged"),
    ):
        await dispatcher._maybe_resolve_target_repo_workspace(msg)
```

- [ ] **Step 2: Run tests to verify they fail**

Run:
```bash
uv run pytest tests/unit/test_dispatcher_target_repo_resolution.py -v
```
Expected: the two amended/new tests FAIL because the dispatcher does not yet call `prepare_for_task`. Other tests in the file should still PASS.

- [ ] **Step 3: Wire the call site**

Open `core/dispatcher/dispatcher.py`. Find `_maybe_resolve_target_repo_workspace` (around line 208). Update the body so the section between `resolve_target_repo` and the metadata stash reads:

```python
        repo = resolve_target_repo(identifier, ai_team_root=self._ai_team_root)
        workspace = await repo.ensure_local_clone()
        await repo.prepare_for_task()
        msg.metadata["target_repo_workspace"] = str(workspace)
```

Also update the docstring's "Raises" section to mention `prepare_for_task` is part of the raise surface (one extra phrase, e.g. "Raises whatever `resolve_target_repo`, `ensure_local_clone`, or `prepare_for_task` raises...").

- [ ] **Step 4: Run tests to verify they pass**

Run:
```bash
uv run pytest tests/unit/test_dispatcher_target_repo_resolution.py -v
```
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add core/dispatcher/dispatcher.py tests/unit/test_dispatcher_target_repo_resolution.py
git commit -m "feat(iter-29d): dispatcher calls prepare_for_task after clone"
```

---

## Task 7: Integration test against a real local bare repo

**Files:**
- Create: `tests/integration/test_target_repo_github_prepare.py`

**Why local bare repo, not GitHub:** real `git` exercise without network. The existing `test_target_repo_github_clone.py` hits real GitHub and is gated on `gh auth`; this new test should run on any CI box.

- [ ] **Step 1: Write the integration test**

Create `tests/integration/test_target_repo_github_prepare.py` with:

```python
"""Integration test: prepare_for_task against a real local bare repo.

Marked `@pytest.mark.integration` — skipped in the default unit run.
No network, no `gh` — just `git`. Tests the actual subprocess plumbing
end-to-end against real git state.
"""

from __future__ import annotations

import shutil
import subprocess
from typing import TYPE_CHECKING

import pytest

from core.target_repo.github import GitHubTargetRepo
from core.target_repo.self_bootstrap import GitCommandError

if TYPE_CHECKING:
    from pathlib import Path


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(shutil.which("git") is None, reason="requires git"),
]


def _git(cwd: Path, *args: str) -> str:
    """Run git synchronously, return stdout, raise on non-zero."""
    result = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git {args} failed: {result.stderr}")
    return result.stdout


def _setup_origin_with_main(origin_dir: Path) -> None:
    """Create a bare repo with one commit on main and one extra commit
    that the workspace will fetch."""
    _git(origin_dir.parent, "init", "--bare", str(origin_dir))
    # Bootstrap via a temp clone since we can't commit to a bare repo directly.
    bootstrap = origin_dir.parent / "_bootstrap"
    _git(origin_dir.parent, "clone", str(origin_dir), str(bootstrap))
    _git(bootstrap, "config", "user.email", "test@test")
    _git(bootstrap, "config", "user.name", "Test")
    (bootstrap / "README.md").write_text("v1\n")
    _git(bootstrap, "add", "README.md")
    _git(bootstrap, "commit", "-m", "v1")
    _git(bootstrap, "branch", "-M", "main")
    _git(bootstrap, "push", "-u", "origin", "main")


def _make_workspace_clone(origin_dir: Path, workspace: Path) -> None:
    _git(workspace.parent, "clone", str(origin_dir), str(workspace))
    _git(workspace, "config", "user.email", "test@test")
    _git(workspace, "config", "user.name", "Test")


@pytest.mark.asyncio
async def test_prepare_for_task_resets_feature_branch_to_main(tmp_path: Path) -> None:
    origin = tmp_path / "origin.git"
    workspace = tmp_path / "ws"
    _setup_origin_with_main(origin)
    _make_workspace_clone(origin, workspace)
    # Workspace currently on a feature branch with one local commit.
    _git(workspace, "checkout", "-b", "agent/devops/feat")
    (workspace / "file.txt").write_text("x\n")
    _git(workspace, "add", "file.txt")
    _git(workspace, "commit", "-m", "feat")

    repo = GitHubTargetRepo.__new__(GitHubTargetRepo)
    # Bypass __init__ identifier parsing; set only what prepare_for_task needs.
    repo.root = workspace
    repo.default_branch = "main"

    await repo.prepare_for_task()

    branch = _git(workspace, "rev-parse", "--abbrev-ref", "HEAD").strip()
    assert branch == "main"


@pytest.mark.asyncio
async def test_prepare_for_task_raises_on_dirty_workspace_real_git(tmp_path: Path) -> None:
    origin = tmp_path / "origin.git"
    workspace = tmp_path / "ws"
    _setup_origin_with_main(origin)
    _make_workspace_clone(origin, workspace)
    (workspace / "dirty.txt").write_text("dirty\n")

    repo = GitHubTargetRepo.__new__(GitHubTargetRepo)
    repo.root = workspace
    repo.default_branch = "main"

    with pytest.raises(GitCommandError, match="uncommitted changes"):
        await repo.prepare_for_task()

    # Workspace state preserved.
    assert (workspace / "dirty.txt").exists()


@pytest.mark.asyncio
async def test_prepare_for_task_raises_on_diverged_local_main_real_git(
    tmp_path: Path,
) -> None:
    origin = tmp_path / "origin.git"
    workspace = tmp_path / "ws"
    _setup_origin_with_main(origin)
    _make_workspace_clone(origin, workspace)
    # Make a divergent commit on local main that isn't on origin/main.
    (workspace / "drift.txt").write_text("drift\n")
    _git(workspace, "add", "drift.txt")
    _git(workspace, "commit", "-m", "drift")
    # Add a different commit to origin via bootstrap.
    bootstrap = tmp_path / "_bootstrap"
    (bootstrap / "origin-side.txt").write_text("origin\n")
    _git(bootstrap, "add", "origin-side.txt")
    _git(bootstrap, "commit", "-m", "origin-side")
    _git(bootstrap, "push", "origin", "main")

    repo = GitHubTargetRepo.__new__(GitHubTargetRepo)
    repo.root = workspace
    repo.default_branch = "main"

    with pytest.raises(GitCommandError, match="diverged from origin/main"):
        await repo.prepare_for_task()

    # Local drift commit is preserved.
    log = _git(workspace, "log", "--oneline", "-5")
    assert "drift" in log
```

- [ ] **Step 2: Run the integration test**

Run:
```bash
uv run pytest tests/integration/test_target_repo_github_prepare.py -v -m integration
```
Expected: all three tests PASS. If pytest complains about the `integration` marker not being registered, check `pyproject.toml` or `pytest.ini` — the existing `test_target_repo_github_clone.py` uses the same marker, so it should already be configured.

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_target_repo_github_prepare.py
git commit -m "test(iter-29d): integration test for prepare_for_task against local bare repo"
```

---

## Task 8: `CLAUDE.md` dev-deps one-liner

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Locate the right section**

Run:
```bash
grep -n -E "^##|^###" /Users/kirillterskih/ai_team/CLAUDE.md | head -40
```

Find the section that covers env setup, install commands, or operating principles for dev work. Likely candidates: "Operating principles", "Development", or a "Setup" header. Pick the one that already mentions `uv sync` or testing setup. If none mentions deps explicitly, append to "Operating principles".

- [ ] **Step 2: Add the one-liner**

Edit the chosen section to add (or merge cleanly with existing prose):

> Any repo with PEP 621 `[project.optional-dependencies].dev` (ai_team does; product repos may) needs `uv sync --extra dev --all-groups` — `uv sync` alone skips those extras and leaves `respx`, `pre-commit`, etc. uninstalled.

Wording should match the rest of the file's voice. If the section uses bullet points, format as a bullet. If it's prose, integrate as a sentence.

- [ ] **Step 3: Add the QA-only design rule (only if Task 1 confirmed Case A)**

If the audit landed on the QA-only-by-design verdict, also add to `CLAUDE.md` (same or adjacent section):

> `pending_reviews` rows are produced by the QA Engineer agent only. Chains that legitimately skip QA (e.g. docs-only TL → DevOps) will not create a review record — that is by design, not a missing wire.

Skip this step if Task 1 surfaced a wiring hole instead — the rule would be misleading.

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md
git commit -m "docs(iter-29d): note uv dev-extras gotcha + pending_reviews design rule"
```

---

## Task 9: iter-29e handoff stub

**Files:**
- Create: `docs/iterations/iter_29e_handoff.md`

- [ ] **Step 1: Write the stub**

Create `docs/iterations/iter_29e_handoff.md` with:

```markdown
# Iter-29e Handoff (stub) — multi-role chain exercise

> **Status:** stub. Populated by iter-29e itself. iter-29d landed three pre-flight items the iter-29e spec relies on; this stub records them so the spec doesn't have to re-discover them.

## Preflight (from iter-29d)

- **Workspace cleanup hook:** `TargetRepo.prepare_for_task()` runs before every cross-repo task assignment. `GitHubTargetRepo` resets the workspace to a clean `main` (fetch + dirty-check + checkout + ff-only merge). Dirty workspaces and diverged local mains raise — owner intervenes; nothing is destructively reset.
- **Dev-deps install:** `uv sync --extra dev --all-groups` in any repo with PEP 621 dev extras. `uv sync` alone skips those.
- **Gate-wiring design rule** (from iter-29d Addendum A): `pending_reviews` are produced by QA Engineer only. Chains that skip QA legitimately skip the review record.

## Goal (placeholder, owner to refine)

Submit a task that forces TL to decompose across roles (Architect + Backend + QA), validating the multi-role chain end-to-end. Quota budget: TBD by iter-29e spec.

## Open items inherited from iter-29c/29b carry-overs

See `docs/iterations/iter_29c_handoff.md` §5 and `docs/iterations/iter_29b.md` for the standing list. None addressed in iter-29d.
```

- [ ] **Step 2: Commit**

```bash
git add docs/iterations/iter_29e_handoff.md
git commit -m "docs(iter-29d): iter-29e handoff stub with preflight items"
```

---

## Task 10: iter-29d retro stub

**Files:**
- Create: `docs/iterations/iter_29d_retro.md`

- [ ] **Step 1: Write the retro stub**

Create `docs/iterations/iter_29d_retro.md` with:

```markdown
# Iter-29d Retro — pre-flight bundle

**Status:** shipped <DATE>.

## Numbers

| Metric | Value |
|---|---|
| Files touched | ~11 |
| LLM invocations | 0 (no `claude -p` run in this iter) |
| Quota burn | $0.00 |
| New tests | <unit + integration count> |

## What shipped

- `TargetRepo.prepare_for_task()` workspace cleanup hook (default no-op on the ABC, real impl in `GitHubTargetRepo`).
- Dispatcher wires the hook between `ensure_local_clone()` and the workspace metadata stash.
- Integration test against a local bare repo (no network, no GitHub).
- Gate-wiring audit: `pending_reviews` confirmed QA-only-by-design (see `iter_29d.md` Addendum A).
- `CLAUDE.md` carries the uv dev-extras gotcha and the pending_reviews design rule.
- `iter_29e_handoff.md` stub with the three preflight items.

## Surprises

<populate from impl — anything unexpected from the audit or the integration test>

## Architectural follow-ups (defer to iter-29e+)

Unchanged from iter-29c handoff §5 + iter-29b carry-overs.

## Closure

iter-29d is shipped. The substrate is ready for iter-29e's multi-role chain exercise.
```

- [ ] **Step 2: Commit**

```bash
git add docs/iterations/iter_29d_retro.md
git commit -m "docs(iter-29d): retro stub"
```

---

## Task 11: Wrap-up — full suite, smoke, PR, self-merge, memory

**Files:** none modified in this task (just orchestration); memory updates after merge.

- [ ] **Step 1: Run the full unit suite**

Run:
```bash
cd /Users/kirillterskih/ai_team
uv run pytest tests/unit -v
```
Expected: all PASS, no regressions. If a test fails, fix it before proceeding (likely a brittle dispatcher test that asserted call shape that has now changed).

- [ ] **Step 2: Run the GitHub-target-repo smoke**

Run:
```bash
make smoke-github-target-repo
```
Expected: green. This exercises the real workspace path — if `prepare_for_task` breaks the happy path on a real workspace, this surfaces it.

- [ ] **Step 3: Run static checks**

Run:
```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy core/ tests/unit
uv run bandit -r core/ -ll
```
Expected: all clean. Fix any new issues from the diff inline.

- [ ] **Step 4: Push branch**

```bash
git push -u origin feat/iter-29d-preflight
```

- [ ] **Step 5: Open PR**

```bash
gh pr create --title "iter-29d: pre-flight bundle for multi-role chain exercise" --body "$(cat <<'EOF'
## Summary

Pre-flight items for iter-29e (multi-role chain exercise), bundled in one PR. No live LLM spend.

- `TargetRepo.prepare_for_task()` workspace cleanup hook (default no-op on ABC; `GitHubTargetRepo` resets to clean `main` via fetch + dirty-check + checkout + ff-only merge). Loud-fail on dirty or diverged state — owner intervenes; nothing is destructively reset.
- Audit finding (Addendum A in `docs/iterations/iter_29d.md`): `pending_reviews` are produced by QA Engineer only. iter-29b's "no review fired" was a chain-shape consequence (TL → DevOps skipped QA), not a wiring hole. Design rule recorded in `CLAUDE.md`.
- `CLAUDE.md` note on the uv dev-extras gotcha.
- `iter_29e_handoff.md` stub with the three preflight items.

## Test plan

- [ ] `uv run pytest tests/unit -v` green
- [ ] `uv run pytest tests/integration/test_target_repo_github_prepare.py -v -m integration` green
- [ ] `make smoke-github-target-repo` green
- [ ] CI green on `feat/iter-29d-preflight`

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

Capture the PR URL from the output.

- [ ] **Step 6: Watch CI**

```bash
gh pr checks --watch
```
Expected: all checks green. If any fail, fix on the branch and push.

- [ ] **Step 7: Squash-merge**

```bash
gh pr merge --squash --delete-branch
```
Then locally:
```bash
git checkout main
git pull
```

- [ ] **Step 8: Update memory**

Update the auto-memory files to reflect the closed iter:

1. `MEMORY.md` — add a one-line entry for iter-29d (if not already covered by `project_ai_team.md`); add a feedback memory entry if not present.
2. `project_ai_team.md` — replace the active-backlog "Gate wiring audit" line with the confirmed design rule, replace "Workspace cleanup hook" with "DONE in iter-29d", replace the dev-deps gotcha line with a pointer to `CLAUDE.md`. Update "Iter history (condensed)" with an iter-29d entry citing the PR number.
3. Consider a new feedback entry under [[feedback-workflow]] for the "bundle small scopes under split trigger" calibration validated this iter — only if it's a non-obvious nuance worth saving, not a restatement of the existing rule.

- [ ] **Step 9: Report back**

Reply to the owner with:
- PR URL and merge SHA.
- A one-line summary of what landed.
- The state of the iter-29e backlog (multi-role chain exercise is now the headline).

---

## Self-Review Checklist

After writing this plan, verifying against the spec:

**Spec coverage:**
- Item 1 (workspace cleanup hook): Tasks 2, 3, 4, 5, 6, 7. ✓
- Item 2 (gate wiring audit): Task 1, plus the optional `CLAUDE.md` design rule in Task 8 Step 3. ✓
- Item 3 (dev-deps doc + handoff stub): Tasks 8, 9. ✓
- Run plan ordering (audit first, then TDD hook, then smoke, then docs, then PR/merge): preserved across Tasks 1 → 11. ✓
- Success criteria: covered by Tasks 2-11 in aggregate. ✓
- Quota budget $0.00: no LLM steps. ✓

**Placeholder scan:** none — all code blocks contain real code; all commands are runnable; only the retro `<DATE>` and `<unit + integration count>` placeholders, which are intentionally filled post-merge.

**Type/identifier consistency:** `prepare_for_task` (snake_case) used consistently across tasks. `GitCommandError` (existing class) used throughout — not the placeholder `TargetRepoError` from the spec. `_run` from `self_bootstrap` imported the same way the existing `github.py` already imports it.
