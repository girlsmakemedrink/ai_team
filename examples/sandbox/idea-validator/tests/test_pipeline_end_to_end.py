"""End-to-end pipeline integration test using mocks."""
from __future__ import annotations

import pytest

from idea_validator.llm import MockLLMClient
from idea_validator.models import ReportBundle
from idea_validator.pipeline import Pipeline
from idea_validator.search import MockSearchClient, SearchResult


async def test_pipeline_full_run() -> None:
    llm = MockLLMClient(
        responses={
            "market research analyst": {
                "tam_usd": 2_000_000_000,
                "sam_usd": 200_000_000,
                "som_usd": 10_000_000,
                "reasoning": "Growing market.",
            },
            "risk analyst": {
                "items": [
                    {"title": "R1", "severity": "high", "rationale": "r1"},
                    {"title": "R2", "severity": "medium", "rationale": "r2"},
                    {"title": "R3", "severity": "low", "rationale": "r3"},
                ]
            },
            "product strategist": {
                "items": [
                    {"title": "D1", "rationale": "r1"},
                    {"title": "D2", "rationale": "r2"},
                    {"title": "D3", "rationale": "r3"},
                ]
            },
        }
    )
    search = MockSearchClient(
        results=[
            SearchResult(title=f"Co {i}", url=f"https://co{i}.example.com", snippet="s")
            for i in range(5)
        ]
    )
    pipe = Pipeline(llm=llm, search=search, depth="quick")
    bundle = await pipe.run("AI tutoring marketplace")

    assert isinstance(bundle, ReportBundle)
    assert bundle.input.idea == "AI tutoring marketplace"
    assert bundle.input.slug
    assert bundle.input.created_at
    assert 3 <= len(bundle.competitors.items) <= 5
    assert bundle.market.tam_usd > 0
    assert len(bundle.risks.items) == 3
    assert len(bundle.differentiators.items) == 3
    assert 1 <= bundle.score.score <= 10
    assert bundle.report_md


async def test_pipeline_write_seven_files(tmp_path: object) -> None:
    from pathlib import Path
    llm = MockLLMClient(
        responses={
            "market research analyst": {
                "tam_usd": 1_000_000_000, "sam_usd": 100_000_000,
                "som_usd": 5_000_000, "reasoning": "ok",
            },
            "risk analyst": {
                "items": [
                    {"title": "R1", "severity": "low", "rationale": "r"},
                    {"title": "R2", "severity": "low", "rationale": "r"},
                    {"title": "R3", "severity": "low", "rationale": "r"},
                ]
            },
            "product strategist": {
                "items": [
                    {"title": "D1", "rationale": "r"},
                    {"title": "D2", "rationale": "r"},
                    {"title": "D3", "rationale": "r"},
                ]
            },
        }
    )
    search = MockSearchClient(results=[
        SearchResult(title="A", url="https://a.example.com", snippet="s") for _ in range(3)
    ])
    pipe = Pipeline(llm=llm, search=search, depth="quick")
    bundle = await pipe.run("test idea")
    out = Path(str(tmp_path)) / "report"
    bundle.write_to_dir(out)
    names = {f.name for f in out.iterdir()}
    assert names == {"input.json", "competitors.json", "market.md", "risks.md",
                     "differentiators.md", "score.json", "report.md"}
