"""Local LLMClient Protocol — mirrors core/llm/base.py. See ADR-0008/0011/0021."""
from __future__ import annotations

import asyncio
import json
import os
from typing import Any, Literal, Protocol


class LLMResponse:
    def __init__(self, structured: dict[str, Any] | None, text: str = "") -> None:
        self.structured = structured
        self.text = text


class LLMClient(Protocol):
    async def invoke(
        self,
        *,
        system_prompt: str,
        user_message: str,
        json_schema: dict[str, Any] | None = None,
    ) -> LLMResponse: ...


class MockLLMClient:
    """Returns canned structured responses keyed by stage name in system_prompt."""

    def __init__(self, responses: dict[str, dict[str, Any]] | None = None) -> None:
        self._responses: dict[str, dict[str, Any]] = responses or {}

    async def invoke(
        self,
        *,
        system_prompt: str,
        user_message: str,
        json_schema: dict[str, Any] | None = None,
    ) -> LLMResponse:
        for key, data in self._responses.items():
            if key in system_prompt:
                return LLMResponse(structured=data)
        return LLMResponse(structured={}, text="(mock: no matching key)")


class HeadlessLLMClient:
    """Calls `claude -p` subprocess. Used when IDEA_VALIDATOR_REAL_LLM=1."""

    def __init__(self, model_tier: str = "sonnet") -> None:
        model_map = {
            "haiku": "claude-haiku-4-5-20251001",
            "sonnet": "claude-sonnet-4-6",
            "opus": "claude-opus-4-7",
        }
        self._model = model_map.get(model_tier, "claude-sonnet-4-6")

    async def invoke(
        self,
        *,
        system_prompt: str,
        user_message: str,
        json_schema: dict[str, Any] | None = None,
    ) -> LLMResponse:
        cmd = [
            "claude", "-p",
            "--output-format", "json",
            "--model", self._model,
            "--max-turns", "2",
            "--system-prompt", system_prompt,
        ]
        if json_schema:
            cmd += ["--json-schema", json.dumps(json_schema)]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate(user_message.encode())
        raw = json.loads(stdout)
        structured = raw.get("structured_output") or raw.get("result")
        return LLMResponse(structured=structured, text=raw.get("result", ""))


def make_llm(tier: Literal["haiku", "sonnet", "opus"] = "sonnet") -> LLMClient:
    """Factory: raises if ANTHROPIC_API_KEY is set (subscription-only per ADR-0008)."""
    if os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError(
            "idea-validator is subscription-only; ANTHROPIC_API_KEY must not be set"
        )
    if os.environ.get("IDEA_VALIDATOR_REAL_LLM") == "1":
        return HeadlessLLMClient(model_tier=tier)
    return MockLLMClient()
