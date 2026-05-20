"""iter-18: handler tests for ai_team_tasks.

Mirrors tests/unit/test_mcp_ai_team_repo_handlers.py. The
load-bearing handler is `handle_request_human_review` —
it INSERTs a `PendingReview` row that closes the formal
owner-approval gate (`GET /api/reviews` +
`POST /api/reviews/{id}/approve`). Tests use a sqlite-
backed AsyncEngine for unit-test speed; the integration
test in
`tests/integration/test_mcp_ai_team_tasks_pending_review.py`
exercises real Postgres.

`mark_task_done` and `update_task_status` remain STUBS
per iter-18 handoff §2 — regression tests below pin the
stub shape so a future iteration that implements them
must update those tests explicitly.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator  # noqa: TC003 runtime fixture types
from typing import cast
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import Table, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from core.persistence.models import Base, PendingReview
from tools.mcp_servers.ai_team_tasks.handlers import (
    Context,
    handle_mark_task_done,
    handle_request_human_review,
    handle_update_task_status,
)


@pytest_asyncio.fixture
async def session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        # Only the pending_reviews table is exercised here; create just it.
        # SQLAlchemy types `__table__` as `FromClause`; the concrete subclass
        # is `Table`, which is what `create_all(tables=...)` expects.
        tables = [cast("Table", PendingReview.__table__)]
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


def _ctx(factory: async_sessionmaker[AsyncSession]) -> Context:
    return Context(session_factory=factory, default_agent="qa_engineer")


@pytest.mark.asyncio
async def test_request_human_review_inserts_pending_row(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    cid = str(uuid4())
    ctx = _ctx(session_factory)
    result = await handle_request_human_review(
        ctx,
        {
            "correlation_id": cid,
            "agent": "qa_engineer",
            "summary": "54/54 tests pass; coverage 90.6%",
            "target_artifact": "agent/qa_engineer/idea-validator-v2",
        },
    )
    assert result["isError"] is False
    payload = json.loads(result["content"][0]["text"])
    review_id = payload["review_id"]

    async with session_factory() as s:
        row = (await s.execute(select(PendingReview))).scalar_one()
    assert str(row.id) == review_id
    assert str(row.correlation_id) == cid
    assert row.requesting_agent == "qa_engineer"
    assert row.summary == "54/54 tests pass; coverage 90.6%"
    assert row.target_artifact == "agent/qa_engineer/idea-validator-v2"
    assert row.status == "pending"


@pytest.mark.asyncio
async def test_request_human_review_missing_summary_is_error(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    result = await handle_request_human_review(
        _ctx(session_factory),
        {"correlation_id": str(uuid4()), "agent": "qa_engineer"},
    )
    assert result["isError"] is True
    assert "summary" in result["content"][0]["text"]


@pytest.mark.asyncio
async def test_request_human_review_missing_correlation_id_is_error(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    result = await handle_request_human_review(
        _ctx(session_factory),
        {"summary": "x", "agent": "qa_engineer"},
    )
    assert result["isError"] is True
    assert "correlation_id" in result["content"][0]["text"]


@pytest.mark.asyncio
async def test_request_human_review_rejects_malformed_correlation_id(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    result = await handle_request_human_review(
        _ctx(session_factory),
        {"correlation_id": "not-a-uuid", "summary": "x"},
    )
    assert result["isError"] is True
    assert "correlation_id" in result["content"][0]["text"]


@pytest.mark.asyncio
async def test_request_human_review_defaults_agent_from_ctx(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """If `agent` is missing from args, fall back to
    Context.default_agent (sourced from AI_TEAM_AGENT_ROLE env)."""
    cid = str(uuid4())
    ctx = Context(session_factory=session_factory, default_agent="frontend_developer")
    result = await handle_request_human_review(
        ctx, {"correlation_id": cid, "summary": "landing page shipped"}
    )
    assert result["isError"] is False
    async with session_factory() as s:
        row = (await s.execute(select(PendingReview))).scalar_one()
    assert row.requesting_agent == "frontend_developer"


def test_context_from_env_uses_default_agent_unknown() -> None:
    ctx = Context.from_env({})
    assert ctx.default_agent == "unknown"


def test_context_from_env_reads_ai_team_agent_role() -> None:
    ctx = Context.from_env({"AI_TEAM_AGENT_ROLE": "qa_engineer"})
    assert ctx.default_agent == "qa_engineer"


# iter-19 Phase 2: correlation_id fallback (defense-in-depth mirror
# of iter-18's default_agent fallback).


@pytest.mark.asyncio
async def test_request_human_review_defaults_correlation_id_from_ctx(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """When `correlation_id` is missing from args,
    fall back to ctx.default_correlation_id sourced
    from AI_TEAM_CORRELATION_ID env. Same
    defense-in-depth pattern as default_agent. See
    iter_19.md Phase 2."""
    cid = str(uuid4())
    ctx = Context(
        session_factory=session_factory,
        default_agent="qa_engineer",
        default_correlation_id=cid,
    )
    result = await handle_request_human_review(ctx, {"summary": "x", "agent": "qa_engineer"})
    assert result["isError"] is False
    payload = json.loads(result["content"][0]["text"])
    assert payload["correlation_id"] == cid


def test_context_from_env_reads_correlation_id() -> None:
    cid = str(uuid4())
    ctx = Context.from_env({"AI_TEAM_CORRELATION_ID": cid})
    assert ctx.default_correlation_id == cid


def test_context_from_env_correlation_id_none_when_unset() -> None:
    ctx = Context.from_env({})
    assert ctx.default_correlation_id is None


@pytest.mark.asyncio
async def test_mark_task_done_remains_stub(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    result = await handle_mark_task_done(_ctx(session_factory), {})
    assert result["isError"] is False
    assert "stub" in result["content"][0]["text"].lower()


@pytest.mark.asyncio
async def test_update_task_status_remains_stub(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    result = await handle_update_task_status(_ctx(session_factory), {})
    assert result["isError"] is False
    assert "stub" in result["content"][0]["text"].lower()
