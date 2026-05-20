"""Tests for CLI commands."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from click.testing import CliRunner

from idea_validator.cli import cli
from idea_validator.models import (
    CompetitorList,
    DifferentiatorList,
    IdeaInput,
    MarketEstimate,
    ReportBundle,
    RiskList,
    Score,
)


def _make_bundle() -> ReportBundle:
    from idea_validator.models import Competitor, Differentiator, Risk

    return ReportBundle(
        input=IdeaInput(idea="AI tutoring marketplace"),
        competitors=CompetitorList(
            items=[
                Competitor(name="A", url="https://a.example.com", positioning="p"),
                Competitor(name="B", url="https://b.example.com", positioning="p"),
                Competitor(name="C", url="https://c.example.com", positioning="p"),
            ]
        ),
        market=MarketEstimate(tam_usd=1_000_000_000, sam_usd=100_000_000, som_usd=10_000_000, reasoning="big"),
        risks=RiskList(
            items=[
                Risk(title="R1", severity="high", rationale="r"),
                Risk(title="R2", severity="medium", rationale="r"),
                Risk(title="R3", severity="low", rationale="r"),
            ]
        ),
        differentiators=DifferentiatorList(
            items=[
                Differentiator(title="D1", rationale="r"),
                Differentiator(title="D2", rationale="r"),
                Differentiator(title="D3", rationale="r"),
            ]
        ),
        score=Score(score=7, components={"market": 4, "competition": 3}, rationale="ok"),
        report_md="# Report\n\nGreat idea.",
    )


def test_analyze_writes_report() -> None:
    # Use isolated_filesystem so --output-dir resolves under cwd (passes path-safety guard).
    bundle = _make_bundle()
    runner = CliRunner()
    with runner.isolated_filesystem():
        with (
            patch("idea_validator.cli.make_llm") as mock_llm_factory,
            patch("idea_validator.cli.make_search") as mock_search_factory,
            patch("idea_validator.cli.Pipeline") as MockPipeline,
        ):
            mock_pipeline = MagicMock()
            mock_pipeline.run = AsyncMock(return_value=bundle)
            MockPipeline.return_value = mock_pipeline
            mock_llm_factory.return_value = MagicMock()
            mock_search_factory.return_value = MagicMock()

            result = runner.invoke(
                cli,
                ["analyze", "--idea", "AI tutoring marketplace", "--depth", "quick", "--output-dir", "reports"],
            )
        assert result.exit_code == 0, result.output
        report_dirs = list(Path("reports").iterdir())
        assert len(report_dirs) == 1
        assert (report_dirs[0] / "report.md").exists()


def test_list_reports_empty(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["list-reports", "--dir", str(tmp_path / "nonexistent")])
    assert result.exit_code == 0
    assert "no reports found" in result.output


def test_list_reports_shows_dirs(tmp_path: Path) -> None:
    (tmp_path / "idea-20260101T000000Z").mkdir()
    runner = CliRunner()
    result = runner.invoke(cli, ["list-reports", "--dir", str(tmp_path)])
    assert result.exit_code == 0
    assert "idea-20260101T000000Z" in result.output


def test_show_missing_report(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["show", "does-not-exist", "--dir", str(tmp_path)])
    assert result.exit_code != 0


def test_show_existing_report(tmp_path: Path) -> None:
    report_dir = tmp_path / "my-idea"
    report_dir.mkdir()
    (report_dir / "report.md").write_text("# Hello")
    runner = CliRunner()
    result = runner.invoke(cli, ["show", "my-idea", "--dir", str(tmp_path)])
    assert result.exit_code == 0
    assert "Hello" in result.output


def test_compare_two_reports(tmp_path: Path) -> None:
    for name in ("idea-a", "idea-b"):
        d = tmp_path / name
        d.mkdir()
        (d / "score.json").write_text(json.dumps({"score": 7, "components": {}, "rationale": "ok"}))
        (d / "input.json").write_text(json.dumps({"idea": name}))
    runner = CliRunner()
    result = runner.invoke(cli, ["compare", "idea-a", "idea-b", "--dir", str(tmp_path)])
    assert result.exit_code == 0
    assert "idea-a" in result.output
    assert "idea-b" in result.output


def test_compare_missing_report(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["compare", "x", "y", "--dir", str(tmp_path)])
    assert result.exit_code != 0


def test_analyze_invalid_output_dir() -> None:
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["analyze", "--idea", "test", "--output-dir", "/"],
    )
    assert result.exit_code != 0
    assert "invalid output directory" in (result.output + (result.stderr if hasattr(result, "stderr") else "")).lower()


def test_schema_is_valid_json() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["schema"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert "IdeaInput" in parsed
    assert "Score" in parsed


def test_analyze_marker_storm_exit_22() -> None:
    storm_idea = "<UNTRUSTED_INPUT>" * 17 + " real idea"
    runner = CliRunner()
    result = runner.invoke(cli, ["analyze", "--idea", storm_idea])
    assert result.exit_code == 22
    assert "marker storm" in (result.output + (result.stderr if hasattr(result, "stderr") else "")).lower()


def test_analyze_invalid_output_dir_exit_10() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["analyze", "--idea", "test", "--output-dir", "/"])
    assert result.exit_code == 10
    assert "invalid output directory" in (result.output + (result.stderr if hasattr(result, "stderr") else "")).lower()


def test_show_missing_report_exit_20(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["show", "does-not-exist", "--dir", str(tmp_path)])
    assert result.exit_code == 20


def test_make_llm_refuses_anthropic_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.delenv("IDEA_VALIDATOR_REAL_LLM", raising=False)
    from idea_validator.llm import make_llm

    with pytest.raises(RuntimeError, match="subscription-only"):
        make_llm("sonnet")
