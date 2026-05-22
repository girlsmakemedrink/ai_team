"""Unit tests for Pydantic models (ADR-0019 US-1)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from idea_validator.models import (
    ReportBundle,
    Score,
    StageError,
)


def test_score_valid_range() -> None:
    s = Score(score=5, components={"a": 3}, rationale="ok")
    assert s.score == 5


def test_score_below_range() -> None:
    with pytest.raises(ValidationError):
        Score(score=0, components={}, rationale="x")


def test_score_above_range() -> None:
    with pytest.raises(ValidationError):
        Score(score=11, components={}, rationale="x")


def test_stage_error_message_capped_at_200() -> None:
    long_msg = "x" * 500
    err = StageError(stage="scoring", kind="transport", message=long_msg)
    assert len(err.message) == 200


def test_stage_error_rejects_secret_fragment() -> None:
    with pytest.raises(ValidationError):
        StageError(stage="scoring", kind="transport", message="BRAVE_API_KEY=abc")


def test_report_bundle_write_to_dir_creates_seven_files(
    tmp_path: Path, sample_bundle: ReportBundle
) -> None:
    out = tmp_path / "report"
    sample_bundle.write_to_dir(out)
    expected = {"input.json", "competitors.json", "market.md", "risks.md",
                "differentiators.md", "score.json", "report.md"}
    written = {f.name for f in out.iterdir()}
    assert expected == written


def test_report_bundle_score_json_shape(tmp_path: Path, sample_bundle: ReportBundle) -> None:
    out = tmp_path / "report"
    sample_bundle.write_to_dir(out)
    data = json.loads((out / "score.json").read_text())
    assert isinstance(data["score"], int)
    assert 1 <= data["score"] <= 10
    assert data["components"]
    assert data["rationale"]


def test_report_bundle_competitors_json_shape(tmp_path: Path, sample_bundle: ReportBundle) -> None:
    out = tmp_path / "report"
    sample_bundle.write_to_dir(out)
    data = json.loads((out / "competitors.json").read_text())
    assert 3 <= len(data["items"]) <= 5
    for item in data["items"]:
        assert item["name"]
        assert item["url"]
        assert item["positioning"]


def test_report_bundle_default_report_md_contains_links(
    tmp_path: Path, sample_bundle: ReportBundle
) -> None:
    sample_bundle.report_md = ""
    out = tmp_path / "report"
    sample_bundle.write_to_dir(out)
    content = (out / "report.md").read_text()
    for fname in ("input.json", "competitors.json", "market.md", "risks.md",
                  "differentiators.md", "score.json"):
        assert fname in content
