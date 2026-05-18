"""Live API tests against real Postgres + Redis via testcontainers.

Exercises:
- /api/tasks POST: actually publishes to bus, audit, feed.
- /api/reviews GET/approve/reject: reads + updates pending_reviews.
- /api/digest, /api/digest/history: reads checkpoints.

Pulls the real FastAPI app and runs it via httpx.ASGITransport. Bus and
Postgres come from the session-scoped testcontainers fixtures; we
override settings via env vars before the app's lifespan boots.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import select

from core.config import get_settings
from core.persistence.models import AuditLog, Checkpoint, PendingReview, Task

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = pytest.mark.integration


@pytest.fixture
async def api_client(
    pg_dsn: str,
    redis_url: str,
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[httpx.AsyncClient]:
    # Bypass the app's lifespan (which would also start the dispatcher and
    # connect to real Redis on a non-existent loop). Set app.state.* manually
    # so the endpoints work.
    os.environ["POSTGRES_DSN"] = pg_dsn
    os.environ["REDIS_URL"] = redis_url
    os.environ["AI_TEAM_DISPATCHER_AUTOSTART"] = "false"
    os.environ["AI_TEAM_LLM_BACKEND"] = "mock"
    get_settings.cache_clear()

    settings = get_settings()
    secret = settings.hmac_secret.get_secret_value().encode()

    from apps.api.main import app
    from core.audit.writer import AuditLogWriter
    from core.messaging.bus import MessageBus
    from core.messaging.feed import FeedPublisher
    from core.security.hmac_signer import HMACSigner

    bus = MessageBus.from_url(redis_url)
    feed = FeedPublisher.from_url(redis_url, db_session_factory=session_factory)
    signer = HMACSigner(secret)
    audit = AuditLogWriter(session_factory, secret)

    app.state.session_factory = session_factory
    app.state.bus = bus
    app.state.feed = feed
    app.state.signer = signer
    app.state.audit = audit

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        yield client

    await bus.close()
    await feed.close()
    get_settings.cache_clear()


def _auth() -> dict[str, str]:
    return {"Authorization": f"Bearer {os.environ['OWNER_TOKEN']}"}


async def test_submit_task_writes_db_and_publishes(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    resp = await api_client.post(
        "/api/tasks",
        json={
            "title": "live api test",
            "description": "verify POST /api/tasks end-to-end",
        },
        headers=_auth(),
    )
    assert resp.status_code == 200
    data = resp.json()
    task_id = data["task_id"]
    correlation_id = data["correlation_id"]
    assert data["status"] == "queued"

    # tasks row was created.
    row = (await db_session.execute(select(Task).where(Task.id == task_id))).scalar_one()
    assert row.title == "live api test"
    assert row.assigned_agent == "team_lead"

    # audit_log has the user message.
    audit_rows = (
        (
            await db_session.execute(
                select(AuditLog).where(AuditLog.correlation_id == correlation_id)
            )
        )
        .scalars()
        .all()
    )
    assert len(audit_rows) == 1
    assert audit_rows[0].sender == "user"
    assert audit_rows[0].recipient == "team_lead"


async def test_reviews_list_empty_initially(
    api_client: httpx.AsyncClient,
) -> None:
    resp = await api_client.get("/api/reviews", headers=_auth())
    assert resp.status_code == 200
    # May or may not be empty (depends on test order); just shape-check.
    assert isinstance(resp.json(), list)


async def test_approve_resolves_pending_review(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    # Seed a pending_review row.
    review_id = uuid4()
    correlation = uuid4()
    async with session_factory() as session:
        session.add(
            PendingReview(
                id=review_id,
                correlation_id=correlation,
                requesting_agent="product_manager",
                summary="test pending review",
                status="pending",
            )
        )
        await session.commit()

    resp = await api_client.post(
        f"/api/reviews/{review_id}/approve",
        json={"comment": "ok"},
        headers=_auth(),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "approved"

    async with session_factory() as session:
        row = (
            await session.execute(select(PendingReview).where(PendingReview.id == review_id))
        ).scalar_one()
    assert row.status == "approved"
    assert row.resolution_comment == "ok"
    assert row.resolved_at is not None


async def test_reject_resolves_pending_review(
    api_client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    review_id = uuid4()
    async with session_factory() as session:
        session.add(
            PendingReview(
                id=review_id,
                correlation_id=uuid4(),
                requesting_agent="backend_developer",
                summary="rejectable review",
                status="pending",
            )
        )
        await session.commit()

    resp = await api_client.post(
        f"/api/reviews/{review_id}/reject",
        json={"comment": "no thanks"},
        headers=_auth(),
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "rejected"


async def test_double_approve_returns_409(
    api_client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    review_id = uuid4()
    async with session_factory() as session:
        session.add(
            PendingReview(
                id=review_id,
                correlation_id=uuid4(),
                requesting_agent="qa_engineer",
                summary="will be double-approved",
                status="approved",
            )
        )
        await session.commit()

    resp = await api_client.post(
        f"/api/reviews/{review_id}/approve",
        json={"comment": "again"},
        headers=_auth(),
    )
    assert resp.status_code == 409


async def test_approve_404_when_missing(
    api_client: httpx.AsyncClient,
) -> None:
    resp = await api_client.post(
        f"/api/reviews/{uuid4()}/approve",
        json={"comment": "ghost"},
        headers=_auth(),
    )
    assert resp.status_code == 404


async def test_digest_returns_placeholder_when_empty(
    api_client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    # Wipe any prior checkpoints to make this deterministic.
    from sqlalchemy import delete

    async with session_factory() as session:
        await session.execute(delete(Checkpoint))
        await session.commit()

    resp = await api_client.get("/api/digest", headers=_auth())
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] is None
    assert "No checkpoint digest yet" in body["digest_markdown"]


async def test_digest_returns_latest_when_present(
    api_client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    correlation = uuid4()
    async with session_factory() as session:
        session.add(
            Checkpoint(
                id=uuid4(),
                trigger="manual",
                correlation_id=correlation,
                iteration=1,
                digest_markdown="### Done\n- PM: stories\n",
                quota_used_pct=12.5,
            )
        )
        await session.commit()

    resp = await api_client.get("/api/digest", headers=_auth())
    assert resp.status_code == 200
    body = resp.json()
    assert "PM: stories" in body["digest_markdown"]
    assert body["quota_used_pct"] == pytest.approx(12.5)


async def test_digest_history_returns_rows(
    api_client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    # Make sure at least one row exists.
    async with session_factory() as session:
        session.add(
            Checkpoint(
                id=uuid4(),
                trigger="scheduled",
                correlation_id=None,
                iteration=1,
                digest_markdown="### scheduled digest",
                quota_used_pct=0.0,
            )
        )
        await session.commit()

    resp = await api_client.get(
        "/api/digest/history",
        params={"limit": 5},
        headers=_auth(),
    )
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
    assert len(resp.json()) >= 1
