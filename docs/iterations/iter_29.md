# Iter-29 Implementation Plan — LLM voice drafter for `telegram-tech-publisher` (ADR-0004 product slice via cross-repo agent chain)

> **For agentic workers:** This iter is dispatched against an *external* product repo via `GitHubTargetRepo` (iter-28). The chain runs TL → Architect → Backend → QA. The owner approves a single `pending_review` after QA. **Architect produces the file-by-file implementation plan inside the product repo (`docs/design/voice_drafter.md`) — this `iter_29.md` is the input specification for that plan, not a step-by-step TDD walkthrough on the ai_team side.**

**Goal:** Implement ADR-0004 ("Voice calibration") inside `girlsmakemedrink/telegram-tech-publisher` as the first end-to-end agent-driven product-repo PR. After this iter, the product repo has:
1. A working DB substrate (alembic + asyncpg + sqlalchemy[asyncio] + `users` table with JSONB `voice_store`).
2. An `LLMDrafterClient` Protocol with a `MockLLMDrafterClient` (unit tests) and an `AnthropicLLMDrafterClient` (real Sonnet 4.6, paid OPEX).
3. A `voice` module: 5 pre-built defaults + JSONB store + weighted sampling + prompt assembly.
4. A `Drafter` service that turns `(Candidate, User)` into a `Draft`.
5. A `/retune` admin command on the existing Telegram bot, gated by an env-driven allowlist.
6. A gated `@pytest.mark.real_llm` smoke (~$0.03/run) verifying the real API call works end-to-end.

End-state proof: PR opened by Backend on `iter-29/voice-drafter` branch, CI green, QA verdict `PASS`, owner approves `pending_review`, owner squash-merges manually.

**Architecture:** Single agent chain dispatched from ai_team. Two distinct LLM substrates:
- **ai_team agents** (TL/Architect/Backend/QA) run under owner's Max 5x via `claude -p` subprocess. Subscription-only. NEVER set `ANTHROPIC_API_KEY` in the ai_team env.
- **Product repo at runtime** uses the paid Anthropic API (`anthropic>=0.40`). `ANTHROPIC_API_KEY` lives in `.env.local` in the workspace (gitignored). Treated as product OPEX, not ai_team substrate.

The product repo's voice drafter follows ADR-008 (`LLMClient` Protocol pattern from ai_team) — the real `anthropic` SDK is imported in exactly one file (`llm/anthropic_client.py`); everywhere else uses the Protocol.

**Tech Stack additions to the product repo:**
- Runtime: `anthropic>=0.40`, `sqlalchemy[asyncio]>=2.0`, `alembic>=1.14`, `asyncpg>=0.30`.
- Dev: `aiosqlite>=0.20` (optional — not required if all DB-touching tests are marked `integration`).
- No new ai_team-side deps.

**Source spec inputs:**
- `girlsmakemedrink/telegram-tech-publisher:docs/adr/0004-voice-calibration.md` — locked spec; **see "Implementation refinements vs ADR-0004" below for explicit deviations**.
- `girlsmakemedrink/telegram-tech-publisher:src/telegram_tech_publisher/sources/base.py` — `Candidate` model (input contract).
- `girlsmakemedrink/telegram-tech-publisher:src/telegram_tech_publisher/publishers/telegram.py` — `TelegramPublisher` (unchanged in iter-29; iter-30 wires Source → Drafter → Publisher).
- `ai_team:docs/iterations/iter_28_handoff.md` — iter-29 strategic top: first agent task against product repo.
- `ai_team:docs/adr/0008-llm-access-strategy.md` — Protocol + Mock + Real pattern to replicate.

---

## Implementation refinements vs ADR-0004

These deviations are intentional refinements approved during iter-29 brainstorming (owner-acknowledged 2026-05-22). ADR-0004 amendment to ship in iter-29 wrap (post-merge, see "Approval ask" step 4 below).

| ADR-0004 says | iter-29 ships | Reason |
|---|---|---|
| `voice_store.examples: [{text, label, weight}]` | `voice_store.samples: [{id, candidate_external_id, draft_text, kind, score, created_at}]` | Traceability (id + provenance + timestamp). `kind` is explicit enum (`approved` / `edited`) replacing free-form `label`. `score` replaces `weight` (same semantics). |
| `defaults_template: str` (full text) | `default_voice: str \| None` (a key into `VOICE_DEFAULTS`) | The 5 default markdown files are static, version-controlled, large (~1500 tokens each). Storing the key is enough; full text is loaded at runtime. |
| `last_retuned_at: timestamp` | Dropped (per-sample `created_at` is enough; `max(samples.created_at)` reconstructs it) | Single source of truth. |
| Two-tier de-emphasis (10 → weight=0.3, 20 → drop) | Single threshold: clear `default_voice` once `labeled_count >= 20` | Simpler. iter-30+ can revisit if drafts feel off-voice in the 10–20 sample window. |
| ≤8 examples per draft, weighted by recency × user-label-score | Same | Unchanged. |
| `/retune` admin command | Same, plus an env-driven `ADMIN_TELEGRAM_USER_IDS` allowlist; non-admin senders are silently ignored *with a structlog warning line* | Allowlist closes a privilege gap; silent-no-reply prevents fingerprinting. |
| Prompt cache: voice block at top, behind cache marker | Same. `cache_control={"type": "ephemeral"}` on the system block holding the voice text | Unchanged. |

The voice_store JSONB shape, validated app-side via Pydantic in `voice/store.py`:
```json
{
  "default_voice": "python",
  "samples": [
    {
      "id": "uuid4",
      "candidate_external_id": "hn-42",
      "draft_text": "…",
      "kind": "approved",
      "score": 1.0,
      "created_at": "2026-05-22T18:00:00Z"
    }
  ]
}
```

Three rules enforced in `voice/store.py::append_sample` (pure function, easy to unit-test):
1. If `labeled_count + 1 >= 20`, clear `default_voice` to `None` on next write.
2. `samples` hard-capped at 200; oldest dropped on append.
3. `kind` and `score` validated by Pydantic; unknown `kind` raises `ValidationError` before DB write.

---

## Non-Goals (out of scope for iter-29)

- **Source → Drafter → Publisher wiring in the polling loop.** iter-30.
- **Labeling commands** (e.g., inline-keyboard 👍/👎 to grow `voice_store.samples`). iter-30.
- **Multi-admin scoping** beyond a flat `telegram_user_id` allowlist. Future.
- **Voice synthesis** from samples (distilling examples into a learned prose block). iter-30+ if drafts feel off-voice after personalization.
- **Topical reranking** of examples vs the candidate article. iter-30+ if needed.
- **Webhook mode** for the Telegram bot. Long-polling only.
- **FastAPI integration with the bot.** They're separate processes; the existing `telegram-tech-publisher` CLI entry isn't touched. New sibling subcommand `telegram-tech-publisher bot`.
- **Retry / circuit-breaker** around the `AnthropicLLMDrafterClient`. Lets errors propagate; iter-30 problem when the pipeline is wired.
- **Production deployment, monitoring, alerting.** Not part of any iter on this project yet.
- **Closing other iter-28 carry-overs** (priority #2 `_run` promotion, #3 dispatcher cascade flake, #4 workspace GC). Deferrable to iter-30+; not blocking.
- **Owner running the `real_llm` smoke.** Post-merge, owner's clock, paid OPEX. Not gating.

---

## File Structure (product repo)

### Created

```
src/telegram_tech_publisher/
├── db/
│   ├── __init__.py
│   ├── models.py            # SQLAlchemy 2 typed mapped-column: User
│   └── session.py           # async_engine + async_sessionmaker
├── llm/
│   ├── __init__.py
│   ├── client.py            # LLMDrafterClient Protocol, Example, Draft
│   ├── mock.py              # MockLLMDrafterClient (unit tests)
│   └── anthropic_client.py  # AnthropicLLMDrafterClient (only file importing `anthropic`)
├── voice/
│   ├── __init__.py
│   ├── defaults.py          # VOICE_DEFAULTS dict loaded from markdown
│   ├── store.py             # VoiceStore + VoiceSample + load/save/append_sample
│   ├── sampling.py          # pick_examples(store, k=8, now=…)
│   └── prompt.py            # build_voice_block(store) -> str
├── drafter/
│   ├── __init__.py
│   └── service.py           # Drafter class + UserNotFoundError
├── bot/
│   ├── __init__.py
│   ├── app.py               # build_application(...) → PTB Application
│   └── retune.py            # retune_command handler
└── prompts/voice_defaults/
    ├── python.md
    ├── devops.md
    ├── ai_ml.md
    ├── backend.md
    └── security.md

alembic/
├── env.py
├── script.py.mako
└── versions/
    └── 20260522_0001_init.py  # users table + voice_store JSONB

tests/unit/
├── test_voice_defaults.py
├── test_voice_store.py
├── test_voice_sampling.py
├── test_voice_prompt.py
├── test_drafter.py
└── test_retune_command.py

tests/integration/
├── test_db_roundtrip.py            # @integration
└── test_drafter_real_llm.py        # @real_llm + @integration, single API call, ~$0.03

alembic.ini
.env.local.example               # commits the schema, not the values
```

### Modified

- `pyproject.toml` — add `anthropic>=0.40`, `sqlalchemy[asyncio]>=2.0`, `alembic>=1.14`, `asyncpg>=0.30`. Register `real_llm` marker.
- `src/telegram_tech_publisher/__init__.py` (or wherever the click CLI lives) — add `bot` subcommand wiring `build_application(...)` + `run_polling()`.
- `README.md` — append a "Voice drafter smoke" section with the exact owner-side command.
- `.gitignore` — ensure `.env.local` is ignored.

### Settings additions (pydantic-settings; existing or newly-created `Settings(BaseSettings)`)

- `telegram_bot_token: str` (already needed for the bot; required at startup)
- `admin_telegram_user_ids: list[int]` (comma-separated in env)
- `database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/ttp_dev"`
- `anthropic_api_key: str | None = None` (None ⇒ `AnthropicLLMDrafterClient` can't be constructed; tests use mock)

---

## Design (file-by-file)

### `db/models.py`

SQLAlchemy 2 typed mapped-column. One table for iter-29:

```python
class User(Base):
    __tablename__ = "users"
    id: Mapped[UUID] = mapped_column(primary_key=True)
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, unique=True)
    voice_store: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    labeled_count: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now())
```

UUIDs generated app-side via `uuid.uuid4()` (no `pgcrypto`/`uuid-ossp` extension required).

### `db/session.py`

```python
engine = create_async_engine(settings.database_url, pool_pre_ping=True)
session_factory = async_sessionmaker(engine, expire_on_commit=False)
```

### Migration `alembic/versions/20260522_0001_init.py`

`op.create_table("users", ...)` matching the model exactly. `voice_store` defaults to `{}` JSONB. `created_at`/`updated_at` default to `now()` server-side. `telegram_user_id` is unique-indexed.

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

### `llm/mock.py`

`MockLLMDrafterClient` returns a deterministic stub: `f"[{candidate.title}] (mock draft, voice_len={len(voice_block)}, n_examples={len(examples)})"`. Token counts all 0 by default; tests that need specific values inject them via constructor args.

### `llm/anthropic_client.py`

Only file in the repo that imports `anthropic`. Sonnet 4.6 (`claude-sonnet-4-6`), max_tokens 2048, temperature 0.7. Reads `ANTHROPIC_API_KEY` from env if not passed to the constructor.

Message shape — `cache_control={"type": "ephemeral"}` on the system block holding the voice text:
```python
system = [{
    "type": "text",
    "text": voice_block,
    "cache_control": {"type": "ephemeral"},
}]
messages = [{"role": "user", "content": format_examples_and_candidate(examples, candidate)}]
response = await client.messages.create(
    model=self.model, system=system, messages=messages,
    max_tokens=self.max_tokens, temperature=self.temperature,
)
```

**Split for unit testability:** put pure prompt-shaping (`_build_request`) into a helper that returns a dict. Unit tests assert dict shape, cache_control placement, model id without ever calling the SDK. SDK call site stays thin.

No retry / circuit breaker in iter-29. `anthropic.APIError` and subclasses propagate.

### `voice/defaults.py`

```python
_DEFAULTS_DIR = Path(__file__).parent.parent / "prompts" / "voice_defaults"
VOICE_DEFAULTS: dict[str, str] = {
    name: (_DEFAULTS_DIR / f"{name}.md").read_text(encoding="utf-8")
    for name in ("python", "devops", "ai_ml", "backend", "security")
}
```

Each markdown file is ≥1024 tokens of voice/style guidance — the Anthropic prompt-cache min-block-size floor. Authored as part of iter-29 Backend work; ADR-0004 style.

### `voice/store.py`

```python
class VoiceSampleKind(StrEnum):
    APPROVED = "approved"
    EDITED = "edited"

class VoiceSample(BaseModel):
    id: UUID
    candidate_external_id: str
    draft_text: str
    kind: VoiceSampleKind
    score: float = Field(ge=0.0, le=1.0)
    created_at: datetime

class VoiceStore(BaseModel):
    default_voice: str | None
    samples: list[VoiceSample] = Field(default_factory=list)

async def load_voice_store(session, user_id) -> VoiceStore: ...
async def save_voice_store(session, user_id, store) -> None: ...
def append_sample(store: VoiceStore, sample: VoiceSample, labeled_count: int) -> VoiceStore: ...
```

`append_sample` enforces the three rules (clear-at-20, cap-at-200, Pydantic-validates-kind).

`save_voice_store` writes via `model_dump(mode="json")` into the JSONB column and increments `labeled_count` in the same transaction.

### `voice/sampling.py`

```python
def pick_examples(store: VoiceStore, k: int = 8, now: datetime | None = None) -> list[Example]:
    now = now or datetime.now(timezone.utc)
    def weight(s: VoiceSample) -> float:
        age_days = (now - s.created_at).total_seconds() / 86400
        return math.exp(-age_days / 30.0) * s.score
    ranked = sorted(store.samples, key=weight, reverse=True)
    return [_sample_to_example(s) for s in ranked[:k]]
```

Deterministic top-k (no randomization — LLM temperature provides variation). `now` injectable for tests. Score conventions: `approved` → 1.0, `edited` → 0.7 (set at write-site, not here).

### `voice/prompt.py`

```python
_NO_DEFAULT_STUB = (
    "Match the user's writing voice as demonstrated in the examples below. "
    "If no examples are present, write in a neutral, technical, "
    "Telegram-channel-appropriate tone."
)

def build_voice_block(store: VoiceStore) -> str:
    if store.default_voice is None:
        return _NO_DEFAULT_STUB
    return VOICE_DEFAULTS[store.default_voice]
```

When `default_voice is None`, the stub is ~50 tokens — too short for Anthropic's cache. Acceptable: post-personalization users trade cache hit for higher draft quality from real examples.

### `drafter/service.py`

```python
class UserNotFoundError(LookupError): ...

class Drafter:
    def __init__(self, llm_client: LLMDrafterClient) -> None:
        self._llm = llm_client
        self._log = structlog.get_logger(__name__)

    async def draft(
        self,
        session: AsyncSession,
        candidate: Candidate,
        telegram_user_id: int,
    ) -> Draft:
        user = await self._load_user(session, telegram_user_id)
        store = VoiceStore.model_validate(user.voice_store)
        voice_block = build_voice_block(store)
        examples = pick_examples(store, k=8)
        result = await self._llm.draft(voice_block, examples, candidate)
        self._log.info(
            "drafter.draft",
            telegram_user_id=telegram_user_id,
            candidate_external_id=candidate.external_id,
            default_voice=store.default_voice,
            n_examples=len(examples),
            voice_block_chars=len(voice_block),
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            cache_read_tokens=result.cache_read_tokens,
            model=result.model,
        )
        return result
```

Stateless. Returns the full `Draft` (text + token counts) so callers can observe cache behavior. `UserNotFoundError` raised explicitly when no row exists for `telegram_user_id` — Drafter is not a user-creation point; that's `/retune`.

### `bot/retune.py`

```python
async def retune_command(
    update, context, *, session_factory, admin_ids: frozenset[int],
) -> None:
    user = update.effective_user
    if user is None or user.id not in admin_ids:
        structlog.get_logger(__name__).warning(
            "bot.retune.unauthorized",
            telegram_user_id=getattr(user, "id", None),
        )
        return                                       # silent — don't fingerprint

    args = context.args or []
    valid = sorted(VOICE_DEFAULTS.keys())

    async with session_factory() as session, session.begin():
        if not args:
            store = await _load_or_init(session, user.id)
            await update.message.reply_text(
                f"Current default voice: {store.default_voice or '(none — using your labeled samples)'}\n"
                f"Samples on file: {len(store.samples)}\n"
                f"Usage: /retune <{'|'.join(valid)}|clear>"
            )
            return

        choice = args[0].lower()
        if choice == "clear":
            await _set_default(session, user.id, None)
            await update.message.reply_text("Default voice cleared. Drafts now lean on your labeled samples.")
        elif choice in VOICE_DEFAULTS:
            await _set_default(session, user.id, choice)
            await update.message.reply_text(f"Default voice set to '{choice}'.")
        else:
            await update.message.reply_text(
                f"Unknown voice '{args[0]}'. Choose from: {', '.join(valid)}, clear."
            )
```

`_load_or_init` is the single creation point for `User` rows in iter-29: if no row exists for `telegram_user_id`, INSERT one with `voice_store={"default_voice": None, "samples": []}`, `labeled_count=0`. Returns a `VoiceStore`.

### `bot/app.py` + new CLI subcommand

```python
def build_application(*, bot_token, session_factory, admin_ids) -> Application:
    app = Application.builder().token(bot_token).build()
    app.add_handler(CommandHandler(
        "retune",
        partial(retune_command, session_factory=session_factory, admin_ids=admin_ids),
    ))
    return app

@cli.command("bot")
def bot_cmd() -> None:
    settings = Settings()
    engine = create_async_engine(settings.database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    app = build_application(
        bot_token=settings.telegram_bot_token,
        session_factory=session_factory,
        admin_ids=frozenset(settings.admin_telegram_user_ids),
    )
    app.run_polling()
```

Long-polling only. Doesn't touch the existing FastAPI entry.

---

## Test plan

**Markers** (added to `[tool.pytest.ini_options].markers` in `pyproject.toml`):
```toml
markers = [
    "integration: tests requiring infra (Postgres, Redis)",
    "real_llm: tests that call the real Anthropic API (paid, opt-in)",
]
```
CI runs the default suite (no markers). Owner runs `integration` locally. `real_llm` is explicit opt-in.

**Unit tests** — fast, hermetic, no network, no DB. Run on every `pytest -q`.

| File | Coverage target |
|---|---|
| `test_voice_defaults.py` | All 5 keys present; each markdown ≥1024 tokens (approximate `len(text) // 4`); idempotent re-import. |
| `test_voice_store.py` | `append_sample` rules: clears `default_voice` at `labeled_count + 1 >= 20`; caps `samples` at 200 (oldest dropped); rejects unknown `kind` via Pydantic. |
| `test_voice_sampling.py` | `pick_examples`: top-k by `exp(-age/30) * score`; `k=8` cap; empty store → `[]`; deterministic ordering with injected `now`. |
| `test_voice_prompt.py` | `build_voice_block` returns the right default; stub when `default_voice is None`. |
| `test_drafter.py` | Drafter with `MockLLMDrafterClient` + a stub `AsyncSession` (small protocol-conforming helper in `tests/conftest.py`) returning a fixed `User`. Asserts: voice_block/examples/candidate passed correctly; `UserNotFoundError` on missing user; log emitted with right fields. |
| `test_retune_command.py` | Stub `Update` (mock effective_user + message) + stub session. Cases: non-admin → silent + structlog warning; admin no-args → state reply; admin valid voice → default set; admin invalid voice → error reply; admin `clear` → default cleared; first-time admin → User row created. |

**Integration tests** — owner runs `uv run pytest -m integration`. Not in CI.

| File | What it verifies |
|---|---|
| `test_db_roundtrip.py` | Real Postgres fixture. Insert a `User`, write a `VoiceStore` with samples, read it back via Pydantic, assert equality. Catches Pydantic↔JSONB shape drift early. |
| `test_drafter_real_llm.py` | **`@pytest.mark.real_llm` + `@pytest.mark.integration`.** Single API call. Insert admin user with `default_voice="python"`; build `AnthropicLLMDrafterClient` from env; call `Drafter.draft(...)` with a fixture `Candidate`. Assertions: `draft.text` non-empty; `draft.model == "claude-sonnet-4-6"`; `draft.input_tokens > 0`; `draft.output_tokens > 0`. **No content assertion** — LLM output isn't deterministic. ~$0.03 per run. |

**How owner runs the smoke** (documented in `README.md`):

```bash
# one-time: put ANTHROPIC_API_KEY in .env.local (gitignored)
echo "ANTHROPIC_API_KEY=sk-ant-..." >> .env.local

# run the gated smoke (~$0.03, ~10s)
uv run --env-file .env.local pytest -m "real_llm" -v
```

Postgres must be running locally (`docker compose up -d db` if a compose file lands in iter-29; otherwise owner-managed).

**Coverage:** Project standard is 80 % diff-cover. Unit tests hit `voice/*`, `drafter/*`, most of `bot/retune.py` ≥90 %. `llm/anthropic_client.py` is the hardest — its `_build_request` helper is fully unit-tested; the actual `messages.create` call site is only exercised under `real_llm`. Acceptable; project standard already exempts thin third-party-SDK glue.

---

## Agent chain choreography (ai_team-side dispatch)

### Chain shape

```
TL  →  Architect  →  Backend  →  QA  →  [pending_review #1]  →  owner merges
```

**Single pending_review** at the end of QA (owner decision 2026-05-22, reduced from the originally-proposed two-gate chain to keep momentum).

### Per-agent `TaskAssignmentPayload`s queued by TL on iter-29 kickoff

| # | Agent | `target_repo` | `requires_review` | `depends_on` | Deliverable |
|---|---|---|---|---|---|
| 1 | TL | (none — ai_team side) | False | — | Enqueues tasks 2–4 with the dependency graph below. |
| 2 | Architect | `girlsmakemedrink/telegram-tech-publisher` | False | task 1 | `docs/design/voice_drafter.md` in product repo on branch `iter-29/voice-drafter`. File-by-file plan mirroring this spec's "Design (file-by-file)" section. Commits the design doc as the first commit of the PR's branch. |
| 3 | Backend | `girlsmakemedrink/telegram-tech-publisher` | False | task 2 | All code + tests committed to `iter-29/voice-drafter`. PR opened via `GitHubTargetRepo.open_pr` against `main`. |
| 4 | QA | `girlsmakemedrink/telegram-tech-publisher` | **True** (pending_review #1) | task 3 | Runs `alembic upgrade head` in the workspace (so the `users` table exists for integration tests), then the unit + `integration` test suites; posts a PR comment with verdict (PASS / FAIL + specific findings). If Postgres is unreachable, falls back to `pytest -m "not integration"` and notes the skip in the verdict comment. Does **not** run the `real_llm` smoke. |

After pending_review #1 is approved, the chain terminates. Owner manually runs `gh pr merge --squash --delete-branch` from the product repo dir.

### Branch hygiene

CLAUDE.md hard constraint: "branch BEFORE first commit on a fresh-cloned repo."
- Architect's first action on the workspace: `git checkout -B iter-29/voice-drafter` (idempotent — handles fresh clone *and* re-runs).
- Forbidden-branch guards in `SelfBootstrapTargetRepo` (iter-28) prevent staging commits to `main`.

### Workspace reuse

All four agents share `~/.ai_team/workspaces/girlsmakemedrink--telegram-tech-publisher/`. Each invocation runs `ensure_local_clone()` (fetches if workspace exists, clones if not), then operates in place.

### Single-PR commit shape (Backend)

Conventional commits, squash on merge → one commit on `main`:
- `feat(db): bootstrap alembic + asyncpg + users table`
- `feat(llm): drafter client protocol + mock + anthropic impl`
- `feat(voice): defaults + store + sampling + prompt assembly`
- `feat(drafter): orchestrate voice + llm into Drafter service`
- `feat(bot): /retune admin command + bot CLI subcommand`
- `test: unit suite + db roundtrip + real_llm gated smoke`
- `docs: README voice drafter smoke + design doc`

### LLM substrate boundaries (re-stated for the chain)

- ai_team agents (TL/Architect/Backend/QA): subscription-only via `claude -p`. **NEVER** read `ANTHROPIC_API_KEY` from ai_team env.
- Product repo runtime: paid Anthropic API. `ANTHROPIC_API_KEY` in workspace `.env.local` (gitignored). Owner-managed. Smoke is owner-run from the workspace shell after merge.

### Cost envelope (subscription quota)

- TL: ~1 turn, negligible.
- Architect: ~3–6 turns producing `docs/design/voice_drafter.md`. ~$2–5.
- Backend: the heavy one. ~15–20 new files, ~30–50 turns including the test/lint loop. ~$20–50.
- QA: ~5–10 turns. ~$3–5.
- **Chain total: ~$25–60.** Within Max 5x tolerance.

---

## iter-29 Done Criteria

iter-29 is **done** when all of the following are true:

- [ ] PR opened by Backend agent against `girlsmakemedrink/telegram-tech-publisher:main` from `iter-29/voice-drafter` via `GitHubTargetRepo.open_pr`.
- [ ] PR diff contains the full file set from "File Structure → Created" + listed Modified files.
- [ ] CI green on the PR (lint `ruff check`, type-check `mypy --strict`, security `bandit --severity-level high`, default pytest).
- [ ] 80 % diff-cover met.
- [ ] QA verdict = PASS, posted as a PR comment, including:
  - Unit suite passed in workspace.
  - `pyproject.toml` registers `real_llm` marker.
  - No `anthropic` import outside `llm/anthropic_client.py` (grep check).
  - Migration `20260522_0001_init.py` present; model matches migration.
- [ ] Pending_review #1 approved by owner via `ai-team approve <task_id>`.
- [ ] Owner merges with `gh pr merge --squash --delete-branch`.
- [ ] Owner has optionally run the `real_llm` smoke locally and confirmed a non-empty draft was returned. (**Not gating** — post-merge owner activity.)
- [ ] `docs/iterations/iter_29_retro.md` written, including: cost actuals (subscription burn + optional paid API), what surprised, what's deferred to iter-30, ADR-0004 amendment landed (or scheduled).
- [ ] `docs/iterations/iter_29_handoff.md` written, surfacing iter-30 priorities (Source → Drafter → Publisher wiring, labeling commands, ADR-0004 amendment if not done in iter-29).

---

## Cost / time estimate

- **ai_team subscription quota**: ~$25–60 across the chain (estimates above).
- **Paid Anthropic API** (owner-side, optional): ~$0.03 if owner runs the `real_llm` smoke once. Not iter-29-gating.
- **Wall-clock**: ~1–2 days, dominated by Backend implementation + the inevitable test/lint loop.
- **Owner manual actions**: (a) approve pending_review #1; (b) `gh pr merge --squash --delete-branch`; (c) optionally run smoke + write retro/handoff.

---

## Risks specific to iter-29

1. **Backend task is the largest ai_team has attempted in one chain** (~15–20 new files). Mitigation: Architect's `docs/design/voice_drafter.md` enumerates every file with a one-line purpose, giving Backend a concrete checklist. If Backend stalls, owner interrupts, captures state in `iter_29_retro.md`, and either resumes or splits into a follow-on iter-29b.
2. **Dispatcher cascade flake** (iter-28 priority #3) could surface during the longer chain. Not solving inline. Note in retro if it happens.
3. **Postgres availability for QA's integration suite.** QA must detect-and-skip integration tests if no DB is reachable; unit suite is always-run. The QA agent prompt should explicitly handle this with a `pytest -m "not integration"` fallback and a note in the verdict comment.
4. **Anthropic SDK version drift.** Pin `anthropic>=0.40` but uncapped — minor API changes in patch releases of the SDK have hit other projects in past iters. Mitigation: `_build_request` is the seam; if a future SDK release breaks the call shape, only that helper changes.
5. **Voice default markdown authoring quality.** The 5 default files have to ≥1024 tokens *and* feel coherent as a writing-voice spec. If they're sloppy, drafts will be sloppy. The agent doesn't have access to "real" channel idiom, so the bar is: internally consistent, plausibly-developer-Telegram voice, distinct between the 5 categories (a python.md draft should be recognizably different from a security.md draft). Owner can refine them in a follow-up PR after running the smoke.
6. **Silent-ignore on non-admin `/retune`** could mask owner setup errors (wrong `ADMIN_TELEGRAM_USER_IDS` value). Mitigation already in design: structlog warning line logged — owner greps logs during initial setup.
7. **PR scope is large for a single review.** Mitigation: squash on merge keeps `main` clean; the design doc inside the PR gives the reviewer (owner) a structured starting point.

---

## What iter-29 explicitly does NOT do (re-stated)

- No Source → Drafter → Publisher wiring. iter-30.
- No labeling commands; no inline-keyboard 👍/👎. iter-30.
- No retry / circuit breaker around the Anthropic SDK.
- No webhook mode for the bot.
- No `core/config.py`-equivalent restructure.
- No closing of iter-28 P2/P3 carry-overs (`_run` promotion, cascade flake, workspace GC).
- No `real_llm` smoke run inside the chain (owner-only, post-merge, paid).
- No auto-merge from QA — single owner pending_review checkpoint after QA.

---

## Approval ask

Owner approves this spec by reading + responding with redlines or "approved". Once approved:

1. ai_team-side `iter_29.md` PR opened on `docs/iter-29-plan` branch in the ai_team repo, CI green, self-merge (standing dev-PR autonomy).
2. Chain kicked off: TL dispatched against `girlsmakemedrink/telegram-tech-publisher` with this spec as the source input.
3. Owner intervenes only at pending_review #1 (after QA) and the final manual `gh pr merge --squash --delete-branch`.
4. iter-29 wrap (after merge): retro + handoff + ADR-0004 amendment PR on the product repo to bring the ADR in line with the shipped schema (samples vs examples; single threshold; default_voice as key).
