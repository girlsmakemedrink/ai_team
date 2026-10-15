"""Stage 7: assemble the Markdown report."""
from __future__ import annotations

from idea_validator.models import (
    CompetitorList,
    DifferentiatorList,
    IdeaInput,
    MarketEstimate,
    RiskList,
    Score,
)


def run(
    idea_input: IdeaInput,
    competitors: CompetitorList,
    market: MarketEstimate,
    risks: RiskList,
    differentiators: DifferentiatorList,
    score: Score,
) -> str:
    return (
        f"# Idea Validation Report\n\n"
        f"**Idea:** {idea_input.idea}\n\n"
        f"**Viability Score: {score.score}/10**\n\n"
        f"{score.rationale}\n\n"
        "## Files\n\n"
        "- [input.json](input.json)\n"
        "- [competitors.json](competitors.json)\n"
        "- [market.md](market.md)\n"
        "- [risks.md](risks.md)\n"
        "- [differentiators.md](differentiators.md)\n"
        "- [score.json](score.json)\n"
    )
