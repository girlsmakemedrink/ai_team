"""Future backend: Claude Agent SDK. See ADR-008.

Currently stubbed out: Claude Agent SDK requires API-key auth (no
subscription auth path confirmed for our case as of 2026-05-18), and
the owner's constraint is subscription-only. Re-enable once Anthropic
ships subscription auth for the SDK *and* its usage counts against the
same Max 5x programmatic quota as `claude -p`.

Tracking: revisit by 2026-09-01 or sooner if Anthropic announces.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

    from core.llm.base import LLMResponse, ModelTier


class ClaudeAgentSDKClient:
    async def invoke(
        self,
        *,
        system_prompt: str,
        user_message: str,
        model: ModelTier = "sonnet",
        allowed_tools: Sequence[str] = (),
        disallowed_tools: Sequence[str] = (),
        session_id: str | None = None,
        mcp_config_path: str | None = None,
        timeout_s: int = 120,
        max_turns: int = 8,
    ) -> LLMResponse:
        raise NotImplementedError(
            "Claude Agent SDK backend pending subscription-auth support; "
            "use ClaudeCodeHeadlessClient. See ADR-008."
        )

    async def reset_session(self, session_id: str) -> None:
        raise NotImplementedError
