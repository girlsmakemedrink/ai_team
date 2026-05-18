# Iteration 2b — Plan

- **Status**: Approved 2026-05-18 (owner accepted the four recommendations below)
- **Plan author**: Claude (Opus 4.7)
- **Date drafted**: 2026-05-18
- **Base commit**: `d8bc3e8` on `main` (iter-2 squash)
- **Branch**: `worktree-iter-2b`
- **Anchors (do not contradict)**: ADR-001, ADR-004, ADR-006, ADR-008, ADR-009;
  iter-2 retro action items

## Goal — one sentence

Close iter-2's open items (forbidden-PR-base env-driven, per-role MCP
path-scope at spawn time, `TargetRepo` active methods, ADR-008
validation refresh), execute the real-LLM end-to-end demo and capture
the report, then bring **Designer + DevOps + Market Researcher** online
(Frontend + SRE deferred to iter-2c).

## Success criteria (binary, measurable)

1. **Real-LLM e2e demo report** at
   `docs/iterations/iter_2_demo_report.md` — owner submits "implement
   idea-validator from spec", chain runs TL → Architect → Backend →
   QA → `pending_review`, owner approves, PR lands. Real cost +
   wallclock recorded.
2. **`AI_TEAM_FORBID_BRANCH_RE`** drives the `gh_pr_create` base
   validator (currently the regex is hard-coded in
   `commands.py:_validate_gh_pr_create`). Per-target-repo override
   works without code change.
3. **Per-role MCP path-scope at spawn time.** `LLMClient.invoke`
   accepts `env: Mapping[str,str] | None`; agents set `mcp_env:
   ClassVar[Mapping[str,str]]`. Architect's MCP server spawns with
   `AI_TEAM_PATH_PREFIXES="docs/adr,docs/architecture.md"`, Backend
   with the target-repo working tree minus `infra/`+`.github/workflows/`,
   QA with `tests/`. ADR-004's least-privilege matrix becomes
   enforceable.
4. **`TargetRepo` active methods** filled in with subprocess impls
   (`checkout`, `stage_and_commit`, `push`, `open_pr`, `run_tests`,
   `run_linter`, `status`). Tested against a real tmp git repo in
   `tests/integration/test_target_repo.py`. The existing security
   guards stay where they are.
5. **ADR-008 validation table amended** to match observed reality
   (median ≤ 10s, max ≤ 25s for cold haiku — what `make smoke-llm`
   actually asserts post-iter-2).
6. **Designer agent** (Sonnet) — receives task_assignment, writes
   design notes / wireframe markdown to `docs/design/` via path-scoped
   MCP write, reports back to TL.
7. **DevOps agent** (Sonnet) — receives task_assignment, modifies
   `infra/`, `.github/workflows/`, `Makefile`, `docker-compose.yml`
   only. Bash allowlist tighter than Backend (no `git_push_feature` to
   non-`agent/devops/*` branches, no `make_test` arbitrary targets).
8. **Market Researcher agent** (Sonnet) — receives task_assignment,
   uses `WebFetch` + LLM reasoning, writes a market scan to
   `docs/sandbox/ideas/` or `docs/market/`, reports back.
9. `make test-unit` green; `make test-integration` green;
   `make lint`, `make typecheck`, `make sec` clean; diff-cover ≥ 80 %;
   `make smoke-llm` green.
10. `docs/iterations/iter_2b_retro.md` + `iter_2c_handoff.md` stub.

## Non-goals (explicitly deferred)

- **Frontend Developer agent** — heaviest single agent (web UI
  generation, separate testing patterns). Iter-2c.
- **SRE/Support agent** — runbooks + monitoring; not blocking until
  iter-5 server move. Iter-2c or later.
- **`GitHubTargetRepo` impl** — still waiting on first commercial
  product.
- **`audit_writer` Postgres role enforcement** — iter-3.
- **Hash-chain alert job** — iter-3.
- **Splitting API + dispatcher processes** — iter-5.

## Plan — two phases

### Phase 1 — close iter-2 open items (in this order)

| # | Task | Output | Cost |
|---|------|--------|------|
| 1A | Env-driven forbidden-PR-base | `commands.py` reads regex from `AI_TEAM_FORBID_BRANCH_RE`; unit test pins per-target override | $0 |
| 1B | Per-role MCP env at spawn time | `env:` kwarg on `LLMClient.invoke`, `mcp_env` on each agent, unit tests for the merge | $0 |
| 1C | ADR-008 latency table refresh | Doc-only edit; smoke script values become the official numbers | $0 |
| 1D | Real-LLM e2e demo run | `iter_2_demo_report.md` captures cost, wallclock, failure modes | ~$0.40 |
| 1E | `TargetRepo` active methods | Subprocess impls + integration tests against tmp git repo | $0 |

Why this order:
- 1A and 1B unblock the demo (`gh_pr_create` + per-role scope).
- 1C is doc-only and free.
- 1D is the budget hit; do it once Phase 1 plumbing is right.
- 1E lands last in Phase 1 because no Python call-site reaches the
  methods yet — adding them while everything else changes is friction.

### Phase 2 — three new agents (parallelisable after Phase 1)

| # | Task | Owner approval |
|---|------|----------------|
| 2A | Designer agent + prompt + tests | unit + cassette |
| 2B | DevOps agent + prompt + tests | unit + cassette |
| 2C | Market Researcher agent + prompt + tests | unit + cassette |
| 2D | Iter-2b end-to-end demo run (TL → DevOps for CI change, say) | owner runs `ai-team approve` |
| 2E | Retro + iter-2c handoff stub | n/a |

The three agents follow the same `BaseAgent` shape Architect/Backend/QA
used in iter-2 — should be ~250-350 LOC each including tests, ~1 day
of work per agent.

## Detailed design notes

### 1A — env-driven forbidden-PR-base

Currently `tools/mcp_servers/ai_team_repo/commands.py` has:

```python
_FORBIDDEN_PR_BASE_RE = re.compile(r"^(main|master|release/.*)$")

def _validate_gh_pr_create(args):
    ...
    if _FORBIDDEN_PR_BASE_RE.match(base):
        raise CommandRejected(...)
```

Move the regex into `commands.py` module-init time read from env
(`AI_TEAM_FORBID_PR_BASE_RE`, defaulting to current regex), OR pass
the context through the validator. The latter requires plumbing
`Context` into `resolve_command`. Cleanest: a module-level
`set_forbidden_base_re(pattern: str)` setter called from
`handlers.py:Context.from_env` so the registry stays singleton-style.

Test: `commands.py` accepts the override; per-target overrides work.

### 1B — per-role MCP env at spawn time

`LLMClient.invoke` adds `env: Mapping[str, str] | None = None`.
`ClaudeCodeHeadlessClient` merges that on top of `os.environ` when
spawning the subprocess (`asyncio.create_subprocess_exec(... , env=...)`).
`BaseAgent` gets `mcp_env: ClassVar[Mapping[str, str]] = {}`.
`BaseAgent._invoke_with_retries` (and each agent's overridden `handle`)
passes `env=self.mcp_env`.

Per-role values:

| Agent | `AI_TEAM_PATH_PREFIXES` |
|-------|-------------------------|
| Architect | `docs/adr,docs/architecture.md` |
| Backend | `*` minus `infra/` + `.github/workflows/` (handled by an explicit denylist in scope.py; iter-2b shipping) |
| QA | `tests/` |
| Designer | `docs/design/,prompts/designer.md` |
| DevOps | `infra/,.github/workflows/,Makefile,docker-compose.yml,scripts/` |
| Market Researcher | `docs/sandbox/ideas/,docs/market/` |

`scope.py` gets an optional denylist (`AI_TEAM_PATH_DENY_PREFIXES`) so
Backend can be `*`-allowed minus the two protected directories.

Tests: each agent's `mcp_env` round-trips through invoke; subprocess
env is merged correctly; denylist works.

### 1C — ADR-008 validation table

Replace:

| Property | Threshold |
|----------|-----------|
| Cold-start latency p50 / p99 | < 3 s / < 6 s |

With:

| Property | Threshold |
|----------|-----------|
| Cold-start latency median (5 samples) | ≤ 10 s |
| Cold-start latency max (5 samples) | ≤ 25 s |

Same place that currently lives in `docs/adr/0008-llm-access-strategy.md`.
Doc-only.

### 1D — real-LLM e2e demo

Run `AI_TEAM_DEMO_NON_INTERACTIVE=1 make demo-iter-2` after Phase 1
1A+1B land. Capture:

- Total wallclock per agent (TL Opus, Architect Opus, Backend Sonnet,
  QA Sonnet).
- Cost per agent + total.
- Schema-validation rate (`validated_against_schema=True` ratio).
- Failure modes (if any) — write them up in the report.
- The PR URL and a hand-eyeball check of the produced
  `examples/sandbox/idea-validator/` code.

If Backend produces ≥ 200 LOC of working Python with ≥ 80% test
coverage that QA confirms passes → demo is "fully successful" and
iter-2b's reason-to-exist is mostly closed.

Owner approves the resulting PR via `ai-team approve <id>`. The PR can
then be self-merged via the standard squash flow.

### 1E — `TargetRepo` active methods

Fill in `core/target_repo/self_bootstrap.py` methods, behind the
existing security guards. Use `asyncio.create_subprocess_exec` for
all git ops. Integration tests in `tests/integration/test_target_repo.py`
spin up a tmp git repo + tmp remote (also git init) and exercise:

- `checkout(branch, base=main)` from a clean repo
- `stage_and_commit(paths, message, author)` with a real diff
- `push(branch)` to the tmp remote (refused for `main`)
- `run_tests` runs `pytest -q` and parses output
- `status` returns expected fields

Marked `@pytest.mark.integration` so they don't slow the pre-push hook.

### 2A–2C — three new agents

All three are direct copies of the Architect / Backend / QA pattern:

- ClassVar `role`, `model_tier="sonnet"`, `allowed_tools` (no raw
  Bash/Write/Edit; MCP only), `system_prompt_path`.
- `handle()` invokes LLM with the role-specific JSON schema and
  `mcp_env`, build_outputs unpacks the response.
- Prompt explicitly enumerates the sections of the output and asks
  for citations to ADRs / specs by file path.

**Designer**: outputs design notes / wireframes in markdown +
optionally ASCII layouts. Path scope `docs/design/`. Schema includes
{summary, layout, decisions, links}.

**DevOps**: outputs CI/infra patches. Path scope
`infra/,.github/workflows/,Makefile,docker-compose.yml`.
Schema includes {target_files, changes, rationale, validation_step}.
Bash via `run_shell(command_class="make_test")` only.

**Market Researcher**: outputs a market scan. Path scope
`docs/sandbox/ideas/,docs/market/`. WebFetch on the allowlist (this is
the only agent that uses it). Schema includes {competitors,
market_size, top_risks, top_opportunities, viability_score}.

### Cost / quota envelope

- Phase 1 1A+1B+1C+1E: $0 (code + tests, mocked LLM).
- Phase 1 1D (real-LLM demo): ~$0.40.
- Phase 2 2A+2B+2C: $0 for the code, ~$0.05-$0.10 each for cassette
  recording when adding the first integration test.
- Phase 2 2D (iter-2b end-to-end demo): ~$0.30.
- Total budgeted for iter-2b: **≤ $1.00**.

## Risks & mitigations

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| Real-LLM demo fails on Backend's code quality (LLM can't produce 300 LOC of working idea-validator) | medium | Spec is small + well-defined; if it fails, capture the actual output in the demo report — that's also a valuable signal |
| Per-role env plumbing has a bypass | low | Unit tests pin per-agent env round-trip; the subprocess env layer is small + auditable |
| `TargetRepo` integration tests are flaky on different OSes | low | Use `pytest-asyncio` + git timeouts; mark as integration, run in CI only |
| iter-2b agents drift from the established pattern | low | Architect/Backend/QA in iter-2 set strong precedent; reviewers will catch divergence |

## Resolved decisions (owner-approved 2026-05-18)

1. **Backend path-scope = `*` allow + explicit denylist.** `scope.py`
   grows `AI_TEAM_PATH_DENY_PREFIXES` (csv). Backend's env sets
   `AI_TEAM_PATH_PREFIXES="*"` and
   `AI_TEAM_PATH_DENY_PREFIXES="infra/,.github/workflows/"`.
2. **Demo report scope = metrics + outcome + PR link.** No pasted
   copies of ADRs or diffs; links to live files only.
3. **Cassettes are over-engineering for current scale.** Stay with
   `_StubLLM` unit tests; add one real-LLM smoke per agent under
   `tests/real_llm/` (gated `@pytest.mark.real_llm --real-llm`).
4. **Frontend + SRE deferred to iter-2c.** Iter-2b ships three new
   agents (Designer, DevOps, Market Researcher).

## Sequencing (one commit = one squash-merge PR)

```
[iter-2b: Phase 1]
  c1  docs(iter-2b): plan
  c2  fix(mcp): env-driven forbidden-PR-base
  c3  feat(llm): env kwarg on LLMClient.invoke + per-agent mcp_env
  c4  docs(adr-008): refresh latency table
  c5  feat(target-repo): subprocess impls + integration tests
  c6  docs(iter-2): real-LLM e2e demo report  ← may slip if demo fails

[iter-2b: Phase 2]
  c7  feat(designer): agent + prompt + tests
  c8  feat(devops): agent + prompt + tests
  c9  feat(market-researcher): agent + prompt + tests
  c10 feat(demo): iter-2b end-to-end demo

[iter-2b: close]
  c11 docs(iter-2b): retro + iter-2c handoff
```

## What I will NOT do without asking

- Add any new framework dependency (LangGraph, CrewAI, OpenAI SDK,
  AgentSDK with API key) — ADR-001 / ADR-008 forbid.
- Lower diff-cover gate below 80 %.
- Force-push, drop DB, or skip hooks.
- Touch `apps/web/` (Frontend agent territory — deferred to iter-2c).
- Persist anything to the audit chain bypassing
  `core/audit/writer.py:append_event`.

## Current task

Phase 1 step **1A** — lift `_FORBIDDEN_PR_BASE_RE` out of
`commands.py` module constant and into an env-driven setting
(`AI_TEAM_FORBID_PR_BASE_RE`, defaulting to the current regex). Unit
test pins per-target override behaviour.
