"""Shared fixtures for idea-validator tests."""
from __future__ import annotations

import pytest

from idea_validator.llm import MockLLMClient
from idea_validator.models import (
    Competitor,
    CompetitorList,
    DifferentiatorList,
    MarketEstimate,
    RiskList,
    Score,
)
from idea_validator.search import MockSearchClient, SearchResult


@pytest.fixture()
def sample_search_results() -> list[SearchResult]:
    return [
        SearchResult(title="Acme Tutors - Online Learning", url="https://acme.example.com", snippet="AI-powered tutoring"),
        SearchResult(title="BrightPath Education", url="https://brightpath.example.com", snippet="Personalised study plans"),
        SearchResult(title="LearnFast - Marketplace", url="https://learnfast.example.com", snippet="Tutor marketplace"),
        SearchResult(title="SkillBoost", url="https://skillboost.example.com", snippet="Skill-based matching"),
        SearchResult(title="EduMatch Pro", url="https://edumatch.example.com", snippet="AI matching engine"),
    ]


@pytest.fixture()
def mock_search(sample_search_results: list[SearchResult]) -> MockSearchClient:
    return MockSearchClient(results=sample_search_results)


@pytest.fixture()
def mock_llm_responses() -> dict[str, object]:
    return {
        "market research analyst": {
            "tam_usd": 50_000_000_000,
            "sam_usd": 5_000_000_000,
            "som_usd": 100_000_000,
            "reasoning": "Global tutoring market is large and growing.",
        },
        "risk analyst": {
            "items": [
                {"title": "Regulatory risk", "severity": "high", "rationale": "EdTech regulations vary."},
                {"title": "Tutor supply", "severity": "medium", "rationale": "Hard to onboard quality tutors."},
                {"title": "Retention risk", "severity": "low", "rationale": "Students may churn after goals met."},
            ]
        },
        "product strategist": {
            "items": [
                {"title": "AI matching", "rationale": "Proprietary algorithm reduces search friction."},
                {"title": "Verified tutors", "rationale": "Background checks build trust."},
                {"title": "Progress tracking", "rationale": "Data-driven learning plans."},
            ]
        },
    }


@pytest.fixture()
def mock_llm(mock_llm_responses: dict[str, object]) -> MockLLMClient:
    return MockLLMClient(responses=mock_llm_responses)  # type: ignore[arg-type]


@pytest.fixture()
def sample_competitors() -> CompetitorList:
    return CompetitorList(
        items=[
            Competitor(name="Acme Tutors", url="https://acme.example.com", positioning="AI tutoring"),
            Competitor(name="BrightPath", url="https://brightpath.example.com", positioning="Study plans"),
            Competitor(name="LearnFast", url="https://learnfast.example.com", positioning="Marketplace"),
        ]
    )


@pytest.fixture()
def sample_market() -> MarketEstimate:
    return MarketEstimate(
        tam_usd=50_000_000_000,
        sam_usd=5_000_000_000,
        som_usd=100_000_000,
        reasoning="Large market.",
    )


@pytest.fixture()
def sample_risks() -> RiskList:
    return RiskList(
        items=[
            {"title": "Regulatory risk", "severity": "high", "rationale": "Varies by region."},
            {"title": "Supply risk", "severity": "medium", "rationale": "Hard to scale tutors."},
            {"title": "Churn risk", "severity": "low", "rationale": "Students may leave."},
        ]
    )


@pytest.fixture()
def sample_diffs() -> DifferentiatorList:
    return DifferentiatorList(
        items=[
            {"title": "AI matching", "rationale": "Reduces friction."},
            {"title": "Verified tutors", "rationale": "Builds trust."},
            {"title": "Progress tracking", "rationale": "Data-driven."},
        ]
    )


@pytest.fixture()
def sample_score(sample_competitors: CompetitorList, sample_market: MarketEstimate, sample_risks: RiskList, sample_diffs: DifferentiatorList) -> Score:
    from idea_validator.stages import scoring
    return scoring.run(sample_competitors, sample_market, sample_risks, sample_diffs)
