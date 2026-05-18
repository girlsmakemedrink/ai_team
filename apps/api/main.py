"""FastAPI entry point. See ADR-005, ADR-007.

Runs the agent dispatcher inside the same process via the lifespan
context manager: on startup, wire up bus/feed/audit/signer/agents and
launch the dispatcher task; on shutdown, drain it.

For Iteration 5 we'll split this into two processes (API + dispatcher
side-by-side); for now single-process is the cheapest setup.
"""

from __future__ import annotations

import asyncio
import contextlib
import datetime
import json
import os
from collections.abc import AsyncIterator  # noqa: TC003  runtime SSE generator
from contextlib import asynccontextmanager
from typing import Annotated, Any
from uuid import UUID, uuid4

import structlog
from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sse_starlette.sse import EventSourceResponse

from agents.product_manager import ProductManagerAgent
from agents.team_lead import TeamLeadAgent
from core.audit.writer import AuditLogWriter
from core.config import Settings, get_settings
from core.dispatcher import AgentDispatcher
from core.llm.factory import make_llm_client
from core.messaging.bus import MessageBus
from core.messaging.feed import FeedPublisher, FeedSubscriber
from core.messaging.schemas import (
    AgentId,
    AgentMessage,
    MessageType,
    Priority,
    TaskAssignmentPayload,
)
from core.observability import configure_logging, render_metrics
from core.persistence.models import Checkpoint, PendingReview, Task
from core.security.hmac_signer import HMACSigner

_log = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.log_level)
    _log.info("api.startup", port=settings.api_port)

    # === Persistence ===
    engine = create_async_engine(settings.postgres_dsn, echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    # === Messaging ===
    bus = MessageBus.from_url(settings.redis_url)
    feed = FeedPublisher.from_url(settings.redis_url, db_session_factory=session_factory)

    # === Security ===
    hmac_secret = settings.hmac_secret.get_secret_value().encode()
    signer = HMACSigner(hmac_secret)
    audit = AuditLogWriter(session_factory, hmac_secret)

    # === Agents + dispatcher ===
    llm = make_llm_client()
    agents = {
        AgentId.TEAM_LEAD: TeamLeadAgent(llm=llm),
        AgentId.PRODUCT_MANAGER: ProductManagerAgent(llm=llm),
    }
    dispatcher = AgentDispatcher(
        bus=bus,
        feed=feed,
        audit=audit,
        signer=signer,
        agents=agents,
        iteration=1,
    )

    # Disable in unit tests where no Redis is available. The integration
    # suite spins up its own testcontainers and enables this.
    autostart = os.environ.get("AI_TEAM_DISPATCHER_AUTOSTART", "true").lower() != "false"
    dispatcher_task: asyncio.Task[None] | None = None
    if autostart:
        dispatcher_task = asyncio.create_task(dispatcher.run(), name="dispatcher")

    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.bus = bus
    app.state.feed = feed
    app.state.signer = signer
    app.state.audit = audit
    app.state.dispatcher = dispatcher
    app.state.dispatcher_task = dispatcher_task

    try:
        yield
    finally:
        _log.info("api.shutdown")
        dispatcher.shutdown()
        if dispatcher_task is not None:
            with contextlib.suppress(TimeoutError, asyncio.CancelledError):
                await asyncio.wait_for(dispatcher_task, timeout=10)
        await bus.close()
        await feed.close()
        await engine.dispose()


app = FastAPI(title="ai_team API", version="0.2.0", lifespan=lifespan)


# === Auth ===


def require_owner_token(
    authorization: Annotated[str | None, Header()] = None,
    settings: Settings = Depends(get_settings),
) -> None:
    if authorization is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing Authorization header",
        )
    expected = "Bearer " + settings.owner_token.get_secret_value()
    if authorization != expected:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid owner token")


# === Health & metrics ===


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/metrics")
async def metrics() -> Response:
    return Response(
        content=render_metrics(),
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )


# === team_feed SSE ===


@app.get("/api/feed/stream")
async def feed_stream(request: Request) -> EventSourceResponse:
    settings = get_settings()
    sub = FeedSubscriber.from_url(settings.redis_url)

    async def event_gen() -> AsyncIterator[dict[str, str]]:
        try:
            async for event in sub.stream():
                if await request.is_disconnected():
                    break
                yield {"data": json.dumps(event)}
        finally:
            await sub.close()

    return EventSourceResponse(event_gen())


# === Tasks ===


class SubmitTaskRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=10_000)
    target_repo: str | None = None
    priority: Priority = Priority.P2


class SubmitTaskResponse(BaseModel):
    task_id: UUID
    correlation_id: UUID
    status: str


@app.post(
    "/api/tasks",
    response_model=SubmitTaskResponse,
    dependencies=[Depends(require_owner_token)],
)
async def submit_task(req: SubmitTaskRequest, request: Request) -> SubmitTaskResponse:
    task_id = uuid4()
    correlation_id = uuid4()
    session_factory: async_sessionmaker[Any] = request.app.state.session_factory

    async with session_factory() as session:
        session.add(
            Task(
                id=task_id,
                correlation_id=correlation_id,
                title=req.title,
                description=req.description,
                target_repo=req.target_repo,
                status="in_progress",
                assigned_agent=AgentId.TEAM_LEAD.value,
                priority=req.priority.value,
                iteration=1,
            )
        )
        await session.commit()

    msg = AgentMessage(
        correlation_id=correlation_id,
        sender=AgentId.USER,
        recipient=AgentId.TEAM_LEAD,
        message_type=MessageType.TASK_ASSIGNMENT,
        priority=req.priority,
        payload=TaskAssignmentPayload(
            task_id=task_id,
            title=req.title,
            description=req.description,
            target_repo=req.target_repo,
        ),
    )
    signer: HMACSigner = request.app.state.signer
    signed = signer.with_signature(msg)

    bus: MessageBus = request.app.state.bus
    await bus.publish(signed)

    feed: FeedPublisher = request.app.state.feed
    await feed.publish(signed)

    audit: AuditLogWriter = request.app.state.audit
    await audit.write_message(signed, iteration=1)

    _log.info(
        "api.task.submitted",
        task_id=str(task_id),
        correlation_id=str(correlation_id),
    )
    return SubmitTaskResponse(task_id=task_id, correlation_id=correlation_id, status="queued")


# === Reviews ===


class ReviewListItem(BaseModel):
    id: UUID
    requesting_agent: str
    summary: str
    target_artifact: str | None
    created_at: datetime.datetime
    correlation_id: UUID


@app.get(
    "/api/reviews",
    response_model=list[ReviewListItem],
    dependencies=[Depends(require_owner_token)],
)
async def list_pending_reviews(request: Request) -> list[ReviewListItem]:
    session_factory: async_sessionmaker[Any] = request.app.state.session_factory
    async with session_factory() as session:
        rows = (
            (
                await session.execute(
                    select(PendingReview)
                    .where(PendingReview.status == "pending")
                    .order_by(PendingReview.created_at.asc())
                )
            )
            .scalars()
            .all()
        )
    return [
        ReviewListItem(
            id=r.id,
            requesting_agent=r.requesting_agent,
            summary=r.summary,
            target_artifact=r.target_artifact,
            created_at=r.created_at,
            correlation_id=r.correlation_id,
        )
        for r in rows
    ]


class ApproveBody(BaseModel):
    comment: str | None = None


async def _resolve_review(
    request: Request, review_id: UUID, new_status: str, comment: str | None
) -> dict[str, str]:
    session_factory: async_sessionmaker[Any] = request.app.state.session_factory
    async with session_factory() as session:
        row = (
            await session.execute(select(PendingReview).where(PendingReview.id == review_id))
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=404, detail="review not found")
        if row.status != "pending":
            raise HTTPException(status_code=409, detail=f"review already {row.status}")
        row.status = new_status
        row.resolved_at = datetime.datetime.now(tz=datetime.UTC)
        row.resolution_comment = comment
        await session.commit()
    _log.info("api.review.resolved", review_id=str(review_id), status=new_status)
    return {"status": new_status, "review_id": str(review_id)}


@app.post(
    "/api/reviews/{review_id}/approve",
    dependencies=[Depends(require_owner_token)],
)
async def approve_review(review_id: UUID, body: ApproveBody, request: Request) -> dict[str, str]:
    return await _resolve_review(request, review_id, "approved", body.comment)


@app.post(
    "/api/reviews/{review_id}/reject",
    dependencies=[Depends(require_owner_token)],
)
async def reject_review(review_id: UUID, body: ApproveBody, request: Request) -> dict[str, str]:
    return await _resolve_review(request, review_id, "rejected", body.comment)


# === Checkpoint digests ===


class CheckpointResponse(BaseModel):
    id: UUID | None
    created_at: datetime.datetime | None
    trigger: str | None
    correlation_id: UUID | None
    iteration: int | None
    digest_markdown: str
    quota_used_pct: float


@app.get(
    "/api/digest",
    response_model=CheckpointResponse,
    dependencies=[Depends(require_owner_token)],
)
async def latest_digest(request: Request) -> CheckpointResponse:
    session_factory: async_sessionmaker[Any] = request.app.state.session_factory
    async with session_factory() as session:
        row = (
            await session.execute(select(Checkpoint).order_by(desc(Checkpoint.created_at)).limit(1))
        ).scalar_one_or_none()
    if row is None:
        return CheckpointResponse(
            id=None,
            created_at=None,
            trigger=None,
            correlation_id=None,
            iteration=None,
            digest_markdown=(
                "No checkpoint digest yet. Team Lead emits one after the first task completes."
            ),
            quota_used_pct=0.0,
        )
    return CheckpointResponse(
        id=row.id,
        created_at=row.created_at,
        trigger=row.trigger,
        correlation_id=row.correlation_id,
        iteration=row.iteration,
        digest_markdown=row.digest_markdown,
        quota_used_pct=row.quota_used_pct,
    )


@app.get(
    "/api/digest/history",
    dependencies=[Depends(require_owner_token)],
)
async def digest_history(request: Request, limit: int = 20) -> list[CheckpointResponse]:
    session_factory: async_sessionmaker[Any] = request.app.state.session_factory
    async with session_factory() as session:
        rows = (
            (
                await session.execute(
                    select(Checkpoint).order_by(desc(Checkpoint.created_at)).limit(limit)
                )
            )
            .scalars()
            .all()
        )
    return [
        CheckpointResponse(
            id=r.id,
            created_at=r.created_at,
            trigger=r.trigger,
            correlation_id=r.correlation_id,
            iteration=r.iteration,
            digest_markdown=r.digest_markdown,
            quota_used_pct=r.quota_used_pct,
        )
        for r in rows
    ]
