"""Shared test fixtures."""
from __future__ import annotations

import pytest

from idea_validator.llm import MockLLMClient
from idea_validator.models import (
    Competitor,
    CompetitorList,
    Differentiator,
    DifferentiatorList,
    IdeaInput,
    MarketEstimate,
    ReportBundle,
    Risk,
    RiskList,
    Score,
)
from idea_validator.search import MockSearchClient, SearchResult

_MOCK_LLM_RESPONSES = {
    "market research analyst": {
        "tam_usd": 5_000_000_000,
        "sam_usd": 500_000_000,
        "som_usd": 25_000_000,
        "reasoning": "Large addressable market.",
    },
    "risk analyst": {
        "items": [
            {"title": "Competition", "severity": "high", "rationale": "Many incumbents"},
            {"title": "Regulation", "severity": "medium", "rationale": "Possible GDPR issues"},
            {"title": "Tech debt", "severity": "low", "rationale": "Manageable"},
        ]
    },
    "product strategist": {
        "items": [
            {"title": "Speed", "rationale": "Faster than incumbents"},
            {"title": "Price", "rationale": "50% cheaper"},
            {"title": "UX", "rationale": "Best-in-class experience"},
        ]
    },
}


@pytest.fixture
def mock_llm() -> MockLLMClient:
    return MockLLMClient(responses=_MOCK_LLM_RESPONSES)


@pytest.fixture
def mock_search() -> MockSearchClient:
    return MockSearchClient(
        results=[
            SearchResult(title=f"Competitor {i}", url=f"https://comp{i}.example.com", snippet=f"desc {i}")
            for i in range(5)
        ]
    )


@pytest.fixture
def sample_bundle() -> ReportBundle:
    return ReportBundle(
        input=IdeaInput(idea="AI tutoring marketplace"),
        competitors=CompetitorList(
            items=[
                Competitor(name="A", url="https://a.example.com", positioning="p1"),
                Competitor(name="B", url="https://b.example.com", positioning="p2"),
                Competitor(name="C", url="https://c.example.com", positioning="p3"),
            ]
        ),
        market=MarketEstimate(
            tam_usd=10_000_000_000, sam_usd=1_000_000_000, som_usd=50_000_000,
            reasoning="Large market.",
        ),
        risks=RiskList(
            items=[
                Risk(title="R1", severity="high", rationale="reason1"),
                Risk(title="R2", severity="medium", rationale="reason2"),
                Risk(title="R3", severity="low", rationale="reason3"),
            ]
        ),
        differentiators=DifferentiatorList(
            items=[
                Differentiator(title="D1", rationale="r1"),
                Differentiator(title="D2", rationale="r2"),
                Differentiator(title="D3", rationale="r3"),
            ]
        ),
        score=Score(
            score=7,
            components={"market": 4, "competition": 3, "risk": 2, "differentiation": 3},
            rationale="Solid opportunity.",
        ),
        report_md=(
            "# Idea Validation Report\n\n**Idea:** AI tutoring marketplace\n"
            "**Viability Score: 7/10**\n\nSolid opportunity.\n\n"
            "## Files\n\n"
            "- [input.json](input.json)\n"
            "- [competitors.json](competitors.json)\n"
            "- [market.md](market.md)\n"
            "- [risks.md](risks.md)\n"
            "- [differentiators.md](differentiators.md)\n"
            "- [score.json](score.json)\n"
        ),
    )
