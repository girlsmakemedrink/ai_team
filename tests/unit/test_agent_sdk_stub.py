import pytest

from core.llm.agent_sdk_stub import ClaudeAgentSDKClient


async def test_invoke_not_implemented() -> None:
    client = ClaudeAgentSDKClient()
    with pytest.raises(NotImplementedError, match="subscription-auth"):
        await client.invoke(system_prompt="x", user_message="y")


async def test_reset_session_not_implemented() -> None:
    client = ClaudeAgentSDKClient()
    with pytest.raises(NotImplementedError):
        await client.reset_session("s")
