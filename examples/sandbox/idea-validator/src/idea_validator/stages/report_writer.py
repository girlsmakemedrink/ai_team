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
    lines: list[str] = []
    lines.append(f"# Idea Validation Report\n\n**Idea:** {idea_input.idea}\n")
    lines.append(f"**Viability Score: {score.score}/10**\n\n{score.rationale}\n")

    lines.append("## Competitors\n")
    for c in competitors.items:
        lines.append(f"- **{c.name}** ({c.url}): {c.positioning}")
    lines.append("")

    lines.append("## Market Estimate\n")
    lines.append(f"- TAM: ${market.tam_usd:,}")
    lines.append(f"- SAM: ${market.sam_usd:,}")
    lines.append(f"- SOM: ${market.som_usd:,}")
    lines.append(f"\n{market.reasoning}\n")

    lines.append("## Top Risks\n")
    for r in risks.items:
        lines.append(f"- [{r.severity.upper()}] **{r.title}**: {r.rationale}")
    lines.append("")

    lines.append("## Key Differentiators\n")
    for d in differentiators.items:
        lines.append(f"- **{d.title}**: {d.rationale}")
    lines.append("")

    lines.append("## Files\n")
    for fname in ("input.json", "competitors.json", "market.md", "risks.md", "differentiators.md", "score.json"):
        lines.append(f"- [{fname}]({fname})")
    lines.append("")

    return "\n".join(lines)
