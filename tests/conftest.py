"""Shared pytest fixtures."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import Iterator


@pytest.fixture(scope="session", autouse=True)
def _ensure_test_env() -> Iterator[None]:
    """Provide dummy values for required settings, so importing core.config
    works in tests without a .env file."""
    os.environ.setdefault("OWNER_TOKEN", "test-token-32-chars-aaaaaaaaaaaaaaaaa")
    os.environ.setdefault("HMAC_SECRET", "test-secret-32-chars-bbbbbbbbbbbbbbbb")
    yield


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--real-llm",
        action="store_true",
        default=False,
        help="Run tests marked real_llm against real `claude -p` (uses subscription quota).",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if config.getoption("--real-llm"):
        return
    skip_real = pytest.mark.skip(reason="needs --real-llm")
    for item in items:
        if "real_llm" in item.keywords:
            item.add_marker(skip_real)
