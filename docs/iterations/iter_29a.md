# Iter-29a Implementation Plan — DB + LLM substrate for `telegram-tech-publisher` (cross-repo agent chain)

> **For agentic workers:** This iter is dispatched against an *external* product repo via `GitHubTargetRepo` (iter-28). The chain runs **TL → Architect → Backend → QA**. The owner approves a **single `pending_review`** after QA. **Architect produces the file-by-file implementation plan inside the product repo (`docs/design/29a_substrate.md`) — this `iter_29a.md` is the input specification for that plan, not a step-by-step TDD walkthrough on the ai_team side.**

**Goal:** Land the DB + LLM substrate inside `girlsmakemedrink/telegram-tech-publisher` ahead of iter-29b's voice/drafter/bot work. After 29a, the product repo has:

1. A working async DB substrate — alembic + asyncpg + sqlalchemy[asyncio] + a `users` table with a JSONB `voice_store` column + `labeled_count`.
2. An `LLMDrafterClient` Protocol with a `MockLLMDrafterClient` (unit tests) and an `AnthropicLLMDrafterClient` (real Sonnet 4.6, paid OPEX) — the latter built around a unit-testable `_build_request` helper.
3. `pyproject.toml` deps + the `real_llm` pytest marker registered (no `real_llm` test yet; that ships in 29b).
4. A single integration test (`tests/integration/test_db_roundtrip.py`) proving the migration + asyncpg/sqlalchemy wiring actually rounds-trips a `User` row.

End-state proof: PR opened by Backend on `iter-29a/substrate` branch, CI green, QA verdict `PASS`, owner approves `pending_review`, owner squash-merges manually.

**Architecture:** Single agent chain dispatched from ai_team. Two distinct LLM substrates kept rigorously separate:

- **ai_team agents** (TL/Architect/Backend/QA) run under owner's Max 5x via `claude -p` subprocess. Subscription-only. **NEVER** set `ANTHROPIC_API_KEY` in the ai_team env.
- **Product repo at runtime** uses the paid Anthropic API (`anthropic>=0.40`). `ANTHROPIC_API_KEY` lives in `.env.local` in the workspace (gitignored). Treated as product OPEX. No 29a test exercises this — the AnthropicLLMDrafterClient ships dark in 29a; first real call happens in 29b's smoke.

The product repo's voice drafter follows ADR-008 (`LLMClient` Protocol pattern from ai_team) — the real `anthropic` SDK is imported in exactly one file (`llm/anthropic_client.py`); everywhere else uses the Protocol. QA enforces with a grep check.

**Tech Stack additions to the product repo:**
- Runtime: `anthropic>=0.40`, `sqlalchemy[asyncio]>=2.0`, `alembic>=1.14`, `asyncpg>=0.30`.
- Dev: none. (`aiosqlite` deferred; if any test needs in-memory SQLite later, add then.)
- No new ai_team-side deps.

**Source spec inputs:**
- `girlsmakemedrink/telegram-tech-publisher:docs/adr/0004-voice-calibration.md` — amended schema (samples shape, `default_voice` key, single 20-sample threshold, `/retune` allowlist note). PR #4 merged 2026-05-22.
- `girlsmakemedrink/telegram-tech-publisher:src/telegram_tech_publisher/sources/base.py` — `Candidate` model (used in `LLMDrafterClient.draft()` signature).
- `girlsmakemedrink/telegram-tech-publisher:src/telegram_tech_publisher/config.py` — existing `Settings` class; 29a extends.
- `ai_team:docs/adr/0008-llm-access-strategy.md` — Protocol + Mock + Real pattern to replicate.
- `ai_team:docs/iterations/iter_28_handoff.md` — iter-29 strategic top: first agent chain against external product repo, split into 29a + 29b.

---

## Non-Goals (out of scope for iter-29a — these land in iter-29b)

- **`voice/` module.** Defaults, `VoiceStore` Pydantic, sampling, prompt assembly — all 29b. In 29a, `voice_store` on the `User` model is typed `dict[str, Any]` and validated by Pydantic only in 29b.
- **`drafter/` service.** The orchestrator that consumes the `LLMDrafterClient` + a user's voice — 29b.
- **`bot/` module.** `/retune` command, `bot/app.py`, the `telegram-tech-publisher bot` CLI subcommand — 29b.
- **`prompts/voice_defaults/*.md`.** The 5 default voice markdown files — 29b.
- **Settings: `admin_telegram_user_ids`.** That's bot-side, 29b. (29a adds `anthropic_api_key` only.)
- **`real_llm` smoke test.** The marker is registered in 29a; the test using it lands in 29b.
- **README "Voice drafter smoke" section.** 29b.
- **iter-30+ items:** Source → Drafter → Publisher wiring; labeling commands (👍/👎); retry / circuit breaker around the SDK; multi-admin scoping; webhook mode.

---

## File Structure (product repo)

### Created

```
src/telegram_tech_publisher/
├── db/
│   ├── __init__.py
│   ├── models.py            # SQLAlchemy 2 typed mapped-column: User
│   └── session.py           # async_engine + async_sessionmaker
└── llm/
    ├── __init__.py
    ├── client.py            # LLMDrafterClient Protocol, Example, Draft
    ├── mock.py              # MockLLMDrafterClient (unit tests)
    └── anthropic_client.py  # AnthropicLLMDrafterClient + _build_request

alembic/
├── env.py
├── script.py.mako
└── versions/
    └── 20260522_0001_init.py  # users table + voice_store JSONB

alembic.ini
.env.local.example               # ANTHROPIC_API_KEY schema only, gitignored counterpart

tests/unit/
├── test_db_models.py
├── test_llm_client_schemas.py
├── test_mock_drafter.py
└── test_anthropic_build_request.py

tests/integration/
└── test_db_roundtrip.py            # @pytest.mark.integration
```

### Modified

- `pyproject.toml` — add `anthropic>=0.40`, `sqlalchemy[asyncio]>=2.0`, `alembic>=1.14`, `asyncpg>=0.30` to `[project].dependencies`. Register `real_llm` marker (alongside the existing `integration` marker).
- `src/telegram_tech_publisher/config.py` — add `anthropic_api_key: str | None = None` to `Settings`.
- `.env.example` — append `ANTHROPIC_API_KEY=<paste-from-console.anthropic.com>` (with a comment noting it's optional in dev; required only for `real_llm` smoke in 29b+).
- `.gitignore` — ensure `.env.local` is ignored (likely already covered by `.env*` rule; verify).

### Settings additions (Pydantic-Settings)

Only one new field in 29a:

- `anthropic_api_key: str | None = None`
  - `None` ⇒ `AnthropicLLMDrafterClient` cannot be constructed (it raises `ValueError` if neither the constructor arg nor env is set). Tests use `MockLLMDrafterClient`.

`database_url` already exists from iter-27's anticipatory scaffold (default `postgresql+asyncpg://localhost/telegram_tech_publisher`). 29a uses it as-is.

---

## Design (file-by-file)

### `db/models.py`

SQLAlchemy 2 typed mapped-column style. One table for iter-29a (the only table iter-29 introduces, period — iter-29b is service code only):

```python
class Base(DeclarativeBase): ...

class User(Base):
    __tablename__ = "users"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    voice_store: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    labeled_count: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )
```

UUIDs generated app-side via `uuid.uuid4()` (no `pgcrypto` / `uuid-ossp` extension required). `voice_store` defaults to `{}` server-side via JSONB column default.

### `db/session.py`

```python
def make_engine(database_url: str) -> AsyncEngine:
    return create_async_engine(database_url, pool_pre_ping=True)

def make_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)
```

Factory functions (no module-level engine). Lets tests pass a Postgres-fixture URL; lets the future bot CLI build its own engine from `Settings`.

### Migration `alembic/versions/20260522_0001_init.py`

`op.create_table("users", …)` matching the model exactly:
- `id UUID PRIMARY KEY`
- `telegram_user_id BIGINT NOT NULL UNIQUE`
- `voice_store JSONB NOT NULL DEFAULT '{}'`
- `labeled_count INTEGER NOT NULL DEFAULT 0`
- `created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()`
- `updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()`
- Unique-index on `telegram_user_id` (covered by the `UNIQUE` constraint above; alembic emits it as a separate index for explicitness).

`downgrade()` drops the table.

`alembic/env.py` uses `target_metadata = Base.metadata` so future autogenerate works. `alembic.ini` reads `sqlalchemy.url` from `DATABASE_URL` env (via `interpolation` or explicit `env_from_config` — Architect picks the idiomatic approach).

### `llm/client.py`

```python
class Example(BaseModel):
    input_title: str
    input_body: str
    output_text: str

class Draft(BaseModel):
    text: str
    model: str
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int

class LLMDrafterClient(Protocol):
    async def draft(
        self,
        voice_block: str,
        examples: list[Example],
        candidate: Candidate,
    ) -> Draft: ...
```

`Candidate` imported from `sources/base.py`. Protocol is the ONLY surface 29b's `Drafter` will depend on.

### `llm/mock.py`

`MockLLMDrafterClient` returns a deterministic stub:

```python
return Draft(
    text=f"[{candidate.title}] (mock draft, voice_len={len(voice_block)}, n_examples={len(examples)})",
    model="mock",
    input_tokens=0,
    output_tokens=0,
    cache_read_tokens=0,
)
```

Constructor args let tests inject specific token counts when they need to assert cache-behavior reporting.

### `llm/anthropic_client.py`

**The only file in the repo that imports `anthropic`.**

Sonnet 4.6 — model id **`claude-sonnet-4-6`**. `max_tokens=2048`. `temperature=0.7`.

**API-key resolution.** Constructor signature: `__init__(self, *, api_key: str | None = None, model: str = "claude-sonnet-4-6", max_tokens: int = 2048, temperature: float = 0.7)`. If `api_key is None`, falls back to `os.environ.get("ANTHROPIC_API_KEY")`; raises `ValueError("ANTHROPIC_API_KEY not set")` if both are missing. The client does **not** depend on `Settings` — keeps the substrate library-grade. The 29b bot CLI is responsible for wiring `AnthropicLLMDrafterClient(api_key=settings.anthropic_api_key)` (or letting it fall through to env). Unit tests pass `api_key="test-key"`; the "missing key" test calls `AnthropicLLMDrafterClient(api_key=None)` with `ANTHROPIC_API_KEY` cleared from `os.environ` via `monkeypatch.delenv`.

**`_build_request` helper (the unit-test seam):**

```python
def _build_request(
    self,
    voice_block: str,
    examples: list[Example],
    candidate: Candidate,
) -> dict[str, Any]:
    return {
        "model": self.model,
        "max_tokens": self.max_tokens,
        "temperature": self.temperature,
        "system": [
            {
                "type": "text",
                "text": voice_block,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        "messages": [
            {
                "role": "user",
                "content": _format_examples_and_candidate(examples, candidate),
            }
        ],
    }
```

The `draft()` method is:

```python
async def draft(self, voice_block, examples, candidate) -> Draft:
    request = self._build_request(voice_block, examples, candidate)
    response = await self._client.messages.create(**request)
    return Draft(
        text=response.content[0].text,
        model=response.model,
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
        cache_read_tokens=getattr(response.usage, "cache_read_input_tokens", 0),
    )
```

Thin. The whole request shape is in `_build_request`, fully unit-testable. The SDK call site is two lines.

No retry / circuit breaker in iter-29a (or 29b). `anthropic.APIError` and subclasses propagate. iter-30+ when the polling loop wires this in.

`_format_examples_and_candidate` is a private helper that produces the user-message string. Examples are formatted as numbered "Past post N: …" blocks; the candidate is a "Draft a Telegram post for: title=… body=…" trailer. Plain-text formatting — no XML tags, no JSON. Architect refines the exact wording.

---

## Test plan

**Markers** (added to `[tool.pytest.ini_options].markers`):
```toml
markers = [
    "integration: tests requiring infra (Postgres, Redis)",  # existing
    "real_llm: tests that call the real Anthropic API (paid, opt-in)",  # new in 29a
]
```
CI runs the default suite (no markers). Owner runs `integration` locally (`uv run pytest -m integration`). `real_llm` is explicit opt-in — no test uses it yet; the marker exists so 29b can add tests without touching `pyproject.toml`.

### Unit tests — fast, hermetic, no network, no DB

| File | Coverage target |
|---|---|
| `test_db_models.py` | `User.__table__` has the expected columns + types (BigInteger on `telegram_user_id`, JSONB on `voice_store`, etc.); `User(...)` instantiation defaults are correct (`voice_store={}`, `labeled_count=0`). No session needed. |
| `test_llm_client_schemas.py` | `Example` + `Draft` Pydantic models accept valid inputs, reject missing required fields. Trivial — guards against accidental schema drift. |
| `test_mock_drafter.py` | `MockLLMDrafterClient.draft(...)` returns a deterministic stub with the right `voice_len`/`n_examples` substitution; injected token counts surface in the returned `Draft`. |
| `test_anthropic_build_request.py` | `AnthropicLLMDrafterClient(...)._build_request(...)` returns a dict with: `model == "claude-sonnet-4-6"`, `max_tokens == 2048`, `temperature == 0.7`, `system[0].cache_control == {"type": "ephemeral"}`, `system[0].text == <voice_block>`, `messages[0].role == "user"`. Also: constructor raises `ValueError` when no API key in arg + no `ANTHROPIC_API_KEY` env. |

### Integration tests — owner / QA runs `uv run pytest -m integration`; not in CI

| File | What it verifies |
|---|---|
| `test_db_roundtrip.py` | Real Postgres fixture (DSN from `DATABASE_URL` env, or `pytest.skip(...)` if unset/unreachable). Insert a `User(telegram_user_id=42, voice_store={})`, commit, re-query via `select(User).where(User.telegram_user_id == 42)`, assert `voice_store == {}`, `labeled_count == 0`, `id` is a UUID, `created_at` is set. Catches alembic / asyncpg / sqlalchemy[asyncio] wiring issues early. |

The integration test runs against a Postgres set up by the owner (or QA in the workspace via `docker compose up -d db` if Compose lands later; for now, owner-managed local Postgres). The pytest fixture handles transaction-per-test rollback.

**Coverage:** Project standard is 80% diff-cover. Unit tests hit `db/models.py`, `llm/client.py`, `llm/mock.py`, `llm/anthropic_client.py::_build_request` ≥90%. The SDK call site in `draft()` is exempt per project standard (thin third-party-SDK glue). `db/session.py` is thin enough to be covered by the integration test.

---

## Agent chain choreography (ai_team-side dispatch)

### Chain shape

```
TL  →  Architect  →  Backend  →  QA  →  [pending_review #1]  →  owner merges
```

**Single pending_review** at the end of QA (owner decision 2026-05-22).

### Per-agent `TaskAssignmentPayload`s queued by TL on iter-29a kickoff

| # | Agent | `target_repo` | `requires_review` | `depends_on` | Deliverable |
|---|---|---|---|---|---|
| 1 | TL | (none — ai_team side) | False | — | Enqueues tasks 2–4 with the dependency graph below. |
| 2 | Architect | `girlsmakemedrink/telegram-tech-publisher` | False | task 1 | `docs/design/29a_substrate.md` in product repo on branch `iter-29a/substrate`. File-by-file plan mirroring this spec's "Design (file-by-file)" section. Commits the design doc as the first commit of the PR's branch. |
| 3 | Backend | `girlsmakemedrink/telegram-tech-publisher` | False | task 2 | All code + tests committed to `iter-29a/substrate`. PR opened via `GitHubTargetRepo.open_pr` against `main`. |
| 4 | QA | `girlsmakemedrink/telegram-tech-publisher` | **True** (pending_review #1) | task 3 | Runs `alembic upgrade head` in the workspace (so the `users` table exists for the integration test), then `pytest` (unit) + `pytest -m integration`; posts a PR comment with verdict (PASS / FAIL + specific findings). If Postgres is unreachable, falls back to `pytest -m "not integration"` and notes the skip in the verdict comment. Does **not** run any `real_llm` test (none exists in 29a). |

After pending_review #1 is approved, the chain terminates. Owner manually runs `gh pr merge --squash --delete-branch` from the product repo workspace.

### Branch hygiene

CLAUDE.md hard constraint (added in iter-28 wrap): "branch BEFORE first commit on a fresh-cloned repo."
- Architect's first action on the workspace: `git checkout -B iter-29a/substrate` (uppercase `-B`, idempotent — handles fresh clone *and* re-runs).
- Forbidden-branch guards in `SelfBootstrapTargetRepo` (iter-28) prevent staging commits to `main`.

### Workspace reuse

All four agents share `~/.ai_team/workspaces/girlsmakemedrink--telegram-tech-publisher/`. Each invocation runs `ensure_local_clone()` (fetches if workspace exists, clones if not), then operates in place.

### Single-PR commit shape (Backend)

Conventional commits, squash on merge → one commit on `main`:
- `chore(deps): add alembic, sqlalchemy[asyncio], asyncpg, anthropic`
- `feat(db): bootstrap alembic + users table with JSONB voice_store`
- `feat(llm): drafter client protocol + mock + anthropic impl`
- `feat(config): add anthropic_api_key setting + .env.local schema`
- `test: unit suite + db roundtrip integration test`
- `docs: design doc for iter-29a substrate`

### LLM substrate boundaries (re-stated for the chain)

- ai_team agents (TL/Architect/Backend/QA): subscription-only via `claude -p`. **NEVER** read `ANTHROPIC_API_KEY` from ai_team env.
- Product repo runtime: paid Anthropic API. `ANTHROPIC_API_KEY` in workspace `.env.local` (gitignored). Owner-managed. **No 29a test uses it** — first real call happens in 29b's smoke.

### Cost envelope (subscription quota)

- TL: ~1 turn, negligible.
- Architect: ~2–4 turns producing `docs/design/29a_substrate.md`. ~$1–3.
- Backend: ~8–12 new files, ~20–30 turns with the test/lint loop. ~$10–20.
- QA: ~3–5 turns. ~$2–4.
- **Chain total: ~$13–27.** Comfortably within Max 5x tolerance and smaller than the original unified iter-29 estimate (~$25–60).

---

## iter-29a Done Criteria

iter-29a is **done** when all of the following are true:

- [ ] PR opened by Backend agent against `girlsmakemedrink/telegram-tech-publisher:main` from `iter-29a/substrate` via `GitHubTargetRepo.open_pr`.
- [ ] PR diff contains the full file set from "File Structure → Created" + listed Modified files.
- [ ] CI green on the PR (lint `ruff check`, type-check `mypy --strict`, security `bandit --severity-level high`, default pytest).
- [ ] 80% diff-cover met.
- [ ] QA verdict = `PASS`, posted as a PR comment, including:
  - Unit suite passed in workspace.
  - `pytest -m integration` passed in workspace (or graceful skip with Postgres-unreachable note).
  - `pyproject.toml` registers both `integration` and `real_llm` markers.
  - No `anthropic` import outside `llm/anthropic_client.py` (grep check).
  - Migration `20260522_0001_init.py` present; model matches migration (column types + nullability + defaults).
- [ ] `pending_review #1` approved by owner via `ai-team approve <task_id>`.
- [ ] Owner merges with `gh pr merge --squash --delete-branch`.

(iter-29a does **not** require a retro / handoff — those land at the end of iter-29b, covering both slices together.)

---

## Cost / time estimate

- **ai_team subscription quota**: ~$13–27 across the chain.
- **Paid Anthropic API**: $0 in 29a — no `real_llm` test runs. First paid call is in 29b's owner-run smoke.
- **Wall-clock**: ~half a day, dominated by Backend implementation + the test/lint loop.
- **Owner manual actions**: (a) approve pending_review #1; (b) `gh pr merge --squash --delete-branch`; (c) brief check that CI was green before merge (per the autonomy policy, this is usually a glance not a deep review).

---

## Risks specific to iter-29a

1. **First cross-repo chain since iter-28 GitHubTargetRepo landed.** Chain has run once in iter-28 (Backend wrap PR #43), but this is the first full TL→Architect→Backend→QA against an external repo with real code generation. Mitigation: spec is tight, scope is small, workspace already exists from iter-28 testing.
2. **alembic + asyncpg first-time setup.** `env.py` async-mode boilerplate is notoriously finicky. Mitigation: Architect should follow the canonical SQLAlchemy 2.0 async-alembic recipe; if Backend hits issues, falls back to a sync engine just for migration generation (asyncpg is runtime-only). Architect documents the chosen pattern.
3. **Postgres availability for QA's integration test.** QA must detect-and-skip with a `pytest -m "not integration"` fallback if no DB is reachable. The QA agent prompt explicitly handles this. (Same risk as iter-28's plan; no new mitigation needed.)
4. **`Candidate` import coupling.** `llm/client.py` imports `Candidate` from `sources/base.py`. If iter-27's `Candidate` definition shifts in iter-29b (it shouldn't), 29a tests break. Mitigation: iter-29a does not modify `Candidate`; if iter-29b needs to, it ships the change as part of 29b's diff.
5. **PR is mostly green-field code without runtime exercise.** Unit tests + one DB roundtrip is reasonable substrate coverage, but the AnthropicLLMDrafterClient's `draft()` method only runs under `real_llm`, which is 29b. We accept that the `_build_request` helper is the unit-tested surface and the SDK call site rides on 29b's smoke.

---

## What iter-29a explicitly does NOT do (re-stated)

- No `voice/` module — defaults, store, sampling, prompt. All 29b.
- No `drafter/` service. 29b.
- No `bot/` module, no `/retune`, no `bot` CLI subcommand. 29b.
- No `real_llm` smoke test (the marker is registered; the test isn't). 29b.
- No README "Voice drafter smoke" section. 29b.
- No retry / circuit breaker around the Anthropic SDK. iter-30+.
- No Source → Drafter → Publisher wiring. iter-30+.
- No closing of iter-28 P2/P3 carry-overs (`_run` promotion, dispatcher cascade flake, workspace GC). iter-30+.
- No retro / handoff doc for 29a in isolation — those write at the end of 29b.

---

## Approval ask

Owner approves this spec by reading + responding with redlines or "approved". Once approved:

1. ai_team-side `iter_29a.md` PR opened on `docs/iter-29a-plan` branch in the ai_team repo, CI green, owner self-merges (per standing dev-PR autonomy + the brainstorming workflow's "user reviews written spec" gate).
2. Chain kicked off: TL dispatched against `girlsmakemedrink/telegram-tech-publisher` with this spec as the source input.
3. Owner intervenes only at pending_review #1 (after QA) and the final manual `gh pr merge --squash --delete-branch`.
4. After 29a merges, the iter-29b spec gets brainstormed + written + dispatched on its own chain (voice + drafter + bot + tests + README + retro + handoff).
