"""BaseAgent abstract class. See ADR-001, ADR-004, ADR-006.

Concrete agents (TeamLead, ProductManager, ...) land in Iteration 1+.
This is the contract every agent satisfies.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import ClassVar

import structlog

from core.llm.base import LLMClient, ModelTier
from core.messaging.schemas import AgentId, AgentMessage

_log = structlog.get_logger(__name__)


class BaseAgent(ABC):
    """Abstract base for all agents.

    Concrete subclasses declare role, default model tier, allowed tools,
    and the path to their system prompt. They implement `handle()` to
    process one incoming `AgentMessage` and return outgoing messages.

    The orchestrator owns: receive-from-bus, HMAC verify, audit-log
    write, dispatch to `handle()`, sign + publish outputs. Agents own:
    the LLM call(s) and any reasoning that happens within a single
    received-message turn.
    """

    role: ClassVar[AgentId]
    model_tier: ClassVar[ModelTier] = "sonnet"
    allowed_tools: ClassVar[tuple[str, ...]] = ()
    disallowed_tools: ClassVar[tuple[str, ...]] = ()
    system_prompt_path: ClassVar[Path]
    max_turns: ClassVar[int] = 8

    def __init__(self, *, llm: LLMClient) -> None:
        self._llm = llm
        self._cached_prompt: str | None = None
        self._log = _log.bind(agent=self.role.value)

    def system_prompt(self) -> str:
        if self._cached_prompt is None:
            self._cached_prompt = self.system_prompt_path.read_text()
        return self._cached_prompt

    @abstractmethod
    async def handle(self, msg: AgentMessage) -> list[AgentMessage]:
        """Process one incoming message; return outgoing messages.

        Implementations should:
        1. Validate the message is for this agent (or BROADCAST).
        2. Build a user-message prompt from msg.payload (sanitised via
           wrap_untrusted() for any externally-sourced content).
        3. Call `self._llm.invoke(...)` with this agent's tier, allowed
           tools, and (optionally) session_id keyed on correlation_id.
        4. Parse the response (text or structured JSON) into outgoing
           AgentMessage objects.
        5. Return the list. The orchestrator publishes them.
        """
