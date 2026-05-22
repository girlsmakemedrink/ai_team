#!/usr/bin/env bash
# iter-29c smoke: dispatcher → BaseAgent → recording LLM, against
# girlsmakemedrink/telegram-tech-publisher. Confirms the workspace
# path threads to cwd + AI_TEAM_REPO_ROOT. Real `claude -p` NOT
# invoked. Real `ensure_local_clone` IS invoked against
# ~/.ai_team/workspaces/.

set -euo pipefail

cd "$(dirname "$0")/.."

if ! gh auth status >/dev/null 2>&1; then
  echo "ERROR: gh auth status failed. Run 'gh auth login' first." >&2
  exit 1
fi

uv run python - <<'PY'
import asyncio
from pathlib import Path
from uuid import uuid4
from unittest.mock import AsyncMock

from agents._base import BaseAgent
from core.dispatcher.dispatcher import AgentDispatcher
from core.llm.base import LLMResponse, TokensUsage
from core.messaging.schemas import (
    AgentId, AgentMessage, MessageType, Priority, TaskAssignmentPayload,
)


class _RecordingLLM:
    def __init__(self):
        self.calls = []

    async def invoke(self, **kwargs):
        self.calls.append(kwargs)
        return LLMResponse(
            text='ok', session_id='s',
            tokens=TokensUsage(input=0, output=0, model='mock'),
            duration_ms=0,
        )

    async def reset_session(self, session_id):
        return None


class _DummyAgent(BaseAgent):
    role = AgentId.BACKEND_DEVELOPER
    system_prompt_path = Path('/dev/null')
    allowed_tools = ()
    def build_outputs(self, response, incoming): return []
    def system_prompt(self): return 'system'


async def main():
    llm = _RecordingLLM()
    agent = _DummyAgent(llm=llm)
    dispatcher = AgentDispatcher(
        bus=AsyncMock(), feed=AsyncMock(), audit=AsyncMock(), signer=AsyncMock(),
        agents={AgentId.BACKEND_DEVELOPER: agent},
    )
    msg = AgentMessage(
        correlation_id=uuid4(),
        sender=AgentId.USER,
        recipient=AgentId.BACKEND_DEVELOPER,
        message_type=MessageType.TASK_ASSIGNMENT,
        priority=Priority.P2,
        payload=TaskAssignmentPayload(
            task_id=uuid4(), title='probe', description='d',
            target_repo='girlsmakemedrink/telegram-tech-publisher',
        ),
    )
    await dispatcher._maybe_resolve_target_repo_workspace(msg)
    workspace = msg.metadata.get('target_repo_workspace', '<missing>')
    print(f'resolved workspace: {workspace}')
    await agent._invoke_with_retries(msg=msg, system_prompt='sp', user_message='um')
    call = llm.calls[0]
    print(f"llm.invoke cwd: {call['cwd']}")
    print(f"llm.invoke env.AI_TEAM_REPO_ROOT: {call['env'].get('AI_TEAM_REPO_ROOT')}")
    assert call['cwd'] == workspace, f"cwd mismatch: {call['cwd']!r} != {workspace!r}"
    assert call['env'].get('AI_TEAM_REPO_ROOT') == workspace, 'env mismatch'
    print('SMOKE OK')


asyncio.run(main())
PY
