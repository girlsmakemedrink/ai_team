# ADR-0009 — `TARGET_REPO` abstraction

- **Status**: Accepted
- **Date**: 2026-05-18

## Context

`ai_team`'s long-term purpose is to develop *commercial products*, each in
its own repository. The MVP is self-bootstrapping (the team develops
`ai_team` itself) — but the architecture must not bake that assumption
into agent code. Otherwise, when we point the team at a separate repo,
we'd be refactoring half the system.

We also have the training task in `examples/sandbox/idea-validator/`
which is *inside* `ai_team` but conceptually a "target product." That's
a third mode (in-repo example).

## Decision

Every code-producing or repo-touching agent receives a `TargetRepo`
instance as part of its task context. Self-bootstrapping, example/sandbox,
and external commercial repos are *three concrete implementations* of
the same interface.

### Interface

```python
# core/target_repo/base.py

class TargetRepo(ABC):
    name: str                       # human-readable
    root: Path                      # local working tree
    default_branch: str = "main"
    remote_url: str | None = None   # None for example/sandbox sub-trees

    @abstractmethod
    async def ensure_local_clone(self) -> Path: ...
    @abstractmethod
    async def checkout(self, branch: str, *, base: str | None = None) -> None: ...
    @abstractmethod
    async def stage_and_commit(self, paths: Sequence[str], message: str,
                                author: str) -> str: ...   # commit sha
    @abstractmethod
    async def push(self, branch: str) -> None: ...
    @abstractmethod
    async def open_pr(self, *, head: str, base: str, title: str, body: str
                      ) -> PullRequest: ...
    @abstractmethod
    async def run_tests(self, command: str | None = None) -> TestRunResult: ...
    @abstractmethod
    async def run_linter(self) -> LintRunResult: ...
    @abstractmethod
    async def status(self) -> RepoStatus: ...
```

### Implementations

1. **`SelfBootstrapTargetRepo`** — `name='ai_team'`,
   `root=/Users/<owner>/ai_team`, `remote_url=...ai_team.git`. The repo
   we're in. Used when the owner says "improve ai_team itself."
2. **`InRepoExampleTargetRepo`** — `name='idea_validator'`,
   `root=ai_team/examples/sandbox/idea-validator`,
   `remote_url=None`. Code lives inside `ai_team`; commits made on
   ai_team branches. Used for Iteration 1–2 training task.
3. **`GitHubTargetRepo`** — `name='<external>'`, `root` is a cloned
   working copy under `~/.ai_team/workspaces/<repo>/`,
   `remote_url='git@github.com:<owner>/<repo>.git'`. Used for actual
   commercial products. Constructed from a `TARGET_REPO` env or per-task
   override.

### Task assignment

`TaskAssignmentPayload` carries an optional `target_repo: str | None`:

- `None` → defaults to `DEFAULT_TARGET_REPO` env (Iteration 0–2:
  `ai_team` itself).
- `"examples/sandbox/idea_validator"` → `InRepoExampleTargetRepo`.
- `"https://github.com/<owner>/<repo>"` or `"<owner>/<repo>"` →
  `GitHubTargetRepo`.

The dispatcher resolves the string to an implementation via a factory
in `core/target_repo/registry.py` before forwarding to the agent.

### Authentication

- **Self / in-repo example**: use local file-system access; `git`
  operations use the owner's existing local credentials.
- **External GitHub repos**: use the owner's `gh` CLI auth (Iteration
  2+); future commercial use may add per-repo PATs.

### Branch model (default for all repos)

- Agents work on `agent/<role>/<correlation-id-short>-<slug>` branches.
- Agent commits author themselves as `<Role Name> via ai_team
  <role@ai-team.local>`, with a `Co-Authored-By: <Owner>` trailer.
- PRs target `develop` (or the repo's configured default working branch),
  never `main` directly.
- Merge to `main` is owner-approved release operation; never automated.

### Scopes & safety

- `TargetRepo.stage_and_commit` rejects paths outside `target_repo.root`.
- `push` rejects refs matching `main|master|release/.*` (only
  branches under `agent/` and `develop` are permitted programmatically).
- All repo operations are wrapped by `mcp__ai_team_repo__*` MCP tools
  (Iteration 2 deliverable) that add audit-log entries.

## Consequences

### Positive

- Self-bootstrap, sandbox example, and commercial repos are
  indistinguishable from the agent's point of view — write code, ask the
  `TargetRepo` to commit and push.
- Switching the team to a new commercial product is a configuration
  change (env + onboarding script), not a code change.
- The interface forces us to think about "what does this agent need from
  the repo?" up front. Agents that don't need a repo (PM, Architect
  drafting ADRs) don't get one.

### Negative

- Three implementations to maintain. Acceptable; the surface area is
  small.
- `GitHubTargetRepo` working tree management adds operational state to
  the host (clones under `~/.ai_team/workspaces/`). Cleanup policy: GC
  workspaces unused > 14 days, configurable.

## Alternatives considered

- **Hardcode `ai_team` self-bootstrap and refactor later.** Rejected by
  owner: explicit project requirement to design for arbitrary
  `TARGET_REPO` from the start.
- **One git wrapper class, configured via env.** Rejected — the
  semantics of "in-repo example" (no remote) and "external repo" (clone
  + remote + auth) are different enough that conditional logic in one
  class is uglier than three small classes.

## References

- [ADR-001 — Orchestrator][ADR-001]
- [ADR-002 — Message schema][ADR-002] (`target_repo` field)
- [ADR-004 — Tool inventory][ADR-004] (path-scope enforcement)

[ADR-001]: 0001-orchestrator-choice.md
[ADR-002]: 0002-message-schema.md
[ADR-004]: 0004-tool-inventory.md
