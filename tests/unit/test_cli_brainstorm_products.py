"""ai-team brainstorm-products builds the correct request body."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import httpx
import respx
from click.testing import CliRunner

if TYPE_CHECKING:
    from pathlib import Path

from apps.cli.main import cli


@respx.mock
def test_brainstorm_products_posts_intent_inputs(tmp_path: Path) -> None:
    constraints = tmp_path / "constraints.json"
    constraints.write_text(
        json.dumps(
            {
                "solo_developer": True,
                "max_product_llm_opex_usd_per_day": 3,
            }
        )
    )

    route = respx.post("http://localhost:8000/api/tasks").mock(
        return_value=httpx.Response(
            200,
            json={
                "task_id": "00000000-0000-0000-0000-000000000001",
                "correlation_id": "00000000-0000-0000-0000-000000000002",
                "status": "in_progress",
            },
        )
    )

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "brainstorm-products",
            "--niches",
            "dev_tools,b2b_smb,creator_tools",
            "--candidates-per-niche",
            "5",
            "--constraints-json",
            str(constraints),
        ],
    )

    assert result.exit_code == 0, result.output
    assert route.called

    body = json.loads(route.calls.last.request.content)
    assert body["inputs"]["intent"] == "brainstorm_products"
    assert body["inputs"]["niches"] == ["dev_tools", "b2b_smb", "creator_tools"]
    assert body["inputs"]["candidates_per_niche"] == 5
    assert body["inputs"]["constraints"]["solo_developer"] is True


@respx.mock
def test_brainstorm_products_empty_niches_rejected(tmp_path: Path) -> None:
    """Missing-niches edge case."""
    constraints = tmp_path / "constraints.json"
    constraints.write_text("{}")

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "brainstorm-products",
            "--niches",
            "",
            "--candidates-per-niche",
            "5",
            "--constraints-json",
            str(constraints),
        ],
    )
    assert result.exit_code != 0
