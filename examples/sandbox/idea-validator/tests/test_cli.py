"""CLI command tests (ADR-0019 US-2, ADR-0021 exit codes)."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from click.testing import CliRunner

from idea_validator.cli import cli
from idea_validator.models import ReportBundle


def test_schema_exits_0() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["schema"])
    assert result.exit_code == 0
    assert "IdeaInput" in result.output


def test_list_reports_empty_dir(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["list-reports", "--dir", str(tmp_path)])
    assert result.exit_code == 0


def test_list_reports_with_entries(tmp_path: Path) -> None:
    (tmp_path / "my-idea-20260101").mkdir()
    runner = CliRunner()
    result = runner.invoke(cli, ["list-reports", "--dir", str(tmp_path)])
    assert result.exit_code == 0
    assert "my-idea-20260101" in result.output


def test_list_reports_nonexistent_dir() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["list-reports", "--dir", "/nonexistent/path/xyz"])
    assert result.exit_code == 0
    assert "No reports found" in result.output


def test_show_not_found(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["show", "nonexistent", "--dir", str(tmp_path)])
    assert result.exit_code == 20


def test_show_found(tmp_path: Path) -> None:
    d = tmp_path / "my-report"
    d.mkdir()
    (d / "report.md").write_text("# Hello\n")
    runner = CliRunner()
    result = runner.invoke(cli, ["show", "my-report", "--dir", str(tmp_path)])
    assert result.exit_code == 0
    assert "Hello" in result.output


def test_compare_not_found(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["compare", "missing1", "missing2", "--dir", str(tmp_path)])
    assert result.exit_code == 20


def test_compare_different_reports(tmp_path: Path) -> None:
    for name, score in (("r1", 5), ("r2", 8)):
        d = tmp_path / name
        d.mkdir()
        (d / "score.json").write_text(json.dumps({"score": score, "components": {}, "rationale": "ok"}))
    runner = CliRunner()
    result = runner.invoke(cli, ["compare", "r1", "r2", "--dir", str(tmp_path)])
    assert result.exit_code == 0
    assert "r1" in result.output
    assert "r2" in result.output


def test_analyze_exit_10_invalid_output_dir(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BRAVE_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    runner = CliRunner()
    result = runner.invoke(
        cli, ["analyze", "--idea", "test", "--depth", "quick", "--output-dir", "/etc/forbidden"]
    )
    assert result.exit_code == 10


def test_analyze_exit_22_marker_storm(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BRAVE_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    storm = "<untrusted_input>" * 20
    runner = CliRunner()
    result = runner.invoke(cli, ["analyze", "--idea", storm, "--depth", "quick"])
    assert result.exit_code == 22


def test_analyze_success_mocked(monkeypatch: pytest.MonkeyPatch, sample_bundle: ReportBundle) -> None:
    monkeypatch.delenv("BRAVE_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    runner = CliRunner()
    with runner.isolated_filesystem():
        with (
            patch("idea_validator.cli.Pipeline") as MockPipeline,
            patch("idea_validator.cli.make_llm"),
            patch("idea_validator.cli.make_search"),
        ):
            mock_pipe = MagicMock()
            mock_pipe.run = AsyncMock(return_value=sample_bundle)
            MockPipeline.return_value = mock_pipe
            result = runner.invoke(
                cli, ["analyze", "--idea", "AI tutoring marketplace", "--depth", "quick", "--output-dir", "out"]
            )
    assert result.exit_code == 0, result.output
