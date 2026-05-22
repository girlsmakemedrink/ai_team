# Iteration 27 handoff

> Read **after** `CLAUDE.md`, `docs/iterations/iter_27.md`, and
> `docs/iterations/iter_27_retro.md`.

## Where we are (2026-05-22 EOD, iter-27 merged)

🚢 **First commercial product is bootstrapped.** The new repo at
`git@github.com:girlsmakemedrink/telegram-tech-publisher.git` is public,
CI-green on `main`, and has both ends of the eventual data flow proven
end-to-end with hardcoded inputs:

- `make smoke-github` polls GitHub releases for one repo and emits
  `Candidate` shapes (`anthropics/anthropic-sdk-python`, 5 releases).
- `make smoke-telegram` publishes one MarkdownV2-escaped message to
  the owner's test channel (`-1003629093519`, `message_id=3`).

🏗️ **Scaffold is identical-stack to ai_team.** Python 3.11 + uv (lockfile
committed) + ruff strict + mypy strict + bandit high-only + pytest with
≥80% coverage gate + commitlint + squash-merge-only branch protection.

📐 **iter-27 was Claude-Code-as-dev, not ai_team-agents-as-dev.** No agent
chains ran. The new repo has zero coupling to `ai_team/core/target_repo/`
yet — `GitHubTargetRepo` deferral was intentional and is now justified by
lived experience (see retro "Lessons for iter-28").

📚 **Doc footprint in the product repo:**
- `docs/PRD.md` (131 lines) — MVP scope, 5-tier pricing, success metrics.
- `docs/adr/0001-stack.md` … `0006-multi-tenancy.md` (333 lines total).
- `docs/playbooks/crisis_telegram_blocking.md` (114 lines, all 7 sections).
- `docs/risks.md` (5-row register carried from QA's iter-26b diligence).

## iter-28 priorities (in order)

### 1. (STRATEGIC TOP) Owner picks: `GitHubTargetRepo` impl vs first MVP feature

This is the iter-28 fork. Both are reasonable; pick one before opening
iter_28.md.

- **(a) Build `GitHubTargetRepo` in `ai_team/core/target_repo/`** —
  close the iter-26 carry-over. Lets ai_team agents (TL, Architect,
  Backend, QA) operate on the external product repo via the same
  abstraction they use for self-bootstrap. After iter-27 lived
  experience, the abstraction needs to encode "two-repo handoff
  between spec (ai_team) and code (product)" — not just GitHub API
  access. This is the unblocker for "agents build product features."
- **(b) Build the first real product feature directly in
  `telegram-tech-publisher`** — LLM voice drafting (Sonnet 4.6
  few-shot, per product ADR-0004). Claude-Code-as-dev pattern
  continues; ai_team stays on the bench until iter-29+. Faster
  product feedback, but ai_team is idle.

iter-27 retro recommends **(a)**, because the longer ai_team sits
unused, the more it accumulates drift risk and the longer it takes to
remember how it works. Owner picks in the first iter-28 task.

### 2. (P1 — operational, time-sensitive) Rotate `TELEGRAM_BOT_TOKEN`

The token shipped to the owner via @BotFather (`8910693426:AAHA…`) was
shared in the iter-27 conversation transcript during smoke setup. It
sits in `~/telegram-tech-publisher/.env` (gitignored, never pushed) but
chat logs are not a credential vault. `@BotFather` → `/revoke` → paste
new token into `.env`. ~30s. Should happen before iter-28 starts.

### 3. (P2) Add "Run smoke locally" section to product README

The owner had to ask "what do I do with this bot token?" — the README
didn't say. Add a `## Smoke pipelines` section walking through `.env`
setup + `make smoke-github` + `make smoke-telegram`. Cheap (~30 min);
unblocks any future contributor (or future-Claude) doing the same
ramp.

### 4. (P3) Backport "branch BEFORE first commit on a fresh repo" to CLAUDE.md

iter-27 Phase A committed scaffold to local `main` accidentally before
branching. Recovered cleanly but the auto-classifier (correctly)
blocked the `git reset --hard` shortcut. If this happens again to
future-Claude in a fresh repo, save them the recovery time by adding
a one-liner to CLAUDE.md "Operating principles":

> When working in a freshly-cloned repo, branch BEFORE the first
> commit. Default to a feature branch even when "I'll branch after
> this commit" feels obvious — local-main divergence is harder to
> undo than to prevent.

### 5. (Carry-overs ≥5, unchanged from iter-26)

All still pending. None blocked iter-27.

- HoldQueue persistence (Postgres).
- `pytest-rerunfailures` plugin pin.
- TL auto-hop investigation.
- `audit_writer` restricted Postgres role.
- Hash-chain alert job.
- `GitHubTargetRepo` implementation. ← would land in iter-28 if owner picks (a).
- TL decomposition transactional insert.
- `BaseAgent.handle()` template-method refactor.
- `mark_task_done` / `update_task_status` real impls.
- Substrate-level `--allowed-tools ""` fix.

## Hard constraints (unchanged from iter-26)

All iter-4..26b constraints hold. iter-27 added no new architectural
constraints on `ai_team` — all new architecture lives in the product repo
under `docs/adr/0001-0006`.

**iter-27 lesson added (per iter-28 #4 above)**: branch before the
first commit on a fresh-cloned repo.

## What iter-27 specifically did NOT do

See `iter_27_retro.md` "What iter-27 specifically did NOT do" for the
full list. Headlines:

- No LLM drafting, no scheduler, no payments, no multi-tenant code.
- No `GitHubTargetRepo` impl (carry-over → iter-28 if owner picks (a)).
- No ai_team agent invocations against the new repo.
- No production deployment.
- No iter-26b carry-overs closed.

## Inherited decisions (do not contradict without revisiting)

All iter-19..26b decisions hold. New iter-27 decisions, all owner-approved:

- **Two-repo split locked.** ai_team holds iter specs + retros + handoffs;
  product code lives in `girlsmakemedrink/<slug>`. iter-27 =
  `telegram-tech-publisher`.
- **Telegram Stars primary, YooKassa post-MVP parallel track** — per
  product ADR-0003 + owner caveat #1. CryptoPay rejected.
- **Pre-built developer-channel voice templates over per-user
  embeddings** — per product ADR-0004. Embedding retrieval rejected
  as overengineering for MVP.
- **Postgres-as-queue + APScheduler in the product repo** — per
  product ADR-0005. Different choice than ai_team's Redis bus
  because product load is low-rate scheduled publishes, not
  high-rate agent messages.
- **Row-level multi-tenancy on `user_id` in a single Postgres,
  encrypted GitHub PATs at rest** — per product ADR-0006.
- **80% coverage gate + ruff strict + mypy strict + bandit high-only
  + squash-merge only + commitlint** — same conventions as ai_team.
- **`GitHubTargetRepo` carry-over stays deferred until owner picks
  iter-28 direction** — confirmed by iter-27 lived experience.

## Ready-to-paste prompt for the new session

```
Starting Iteration 28 on the ai_team project.

First, read these in this order:

1. CLAUDE.md (note iter-27 paragraph + External-product-repos block)
2. docs/iterations/iter_27.md (the bootstrap spec)
3. docs/iterations/iter_27_retro.md (what happened + lessons)
4. docs/iterations/iter_27_handoff.md (this file — iter-28 priorities)

iter-28 priorities (in order):

1. (STRATEGIC TOP) Owner picks the iter-28 direction:
   (a) build `GitHubTargetRepo` in ai_team/core/target_repo/ so
       agents can operate on the new product repo, OR
   (b) build the first real product feature (LLM voice drafter)
       directly in girlsmakemedrink/telegram-tech-publisher,
       continuing the Claude-Code-as-dev pattern from iter-27.
   iter-27 retro recommends (a). Draft iter_28.md based on the
   pick.

2. (P1, operational) Confirm owner has rotated TELEGRAM_BOT_TOKEN
   from iter-27 (was shared in chat during smoke setup). If not,
   prompt them to /revoke via @BotFather before iter-28 work
   touches the product repo.

3. (P2) Add "Run smoke locally" section to the
   telegram-tech-publisher README (helps any future contributor
   ramp on .env + make smoke-*).

4. (P3) Backport "branch BEFORE first commit on fresh repo" to
   ai_team CLAUDE.md "Operating principles".

5. (Carry-overs ≥5, unchanged) — see iter_27_handoff.md.

Workflow: plan-before-code. Draft docs/iterations/iter_28.md AFTER
the strategic decision in #1. Surface the plan, then code.
Run validation + PR merges yourself.

Constraints unchanged from iter-26b — see CLAUDE.md gotchas + the
"Hard constraints" section of iter_27_handoff.md.

When ready, create the iter-28 task list and surface the
strategic decision first.
```
