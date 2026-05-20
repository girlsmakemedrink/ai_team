from __future__ import annotations

from idea_validator.models import (
    CompetitorList,
    DifferentiatorList,
    MarketEstimate,
    RiskList,
    Score,
)

_SEVERITY_WEIGHT = {"low": 1, "medium": 2, "high": 3}


def run(
    competitors: CompetitorList,
    market: MarketEstimate,
    risks: RiskList,
    differentiators: DifferentiatorList,
) -> Score:
    # Market score: log-scale TAM up to 5 points
    import math

    tam_score = min(5, max(1, int(math.log10(max(market.tam_usd, 1)))))

    # Competitor score: fewer competitors = higher score (inverted, 1-5)
    comp_count = len(competitors.items)
    comp_score = max(1, 6 - comp_count)

    # Risk score: penalise high-severity risks
    risk_penalty = sum(_SEVERITY_WEIGHT[r.severity] for r in risks.items)
    risk_score = max(1, 5 - risk_penalty // 2)

    # Differentiator score: 1 per differentiator, capped at 3 → normalised to 5
    diff_score = min(5, len(differentiators.items) * 2 - 1)

    components = {
        "market": tam_score,
        "competition": comp_score,
        "risk": risk_score,
        "differentiation": diff_score,
    }
    raw = sum(components.values())
    # normalise 4-20 range to 1-10
    score = max(1, min(10, round((raw - 4) / 16 * 9 + 1)))
    rationale = (
        f"Market={tam_score}/5, Competition={comp_score}/5, "
        f"Risk={risk_score}/5, Differentiation={diff_score}/5 → raw={raw} → score={score}/10"
    )
    return Score(score=score, components=components, rationale=rationale)
