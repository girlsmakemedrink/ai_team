"""Tests for MarketResearcherAgent — Sonnet, market scans with WebFetch."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest

from agents.market_researcher import MarketResearcherAgent
from core.llm.base import LLMResponse, TokensUsage
from core.messaging.schemas import (
    AgentId,
    AgentMessage,
    MessageType,
    Priority,
    TaskAssignmentPayload,
    TaskReportPayload,
)

if TYPE_CHECKING:
    from pathlib import Path


class _StubLLM:
    def __init__(self, response: LLMResponse) -> None:
        self._response = response

    async def invoke(self, **kwargs: object) -> LLMResponse:
        return self._response

    async def reset_session(self, session_id: str) -> None:
        return None


def _scan_response(*, slug: str = "ai-tutor-marketplace") -> LLMResponse:
    structured = {
        "title": "AI Tutor Marketplace",
        "slug": slug,
        "summary": "Crowded with Preply/italki + AI-matching layers; viability 5/10.",
        "competitors": [
            {
                "name": "Preply",
                "url": "https://preply.com",
                "positioning": "tutor marketplace, human-led",
            },
            {
                "name": "italki",
                "url": "https://italki.com",
                "positioning": "language tutor marketplace",
            },
        ],
        "market_size": (
            "Global online tutoring TAM ~$300B by 2030; AI-matching slice <not enough public data>"
        ),
        "top_risks": [
            "LLM matching quality",
            "tutor acquisition cost",
            "regulation in EU/RU markets",
        ],
        "top_opportunities": ["AI-matching as differentiator", "subscription model"],
        "viability_score": 5,
        "score_rationale": "Crowded incumbents but AI-matching is a real wedge if quality holds.",
    }
    return LLMResponse(
        text=json.dumps(structured),
        structured=structured,
        tools_used=[],
        session_id="m-sess",
        tokens=TokensUsage(input=120, output=300, model="claude-sonnet-4-6"),
        cost_estimate_cents=6,
        duration_ms=3000,
        validated_against_schema=True,
        raw={},
    )


def _task() -> AgentMessage:
    return AgentMessage(
        correlation_id=uuid4(),
        sender=AgentId.TEAM_LEAD,
        recipient=AgentId.MARKET_RESEARCHER,
        message_type=MessageType.TASK_ASSIGNMENT,
        priority=Priority.P3,
        payload=TaskAssignmentPayload(
            task_id=uuid4(),
            title="Scan the AI tutor marketplace idea",
            description="Investigate competitors, market size, viability.",
        ),
    )


def test_role_and_tier() -> None:
    assert MarketResearcherAgent.role == AgentId.MARKET_RESEARCHER
    assert MarketResearcherAgent.model_tier == "sonnet"


def test_webfetch_is_on_allowlist() -> None:
    """Market Researcher is the only iter-2b agent with WebFetch."""
    assert "WebFetch" in MarketResearcherAgent.allowed_tools


def test_no_raw_bash_write() -> None:
    forbidden = {"Bash", "Write", "Edit", "MultiEdit"}
    assert not (set(MarketResearcherAgent.allowed_tools) & forbidden)


def test_mcp_env_scopes_to_ideas_and_market_dirs() -> None:
    prefixes = MarketResearcherAgent.mcp_env["AI_TEAM_PATH_PREFIXES"]
    assert "docs/sandbox/ideas" in prefixes
    assert "docs/market" in prefixes


@pytest.mark.asyncio
async def test_handle_writes_scan_md_and_reports_to_tl(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ideas_dir = tmp_path / "docs" / "sandbox" / "ideas"
    monkeypatch.setattr("agents.market_researcher.agent._IDEAS_DIR", ideas_dir)

    agent = MarketResearcherAgent(llm=_StubLLM(_scan_response()))
    outputs = await agent.handle(_task())

    payload = outputs[0].payload
    assert isinstance(payload, TaskReportPayload)
    assert payload.status.value == "done"
    assert payload.artifacts == ["docs/sandbox/ideas/ai-tutor-marketplace.md"]
    assert "viability 5/10" in payload.summary

    md = (ideas_dir / "ai-tutor-marketplace.md").read_text()
    assert "Market scan — AI Tutor Marketplace" in md
    assert "Preply" in md and "italki" in md
    assert "AI-matching" in md


@pytest.mark.asyncio
async def test_handle_rejects_invalid_slug(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "agents.market_researcher.agent._IDEAS_DIR", tmp_path / "docs" / "sandbox" / "ideas"
    )
    agent = MarketResearcherAgent(llm=_StubLLM(_scan_response(slug="Bad Slug")))
    payload = (await agent.handle(_task()))[0].payload
    assert isinstance(payload, TaskReportPayload)
    assert payload.status.value == "failed"


@pytest.mark.asyncio
async def test_handle_fails_on_missing_structured() -> None:
    bad = LLMResponse(
        text="",
        structured=None,
        tools_used=[],
        session_id="x",
        tokens=TokensUsage(input=1, output=1, model="claude-sonnet-4-6"),
        cost_estimate_cents=0,
        duration_ms=1,
        validated_against_schema=False,
        raw={},
    )
    agent = MarketResearcherAgent(llm=_StubLLM(bad))
    payload = (await agent.handle(_task()))[0].payload
    assert isinstance(payload, TaskReportPayload)
    assert payload.status.value == "failed"


@pytest.mark.asyncio
async def test_handle_skips_non_task_assignment() -> None:
    agent = MarketResearcherAgent(llm=_StubLLM(_scan_response()))
    other = AgentMessage(
        correlation_id=uuid4(),
        sender=AgentId.TEAM_LEAD,
        recipient=AgentId.MARKET_RESEARCHER,
        message_type=MessageType.QUESTION,
        priority=Priority.P3,
        payload={"kind": "question", "question_id": str(uuid4()), "text": "hi"},
    )
    assert await agent.handle(other) == []
