"""iter-26a real-LLM smoke for MR brainstorm-niche mode.

Cost target: ≤ $0.80. Run on demand:

    uv run pytest tests/integration/test_mr_brainstorm_one_niche_real_llm.py --real-llm -v

Excluded from CI. iter-26a uses this for adversarial prompt-tuning, not
regression. Acceptance criteria are checked end-to-end against the real
`claude -p` subscription pipeline:

- Agent returns TaskStatus.DONE (i.e. WebFetch fired, JSON validated
  against BRAINSTORM_NICHE_SCHEMA, top-3 ⊂ candidates, composite_score
  cross-check passed).
- The brainstorm Markdown artifact was written to
  docs/products/_candidates/_brainstorm_dev_tools.md (or wherever
  _BRAINSTORM_DIR was redirected for the test).

Owner runs this manually after Tasks 1-10 land; not part of automated
acceptance.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import uuid4

import pytest

from agents.market_researcher.agent import MarketResearcherAgent
from core.llm.claude_code_headless import ClaudeCodeHeadlessClient
from core.messaging.schemas import (
    AgentId,
    AgentMessage,
    MessageType,
    Priority,
    TaskAssignmentPayload,
    TaskReportPayload,
    TaskStatus,
)

if TYPE_CHECKING:
    from pathlib import Path


@pytest.mark.integration
@pytest.mark.real_llm
@pytest.mark.asyncio
async def test_mr_brainstorm_dev_tools_real_llm(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Real `claude -p` smoke — 5 dev_tools candidates."""
    monkeypatch.setattr("agents.market_researcher.agent._REPO_ROOT", tmp_path)
    monkeypatch.setattr(
        "agents.market_researcher.agent._BRAINSTORM_DIR",
        tmp_path / "docs" / "products" / "_candidates",
    )

    llm = ClaudeCodeHeadlessClient()
    agent = MarketResearcherAgent(llm=llm)

    msg = AgentMessage(
        correlation_id=uuid4(),
        sender=AgentId.TEAM_LEAD,
        recipient=AgentId.MARKET_RESEARCHER,
        message_type=MessageType.TASK_ASSIGNMENT,
        priority=Priority.P2,
        payload=TaskAssignmentPayload(
            task_id=uuid4(),
            title="Brainstorm 5 dev_tools candidates",
            description=(
                "Brainstorm 5 monetizable dev_tools candidates. "
                "Constraints: solo developer, ≤6 months TTFR, "
                "≤$3/day product LLM-opex."
            ),
            inputs={
                "mode": "brainstorm_niche",
                "niche": "dev_tools",
                "candidates": 5,
                "constraints": {
                    "solo_developer": True,
                    "max_time_to_first_revenue_months": 6,
                    "max_product_llm_opex_usd_per_day": 3,
                    "monetization_preferences": ["subscription", "per-seat", "usage"],
                },
            },
        ),
    )

    outputs = await agent.handle(msg)

    assert outputs, "MR returned no outputs"
    report = outputs[0].payload
    assert isinstance(report, TaskReportPayload)
    assert report.status == TaskStatus.DONE, f"expected DONE, got {report.status}: {report.summary}"
    assert any("_brainstorm_dev_tools.md" in a for a in report.artifacts), (
        f"missing brainstorm artifact path; got {report.artifacts}"
    )

    written = tmp_path / "docs" / "products" / "_candidates" / "_brainstorm_dev_tools.md"
    assert written.exists(), f"brainstorm file not written at {written}"
    text = written.read_text()
    assert "Brainstorm — dev_tools" in text
