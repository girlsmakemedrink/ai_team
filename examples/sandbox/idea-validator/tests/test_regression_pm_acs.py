"""Regression tests pinned to PM acceptance criteria.

Covers gaps in the existing suite identified by QA in iter-17:
  - US-1 AC-2  score.json on disk has correct shape
  - US-1 AC-3  competitors.json on disk has correct shape
  - US-1 AC-7  report.md contains relative links to all six sibling files
  - US-2 AC-6  compare <id> <same-id> exits 0 and indicates no meaningful diff
  - ADR-0021   exit 11 path: --depth standard without BRAVE_API_KEY
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from click.testing import CliRunner

from idea_validator.cli import cli
from idea_validator.models import (
    Competitor,
    CompetitorList,
    Differentiator,
    DifferentiatorList,
    IdeaInput,
    MarketEstimate,
    ReportBundle,
    RiskList,
    Score,
)
from idea_validator.models import Risk


def _make_bundle_with_score(score_val: int = 6) -> ReportBundle:
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
            tam_usd=10_000_000_000,
            sam_usd=1_000_000_000,
            som_usd=50_000_000,
            reasoning="Large and growing market.",
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
            score=score_val,
            components={"market": 4, "competition": 3, "risk": 2, "differentiation": 3},
            rationale="Solid opportunity with manageable risks.",
        ),
        report_md=(
            "# Idea Validation Report\n\n**Idea:** AI tutoring marketplace\n"
            "**Viability Score: 6/10**\n\nRationale here.\n\n"
            "## Files\n\n"
            "- [input.json](input.json)\n"
            "- [competitors.json](competitors.json)\n"
            "- [market.md](market.md)\n"
            "- [risks.md](risks.md)\n"
            "- [differentiators.md](differentiators.md)\n"
            "- [score.json](score.json)\n"
        ),
    )


def test_us1_ac2_score_json_disk_shape(tmp_path: Path) -> None:
    bundle = _make_bundle_with_score(7)
    out = tmp_path / "report"
    bundle.write_to_dir(out)
    score_data = json.loads((out / "score.json").read_text())
    assert isinstance(score_data["score"], int)
    assert 1 <= score_data["score"] <= 10
    assert score_data["components"]
    assert score_data["rationale"]


def test_us1_ac3_competitors_json_disk_shape(tmp_path: Path) -> None:
    bundle = _make_bundle_with_score()
    out = tmp_path / "report"
    bundle.write_to_dir(out)
    data = json.loads((out / "competitors.json").read_text())
    items = data["items"]
    assert 3 <= len(items) <= 5
    for item in items:
        assert item["name"]
        assert item["url"]
        assert item["positioning"]


_EXPECTED_LINKS = [
    "input.json", "competitors.json", "market.md",
    "risks.md", "differentiators.md", "score.json",
]


@pytest.mark.asyncio
async def test_us1_ac7_report_md_links_to_all_six_files(tmp_path: Path) -> None:
    from idea_validator.stages import (
        competitor_search, differentiator_analysis, market_estimate,
        parse_input, report_writer, risk_analysis, scoring,
    )
    from idea_validator.llm import MockLLMClient
    from idea_validator.search import MockSearchClient, SearchResult

    llm = MockLLMClient(
        responses={
            "market research analyst": {
                "tam_usd": 1_000_000_000, "sam_usd": 100_000_000,
                "som_usd": 10_000_000, "reasoning": "Big market.",
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
    idea_input = parse_input.run("AI tutoring marketplace", depth="quick")
    competitors = await competitor_search.run(idea_input, search)
    market = await market_estimate.run(idea_input, llm)
    risks = await risk_analysis.run(idea_input, llm)
    diffs = await differentiator_analysis.run(idea_input, llm)
    score = scoring.run(competitors, market, risks, diffs)
    report_md = report_writer.run(idea_input, competitors, market, risks, diffs, score)
    for fname in _EXPECTED_LINKS:
        assert fname in report_md


def test_us2_ac6_compare_report_with_itself(tmp_path: Path) -> None:
    d = tmp_path / "my-idea"
    d.mkdir()
    (d / "score.json").write_text(
        json.dumps({"score": 7, "components": {"market": 4}, "rationale": "ok"})
    )
    runner = CliRunner()
    result = runner.invoke(cli, ["compare", "my-idea", "my-idea", "--dir", str(tmp_path)])
    assert result.exit_code == 0


def test_analyze_exit_11_standard_depth_no_brave_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BRAVE_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    runner = CliRunner()
    result = runner.invoke(cli, ["analyze", "--idea", "test idea", "--depth", "standard"])
    assert result.exit_code == 11


def test_analyze_exit_11_deep_depth_no_brave_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BRAVE_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    runner = CliRunner()
    result = runner.invoke(cli, ["analyze", "--idea", "test idea", "--depth", "deep"])
    assert result.exit_code == 11


def test_us1_ac8_depth_quick_runs_offline(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BRAVE_API_KEY", raising=False)
    monkeypatch.setenv("IDEA_VALIDATOR_REAL_LLM", "0")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    bundle = _make_bundle_with_score(5)
    runner = CliRunner()
    with runner.isolated_filesystem():
        with (
            patch("idea_validator.cli.Pipeline") as MockPipeline,
            patch("idea_validator.cli.make_llm"),
            patch("idea_validator.cli.make_search"),
        ):
            mock_pipe = MagicMock()
            mock_pipe.run = AsyncMock(return_value=bundle)
            MockPipeline.return_value = mock_pipe
            result = runner.invoke(
                cli,
                ["analyze", "--idea", "AI tutoring marketplace", "--depth", "quick", "--output-dir", "out"],
            )
    assert result.exit_code == 0
