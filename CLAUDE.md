# ai_team — Claude session handbook

> Required reading on first message of every new session. ~10k chars, designed
> to give a fresh Claude full operating context without rereading the codebase.

## Project

`ai_team` — мультиагентная команда разработки, которая выпускает софт.
Цель: **монетизируемые коммерческие продукты**, один репозиторий на продукт.
Владелец: solo dev (@girlsmakemedrink), других людей в петле нет.

Историю итераций здесь НЕ держим — она устаревает быстрее, чем файл перечитывается.
Текущее состояние и незакрытые хвосты всегда в последнем handoff:
`ls -t docs/iterations/ | head -4` → свежие `*_retro.md` (что сделано) и `*_handoff.md` (что открыто).
⚠️ Именно `-t` (по времени), не `tail`: по алфавиту `iter_9` встаёт ПОСЛЕ `iter_29`.

## Hard constraint — LLM access

**Subscription-only. NEVER set ANTHROPIC_API_KEY. NEVER add API billing.**

All LLM calls go through Claude Code (`claude` CLI) running locally under
the owner's Max 5x subscription. The adapter is in `core/llm/`:

- `ClaudeCodeHeadlessClient` (primary) — invokes `claude -p` as subprocess.
  Canonical interface in `core/llm/base.py:LLMClient` (Protocol). Required:
  `system_prompt`, `user_message`. Optional: `model` (tier), `allowed_tools`,
  `disallowed_tools`, `json_schema`, `max_budget_usd`, `session_id`,
  `mcp_config_path`, `timeout_s`, `max_turns`.
- `MockLLMClient` — fixture-based, used by every unit/integration test.
- `ClaudeAgentSDKClient` — stub; re-enable when SDK supports subscription auth.

**Gotchas (learned the hard way in iter-1)**:

1. `claude -p --json-schema` returns the validated object in
   the **`structured_output`** field of the JSON output, NOT in `result`.
   `_parse_response` prefers `structured_output` when present.
2. **Session flags are split, not interchangeable.** `--session-id <uuid>`
   *creates* a session with that ID and errors on second use
   ("Session ID is already in use"). `--resume <sid>` *resumes* an
   existing session and errors on an unknown ID. The adapter
   (`ClaudeCodeHeadlessClient`) uses `--session-id` on the first call
   with a given ID and `--resume` on subsequent ones — that's what
   gives us prompt caching across turns. Don't pass either flag from
   agent code; pass `session_id=…` on `LLMClient.invoke()` and let the
   adapter pick the right flag. (PR #3 set `--session-id` on every call
   and broke caching silently — iter-2 Day-1A re-measurement caught
   it; see `docs/iterations/iter_2_cache_report.md`.)
3. `--max-budget-usd` is a real CLI flag — per-tier defaults in
   `DEFAULT_MAX_BUDGET_USD_PER_TIER` (haiku 0.10 / sonnet 0.50 / opus 2.00).
   These are **subscription-quota dollars** (counted against the Max 5x
   programmatic budget by Anthropic). Not API billing. Setting them does
   NOT enable pay-as-you-go.
4. **`api_error_status=429` ≠ per-call budget exhaustion.** When an agent
   goes `BLOCKED(budget)` and the preserved API log shows
   `api_error_status=429` with `total_cost_usd` *far below* the per-call
   cap (e.g. $0.10 vs $2.50), the cause is the Max 5x **session/window
   quota**, not the `--max-budget-usd` flag. The 429 body includes the
   reset time ("resets HH:MM Europe/Moscow"). Wait for the reset and
   re-run via `ai-team retry-blocked`. iter-15's adapter correctly maps
   429 → `LLMBudgetExhaustedError` → `BLOCKED(budget)` for observability;
   do **not** "tune" `max_budget_usd` to try to dodge it. Seen in
   iter-23 R#2 and iter-25 R#2 — closed as environmental, not
   architectural. See `docs/iterations/iter_25_demo_report.md`.

Budget gates (estimate, not authoritative):
- 70 % monthly quota → soft warning in feed digest
- 90 % → pause non-critical (regression, monitoring, market scans)
- 100 % → `claude -p` returns a quota-exhausted error. Dispatcher marks
  itself `quota_exhausted`, refuses new tasks. CLI `ai-team submit` returns
  503 with a one-line explanation; `ai-team watch` shows a P1 alert in
  the feed. System recovers automatically when quota rolls over.

## Stack — boring on purpose

- Python 3.11+, `uv` for dep mgmt (lockfile committed).
- FastAPI + uvicorn (entry point: `apps/api/main.py`).
- Click + Rich for the `ai-team` CLI (`apps/cli/main.py`).
- Redis Streams (durable bus) + Pub/Sub (`team_feed`).
- Postgres 15 + SQLAlchemy 2.x async + Alembic.
- `structlog` (JSON logs with correlation_id), `prometheus-client`.
- `tenacity` for retries, `cryptography` for HMAC.
- `pytest`, `pytest-asyncio`, `testcontainers[postgres,redis]`.
- `ruff` (strict select), `mypy` (strict), `bandit` (gate on high only).
- Docker compose for local infra; no k8s/Helm in MVP.

If you reach for LangGraph, CrewAI, OpenAI SDK, or any "framework du jour" —
stop. We rejected those in ADR-001 for good reasons. Re-read it.

## Project conventions

- **Plan before code.** Every iteration starts with
  `docs/iterations/iter_N.md` written by Claude, reviewed by owner, only then
  code begins. After iteration: `iter_N_retro.md` with action items.
- **Conventional commits** (`feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert`).
- **Conventional-pre-commit** + `wagoid/commitlint-github-action` enforce it.
- **Squash-merge only.** `main` is protected: no force-push, no deletions,
  linear history, conversation resolution required. Branch protection does
  NOT require reviewer count (solo dev → self-approve allowed).
- **Two distinct approval layers — do not confuse them:**
  - **Claude-Code-as-dev PRs on `ai_team`**: Claude opens, CI runs, Claude
    squash-merges itself once green. Self-approve OK.
  - **AI agents (TL, PM, Architect, …) producing `task_report`s**:
    ALWAYS require owner approval via `ai-team approve <id>`. Agent →
    `pending_review` row → owner reviews → approve / reject with comment.
    Architect agent review is non-final; owner is final. Never skip this
    gate, even if all CI is green.
- **No mocks without TODO**. Any stub references a tracked issue.
- **80 % diff-cover gate** on every PR. (Iter-0 foundation PR was an
  exception at 60 % because most of the diff was untestable-without-infra
  scaffold; raised back to 80 % when integration tests landed in iter-1.
  See `docs/iterations/iter_0_retro.md` + `iter_1_retro.md` if you're
  tempted to lower it again — the answer is almost always "write the
  integration test instead.")
- **Bandit gates on high-severity only** (ADR-005 spec; low/medium are
  surfaced but advisory).
- **Tests**: unit (no infra, default), integration
  (`@pytest.mark.integration`, testcontainers spins up Postgres + Redis),
  real_llm (`@pytest.mark.real_llm --real-llm`, hits real `claude -p`).

## Make targets you'll use

```
make dev              # uv sync + pre-commit + .env
make up               # postgres + redis + prometheus + grafana via docker
make down             # tear down
make test             # full suite (unit + integration, mocked LLM)
make test-unit        # unit only
make test-integration # needs `make up` OR testcontainers
make lint             # ruff check
make typecheck        # mypy strict
make sec              # bandit high-only
make smoke-llm        # validate `claude -p` substrate against ADR-008
make demo             # iter-1 demo end-to-end
```

### iter-26 product CLI

```
ai-team brainstorm-products --niches X,Y,Z --constraints-json scripts/iter_26a_constraints.json
   # iter-26a: MR brainstorms 5 candidates per niche × 3 niches → 15 total,
   # QA ranks, owner picks top-3 in approval comment. ~$1-3 + ~15-25 min.

ai-team validate-product --slug <slug> --candidate-file <md> --depth standard
   # iter-26b: 4-agent diligence on one slug (MR competitors + Architect
   # tech-risk + PM revenue + QA go/no-go). Owner approves with
   # `decision: go|pivot|kill — <rationale>`. ~$8-14 + ~15-25 min at
   # depth=standard. Default constraints file: scripts/iter_26b_constraints.json.

scripts/demo_iter_26a.sh                       # owner-manual brainstorm demo
scripts/demo_iter_26b.sh [slug] [depth]        # owner-manual validate demo
```

## Operating principles for this Claude

- **Boring stack over trendy.** Reject framework adds unless explicitly
  needed. We rejected LangGraph and CrewAI — re-read ADR-001 if tempted.
- **Run validation checks yourself** (CI, smoke, demo). Don't ask the
  owner to run them. Self-approve your own dev PRs on `ai_team` once
  CI is green — this is the dev-PR layer, separate from the
  AI-agent-task-report layer above.
- **Confirm before destructive actions**: force-push, secret rotation,
  external sends, dropping DB data, package downgrades.
- **No mocks for real-LLM gotchas**. ScriptedLLM bypasses the
  `claude -p` parser, so every iteration should run `make smoke-llm` and
  `make demo` against real `claude -p` before claiming done.
- **Quota estimates are best-effort, not authoritative.** When `claude -p`
  returns a quota-exhausted error, that is the only authoritative signal.
  Do not try to outsmart the limit by tweaking the estimate formula or
  per-tier budgets to squeeze more in — that's a waste of cycles. If
  estimates drift from reality > 20 %, recalibrate the price table in
  `core/llm/base.py:PRICE_TABLE_CENTS_PER_MTOK`, then move on.
- **Use TaskCreate** to track work in iterations of ≥3 steps.
- **Branch BEFORE the first commit on a fresh-cloned repo.** Default to
  a feature branch even when "I'll branch after this commit" feels
  obvious — local-`main` divergence is harder to undo than to prevent,
  and the auto-classifier (correctly) blocks `git reset --hard` as a
  recovery shortcut. Lesson from iter-27 Phase A.
- **Cross-repo tasks run with `cwd = workspace`.** When a
  `TaskAssignment` carries `payload.target_repo="<owner>/<repo>"`, the
  dispatcher resolves to `~/.ai_team/workspaces/<owner>--<repo>/` and
  the agent's `claude -p` subprocess runs in that cwd with
  `AI_TEAM_REPO_ROOT` populated. Self-hosting tasks (no `target_repo`)
  keep their current behavior — `cwd` inherits the dispatcher's cwd.
  Added in iter-29c PR 1 (`8015123`).
- **Commit small, conventional, push frequently.** Squash-merge collapses
  on merge.
- **Dev extras require `uv sync --extra dev --all-groups`.** Any repo with
  PEP 621 `[project.optional-dependencies].dev` (ai_team does; product
  repos may) needs that flag — bare `uv sync` skips those extras and
  leaves `respx`, `pre-commit`, etc. uninstalled.
- **`pending_reviews` rows are produced by the QA Engineer agent only.**
  Chains that legitimately skip QA (e.g. docs-only TL → DevOps) will not
  create a review record — that is by design, not a missing wire.

## Вынесено в `.claude/rules/` (грузится по месту работы)

- `Architecture (one screen)` → `.claude/rules/architecture.md` (32 строк)
- `Agents (9 + 1 stub)` → `.claude/rules/agents-roster.md` (26 строк)
- `Where to look` → `.claude/rules/repo-map.md` (45 строк)
- `Key ADRs (`docs/adr/`)` → `.claude/rules/adrs.md` (16 строк)
