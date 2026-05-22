"""QA Engineer rank-brainstorm-candidates intent."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from agents.qa_engineer.agent import QAEngineerAgent
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
    """Same shape as the MR test's stub. Just returns the structured dict."""

    def __init__(self, structured: dict[str, Any] | None) -> None:
        self._structured = structured

    async def invoke(self, **kwargs: Any) -> LLMResponse:
        return LLMResponse(
            text=json.dumps(self._structured) if self._structured else "",
            structured=self._structured,
            tools_used=[],
            session_id="sid",
            tokens=TokensUsage(input=10, output=10, cached_input=0, model="claude-sonnet-4-6"),
            cost_estimate_cents=1,
            duration_ms=100,
            validated_against_schema=True,
            raw={},
        )

    async def reset_session(self, session_id: str) -> None:
        return None


def _brainstorm_md(niche: str, slugs: list[str]) -> str:
    """Minimal brainstorm artifact — just enough for QA to glob+open."""
    parts = [f"# Brainstorm — {niche}", "", "## All candidates", ""]
    for i, slug in enumerate(slugs):
        parts.append(f"### Title {i} (`{slug}`)")
        parts.append("")
        parts.append(f"- **Scores**: composite {10 + i}/25")
        parts.append("")
    return "\n".join(parts)


@pytest.mark.asyncio
async def test_qa_rank_brainstorm_writes_combined_ranking_with_explicit_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When inputs.brainstorm_artifacts is explicitly provided, QA reads from those paths."""
    monkeypatch.setattr("agents.qa_engineer.agent._REPO_ROOT", tmp_path)
    monkeypatch.setattr(
        "agents.qa_engineer.agent._RANKING_DIR",
        tmp_path / "docs" / "products" / "_candidates",
    )

    cands_dir = tmp_path / "docs" / "products" / "_candidates"
    cands_dir.mkdir(parents=True)
    artifacts: list[str] = []
    for niche in ("dev_tools", "b2b_smb", "creator_tools"):
        path = cands_dir / f"_brainstorm_{niche}.md"
        path.write_text(_brainstorm_md(niche, [f"{niche}-{i}" for i in range(5)]))
        artifacts.append(f"docs/products/_candidates/_brainstorm_{niche}.md")

    rank_payload = {
        "intent_completed": "rank_brainstorm_candidates",
        "ranking_summary": "15 candidates ranked; top-3 listed.",
        "top_3_overall": ["dev_tools-4", "b2b_smb-4", "creator_tools-4"],
    }
    agent = QAEngineerAgent(llm=_StubLLM(rank_payload))

    msg = AgentMessage(
        correlation_id=uuid4(),
        sender=AgentId.TEAM_LEAD,
        recipient=AgentId.QA_ENGINEER,
        message_type=MessageType.TASK_ASSIGNMENT,
        priority=Priority.P2,
        payload=TaskAssignmentPayload(
            task_id=uuid4(),
            title="Rank brainstorm candidates",
            description="Merge and rank.",
            inputs={
                "intent": "rank_brainstorm_candidates",
                "brainstorm_artifacts": artifacts,
            },
        ),
    )

    outputs = await agent.handle(msg)

    assert outputs[0].payload.status == TaskStatus.DONE
    ranking = cands_dir / "_combined_ranking.md"
    assert ranking.exists(), "_combined_ranking.md must be written"
    text = ranking.read_text()
    for slug in ("dev_tools-4", "b2b_smb-4", "creator_tools-4"):
        assert slug in text


@pytest.mark.asyncio
async def test_qa_rank_brainstorm_fallback_glob_when_artifacts_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When inputs.brainstorm_artifacts is absent, QA globs _brainstorm_*.md from _RANKING_DIR."""
    monkeypatch.setattr("agents.qa_engineer.agent._REPO_ROOT", tmp_path)
    monkeypatch.setattr(
        "agents.qa_engineer.agent._RANKING_DIR",
        tmp_path / "docs" / "products" / "_candidates",
    )

    cands_dir = tmp_path / "docs" / "products" / "_candidates"
    cands_dir.mkdir(parents=True)
    for niche in ("dev_tools", "b2b_smb"):
        (cands_dir / f"_brainstorm_{niche}.md").write_text(
            _brainstorm_md(niche, [f"{niche}-{i}" for i in range(5)])
        )

    rank_payload = {
        "intent_completed": "rank_brainstorm_candidates",
        "ranking_summary": "10 candidates ranked.",
        "top_3_overall": ["dev_tools-4", "b2b_smb-4", "dev_tools-3"],
    }
    agent = QAEngineerAgent(llm=_StubLLM(rank_payload))

    msg = AgentMessage(
        correlation_id=uuid4(),
        sender=AgentId.TEAM_LEAD,
        recipient=AgentId.QA_ENGINEER,
        message_type=MessageType.TASK_ASSIGNMENT,
        priority=Priority.P2,
        payload=TaskAssignmentPayload(
            task_id=uuid4(),
            title="Rank brainstorm candidates",
            description="Merge and rank.",
            inputs={"intent": "rank_brainstorm_candidates"},  # no brainstorm_artifacts
        ),
    )

    outputs = await agent.handle(msg)
    assert outputs[0].payload.status == TaskStatus.DONE
    ranking = cands_dir / "_combined_ranking.md"
    assert ranking.exists()
    text = ranking.read_text()
    assert "_brainstorm_dev_tools.md" in text or "dev_tools-4" in text


@pytest.mark.asyncio
async def test_qa_existing_intent_still_works() -> None:
    """Regression — existing single-suite QA path unchanged when intent is absent."""
    rank_payload = {
        "suite_passed": True,
        "summary": "All 42 tests pass.",
        "tests_run": 42,
        "tests_failed": 0,
        "coverage_pct": 91,
        "failures": [],
    }
    agent = QAEngineerAgent(llm=_StubLLM(rank_payload))
    msg = AgentMessage(
        correlation_id=uuid4(),
        sender=AgentId.TEAM_LEAD,
        recipient=AgentId.QA_ENGINEER,
        message_type=MessageType.TASK_ASSIGNMENT,
        priority=Priority.P2,
        payload=TaskAssignmentPayload(
            task_id=uuid4(),
            title="Run QA on Backend artifact",
            description="Run tests.",
            inputs={},
        ),
    )
    outputs = await agent.handle(msg)
    assert outputs[0].payload.status == TaskStatus.DONE
