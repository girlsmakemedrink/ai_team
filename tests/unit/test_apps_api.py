"""FastAPI smoke tests using TestClient."""

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


def test_tasks_accepts_valid_token(client: TestClient) -> None:
    # OWNER_TOKEN comes from tests/conftest.py
    import os

    resp = client.post(
        "/api/tasks",
        json={"title": "Test", "description": "Body"},
        headers={"Authorization": f"Bearer {os.environ['OWNER_TOKEN']}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "task_id" in data
    assert "correlation_id" in data
    assert data["status"] == "queued"


def test_reviews_list_empty_iteration_0(client: TestClient) -> None:
    import os

    resp = client.get(
        "/api/reviews",
        headers={"Authorization": f"Bearer {os.environ['OWNER_TOKEN']}"},
    )
    assert resp.status_code == 200
    assert resp.json() == []


def test_approve_review_returns_status(client: TestClient) -> None:
    import os
    from uuid import uuid4

    review_id = uuid4()
    resp = client.post(
        f"/api/reviews/{review_id}/approve",
        json={"comment": "lgtm"},
        headers={"Authorization": f"Bearer {os.environ['OWNER_TOKEN']}"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "approved"


def test_reject_review_returns_status(client: TestClient) -> None:
    import os
    from uuid import uuid4

    review_id = uuid4()
    resp = client.post(
        f"/api/reviews/{review_id}/reject",
        json={"comment": "no"},
        headers={"Authorization": f"Bearer {os.environ['OWNER_TOKEN']}"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "rejected"
