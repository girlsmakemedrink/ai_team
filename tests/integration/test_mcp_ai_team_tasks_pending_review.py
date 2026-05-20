"""iter-18: integration test for ai_team_tasks request_human_review.

Real Postgres via testcontainers (session-scoped fixtures
from `tests/integration/conftest.py`). Calls the handler
directly (not via subprocess JSON-RPC — that's already
covered by the iter-17 handshake suite); verifies the row
lands in Postgres with the expected field shape.
"""

from __future__ import annotations

import json
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.persistence.models import PendingReview
from tools.mcp_servers.ai_team_tasks.handlers import (
    Context,
    handle_request_human_review,
)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_request_human_review_writes_row_to_postgres(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    cid = uuid4()
    tid = uuid4()
    ctx = Context(session_factory=session_factory, default_agent="qa_engineer")

    result = await handle_request_human_review(
        ctx,
        {
            "correlation_id": str(cid),
            "agent": "qa_engineer",
            "summary": "54/54 tests pass; 90.6% coverage on idea_validator",
            "target_artifact": "agent/backend_developer/idea-validator-v2",
            "task_id": str(tid),
        },
    )
    assert result["isError"] is False
    payload = json.loads(result["content"][0]["text"])
    review_id = payload["review_id"]

    async with session_factory() as s:
        row = (
            await s.execute(
                select(PendingReview).where(PendingReview.correlation_id == cid)
            )
        ).scalar_one()
    assert str(row.id) == review_id
    assert row.requesting_agent == "qa_engineer"
    assert row.status == "pending"
    assert row.target_artifact == "agent/backend_developer/idea-validator-v2"
    assert row.task_id == tid


@pytest.mark.integration
@pytest.mark.asyncio
async def test_request_human_review_two_calls_two_rows(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    ctx = Context(
        session_factory=session_factory, default_agent="frontend_developer"
    )
    cid_a, cid_b = uuid4(), uuid4()
    for cid, summary in ((cid_a, "first"), (cid_b, "second")):
        result = await handle_request_human_review(
            ctx, {"correlation_id": str(cid), "summary": summary}
        )
        assert result["isError"] is False

    async with session_factory() as s:
        rows = (
            (
                await s.execute(
                    select(PendingReview)
                    .where(PendingReview.correlation_id.in_([cid_a, cid_b]))
                    .order_by(PendingReview.created_at)
                )
            )
            .scalars()
            .all()
        )
    summaries = [r.summary for r in rows]
    assert "first" in summaries
    assert "second" in summaries
    assert all(r.requesting_agent == "frontend_developer" for r in rows)
