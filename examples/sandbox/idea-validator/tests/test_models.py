"""Unit tests for models.py."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest
from pydantic import ValidationError

from idea_validator.models import (
    Competitor,
    CompetitorList,
    DifferentiatorList,
    IdeaInput,
    MarketEstimate,
    ReportBundle,
    RiskList,
    Score,
)


def test_idea_input_slug_generated() -> None:
    inp = IdeaInput(idea="AI Tutoring Platform")
    assert inp.slug == "ai-tutoring-platform"


def test_idea_input_slug_truncated() -> None:
    inp = IdeaInput(idea="A" * 100)
    assert len(inp.slug) <= 40


def test_competitor_list_too_few() -> None:
    with pytest.raises(ValidationError):
        CompetitorList(
            items=[
                Competitor(name="A", url="https://a.example.com", positioning="x"),
                Competitor(name="B", url="https://b.example.com", positioning="y"),
            ]
        )


def test_competitor_list_too_many() -> None:
    with pytest.raises(ValidationError):
        CompetitorList(
            items=[
                Competitor(name=str(i), url=f"https://{i}.example.com", positioning="x")
                for i in range(6)
            ]
        )


def test_competitor_list_valid() -> None:
    cl = CompetitorList(
        items=[
            Competitor(name=str(i), url=f"https://{i}.example.com", positioning="x")
            for i in range(3)
        ]
    )
    assert len(cl.items) == 3


def test_risk_list_wrong_count() -> None:
    with pytest.raises(ValidationError):
        RiskList(
            items=[{"title": "r", "severity": "low", "rationale": "x"}]
        )


def test_differentiator_list_wrong_count() -> None:
    with pytest.raises(ValidationError):
        DifferentiatorList(items=[{"title": "d", "rationale": "x"}, {"title": "e", "rationale": "y"}])


def test_score_bounds() -> None:
    with pytest.raises(ValidationError):
        Score(score=11, components={}, rationale="bad")
    with pytest.raises(ValidationError):
        Score(score=0, components={}, rationale="bad")


def test_report_bundle_write_to_dir(
    sample_competitors: CompetitorList,
    sample_market: MarketEstimate,
    sample_risks: RiskList,
    sample_diffs: DifferentiatorList,
    sample_score: Score,
) -> None:
    bundle = ReportBundle(
        input=IdeaInput(idea="test idea"),
        competitors=sample_competitors,
        market=sample_market,
        risks=sample_risks,
        differentiators=sample_diffs,
        score=sample_score,
        report_md="# Report",
    )
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "report"
        bundle.write_to_dir(out)
        assert (out / "input.json").exists()
        assert (out / "competitors.json").exists()
        assert (out / "market.md").exists()
        assert (out / "risks.md").exists()
        assert (out / "differentiators.md").exists()
        assert (out / "score.json").exists()
        assert (out / "report.md").exists()
        score_data = json.loads((out / "score.json").read_text())
        assert 1 <= score_data["score"] <= 10
