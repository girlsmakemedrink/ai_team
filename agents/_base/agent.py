"""BaseAgent abstract class with a default LLM-backed handle().

See ADR-001 (orchestrator), ADR-004 (per-agent tool allowlist), ADR-006
(model tier per agent), ADR-008 (LLMClient adapter).

Concrete agents override:
    - role (ClassVar)
    - model_tier (ClassVar; default "sonnet")
    - allowed_tools (ClassVar tuple)
    - system_prompt_path (ClassVar)
    - build_outputs(response, incoming) — pure function returning AgentMessages

For agents that don't follow the simple "one LLM call → some output messages"
shape (e.g. Team Lead with periodic checkpoints), override handle() entirely.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, ClassVar

import structlog
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from core.llm.base import LLMTimeoutError, ModelTier
from core.security.sanitizer import wrap_untrusted

if TYPE_CHECKING:
    from core.messaging.schemas import AgentId, AgentMessage

if TYPE_CHECKING:
    from pathlib import Path

    from core.llm.base import LLMClient, LLMResponse

_log = structlog.get_logger(__name__)


class BaseAgent(ABC):
    """Abstract base for all agents.

    Subclasses set the class-level config and implement `build_outputs`.
    The default `handle()` does: load system prompt → wrap_untrusted on
    payload → LLM invoke → build_outputs.
    """

    role: ClassVar[AgentId]
    model_tier: ClassVar[ModelTier] = "sonnet"
    allowed_tools: ClassVar[tuple[str, ...]] = ()
    disallowed_tools: ClassVar[tuple[str, ...]] = ()
    system_prompt_path: ClassVar[Path]
    max_turns: ClassVar[int] = 8
    llm_timeout_s: ClassVar[int] = 120
    max_concurrent: ClassVar[int] = 1  # serial per agent by default

    def __init__(self, *, llm: LLMClient) -> None:
        self._llm = llm
        self._cached_prompt: str | None = None
        self._log = _log.bind(agent=self.role.value)

    def system_prompt(self) -> str:
        if self._cached_prompt is None:
            self._cached_prompt = self.system_prompt_path.read_text()
        return self._cached_prompt

    async def handle(self, msg: AgentMessage) -> list[AgentMessage]:
        """Default LLM-backed processing. Subclasses can override."""
        user_msg = self._user_message_for(msg)
        response = await self._invoke_with_retries(
            system_prompt=self.system_prompt(),
            user_message=user_msg,
            session_key=str(msg.correlation_id),
        )
        return self.build_outputs(response, msg)

    @abstractmethod
    def build_outputs(
        self, response: LLMResponse, incoming: AgentMessage
    ) -> list[AgentMessage]:
        """Translate the LLM response into outbound AgentMessages."""

    # ----- helpers subclasses may override -----

    def _user_message_for(self, msg: AgentMessage) -> str:
        """Build the user message text from the incoming payload.

        Default: serialise the payload as JSON, wrap in <UNTRUSTED_INPUT>.
        Subclasses can override for richer prompts.
        """
        payload_json = json.dumps(
            msg.payload.model_dump(mode="json"), ensure_ascii=False
        )
        return (
            f"You received a message of type `{msg.message_type.value}` from "
            f"`{msg.sender.value}` (correlation `{msg.correlation_id}`). "
            f"Payload follows.\n\n{wrap_untrusted(payload_json)}"
        )

    async def _invoke_with_retries(
        self,
        *,
        system_prompt: str,
        user_message: str,
        session_key: str | None = None,
    ) -> LLMResponse:
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(3),
            wait=wait_exponential_jitter(initial=1, max=20),
            retry=retry_if_exception_type(LLMTimeoutError),
            reraise=True,
        ):
            with attempt:
                return await self._llm.invoke(
                    system_prompt=system_prompt,
                    user_message=user_message,
                    model=self.model_tier,
                    allowed_tools=self.allowed_tools,
                    disallowed_tools=self.disallowed_tools,
                    session_id=session_key,
                    timeout_s=self.llm_timeout_s,
                    max_turns=self.max_turns,
                )
        # Unreachable: AsyncRetrying with reraise=True always returns or raises.
        raise RuntimeError("unreachable")
