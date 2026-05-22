# Iter-27 Implementation Plan — Bootstrap `telegram-tech-publisher` product repo

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bootstrap a new GitHub repository `girlsmakemedrink/telegram-tech-publisher` with PRD, foundational ADRs, crisis playbook, CI skeleton, and two smoke-grade pipelines (GitHub release polling → stdout, Telegram Bot publish → test channel). End-state: a fresh repo that can compile, lint, test, and prove both ends of the eventual data flow with hardcoded inputs. Feature implementation (LLM voice drafting, scheduler, multi-tenant, payments, owner-onboarding) is deferred to iter-28+.

**Architecture:** Two-repo split per ADR-009 (`TARGET_REPO` abstraction). `ai_team` stays in self-bootstrap mode for this iter — Claude Code (me) drives work in the new repo directly via local tools, without going through ai_team agents. The new repo follows the same boring-stack conventions as ai_team (Python 3.11 + uv + FastAPI + Postgres + Click + Rich + ruff/mypy/bandit + commitlint + conventional commits + squash-merge). `GitHubTargetRepo` carry-over stays deferred to iter-28 (when we will have lived with the new repo for a few days and know what shape the abstraction actually needs).

**Tech Stack (target repo):** Python 3.11, uv (lockfile committed), FastAPI + uvicorn, Click + Rich (CLI), Postgres 15 + SQLAlchemy 2.x async + Alembic, `httpx` (HTTP), `python-telegram-bot` v22 (Bot API client; sync mode for smoke, async for v0), `feedparser` (RSS smoke later), `pytest` + `pytest-asyncio` + `testcontainers[postgres]`, `ruff` (strict select), `mypy` (strict), `bandit` (gate on high), `structlog` (JSON logs), `prometheus-client` (later). No LangGraph / CrewAI / OpenAI SDK; reuse `ClaudeCodeHeadlessClient` pattern from ai_team when LLM work lands in iter-28+.

**Source spec inputs:** `docs/products/telegram-tech-publisher/_validation_summary.md` (owner-approved `go_with_caveats`, 2026-05-22), plus the three upstream diligence artifacts (`competitors.md`, `tech_risk.md`, `revenue.md`).

**Owner's two MVP caveats (locked, must be honored):**
1. Telegram Stars as primary payment rail for MVP; YooKassa legal-entity setup as parallel post-MVP track.
2. Draft a Telegram-blocking crisis playbook (English-channel pivot criteria + Bot API failover) BEFORE launch. iter-27 ships v1 of this playbook.

---

## Non-Goals (out of scope for iter-27)

- LLM voice drafting (Sonnet few-shot) — iter-28.
- Multi-source aggregation beyond GitHub releases — iter-28.
- Scheduler / queue / publish-cadence engine — iter-28.
- User onboarding flow (voice samples, channel link, source config) — iter-29.
- Payment integration (Telegram Stars handler) — iter-30.
- Multi-tenant (Postgres per-tenant row partitioning) — iter-30.
- YooKassa legal entity setup — owner-side action, tracked separately.
- `GitHubTargetRepo` implementation (the abstraction in `ai_team/core/target_repo/`) — iter-28 carry-over.
- Production deployment (caddy, systemd, monitoring) — iter-31+.
- Anything related to X/Twitter source — descoped per QA (rss.app bridge stays as a future placeholder, not built in iter-27).

---

## File Structure

### In `ai_team` repo (this PR + iter-end PRs)

**Created (this PR):**
- `docs/iterations/iter_27.md` — this file.

**Created (end of iter-27):**
- `docs/iterations/iter_27_retro.md` — retro after iter-27 done.
- `docs/iterations/iter_27_handoff.md` — handoff to iter-28.

**Modified (end of iter-27):**
- `CLAUDE.md` — one paragraph in "Where to look" pointing at the new repo; one line in "Project" section noting the iter-27 bootstrap.

### In new `telegram-tech-publisher` repo (iter-27 deliverables)

**Repo root:**
- `README.md` — one-screen product elevator + bootstrap status.
- `LICENSE` — MIT (matches owner's other repos; confirm in step A3 if different).
- `.gitignore` — Python + uv + IDE + `.env*` + `*.log`.
- `pyproject.toml` — uv-managed, project name `telegram-tech-publisher`, deps listed under `[project.dependencies]`.
- `uv.lock` — committed.
- `.python-version` — `3.11`.
- `.env.example` — `TELEGRAM_BOT_TOKEN`, `TELEGRAM_TEST_CHANNEL_ID`, `GITHUB_TOKEN`, `DATABASE_URL`, `LOG_LEVEL`.
- `Makefile` — `dev`, `lint`, `typecheck`, `sec`, `test`, `smoke-github`, `smoke-telegram`.
- `.pre-commit-config.yaml` — ruff + mypy + commitlint hooks (mirror ai_team).
- `commitlint.config.js` — `@commitlint/config-conventional`, subject-max-length 100, body-max-line-length 100 (warning) — matches ai_team.

**`.github/workflows/`:**
- `ci.yml` — lint + typecheck + test job (Python 3.11 + uv).
- `commitlint.yml` — `wagoid/commitlint-github-action@v6` (mirror ai_team).

**`docs/`:**
- `PRD.md` — owner-facing product spec (MVP scope, success metrics, non-goals).
- `adr/0001-stack.md` — Python + FastAPI + Postgres + uv + boring-stack rationale.
- `adr/0002-source-priorities.md` — GitHub + HN sources in MVP; X via rss.app deferred; RSS in iter-29+.
- `adr/0003-payment-rail.md` — Telegram Stars primary; YooKassa parallel post-MVP track; CryptoPay rejected.
- `adr/0004-voice-calibration.md` — Sonnet 4.6 few-shot with pre-built developer-channel voice defaults; embedding-retrieval rejected as overengineering.
- `adr/0005-scheduler.md` — Postgres-as-queue + APScheduler; per-user timezone aware; exponential backoff on Telegram 5xx; idempotency via job-id de-dupe.
- `adr/0006-multi-tenancy.md` — single Postgres, row-level tenancy keyed on `user_id`; encrypt GitHub PATs at rest.
- `playbooks/crisis_telegram_blocking.md` — owner's caveat #2: monitoring signals, English-channel pivot criteria, Bot API failover logic, drill cadence.
- `risks.md` — carried over from QA's iter-26b risk register.

**`src/telegram_tech_publisher/`:**
- `__init__.py`
- `sources/__init__.py`
- `sources/github_releases.py` — smoke: poll one hardcoded repo's releases endpoint, emit `Candidate` instances.
- `sources/base.py` — `Source(Protocol)` + `Candidate(BaseModel)` shapes.
- `publishers/__init__.py`
- `publishers/telegram.py` — smoke: send one hardcoded message to `TELEGRAM_TEST_CHANNEL_ID`.
- `cli.py` — Click entry exposing `smoke-github` and `smoke-telegram` sub-commands (also wired in Makefile).
- `config.py` — `pydantic-settings` env loader.

**`tests/`:**
- `unit/test_github_releases.py` — mock the GitHub HTTP response, assert `Candidate` shape.
- `unit/test_telegram_publisher.py` — mock the Bot API client, assert payload + escaping.
- `unit/test_config.py` — env loader sanity.
- `unit/conftest.py` — shared fixtures.

**Files NOT created in iter-27** (explicit non-goals — see Non-Goals section):
- `src/.../drafter/` (LLM voice), `src/.../scheduler/`, `src/.../payments/`, `src/.../onboarding/`, Postgres migrations under `src/.../persistence/migrations/`, `infra/`, `prompts/`.

---

## Phase A — Repo creation + scaffold (Day 1, ~4-6h)

### Task A1: Create empty GitHub repo

**Files:** none (remote-only action).

- [ ] **Step A1.1: Confirm repo doesn't already exist**

Run: `gh repo view girlsmakemedrink/telegram-tech-publisher 2>&1 | head -3`
Expected: `Could not resolve to a Repository ...` (i.e., 404 — repo does not yet exist).

- [ ] **Step A1.2: Create the repo with `gh`**

Run:
```bash
gh repo create girlsmakemedrink/telegram-tech-publisher \
  --public \
  --description "AI content engine for Telegram developer channels" \
  --license mit \
  --confirm
```
Expected: prints the new repo URL.

- [ ] **Step A1.3: Verify branch protection-friendly defaults**

Run: `gh repo view girlsmakemedrink/telegram-tech-publisher --json defaultBranchRef,visibility,licenseInfo --jq .`
Expected: `defaultBranchRef.name == "main"`, `visibility == "PUBLIC"`, `licenseInfo.key == "mit"`.

### Task A2: Clone locally and create initial commit

**Files:**
- Create: `~/telegram-tech-publisher/` (working tree).

- [ ] **Step A2.1: Clone**

Run: `cd ~ && gh repo clone girlsmakemedrink/telegram-tech-publisher`
Expected: clones to `~/telegram-tech-publisher` (gh auto-uses SSH if configured).

- [ ] **Step A2.2: Verify clean state**

Run: `cd ~/telegram-tech-publisher && git log --oneline -5 && git status`
Expected: 1-2 initial commits from `gh repo create` (LICENSE + README.md), clean tree.

### Task A3: Add `.gitignore`, README skeleton, `.python-version`

**Files:**
- Create: `~/telegram-tech-publisher/.gitignore`
- Modify: `~/telegram-tech-publisher/README.md` (replace gh-generated stub)
- Create: `~/telegram-tech-publisher/.python-version`
- Create: `~/telegram-tech-publisher/.env.example`

- [ ] **Step A3.1: Write `.gitignore`** (copy from ai_team baseline + uv additions)

```
# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
build/
dist/
*.egg-info/
.pytest_cache/
.mypy_cache/
.ruff_cache/
htmlcov/
.coverage
coverage.xml

# uv
.venv/

# IDE
.vscode/
.idea/
*.swp
*.swo

# Env / secrets
.env
.env.*
!.env.example

# Logs
*.log
logs/
```

- [ ] **Step A3.2: Write `README.md`** (replace the gh stub)

```markdown
# telegram-tech-publisher

AI content engine for Telegram developer channels. Curates from GitHub releases + HN, drafts in the channel's voice, ships 3 posts/day.

**Status:** iter-27 bootstrap (2026-05-22). Foundational docs + two smoke pipelines only — not production-ready. See `docs/PRD.md` for product scope and `docs/iterations/` (in the [ai_team repo](https://github.com/girlsmakemedrink/ai_team)) for iteration history.

## Quickstart (dev)

```bash
uv sync
cp .env.example .env  # fill in TELEGRAM_BOT_TOKEN + TELEGRAM_TEST_CHANNEL_ID + GITHUB_TOKEN
make smoke-github     # poll one repo's releases, print candidates to stdout
make smoke-telegram   # send "iter-27 smoke" message to test channel
```

## License

MIT — see [LICENSE](LICENSE).
```

- [ ] **Step A3.3: Write `.python-version`**

```
3.11
```

- [ ] **Step A3.4: Write `.env.example`**

```
# Telegram Bot API
TELEGRAM_BOT_TOKEN=<paste-from-@BotFather>
TELEGRAM_TEST_CHANNEL_ID=<channel-id-or-@username>

# GitHub
GITHUB_TOKEN=<paste-from-https://github.com/settings/tokens>

# Database (iter-28+)
DATABASE_URL=postgresql+asyncpg://localhost/telegram_tech_publisher

# Logging
LOG_LEVEL=INFO
```

- [ ] **Step A3.5: Commit**

```bash
git add .gitignore README.md .python-version .env.example
git commit -m "chore: scaffold repo skeleton (.gitignore, README, .python-version, .env.example)"
```

### Task A4: `uv init` Python project + `pyproject.toml`

**Files:**
- Create: `~/telegram-tech-publisher/pyproject.toml`
- Create: `~/telegram-tech-publisher/uv.lock`
- Create: `~/telegram-tech-publisher/src/telegram_tech_publisher/__init__.py`

- [ ] **Step A4.1: Initialize uv project**

Run:
```bash
cd ~/telegram-tech-publisher
uv init --package --name telegram-tech-publisher --python 3.11
```
Expected: creates `pyproject.toml` + `src/telegram_tech_publisher/__init__.py` + stub.

- [ ] **Step A4.2: Add core dependencies**

Run:
```bash
uv add \
  'fastapi>=0.115' \
  'uvicorn[standard]>=0.32' \
  'click>=8.1' \
  'rich>=13.9' \
  'httpx>=0.27' \
  'pydantic>=2.9' \
  'pydantic-settings>=2.6' \
  'python-telegram-bot>=22.0' \
  'structlog>=24.4'
```

- [ ] **Step A4.3: Add dev dependencies**

Run:
```bash
uv add --dev \
  'ruff>=0.7' \
  'mypy>=1.13' \
  'bandit>=1.8' \
  'pytest>=8.3' \
  'pytest-asyncio>=0.24' \
  'pytest-cov>=6.0' \
  'respx>=0.21'
```

- [ ] **Step A4.4: Verify install**

Run: `uv sync && uv run python -c "import telegram_tech_publisher; print('ok')"`
Expected: `ok`.

- [ ] **Step A4.5: Edit `pyproject.toml` — add ruff/mypy/pytest config**

Append the following to `pyproject.toml`:
```toml
[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "I", "N", "UP", "B", "A", "C4", "SIM", "TCH", "RUF"]
ignore = ["E501"]

[tool.mypy]
python_version = "3.11"
strict = true
warn_unreachable = true
disallow_any_generics = true

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
markers = [
    "integration: tests requiring infra (Postgres, Redis)",
]
```

- [ ] **Step A4.6: Commit**

```bash
git add pyproject.toml uv.lock src/telegram_tech_publisher/__init__.py
git commit -m "chore: bootstrap uv project + core deps + ruff/mypy/pytest config"
```

### Task A5: CI skeleton (`.github/workflows/`)

**Files:**
- Create: `~/telegram-tech-publisher/.github/workflows/ci.yml`
- Create: `~/telegram-tech-publisher/.github/workflows/commitlint.yml`

- [ ] **Step A5.1: Write `ci.yml`**

```yaml
name: ci
on:
  push:
    branches: [main]
  pull_request:

jobs:
  lint-and-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
        with:
          enable-cache: true
      - name: Set up Python
        run: uv python install 3.11
      - name: Sync deps
        run: uv sync --frozen
      - name: Ruff
        run: uv run ruff check .
      - name: Ruff format check
        run: uv run ruff format --check .
      - name: Mypy
        run: uv run mypy src
      - name: Bandit (high-only)
        run: uv run bandit -r src -ll
      - name: Pytest
        run: uv run pytest -v --cov=src --cov-fail-under=80
```

- [ ] **Step A5.2: Write `commitlint.yml`** (mirror ai_team)

```yaml
name: commitlint
on:
  pull_request:

jobs:
  commitlint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: wagoid/commitlint-github-action@v6
        with:
          configFile: commitlint.config.js
```

- [ ] **Step A5.3: Write `commitlint.config.js`** (mirror ai_team)

```javascript
module.exports = {
  extends: ['@commitlint/config-conventional'],
  rules: {
    'subject-max-length': [2, 'always', 100],
    'body-max-line-length': [1, 'always', 100],
  },
};
```

- [ ] **Step A5.4: Commit**

```bash
git add .github/workflows/ commitlint.config.js
git commit -m "ci: add lint-test + commitlint GitHub Actions"
```

### Task A6: Makefile

**Files:**
- Create: `~/telegram-tech-publisher/Makefile`

- [ ] **Step A6.1: Write Makefile**

```makefile
.PHONY: dev lint typecheck sec test smoke-github smoke-telegram

dev:
	uv sync
	cp -n .env.example .env || true

lint:
	uv run ruff check .
	uv run ruff format --check .

typecheck:
	uv run mypy src

sec:
	uv run bandit -r src -ll

test:
	uv run pytest -v --cov=src --cov-fail-under=80

smoke-github:
	uv run python -m telegram_tech_publisher.cli smoke-github

smoke-telegram:
	uv run python -m telegram_tech_publisher.cli smoke-telegram
```

- [ ] **Step A6.2: Verify `make dev` works**

Run: `cd ~/telegram-tech-publisher && make dev`
Expected: uv sync runs clean, `.env` created (or already exists).

- [ ] **Step A6.3: Commit**

```bash
git add Makefile
git commit -m "chore: add Makefile targets (dev/lint/typecheck/sec/test/smoke-*)"
```

### Task A7: Push scaffold + open Phase-A PR

- [ ] **Step A7.1: Push to feature branch, open PR**

Run:
```bash
cd ~/telegram-tech-publisher
git checkout -b chore/iter-27-phase-a-scaffold
git push -u origin chore/iter-27-phase-a-scaffold
gh pr create --title "chore(iter-27): Phase A scaffold (uv + CI + Makefile)" \
  --body "iter-27 Phase A: repo scaffold per ai_team/docs/iterations/iter_27.md. No product code yet — just bootstrap."
```

- [ ] **Step A7.2: Watch CI, squash-merge when green**

Run: `gh pr checks <pr-num> --watch` then `gh pr merge <pr-num> --squash --delete-branch`.

---

## Phase B — Docs (PRD + ADRs + crisis playbook) (Days 2-3, ~8-12h)

### Task B1: PRD

**Files:**
- Create: `~/telegram-tech-publisher/docs/PRD.md`

- [ ] **Step B1.1: Draft PRD outline**

Use the iter-26b `_validation_summary.md` MVP scope as input. PRD structure:
- **Problem** (2 paragraphs from validation: CIS developer-influencer pain, source-monitor-then-draft loop)
- **Solution** (1 paragraph: AI content engine, GitHub+HN sources, voice-aware drafting, Telegram delivery)
- **MVP scope** (bullets — single channel, 3 posts/day, GitHub + HN sources, Telegram Stars, no X)
- **Out of scope for MVP** (X, multi-channel, RSS, free-tier ad model)
- **Success metrics** (10 paying users via owner's CIS network in 90 days; 90%+ post-approval rate; <$0.30/user/day LLM opex)
- **Pricing** ($20-35/month tier — confirmed in revenue.md)
- **Risks** (link to `risks.md`, summarize top-3)
- **Caveats** (Telegram Stars commitment, crisis playbook required pre-launch)
- **Build timeline** (8-12 week target post iter-27, 8-iter rough plan to first paying user)

- [ ] **Step B1.2: Write `docs/PRD.md`** (target: 250-400 lines)

Pull MVP scope verbatim from `_validation_summary.md` `## Next steps` section so the QA-blessed scope isn't drift-prone. Cite the validation summary at the top.

- [ ] **Step B1.3: Commit on feature branch**

```bash
git checkout -b docs/iter-27-phase-b-prd
git add docs/PRD.md
git commit -m "docs: add MVP PRD (single-channel + GitHub/HN sources + Telegram Stars)"
```

### Task B2: ADRs 0001-0006

**Files:**
- Create: `~/telegram-tech-publisher/docs/adr/0001-stack.md`
- Create: `~/telegram-tech-publisher/docs/adr/0002-source-priorities.md`
- Create: `~/telegram-tech-publisher/docs/adr/0003-payment-rail.md`
- Create: `~/telegram-tech-publisher/docs/adr/0004-voice-calibration.md`
- Create: `~/telegram-tech-publisher/docs/adr/0005-scheduler.md`
- Create: `~/telegram-tech-publisher/docs/adr/0006-multi-tenancy.md`

- [ ] **Step B2.1: Write ADR-0001 (stack)** — same boring-stack rationale as ai_team ADR-001, scoped to single-product needs.

- [ ] **Step B2.2: Write ADR-0002 (source priorities)** — GitHub releases + HN in MVP; X via rss.app deferred; RSS in iter-29+. Cite `tech_risk.md` X risk component (severity 5).

- [ ] **Step B2.3: Write ADR-0003 (payment rail)** — Telegram Stars primary (0% friction in-Telegram, accept 50% cut at MVP scale); YooKassa as parallel post-MVP track when legal entity ready; CryptoPay rejected (niche). Cite owner's iter-26b approval comment verbatim.

- [ ] **Step B2.4: Write ADR-0004 (voice calibration)** — Sonnet 4.6 few-shot with 10-20 user-labeled examples + pre-built developer-channel voice defaults to eliminate cold-start. Reject embeddings/fine-tune as premature. Cite `tech_risk.md` LLM voice-tone drafting component (complexity 3) + `_validation_summary.md` risk #5.

- [ ] **Step B2.5: Write ADR-0005 (scheduler)** — Postgres-as-queue + APScheduler in-process. Per-user timezone via `zoneinfo`. Exponential backoff on Telegram 5xx. Idempotency via job-id de-dupe (never double-post on worker restart). Cite `tech_risk.md` scheduler/queue component (complexity 2).

- [ ] **Step B2.6: Write ADR-0006 (multi-tenancy)** — single Postgres, row-level tenancy keyed on `user_id`. Encrypt GitHub PATs at rest (Fernet, key in env). Voice samples stored as JSONB (10-50KB/user per `tech_risk.md`).

- [ ] **Step B2.7: Commit (single conventional commit covering all ADRs)**

```bash
git add docs/adr/
git commit -m "docs: add foundational ADRs 0001-0006 (stack, sources, payment, voice, scheduler, tenancy)"
```

### Task B3: Crisis playbook

**Files:**
- Create: `~/telegram-tech-publisher/docs/playbooks/crisis_telegram_blocking.md`

- [ ] **Step B3.1: Write the playbook**

Required sections (per owner's caveat #2):
- **Trigger signals** — what to watch for (Roskomnadzor announcements, mass-block reports from SMMplanner-style canaries, Telegram throttling/error spikes in our metrics).
- **Severity tiers** — yellow (rumors), orange (partial blocking observed), red (channel access lost).
- **Pivot criteria** — quantitative thresholds for when to activate English-channel pivot (e.g., >20% drop in CIS subscriber DAU sustained 7 days).
- **English-channel pivot plan** — pre-built English-language voice defaults, GitHub global trending as source, US/EU dev Telegram channels for distribution.
- **Bot API failover** — alternative Telegram API endpoints, MTProto vs Bot API, fallback to email/RSS digest delivery if Telegram outbound dies entirely.
- **Drill cadence** — quarterly tabletop, annual live drill (red-day simulation).
- **Decision authority** — owner is sole decision-maker; no committee.

- [ ] **Step B3.2: Write `docs/risks.md`** — port the 5-row risk register from `_validation_summary.md` verbatim, add a "last reviewed" header for revisit cadence.

- [ ] **Step B3.3: Commit**

```bash
git add docs/playbooks/ docs/risks.md
git commit -m "docs: add crisis playbook (Telegram blocking) + risk register"
```

### Task B4: Push Phase-B PR

- [ ] **Step B4.1: Push branch + open PR**

Run:
```bash
git push -u origin docs/iter-27-phase-b-prd
gh pr create --title "docs(iter-27): Phase B — PRD + ADRs 0001-0006 + crisis playbook + risks" \
  --body "iter-27 Phase B. Locks owner's two MVP caveats (Telegram Stars + crisis playbook) into the repo."
```

- [ ] **Step B4.2: Watch CI, squash-merge when green.**

---

## Phase C — Smoke milestones (Days 4-5, ~8-12h)

### Task C1: `Source(Protocol)` + `Candidate(BaseModel)` + smoke GitHub poller

**Files:**
- Create: `~/telegram-tech-publisher/src/telegram_tech_publisher/sources/__init__.py`
- Create: `~/telegram-tech-publisher/src/telegram_tech_publisher/sources/base.py`
- Create: `~/telegram-tech-publisher/src/telegram_tech_publisher/sources/github_releases.py`
- Create: `~/telegram-tech-publisher/src/telegram_tech_publisher/config.py`
- Create: `~/telegram-tech-publisher/tests/__init__.py`
- Create: `~/telegram-tech-publisher/tests/unit/__init__.py`
- Create: `~/telegram-tech-publisher/tests/unit/conftest.py`
- Create: `~/telegram-tech-publisher/tests/unit/test_github_releases.py`
- Create: `~/telegram-tech-publisher/tests/unit/test_config.py`

- [ ] **Step C1.1: Write `config.py`** (pydantic-settings env loader)

```python
"""Env-backed settings loader."""
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    telegram_bot_token: str = Field(..., min_length=10)
    telegram_test_channel_id: str = Field(..., min_length=1)
    github_token: str = Field(..., min_length=10)
    database_url: str = "postgresql+asyncpg://localhost/telegram_tech_publisher"
    log_level: str = "INFO"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")
```

- [ ] **Step C1.2: Write `sources/base.py`**

```python
"""Source interface and Candidate shape."""
from datetime import datetime
from typing import Protocol

from pydantic import BaseModel, HttpUrl


class Candidate(BaseModel):
    source: str  # "github_releases" | "hn" | ...
    external_id: str  # source-native ID, used for de-dupe
    title: str
    body: str
    url: HttpUrl
    published_at: datetime


class Source(Protocol):
    name: str

    async def poll(self) -> list[Candidate]: ...
```

- [ ] **Step C1.3: Write failing test for GitHub poller** (TDD)

`tests/unit/test_github_releases.py`:
```python
"""GitHubReleasesSource: poll one repo's releases, return Candidates."""
import respx
from httpx import Response

from telegram_tech_publisher.sources.github_releases import GitHubReleasesSource


@respx.mock
async def test_poll_returns_candidates_for_repo() -> None:
    respx.get("https://api.github.com/repos/anthropics/anthropic-sdk-python/releases").mock(
        return_value=Response(
            200,
            json=[
                {
                    "id": 12345,
                    "name": "v0.42.0",
                    "body": "## What's Changed\n- Added X",
                    "html_url": "https://github.com/anthropics/anthropic-sdk-python/releases/tag/v0.42.0",
                    "published_at": "2026-05-22T10:00:00Z",
                },
            ],
        )
    )

    source = GitHubReleasesSource(
        repo="anthropics/anthropic-sdk-python",
        token="ghp_test",
    )
    candidates = await source.poll()

    assert len(candidates) == 1
    assert candidates[0].source == "github_releases"
    assert candidates[0].external_id == "12345"
    assert candidates[0].title == "v0.42.0"
    assert "Added X" in candidates[0].body
```

- [ ] **Step C1.4: Run failing test**

Run: `uv run pytest tests/unit/test_github_releases.py -v`
Expected: ImportError or AttributeError — module doesn't exist yet.

- [ ] **Step C1.5: Implement `sources/github_releases.py`**

```python
"""GitHub releases source: polls one repo's /releases endpoint."""
from datetime import datetime

import httpx

from telegram_tech_publisher.sources.base import Candidate


class GitHubReleasesSource:
    name = "github_releases"

    def __init__(self, repo: str, token: str) -> None:
        self._repo = repo
        self._token = token

    async def poll(self) -> list[Candidate]:
        url = f"https://api.github.com/repos/{self._repo}/releases"
        headers = {"Authorization": f"Bearer {self._token}", "Accept": "application/vnd.github+json"}
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers, timeout=15.0)
            response.raise_for_status()
        return [
            Candidate(
                source=self.name,
                external_id=str(release["id"]),
                title=release["name"] or release.get("tag_name", "unnamed"),
                body=release.get("body") or "",
                url=release["html_url"],
                published_at=datetime.fromisoformat(release["published_at"].replace("Z", "+00:00")),
            )
            for release in response.json()
        ]
```

- [ ] **Step C1.6: Run tests — expect green**

Run: `uv run pytest tests/unit/ -v`
Expected: all pass.

- [ ] **Step C1.7: Commit**

```bash
git checkout -b feat/iter-27-phase-c-smoke
git add src/telegram_tech_publisher/sources/ src/telegram_tech_publisher/config.py tests/
git commit -m "feat(sources): add GitHub releases poller (smoke) + Candidate shape"
```

### Task C2: Telegram Bot publisher smoke

**Files:**
- Create: `~/telegram-tech-publisher/src/telegram_tech_publisher/publishers/__init__.py`
- Create: `~/telegram-tech-publisher/src/telegram_tech_publisher/publishers/telegram.py`
- Create: `~/telegram-tech-publisher/tests/unit/test_telegram_publisher.py`

- [ ] **Step C2.1: Write failing test**

```python
"""TelegramPublisher: send_message hits Bot API with escaped MarkdownV2."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from telegram_tech_publisher.publishers.telegram import TelegramPublisher, escape_markdown_v2


def test_escape_markdown_v2_escapes_all_specials() -> None:
    # Telegram MarkdownV2 requires escaping: _ * [ ] ( ) ~ ` > # + - = | { } . !
    raw = "Hello *world*! (test) [link] _under_"
    escaped = escape_markdown_v2(raw)
    assert escaped == r"Hello \*world\*\! \(test\) \[link\] \_under\_"


@pytest.mark.asyncio
async def test_publisher_sends_to_configured_channel() -> None:
    fake_bot = MagicMock()
    fake_bot.send_message = AsyncMock(return_value=MagicMock(message_id=999))

    publisher = TelegramPublisher(bot=fake_bot, channel_id="@test_channel")
    msg_id = await publisher.send("iter-27 smoke")

    assert msg_id == 999
    fake_bot.send_message.assert_awaited_once_with(
        chat_id="@test_channel",
        text="iter\\-27 smoke",
        parse_mode="MarkdownV2",
    )
```

- [ ] **Step C2.2: Run failing test**

Run: `uv run pytest tests/unit/test_telegram_publisher.py -v`
Expected: ImportError.

- [ ] **Step C2.3: Implement `publishers/telegram.py`**

```python
"""Telegram Bot publisher (MarkdownV2)."""
import re

from telegram import Bot

_MD_V2_SPECIALS = re.compile(r"([_*\[\]()~`>#+\-=|{}.!])")


def escape_markdown_v2(text: str) -> str:
    return _MD_V2_SPECIALS.sub(r"\\\1", text)


class TelegramPublisher:
    def __init__(self, bot: Bot, channel_id: str) -> None:
        self._bot = bot
        self._channel_id = channel_id

    async def send(self, text: str) -> int:
        result = await self._bot.send_message(
            chat_id=self._channel_id,
            text=escape_markdown_v2(text),
            parse_mode="MarkdownV2",
        )
        return result.message_id
```

- [ ] **Step C2.4: Run tests — expect green**

Run: `uv run pytest tests/unit/ -v`
Expected: all pass.

- [ ] **Step C2.5: Commit**

```bash
git add src/telegram_tech_publisher/publishers/ tests/unit/test_telegram_publisher.py
git commit -m "feat(publishers): add Telegram Bot publisher (smoke) with MarkdownV2 escaping"
```

### Task C3: CLI wire-up — `smoke-github` and `smoke-telegram` sub-commands

**Files:**
- Create: `~/telegram-tech-publisher/src/telegram_tech_publisher/cli.py`

- [ ] **Step C3.1: Write `cli.py`**

```python
"""Click CLI for smoke commands."""
import asyncio

import click
from rich.console import Console
from telegram import Bot

from telegram_tech_publisher.config import Settings
from telegram_tech_publisher.publishers.telegram import TelegramPublisher
from telegram_tech_publisher.sources.github_releases import GitHubReleasesSource

console = Console()


@click.group()
def cli() -> None:
    """telegram-tech-publisher smoke commands."""


@cli.command("smoke-github")
@click.option("--repo", default="anthropics/anthropic-sdk-python", help="owner/repo to poll")
def smoke_github(repo: str) -> None:
    """Poll one repo's /releases and print candidates."""
    settings = Settings()
    source = GitHubReleasesSource(repo=repo, token=settings.github_token)
    candidates = asyncio.run(source.poll())
    console.print(f"[bold]{len(candidates)}[/bold] candidates from {repo}:")
    for c in candidates[:5]:
        console.print(f"  {c.published_at:%Y-%m-%d} [cyan]{c.title}[/cyan] → {c.url}")


@cli.command("smoke-telegram")
def smoke_telegram() -> None:
    """Send one hardcoded message to the test channel."""
    settings = Settings()
    bot = Bot(token=settings.telegram_bot_token)
    publisher = TelegramPublisher(bot=bot, channel_id=settings.telegram_test_channel_id)
    msg_id = asyncio.run(publisher.send("iter-27 smoke from telegram-tech-publisher"))
    console.print(f"[green]sent[/green] message_id={msg_id} to {settings.telegram_test_channel_id}")


if __name__ == "__main__":
    cli()
```

- [ ] **Step C3.2: Verify both smokes manually**

Pre-req: owner creates a Telegram bot via @BotFather + a private test channel, adds the bot as admin, populates `.env`.

Run:
```bash
make smoke-github
# expect: lists 5 most recent releases for anthropic-sdk-python
make smoke-telegram
# expect: "iter-27 smoke from telegram-tech-publisher" lands in the test channel
```

- [ ] **Step C3.3: Commit**

```bash
git add src/telegram_tech_publisher/cli.py
git commit -m "feat(cli): wire smoke-github + smoke-telegram CLI sub-commands"
```

### Task C4: Push Phase-C PR + verify CI green + smoke confirmation in PR body

- [ ] **Step C4.1: Push + open PR**

```bash
git push -u origin feat/iter-27-phase-c-smoke
gh pr create --title "feat(iter-27): Phase C — GitHub poll + Telegram publish smoke pipelines" \
  --body "$(cat <<'EOF'
## Summary
- `GitHubReleasesSource.poll()` returns `Candidate` instances for one hardcoded repo.
- `TelegramPublisher.send()` posts a hardcoded message to a test channel with MarkdownV2 escaping.
- Both wired via `make smoke-github` / `make smoke-telegram`.

## Smoke evidence (manual)
- [ ] `make smoke-github` lists 5 releases for `anthropics/anthropic-sdk-python`
- [ ] `make smoke-telegram` lands message in test channel (paste msg_id here)

## Test plan
- [ ] All unit tests green in CI
- [ ] Mypy/ruff/bandit green
- [ ] Diff-cover ≥80% (smoke modules are minimal — verify covered)
EOF
)"
```

- [ ] **Step C4.2: Watch CI, squash-merge when green + manual smokes confirmed**

---

## Phase D — Wire-back to ai_team (Day 6, ~2-4h)

### Task D1: Update ai_team CLAUDE.md with pointer to new repo

**Files:**
- Modify: `/Users/kirillterskih/ai_team/CLAUDE.md`

- [ ] **Step D1.1: Add to "Project" section**

After the "Current phase" paragraph, append:

> **iter-27 (2026-05-NN, bootstrap done)**: first commercial product `telegram-tech-publisher` lives in its own repo at `git@github.com:girlsmakemedrink/telegram-tech-publisher.git`. ai_team is on the bench for iter-27 (no `GitHubTargetRepo` integration yet — deferred to iter-28). iter-27 deliverables: PRD + 6 ADRs + crisis playbook + smoke pipelines (GitHub poll + Telegram publish).

- [ ] **Step D1.2: Add to "Where to look" section**

After the `docs/products/<slug>/` entry, append:

> **External product repos** (iter-27+): the actual product code lives outside `ai_team`. Per-product GitHub repos under `girlsmakemedrink/<slug>`. iter-27 = `girlsmakemedrink/telegram-tech-publisher`. ai_team holds the iter spec + handoff; the product repo holds PRD + ADRs + code.

### Task D2: Write iter-27 retro

**Files:**
- Create: `/Users/kirillterskih/ai_team/docs/iterations/iter_27_retro.md`

- [ ] **Step D2.1: Draft retro** with sections: "What went well", "What was harder than expected", "Lessons for iter-28", "Action items".

Specific items to capture:
- Whether the two-repo split friction was tolerable (e.g., bouncing between cwds, dual lint configs).
- Whether smoke pipelines surfaced real gaps in the QA risk register (e.g., MarkdownV2 escape edge cases not in `tech_risk.md`).
- Owner feedback on PRD scope.
- Whether `GitHubTargetRepo` deferral to iter-28 still feels right or should be moved earlier.

### Task D3: Write iter-27 handoff

**Files:**
- Create: `/Users/kirillterskih/ai_team/docs/iterations/iter_27_handoff.md`

- [ ] **Step D3.1: Draft handoff** following the iter_26_handoff.md template:
- Where we are at end of iter-27.
- iter-28 priorities ordered (top: `GitHubTargetRepo` impl OR first product feature — owner picks).
- Inherited decisions (don't contradict without revisiting).
- Ready-to-paste prompt for the new session.

### Task D4: Commit + PR (iter-27 wrap)

- [ ] **Step D4.1: Branch + commit + PR**

```bash
cd /Users/kirillterskih/ai_team
git checkout main && git pull --ff-only
git checkout -b docs/iter-27-wrap
git add CLAUDE.md docs/iterations/iter_27_retro.md docs/iterations/iter_27_handoff.md
git commit -m "docs(iter-27): wrap — CLAUDE.md pointer + retro + handoff"
git push -u origin docs/iter-27-wrap
gh pr create --title "docs(iter-27): wrap iter-27 — CLAUDE.md pointer + retro + handoff to iter-28" \
  --body "Closes iter-27. Product MVP scaffold landed in girlsmakemedrink/telegram-tech-publisher; handoff queues iter-28."
```

- [ ] **Step D4.2: Watch CI, squash-merge when green.**

---

## iter-27 Done Criteria

iter-27 is **done** when all of the following are true:

- [ ] `girlsmakemedrink/telegram-tech-publisher` exists as a public GitHub repo with CI passing on main.
- [ ] Repo has `pyproject.toml` + `uv.lock` + `.python-version` + `.env.example` + Makefile.
- [ ] `docs/PRD.md` exists, ≥250 lines, cites `_validation_summary.md` as source of truth.
- [ ] `docs/adr/0001-stack.md` through `docs/adr/0006-multi-tenancy.md` all exist.
- [ ] `docs/playbooks/crisis_telegram_blocking.md` exists with all 7 required sections.
- [ ] `docs/risks.md` exists with 5-row register from QA.
- [ ] `make smoke-github` lists releases for at least one repo.
- [ ] `make smoke-telegram` posts a message to the owner's test channel (msg_id recorded in Phase-C PR).
- [ ] CI green on every PR (lint + typecheck + bandit + pytest + commitlint).
- [ ] ai_team `CLAUDE.md` references the new repo.
- [ ] `iter_27_retro.md` + `iter_27_handoff.md` exist in ai_team.
- [ ] Owner has approved both the iter_27.md spec (this file) AND the iter-27 wrap PR.

---

## Cost / time estimate

- **Claude usage**: minimal — iter-27 is documentation + scaffold + boilerplate code. No LLM agents running. Estimate: <$1 of subscription quota for occasional `claude -p` reasoning during PR review.
- **Wall-clock**: ~5-6 dev days (Day 1 scaffold, Days 2-3 docs, Days 4-5 smoke + manual verify, Day 6 wrap).
- **Owner manual actions required**: (a) one-time Telegram bot creation via @BotFather + test-channel setup (~10 min); (b) PR reviews (~30 min total across 4 PRs); (c) final approval of wrap PR.

---

## Risks specific to iter-27 execution

1. **Two-repo cwd confusion** — easy to commit to the wrong repo. Mitigation: every Bash command in this plan uses absolute paths or explicit `cd`.
2. **`.env` accidentally committed** — `.gitignore` covers `.env*` with explicit `.env.example` allowlist; pre-commit also blocks. Verify in step A3.1.
3. **Telegram bot token leaked in commit message or test** — never paste real token; use `<paste-from-BotFather>` placeholders in `.env.example`; tests use `"test_token"` literals.
4. **Smoke message spammed to wrong channel** — `smoke-telegram` reads `TELEGRAM_TEST_CHANNEL_ID` strictly from env (no CLI override) so a misconfigured `.env` is the only way to mis-route; documented in `.env.example`.
5. **CI red because `uv` action version drift** — pin `astral-sh/setup-uv@v3` (not `@latest`).
6. **Spec drift from `_validation_summary.md`** — PRD step B1 explicitly cites the validation summary verbatim for MVP scope; any divergence is intentional and called out in the ADR rationale.

---

## What iter-27 explicitly does NOT do (re-stated for clarity)

- No `GitHubTargetRepo` implementation in `ai_team/core/target_repo/`.
- No ai_team agent invocations against the new repo.
- No LLM drafting code.
- No scheduler, no payments, no multi-tenant.
- No production deployment.
- No iter-26b carry-overs (HoldQueue persistence, BaseAgent refactor, etc.) — all deferred.

---

## Approval ask

Owner approves this spec by responding "approved" (or with redlines). Once approved, I:
1. Open PR for this iter_27.md doc on `docs/iter-27-plan` branch.
2. Merge once CI green.
3. Begin Phase A immediately (no further approval needed for individual phases).
4. Surface for approval again at iter-27 wrap (Phase D PR), where the owner reviews retro + handoff before merge.
