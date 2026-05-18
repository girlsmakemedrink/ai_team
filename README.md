# ai_team

> Multi-agent AI development team that ships software.

`ai_team` is a framework where a small team of LLM-powered agents — Team Lead
plus eight specialists — collaborates on software projects: receiving tasks,
decomposing them, writing code, reviewing it, and shipping. The owner stays in
the loop through a live chat feed and explicit approval checkpoints before any
merge or deploy.

## Status

**Iteration 0 — Foundation.** Repo scaffolding, ADR-001..009, infrastructure
skeleton. No live agents yet. See [docs/iterations/iter_0.md](docs/iterations/iter_0.md)
for the current iteration scope and `docs/iterations/` for the full plan.

## The team

| Role                | Model    | Responsibility                                   |
|---------------------|----------|--------------------------------------------------|
| Team Lead           | Opus     | Owner's single contact; decomposes & delegates.  |
| Product Manager     | Sonnet   | User stories, backlog, prioritisation.           |
| Designer            | Sonnet   | Wireframes, design tokens, component libs.       |
| Architect           | Opus     | ADRs, system design, security review.            |
| Backend Developer   | Sonnet   | Server-side code with tests in same PR.          |
| Frontend Developer  | Sonnet   | UI code with component + screenshot tests.       |
| DevOps              | Sonnet   | CI/CD, Docker, infra-as-code.                    |
| QA Engineer         | Sonnet   | Smoke/regression suites; pre-merge gatekeeper.   |
| SRE / Support       | Sonnet   | Alerts, runbooks, P1 remediation.                |
| Market Researcher\* | Sonnet   | Trends, niches, idea generation (stub in MVP).   |

\* Added as the ninth agent; stub in MVP, expanded post-MVP.

## Quickstart

```bash
# Prereqs: Python 3.11+, Docker, uv, Claude Code CLI (subscription auth — no API key)

git clone https://github.com/girlsmakemedrink/ai_team.git
cd ai_team

make dev          # install deps, pre-commit, pre-push hook, .env scaffold
make up           # start postgres, redis, prometheus, grafana
make test         # unit + integration with mocked LLM
make smoke-llm    # validate `claude -p` substrate (ADR-008)
make demo         # Iteration 0 demo: publish test message, see it in CLI feed
```

The pre-push hook installed by `make dev` (or `make install-hooks` standalone) runs `make lint && ruff format --check && make test` before every `git push`, so CI doesn't waste a cycle on a format-only fail. Run `make fix` to auto-apply formatting if the hook trips.

## How it works (at a glance)

```
      ┌──────────┐  owner_token         ┌──────────┐
 You ─┤ ai-team  ├────────┬─────────────┤   API    │── SSE /api/feed/stream
      │   CLI    │        │             │ FastAPI  │── /api/tasks
      └──────────┘        │             └────┬─────┘── /api/reviews/:id/approve
                          │                  │
                          │                  ▼
                          │            ┌──────────┐
                          │            │ Team Lead│  Opus 4.7
                          │            └────┬─────┘
                          │                 │ dispatches
                          ▼                 ▼
                ┌───────────────────────────────────────┐
                │  Redis Streams bus  (durable, audited)│
                └────┬────────────────────────────┬─────┘
                     │                            │
            ┌────────▼────────┐         ┌─────────▼────────┐
            │ Specialist      │ ...x8   │ Specialist agent │
            │ agent           │         │                  │
            │ `claude -p`     │         │ `claude -p`      │
            └────────┬────────┘         └──────────────────┘
                     │
                     ▼
            ┌─────────────────┐
            │ team_feed       │── Pub/Sub broadcast
            │ Redis + Postgres│── persistent history
            └─────────────────┘
                     │
                     ▼
            ┌─────────────────┐
            │ audit_log       │── append-only, HMAC-signed
            │ Postgres        │── prev_hash chain
            └─────────────────┘
```

- LLM substrate: `claude -p` (Claude Code headless mode) — subscription-only,
  no API billing. See [ADR-008](docs/adr/0008-llm-access-strategy.md).
- Bus: Redis Streams (durable) + Pub/Sub (`team_feed` for live visibility).
- Persistence: Postgres for tasks, audit log, feed history, checkpoints,
  pending reviews. Alembic-managed schema.
- Every task an agent considers done routes through a `pending_review` queue;
  owner approval is required before merge or deploy.

## Architecture Decision Records

| #   | Decision                                                                       |
|-----|--------------------------------------------------------------------------------|
| [001](docs/adr/0001-orchestrator-choice.md) | Hybrid orchestrator: custom outer + `claude -p` inner       |
| [002](docs/adr/0002-message-schema.md)      | `AgentMessage` Pydantic schema & versioning                 |
| [003](docs/adr/0003-audit-log-strategy.md)  | Append-only Postgres audit log with `prev_hash`             |
| [004](docs/adr/0004-tool-inventory.md)      | Per-agent tool allowlist; least-privilege                   |
| [005](docs/adr/0005-auth-secrets.md)        | `OWNER_TOKEN` + HMAC now; mTLS + Vault later                |
| [006](docs/adr/0006-cost-context-optimization.md) | Tiered models, prompt caching, subscription quota gates |
| [007](docs/adr/0007-visibility-checkpoints.md) | `team_feed` (Redis + Postgres + SSE) + TL digests       |
| [008](docs/adr/0008-llm-access-strategy.md) | `LLMClient` adapter; `claude -p` primary, Agent SDK stub    |
| [009](docs/adr/0009-target-repo-abstraction.md) | `TARGET_REPO` parametrisation for multi-project reuse   |

## Repository layout

```
ai_team/
├── apps/
│   ├── api/             # FastAPI: owner-facing REST + SSE feed
│   └── cli/             # `ai-team` CLI (watch, submit, approve, digest)
├── agents/              # One package per agent + `_base/`
├── core/                # Shared platform
│   ├── messaging/       # Redis Streams bus, AgentMessage schemas
│   ├── persistence/     # SQLAlchemy models, Alembic
│   ├── llm/             # LLMClient adapter, claude-p backend
│   ├── security/        # Sanitizer, HMAC, redaction
│   ├── observability/   # structlog, prometheus
│   └── target_repo/     # TARGET_REPO abstraction
├── tools/mcp_servers/   # Custom MCP servers exposed to `claude -p`
├── prompts/             # System prompts per agent (markdown)
├── tests/               # unit / integration / e2e
├── infra/               # docker-compose, monitoring configs
├── docs/                # architecture, adr/, iterations/, runbooks/, sandbox/
├── scripts/             # smoke tests, demos, ops helpers
└── examples/sandbox/    # idea-validator: training task for Iteration 1–2
```

## License

MIT — see [LICENSE](LICENSE).
