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
