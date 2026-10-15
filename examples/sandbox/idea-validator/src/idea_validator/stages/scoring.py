"""Stage 6: deterministic scoring (no LLM call)."""
from __future__ import annotations

from idea_validator.models import (
    CompetitorList,
    DifferentiatorList,
    MarketEstimate,
    RiskList,
    Score,
)


def run(
    competitors: CompetitorList,
    market: MarketEstimate,
    risks: RiskList,
    differentiators: DifferentiatorList,
) -> Score:
    high = sum(1 for r in risks.items if r.severity == "high")
    med = sum(1 for r in risks.items if r.severity == "medium")
    rs = max(1, 5 - high * 2 - med)
    ms = min(5, max(1, market.tam_usd // 1_000_000_000 + 2))
    ds = min(5, len(differentiators.items) + 2)
    cs = min(5, max(1, 6 - len(competitors.items)))
    total = max(1, min(10, round((ms + ds + rs + cs) / 4 * 2)))
    return Score(
        score=total,
        components={"market": ms, "differentiation": ds, "risk": rs, "competition": cs},
        rationale=f"market={ms}/5 diff={ds}/5 risk={rs}/5 competition={cs}/5.",
    )
