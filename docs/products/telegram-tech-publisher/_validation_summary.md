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
