"""End-to-end: TaskAssignment(target_repo=...) → dispatcher → BaseAgent →
recording LLM. iter-29c.

@pytest.mark.integration — stays out of the default unit run.
Pre-clones into tmp_path workspace (NOT ~/.ai_team/workspaces/).
Skips if `gh auth status` fails.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from agents._base import BaseAgent
from core.dispatcher.dispatcher import AgentDispatcher
from core.llm.base import LLMResponse, TokensUsage
from core.messaging.schemas import (
    AgentId,
    AgentMessage,
    MessageType,
    Priority,
    TaskAssignmentPayload,
)


def _gh_authed() -> bool:
    try:
        result = subprocess.run(["gh", "auth", "status"], capture_output=True, check=False)
        return result.returncode == 0
    except FileNotFoundError:
        return False


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not _gh_authed(), reason="requires `gh auth login`"),
    pytest.mark.skipif(shutil.which("git") is None, reason="requires git"),
]


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

    def build_outputs(self, response: LLMResponse, incoming: AgentMessage) -> list[AgentMessage]:
        return []

    def system_prompt(self) -> str:
        return "system"


async def test_cross_repo_dispatch_threads_workspace_to_llm(tmp_path: Path) -> None:
    """Submit a TaskAssignment(target_repo=...) and confirm the
    dispatcher + BaseAgent threaded workspace cwd + AI_TEAM_REPO_ROOT
    down to the recording LLM."""
    from core.target_repo.github import GitHubTargetRepo

    # Pre-clone into tmp_path/workspaces/ to avoid touching ~/.ai_team/.
    workspaces = tmp_path / "workspaces"
    workspaces.mkdir()
    repo = GitHubTargetRepo(
        "girlsmakemedrink/telegram-tech-publisher", workspaces_dir=workspaces
    )
    workspace = await repo.ensure_local_clone()
    assert (workspace / ".git").is_dir()

    llm = _RecordingLLM()
    agent = _DummyAgent(llm=llm)

    dispatcher = AgentDispatcher(
        bus=AsyncMock(),
        feed=AsyncMock(),
        audit=AsyncMock(),
        signer=AsyncMock(),
        agents={AgentId.BACKEND_DEVELOPER: agent},
        ai_team_root=tmp_path,
    )

    msg = AgentMessage(
        correlation_id=uuid4(),
        sender=AgentId.USER,
        recipient=AgentId.BACKEND_DEVELOPER,
        message_type=MessageType.TASK_ASSIGNMENT,
        priority=Priority.P2,
        payload=TaskAssignmentPayload(
            task_id=uuid4(),
            title="probe",
            description="any",
            target_repo="girlsmakemedrink/telegram-tech-publisher",
        ),
    )

    # Stub the registry to return our pre-cloned repo so the test
    # doesn't re-clone under ~/.ai_team/.
    with patch(
        "core.dispatcher.dispatcher.resolve_target_repo",
        return_value=repo,
    ):
        await dispatcher._maybe_resolve_target_repo_workspace(msg)
        assert msg.metadata.get("target_repo_workspace") == str(workspace)
        await agent._invoke_with_retries(
            msg=msg, system_prompt="sp", user_message="um"
        )

    assert len(llm.calls) == 1
    call = llm.calls[0]
    assert call["cwd"] == str(workspace)
    assert call["env"]["AI_TEAM_REPO_ROOT"] == str(workspace)
