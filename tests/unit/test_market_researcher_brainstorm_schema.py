"""BRAINSTORM_NICHE_SCHEMA + renderer for the brainstorm-niche mode."""

from __future__ import annotations

from typing import Any

import jsonschema  # type: ignore[import-untyped]
import pytest

from agents.market_researcher.agent import (
    BRAINSTORM_NICHE_SCHEMA,
    _render_brainstorm_markdown,
)


def _valid_brainstorm() -> dict[str, Any]:
    candidate = {
        "title": "AI commit-message generator",
        "slug": "ai-commit-message-generator",
        "one_paragraph": (
            "Reads `git diff --staged`, emits Conventional Commit messages via a local model."
        ),
        "target_buyer": "Solo developers and small dev teams.",
        "monetization": "subscription",
        "known_competitors": [
            {
                "name": "Co-author Pro",
                "url": "https://example.com",
                "positioning": "JetBrains plugin",
            }
        ],
        "scores": {
            "tam_signal": 4,
            "solo_fit": 5,
            "llm_opex_fit": 4,
            "defensibility": 2,
            "time_to_first_revenue": 4,
        },
        "composite_score": 19,
        "rationale": "Strong solo fit; weak moat.",
    }
    return {
        "niche": "dev_tools",
        "candidates": [dict(candidate, slug=f"cand-{i}") for i in range(5)],
        "researcher_top_3_slugs": ["cand-0", "cand-1", "cand-2"],
        "research_sources_used": ["https://news.ycombinator.com/item?id=1"],
    }


def test_valid_brainstorm_passes_schema() -> None:
    jsonschema.validate(_valid_brainstorm(), BRAINSTORM_NICHE_SCHEMA)


def test_unknown_niche_rejected() -> None:
    bad = _valid_brainstorm()
    bad["niche"] = "fintech"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, BRAINSTORM_NICHE_SCHEMA)


def test_four_candidates_rejected() -> None:
    bad = _valid_brainstorm()
    bad["candidates"] = bad["candidates"][:4]
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, BRAINSTORM_NICHE_SCHEMA)


def test_six_candidates_rejected() -> None:
    bad = _valid_brainstorm()
    extra = dict(bad["candidates"][0], slug="cand-5")
    bad["candidates"] = [*bad["candidates"], extra]
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, BRAINSTORM_NICHE_SCHEMA)


def test_composite_score_out_of_range_rejected() -> None:
    bad = _valid_brainstorm()
    bad["candidates"][0]["composite_score"] = 26
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, BRAINSTORM_NICHE_SCHEMA)


def test_score_axis_out_of_range_rejected() -> None:
    bad = _valid_brainstorm()
    bad["candidates"][0]["scores"]["tam_signal"] = 6
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, BRAINSTORM_NICHE_SCHEMA)


def test_render_brainstorm_markdown_contains_each_candidate_title() -> None:
    md = _render_brainstorm_markdown(_valid_brainstorm())
    assert "# Brainstorm — dev_tools" in md
    assert "## Researcher top-3" in md
    for cand in _valid_brainstorm()["candidates"]:
        assert cand["title"] in md
    assert "https://news.ycombinator.com" in md
