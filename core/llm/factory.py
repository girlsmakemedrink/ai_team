"""LLM client factory. See ADR-008."""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

from core.llm.claude_code_headless import ClaudeCodeHeadlessClient
from core.llm.mock import MockLLMClient

if TYPE_CHECKING:
    from core.llm.base import LLMClient


def make_llm_client(*, mock_fixtures_dir: Path | None = None) -> LLMClient:
    """Resolve the LLMClient backend per AI_TEAM_LLM_BACKEND env var.

    - "claude_p" (default): real ClaudeCodeHeadlessClient → `claude -p`.
    - "mock": MockLLMClient with fixtures (lenient by default).

    Tests should construct their own LLMClient instance and inject it
    rather than relying on this factory.
    """
    backend = os.environ.get("AI_TEAM_LLM_BACKEND", "claude_p")
    if backend == "claude_p":
        return ClaudeCodeHeadlessClient()
    if backend == "mock":
        if mock_fixtures_dir is None:
            mock_fixtures_dir = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "llm"
        return MockLLMClient(mock_fixtures_dir, strict=False)
    raise ValueError(f"Unknown AI_TEAM_LLM_BACKEND={backend!r}; expected 'claude_p' or 'mock'.")
