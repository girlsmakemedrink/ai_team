"""FastAPI unit-level smoke tests (routes that don't need DB/Redis).

The DB-touching endpoints (/api/tasks, /api/reviews, /api/digest) are
covered by tests/integration/test_apps_api_live.py with testcontainers.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from apps.api.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_health_returns_ok(client: TestClient) -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_metrics_returns_prometheus_text(client: TestClient) -> None:
    resp = client.get("/metrics")
    assert resp.status_code == 200
    assert "text/plain" in resp.headers["content-type"]
    assert "subscription_quota_used_pct" in resp.text


def test_tasks_requires_owner_token(client: TestClient) -> None:
    resp = client.post("/api/tasks", json={"title": "x", "description": "y"})
    assert resp.status_code == 401


def test_tasks_rejects_wrong_token(client: TestClient) -> None:
    resp = client.post(
        "/api/tasks",
        json={"title": "x", "description": "y"},
        headers={"Authorization": "Bearer wrong-token"},
    )
    assert resp.status_code == 401


def test_reviews_requires_owner_token(client: TestClient) -> None:
    resp = client.get("/api/reviews")
    assert resp.status_code == 401


def test_digest_requires_owner_token(client: TestClient) -> None:
    resp = client.get("/api/digest")
    assert resp.status_code == 401
