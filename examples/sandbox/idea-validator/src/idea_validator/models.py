"""Pydantic DTOs for idea-validator v2 (ADR-0019, ADR-0021)."""
from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, field_validator


class StageError(BaseModel):
    stage: Literal[
        "parse_input", "competitor_search", "market_estimate",
        "risk_analysis", "differentiator_analysis", "scoring", "report_writer",
    ]
    kind: Literal["transport", "validation", "upstream_missing"]
    message: str

    @field_validator("message")
    @classmethod
    def _cap(cls, v: str) -> str:
        if "BRAVE_API_KEY=" in v or v.startswith("sk-"):
            raise ValueError("secret fragment in message")
        return v[:200]


class IdeaInput(BaseModel):
    idea: str
    depth: Literal["quick", "standard", "deep"] = "standard"
    created_at: str = ""
    slug: str = ""


class Competitor(BaseModel):
    name: str
    url: str
    positioning: str


class CompetitorList(BaseModel):
    items: list[Competitor]


class MarketEstimate(BaseModel):
    tam_usd: int
    sam_usd: int
    som_usd: int
    reasoning: str


class Risk(BaseModel):
    title: str
    severity: Literal["low", "medium", "high"]
    rationale: str


class RiskList(BaseModel):
    items: list[Risk]


class Differentiator(BaseModel):
    title: str
    rationale: str


class DifferentiatorList(BaseModel):
    items: list[Differentiator]


class Score(BaseModel):
    score: int
    components: dict[str, int]
    rationale: str

    @field_validator("score")
    @classmethod
    def _in_range(cls, v: int) -> int:
        if not 1 <= v <= 10:
            raise ValueError(f"score {v} not in [1,10]")
        return v


class ReportBundle(BaseModel):
    input: IdeaInput
    competitors: CompetitorList
    market: MarketEstimate
    risks: RiskList
    differentiators: DifferentiatorList
    score: Score
    report_md: str = ""
    errors: list[StageError] = []

    def write_to_dir(self, path: Path) -> None:
        path.mkdir(parents=True, exist_ok=True)
        (path / "input.json").write_text(self.input.model_dump_json(indent=2))
        (path / "competitors.json").write_text(self.competitors.model_dump_json(indent=2))
        (path / "score.json").write_text(self.score.model_dump_json(indent=2))
        m = self.market
        (path / "market.md").write_text(
            f"TAM: ${m.tam_usd:,}\nSAM: ${m.sam_usd:,}\nSOM: ${m.som_usd:,}\n\n{m.reasoning}\n"
        )
        (path / "risks.md").write_text(
            "\n\n".join(
                f"## {r.title}\nSeverity: {r.severity}\n{r.rationale}" for r in self.risks.items
            ) + "\n"
        )
        (path / "differentiators.md").write_text(
            "\n\n".join(
                f"## {d.title}\n{d.rationale}" for d in self.differentiators.items
            ) + "\n"
        )
        (path / "report.md").write_text(self.report_md or self._make_report())

    def _make_report(self) -> str:
        return (
            f"# Idea Validation Report\n\n**Idea:** {self.input.idea}\n"
            f"**Score: {self.score.score}/10**\n\n{self.score.rationale}\n\n"
            "## Files\n\n"
            "- [input.json](input.json)\n- [competitors.json](competitors.json)\n"
            "- [market.md](market.md)\n- [risks.md](risks.md)\n"
            "- [differentiators.md](differentiators.md)\n- [score.json](score.json)\n"
        )
