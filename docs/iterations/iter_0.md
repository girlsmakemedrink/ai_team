# Iteration 0 — Foundation

- **Duration**: 2–3 days
- **Goal**: repository initialised, ADR-001..009 written and reviewed,
  baseline code skeleton (no live agents yet) starts cleanly via
  `make up`, CI is green on the empty code, the `claude -p` substrate
  is validated by a smoke experiment.

## Definition of Done (Iteration 0)

- [ ] `make dev && make up` brings the four infra containers (postgres,
      redis, prometheus, grafana) to healthy.
- [ ] `make test` is green; coverage ≥ 80 % on the foundation code.
- [ ] `make smoke-llm` produces a smoke report that meets the thresholds
      in [ADR-008](../adr/0008-llm-access-strategy.md) §Smoke validation.
- [ ] All nine ADRs (0001–0009) are in `docs/adr/` and merged.
- [ ] `make demo` walks the owner through: start infra → publish a test
      message via a script → see it appear in `ai-team watch` → see it
      persisted in `feed_events`.
- [ ] PR `feature/iter-0-foundation` is open, CI is green, branch
      protection on `main` is in effect.

## MVP scope — required to ship Iteration 0

### Repo bootstrap

- [x] `git clone girlsmakemedrink/ai_team`, `feature/iter-0-foundation`
      branch created.
- [x] `pyproject.toml` (uv-managed), `Makefile`, `.gitignore`,
      `.editorconfig`, `.env.example`, `.python-version`, `LICENSE`,
      `README.md`.
- [x] `.github/PULL_REQUEST_TEMPLATE.md`, `CODEOWNERS`.
- [ ] `.pre-commit-config.yaml` installed via `make dev`.
- [ ] Branch protection on `main` (squash-only, status checks
      required, no force-push, no deletions, linear history;
      reviewer-count requirement off — solo dev).

### Architecture Decision Records

- [x] ADR-001 Orchestrator choice (custom outer + `claude -p` inner).
- [x] ADR-002 Message schema & protocol.
- [x] ADR-003 Audit log strategy.
- [x] ADR-004 Tool inventory & per-agent allowlist.
- [x] ADR-005 Auth & secrets.
- [x] ADR-006 Cost & context optimisation.
- [x] ADR-007 Visibility & checkpoint strategy.
- [x] ADR-008 LLM access strategy (`LLMClient` adapter).
- [x] ADR-009 `TARGET_REPO` abstraction.

### Infrastructure

- [ ] `infra/docker-compose.yml`: postgres-15, redis-7, prometheus,
      grafana. Healthchecks. Named volumes.
- [ ] `infra/monitoring/prometheus.yml` scrape config for `apps.api`.
- [ ] `infra/monitoring/grafana/` provisioned datasource +
      placeholder dashboard.
- [ ] Alembic initialised; first migration creates `audit_log`,
      `feed_events`, `tasks`, `checkpoints`, `pending_reviews`,
      `audit_log_verifications` tables.
- [ ] Postgres role `audit_writer` with INSERT-only grant on
      `audit_log` (in the migration).

### Core skeleton (no live agents yet)

- [ ] `core/messaging/schemas.py` — `AgentMessage` + payload union.
- [ ] `core/messaging/bus.py` — Redis Streams producer/consumer.
- [ ] `core/messaging/feed.py` — Pub/Sub publisher + SSE endpoint
      wiring.
- [ ] `core/persistence/database.py`, `core/persistence/models.py` —
      SQLAlchemy 2.x async setup.
- [ ] `core/llm/base.py`, `core/llm/claude_code_headless.py`,
      `core/llm/mock.py`, `core/llm/agent_sdk_stub.py`.
- [ ] `core/security/sanitizer.py`, `core/security/hmac_signer.py`,
      `core/security/redaction.py`.
- [ ] `core/observability/logging.py` (structlog),
      `core/observability/metrics.py` (Prometheus).
- [ ] `core/target_repo/base.py` — `TargetRepo` ABC + three impls.
- [ ] `agents/_base/agent.py` — `BaseAgent` abstract class (no real
      agents yet).

### Apps

- [ ] `apps/api/main.py` — FastAPI app with `/health`,
      `/api/feed/stream` SSE, `/api/tasks`, `/api/reviews/:id/approve`.
- [ ] `apps/cli/main.py` — Click `ai-team` with: `up`, `watch`,
      `submit`, `status`, `digest`, `approve`, `list-pending`.
- [ ] `tools/mcp_servers/ai_team_bus/` — MCP server skeleton with
      `publish_message`, `read_team_feed`, `read_audit_log_summary`
      stubs.
- [ ] `tools/mcp_servers/ai_team_tasks/` — `mark_task_done`,
      `request_human_review`, `update_task_status` stubs.

### Validation

- [ ] `scripts/smoke_claude_p.py` — runs the five checks in
      ADR-008 §Smoke validation. Report at
      `docs/iterations/iter_0_smoke_report.md`.
- [ ] `tests/unit/` — coverage on `core/`, `agents/_base/`,
      `apps/cli`. Threshold ≥ 80 %.
- [ ] `tests/integration/test_bus_roundtrip.py` — publish a message,
      read it from a consumer group, verify HMAC, see feed event row,
      see audit row.
- [ ] `tests/contract/test_message_schema_snapshot.py` — JSON schema
      snapshot of `AgentMessage`.

### CI

- [ ] `.github/workflows/ci.yml` — ruff + mypy + pytest +
      `diff-cover` ≥ 80 % + commitlint. PR-gated.
- [ ] `.github/workflows/real-llm.yml` — nightly + manual trigger,
      runs e2e tests with real `claude -p`, hard timeout + quota
      pre-check (skip with warning if quota < 10 %).

### Demo

- [ ] `scripts/demo_iter_0.sh` — see Definition of Done above.
- [ ] `docs/iterations/iter_0_retro.md` — completed at end-of-iteration.

## Stretch — explicitly deferred (do **not** block Iteration 0)

- Hash-chain audit log (Phase 2 of ADR-003); we ship `prev_hash` only.
- OpenTelemetry traces.
- Helm chart / k8s manifests.
- Mutation testing (`mutmut`/`cosmic-ray`).
- Signed commits enforcement.
- Secret scanning (`gitleaks`) in CI.

## Out of scope for Iteration 0

- Any live agent (deferred to Iteration 1+).
- Real LLM calls outside the smoke test.
- Next.js frontend (Iteration 6).
- Server provisioning / production deployment (Iteration 5).

## Risks

| Risk                                                 | Mitigation                                            |
|------------------------------------------------------|-------------------------------------------------------|
| `claude -p` concurrency limits unknown               | Smoke experiment §1 explicitly tests this.            |
| `--allowed-tools` enforcement uncertain              | Smoke experiment §2 verifies.                         |
| Subscription quota measurement unreliable            | Estimate from `usage` field; calibrate weekly.        |
| Pre-commit hooks slow PRs                            | Use ruff (fast); keep mypy in CI only, not pre-commit.|
| `gh` API misses `workflow` scope for protection      | Confirmed scope added prior to Iteration 0 start.     |

## Iteration 1 preview (next)

- Team Lead + Product Manager agents live.
- Owner submits a real task via `ai-team submit`, sees decomposition
  in `ai-team watch`, gets a checkpoint digest, approves.
- Sandbox task: idea-validator CLI scaffolding (see
  [docs/sandbox/idea_validator_spec.md](../sandbox/idea_validator_spec.md)).
