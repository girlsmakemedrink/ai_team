"""Unit tests for individual pipeline stages."""
from __future__ import annotations

import pytest

from idea_validator.llm import MockLLMClient
from idea_validator.models import (
    CompetitorList,
    DifferentiatorList,
    IdeaInput,
    MarketEstimate,
    RiskList,
    Score,
)
from idea_validator.search import MockSearchClient, SearchResult
from idea_validator.stages import (
    competitor_search,
    differentiator_analysis,
    market_estimate,
    parse_input,
    report_writer,
    risk_analysis,
    scoring,
)


def test_parse_input_slug_generation() -> None:
    inp = parse_input.run("AI Tutoring Marketplace!", depth="quick")
    assert inp.slug == "ai-tutoring-marketplace"
    assert inp.depth == "quick"
    assert inp.created_at


def test_parse_input_slug_truncated() -> None:
    inp = parse_input.run("a" * 100)
    assert len(inp.slug) <= 40


def test_parse_input_frozen_timestamp() -> None:
    from datetime import datetime, timezone
    ft = datetime(2026, 1, 1, tzinfo=timezone.utc)
    inp = parse_input.run("test idea", frozen_timestamp=ft)
    assert "2026-01-01" in inp.created_at


async def test_competitor_search_returns_3_to_5(mock_search: MockSearchClient) -> None:
    inp = IdeaInput(idea="test", depth="quick")
    result = await competitor_search.run(inp, mock_search)
    assert 3 <= len(result.items) <= 5


async def test_competitor_search_pads_short_results() -> None:
    tiny_search = MockSearchClient(results=[
        SearchResult(title="Only One", url="https://one.example.com", snippet="s")
    ])
    inp = IdeaInput(idea="test", depth="quick")
    result = await competitor_search.run(inp, tiny_search)
    assert len(result.items) >= 3


async def test_market_estimate_run(mock_llm: MockLLMClient) -> None:
    inp = IdeaInput(idea="test idea", depth="quick")
    result = await market_estimate.run(inp, mock_llm)
    assert isinstance(result, MarketEstimate)
    assert result.tam_usd > 0
    assert result.reasoning


async def test_risk_analysis_run(mock_llm: MockLLMClient) -> None:
    inp = IdeaInput(idea="test idea", depth="quick")
    result = await risk_analysis.run(inp, mock_llm)
    assert isinstance(result, RiskList)
    assert len(result.items) == 3


async def test_differentiator_analysis_run(mock_llm: MockLLMClient) -> None:
    inp = IdeaInput(idea="test idea", depth="quick")
    result = await differentiator_analysis.run(inp, mock_llm)
    assert isinstance(result, DifferentiatorList)
    assert len(result.items) == 3


def test_scoring_produces_valid_score(sample_bundle: object) -> None:
    from idea_validator.models import (
        Competitor, CompetitorList, Differentiator, DifferentiatorList,
        MarketEstimate, Risk, RiskList,
    )
    comps = CompetitorList(items=[
        Competitor(name="X", url="https://x.example.com", positioning="p")
        for _ in range(4)
    ])
    market = MarketEstimate(tam_usd=5_000_000_000, sam_usd=500_000_000, som_usd=25_000_000, reasoning="ok")
    risks = RiskList(items=[
        Risk(title="R1", severity="low", rationale="r"),
        Risk(title="R2", severity="low", rationale="r"),
        Risk(title="R3", severity="low", rationale="r"),
    ])
    diffs = DifferentiatorList(items=[
        Differentiator(title="D1", rationale="r"),
        Differentiator(title="D2", rationale="r"),
        Differentiator(title="D3", rationale="r"),
    ])
    score = scoring.run(comps, market, risks, diffs)
    assert isinstance(score, Score)
    assert 1 <= score.score <= 10
    assert score.components
    assert score.rationale


def test_report_writer_contains_all_file_links() -> None:
    from idea_validator.models import (
        Competitor, CompetitorList, Differentiator, DifferentiatorList,
        MarketEstimate, Risk, RiskList, Score,
    )
    inp = IdeaInput(idea="test", depth="quick", slug="test", created_at="2026-01-01T00:00:00+00:00")
    comps = CompetitorList(items=[Competitor(name="X", url="https://x.example.com", positioning="p")])
    market = MarketEstimate(tam_usd=1_000_000_000, sam_usd=100_000_000, som_usd=10_000_000, reasoning="ok")
    risks = RiskList(items=[Risk(title="R", severity="low", rationale="r")])
    diffs = DifferentiatorList(items=[Differentiator(title="D", rationale="r")])
    score = Score(score=5, components={"a": 3}, rationale="ok")
    md = report_writer.run(inp, comps, market, risks, diffs, score)
    for fname in ("input.json", "competitors.json", "market.md", "risks.md",
                  "differentiators.md", "score.json"):
        assert fname in md
