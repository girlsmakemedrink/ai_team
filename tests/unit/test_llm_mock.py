import json
from pathlib import Path

import pytest

from core.llm.base import LLMInvocationError, LLMResponse, TokensUsage
from core.llm.mock import MockLLMClient


@pytest.fixture
def fixture_dir(tmp_path: Path) -> Path:
    return tmp_path


def _make_response_json() -> dict[str, object]:
    return LLMResponse(
        text="hi",
        structured=None,
        tools_used=[],
        session_id="sess-1",
        tokens=TokensUsage(input=10, output=2, model="mock-sonnet"),
        cost_estimate_cents=0,
        duration_ms=5,
        raw={"mock": True},
    ).model_dump()


async def test_returns_fixture_when_present(fixture_dir: Path) -> None:
    client = MockLLMClient(fixture_dir, strict=True)
    key = MockLLMClient._make_key("sys", "user")
    (fixture_dir / f"{key}.json").write_text(json.dumps(_make_response_json()))
    resp = await client.invoke(system_prompt="sys", user_message="user")
    assert resp.text == "hi"
    assert resp.session_id == "sess-1"


async def test_strict_raises_on_missing(fixture_dir: Path) -> None:
    client = MockLLMClient(fixture_dir, strict=True)
    with pytest.raises(LLMInvocationError, match="missing fixture"):
        await client.invoke(system_prompt="sys", user_message="unmatched")


async def test_lenient_returns_placeholder(fixture_dir: Path) -> None:
    client = MockLLMClient(fixture_dir, strict=False)
    resp = await client.invoke(system_prompt="sys", user_message="anything")
    assert resp.text.startswith("[mock]")


async def test_records_calls(fixture_dir: Path) -> None:
    client = MockLLMClient(fixture_dir, strict=False)
    await client.invoke(system_prompt="a", user_message="b")
    await client.invoke(system_prompt="c", user_message="d", model="haiku")
    assert len(client.calls) == 2
    assert client.calls[1]["model"] == "haiku"
