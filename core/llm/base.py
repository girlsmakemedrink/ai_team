"""LLMClient Protocol and supporting types. See ADR-008."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from collections.abc import Sequence

ModelTier = Literal["haiku", "sonnet", "opus"]


class LLMError(Exception):
    """Base class for LLM-related failures."""


class LLMTimeoutError(LLMError):
    """Raised when a `claude -p` invocation exceeds the configured timeout."""


class LLMInvocationError(LLMError):
    """Raised when the underlying LLM process exits non-zero or returns
    malformed output."""


class TokensUsage(BaseModel):
    input: int = 0
    output: int = 0
    cached_input: int = 0
    model: str

    model_config = ConfigDict(extra="forbid")

    @property
    def total(self) -> int:
        return self.input + self.output


class ToolUse(BaseModel):
    name: str
    input: dict[str, Any] = Field(default_factory=dict)
    output_summary: str | None = None

    model_config = ConfigDict(extra="forbid")


class LLMResponse(BaseModel):
    text: str
    structured: dict[str, Any] | None = None
    tools_used: list[ToolUse] = Field(default_factory=list)
    session_id: str
    tokens: TokensUsage
    cost_estimate_cents: int = 0
    duration_ms: int
    raw: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")


class LLMClient(Protocol):
    """Async interface to an LLM. Implementations in this package:

    - `ClaudeCodeHeadlessClient` (primary, see `claude_code_headless.py`)
    - `ClaudeAgentSDKClient` (stub for future, see `agent_sdk_stub.py`)
    - `MockLLMClient` (tests, see `mock.py`)
    """

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
    ) -> LLMResponse: ...

    async def reset_session(self, session_id: str) -> None: ...


# Static price table (US cents per 1M input/output tokens).
# Used to compute LLMResponse.cost_estimate_cents. Update when Anthropic
# revises pricing. These are conservative defaults; see ADR-006.
PRICE_TABLE_CENTS_PER_MTOK: dict[str, tuple[int, int]] = {
    # model_id: (input, output)
    "claude-haiku-4-5": (80, 400),
    "claude-sonnet-4-6": (300, 1500),
    "claude-opus-4-7": (1500, 7500),
}


def estimate_cost_cents(model_id: str, tokens: TokensUsage) -> int:
    in_price, out_price = PRICE_TABLE_CENTS_PER_MTOK.get(model_id, (0, 0))
    cents = (tokens.input * in_price + tokens.output * out_price) // 1_000_000
    return int(cents)
