"""validate-product CLI: extracts the slug's section from a brainstorm
file, loads constraints JSON, posts inputs.intent='validate_product'."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from click.testing import CliRunner

from apps.cli.main import _extract_candidate_section, cli

if TYPE_CHECKING:
    from pathlib import Path


SAMPLE_BRAINSTORM = """# Brainstorm: creator_tools — 5 Candidates

Generated: 2026-05-22 | Niche: creator_tools

## 1. AI Content Engine for Telegram Developer Channels

**Slug:** telegram-tech-publisher
**Monetization:** subscription
**Target Buyer:** Developer-influencers running Telegram channels.

**One Paragraph:** Telegram is the dominant technical content platform.

**Scores:** tam_signal=3, solo_fit=5, llm_opex_fit=5, defensibility=4, time_to_first_revenue=5
**Composite:** 22

## 2. Another Idea

**Slug:** ai-technical-repurposer
**Monetization:** subscription

**One Paragraph:** Different content.
"""


def test_extracts_slug_section_exact_match() -> None:
    section = _extract_candidate_section(SAMPLE_BRAINSTORM, "telegram-tech-publisher")
    assert section.startswith("## 1. AI Content Engine for Telegram")
    assert "**Slug:** telegram-tech-publisher" in section
    assert "Composite:** 22" in section
    # Stops before the next H2.
    assert "ai-technical-repurposer" not in section


def test_extracts_second_section_when_slug_matches_it() -> None:
    section = _extract_candidate_section(SAMPLE_BRAINSTORM, "ai-technical-repurposer")
    assert section.startswith("## 2. Another Idea")
    assert "**Slug:** ai-technical-repurposer" in section
    # Should not include the first idea.
    assert "telegram-tech-publisher" not in section


def test_raises_on_unknown_slug() -> None:
    with pytest.raises(ValueError, match="not found"):
        _extract_candidate_section(SAMPLE_BRAINSTORM, "no-such-slug")


def test_raises_on_empty_file() -> None:
    with pytest.raises(ValueError):
        _extract_candidate_section("", "any-slug")


def _write_constraints(tmp_path: Path) -> Path:
    p = tmp_path / "constraints.json"
    p.write_text(json.dumps({"owner_profile": "solo_developer", "max_total_dev_time_weeks": 12}))
    return p


def _write_brainstorm(tmp_path: Path) -> Path:
    p = tmp_path / "brainstorm.md"
    p.write_text(SAMPLE_BRAINSTORM)
    return p


def test_validate_product_posts_with_expected_inputs(tmp_path: Path) -> None:
    brainstorm = _write_brainstorm(tmp_path)
    constraints = _write_constraints(tmp_path)

    fake_resp = MagicMock()
    fake_resp.status_code = 200
    fake_resp.json.return_value = {"task_id": str(uuid4()), "correlation_id": str(uuid4())}

    with patch("apps.cli.main.httpx.post", return_value=fake_resp) as post_mock:
        result = CliRunner().invoke(
            cli,
            [
                "validate-product",
                "--slug",
                "telegram-tech-publisher",
                "--candidate-file",
                str(brainstorm),
                "--depth",
                "standard",
                "--constraints-json",
                str(constraints),
            ],
            env={"OWNER_TOKEN": "test-token"},
        )

    assert result.exit_code == 0, result.output
    post_mock.assert_called_once()
    posted_json = post_mock.call_args.kwargs["json"]
    assert posted_json["title"] == "Validate product: telegram-tech-publisher"
    assert "**Slug:** telegram-tech-publisher" in posted_json["description"]
    # API rejects lowercase "p2" with 422 (Priority enum is P1..P4).
    assert posted_json["priority"] == "P2"
    inputs = posted_json["inputs"]
    assert inputs["intent"] == "validate_product"
    assert inputs["slug"] == "telegram-tech-publisher"
    assert inputs["depth"] == "standard"
    assert inputs["constraints"]["owner_profile"] == "solo_developer"
    assert "candidate_brief" in inputs
    assert inputs["candidate_brief"].startswith("## 1. AI Content Engine for Telegram")


def test_validate_product_rejects_unknown_slug(tmp_path: Path) -> None:
    brainstorm = _write_brainstorm(tmp_path)
    constraints = _write_constraints(tmp_path)

    result = CliRunner().invoke(
        cli,
        [
            "validate-product",
            "--slug",
            "no-such-slug",
            "--candidate-file",
            str(brainstorm),
            "--constraints-json",
            str(constraints),
        ],
        env={"OWNER_TOKEN": "test-token"},
    )
    assert result.exit_code != 0
    assert "not found" in result.output.lower()


def test_validate_product_rejects_constraints_that_arent_dict(tmp_path: Path) -> None:
    brainstorm = _write_brainstorm(tmp_path)
    bad_constraints = tmp_path / "bad_constraints.json"
    bad_constraints.write_text(json.dumps([1, 2, 3]))  # valid JSON, not a dict

    result = CliRunner().invoke(
        cli,
        [
            "validate-product",
            "--slug",
            "telegram-tech-publisher",
            "--candidate-file",
            str(brainstorm),
            "--constraints-json",
            str(bad_constraints),
        ],
        env={"OWNER_TOKEN": "test-token"},
    )
    assert result.exit_code != 0
    assert "constraints json" in result.output.lower()
    assert "object" in result.output.lower() or "dict" in result.output.lower()
