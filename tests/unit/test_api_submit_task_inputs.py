"""SubmitTaskRequest must accept and forward an optional `inputs` dict
so brainstorm-products (and future structured-intent flows) can pass
typed metadata to TL without encoding it in description text."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from apps.api.main import SubmitTaskRequest


def test_inputs_default_is_none() -> None:
    req = SubmitTaskRequest(title="t", description="d")
    assert req.inputs is None


def test_inputs_accepts_dict_with_nested_values() -> None:
    payload = {
        "intent": "brainstorm_products",
        "niches": ["dev_tools", "b2b_smb"],
        "candidates_per_niche": 5,
        "constraints": {"solo_developer": True, "ttfr_max_months": 6},
    }
    req = SubmitTaskRequest(title="t", description="d", inputs=payload)
    assert req.inputs == payload


def test_inputs_rejects_non_dict() -> None:
    with pytest.raises(ValidationError):
        SubmitTaskRequest(title="t", description="d", inputs=["not", "a", "dict"])


def test_submit_task_endpoint_forwards_inputs_to_payload() -> None:
    """Regression: a refactor that drops inputs forwarding must fail this test.

    Exercises the full submit_task endpoint handler via TestClient with all
    external dependencies (DB, Redis, audit) mocked on app.state.
    Asserts the AgentMessage passed to bus.publish carries the original inputs.
    """
    from typing import Any
    from unittest.mock import AsyncMock, MagicMock

    from fastapi.testclient import TestClient
    from pydantic import SecretStr

    from apps.api.main import app
    from core.config import Settings, get_settings

    _TEST_TOKEN = "test-token-replace-me-min-32-chars-xxxx"

    # Override get_settings so require_owner_token uses our known token.
    def fake_settings() -> Settings:
        return Settings(
            owner_token=SecretStr(_TEST_TOKEN),
            hmac_secret=SecretStr("test-hmac-replace-me-min-32-chars-yyyy"),
        )

    captured_msgs: list[Any] = []

    async def fake_publish(msg: Any, *args: Any, **kwargs: Any) -> None:
        captured_msgs.append(msg)

    # Build a session mock whose async context manager is a no-op DB session.
    mock_session = MagicMock()
    mock_session.add = MagicMock()
    mock_session.commit = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    mock_session_factory = MagicMock(return_value=mock_session)

    # signer.with_signature is identity so the captured msg has the full payload.
    mock_signer = MagicMock()
    mock_signer.with_signature = lambda m: m

    mock_bus = MagicMock()
    mock_bus.publish = AsyncMock(side_effect=fake_publish)

    mock_feed = MagicMock()
    mock_feed.publish = AsyncMock()

    mock_audit = MagicMock()
    mock_audit.write_message = AsyncMock()

    app.dependency_overrides[get_settings] = fake_settings
    try:
        # TestClient.__enter__ runs the lifespan, which sets app.state.* from
        # the real infra. Override those attributes inside the `with` block,
        # after lifespan startup but before the request is sent.
        with TestClient(app, raise_server_exceptions=True) as client:
            app.state.session_factory = mock_session_factory
            app.state.signer = mock_signer
            app.state.bus = mock_bus
            app.state.feed = mock_feed
            app.state.audit = mock_audit

            resp = client.post(
                "/api/tasks",
                json={
                    "title": "brainstorm title",
                    "description": "describe brainstorm task",
                    "inputs": {"intent": "brainstorm_products", "niches": ["dev_tools"]},
                },
                headers={"Authorization": f"Bearer {_TEST_TOKEN}"},
            )
            assert resp.status_code == 200, resp.text
    finally:
        app.dependency_overrides.pop(get_settings, None)

    assert captured_msgs, "expected bus.publish to be called at least once"
    forwarded = captured_msgs[0].payload
    assert forwarded.inputs == {"intent": "brainstorm_products", "niches": ["dev_tools"]}
