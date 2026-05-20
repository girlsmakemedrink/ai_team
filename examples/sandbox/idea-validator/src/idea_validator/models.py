"""Pydantic v2 data contracts for idea-validator. See ADR-0011."""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator


class IdeaInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    idea: str
    depth: Literal["quick", "standard", "deep"] = "quick"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    slug: str = ""

    def model_post_init(self, __context: object) -> None:
        if not self.slug:
            self.slug = re.sub(r"[^a-z0-9]+", "-", self.idea.lower())[:40].strip("-")


class Competitor(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    url: HttpUrl
    positioning: str


class CompetitorList(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[Competitor]

    @field_validator("items")
    @classmethod
    def between_three_and_five(cls, v: list[Competitor]) -> list[Competitor]:
        if not (3 <= len(v) <= 5):
            raise ValueError(f"expected 3-5 competitors, got {len(v)}")
        return v


class MarketEstimate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tam_usd: int
    sam_usd: int
    som_usd: int
    reasoning: str


class Risk(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str
    severity: Literal["low", "medium", "high"]
    rationale: str


class RiskList(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[Risk]

    @field_validator("items")
    @classmethod
    def exactly_three(cls, v: list[Risk]) -> list[Risk]:
        if len(v) != 3:
            raise ValueError(f"expected exactly 3 risks, got {len(v)}")
        return v


class Differentiator(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str
    rationale: str


class DifferentiatorList(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[Differentiator]

    @field_validator("items")
    @classmethod
    def exactly_three(cls, v: list[Differentiator]) -> list[Differentiator]:
        if len(v) != 3:
            raise ValueError(f"expected exactly 3 differentiators, got {len(v)}")
        return v


class Score(BaseModel):
    model_config = ConfigDict(extra="forbid")
    score: int = Field(ge=1, le=10)
    components: dict[str, int]
    rationale: str


class ReportBundle(BaseModel):
    model_config = ConfigDict(extra="forbid")
    input: IdeaInput
    competitors: CompetitorList
    market: MarketEstimate
    risks: RiskList
    differentiators: DifferentiatorList
    score: Score
    report_md: str = ""

    def write_to_dir(self, path: Path) -> None:
        path.mkdir(parents=True, exist_ok=True)
        (path / "input.json").write_text(self.input.model_dump_json(indent=2))
        (path / "competitors.json").write_text(self.competitors.model_dump_json(indent=2))
        (path / "market.md").write_text(
            f"# Market Estimate\n\n"
            f"- TAM: ${self.market.tam_usd:,}\n"
            f"- SAM: ${self.market.sam_usd:,}\n"
            f"- SOM: ${self.market.som_usd:,}\n\n"
            f"{self.market.reasoning}\n"
        )
        (path / "risks.md").write_text(
            "# Risks\n\n"
            + "\n".join(
                f"- [{r.severity.upper()}] **{r.title}**: {r.rationale}"
                for r in self.risks.items
            )
            + "\n"
        )
        (path / "differentiators.md").write_text(
            "# Differentiators\n\n"
            + "\n".join(
                f"- **{d.title}**: {d.rationale}" for d in self.differentiators.items
            )
            + "\n"
        )
        (path / "score.json").write_text(self.score.model_dump_json(indent=2))
        (path / "report.md").write_text(self.report_md)
