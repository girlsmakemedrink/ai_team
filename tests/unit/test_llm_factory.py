"""Tests for the LLMClient factory."""

from __future__ import annotations

from pathlib import Path  # noqa: TC003  used at runtime in test signature

import pytest

from core.llm.claude_code_headless import ClaudeCodeHeadlessClient
from core.llm.factory import make_llm_client
from core.llm.mock import MockLLMClient


def test_default_returns_claude_code_headless(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AI_TEAM_LLM_BACKEND", raising=False)
    client = make_llm_client()
    assert isinstance(client, ClaudeCodeHeadlessClient)


def test_explicit_claude_p(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_TEAM_LLM_BACKEND", "claude_p")
    client = make_llm_client()
    assert isinstance(client, ClaudeCodeHeadlessClient)


def test_mock_backend(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AI_TEAM_LLM_BACKEND", "mock")
    client = make_llm_client(mock_fixtures_dir=tmp_path)
    assert isinstance(client, MockLLMClient)


def test_mock_backend_default_dir(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_TEAM_LLM_BACKEND", "mock")
    client = make_llm_client()  # default fixture dir
    assert isinstance(client, MockLLMClient)


def test_unknown_backend_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_TEAM_LLM_BACKEND", "nonsense")
    with pytest.raises(ValueError, match="Unknown AI_TEAM_LLM_BACKEND"):
        make_llm_client()
