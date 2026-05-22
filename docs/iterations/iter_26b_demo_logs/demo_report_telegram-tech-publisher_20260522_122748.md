# iter-26b demo report — 20260522_122748

- slug: telegram-tech-publisher
- depth: standard
- correlation_id: 0889e923-bbb8-4870-a720-d9afe8046b09

## Per-message audit

 id | sender | recipient | message_type | model | tokens_in | tokens_out | cached_input | cost_cents | duration_ms 
----+--------+-----------+--------------+-------+-----------+------------+--------------+------------+-------------
(0 rows)


## docs/products/telegram-tech-publisher/competitors.md

# Competitor scan: telegram-tech-publisher

- Competitors found: **15**
- Pain signals found: **7**
- Verdict: **underserved**

## Summary

The competitive landscape for telegram-tech-publisher is structurally underserved: zero competitors combine Telegram publishing, code-aware AI drafting, and developer-source curation for the developer-influencer buyer. The market fractures across three failure modes. First, the entire Western scheduler category (Buffer, Hootsuite, Typefully, SocialBee, Hypefury — 6 competitors) has zero Telegram support, confirmed on feature pages; they optimize for ad-platform APIs and have no incentive to build Telegram integrations. Second, global tools that do support Telegram (PostSyncer at $29–99/month, Postly at $16+/month, Social Champ) use generic AI that produces marketing captions and hashtags — not technically accurate developer posts with code blocks, benchmark comparisons, or library release notes. Postly is the closest competitor, with the most Telegram-native feature set (silent posts, inline buttons, spoiler media), yet its AI output is indistinguishable from an Instagram caption generator. Third, CIS/Russian tools (SMMplanner at 660–2250₽/month, SmmBox at 350–2380₽/month, PostMyPost) cover Telegram plus ChatGPT-powered AI, but target SMM agency workflows for brand accounts, not developer-influencer channels — and SMMplanner's own blog published guidance on abandoning Telegram post-blocking in March 2026, signaling strategic retreat. The Telegram-native scheduling tool (Telepost.me) is free, widely adopted, and has no monetization or AI layer — a signal that the scheduling wedge is proven but the value capture is entirely open. No competitor monitors GitHub releases, Hacker News, or RSS feeds as source curation for content ideas. Verdict: underserved — at most 1 competitor (Postly) partially overlaps on Telegram delivery, and 0 competitors address the developer-voice AI drafting or source-monitoring requirements.

## Distribution feasibility

- **Channel estimate**: ~250–400 CIS developer Telegram channels with 5k+ subscribers across Python, DevOps, AI/ML, backend, and security niches. No Western competitor has meaningful presence or awareness in this ecosystem.
- **Audience reach estimate**: 8–15M total subscriptions (3–5M unique developers due to heavy overlap). Organic distribution via a single well-placed post in a 50k-sub dev channel reaches the exact buyer persona at zero cost — owner's existing CIS network makes this the primary acquisition channel.
- **Conversion-to-paid estimate**: 0.3–1.0% conversion to paid ($20–35/month) is realistic given direct pain-to-product fit for channel owners. Channel operator cohort (250–400 channels × 2–3 paying admins) implies a 750–1,200 subscriber launch ceiling before expanding to global dev channels.

### Notes

The owner's Russian-native background and existing CIS dev channel relationships constitute an unfair GTM advantage that no competitor can replicate. CIS SMM tools (SMMplanner, SmmBox) do not serve developer influencers — they serve brand managers. Western tools ignore Telegram entirely. The primary distribution risk is if Telegram faces another major CIS blocking event (SMMplanner wrote about this in March 2026), which would compress the TAM window.

## docs/products/telegram-tech-publisher/tech_risk.md

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

## docs/products/telegram-tech-publisher/revenue.md

# Revenue model: telegram-tech-publisher

- Verdict: **viable_with_caveats**
- Break-even users: **324**
- Time to first revenue: **14 weeks**
- Time to $1k MRR: **26 weeks**

## Summary

Pricing tiers $0/$15/$29/$59 with 69–70% gross margins, ARPU $24.30, LTV ~$405, CAC $0. Time to first revenue ~14 weeks (within 24-week / 6-month constraint). Month-6 MRR base case $1,166 (~48 paid users). Break-even at ~324 paid users — exceeds the 200-user threshold for a clean "viable" verdict, hence viable_with_caveats. The 324-user milestone requires 12–18 months of organic growth post-launch at 3–5 new paid users/week; owner must treat this as an asset-building phase rather than near-term income replacement. On infrastructure opex alone (excluding owner cost-of-time), break-even is only ~10 users. Gross margins are healthy because LLM opex is tightly capped per tier ($0.15–$0.60/day) via Haiku 4.5 for drafts + prompt caching, well under the $3/day ceiling. The $0 CAC via owner's CIS Telegram distribution is a genuine moat: no US-based competitor can replicate the in-community trust. Primary churn risks are draft quality falling below manual bar and CIS payment-rail friction (Stripe + Paddle fallback recommended). The slope is good — $1k MRR likely at month 5–6 post-launch — but break-even on full owner time requires patience beyond the 6-month window.

## Buyer persona

Russian-speaking backend/DevOps/AI engineer running a Telegram dev channel as a side project. Channel size 500–50k subs (sweet spot 2k–20k). Income $40k–100k USD/yr from primary job; earns $0–500/mo from channel sponsorships. Currently pays for Notion ($8/mo) but nothing purpose-built for publishing. Spends 30–60 min/day sourcing, rewriting, and formatting posts — the core pain. WTP signal: Taplio (LinkedIn creator AI analogue) retains at $39/mo; CIS buyers accept USD pricing when value is demonstrably time-saving.

## Addressable population

CIS developer Telegram channels 500+ subs: ~3,000–6,000. Global English dev channels 500–100k subs: ~5,000–10,000. Total TAM: 8,000–16,000 channels. Active creators posting ≥3×/week: ~20% = 1,600–3,200. Payment-willing subset (earns from channel or values 30 min/day): ~30% of ICP = 500–950 users. Year-1 SAM ~700 users at realistic penetration.

## Pricing tiers

| Tier | $/month | Target user |
|---|---|---|
| Free | $0 | Hobbyist / acquisition funnel — 1 draft/day, 1 source. Converts to Starter after first week of daily use. |
| Starter | $15 | Solo creator with small channel <2k subs, CIS-anchored price point. 3 drafts/day, 3 sources. Anchored below Typefully Pro ($12.50) and Buffer ($18). |
| Pro | $29 | Serious creator 2k–50k subs who earns sponsorships. 5 drafts/day, 10 sources, voice-tuning runs. Anchored at Hypefury mid-tier. |
| Studio | $59 | High-volume creator or agency managing multiple channels. 10 drafts/day, unlimited sources, multi-channel. Anchored below Taplio Pro ($39 comparable, Studio is differentiated by Telegram+code niche). |

## Unit economics

- CAC envelope: **$0** / user
- LTV envelope: **$405** / user

## Revenue forecast (month 6)

- Conservative: $730 MRR
- Base:         $1166 MRR
- Optimistic:   $2041 MRR

## docs/products/telegram-tech-publisher/_validation_summary.md

---
slug: telegram-tech-publisher
recommendation: go_with_caveats
confidence: 4
build_window: 8-12 weeks
fatal_flaws_count: 0
---

# Validation summary: telegram-tech-publisher

## Recommendation

**go_with_caveats** (confidence 4/5)

## Summary

Three upstream diligence agents converge on go_with_caveats. The market is structurally underserved — zero competitors combine Telegram publishing, code-aware AI drafting, and developer-source curation for the developer-influencer buyer. Architecture is boring-good: Python poller + Haiku relevance filter + Sonnet voice drafter + Telegram Bot API publisher, 8-12 week solo build window with X descoped from MVP. Unit economics are healthy: 69-70% gross margin, $0 CAC via owner's CIS dev-channel network, LTV ~$405. The two cross-cutting caveats are: (1) CIS payment complexity — Stripe is blocked in RU/BY, so MVP must commit to one rail (Telegram Stars at 50% cut, or YooKassa requiring a legal entity); (2) the distribution moat and the product's delivery mechanism both depend on Telegram remaining unblocked in RU/BY — a single-point-of-failure risk that neither Architect nor PM modeled explicitly in their forecasts, making it the top emergent cross-agent risk. Break-even at 324 paid users requires 12-18 months of organic growth post-launch, sustainable only if treated as asset-building. Proceed with X descoped, one payment rail committed upfront, and a Telegram-blocking crisis playbook drafted before launch.

## Risk register

| # | Risk | Severity (1-5) | Mitigation |
|---|---|---|---|
| 1 | CIS Telegram blocking event | 4 | Build parallel English-language global dev channel track from day one; monitor blocking signals; draft a Bot API failover/geo-pivot playbook. SMMplanner's March 2026 retreat is the canary. Neither Architect nor PM modeled this scenario in their forecasts — it is an emergent cross-agent risk that could simultaneously destroy distribution and delivery. |
| 2 | CIS payment rail complexity (Stripe blocked in RU/BY) | 3 | Start with Telegram Stars for zero-friction MVP onboarding (accept 50% cut at early scale); initiate YooKassa legal entity setup in parallel as post-MVP track. Both Architect (complexity=4) and PM (primary churn risk) flag this independently — it is a compounding cross-agent risk. |
| 3 | Break-even timeline of 12-18 months post-launch | 3 | Month-6 base case is only 48 paid users ($1,166 MRR); break-even at 324 users. $0 CAC means no acquisition burn — owner's primary income covers runway. Frame explicitly as asset-building phase, not near-term income replacement. |
| 4 | X/Twitter source descoped from MVP (TOS violation + API cost cliff) | 2 | Implement rss.app bridge for X-sourced content and community-submitted links in MVP. Revisit X API at >3k paid users when Pro tier ($5k/mo) becomes affordable. GitHub + HN sources are sufficient for developer channels at launch. |
| 5 | Voice onboarding friction (requires 10-20 labeled past posts) | 2 | Pre-build developer-channel voice defaults to eliminate cold-start; progressive refinement UX; 'retune from last N posts' admin command. Both Architect and PM (as churn risk) note draft quality is critical to retention. |

## Next steps

- Commit to Telegram Stars as primary payment rail for MVP; initiate YooKassa legal entity setup in parallel as post-MVP track.
- Descope X from MVP; implement rss.app bridge as placeholder X-content source for day one.
- Design voice-calibration UX with pre-built developer-channel voice defaults to reduce cold-start friction.
- First-iteration scope: GitHub releases + HN sources, single-channel, Telegram Stars payment, 3 drafts/day.
- Draft a Telegram-blocking crisis playbook: monitoring signals, English-channel pivot criteria, Bot API failover logic.
- Target first 10 paying users through owner's personal CIS dev-channel network before any broader outreach.
- Post-MVP tracks: YooKassa payment once legal entity established; X API at >3k paid users; multi-channel Studio tier.

