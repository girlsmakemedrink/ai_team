"""Unit tests for each pipeline stage."""
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


def test_parse_input_strips_whitespace() -> None:
    result = parse_input.run("  My Idea  ", depth="standard")
    assert result.idea == "My Idea"
    assert result.depth == "standard"


def test_parse_input_slug() -> None:
    result = parse_input.run("AI Tutoring Platform")
    assert result.slug == "ai-tutoring-platform"


def test_parse_input_frozen_timestamp() -> None:
    from datetime import datetime

    ts = datetime(2026, 1, 1, 0, 0, 0)
    result = parse_input.run("test", created_at=ts)
    assert result.created_at == ts


@pytest.mark.asyncio
async def test_competitor_search_ok(mock_search: MockSearchClient) -> None:
    idea = IdeaInput(idea="AI tutoring marketplace")
    result = await competitor_search.run(idea, mock_search)
    assert isinstance(result, CompetitorList)
    assert 3 <= len(result.items) <= 5


@pytest.mark.asyncio
async def test_competitor_search_too_few() -> None:
    sparse = MockSearchClient(results=[
        SearchResult(title="A", url="https://a.example.com", snippet="x"),
        SearchResult(title="B", url="https://b.example.com", snippet="y"),
    ])
    idea = IdeaInput(idea="test")
    with pytest.raises(ValueError, match="at least 3"):
        await competitor_search.run(idea, sparse)


@pytest.mark.asyncio
async def test_market_estimate(mock_llm: MockLLMClient) -> None:
    idea = IdeaInput(idea="AI tutoring marketplace")
    result = await market_estimate.run(idea, mock_llm)
    assert isinstance(result, MarketEstimate)
    assert result.tam_usd > 0


@pytest.mark.asyncio
async def test_risk_analysis(mock_llm: MockLLMClient) -> None:
    idea = IdeaInput(idea="AI tutoring marketplace")
    result = await risk_analysis.run(idea, mock_llm)
    assert isinstance(result, RiskList)
    assert len(result.items) == 3


@pytest.mark.asyncio
async def test_differentiator_analysis(mock_llm: MockLLMClient) -> None:
    idea = IdeaInput(idea="AI tutoring marketplace")
    result = await differentiator_analysis.run(idea, mock_llm)
    assert isinstance(result, DifferentiatorList)
    assert len(result.items) == 3


def test_scoring_range(
    sample_competitors: CompetitorList,
    sample_market: MarketEstimate,
    sample_risks: RiskList,
    sample_diffs: DifferentiatorList,
) -> None:
    result = scoring.run(sample_competitors, sample_market, sample_risks, sample_diffs)
    assert isinstance(result, Score)
    assert 1 <= result.score <= 10
    assert "market" in result.components
    assert "competition" in result.components


def test_report_writer_contains_sections(
    sample_competitors: CompetitorList,
    sample_market: MarketEstimate,
    sample_risks: RiskList,
    sample_diffs: DifferentiatorList,
    sample_score: Score,
) -> None:
    idea = IdeaInput(idea="AI tutoring marketplace")
    md = report_writer.run(idea, sample_competitors, sample_market, sample_risks, sample_diffs, sample_score)
    assert "# Idea Validation Report" in md
    assert "## Competitors" in md
    assert "## Market Estimate" in md
    assert "## Top Risks" in md
    assert "## Key Differentiators" in md
    assert str(sample_score.score) in md
    # US-1 AC-7: report.md must link to all six sibling files
    for fname in ("input.json", "competitors.json", "market.md", "risks.md", "differentiators.md", "score.json"):
        assert f"[{fname}]({fname})" in md, f"report.md missing relative link to {fname}"


def test_make_search_quick_returns_stub_results() -> None:
    from idea_validator.search import make_search

    client = make_search("quick")
    import asyncio

    results = asyncio.run(client.search("anything", 5))
    assert len(results) >= 3


def test_make_search_no_brave_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BRAVE_API_KEY", raising=False)
    from idea_validator.search import make_search

    with pytest.raises(RuntimeError, match="BRAVE_API_KEY not set"):
        make_search("standard")
