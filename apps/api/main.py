"""FastAPI entry point. See ADR-005, ADR-007."""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Annotated
from uuid import UUID, uuid4

import structlog
from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from core.config import Settings, get_settings
from core.messaging.feed import FeedSubscriber
from core.observability import configure_logging, render_metrics

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

_log = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.log_level)
    _log.info("api.startup", port=settings.api_port)
    yield
    _log.info("api.shutdown")


app = FastAPI(title="ai_team API", version="0.1.0", lifespan=lifespan)


# === Auth dependency ===


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


# === Tasks (stub, full implementation in Iteration 1) ===


class SubmitTaskRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=10_000)
    target_repo: str | None = None


class SubmitTaskResponse(BaseModel):
    task_id: UUID
    correlation_id: UUID
    status: str


@app.post("/api/tasks", dependencies=[Depends(require_owner_token)])
async def submit_task(req: SubmitTaskRequest) -> SubmitTaskResponse:
    # Iteration 0: just accept and echo. Real dispatch happens in
    # Iteration 1 when Team Lead is wired up.
    task_id = uuid4()
    correlation_id = uuid4()
    _log.info(
        "api.task.submitted",
        task_id=str(task_id),
        correlation_id=str(correlation_id),
        title_len=len(req.title),
    )
    return SubmitTaskResponse(task_id=task_id, correlation_id=correlation_id, status="queued")


# === Reviews (stub) ===


class ReviewListItem(BaseModel):
    id: UUID
    requesting_agent: str
    summary: str
    created_at: str


@app.get("/api/reviews", dependencies=[Depends(require_owner_token)])
async def list_pending_reviews() -> list[ReviewListItem]:
    # Iteration 0: empty list. Iteration 2 wires real persistence.
    return []


class ApproveBody(BaseModel):
    comment: str | None = None


@app.post("/api/reviews/{review_id}/approve", dependencies=[Depends(require_owner_token)])
async def approve_review(review_id: UUID, body: ApproveBody) -> dict[str, str]:
    _log.info("api.review.approve", review_id=str(review_id), has_comment=body.comment is not None)
    return {"status": "approved", "review_id": str(review_id)}


@app.post("/api/reviews/{review_id}/reject", dependencies=[Depends(require_owner_token)])
async def reject_review(review_id: UUID, body: ApproveBody) -> dict[str, str]:
    _log.info("api.review.reject", review_id=str(review_id))
    return {"status": "rejected", "review_id": str(review_id)}
