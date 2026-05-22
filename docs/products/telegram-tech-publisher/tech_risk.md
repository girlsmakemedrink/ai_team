# Tech-risk register: telegram-tech-publisher

- Verdict: **feasible_with_caveats**
- Build window: **8-12 weeks**
- Risks found: **7**

## Summary

Architecture is boring and well-scoped: Python service polls four source classes (GitHub, RSS, HN, X), runs a Haiku-tier relevance filter, drafts in the creator's voice with Sonnet 4.6 + 10-20-example few-shot, formats for Telegram MarkdownV2 with Telegra.ph fallback for long-reads, and schedules via Telegram Bot API. Telegram rate limits (1/s per chat, 30/s across chats) are non-binding for publishers shipping 3-5 posts/day per channel. LLM opex projects at ~$0.25-0.30/user/day at all three scale tiers — well under the $3/user/day ceiling and invariant to user count (prompt caching on shared source digests trims it modestly at 10k users). Two caveats drive the 'feasible_with_caveats' verdict. (1) X/Twitter source is the dominant risk: scraping violates TOS and the API v2 Basic tier ($100/mo, 10k reads/mo) caps support around 50-100 users — descope X from MVP and bridge via rss.app or community-submitted links; revisit at >3k paid users when the $5k/mo Pro tier becomes affordable. (2) CIS payment processing is non-trivial because Stripe is blocked in RU/BY — pick one of Telegram Stars (zero-friction, 50% cut), YooKassa (requires RU legal entity), or CryptoPay (USDT, no KYC, niche audience). Owner is a solo dev with native Russian + CIS Telegram-channel distribution assets, which neutralizes the GTM risk that would normally make a 12-week solo build infeasible. Build window of 8-12 weeks is tight but achievable if X is scoped out of MVP and payment integration uses one rail rather than two. Voice-tone calibration via few-shot is reliable enough for v1; embeddings/fine-tune are premature. Recommend proceeding with the caveats above explicitly tracked.

## Top risk

X/Twitter source ingestion is the dominant technical risk: scraping violates X's TOS and is aggressively enforced post-2023, while the API v2 Basic tier ($100/mo, 10k reads/mo) only supports ~50–100 active users before forcing a jump to Pro ($5000/mo) — recommend descoping X from MVP and bridging via rss.app or community-submitted links.

## Components

| Name | Complexity (1-5) | Dependency | Scaling limit | Gotchas |
|---|---|---|---|---|
| Telegram Bot publisher (MarkdownV2 + Telegra.ph fallback) | 2 | Telegram Bot API | 1 msg/s per chat, 30/s across chats, 20 msg/min to same group — non-binding for 3-5 posts/day per channel | MarkdownV2 escape rules (every special char) — needs robust escaper + dry-run preview; 4096-char message cap forces Telegra.ph link for long-form code walkthroughs; File caption hard-limited to 1024 chars |
| GitHub source monitor (stars/releases/commits) | 2 | GitHub REST/GraphQL API | 5000 req/hr per authenticated token; one shared token won't survive past ~50 active users polling 5 repos each | Per-user OAuth or GitHub App install needed at scale to multiply rate budget; Release-feed polling vs webhook subscriptions — webhooks better but require public HTTPS endpoint; Star events firehose noisy on popular repos |
| RSS source monitor | 1 | feedparser + readability libs (no API) | Per-host politeness only; effectively unbounded | CIS feeds frequently Win1251 / KOI8-R not UTF-8 — needs charset sniffing; Broken feeds (malformed XML) must not crash the pipeline; Same item republished by multiple aggregators — dedupe on URL+title hash |
| Hacker News source monitor | 1 | HN Firebase API (free, no key) | No documented limit; ~10 req/s is safe | Item firehose is huge — needs score/keyword/topic filter via LLM; topstories vs newstories lag — pick based on creator's niche; Comments often more valuable than submissions for niche channels |
| X/Twitter source monitor | 5 | X API v2 (Basic $100/mo OR Pro $5000/mo) — scraping forbidden by TOS | Basic: 10k tweet-reads/mo, 100 req/15min — supports ~50-100 active users; Pro: 1M reads/mo at $5k/mo, only justifiable above ~3000 paying users | Post-2023 enforcement is aggressive — scraping = account bans + legal exposure; Third-party aggregators (rss.app, Nitter mirrors) are flaky and themselves walk the TOS line; Recommend descoping X from MVP; add rss.app bridge or community-submitted-link fallback |
| LLM voice-tone drafting (Sonnet 4.6, few-shot) | 3 | Anthropic API (Claude Sonnet 4.6) | Anthropic-tier rate limit; prompt-cache TTL 5 min — caches creator's voice examples across same-day calls | Onboard requires 10-20 user-labeled past posts to anchor voice — UX friction; Voice drift on novel topics user hasn't covered before → needs 'retune from last N posts' admin command; Fine-tune unavailable at our API tier; embeddings-retrieval is overengineering for 5 posts/day |
| LLM relevance filter (Haiku 4.5) | 2 | Anthropic API (Claude Haiku 4.5) | Cheap classifier — ~50-100 candidates/day per user → 50k input + 2.5k output tokens | Batch all candidates into one call + prompt-cache the user's interest taxonomy to cut cost ~70%; Cold-start: no past examples means filter is noisy for first week; Owner needs to surface 'why was this skipped' to build user trust |
| Telegra.ph long-form publisher | 1 | Telegra.ph API (free, anonymous) | No documented limit; ~1 req/s is safe per community reports | Anonymous tokens must be persisted server-side — losing them = orphaned pages; No edit-after-publish for anon accounts (only for token-bound accounts); Images must be re-hosted (no hotlinking from arbitrary domains) |
| Post scheduler / queue | 2 | APScheduler or Postgres-as-queue + cron worker | Bound by Postgres + worker count — trivial up to ~10k scheduled jobs/day | Per-user timezone handling (CIS spans 11 zones; default Europe/Moscow is wrong for half the market); Retry-on-fail with exponential backoff for transient Telegram 5xx; Idempotency: never double-post if worker restarts mid-send |
| Payment / subscription (CIS-aware) | 4 | Telegram Stars (50% Telegram cut) OR YooKassa (RUB) OR CryptoPay (USDT) | YooKassa requires RU legal entity (IP or OOO) for onboarding; Stars no KYC but punitive fee | Stripe blocked in RU/BY — cannot be the default for owner's CIS GTM motion; Telegram Stars zero-friction inside Telegram UX but cedes 50% of gross to Telegram — viable only at low ARPU; Recurring billing in Telegram needs your own state machine + monthly invoice re-issuance; no native subscriptions |
| Telegram webhook receiver | 1 | Telegram Bot API setWebhook | n/a — bot is outbound-dominant (publisher), incoming traffic is just admin commands | Requires public HTTPS endpoint with valid cert — free via Caddy/Let's Encrypt but small ops burden; Long-polling fallback fine for local dev but burns a worker; Self-signed certs supported but discouraged |
| Per-tenant state DB (Postgres) | 2 | Postgres 15 | Standard Postgres scaling; ~10k users → ~1 GB w/ voice samples and 6mo of post history | Encrypt OAuth tokens (GitHub, X) at rest — they're long-lived bearer credentials; Voice-sample storage 10-50 KB/user — small, but back it up; Source-config JSON schema needs versioning for migrations |

## LLM opex at scale

- 100 users:    $0.30 / user / day
- 1000 users:   $0.28 / user / day
- 10000 users:  $0.25 / user / day
