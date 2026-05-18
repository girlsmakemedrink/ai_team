# ADR-0004 — Tool inventory & capabilities (per-agent allowlist)

- **Status**: Accepted
- **Date**: 2026-05-18

## Context

Agents reason in an LLM and act through tools. Tool capabilities determine
*everything an agent is allowed to do in the world*: read code, write code,
run shell commands, fetch URLs, post messages, mark tasks done, request
human review.

Two failure modes we must engineer against:

1. **Prompt injection** — untrusted content (user message, web page, repo
   file) tricks an agent into calling a tool it shouldn't (e.g. exfiltrate
   secrets via `curl`).
2. **Role drift** — a Backend agent decides to "help" by ad-hoc deploying
   to production.

Mitigations are layered: input sanitization ([ADR-005]), least-privilege
tool allowlists (this ADR), and human approval gates on destructive
actions ([ADR-007]).

## Decision

### Principle: least privilege, statically declared

Each agent declares its allowed tool set in `agents/<role>/agent.py` as a
constant; the orchestrator passes this list to `claude -p --allowed-tools`
on every invocation. Tools not on the allowlist are unavailable to the
agent even if it asks for them.

### Tool taxonomy

1. **Native Claude Code tools** (provided by `claude`): `Read`, `Write`,
   `Edit`, `MultiEdit`, `Bash`, `Glob`, `Grep`, `WebFetch`.
2. **MCP tools, app-specific** (provided by our MCP servers — see
   `tools/mcp_servers/`):
   - `mcp__ai_team_bus__publish_message`
   - `mcp__ai_team_bus__read_team_feed`
   - `mcp__ai_team_bus__read_audit_log_summary`
   - `mcp__ai_team_tasks__mark_task_done`
   - `mcp__ai_team_tasks__request_human_review`
   - `mcp__ai_team_tasks__update_task_status`
3. **Future MCP tools** (Iteration 2+): `mcp__ai_team_repo__create_pr`,
   `mcp__ai_team_repo__run_tests`, `mcp__ai_team_repo__run_linter`, etc.
   These wrap underlying operations with structured arguments and validation.

### Per-agent matrix (MVP, Iteration 0–2b)

| Tool / Agent             | TL   | PM   | Arch | Des  | BE   | FE   | DevOps | QA   | SRE  | Mkt  |
|--------------------------|------|------|------|------|------|------|--------|------|------|------|
| `Read` (repo files)      | ✅   | ✅   | ✅   | ✅   | ✅   | ✅   | ✅     | ✅   | ✅   | ✅   |
| `Glob`, `Grep`           | ✅   | ✅   | ✅   | ✅   | ✅   | ✅   | ✅     | ✅   | ✅   | ✅   |
| `Write`, `Edit`          | ❌   | ✅\* | ✅\* | ✅\* | ✅   | ✅   | ✅\*\* | ✅\* | ✅\* | ✅\* |
| `Bash`                   | ❌   | ❌   | ❌   | ❌   | ✅\* | ✅\* | ✅\*\* | ✅\* | ✅\* | ❌   |
| `WebFetch`               | ❌   | ✅   | ✅   | ✅   | ❌   | ❌   | ❌     | ❌   | ✅   | ✅   |
| `publish_message`        | ✅   | ✅   | ✅   | ✅   | ✅   | ✅   | ✅     | ✅   | ✅   | ✅   |
| `read_team_feed`         | ✅   | ✅   | ✅   | ✅   | ✅   | ✅   | ✅     | ✅   | ✅   | ✅   |
| `mark_task_done`         | ✅   | ✅   | ✅   | ✅   | ✅   | ✅   | ✅     | ✅   | ✅   | ✅   |
| `request_human_review`   | ✅   | ✅   | ✅   | ✅   | ✅   | ✅   | ✅     | ✅   | ✅   | ✅   |

\* — write/edit limited to specific directory scopes (see "Path
constraints" below).
\*\* — DevOps `Bash` further restricted to a Docker/CI command allowlist;
deploying to `prod` requires `requires_human_approval=true`.

### Path constraints

Beyond tool allowlists, each agent has **path-scope constraints** enforced
at the MCP tool level (we extend `Write`/`Edit`/`Bash` with a wrapper that
validates target paths against allowed prefixes):

- **Architect**: writes only to `docs/adr/`, `docs/architecture.md`.
- **PM**: writes only to `docs/backlog/`, `docs/iterations/*.md`.
- **Designer**: writes only to `docs/design/`, `prompts/designer.md`.
- **Backend**: writes within the current `TARGET_REPO` working tree
  (excluding `infra/`, `.github/workflows/`).
- **Frontend**: writes within `apps/web/`, `apps/cli/` for ai_team's own
  CLI, or the `TARGET_REPO`'s frontend tree.
- **DevOps**: writes only to `infra/`, `.github/workflows/`, `Makefile`,
  `docker-compose.yml`.
- **QA**: writes only to `tests/`.
- **SRE/Support**: writes only to `docs/runbooks/`, `infra/monitoring/`.
- **Market Researcher**: writes only to `docs/sandbox/ideas/`,
  `docs/market/`.

### `Bash` allowlist (when granted)

`Bash` is **never** raw. We expose `Bash` only with a sub-allowlist of
permitted command prefixes per agent:

- Backend: `pytest`, `uv run`, `git status`, `git diff`, `git add`,
  `git commit`, `git push origin agent/*`, `make test`, `ruff`, `mypy`.
- DevOps: above + `docker compose`, `gh pr create`, `gh api`
  (read-only verbs), `alembic`.
- QA: `pytest`, `make test*`, `playwright`.
- SRE: `curl` (read-only against owner-approved internal URLs),
  `promtool`, `journalctl` (when on Iteration 5 server).

Anything not on the prefix list → tool refuses with structured error.

### What is **forbidden for everyone**

- `git push origin main` (or any branch matching `main|master|release/*`).
- `gh pr merge`, `gh release`.
- `curl http*` against external secrets stores.
- `rm -rf` against anything outside `.cache/`, `node_modules/`.
- Direct `docker compose down --volumes`, `docker volume rm`.

These are enforced at the `Bash` allowlist layer and additionally checked
in the `mcp__ai_team_bus__publish_message` validator for any payload that
attempts to mark such an action complete without
`requires_human_approval=true`.

## Consequences

### Positive

- A new agent has *no* tools by default. The author of the agent class
  explicitly opts each tool in, prompting deliberate review.
- Path scopes catch the "BE agent accidentally edits CI workflow" class
  of error.
- The matrix is one table — easy to review, easy to amend, single source
  of truth for security review.

### Negative

- Path-scope enforcement requires our wrapper MCP tools to be implemented
  (Iteration 2). Until then, we lean on `--allowed-tools` only; agents can
  still write anywhere within their tool's reach.
- Adding a new agent or new tool means updating the matrix, the wrapper
  validators, and tests. We accept this friction as a feature.

## Alternatives considered

- **Trust the agent's prompt.** Rejected — prompt injection trivially
  defeats this.
- **One allowlist for all agents.** Rejected — gives an oversight tool to
  agents that don't need it.
- **Runtime confirmation popup for every tool call.** Rejected — would
  flood the owner with low-signal confirmations and break the
  "owner-in-the-loop only at checkpoints" model.

## References

- [ADR-005 — Auth & secrets][ADR-005] (sanitizer, HMAC)
- [ADR-007 — Visibility & checkpoints][ADR-007] (human approval gates)
- [ADR-008 — LLM access strategy][ADR-008] (`--allowed-tools` is enforced
  by `claude -p`)
- Anthropic Claude Code docs — Allowed Tools.

[ADR-005]: 0005-auth-secrets.md
[ADR-007]: 0007-visibility-checkpoints.md
[ADR-008]: 0008-llm-access-strategy.md
