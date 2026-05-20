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
import os
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, ClassVar

import structlog
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from core.llm.base import LLMTimeoutError, MCPUnhealthyError, ModelTier
from core.llm.mcp_health import check_mcp_servers
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
    # 600 s default (was 300 in iter-3..10). iter-11 retro: five
    # subclasses (Backend, Frontend, Architect, Designer, DevOps) were
    # already overriding to 600 — the LLM-bound tier of the team is
    # the majority case. Move the default to the majority value and
    # let the agents that genuinely need ≤300 s (QA, SRE, Market, PM,
    # TL) declare it explicitly. Effective per-agent timeouts are
    # unchanged; pinned in tests/unit/test_agent_timeouts.py.
    llm_timeout_s: ClassVar[int] = 600
    max_concurrent: ClassVar[int] = 1  # serial per agent by default
    # Per-role env merged into claude -p's subprocess env (via LLMClient.invoke
    # env=...). Typically the role-specific AI_TEAM_PATH_PREFIXES / DENY /
    # AI_TEAM_FORBID_PR_BASE_RE so the MCP server spawns with the agent's
    # least-privilege scope. Empty dict = inherit dispatcher's global env
    # (the current iter-2 demo wiring).
    mcp_env: ClassVar[dict[str, str]] = {}

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
        # iter-9: pre-flight MCP health-gate. Catches deterministic
        # startup failures (module import errors, AI_TEAM_REPO_ROOT
        # misconfiguration) before claude -p spawns the MCP server
        # subprocess. Failures route to BLOCKED(mcp_unhealthy) via
        # the dispatcher's iter-9 special-case, dependents stay
        # held instead of cascade-dropping. Silent skip when
        # AI_TEAM_MCP_CONFIG_PATH is unset (mocked-LLM unit tests).
        unhealthy = check_mcp_servers(os.environ.get("AI_TEAM_MCP_CONFIG_PATH"))
        if unhealthy:
            raise MCPUnhealthyError(
                f"MCP servers unhealthy ({len(unhealthy)}): " + "; ".join(unhealthy)
            )
        user_msg = self._user_message_for(msg)
        response = await self._invoke_with_retries(
            system_prompt=self.system_prompt(),
            user_message=user_msg,
            session_key=str(msg.correlation_id),
        )
        outputs = self.build_outputs(response, msg)
        return self._stamp_metrics(outputs, response)

    @abstractmethod
    def build_outputs(self, response: LLMResponse, incoming: AgentMessage) -> list[AgentMessage]:
        """Translate the LLM response into outbound AgentMessages."""

    @staticmethod
    def _stamp_metrics(outputs: list[AgentMessage], response: LLMResponse) -> list[AgentMessage]:
        """Attach per-turn LLM metrics to every output's metadata['llm'].

        Same response object produces N outputs (TL emits 3 sub-task
        assignments from one decomposition turn). Each output carries
        the same metrics — they describe the LLM call that produced
        them, not the message itself.

        The metrics ride in AgentMessage.metadata (already on the
        envelope) so they persist to audit_log.payload_json without
        a schema bump. A single SQL query over the metadata path
        reconstructs the demo report — see scripts/demo_iter_3.sh.
        """
        metrics = {
            "tokens_in": response.tokens.input,
            "tokens_out": response.tokens.output,
            "cached_input": response.tokens.cached_input,
            "cost_cents": response.cost_estimate_cents,
            "duration_ms": response.duration_ms,
            "model": response.tokens.model,
            "validated_against_schema": response.validated_against_schema,
        }
        return [
            out.model_copy(update={"metadata": {**out.metadata, "llm": metrics}}) for out in outputs
        ]

    # ----- helpers subclasses may override -----

    def _user_message_for(self, msg: AgentMessage) -> str:
        """Build the user message text from the incoming payload.

        Default: serialise the payload as JSON, wrap in <UNTRUSTED_INPUT>.
        Subclasses can override for richer prompts.
        """
        payload_json = json.dumps(msg.payload.model_dump(mode="json"), ensure_ascii=False)
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
                    env=dict(self.mcp_env) if self.mcp_env else None,
                )
        # Unreachable: AsyncRetrying with reraise=True always returns or raises.
        raise RuntimeError("unreachable")
