"""Tool implementations for ai_team_tasks.

Iter-18: replaces the iter-0 stub.
`handle_request_human_review` INSERTs a `pending_reviews`
row so the owner-approval gate (`GET /api/reviews` +
`POST /api/reviews/{id}/approve`) becomes load-bearing.

Mirrors the shape of
`tools/mcp_servers/ai_team_repo/handlers.py`: each
handler takes `(Context, args: dict)` and returns a
`ToolResult` envelope. Handlers do NOT raise; they return
`{"isError": True, "content": [...]}` for caller-visible
errors so the agent's LLM gets a structured rejection.

`mark_task_done` and `update_task_status` stay as STUBS
per iter-18 §scope deferral (audit prompts first to
confirm any agent actually calls them). A regression
test in
`tests/unit/test_mcp_ai_team_tasks_handlers.py` pins the
stub shape so the next iteration that implements them
must update that test.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from core.config import get_settings
from core.persistence.models import PendingReview


@dataclass(slots=True, frozen=True)
class Context:
    """Per-process context for ai_team_tasks handlers.

    `session_factory` is the async SQLAlchemy session-maker
    used to write `pending_reviews` rows. `default_agent`
    is the fallback used when a `tools/call` payload omits
    `agent`; orchestrator sets `AI_TEAM_AGENT_ROLE` per
    invocation as defense-in-depth for LLMs that forget
    to pass identity fields.
    """

    session_factory: async_sessionmaker[AsyncSession]
    default_agent: str

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> Context:
        e = env if env is not None else dict(os.environ)
        dsn = e.get("POSTGRES_DSN") or get_settings().postgres_dsn
        engine = create_async_engine(dsn, echo=False, future=True)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        return cls(
            session_factory=factory,
            default_agent=e.get("AI_TEAM_AGENT_ROLE", "unknown"),
        )


def _err(text: str) -> dict[str, Any]:
    return {"isError": True, "content": [{"type": "text", "text": text}]}


def _ok_text(text: str) -> dict[str, Any]:
    return {"isError": False, "content": [{"type": "text", "text": text}]}


def _ok_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "isError": False,
        "content": [{"type": "text", "text": json.dumps(payload, default=str)}],
        "structuredContent": payload,
    }


async def handle_request_human_review(ctx: Context, args: dict[str, Any]) -> dict[str, Any]:
    """INSERT a pending_reviews row; return the new row's UUID."""
    summary = str(args.get("summary", "")).strip()
    if not summary:
        return _err("summary is required and must be non-empty")

    cid_raw = str(args.get("correlation_id", "")).strip()
    if not cid_raw:
        return _err("correlation_id is required")
    try:
        correlation_id = UUID(cid_raw)
    except ValueError:
        return _err(f"correlation_id is not a valid UUID: {cid_raw!r}")

    agent = str(args.get("agent") or ctx.default_agent)

    task_id: UUID | None = None
    tid_raw = args.get("task_id")
    if tid_raw:
        try:
            task_id = UUID(str(tid_raw))
        except ValueError:
            return _err(f"task_id is not a valid UUID: {tid_raw!r}")

    target_artifact = args.get("target_artifact")
    if target_artifact is not None:
        target_artifact = str(target_artifact)[:500]

    review = PendingReview(
        correlation_id=correlation_id,
        requesting_agent=agent[:50],
        task_id=task_id,
        summary=summary,
        target_artifact=target_artifact,
    )
    async with ctx.session_factory() as session:
        session.add(review)
        await session.commit()
        await session.refresh(review)

    return _ok_payload(
        {
            "review_id": str(review.id),
            "correlation_id": str(review.correlation_id),
            "requesting_agent": review.requesting_agent,
            "status": review.status,
        }
    )


async def handle_mark_task_done(_ctx: Context, _args: dict[str, Any]) -> dict[str, Any]:
    """STUB — deferred per iter-18 scope (audit prompts first)."""
    return _ok_text("[stub] mark_task_done not implemented yet (deferred per iter-18)")


async def handle_update_task_status(_ctx: Context, _args: dict[str, Any]) -> dict[str, Any]:
    """STUB — deferred per iter-18 scope (audit prompts first)."""
    return _ok_text("[stub] update_task_status not implemented yet (deferred per iter-18)")


HANDLERS = {
    "request_human_review": handle_request_human_review,
    "mark_task_done": handle_mark_task_done,
    "update_task_status": handle_update_task_status,
}
