# Iteration 1 — Team Lead + Product Manager, live

- **Duration**: 3–4 days
- **Goal**: First two agents work end-to-end against the foundation built in
  Iteration 0. The owner can submit a task, watch the team decompose and
  execute it, receive checkpoint digests, and approve before merge.
- **Concrete demo**: `ai-team submit "Generate user stories for idea-validator"`
  → Team Lead decomposes → assigns to Product Manager → PM emits a user-stories
  markdown document → TL emits a `checkpoint_digest` → owner reviews via
  `ai-team list-pending` → `ai-team approve <id>` → done.

## Definition of Done

- [ ] `make demo-iter-1` runs end-to-end on a fresh checkout: clone → `make dev`
      → `make up` → `make demo-iter-1` → demo task moves through TL → PM →
      pending_review → approved.
- [ ] `ai-team watch` shows live agent ↔ agent communication for the demo task,
      properly redacted, color-coded by role.
- [ ] At least one `checkpoint_digest` is produced by TL during the run and is
      visible to the owner via `ai-team digest` (which queries the
      `checkpoints` table) and in the live feed.
- [ ] Integration tests under `tests/integration/` cover the full
      "submit → TL → PM → pending_review → approve" cycle, mocked LLM.
- [ ] Diff-cover gate raised back to **80 %** in CI.
- [ ] All 4 carry-overs from iter_0_retro closed (see Scope).

## In-scope (MVP for Iteration 1)

### Carry-overs from Iteration 0

- [ ] **Persist `feed_events` to Postgres on every publish.** Add a sink layer
      so `FeedPublisher.publish()` mirrors to the `feed_events` table within
      the same call (best-effort persistence, never blocks Pub/Sub).
- [ ] **testcontainers fixtures.** `tests/integration/conftest.py` spins up
      Postgres 15 + Redis 7 once per session via testcontainers-python; tests
      mark themselves `@pytest.mark.integration`.
- [ ] **`--json-schema` support in `LLMClient.invoke()`.** Adds optional
      `json_schema: dict | None` parameter, threaded to `claude -p --json-schema`.
      MockLLMClient honours it by returning the canned response only if it
      matches the schema (otherwise raises in strict mode).
- [ ] **`max_budget_usd` support in `LLMClient.invoke()`.** Optional parameter,
      threaded to `claude -p --max-budget-usd`. Defaults from a per-tier table
      in `core/config.py`.

### Audit + dispatcher

- [ ] `core/audit/writer.py`: Async function that signs an `AgentMessage` with
      HMAC, computes `prev_hash` from the latest `audit_log` row, INSERTs
      using the `audit_writer` Postgres role. Idempotent on `message_id`.
- [ ] `core/dispatcher.py`: Async loop. For each agent: subscribe to its
      stream, on message → write audit row → call `agent.handle(msg)` → for
      each output AgentMessage: HMAC-sign → publish to bus → publish to feed
      (Pub/Sub + DB) → write audit row → ack source.
- [ ] DLQ handling: malformed messages routed to `bus:dlq` with reason +
      `agent_errors_total` counter increment.
- [ ] Graceful shutdown on SIGTERM/SIGINT.

### Agent base (concrete)

- [ ] `BaseAgent.handle()` provides default behaviour: load + cache system
      prompt, build user prompt by wrapping payload via `wrap_untrusted`, call
      `LLMClient.invoke` with this agent's tier / allowed tools / session ID
      keyed on `correlation_id`, parse structured response, emit outgoing
      messages. Subclasses override only when needed.
- [ ] Per-agent rate limit (`tenacity`-backed) and circuit breaker.

### Team Lead agent

- [ ] `agents/team_lead/agent.py`: subclass of BaseAgent.
- [ ] `prompts/team_lead.md`: role contract, MUST-NOT-CODE rule, decomposition
      JSON schema, checkpoint digest format.
- [ ] Decomposes an incoming `task_assignment` (from `sender=user`) into one
      or more sub-`task_assignment`s targeting other agents. Outputs
      structured JSON: `{"subtasks": [{"recipient": "...", "title": "...",
      "description": "...", "priority": "..."}]}`.
- [ ] Owner-token verification on `sender=user` messages (only TL receives
      user messages).
- [ ] Periodic checkpoint digest emission (background task on a timer +
      explicit trigger after each `task_report{status=done}`).
- [ ] Uses `model_tier="opus"` for decomposition (one of the few Opus-tier
      consumers — per ADR-006).

### Product Manager agent

- [ ] `agents/product_manager/agent.py`: subclass of BaseAgent.
- [ ] `prompts/product_manager.md`: role contract, user-stories markdown
      template, acceptance-criteria-style structure.
- [ ] Receives `task_assignment`, emits a `task_report{status=done}` with the
      generated user-stories text in `summary` (≤2000 chars) and a longer
      markdown artifact written to `docs/backlog/<correlation-id>.md`.
- [ ] Uses Sonnet (`model_tier="sonnet"`).

### `apps/api` live dispatch

- [ ] `POST /api/tasks` now: validates token, creates `tasks` row, signs and
      publishes an `AgentMessage{task_assignment}` to TL's stream. Returns
      `task_id` and `correlation_id`.
- [ ] `GET /api/reviews` reads from `pending_reviews` table.
- [ ] `POST /api/reviews/:id/approve` updates `pending_reviews`, emits a
      synthetic `task_report` from `user` back to the requesting agent.
- [ ] `GET /api/digest` returns the latest checkpoint markdown (CLI calls
      this for `ai-team digest`).

### `apps/cli`

- [ ] `ai-team digest` actually queries `/api/digest` and pretty-prints.
- [ ] `ai-team digest --history` lists last N checkpoints from
      `/api/digest/history`.
- [ ] `ai-team list-pending` actually reads `/api/reviews`.

### Tests

- [ ] testcontainers-based `tests/integration/conftest.py`.
- [ ] `tests/integration/test_audit_writer.py` — sign+insert+chain verify.
- [ ] `tests/integration/test_dispatcher.py` — publish a `task_assignment`,
      assert the agent receives it, the response is published, audit log has
      both rows with valid `prev_hash` chain.
- [ ] `tests/e2e/test_iter_1_demo.py` — full submit → approve cycle against
      a `MockLLMClient` with fixtures recorded once via `--real-llm`.
- [ ] Bring overall coverage and diff-coverage back to ≥80 %.

### Demo + CI

- [ ] `scripts/demo_iter_1.sh` — full end-to-end with two terminals walkthrough.
- [ ] CI: bump `--fail-under=80` in `ci.yml` diff-cover step.

## Out of scope (Iteration 2+)

- Architect, Backend, Frontend, DevOps, QA, SRE, Market Researcher agents.
- Real GitHub PR creation by Backend (Iteration 2).
- `TargetRepo` implementations beyond `SelfBootstrap` (Iteration 2).
- Audit-chain periodic verifier job (write the verifier function, but no
  scheduling yet — Iteration 3 / security harden).
- Hash-chain tamper alerts (Iteration 3 / security harden).
- Per-correlation summarisation when context grows past 70 %
  (Iteration 3 / cost harden).

## Risks

| Risk                                                                  | Mitigation                                                           |
|-----------------------------------------------------------------------|----------------------------------------------------------------------|
| `claude -p` per-invocation latency (~4 s observed) blocks tight loops | Run agents concurrently; TL doesn't wait for one PM call to finish before dispatching next. |
| Structured-JSON parsing flaky on LLM responses                        | `--json-schema` flag + retry once; fall back to fenced ```json``` extraction. |
| Subprocess fork storms under load                                     | Semaphore on `ClaudeCodeHeadlessClient.invoke` (max N concurrent), default N=5. |
| Postgres write contention on `audit_log`                              | INSERT-only single-writer per dispatcher; `audit_writer` role has no UPDATE/DELETE.  |
| Owner can't see what's happening                                      | `team_feed` already works; verified end-to-end in Iteration 0.       |

## Iteration 2 preview

- Architect + Backend + QA come online: full "write code → test → request
  review" loop on the `idea-validator` sandbox.
- `TargetRepo` concrete impls + `mcp__ai_team_repo__*` MCP tools with path
  scopes from ADR-004.
