# Iteration 27 retro

> Read **after** `CLAUDE.md`, `docs/iterations/iter_27.md`, and
> `docs/products/telegram-tech-publisher/_validation_summary.md`.

## Outcome (2026-05-22 EOD)

iter-27 shipped per spec. The new `girlsmakemedrink/telegram-tech-publisher`
repo exists, is public, has CI green on `main`, and both smoke pipelines
(`make smoke-github`, `make smoke-telegram`) have been exercised end-to-end
against real services:

- `smoke-github` pulled 5 real releases from `anthropics/anthropic-sdk-python`.
- `smoke-telegram` published `message_id=3` to the owner's test channel
  `-1003629093519` using the live `@BotFather`-issued bot.

Three PRs landed in 3 sittings on 2026-05-22:

| PR  | Phase | Squash SHA  | What                                            |
|-----|-------|-------------|-------------------------------------------------|
| #1  | A     | `d6cc36f`   | Scaffold (uv + ruff/mypy/bandit + CI + Makefile)|
| #2  | B     | `5fdb821`   | PRD + ADRs 0001-0006 + crisis playbook + risks  |
| #3  | C     | `6caa94d`   | Smoke pipelines (GitHub poll + Telegram publish)|

This wrap-up PR closes iter-27 by adding the CLAUDE.md pointer, this retro,
and the handoff to iter-28.

## What went well

- **Plan-before-code paid off again.** The iter_27.md plan was detailed
  enough that all three product-repo PRs went red→green→commit without
  any in-flight scope decisions. No mid-PR design conversations needed.
- **Boring-stack reuse was zero-friction.** Cloning the ai_team
  `pyproject.toml` shape + ruff/mypy/bandit config into the new repo took
  minutes. ADR-001 ("boring stack") continues to compound: no time spent
  picking tools.
- **TDD discipline at smoke scope worked.** Each of the 5 unit test files
  in PR #3 was written red-first before its implementation. Coverage
  ended at ≥80% with the gate enforced in CI — no after-the-fact test
  scramble.
- **MarkdownV2 escape was caught at unit-test time, not at the live
  smoke.** `_*[]()~\`>#+-=|{}.!` are all special. The 4 escape edge-case
  tests in `test_telegram_publisher.py` would have surfaced the issue
  even without a real channel — the live smoke just confirmed it.
- **Crisis playbook landed alongside scaffold, per owner caveat #2.** Not
  punted to iter-28 "when we have time" — written in Phase B with all 7
  required sections.
- **GitHub branch protection + `wagoid/commitlint-github-action@v6` worked
  out of the box** once the config format was right (see "harder than
  expected" #1 below).

## What was harder than expected

- **commitlint config-file extension.** `wagoid/commitlint-github-action@v6`
  rejects `.js` and demands `.mjs` or `.cjs` (or no extension); the
  ai_team repo uses `.js` via pre-commit only. Lost ~10 min on PR #1 CI
  before porting ai_team's working `.commitlintrc.yml` (YAML) instead.
  Lesson: **don't blindly copy `commitlint.config.js` between repos** —
  the GitHub Action and the local pre-commit hook accept different
  config formats. YAML works for both.
- **Local main divergence after accidental local commit.** Phase A's
  first commit landed on local `main` before I had branched. The
  auto-classifier (correctly) blocked `git reset --hard origin/main`.
  Recovered by branching `chore/iter-27-phase-a-scaffold` from current
  HEAD and pushing only the feature branch; local `main` stayed
  diverged but harmless (never pushed). Lesson: **branch BEFORE the
  first commit on a fresh-cloned repo**, even when it feels obvious
  that branching can wait.
- **Two-repo cwd friction was real but tolerable.** Most of iter-27 was
  spent in `~/telegram-tech-publisher/`; only Phase D returns to
  `~/ai_team/`. Risk of editing the wrong repo was mitigated by always
  using absolute paths in Bash commands (per the plan's #1 risk). No
  cross-repo mistakes happened, but the cognitive overhead of "which
  repo am I in?" was a steady tax on attention.
- **Coverage dipped to 76% after `sources/` landed.** `config.py` was
  the gap (loaded but not tested). Added a 2-test
  `tests/unit/test_config.py` and coverage went back to 100%. Lesson:
  **add the env-loader test in the same PR as the first code that
  uses it**, not "later."
- **`.env` setup landed on the owner, then bounced back to me.** The
  plan assumed the owner would do the `@BotFather` dance and the
  `.env` write. They asked me to handle it instead (provided real
  token + channel ID in chat). Worked, but the token is now in
  conversation logs — see Action items.

## Lessons for iter-28

- **The `GitHubTargetRepo` deferral was the right call.** After living
  in the new repo for one iteration, the abstraction shape is clearer:
  it needs to encode "two-repo handoff between spec (ai_team) and code
  (product)" — not just GitHub API access. iter-28 should design it
  against the actual iter-27 workflow, not against a guess.
- **Per-product repo READMEs need a "Run smoke locally" section.** The
  owner had to ask "what do I do with the bot token?" — the README
  didn't tell them. Add a `## Smoke pipelines` section to the product
  README in iter-28 that walks through `.env` setup + `make smoke-*`.
- **Smoke pipelines surfaced no risks that QA didn't already flag.**
  The `tech_risk.md` already noted MarkdownV2 escape complexity and
  Bot API rate limits; both held up under live testing. QA's
  per-candidate diligence is a real signal, not just paperwork.
- **CI matrix is one-OS one-Python for now.** This is fine for MVP. When
  iter-30+ adds payments + multi-tenant, revisit whether we need
  Python 3.12 + Linux/macOS parity. Don't add it speculatively.
- **PRD scope landed correctly per owner.** Five tiers + Stars-first +
  YooKassa-parallel was approved without redlines. Pattern: when
  the spec is direct quotes from the validation summary, owner
  approval is fast.

## Action items (carry into iter-28 unless flagged)

| #   | Item                                                                  | Priority | Owner   |
|-----|-----------------------------------------------------------------------|----------|---------|
| 1   | Rotate `TELEGRAM_BOT_TOKEN` (shared in chat during smoke setup)       | P1       | owner   |
| 2   | Add "Run smoke locally" section to `telegram-tech-publisher/README.md`| P2       | claude  |
| 3   | Decide iter-28 top item: `GitHubTargetRepo` impl vs first MVP feature | P1       | owner   |
| 4   | Add `make smoke-llm` equivalent to product repo once LLM drafting     | P3       | iter-28 |
|     | lands (mirror ai_team's substrate-validation pattern)                 |          |         |
| 5   | Backport "branch before first commit" reminder to ai_team CLAUDE.md   | P3       | claude  |
|     | "Operating principles" section if it happens again                    |          |         |

Action item #1 (token rotation) is the only operationally urgent one.
The token is in `~/telegram-tech-publisher/.env` (gitignored, not
pushed) and in this conversation transcript, but the GitHub side is
clean. `@BotFather` → `/revoke` is ~30s.

## What iter-27 specifically did NOT do

Re-stated for handoff clarity (all per the iter_27.md non-goals list):

- No LLM voice drafting code (Sonnet few-shot) — iter-28.
- No multi-source aggregation beyond GitHub releases — iter-28.
- No scheduler / queue / publish-cadence engine — iter-28.
- No user onboarding flow — iter-29.
- No payment integration — iter-30.
- No multi-tenant Postgres partitioning — iter-30.
- No `GitHubTargetRepo` impl in `ai_team/core/target_repo/` — iter-28
  carry-over.
- No ai_team agent invocations against the new repo. iter-27 was
  Claude-Code-as-dev driving local tools.
- No production deployment — iter-31+.

## Inherited decisions (do not contradict without revisiting)

All iter-19..26b decisions hold. New iter-27 decisions, all owner-approved:

- **Two-repo split locked.** ai_team holds iter specs + retros + handoffs;
  product code lives in `girlsmakemedrink/<slug>`.
- **Telegram Stars primary, YooKassa parallel post-MVP track** — per
  ADR-0003 in the product repo + owner caveat #1.
- **Pre-built developer-channel voice templates over per-user
  embeddings** — per ADR-0004; embedding retrieval rejected as
  overengineering for MVP.
- **Postgres-as-queue + APScheduler over Redis Streams in the product
  repo** — per ADR-0005. Different from ai_team's Redis-based bus
  because the product has different load characteristics (low-rate
  scheduled publishes, not high-rate agent messages).
- **Row-level multi-tenancy on `user_id`, encrypted GitHub PATs at
  rest** — per ADR-0006. Single Postgres, not per-tenant DB.
- **80% coverage gate + ruff strict + mypy strict + bandit high-only +
  squash-merge only + commitlint** — same conventions as ai_team.
- **`GitHubTargetRepo` carry-over stays deferred to iter-28** — confirmed
  by lived experience in iter-27 (the abstraction needs to encode
  spec/code handoff, not just API access; we now have data to design
  against).
