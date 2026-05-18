"""MockLLMClient — hash-keyed canned responses for unit/integration tests."""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING, Any

from core.llm.base import (
    LLMInvocationError,
    LLMResponse,
    ModelTier,
    TokensUsage,
)

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path


class MockLLMClient:
    """Deterministic LLMClient backed by JSON fixtures on disk.

    Lookup key = sha256(system_prompt || "\\n--\\n" || user_message)[:16].
    Fixture path: <fixture_dir>/<key>.json.

    When a fixture is missing, behaviour depends on `strict`:
    - strict=True (default in CI): raises LLMInvocationError, surfacing
      the missing key + a copy of the inputs to make recording easy.
    - strict=False (local dev): returns a placeholder response.
    """

    def __init__(self, fixture_dir: Path, *, strict: bool = True) -> None:
        self._fixture_dir = fixture_dir
        self._strict = strict
        self._calls: list[dict[str, str]] = []

    @property
    def calls(self) -> list[dict[str, str]]:
        return list(self._calls)

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
        json_schema: dict[str, Any] | None = None,
        max_budget_usd: float | None = None,
    ) -> LLMResponse:
        key = self._make_key(system_prompt, user_message)
        self._calls.append({"key": key, "model": model})

        fixture_path = self._fixture_dir / f"{key}.json"
        if not fixture_path.exists():
            if self._strict:
                raise LLMInvocationError(
                    f"MockLLMClient missing fixture {fixture_path}. "
                    f"Inputs: system={system_prompt[:200]!r}, "
                    f"user={user_message[:200]!r}, model={model}"
                )
            return self._placeholder_response(model)

        data = json.loads(fixture_path.read_text())
        return LLMResponse(**data)

    async def reset_session(self, session_id: str) -> None:
        # No-op: mock is stateless.
        return None

    @staticmethod
    def _make_key(system_prompt: str, user_message: str) -> str:
        h = hashlib.sha256()
        h.update(system_prompt.encode())
        h.update(b"\n--\n")
        h.update(user_message.encode())
        return h.hexdigest()[:16]

    @staticmethod
    def _placeholder_response(model: ModelTier) -> LLMResponse:
        return LLMResponse(
            text="[mock] no fixture; placeholder response",
            structured=None,
            tools_used=[],
            session_id="mock-session",
            tokens=TokensUsage(input=0, output=0, model=f"mock-{model}"),
            cost_estimate_cents=0,
            duration_ms=0,
            raw={"mock": True},
        )
