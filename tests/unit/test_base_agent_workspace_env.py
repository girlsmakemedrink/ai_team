"""BaseAgent workspace env + cwd injection. See iter-29c."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

from agents._base import BaseAgent
from core.llm.base import LLMResponse, TokensUsage
from core.messaging.schemas import (
    AgentId,
    AgentMessage,
    MessageType,
    Priority,
    TaskAssignmentPayload,
)


class _RecordingLLM:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def invoke(self, **kwargs: Any) -> LLMResponse:
        self.calls.append(kwargs)
        return LLMResponse(
            text="ok",
            session_id="s",
            tokens=TokensUsage(input=0, output=0, model="mock"),
            duration_ms=0,
        )

    async def reset_session(self, session_id: str) -> None:
        return None


class _DummyAgent(BaseAgent):
    role = AgentId.BACKEND_DEVELOPER
    system_prompt_path = Path("/dev/null")
    allowed_tools = ()

    def build_outputs(self, response, incoming):  # type: ignore[no-untyped-def]
        return []

    def system_prompt(self) -> str:
        return "system"


def _assignment(*, workspace: str | None = None) -> AgentMessage:
    metadata: dict[str, object] = {}
    if workspace is not None:
        metadata["target_repo_workspace"] = workspace
    return AgentMessage(
        correlation_id=uuid4(),
        sender=AgentId.TEAM_LEAD,
        recipient=AgentId.BACKEND_DEVELOPER,
        message_type=MessageType.TASK_ASSIGNMENT,
        priority=Priority.P2,
        payload=TaskAssignmentPayload(task_id=uuid4(), title="t", description="d"),
        metadata=metadata,
    )


def test_build_env_includes_repo_root_when_workspace_in_metadata() -> None:
    agent = _DummyAgent(llm=_RecordingLLM())
    env = agent._build_env(_assignment(workspace="/tmp/ws-X"))
    assert env["AI_TEAM_REPO_ROOT"] == "/tmp/ws-X"


def test_build_env_omits_repo_root_when_workspace_absent() -> None:
    agent = _DummyAgent(llm=_RecordingLLM())
    env = agent._build_env(_assignment(workspace=None))
    assert "AI_TEAM_REPO_ROOT" not in env


async def test_invoke_passes_cwd_from_metadata() -> None:
    llm = _RecordingLLM()
    agent = _DummyAgent(llm=llm)
    await agent._invoke_with_retries(
        msg=_assignment(workspace="/tmp/ws-Y"),
        system_prompt="sp",
        user_message="um",
    )
    assert llm.calls[0]["cwd"] == "/tmp/ws-Y"
    assert llm.calls[0]["env"]["AI_TEAM_REPO_ROOT"] == "/tmp/ws-Y"


async def test_invoke_cwd_is_none_when_metadata_absent() -> None:
    llm = _RecordingLLM()
    agent = _DummyAgent(llm=llm)
    await agent._invoke_with_retries(
        msg=_assignment(workspace=None),
        system_prompt="sp",
        user_message="um",
    )
    assert llm.calls[0]["cwd"] is None
    assert "AI_TEAM_REPO_ROOT" not in llm.calls[0]["env"]
