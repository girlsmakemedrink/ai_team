# Iteration 2 handoff — bringing Architect + Backend + QA online

> Brief for a fresh Claude session starting Iteration 2. Read this **after**
> CLAUDE.md. Together they're ≈ 15 KB and replace re-reading the
> conversation history.

## Where we are (2026-05-18 EOD)

`main` is at commit `aea9ff7`. Three merged PRs:

| PR | Title | What it brought |
|----|-------|-----------------|
| #1 | iter-0: foundation + 9 ADRs + core skeleton + tests | Repo scaffolding, ADRs 001..009, core/ modules, infra/, CLI/API stubs, 85 unit tests, CI |
| #2 | iter-1: TL + PM live, audit chain, dispatcher | First two live agents, dispatcher loop, HMAC+prev_hash audit, feed_events persistence, live API endpoints, testcontainers integration suite |
| #3 | fix(iter-1): claude -p structured_output + --session-id | Two real-LLM bugs that ScriptedLLM hid — both now fixed and tested |

End-to-end demo with real `claude -p` works: owner submits a task →
TL (Opus) decomposes → PM (Sonnet) emits 7 testable user stories →
markdown lands at `docs/backlog/<correlation>.md`. ~25 s wall time,
~4 cents for the Opus decomposition.

114 unit tests + 9 integration tests pass. Diff-cover gate at 80 %.
ruff / mypy strict / bandit high-only — all clean.

**Last smoke**: iter-0 `make smoke-llm` against real `claude -p` (2026-05-18,
before iter-1) — 5/5 pass, report at `docs/iterations/iter_0_smoke_report.md`.
Cache-hit ratio of ~100 % measured under `--resume`. **NOT re-measured
under the new `--session-id` semantics** — that's the Day-1 iter-2 task
(see scope below). The `make demo` end-to-end run that closed iter-1
produced 7 stories successfully but didn't formally measure cache hits.

## What's NOT in `main` yet (and why)

| Item | Why deferred | Iteration |
|------|--------------|-----------|
| Architect agent (ADRs, design review) | needs Opus prompt + file-write scope to docs/adr/ | **iter-2** |
| Backend Developer agent | needs MCP tool wrappers (`run_tests`, `git_*`, `gh pr create`) | **iter-2** |
| QA Engineer agent | needs MCP `run_tests` + pytest result parser | **iter-2** |
| TL checkpoint digests | timer + post-task hook not wired (manual via `ai-team digest`) | iter-2 (lightweight) |
| Architect / SRE / Frontend / Designer / Market Researcher | post-iter-2 | iter-2b |
| `audit_writer` Postgres role enforcement | role exists in migration; not yet bound to a separate engine | iter-3 (security harden) |
| Hash-chained audit alerts | `prev_hash` + verifier exist; no scheduled job | iter-3 |
| `Bash` allowlist wrapper as MCP tool | currently `--allowed-tools=Bash` is open | **iter-2 (BEFORE Backend lands)** — Backend is the first agent with code-write and `gh pr create` capability; allowlist must close before any task is dispatched to it |
| Real-LLM CI workflow | `real-llm.yml` exists, no self-hosted runner yet | iter-5 |

## Gotchas you MUST know before touching code

These all bit us in iter-1. CLAUDE.md repeats the first two — they are
that important:

1. **`claude -p --json-schema` puts the validated JSON in
   `structured_output`**, not in `result`. If you write a new code path
   that reads from a `claude -p` JSON response, read `structured_output`
   first.
2. **`--session-id` not `--resume`**. We pass our `correlation_id` as
   the session id for prompt caching. `--resume` errors on unknown IDs;
   `--session-id` is create-or-reuse and that's what we want.
3. **ScriptedLLM in integration tests bypasses `claude -p`** entirely —
   both bugs above passed the scripted suite. Every iteration must
   re-run `make smoke-llm` and `make demo` against real `claude -p`
   before claiming done.
4. **`get_settings()` is `lru_cache`d**; clear it (`get_settings.cache_clear()`)
   before re-reading env vars in tests / fixtures.
5. **Lifespan vs ASGITransport**. Default `httpx.ASGITransport(app=app)`
   does NOT run FastAPI's lifespan. For tests that need `app.state.*`
   populated, either use `fastapi.testclient.TestClient` (sync, runs
   lifespan) or populate `app.state.*` manually (see
   `tests/integration/test_apps_api_live.py:api_client` fixture).
6. **`AI_TEAM_DISPATCHER_AUTOSTART=false`** is set by `tests/conftest.py`
   so unit tests don't try to connect to Redis. Integration fixtures
   leave the dispatcher off too and start it explicitly when needed.
7. **Test ordering matters for audit_log**. `test_audit_writer` has an
   autouse fixture that DELETES from `audit_log` before each test;
   other integration tests filter by `correlation_id` to isolate.
8. **CI ruff format check is strict** — always run `make format` (or
   `uv run ruff format .`) locally before `git push`. Two iter-1 PRs
   wasted a CI cycle on format-only fails. Adding a pre-push hook is
   item D in Day-1 scope below.
9. **Pre-push hook is NOT installed** as of this handoff. Until item D
   lands, manually run `make format && make lint && make test` before
   every `git push`. Future-proofing: a `.git/hooks/pre-push` shell
   script + a `make install-hooks` target in iter-2 Day-1.

## Open questions / decisions to revisit

- **Path-scope enforcement for agent writes** — currently agent code
  decides where to write (PM writes to `docs/backlog/`). The MCP tool
  wrapper from ADR-004 is the proper enforcement layer; lands when
  Backend goes live (item 4 in scope).
- **Single-process API + dispatcher** — works for one owner; ADR-001
  says we split in iter-5 when we self-host. Don't split early.
- **`audit_writer` Postgres role enforcement** — role exists in
  migration but writes still go via the main app role. Threat model
  for now (single owner, localhost) is OK with this; lands properly
  in iter-3 security harden.

## Suggested iter-2 scope

### Day 1 (before any agent code)

- [ ] **A. Re-measure cache-hit ratio under `--session-id` semantics**.
      Iter-0 measured ~100 % under `--resume`; we changed to
      `--session-id` after a bug fix and have NOT re-measured. With
      ~$100/mo quota this is foundational — if cache collapsed, every
      decision built on cheap-prompt-caching is at risk. Extend
      `scripts/smoke_claude_p.py` with the same check under the new
      semantics, record result in
      `docs/iterations/iter_2_cache_report.md`.
      Hard requirement: ≥ 30 % cache hit on a repeated context (same
      threshold ADR-008 uses) — if we miss, revisit ADR-001/008 BEFORE
      writing any Architect/Backend code.
- [ ] **B. Bash allowlist wrapper closes**. Implement
      `mcp__ai_team_repo__run_shell(command_class, args)` with a fixed
      enum of `command_class` ∈ {`pytest`, `ruff`, `mypy`, `git_status`,
      `git_diff`, `git_add`, `git_commit`, `git_push_feature`,
      `gh_pr_create`, `make_test`}. Raw `Bash` is removed from
      Backend's `allowed_tools`. Path-scope (per ADR-004) lives here.
- [ ] **C. Add `LLMResponse.validated_against_schema: bool`**. True
      when `claude -p` returned a populated `structured_output`. False
      when we fell back to text-parsing or there was no schema. Surface
      in `_log.info("llm.invoke.ok", ...)` so the feed shows schema
      conformance per turn.
- [ ] **D. Install pre-push git hook**.
      `.githooks/pre-push` runs `make format && make lint && make test`.
      `make install-hooks` symlinks it into `.git/hooks/`. README +
      `make dev` document it.

### Day 2+ (agents)

1. **Architect agent** (Opus) — receives `task_assignment`, emits ADR
   markdown to `docs/adr/<NNNN>-...md` via path-scoped Write through
   MCP. Uses `--json-schema` for the (decision, alternatives,
   consequences) structure.
2. **Backend Developer agent** (Sonnet) — receives task_assignment,
   writes code + tests in a feature branch on `TARGET_REPO`, opens
   PR via the path-scoped `gh_pr_create` MCP tool (item B). Returns
   task_report with PR URL + diff stats.
3. **QA Engineer agent** (Sonnet) — receives a PR / artifact, runs
   pytest through the path-scoped `run_shell` MCP tool, returns
   task_report with pass/fail + coverage delta.
4. **`TargetRepo` concrete impls**: `SelfBootstrapTargetRepo`,
   `InRepoExampleTargetRepo` (for `examples/sandbox/idea-validator`).
   `GitHubTargetRepo` deferred to first real commercial product.
5. **End-to-end demo**: owner submits "implement idea-validator from
   spec" → TL → Architect (ADR) → Backend (code + tests) → QA →
   `pending_review` → owner approves → PR opens. Run with real
   `claude -p` before declaring iter-2 done.
6. **Real-LLM smoke as a pre-merge step** (not just nightly) — at
   minimum, run the full TL → PM → end-to-end cycle on any PR that
   touches `core/llm/`, `core/dispatcher.py`, or any `agents/*/`.

The exact decomposition is the responsibility of the new Claude — write
`docs/iterations/iter_2.md` first, surface it for review, then code.

## Pending items at handoff time

Nothing in `pending_reviews` (no live agents currently running). Nothing
in `pending_reviews` table either — DB is clean since infra is down
between sessions.

`docs/backlog/*.md` contains real PM output from the live demo.
`.gitignore`d (correctly) but kept on disk if you want to inspect.

## Ready-to-paste prompt for the new session

Copy this verbatim into the first message of a new Claude Code session
in `/Users/kirillterskih/ai_team/`:

---

```
Starting Iteration 2 on the ai_team project.

First, read these in this order — they replace re-reading the prior
conversation:

1. `CLAUDE.md` (project handbook, conventions, gotchas)
2. `docs/iterations/iter_2_handoff.md` (where we left off + open items)
3. `docs/iterations/iter_1_retro.md` (what we learned in iter-1)
4. `docs/adr/0001-orchestrator-choice.md`, `0008-llm-access-strategy.md`,
   `0009-target-repo-abstraction.md` (the three you must NOT contradict)

Iteration 2 goal: bring Architect (Opus, ADRs), Backend Developer
(Sonnet, code + tests), and QA Engineer (Sonnet, run-and-report)
agents online. Wire up the first MCP tool servers
(`mcp-ai-team-repo`: create_branch, write_file_in_scope, run_tests,
open_pr) with path-scope enforcement from ADR-004. Implement
`TargetRepo` concrete impls so agents can work against an arbitrary
repo. End-to-end demo: owner submits "implement idea-validator from
spec" → TL → Architect → Backend → QA → pending_review → owner
approves.

Workflow: plan-before-code. Draft `docs/iterations/iter_2.md` first,
surface for review, then code. Run `make smoke-llm` + `make demo`
against real `claude -p` before declaring done — iter-1 had two
real-LLM bugs that the ScriptedLLM tests hid. Run validation checks +
PR merges yourself (autonomy preference is in memory).

Constraints:
- LLM substrate is `claude -p` via subscription. Never set
  ANTHROPIC_API_KEY. Never use Agent SDK with API key.
- `--json-schema` validated output lives in `structured_output`, not
  `result`. `--session-id` for create-or-reuse, never `--resume` with
  our correlation_ids.
- Boring stack only. Re-read ADR-001 before considering any new
  framework.
- Diff-cover gate is 80 %. Bandit gates only on high.
- Conventional commits, squash-merge, plan-before-code, owner approval
  required on every task agents consider done.

When ready, create the iter-2 task list and surface the plan.
```

---

Save your quota: this prompt is ~500 tokens. CLAUDE.md is ~3 KB and
this file is ~3 KB, both read once. The whole onboarding round trip
should be under 10 K tokens of input.
