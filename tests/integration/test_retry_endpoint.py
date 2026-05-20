"""End-to-end /api/tasks/{task_id}/retry tests. iter-11 Phase 1.

Mirrors the api_client fixture pattern from test_apps_api_live.py
(httpx.ASGITransport over the real FastAPI app, bus/feed/signer/audit
wired to testcontainers). `write_audit_message` is a thin local helper
that signs and persists a fully-built AgentMessage through the same
AuditLogWriter the API itself uses.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import select

from core.config import get_settings
from core.messaging.schemas import (
    AgentId,
    AgentMessage,
    MessageType,
    Priority,
    TaskReportPayload,
    TaskStatus,
)
from core.persistence.models import AuditLog, Task

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Awaitable, Callable

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = pytest.mark.integration


@pytest.fixture
async def api_client(
    pg_dsn: str,
    redis_url: str,
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[httpx.AsyncClient]:
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


@pytest.fixture
async def write_audit_message(
    session_factory: async_sessionmaker[AsyncSession],
) -> Callable[[AgentMessage], Awaitable[int]]:
    """Sign + write a message via AuditLogWriter, like the API does."""
    settings = get_settings()
    secret = settings.hmac_secret.get_secret_value().encode()

    from core.audit.writer import AuditLogWriter
    from core.security.hmac_signer import HMACSigner

    signer = HMACSigner(secret)
    writer = AuditLogWriter(session_factory, secret)

    async def _write(msg: AgentMessage) -> int:
        signed = signer.with_signature(msg)
        return await writer.write_message(signed, iteration=1)

    return _write


def _auth() -> dict[str, str]:
    return {"Authorization": f"Bearer {os.environ['OWNER_TOKEN']}"}


def _blocked_report(task_id: UUID, correlation_id: UUID, blocked_on: str) -> AgentMessage:
    return AgentMessage(
        correlation_id=correlation_id,
        sender=AgentId.BACKEND_DEVELOPER,
        recipient=AgentId.TEAM_LEAD,
        message_type=MessageType.TASK_REPORT,
        priority=Priority.P2,
        payload=TaskReportPayload(
            task_id=task_id,
            status=TaskStatus.BLOCKED,
            progress_pct=0,
            summary="MCP server ai-team-repo never connected",
            blocked_on=blocked_on,
        ),
    )


def _done_report(task_id: UUID, correlation_id: UUID) -> AgentMessage:
    return AgentMessage(
        correlation_id=correlation_id,
        sender=AgentId.BACKEND_DEVELOPER,
        recipient=AgentId.TEAM_LEAD,
        message_type=MessageType.TASK_REPORT,
        priority=Priority.P2,
        payload=TaskReportPayload(
            task_id=task_id,
            status=TaskStatus.DONE,
            progress_pct=100,
            summary="done",
        ),
    )


async def test_retry_emits_fresh_assignment_with_same_task_id(
    api_client: httpx.AsyncClient,
    write_audit_message,  # type: ignore[no-untyped-def]
    session_factory,  # type: ignore[no-untyped-def]
) -> None:
    # 1. Submit a task → root assignment audit row + tasks row.
    resp = await api_client.post(
        "/api/tasks",
        json={"title": "x", "description": "y", "priority": "P2"},
        headers=_auth(),
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    task_id = UUID(data["task_id"])
    correlation_id = UUID(data["correlation_id"])

    # 2. Force tasks.status to 'blocked' (the rollup happens via dispatcher,
    #    which isn't running here — we simulate the terminal state).
    async with session_factory() as session:
        row = (await session.execute(select(Task).where(Task.id == task_id))).scalar_one()
        row.status = "blocked"
        await session.commit()

    # 3. Simulate a BLOCKED report from a downstream agent.
    await write_audit_message(_blocked_report(task_id, correlation_id, "mcp_unhealthy"))

    # 4. Hit the retry endpoint.
    resp = await api_client.post(
        f"/api/tasks/{task_id}/retry",
        json={"comment": "test"},
        headers=_auth(),
    )
    assert resp.status_code == 200, resp.text
    retry_data = resp.json()
    assert retry_data["task_id"] == str(task_id)
    assert retry_data["retry_attempt"] == 2
    assert retry_data["status"] == "requeued"

    # 5. audit_log now has TWO task_assignment rows for the same task_id.
    async with session_factory() as session:
        rows = (
            (
                await session.execute(
                    select(AuditLog)
                    .where(AuditLog.message_type == "task_assignment")
                    .where(AuditLog.payload_json["payload"]["task_id"].astext == str(task_id))
                    .order_by(AuditLog.id.asc())
                )
            )
            .scalars()
            .all()
        )
    assert len(rows) == 2
    assert rows[1].payload_json["metadata"]["retry_attempt"] == 2

    # 6. tasks.status flipped back to in_progress.
    async with session_factory() as session:
        task_row = (await session.execute(select(Task).where(Task.id == task_id))).scalar_one()
    assert task_row.status == "in_progress"


async def test_retry_rejects_done_task(
    api_client: httpx.AsyncClient,
    write_audit_message,  # type: ignore[no-untyped-def]
) -> None:
    resp = await api_client.post(
        "/api/tasks",
        json={"title": "x", "description": "y", "priority": "P2"},
        headers=_auth(),
    )
    data = resp.json()
    task_id = UUID(data["task_id"])
    correlation_id = UUID(data["correlation_id"])

    await write_audit_message(_done_report(task_id, correlation_id))

    resp = await api_client.post(
        f"/api/tasks/{task_id}/retry",
        json={"comment": None},
        headers=_auth(),
    )
    assert resp.status_code == 409
    assert "not currently blocked" in resp.json()["detail"]


async def test_retry_rejects_nonexistent_task(api_client: httpx.AsyncClient) -> None:
    bogus = uuid4()
    resp = await api_client.post(
        f"/api/tasks/{bogus}/retry",
        json={"comment": None},
        headers=_auth(),
    )
    assert resp.status_code == 404
