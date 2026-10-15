"""LLMClient Protocol, MockLLMClient, and factory (ADR-0008, ADR-0019, ADR-0021)."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class LLMClient(Protocol):
    async def invoke(
        self,
        system_prompt: str,
        user_message: str,
        json_schema: dict[str, Any] | None = None,
    ) -> dict[str, Any]: ...


class MockLLMClient:
    """Returns canned responses keyed by substring match on system_prompt."""

    def __init__(
        self,
        responses: dict[str, dict[str, Any]] | None = None,
        fixture_dir: Path | None = None,
    ) -> None:
        self._responses = responses or {}
        self._fixture_dir = fixture_dir

    async def invoke(
        self,
        system_prompt: str,
        user_message: str,
        json_schema: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        sp_lower = system_prompt.lower()
        for key, value in self._responses.items():
            if key.lower() in sp_lower:
                return value
        if self._fixture_dir:
            import json
            for f in self._fixture_dir.glob("*.json"):
                if f.stem.lower() in sp_lower:
                    return json.loads(f.read_text())
        return {}


class ClaudeCodeHeadlessClient:
    """Wraps claude -p subprocess per ADR-0008 (real LLM path)."""

    def __init__(self, default_model_tier: str = "sonnet", timeout_s: int = 120) -> None:
        self._tier = default_model_tier
        self._timeout_s = timeout_s

    async def invoke(
        self,
        system_prompt: str,
        user_message: str,
        json_schema: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        raise NotImplementedError("ClaudeCodeHeadlessClient not implemented in sandbox v2")


def make_llm(tier: str = "sonnet") -> LLMClient:
    if os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError(
            "idea-validator is subscription-only; ANTHROPIC_API_KEY must not be set"
        )
    if os.environ.get("IDEA_VALIDATOR_REAL_LLM") == "1":
        return ClaudeCodeHeadlessClient(default_model_tier=tier, timeout_s=120)
    return MockLLMClient(
        fixture_dir=Path(__file__).parent.parent.parent / "tests" / "fixtures" / "llm"
    )
