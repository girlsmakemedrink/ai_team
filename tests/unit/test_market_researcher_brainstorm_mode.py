"""End-to-end mode-dispatch in MR's handle() + build_outputs()."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from agents.market_researcher.agent import MarketResearcherAgent
from core.llm.base import LLMResponse, TokensUsage
from core.messaging.schemas import (
    AgentId,
    AgentMessage,
    MessageType,
    Priority,
    TaskAssignmentPayload,
    TaskStatus,
)


class _StubLLM:
    def __init__(self, structured: dict[str, Any]) -> None:
        self._structured = structured

    async def invoke(self, **kwargs: object) -> LLMResponse:
        return LLMResponse(
            text=json.dumps(self._structured),
            structured=self._structured,
            tools_used=[],
            session_id="stub-session",
            tokens=TokensUsage(input=100, output=200, model="claude-sonnet-4-6"),
            cost_estimate_cents=4,
            duration_ms=1000,
            validated_against_schema=True,
            raw={},
        )

    async def reset_session(self, session_id: str) -> None:
        return None


def _brainstorm_response(niche: str) -> dict[str, Any]:
    def cand(i: int) -> dict[str, Any]:
        return {
            "title": f"{niche.title()} idea {i}",
            "slug": f"{niche}-idea-{i}",
            "one_paragraph": "x" * 30,
            "target_buyer": "y",
            "monetization": "subscription",
            "known_competitors": [{"name": "C", "positioning": "p"}],
            "scores": {
                "tam_signal": 3,
                "solo_fit": 3,
                "llm_opex_fit": 3,
                "defensibility": 3,
                "time_to_first_revenue": 3,
            },
            "composite_score": 15,
            "rationale": "r",
        }

    return {
        "niche": niche,
        "candidates": [cand(i) for i in range(5)],
        "researcher_top_3_slugs": [f"{niche}-idea-{i}" for i in range(3)],
        "research_sources_used": ["https://example.com/a"],
    }


def _assignment(niche: str, mode: str | None = "brainstorm_niche") -> AgentMessage:
    inputs: dict[str, object] = {"niche": niche, "candidates": 5, "constraints": {}}
    if mode is not None:
        inputs["mode"] = mode
    return AgentMessage(
        correlation_id=uuid4(),
        sender=AgentId.TEAM_LEAD,
        recipient=AgentId.MARKET_RESEARCHER,
        message_type=MessageType.TASK_ASSIGNMENT,
        priority=Priority.P2,
        payload=TaskAssignmentPayload(
            task_id=uuid4(),
            title=f"Brainstorm {niche}",
            description="Brainstorm 5 candidates",
            inputs=inputs,
        ),
    )


@pytest.mark.asyncio
async def test_brainstorm_mode_writes_to_products_candidates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("agents.market_researcher.agent._REPO_ROOT", tmp_path)
    monkeypatch.setattr(
        "agents.market_researcher.agent._BRAINSTORM_DIR",
        tmp_path / "docs" / "products" / "_candidates",
    )

    llm = _StubLLM(_brainstorm_response("dev_tools"))
    agent = MarketResearcherAgent(llm=llm)
    msg = _assignment("dev_tools")

    outputs = await agent.handle(msg)

    assert len(outputs) == 1
    report = outputs[0].payload
    assert report.status == TaskStatus.DONE
    assert any("_brainstorm_dev_tools.md" in a for a in report.artifacts)

    written = (
        tmp_path / "docs" / "products" / "_candidates" / "_brainstorm_dev_tools.md"
    ).read_text()
    assert "Brainstorm — dev_tools" in written


@pytest.mark.asyncio
async def test_brainstorm_mode_invalid_top_3_fails_cleanly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("agents.market_researcher.agent._REPO_ROOT", tmp_path)
    monkeypatch.setattr(
        "agents.market_researcher.agent._BRAINSTORM_DIR",
        tmp_path / "docs" / "products" / "_candidates",
    )

    bad = _brainstorm_response("dev_tools")
    bad["researcher_top_3_slugs"] = ["does-not-exist", "x", "y"]
    llm = _StubLLM(bad)
    agent = MarketResearcherAgent(llm=llm)

    outputs = await agent.handle(_assignment("dev_tools"))

    assert outputs[0].payload.status == TaskStatus.FAILED
    assert (
        "top_3" in outputs[0].payload.summary.lower()
        or "slug" in outputs[0].payload.summary.lower()
    )


@pytest.mark.asyncio
async def test_brainstorm_composite_score_mismatch_fails_cleanly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """composite_score must equal sum of axis scores (cross-validation guard)."""
    monkeypatch.setattr("agents.market_researcher.agent._REPO_ROOT", tmp_path)
    monkeypatch.setattr(
        "agents.market_researcher.agent._BRAINSTORM_DIR",
        tmp_path / "docs" / "products" / "_candidates",
    )

    bad = _brainstorm_response("dev_tools")
    bad["candidates"][0]["composite_score"] = 7  # axes sum to 15
    llm = _StubLLM(bad)
    agent = MarketResearcherAgent(llm=llm)

    outputs = await agent.handle(_assignment("dev_tools"))

    assert outputs[0].payload.status == TaskStatus.FAILED
    assert "composite" in outputs[0].payload.summary.lower()


@pytest.mark.asyncio
async def test_single_scan_mode_still_works(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression — the existing single-scan path must keep working when mode is absent."""
    monkeypatch.setattr("agents.market_researcher.agent._REPO_ROOT", tmp_path)
    monkeypatch.setattr(
        "agents.market_researcher.agent._IDEAS_DIR",
        tmp_path / "docs" / "sandbox" / "ideas",
    )

    scan: dict[str, Any] = {
        "title": "Single-scan probe",
        "slug": "single-scan-probe",
        "summary": "short",
        "competitors": [],
        "market_size": "n/a",
        "top_risks": ["r1"],
        "top_opportunities": ["o1"],
        "viability_score": 5,
        "score_rationale": "ok",
    }
    llm = _StubLLM(scan)
    agent = MarketResearcherAgent(llm=llm)

    msg = AgentMessage(
        correlation_id=uuid4(),
        sender=AgentId.TEAM_LEAD,
        recipient=AgentId.MARKET_RESEARCHER,
        message_type=MessageType.TASK_ASSIGNMENT,
        priority=Priority.P2,
        payload=TaskAssignmentPayload(
            task_id=uuid4(),
            title="Scan one idea",
            description="Scan",
            inputs={},
        ),
    )

    outputs = await agent.handle(msg)

    assert outputs[0].payload.status == TaskStatus.DONE
    assert (
        tmp_path / "docs" / "sandbox" / "ideas" / "single-scan-probe.md"
    ).exists()
