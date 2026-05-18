# Iteration 2 — Architect + Backend + QA online, first MCP repo tools, end-to-end demo

- **Status**: Approved 2026-05-18 (owner accepted the three recommendations below)
- **Plan author**: Claude (Opus 4.7)
- **Date drafted**: 2026-05-18
- **Base commit**: `aea9ff7` on `main`
- **Branch**: `worktree-iter-2`
- **Anchors (do not contradict)**: ADR-001, ADR-004, ADR-008, ADR-009; iter-1 retro action items

> Per project convention: this document is reviewed by the owner *before*
> any code is written. After review, code changes land as small
> conventional commits, each squash-merged to `main` once CI is green.

## Goal — one sentence

Stand up Architect (Opus), Backend Developer (Sonnet), and QA Engineer
(Sonnet) agents behind a path-scoped `mcp-ai-team-repo` MCP server,
implement the `TargetRepo` concrete classes, and run an end-to-end
"implement idea-validator from spec" demo against real `claude -p`,
ending at owner approval of the resulting PR.

## Success criteria (binary, measurable)

1. **Cache report** at `docs/iterations/iter_2_cache_report.md` shows
   ≥ 30 % input-token reduction on the second `--session-id` turn (same
   bar ADR-008 set). If miss → halt and revisit ADR-001/008 before any
   agent code lands.
2. `LLMResponse.validated_against_schema` exists, is `True` exactly when
   `claude -p` populated `structured_output`, and is logged on every
   `llm.invoke.ok`.
3. `mcp-ai-team-repo` server present in `tools/mcp_servers/ai_team_repo/`
   with the five tools below, all unit-tested, path-scope-enforced per
   ADR-004. Backend's `allowed_tools` contains **no raw `Bash`**.
4. `core/target_repo/{self_bootstrap,in_repo_example,registry}.py`
   implemented, with a unit test that proves `push` to `main` /
   `master` / `release/*` is refused.
5. Architect, Backend Developer, QA Engineer agent classes wired in
   the dispatcher; each has a system prompt under `prompts/`, an
   `allowed_tools` matching ADR-004's matrix, and unit tests with
   `MockLLMClient` cassettes.
6. `scripts/demo_iter_2.sh` runs end-to-end **against real `claude -p`**:
   owner submits the idea-validator spec → TL decomposes → Architect
   emits ADR → Backend opens PR with code + tests in
   `examples/sandbox/idea-validator/` → QA reports green → row lands in
   `pending_reviews` → `ai-team approve <id>` clears it. Wall time
   target: < 5 min, cost estimate: < $0.40.
7. `make test-unit` green; `make test-integration` green; `make lint`,
   `make typecheck`, `make sec` clean; diff-cover ≥ 80 %; `bandit` high
   = 0; `make smoke-llm` green.
8. Pre-push hook installed and documented; `make install-hooks` exists.
9. `docs/iterations/iter_2_retro.md` written with action items for
   iter-2b.

## Non-goals (explicitly deferred)

- Designer / Frontend / DevOps-as-agent / SRE / Market Researcher
  (→ iter-2b).
- `GitHubTargetRepo` impl — no external commercial repo yet (→ first
  real product).
- `audit_writer` Postgres role binding (→ iter-3 security harden).
- Hash-chain alert job (→ iter-3).
- Self-hosted runner for `real-llm.yml` (→ iter-5).
- TL checkpoint digests as a timer (manual `ai-team digest` is enough
  for now).
- Splitting API + dispatcher processes (→ iter-5 server move).

## Out-of-scope but adjacent (will get a TODO, not code)

- Per-repo PATs for `gh` (`GitHubTargetRepo` will document this once it
  lands).
- MCP `WebFetch` allowlist (PM is the only current consumer; closing it
  is iter-2b alongside Market Researcher).

## Plan — two phases

### Phase 1 — Day-1 prep (in this order; each PR is small)

| # | Task | Output | Gate |
|---|------|--------|------|
| 1A | Re-measure cache savings under `--session-id` | `docs/iterations/iter_2_cache_report.md` | ≥ 30 % input-token reduction |
| 1C | `LLMResponse.validated_against_schema` | `core/llm/base.py` + `claude_code_headless.py` + tests | structlog event shows it |
| 1D | Pre-push hook + `make install-hooks` | `.githooks/pre-push`, Makefile target, README note | hook fails on lint-dirty |
| 1B | `mcp-ai-team-repo` server | `tools/mcp_servers/ai_team_repo/` + `config.example.json` update | unit tests for path-scope + branch-guard |

Why this order: 1A is the floor — if cache collapsed we don't write any
agents this iteration. 1C, 1D unblock the test loop. 1B (the new MCP
server) is the largest, so we do it last in Phase 1 and only when we
know the floor holds.

### Phase 2 — Day-2+ agents (parallelisable after Phase 1)

| # | Task | Output | Owner approval |
|---|------|--------|----------------|
| 2A | `TargetRepo` impls + factory | `core/target_repo/{self_bootstrap,in_repo_example,registry}.py` | unit |
| 2B | Architect agent + prompt | `agents/architect/`, `prompts/architect.md` | unit + cassette |
| 2C | Backend Developer agent + prompt | `agents/backend_developer/`, `prompts/backend_developer.md` | unit + cassette |
| 2D | QA Engineer agent + prompt | `agents/qa_engineer/`, `prompts/qa_engineer.md` | unit + cassette |
| 2E | End-to-end demo against real `claude -p` | `scripts/demo_iter_2.sh`, `make demo-iter-2`, PR in `pending_reviews` | owner runs `ai-team approve` |
| 2F | Retro + iter-2b handoff stub | `docs/iterations/iter_2_retro.md`, `iter_2b_handoff.md` | n/a |

2B, 2C, 2D can be drafted in parallel but merged in order (Architect
first, since its ADR is what Backend reads).

## Detailed design notes

### `mcp-ai-team-repo` tool surface (Task 1B)

Per ADR-004's "Bash never raw" rule. Server exposes:

```
mcp__ai_team_repo__create_branch(branch: str, base: str = "develop")
mcp__ai_team_repo__write_file_in_scope(path: str, content: str, mode: "create" | "overwrite")
mcp__ai_team_repo__run_shell(command_class: Literal[
    "pytest", "ruff", "mypy",
    "git_status", "git_diff", "git_add", "git_commit", "git_push_feature",
    "gh_pr_create", "make_test",
], args: list[str])
mcp__ai_team_repo__open_pr(head: str, base: str, title: str, body: str)
mcp__ai_team_repo__status()  # echoes RepoStatus
```

- All five are thin wrappers over a `TargetRepo` instance resolved from
  the agent's correlation context.
- `write_file_in_scope` rejects any path that resolves outside the
  caller's per-role scope from ADR-004's table.
- `run_shell` validates `command_class` is in the enum, then validates
  `args` against the per-class prefix list. `git_push_feature` refuses
  refs matching `^(main|master|release/.*)$`.
- `open_pr` always sets base = `develop` (or repo-configured working
  branch) — never `main`.
- Every call audited via the existing `audit_writer` chain with
  `tool_call` payload type (ADR-003 already supports this).

### `TargetRepo` impls (Task 2A)

- `SelfBootstrapTargetRepo`: `root = Path(__file__).resolve().parents[2]`
  (the `ai_team` checkout). `remote_url = git@github.com:girlsmakemedrink/ai_team.git`.
- `InRepoExampleTargetRepo`: `root = ai_team_root / "examples/sandbox/idea-validator"`.
  `remote_url = None`. `stage_and_commit` rejects paths outside that
  sub-tree. PR target = `develop` on `ai_team`.
- `registry.resolve(target_repo: str | None) -> TargetRepo`:
  - `None` → `DEFAULT_TARGET_REPO` env → `SelfBootstrapTargetRepo`.
  - `"examples/sandbox/idea-validator"` → `InRepoExampleTargetRepo`.
  - `"<owner>/<repo>"` or URL → raises `NotImplementedError("GitHubTargetRepo deferred")`.

### Agent prompts — tone

Match iter-1 PM/TL house style:

- "respond with JSON only" discipline (works well per retro).
- "Reference the source spec by file path" for artifact links (iter-1
  retro action item).
- Architect prompt explicitly enumerates ADR sections (Context / Decision
  / Consequences / Alternatives / References) and asks for citations to
  existing ADRs by number.
- Backend prompt says "you do not write to `infra/` or
  `.github/workflows/`; if a change there is required, request a
  follow-up task" — keeps role drift out.
- QA prompt says "you do not modify production code; if a fix is needed,
  open a `task_assignment` to Backend Developer."

### Schemas — Architect ADR output

```json
{
  "adr_number": 10,
  "filename": "0010-idea-validator-pipeline.md",
  "title": "...",
  "context": "...",
  "decision": "...",
  "consequences": {"positive": [...], "negative": [...], "neutral": [...]},
  "alternatives": [{"name": "...", "reason_rejected": "..."}],
  "references": ["ADR-009"]
}
```

Validated via `--json-schema`. Architect emits markdown via
`write_file_in_scope` to `docs/adr/<NNNN>-<slug>.md`, then publishes
a `task_report` summary message back to TL.

### End-to-end demo (Task 2E)

`scripts/demo_iter_2.sh`:

1. `make up` (idempotent).
2. `ai-team submit "implement idea-validator from spec at docs/sandbox/idea_validator_spec.md" --target-repo examples/sandbox/idea-validator`.
3. Watch `ai-team watch` for `pending_reviews` row.
4. `ai-team approve <id>` once owner confirms PR.
5. Print final feed digest + total cost.

Pre-flight: skip if `claude -p` quota estimate < 15 % remaining.

## Risks & mitigations

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| Cache savings collapsed under `--session-id` | medium | Task 1A is the *first* gate; halt iter-2 if missed |
| Backend agent over-engineers idea-validator past 300 LOC budget | medium | Spec hard-cap surfaced in PM stories; Architect ADR re-asserts |
| Path-scope wrapper has a bypass (`..`, symlinks) | medium | Unit tests include `..`, absolute, and symlink cases |
| `gh pr create` fails on first commercial repo without auth | low | Defer to `GitHubTargetRepo` iteration; not exercised in iter-2 |
| Real `claude -p` produces malformed JSON for ADR despite schema | low | `validated_against_schema=False` triggers one retry, then `failed_task` |
| Pre-push hook is bypassed via `--no-verify` | n/a | CLAUDE.md already forbids; not a defence layer |

## Cost / quota envelope

- TL (Opus) decomposition: ~$0.04 × 1 = $0.04.
- Architect (Opus) ADR: ~$0.08 × 1 = $0.08.
- Backend (Sonnet) code + tests: ~$0.10 × 2 turns ≈ $0.20.
- QA (Sonnet) run + report: ~$0.02 × 1 = $0.02.
- Smoke + cache report: ~$0.05.
- **Total budgeted ≤ $0.40** per end-to-end run. Multiple runs during
  development; soft cap $2 for iter-2.

## Resolved decisions (owner-approved 2026-05-18)

1. **Default branch for agent PRs on `ai_team`** → **(b)** target `main`
   as a single-repo exception until iter-5. A short note will be added
   to ADR-009 alongside Task 2A. Reason: solo-trunk repo, no parallel
   release lines.
2. **Architect's gating role** → **advisory**. Architect emits an ADR
   as a side-artefact; Backend reads it via `Read`. TL remains the only
   gating router. Keeps the actor graph identical to iter-1.
3. **`idea-validator` LLM substrate** → **shared owner quota** through
   the same `claude -p` adapter. Counts as honest cost accounting.

## Sequencing (one commit = one PR)

```
[iter-2: Day-1 prep]
  c1  docs(iter-2): plan
  c2  feat(llm): validated_against_schema field
  c3  build: pre-push hook + install-hooks target
  c4  feat(smoke): cache-ratio measurement under --session-id
  c5  docs(iter-2): cache report
  c6  feat(mcp): mcp-ai-team-repo server + path-scope wrappers
[iter-2: agents]
  c7  feat(target-repo): SelfBootstrap + InRepoExample + registry
  c8  feat(architect): agent + prompt + tests
  c9  feat(backend): agent + prompt + tests
  c10 feat(qa): agent + prompt + tests
  c11 feat(demo): demo_iter_2.sh + make demo-iter-2
[iter-2: close]
  c12 docs(iter-2): retro + iter-2b handoff stub
```

Each merges only after CI green; agent task-report layer (owner
approval) applies only to c11's `pending_review` row, not to the dev
PRs themselves.

## What I will *not* do without asking

- Add any new framework dependency (LangGraph, CrewAI, OpenAI SDK,
  AgentSDK with API key) — ADR-001 / ADR-008 forbid.
- Lower diff-cover gate below 80 %.
- Force-push, drop DB, or skip hooks (`--no-verify`).
- Open a PR against `main` without `develop` decision (Open Question 1).
- Touch `infra/` or `.github/workflows/` from a code-writing agent
  (ADR-004 path scope).
- Use Agent SDK with `ANTHROPIC_API_KEY` — ever.
- Persist anything to the audit chain bypassing
  `core/audit/writer.py:append_event`.

## Current task

Phase 1 step **1A** — re-measure cache savings under `--session-id`. If
the floor holds (≥ 30 % input-token reduction on a repeated context),
proceed to 1C → 1D → 1B → Phase 2. Otherwise halt and revisit
ADR-001 / ADR-008 before any agent code.
