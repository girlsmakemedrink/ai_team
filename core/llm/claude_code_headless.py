"""`claude -p` subprocess backend for LLMClient. See ADR-008.

Uses subscription auth: the `claude` CLI must already be logged in
(see `claude /login` or device-code flow). NO ANTHROPIC_API_KEY is read
or required.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from typing import TYPE_CHECKING, Any

import structlog

from core.llm.base import (
    DEFAULT_MAX_BUDGET_USD_PER_TIER,
    LLMInvocationError,
    LLMResponse,
    LLMTimeoutError,
    ModelTier,
    TokensUsage,
    ToolUse,
    estimate_cost_cents,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

_log = structlog.get_logger(__name__)


_DEFAULT_MODEL_IDS: dict[ModelTier, str] = {
    "haiku": "claude-haiku-4-5",
    "sonnet": "claude-sonnet-4-6",
    "opus": "claude-opus-4-7",
}


def _resolve_model_id(tier: ModelTier) -> str:
    env_key = f"LLM_MODEL_{tier.upper()}"
    return os.environ.get(env_key, _DEFAULT_MODEL_IDS[tier])


class ClaudeCodeHeadlessClient:
    """Async wrapper around `claude -p ... --output-format json`.

    Notes on the underlying CLI (verified against `claude --help`,
    Claude Code 2.1.143):

    - System prompt is passed via `--append-system-prompt <string>`
      (arg, not file). argv on macOS allows ~256 KB total, so 10 KB
      prompts are fine. We use `create_subprocess_exec` (no shell), so
      special chars in args are not interpolated.
    - `--max-turns` is **not** an available flag. We rely on
      `--max-budget-usd` for hard budget enforcement and on the agent's
      own prompt to bound turns.
    - Session resumption: `--resume <uuid>` reattaches to a previous
      conversation. We use it for prompt caching across turns within
      one `(agent, correlation)` tree.
    - Sessions persist under `~/.claude` unless `--no-session-persistence`
      is set. We let them persist for resumption.
    """

    def __init__(self, *, binary: str = "claude") -> None:
        self._binary = binary

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
        max_turns: int = 8,  # kept for protocol compat; not passed to CLI
        json_schema: dict[str, Any] | None = None,
        max_budget_usd: float | None = None,
    ) -> LLMResponse:
        model_id = _resolve_model_id(model)
        effective_budget = (
            max_budget_usd if max_budget_usd is not None else DEFAULT_MAX_BUDGET_USD_PER_TIER[model]
        )

        cmd: list[str] = [
            self._binary,
            "-p",
            user_message,
            "--output-format",
            "json",
            "--model",
            model_id,
            "--append-system-prompt",
            system_prompt,
            "--max-budget-usd",
            f"{effective_budget:.4f}",
        ]
        if allowed_tools:
            cmd += ["--allowed-tools", ",".join(allowed_tools)]
        if disallowed_tools:
            cmd += ["--disallowed-tools", ",".join(disallowed_tools)]
        if session_id:
            cmd += ["--resume", session_id]
        if mcp_config_path:
            cmd += ["--mcp-config", mcp_config_path]
        if json_schema is not None:
            cmd += ["--json-schema", json.dumps(json_schema, separators=(",", ":"))]

        log = _log.bind(
            model=model_id,
            has_session=bool(session_id),
            tool_count=len(allowed_tools),
            user_msg_len=len(user_message),
            sys_prompt_len=len(system_prompt),
        )
        log.info("llm.invoke.start")
        start = time.perf_counter()

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError as e:
            raise LLMInvocationError(
                f"`{self._binary}` not found on PATH; install Claude Code CLI"
            ) from e

        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
        except TimeoutError as e:
            proc.kill()
            await proc.wait()
            raise LLMTimeoutError(f"claude -p timed out after {timeout_s}s") from e

        duration_ms = int((time.perf_counter() - start) * 1000)

        if proc.returncode != 0:
            err = stderr.decode(errors="replace")[:1000]
            log.error("llm.invoke.failed", returncode=proc.returncode, stderr=err)
            raise LLMInvocationError(f"claude -p exited {proc.returncode}: {err}")

        response = self._parse_response(stdout, model_id=model_id, duration_ms=duration_ms)
        log.info(
            "llm.invoke.ok",
            duration_ms=duration_ms,
            tokens_in=response.tokens.input,
            tokens_out=response.tokens.output,
            cost_cents=response.cost_estimate_cents,
        )
        return response

    async def reset_session(self, session_id: str) -> None:
        """No-op: claude sessions are file-backed and expire naturally."""
        _log.debug("llm.reset_session.noop", session_id=session_id)

    # ----- internals -----

    def _parse_response(
        self,
        raw_stdout: bytes,
        *,
        model_id: str,
        duration_ms: int,
    ) -> LLMResponse:
        try:
            data: dict[str, Any] = json.loads(raw_stdout.decode())
        except json.JSONDecodeError as e:
            preview = raw_stdout[:500]
            raise LLMInvocationError(f"claude -p emitted non-JSON output: {preview!r}") from e

        if data.get("is_error", False):
            raise LLMInvocationError(
                f"claude -p reported error: {data.get('result', '<no detail>')!r}"
            )

        usage_raw: dict[str, int] = data.get("usage") or {}
        tokens = TokensUsage(
            input=int(usage_raw.get("input_tokens", 0)),
            output=int(usage_raw.get("output_tokens", 0)),
            cached_input=int(usage_raw.get("cache_read_input_tokens", 0)),
            model=model_id,
        )

        text: str = str(data.get("result", ""))
        structured = self._maybe_parse_json(text)

        tools_used: list[ToolUse] = []
        for t in data.get("tools_used", []):
            if not isinstance(t, dict):
                continue
            output_summary = t.get("output_summary")
            tools_used.append(
                ToolUse(
                    name=str(t.get("name", "")),
                    input=t.get("input", {}) or {},
                    output_summary=(
                        str(output_summary)[:500] if output_summary is not None else None
                    ),
                )
            )

        return LLMResponse(
            text=text,
            structured=structured,
            tools_used=tools_used,
            session_id=str(data.get("session_id", "")),
            tokens=tokens,
            cost_estimate_cents=estimate_cost_cents(model_id, tokens),
            duration_ms=duration_ms,
            raw=data,
        )

    @staticmethod
    def _maybe_parse_json(text: str) -> dict[str, Any] | None:
        """Try to extract a top-level JSON object from the model's text.

        Accepts either: (a) the entire text is a JSON object, or
        (b) a fenced ```json ... ``` block. Returns None otherwise.
        Agents that need structured output should pass `--json-schema`
        and read `LLMResponse.structured`.
        """
        stripped = text.strip()
        if stripped.startswith("{") and stripped.endswith("}"):
            try:
                value = json.loads(stripped)
                return value if isinstance(value, dict) else None
            except json.JSONDecodeError:
                pass
        if "```json" in text:
            try:
                start = text.index("```json") + len("```json")
                end = text.index("```", start)
                inner = text[start:end].strip()
                value = json.loads(inner)
                return value if isinstance(value, dict) else None
            except (ValueError, json.JSONDecodeError):
                pass
        return None
