# ruff: noqa: E501
"""iter-26b real-LLM smoke for MR validate_competitors mode at depth=quick.

Cost target: ~$0.50-1.50. Run on demand:

    uv run pytest tests/integration/test_validator_one_agent_real_llm.py --real-llm -v

Excluded from CI. iter-26b uses this for adversarial prompt-tuning of
the validate_competitors mode against real `claude -p` before the full
4-agent demo run. Acceptance criteria checked end-to-end:

- Agent returns TaskStatus.DONE (i.e. WebFetch fired if available, JSON
  validated against VALIDATE_COMPETITORS_SCHEMA, competitors_found >= 3
  at depth=quick).
- The competitors Markdown artifact was written to
  docs/products/<slug>/competitors.md (or wherever _VALIDATE_DIR was
  redirected for the test).

Owner runs this manually before invoking scripts/demo_iter_26b.sh.
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


CANDIDATE_BRIEF = """## 1. AI Content Engine for Telegram Developer Channels

**Slug:** telegram-tech-publisher
**Monetization:** subscription
**Target Buyer:** Developer-influencers running Telegram channels (500-100k subscribers) in Russian-speaking and global developer communities who want to post consistently without writing each post manually.
**One Paragraph:** Telegram is the dominant technical content platform in the CIS developer community. This tool monitors the creator's specified sources (GitHub, RSS, Hacker News) and drafts 3-5 Telegram-formatted posts per day in the creator's established voice, including code blocks, inline links, and optional Telegra.ph long-reads for deep dives.

**Scores:** tam_signal=3, solo_fit=5, llm_opex_fit=5, defensibility=4, time_to_first_revenue=5
**Composite:** 22

**Known Competitors:**
- Buffer (https://buffer.com)
- Typefully (https://typefully.com)
"""


@pytest.mark.integration
@pytest.mark.real_llm
@pytest.mark.asyncio
async def test_mr_validate_competitors_quick_depth_real_llm(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Real `claude -p` smoke — MR validate_competitors at depth=quick."""
    monkeypatch.setattr("agents.market_researcher.agent._REPO_ROOT", tmp_path)
    monkeypatch.setattr(
        "agents.market_researcher.agent._VALIDATE_DIR",
        tmp_path / "docs" / "products",
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
            title="Validate competitors: telegram-tech-publisher",
            description=CANDIDATE_BRIEF,
            inputs={
                "intent": "validate_competitors",
                "slug": "telegram-tech-publisher",
                "depth": "quick",
                "candidate_brief": CANDIDATE_BRIEF,
                "target_market": "developer_influencers_telegram_500_to_100k_subs",
                "constraints": {
                    "owner_profile": "solo_developer",
                    "monetization_model": "subscription",
                    "max_product_llm_opex_usd_per_day_per_user": 3,
                },
            },
        ),
    )

    outputs = await agent.handle(msg)

    assert outputs, "MR returned no outputs"
    report = outputs[0].payload
    assert isinstance(report, TaskReportPayload)
    assert report.status == TaskStatus.DONE, f"expected DONE, got {report.status}: {report.summary}"
    assert any("competitors.md" in a for a in report.artifacts), (
        f"missing competitors artifact path; got {report.artifacts}"
    )

    written = tmp_path / "docs" / "products" / "telegram-tech-publisher" / "competitors.md"
    assert written.exists(), f"competitors file not written at {written}"
    text = written.read_text()
    assert "Competitor scan: telegram-tech-publisher" in text
    assert "Verdict:" in text or "verdict:" in text.lower()
    print(f"\n--- Real-LLM competitors.md (first 2000 chars) ---\n{text[:2000]}")
