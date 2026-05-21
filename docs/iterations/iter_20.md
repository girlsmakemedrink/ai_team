# Iteration 20 — Plan

- **Status**: Draft (awaiting owner approval)
- **Plan author**: Claude (Opus 4.7)
- **Date drafted**: 2026-05-21
- **Base commit**: iter-19 squash on `main` (`ed93241
  iter-19: close iter-18 demo caveats (#26)`).
- **Branch**: `worktree-iter-20` (already cut from
  `origin/main`).
- **Anchors (do not contradict)**: ADR-0001
  (orchestrator), ADR-0004 (per-agent tool
  allowlist), ADR-0009 (target-repo), iter-19 retro
  + demo report + handoff.
- **Carry-overs addressed**: items 1–3 of
  `iter_20_handoff.md` — agent-branch-isolation,
  TL Backend decomposition, re-run iter-19 demo
  shape.
- **Deferred unchanged**: carry-overs 4–15 from
  `iter_20_handoff.md`.

## Goal in one sentence

**Close the iter-19 demo's two killer findings
(Backend's `git checkout` corrupting the
orchestrator's worktree + Backend's 600s timeout)
so the iter-19 demo shape can finally produce a
QA-emitted `pending_reviews` row with
`requesting_agent='qa_engineer'`.**

## Investigation evidence (already gathered)

1. **Root cause of iter-19 demo's branch-switch
   surprise**:
   `tools/mcp_servers/ai_team_repo/handlers.py:107-129`'s
   `handle_create_branch` runs `git checkout -b
   <branch> <base>` with `cwd=ctx.scope.root`.
   When the demo configures `AI_TEAM_REPO_ROOT =
   $REPO_ROOT` (the orchestrator's worktree),
   this command **switches the orchestrator's
   HEAD** to the new agent branch. The fix is
   `git worktree add` instead of `git checkout
   -b` — creates an isolated tree without
   touching the shared HEAD.

2. **MCP server lifecycle is per-`claude -p`
   invocation**:
   `core/llm/claude_code_headless.py:209-215`
   passes `--mcp-config` to each `claude -p`
   subprocess; claude spawns a fresh MCP server
   subprocess for each agent's session. **This
   means a module-level variable on the MCP
   server side is naturally scoped to ONE
   agent's session.** We can use this for the
   per-correlation "active worktree" state
   without inventing a session-tracking layer.

3. **All `ai_team_repo` handlers use
   `cwd=str(ctx.scope.root)`** as the
   subprocess cwd
   (`handlers.py:79, 124, 167, 208`). Iter-20
   needs to thread "the active worktree" through
   these — either via an `_ACTIVE_WORKTREE`
   module-level (read inside each handler) or
   by mutating `Context`. Since `Context` is
   `frozen=True`, module-level is simpler.

4. **`git worktree add` semantics**: creates a
   second working tree at the target path,
   sharing the same `.git` directory. The
   original tree's HEAD is unaffected. Cleanup:
   `git worktree remove <path>` or `git
   worktree prune` (after the directory is
   deleted manually). For iter-20's demo, we
   prune on entry + remove on exit.

5. **iter-19 demo's Backend single-subtask was
   ~250 LOC** estimated (idea-validator
   pipeline). At 600s timeout this is borderline
   even on Sonnet. **TL's prompt currently says
   "Prefer fewer, larger subtasks over many tiny
   ones"** (`prompts/team_lead.md:70`) — the
   opposite of what Backend needs. iter-20 must
   carve out an explicit exception for Backend.

6. **Bandit Bandit Bandit**:
   `git worktree add` doesn't ship a network or
   permission escalation. Same bandit
   surface-area as the existing `git checkout
   -b`. No new high-severity findings expected.

## Phases — bite-sized TDD steps with exact paths

### Phase 1 — `handle_create_branch` uses `git worktree add` + module-level `_ACTIVE_WORKTREE`

**Goal**: When `handle_create_branch` runs, it
creates the new branch in an **isolated worktree**
(under `<repo_root>/.claude/agent-worktrees/<sanitized_branch>/`)
rather than switching the orchestrator's HEAD.
Subsequent calls to `handle_run_shell` and
`handle_write_file_in_scope` from the same MCP
server process use the isolated worktree as `cwd`.

**Files**:
- Modify: `tools/mcp_servers/ai_team_repo/handlers.py`
  (`handle_create_branch`, `handle_run_shell`,
  `handle_write_file_in_scope`, `handle_open_pr`;
  add module-level `_ACTIVE_WORKTREE`)
- Test: `tests/unit/test_mcp_ai_team_repo_handlers.py`
  (new tests using real tmp git repos)

#### Step 1.1 — Red: assert handle_create_branch creates isolated worktree

- [ ] **Step 1.1.1** — Add a test fixture for a
  real tmp git repo (handlers' `git worktree
  add` requires a real repo, not a `tmp_path` /
  bare dir). Append to
  `tests/unit/test_mcp_ai_team_repo_handlers.py`:

```python
import asyncio
import subprocess

import pytest


@pytest.fixture
def tmp_git_repo(tmp_path: Path) -> Path:
    """Initialise a real tmp git repo with one
    commit on main. Required by iter-20 worktree
    tests."""
    subprocess.run(
        ["git", "init", "-b", "main"],
        cwd=tmp_path, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "config", "user.email", "iter20@test.local"],
        cwd=tmp_path, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "config", "user.name", "iter-20 test"],
        cwd=tmp_path, check=True, capture_output=True
    )
    (tmp_path / "README.md").write_text("# iter-20 test repo\n")
    subprocess.run(
        ["git", "add", "README.md"],
        cwd=tmp_path, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "commit", "-m", "initial"],
        cwd=tmp_path, check=True, capture_output=True
    )
    return tmp_path


def _orchestrator_head(repo: Path) -> str:
    """Return the symbolic-ref name of the repo's HEAD
    (the iter-20 fix must leave this unchanged
    after handle_create_branch)."""
    result = subprocess.run(
        ["git", "symbolic-ref", "--short", "HEAD"],
        cwd=repo, check=True, capture_output=True
    )
    return result.stdout.decode().strip()


def test_create_branch_does_not_switch_orchestrator_head(
    tmp_git_repo: Path,
) -> None:
    """iter-20 Phase 1: handle_create_branch must
    use `git worktree add`, leaving the orchestrator's
    HEAD on its original branch. iter-19 demo's
    Backend used `git checkout -b` to switch the
    orchestrator's worktree to its own branch —
    surfaced in iter_19_demo_report.md Caveat B."""
    from tools.mcp_servers.ai_team_repo.handlers import (
        handle_create_branch,
    )

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
```

- [ ] **Step 1.1.2 — Run** — expect FAIL:

```
uv run pytest tests/unit/test_mcp_ai_team_repo_handlers.py::test_create_branch_does_not_switch_orchestrator_head -v
```

Expected reason: current `handle_create_branch`
uses `git checkout -b`, switching HEAD.

#### Step 1.2 — Green: rewrite handle_create_branch to use `git worktree add`

- [ ] **Step 1.2.1 — Edit
  `tools/mcp_servers/ai_team_repo/handlers.py`**.
  At module top (below the existing constants):

```python
# iter-20: module-level state for the per-session
# "active worktree" — the directory `handle_create_branch`
# created. Subsequent handler calls in the same MCP
# server process use this as cwd. Naturally scoped
# to ONE agent's session because claude -p spawns
# a fresh MCP server subprocess per invocation —
# the variable's lifetime IS the agent's session.
# See iter_19_demo_report.md Caveat B + iter_20.md
# Phase 1 for the design rationale.
_ACTIVE_WORKTREE: Path | None = None


def _slugify_branch(branch: str) -> str:
    """Filesystem-safe directory name from a branch
    ref. `agent/backend_developer/foo-bar` →
    `agent_backend_developer_foo-bar`."""
    return branch.replace("/", "_")


def _effective_cwd(ctx: Context) -> Path:
    """The cwd subsequent subprocess calls should
    use: the active agent worktree if create_branch
    has run, else the scope root."""
    return _ACTIVE_WORKTREE if _ACTIVE_WORKTREE is not None else ctx.scope.root
```

- [ ] **Step 1.2.2** — Replace the body of
  `handle_create_branch`:

```python
async def handle_create_branch(
    ctx: Context, args: dict[str, Any]
) -> dict[str, Any]:
    global _ACTIVE_WORKTREE  # noqa: PLW0603 - per-MCP-server-process active worktree
    branch = str(args.get("branch", ""))
    base = str(args.get("base") or ctx.default_pr_base)
    if not _BRANCH_ALLOWED_RE.match(branch):
        return _err(f"branch {branch!r} not allowed; must match agent/<role>/<slug>")
    if ctx.forbid_branch_re.match(branch):
        return _err(f"branch {branch!r} is forbidden by AI_TEAM_FORBID_BRANCH_RE")
    worktree_path = (
        ctx.scope.root / ".claude" / "agent-worktrees" / _slugify_branch(branch)
    )
    # iter-20: `git worktree add` instead of `git checkout -b`.
    # Creates an isolated working tree at `worktree_path`
    # sharing the same `.git` dir; orchestrator's HEAD
    # is UNAFFECTED. See iter_19_demo_report.md Caveat B
    # for the iter-19 demo failure that motivated this.
    proc = await asyncio.create_subprocess_exec(
        "git",
        "worktree",
        "add",
        str(worktree_path),
        "-b",
        branch,
        base,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=str(ctx.scope.root),
    )
    _, err = await proc.communicate()
    if proc.returncode != 0:
        return _err(f"git worktree add failed: {err.decode(errors='replace')[:500]}")
    _ACTIVE_WORKTREE = worktree_path
    return _ok(
        {
            "branch": branch,
            "base": base,
            "created": True,
            "worktree_path": str(worktree_path),
        }
    )
```

- [ ] **Step 1.2.3** — Update three other handlers
  to consult `_effective_cwd(ctx)` instead of
  `ctx.scope.root`:

In `handle_status`:
```python
        cwd=str(_effective_cwd(ctx)),
```

In `handle_run_shell` (line ~167):
```python
        cwd=str(_effective_cwd(ctx)),
```

In `handle_open_pr` (line ~208):
```python
        cwd=str(_effective_cwd(ctx)),
```

In `handle_write_file_in_scope`: the `resolve_in_scope`
call uses `ctx.scope.root` to resolve paths.
**Decision**: leave `write_file_in_scope`'s
scope resolution AS-IS (relative to scope.root)
but write the actual file under the active
worktree. The path under the worktree is the
SAME relative path. So change:

```python
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(content)
```
to:
```python
        effective_root = _effective_cwd(ctx)
        relative = resolved.relative_to(ctx.scope.root)
        effective_resolved = effective_root / relative
        effective_resolved.parent.mkdir(parents=True, exist_ok=True)
        effective_resolved.write_text(content)
```
and update the return payload's `absolute_path`:
```python
        return _ok(
            {
                "path": path,
                "absolute_path": str(effective_resolved),
                "bytes_written": len(content),
            }
        )
```

- [ ] **Step 1.2.4 — Run the new test** — expect PASS:

```
uv run pytest tests/unit/test_mcp_ai_team_repo_handlers.py::test_create_branch_does_not_switch_orchestrator_head -v
```

#### Step 1.3 — Red+Green: write_file uses the active worktree

- [ ] **Step 1.3.1** — Add test:

```python
def test_write_file_after_create_branch_lands_in_worktree(
    tmp_git_repo: Path,
) -> None:
    """After handle_create_branch sets the active
    worktree, write_file_in_scope's writes go INTO
    the worktree, not the orchestrator's tree."""
    from tools.mcp_servers.ai_team_repo.handlers import (
        handle_create_branch,
        handle_write_file_in_scope,
    )

    ctx = _ctx(tmp_git_repo)
    cb_result = asyncio.run(
        handle_create_branch(
            ctx,
            {"branch": "agent/backend_developer/wf-test", "base": "main"},
        )
    )
    assert cb_result["isError"] is False
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
```

- [ ] **Step 1.3.2 — Run** — expect PASS if the
  Step 1.2.3 edits are in. If FAIL, the edit
  diverged from the planned shape; re-read and
  align.

#### Step 1.4 — Module-level state reset between tests

- [ ] **Step 1.4.1** — Since `_ACTIVE_WORKTREE` is
  module-level, tests can leak state. Add an
  autouse fixture at the top of
  `test_mcp_ai_team_repo_handlers.py`:

```python
@pytest.fixture(autouse=True)
def _reset_active_worktree() -> Iterator[None]:
    """iter-20: _ACTIVE_WORKTREE is module-level
    (naturally scoped to one MCP server process,
    but pytest reuses the module across tests).
    Reset between tests so order doesn't matter."""
    from tools.mcp_servers.ai_team_repo import handlers
    handlers._ACTIVE_WORKTREE = None
    yield
    handlers._ACTIVE_WORKTREE = None
```

Make sure `Iterator` is imported from
`collections.abc`.

- [ ] **Step 1.4.2 — Run the full handlers test
  suite** — expect all green:

```
uv run pytest tests/unit/test_mcp_ai_team_repo_handlers.py -v
```

#### Step 1.5 — Commit Phase 1

- [ ] **Step 1.5.1**:

```bash
git add tools/mcp_servers/ai_team_repo/handlers.py tests/unit/test_mcp_ai_team_repo_handlers.py
git commit -m "feat(iter-20): handle_create_branch uses git worktree add (close iter-19 Caveat B)

iter-19 demo run #1 surfaced the first concrete
materialisation of iter-17 retro #7
('Agents-branch-isolation'): the Backend agent
ran handle_create_branch which executed
'git checkout -b <branch> <base>' in
cwd=ctx.scope.root (the orchestrator's worktree),
switching the orchestrator's HEAD to the agent's
branch mid-chain.

This patch replaces 'git checkout -b' with
'git worktree add <isolated_path> -b <branch>
<base>'. The new worktree lives at
<scope_root>/.claude/agent-worktrees/<slugified_branch>/
and shares the orchestrator's .git dir; the
orchestrator's HEAD is unaffected.

A module-level _ACTIVE_WORKTREE tracks the
worktree path so subsequent handler calls
(handle_run_shell, handle_write_file_in_scope,
handle_status, handle_open_pr) use it as cwd.
Naturally scoped to one MCP server process,
which lasts exactly one agent's session — claude
-p spawns a fresh MCP server per invocation.

2 new unit tests pin the contract:
- test_create_branch_does_not_switch_orchestrator_head
  (asserts orchestrator HEAD unchanged + worktree
  dir created + branch active inside the worktree)
- test_write_file_after_create_branch_lands_in_worktree
  (asserts files land in worktree, not
  orchestrator tree)"
```

### Phase 2 — TL Backend decomposition prompt edit

**Goal**: Add explicit guidance to TL that Backend
work over ~200 LOC must be decomposed into
multiple Backend subtasks. Prompt-only fix;
runtime tripwire deferred to iter-21+ if demo
still times out.

**Files**:
- Modify: `prompts/team_lead.md`
- Test: extend `tests/unit/test_team_lead_agent.py`
  with a content assertion

#### Step 2.1 — Red: prompt content pin

- [ ] **Step 2.1.1 — Add an assertion** to
  `tests/unit/test_team_lead_agent.py` at the bottom:

```python
def test_tl_prompt_teaches_backend_decomposition() -> None:
    """iter-20 Phase 2: TL prompt must explicitly
    instruct decomposition of large Backend tasks.
    Backend's 600s timeout was the chain-killer in
    iter-19 demo run #1; iter-20 prompts TL to
    avoid emitting single huge Backend subtasks.
    See iter_19_demo_report.md Caveat A."""
    from pathlib import Path

    text = Path("prompts/team_lead.md").read_text()
    # Look for the iter-20 marker (the explicit
    # ≤200 LOC guidance) to confirm the prompt
    # update landed.
    assert "200 LOC" in text or "200 lines" in text, (
        "TL prompt missing iter-20 Backend-decomposition guidance"
    )
    assert "backend" in text.lower()
```

- [ ] **Step 2.1.2 — Run** — expect FAIL (prompt
  doesn't mention "200 LOC" yet).

#### Step 2.2 — Green: edit the prompt

- [ ] **Step 2.2.1 — Edit
  `prompts/team_lead.md`**, replacing the
  "Decomposition style" section:

```markdown
## Decomposition style

- Decompose the task into the smallest useful set of subtasks.
- Prefer fewer, larger subtasks over many tiny ones — the team is small.
- **Exception for Backend work** — `backend_developer` subtasks must be
  scoped to ≤200 LOC of new/modified code, because the agent's session
  timeout is 600s and exceeding it cascades a chain failure across
  every downstream agent. If the requested Backend work plausibly
  exceeds ~200 LOC, emit **multiple** Backend subtasks with explicit
  `depends_on` slugs:
  - first subtask: build the data model + tests
  - second subtask: build the service layer (depends_on the first)
  - third subtask: wire the API surface (depends_on the second)
  Each should be reviewable in one PR. Smaller, sequential subtasks
  with `depends_on` are STRONGLY preferred over a single 500-LOC
  Backend subtask — see iter_19_demo_report.md Caveat A for the
  failure mode this rule prevents.
- If a request is ambiguous, route it to `product_manager` as a clarification
  subtask before any work begins (other subtasks `depends_on` that PM
  clarification).
```

- [ ] **Step 2.2.2 — Run** — expect PASS:

```
uv run pytest tests/unit/test_team_lead_agent.py::test_tl_prompt_teaches_backend_decomposition -v
```

#### Step 2.3 — Commit Phase 2

- [ ] **Step 2.3.1**:

```bash
git add prompts/team_lead.md tests/unit/test_team_lead_agent.py
git commit -m "feat(prompts): TL must decompose Backend work into ≤200 LOC subtasks (iter-20 Phase 2)

iter-19 demo run #1 Caveat A: Backend's
LLMTimeoutError at 600s killed the chain before
QA could run. The 9-iteration carry-over has
been 'TL must decompose Backend into smaller
chunks' — iter-20 finally ships the prompt
update.

The new 'Exception for Backend work' section
under 'Decomposition style' instructs TL to emit
multiple Backend subtasks with depends_on slugs
when the work exceeds ~200 LOC. Three-subtask
example (data model → service layer → API
surface) gives the LLM a concrete template.

Prompt-only fix for iter-20. Runtime tripwire
(Backend agent rejects a too-large
task_assignment payload) deferred to iter-21+
if this prompt edit doesn't fix the timeout in
the iter-20 demo."
```

### Phase 3 — `demo_iter_20.sh` with worktree cleanup

**Goal**: Demo script clones iter-19's, adds
`git worktree prune` on entry + worktree
removal on exit so the iter-20 changes leave
the orchestrator's `.claude/agent-worktrees/`
directory clean.

**Files**:
- Create: `scripts/demo_iter_20.sh`
- Modify: `Makefile`

#### Step 3.1 — Clone iter-19 and edit

- [ ] **Step 3.1.1**:

```bash
cp scripts/demo_iter_19.sh scripts/demo_iter_20.sh
chmod +x scripts/demo_iter_20.sh
```

- [ ] **Step 3.1.2 — Rewrite the header narrative**
  (lines 1–48) for iter-20 — describe the
  branch-isolation fix + TL prompt edit + that
  the success criterion is "the QA-emitted
  pending_review row that iter-19 deferred."

- [ ] **Step 3.1.3** — Change `MCP_CONFIG` path
  (line ~80) from `.iter19-mcp.json` to
  `.iter20-mcp.json`.

- [ ] **Step 3.1.4** — Update the demo task title
  (~line 137) from "iter-19 demo" → "iter-20
  demo".

- [ ] **Step 3.1.5 — Add worktree pre-flight**
  after `step "1/7 — Start infra"`'s block:

```bash
step "1.5/7 — Prune stale agent worktrees"
# iter-20: handle_create_branch now creates
# isolated worktrees under
# .claude/agent-worktrees/. Stale ones from
# prior demo runs would confuse `git worktree
# add`. Prune first.
git worktree prune
rm -rf .claude/agent-worktrees/ 2>/dev/null || true
ok "agent worktrees pruned"
```

- [ ] **Step 3.1.6 — Add worktree cleanup to the
  EXIT trap** (~line 106):

```bash
trap '
    kill $API_PID 2>/dev/null || true
    rm -f "$API_LOG" "$MCP_CONFIG"
    # iter-20: clean up isolated agent worktrees
    if [[ -d .claude/agent-worktrees ]]; then
        for wt in .claude/agent-worktrees/*/; do
            [[ -d "$wt" ]] || continue
            git worktree remove --force "$wt" 2>/dev/null || rm -rf "$wt"
        done
        rmdir .claude/agent-worktrees 2>/dev/null || true
    fi
' EXIT
```

- [ ] **Step 3.1.7 — Update the auto-approve
  comment text** (~line 226) from "iter-19 demo
  auto-approve" → "iter-20 demo auto-approve".

#### Step 3.2 — Makefile + smoke

- [ ] **Step 3.2.1 — Add Makefile target**:

Edit `Makefile`:
```makefile
demo: demo-iter-20 ## Alias for the current iteration's demo

demo-iter-20: ## Run iter-20 e2e (git worktree add + TL Backend decomposition)
	bash scripts/demo_iter_20.sh
```

Add `demo-iter-20` to the `.PHONY` declaration line.

- [ ] **Step 3.2.2** — `bash -n scripts/demo_iter_20.sh`
  expect no output (syntax OK).

#### Step 3.3 — Commit Phase 3

- [ ] **Step 3.3.1**:

```bash
git add scripts/demo_iter_20.sh Makefile
git commit -m "chore(demo): demo_iter_20.sh with agent-worktree cleanup

Clone of demo_iter_19.sh with iter-20 narrative
plus worktree pre-flight + cleanup:

- Pre-flight: 'git worktree prune' + rm -rf
  .claude/agent-worktrees/ before chain start,
  so stale paths from prior demo runs don't
  confuse 'git worktree add'.
- EXIT trap: 'git worktree remove --force' over
  every .claude/agent-worktrees/*/, with rm -rf
  fallback. Keeps the orchestrator's repo clean
  between demos.

Makefile alias demo-iter-20 added; demo target
repointed."
```

### Phase 4 — Validation gates

- [ ] **Step 4.1.1 — ruff check**:
  `uv run ruff check .`
  Expected: `All checks passed!`
- [ ] **Step 4.1.2 — ruff format --check**:
  `uv run ruff format --check .`
- [ ] **Step 4.1.3 — mypy strict**:
  `uv run mypy .`
  Expected: `Success: no issues found`.
- [ ] **Step 4.1.4 — bandit high-only**:
  `uv run bandit -ll -q -r core agents apps tools`
  Expected: `High: 0`.
- [ ] **Step 4.1.5 — full unit suite**:
  `uv run pytest tests/unit -q`
  Expected: all green. iter-19's 418 baseline +
  3 new tests = 421.
- [ ] **Step 4.1.6 — full integration suite**:
  `make up >/dev/null && uv run pytest tests/integration -q`
- [ ] **Step 4.1.7 — smoke-llm**:
  `make smoke-llm`
  Expected: `Overall: PASS`.

### Phase 5 — Real-LLM iter-19-shape demo + report

**Goal**: Re-run the same idea-validator-v2 task
that iter-19 attempted, expect this time the
chain reaches QA and QA writes the pending_review
row.

#### Step 5.1 — Pre-flight

- [ ] **Step 5.1.1**:

```bash
docker ps --filter name=ai_team_ --format '{{.Names}} {{.Status}}'
[ -f .env ] && grep -c '^OWNER_TOKEN=' .env
claude --version
```

- [ ] **Step 5.1.2 — Reset pending_reviews**:

```bash
docker exec ai_team_postgres psql -U ai_team -d ai_team -c \
    "DELETE FROM pending_reviews WHERE status = 'pending';"
```

The iter-18 approved row remains; only stale
pendings are cleared.

#### Step 5.2 — Run

- [ ] **Step 5.2.1**:

```bash
AI_TEAM_DEMO_NON_INTERACTIVE=1 bash scripts/demo_iter_20.sh \
    2>&1 | tee /tmp/iter_20_demo_run_1.log
```

Wall-clock: 30 min initial + 15 min retry = 45 min.

#### Step 5.3 — Capture results

- [ ] **Step 5.3.1 — Confirm orchestrator HEAD
  unchanged** (the iter-19 surprise must not
  recur):

```bash
git rev-parse --abbrev-ref HEAD
```

Expected: `worktree-iter-20`.

- [ ] **Step 5.3.2 — Inspect agent worktrees**:

```bash
git worktree list
```

Expected: orchestrator + one entry per agent
worktree (likely just Backend, since other
agents either don't call create_branch
explicitly or their `cwd` is the orchestrator's
tree for non-mutating ops).

- [ ] **Step 5.3.3 — Inspect pending_review**:

```bash
docker exec ai_team_postgres psql -U ai_team -d ai_team -c \
    "SELECT id, correlation_id, requesting_agent, status, summary
     FROM pending_reviews WHERE status = 'pending'
     ORDER BY created_at DESC LIMIT 5;"
```

**Success criterion**: at least one row with
`requesting_agent = 'qa_engineer'`. This is
iter-19's deferred criterion finally met.

- [ ] **Step 5.3.4 — Cost tally**:

```bash
docker exec ai_team_postgres psql -U ai_team -d ai_team -c \
    "SELECT SUM((payload_json -> 'metadata' -> 'llm' ->> 'cost_cents')::int) AS total_cents
     FROM audit_log
     WHERE correlation_id = '<CORRELATION>';"
```

#### Step 5.4 — Write the demo report

- [ ] **Step 5.4.1** — Create
  `docs/iterations/iter_20_demo_report.md`.
  Required sections (mirror iter-19's shape):
  Date / Run by / Script / Correlation / Outcome
  / Verdict / Run walkthrough / What worked /
  What didn't (carry-overs to iter-21) / Cost /
  Artifacts / Action items for iter-21.

- [ ] **Step 5.4.2 — Commit**:

```bash
git add docs/iterations/iter_20_demo_report.md
git commit -m "docs(iter-20): real-LLM demo report — QA-emitted pending_review (or honest partial)"
```

### Phase 6 — Retro + iter-21 handoff

- [ ] **Step 6.1.1** — Write
  `docs/iterations/iter_20_retro.md`.
- [ ] **Step 6.1.2** — Write
  `docs/iterations/iter_21_handoff.md`.
- [ ] **Step 6.1.3 — Commit**:

```bash
git add docs/iterations/iter_20_retro.md docs/iterations/iter_21_handoff.md
git commit -m "docs(iter-20): retro + iter-21 handoff"
```

### Phase 7 — Merge to `main` via PR

- [ ] **Step 7.1.1 — Push**:
  `git push -u origin worktree-iter-20`
- [ ] **Step 7.1.2 — Open PR** via `gh pr create`
  (template mirrors iter-19 PR #26).
- [ ] **Step 7.1.3 — Wait for CI green**:
  `gh pr checks <N> --watch`
- [ ] **Step 7.1.4 — Squash-merge**:
  `gh pr merge <N> --squash --delete-branch`

## Success criteria (definition of done for iter-20)

1. **Phase 1** — `handle_create_branch` uses
   `git worktree add`; orchestrator HEAD unchanged
   after invocation. 2 new unit tests pin the
   contract. `_ACTIVE_WORKTREE` module-level
   tracks the per-session worktree.
2. **Phase 2** — TL prompt teaches Backend
   decomposition; assertion test pinned.
3. **Phase 3** — `scripts/demo_iter_20.sh` prunes
   stale worktrees on entry + removes them on
   exit. `make demo-iter-20` invokes it.
4. **Phase 4** — every gate green
   (ruff/mypy/bandit/unit/integration/smoke-llm).
5. **Phase 5** — Real-LLM demo: orchestrator
   HEAD stays on `worktree-iter-20` post-run;
   a `pending_reviews` row exists with
   `requesting_agent='qa_engineer'` for the
   first time across 19+ iterations. Cost < $5.
6. **Phase 6** — retro + iter-21 handoff
   committed.
7. **Phase 7** — squash-merged to `main` with
   CI green.

## Out of scope (deferred to iter-21+)

- **Backend runtime tripwire** that rejects
  too-large `task_assignment` payloads. iter-20
  is prompt-only; if the prompt edit doesn't
  fix the timeout, iter-21 adds the tripwire.
- **HoldQueue persistence** (Postgres-backed).
- **`pytest-rerunfailures` plugin pin**.
- **TL auto-hop investigation**.
- **TL over-decomposition prompt hint** — partially
  addressed by iter-20's Backend-decomposition
  edit, but the Architect re-derivation pattern
  is unchanged.
- **Architect spend watch**.
- **`audit_writer` Postgres role**.
- **Hash-chain alert job**.
- **`GitHubTargetRepo` implementation**.
- **TL decomposition transactional insert**.
- **`BaseAgent.handle()` template-method refactor**.
- **`mark_task_done` / `update_task_status`** real
  implementations.
- **Substrate-level `--allowed-tools ""` fix**.

## Risk + mitigations

| Risk | Likelihood | Mitigation |
|------|-----------:|-----------|
| `_ACTIVE_WORKTREE` module-level leaks across pytest test functions | High (caught upfront) | Autouse fixture in Phase 1.4 resets the variable per test. |
| `git worktree add` fails because target dir exists from prior demo | Medium | Phase 3.1.5 pre-flight `git worktree prune` + `rm -rf` clears. |
| Agent's MCP path-scope (`AI_TEAM_PATH_PREFIXES`) doesn't translate to the worktree's relative paths correctly | Low | `resolve_in_scope` operates on `ctx.scope.root`-relative paths; the worktree uses the SAME relative-path semantics by design. Phase 1.3.2 test asserts. |
| TL prompt edit makes TL over-decompose other agents' work | Low-medium | The edit is explicitly scoped to "Backend" only; other roles unaffected. |
| iter-19 demo task's Backend work was ~250 LOC; even decomposed it might trip a 600s timeout per chunk | Medium | If demo hits this, iter-21 needs the runtime tripwire AND Backend prompt edits for smaller per-call scope. Acceptable "iter-21 carry-over" outcome. |
| Per-agent worktrees consume disk + slow down `git fetch` (each worktree has its own index) | Low | iter-20's demo cleans up on exit; ongoing disk usage is bounded by one worktree per concurrent agent. |
| The `_ACTIVE_WORKTREE` pattern doesn't support an agent that calls create_branch twice in one session | Low | iter-20 design: second call overwrites the first. Acceptable; iter-21+ can add a "branch already exists" guard if needed. |

## What this plan does NOT do

- **Does not introduce per-agent worktrees managed
  by the dispatcher**. Option (b) from
  `iter_20_handoff.md` §1 (TargetRepo-managed
  worktrees + `cwd` injected via `LLMClient.invoke`)
  is the durable architectural fix; iter-20 ships
  the surgical alternative (Option (a) extended:
  fix the MCP handler that was the actual
  problem). Tracked for iter-21+ if the surgical
  fix proves insufficient.
- **Does not change ADR-0004's tool matrix** —
  `create_branch` remains in the agent allow-lists;
  its semantics change beneath them.
- **Does not address the deferred carry-overs**
  (4–15 in iter_20_handoff.md). They forward to
  `iter_21_handoff.md`.
- **Does not add a Backend runtime tripwire**.
  iter-20 is prompt-only; iter-21 adds the
  tripwire if the prompt edit alone doesn't
  rescue the demo.
