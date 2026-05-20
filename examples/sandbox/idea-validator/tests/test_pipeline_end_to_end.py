"""End-to-end integration tests for the full pipeline."""
from __future__ import annotations

import pytest

from idea_validator.models import ReportBundle
from idea_validator.pipeline import Pipeline


@pytest.mark.asyncio
async def test_pipeline_end_to_end(mock_llm: object, mock_search: object) -> None:
    pipeline = Pipeline(llm=mock_llm, search=mock_search, depth="quick")  # type: ignore[arg-type]
    bundle = await pipeline.run("AI tutoring marketplace")
    assert isinstance(bundle, ReportBundle)
    assert 1 <= bundle.score.score <= 10
    assert len(bundle.competitors.items) >= 3
    assert len(bundle.risks.items) == 3
    assert len(bundle.differentiators.items) == 3
    assert "# Idea Validation Report" in bundle.report_md


@pytest.mark.asyncio
async def test_pipeline_with_frozen_timestamp(mock_llm: object, mock_search: object) -> None:
    from datetime import datetime

    ts = datetime(2026, 1, 1, 0, 0, 0)
    pipeline = Pipeline(llm=mock_llm, search=mock_search, depth="quick")  # type: ignore[arg-type]
    bundle = await pipeline.run("test idea", frozen_timestamp=ts)
    assert bundle.input.created_at == ts


@pytest.mark.asyncio
async def test_pipeline_writes_to_dir(
    mock_llm: object, mock_search: object, tmp_path: object
) -> None:
    import tempfile
    from pathlib import Path

    pipeline = Pipeline(llm=mock_llm, search=mock_search, depth="quick")  # type: ignore[arg-type]
    bundle = await pipeline.run("AI tutoring marketplace")
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "report"
        bundle.write_to_dir(out)
        expected = {"input.json", "competitors.json", "market.md", "risks.md", "differentiators.md", "score.json", "report.md"}
        assert {f.name for f in out.iterdir()} == expected
