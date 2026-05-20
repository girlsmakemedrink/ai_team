# Iteration 18 — Plan

- **Status**: Draft (awaiting owner approval)
- **Plan author**: Claude (Opus 4.7)
- **Date drafted**: 2026-05-20
- **Base commit**: iter-17 squash on `main` (latest:
  `69187f4 docs(iter-17): retro + iter-18 handoff`)
- **Branch**: `worktree-iter-18` (will be cut from
  `origin/main` after plan approval; current worktree
  sits on `worktree-iter-17` and is reused for plan
  drafting only).
- **Anchors (do not contradict)**: ADR-0001 (orchestrator),
  ADR-0008 (LLM access strategy), iter-17 retro + demo
  report + handoff.
- **Carry-over addressed**: item 1 (top) of
  `iter_18_handoff.md` — implement
  `mcp__ai_team_tasks__request_human_review` so the
  formal `pending_reviews` row finally writes and
  closes the owner-approval gate for the first time
  in 18 iterations.
- **Deferred unchanged** (carry-overs 3–15 from
  `iter_18_handoff.md`): TL Backend decomposition (now
  SEVEN-iteration carry-over), HoldQueue persistence,
  `pytest-rerunfailures` plugin pin, agents'-branch-
  isolation investigation, TL auto-hop investigation,
  TL over-decomposition prompt hint, Architect spend
  watch, `audit_writer` Postgres role, hash-chain
  alert, `GitHubTargetRepo`, transactional TL,
  `BaseAgent` template refactor.

## Investigation evidence (already gathered)

1. **Read `tools/mcp_servers/ai_team_tasks/__main__.py`**
   — the `tools/call` branch returns a hard-coded
   `"[stub] {tool} not implemented until Iteration 2"`
   text envelope for ALL three declared tools
   (`mark_task_done`, `request_human_review`,
   `update_task_status`). Iter-17 added the `initialize`
   handler (commit `8022b9e`) and extracted
   `_build_response(msg)` for testability, but
   `tools/call` is still the iter-0 stub.

2. **Read `tools/mcp_servers/ai_team_repo/__main__.py`
   + `handlers.py`** — these are the shape to mirror:
   - `__main__.py` keeps `_build_response` pure for
     `initialize` / `tools/list` / unknown.
   - The async stdio loop dispatches `tools/call` to
     a `HANDLERS` dict that maps tool-name → async
     handler function. Each handler takes
     `(Context, args: dict)` and returns a
     `dict` envelope `{isError, content, structuredContent?}`.
   - `Context` is a frozen dataclass with a
     `Context.from_env(env: dict | None = None)`
     classmethod that reads `os.environ` (configurable
     for tests).

3. **Read `core/persistence/models.py:111-126`** — the
   `PendingReview` SQLAlchemy model already exists from
   iter-0 (migration `0001_initial.py:138`):
   - `id` UUID PK (default `uuid4`)
   - `created_at` timestamptz (server default `now()`)
   - `correlation_id` UUID NOT NULL (indexed)
   - `requesting_agent` String(50) NOT NULL
   - `task_id` UUID nullable
   - `summary` Text NOT NULL
   - `target_artifact` String(500) nullable
   - `status` String(20) NOT NULL default `"pending"`
   - `resolved_at` timestamptz nullable
   - `resolution_comment` Text nullable

4. **Read `apps/api/main.py:387-456`** — the API already
   surfaces `GET /api/reviews` (lists `pending`),
   `POST /api/reviews/{id}/approve`,
   `POST /api/reviews/{id}/reject`. So once a row
   exists, the owner-approval path is fully wired —
   iter-18 is literally just the missing INSERT.

5. **Read `prompts/qa_engineer.md`** — current prompt
   does NOT mention `request_human_review` even though
   the tool is in QA's allow-list
   (`agents/qa_engineer/agent.py:60`). QA emits
   `task_report(done)` correctly but never calls the
   tool, so even with the stub-replaced handler the row
   wouldn't appear without a prompt change.
   **Iter-18 must update the QA prompt to instruct an
   explicit `request_human_review` call before the
   final JSON output.**

6. **Read `agents/_base/agent.py:179`** — `BaseAgent`
   already propagates per-class `mcp_env` to the
   `claude -p` subprocess via `LLMClient.invoke(env=...)`.
   `claude_code_headless.py:233` merges that on top of
   `os.environ`, so the MCP-server subprocess that
   `claude -p` spawns inherits both the dispatcher's
   env (Postgres DSN via `core.config.get_settings()`)
   and the agent's role-specific env. No new wiring
   needed — `ai_team_tasks` reads the DSN like everything
   else does.

7. **iter-17 demo report `_demo_report.md:177-210`** —
   the missing piece is documented. The reference
   handler shape in the report uses
   `args["correlation_id"]` / `args["agent"]` /
   `args["summary"]` / `args.get("target_artifact")` /
   `args.get("task_id")`. This plan adopts that shape
   verbatim with one tweak: `agent` falls back to an
   env var `AI_TEAM_AGENT_ROLE` if missing in args
   (defense-in-depth; LLMs sometimes forget to pass
   identity fields).

## Goal — one sentence

Replace the iter-0 stub `request_human_review` MCP
tool with a real handler that INSERTs a
`PendingReview` row, plus the QA prompt update that
makes QA call it, so the demo's polling loop finds a
`pending_review` row + auto-approves and the formal
owner-approval loop **closes end-to-end for the first
time across 18 iterations**.

## Success criteria (binary, measurable)

1. **`request_human_review` writes a real row.**
   Calling `mcp__ai_team_tasks__request_human_review`
   with `{summary, correlation_id, agent?, task_id?,
   target_artifact?}` INSERTs a `pending_reviews` row
   visible immediately via `GET /api/reviews`.
2. **Tool inputSchema is tight.** `request_human_review`
   declares `summary` + `correlation_id` as
   `required`, `additionalProperties: false`, and
   types `task_id`/`correlation_id` as `string`
   (UUID-shaped at runtime — the handler validates).
3. **`mark_task_done` and `update_task_status` stay as
   STUBS** with the iter-17 text envelope. A unit test
   pins the stub envelope so a future iteration that
   wires them in must update the test. (Per handoff #2
   — audit prompts first; agents don't call these in
   the current chain.)
4. **QA's prompt instructs an explicit
   `request_human_review` call.** The new workflow
   step appears between "run tests" and "respond with
   JSON". The prompt cites the correlation_id source
   ("from the message header you received") so the LLM
   passes the right value.
5. **5–7 new tests, all RED → GREEN.**
   - 3 unit tests on the handler (happy path; missing
     summary; missing correlation_id).
   - 1 unit test on `Context.from_env` (env defaults +
     overrides).
   - 1 unit test that `mark_task_done` /
     `update_task_status` still stub-respond
     (regression guard).
   - 1 unit test that `__main__.py`'s
     `request_human_review` inputSchema is tight
     (regression guard).
   - 1 integration test (testcontainers Postgres) that
     a `tools/call` for `request_human_review` actually
     INSERTs a row and the row matches what the API
     returns.
6. **Demo loop closes.** A fresh real-LLM run of
   `scripts/demo_iter_18.sh` (clone of
   `demo_iter_17.sh` with iter-18 narrative) sees
   `review_count >= 1` BEFORE the 30-min deadline
   and the existing auto-approve step succeeds via
   `POST /api/reviews/{id}/approve`. Run-cost target
   ≤ $5 (handoff failure 3).
7. **No regressions.** Existing 390 unit + 48
   integration + 18 MCP handshake tests stay green.
   80% diff-cover, bandit-clean, mypy-strict.

## Implementation plan — phased, TDD-driven

### Phase 0 — branch + plan approval

- Plan committed to `worktree-iter-17` (this worktree)
  for review.
- Once approved by owner: cut
  `git worktree add -b worktree-iter-18 ../iter-2d origin/main`,
  cherry-pick this plan onto the new branch, push, and
  continue Phase 1 there. (The current iter-2c
  worktree stays at `worktree-iter-17`; iter-18 lives
  on its own branch per project convention.)

### Phase 1 — `handlers.py` with `Context` + `handle_request_human_review`

Mirror the `ai_team_repo/handlers.py` shape exactly so
the two MCP servers stay structurally parallel.

**Files**:
- Create: `tools/mcp_servers/ai_team_tasks/handlers.py`
- Create: `tests/unit/test_mcp_ai_team_tasks_handlers.py`

**1.1 RED — write failing tests first.**

`tests/unit/test_mcp_ai_team_tasks_handlers.py`:

```python
"""iter-18: handler tests for ai_team_tasks.

Mirrors tests/unit/test_mcp_ai_team_repo_handlers.py.
The handler INSERTs a PendingReview row; tests use a
sqlite-backed AsyncEngine for unit speed (no
testcontainers). Integration test in
tests/integration/test_mcp_ai_team_tasks_pending_review.py
exercises real Postgres.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy import select

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
        # Use a portable subset of the schema; only PendingReview is needed.
        await conn.run_sync(PendingReview.__table__.create)
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
```

- [ ] **Step 1.1: Write the failing tests**
- [ ] **Step 1.2: Run the new tests to verify they fail**

```bash
uv run pytest tests/unit/test_mcp_ai_team_tasks_handlers.py -v
```

Expected: ImportError (`handlers` module / `Context` /
`handle_request_human_review` / `handle_mark_task_done` /
`handle_update_task_status` not defined).

- [ ] **Step 1.3: Add `aiosqlite` to dev dependencies if not already present**

```bash
grep -n aiosqlite pyproject.toml
```

If not present:

```bash
uv add --dev aiosqlite
```

Expected: pyproject.toml + uv.lock updated.

- [ ] **Step 1.4: Implement `handlers.py`**

```python
"""Tool implementations for ai_team_tasks.

Iter-18: replaces the iter-0 stub. `handle_request_human_review`
INSERTs a `pending_reviews` row so the owner-approval gate
(`GET /api/reviews` + `POST /api/reviews/{id}/approve`) becomes
load-bearing.

Mirrors the shape of `tools/mcp_servers/ai_team_repo/handlers.py`:
each handler takes `(Context, args: dict)` and returns a
`ToolResult` envelope. Handlers do NOT raise; they return
`{"isError": True, "content": [...]}` for caller-visible errors so
the agent's LLM gets a structured rejection.

`mark_task_done` and `update_task_status` stay as STUBS per
iter-18's "audit prompts first" deferral. A regression test
in `tests/unit/test_mcp_ai_team_tasks_handlers.py` pins the
stub shape so the next iteration that implements them will
explicitly update the test.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from core.config import get_settings
from core.persistence.models import PendingReview


@dataclass(slots=True, frozen=True)
class Context:
    """Per-process context for ai_team_tasks handlers.

    `session_factory` is the async SQLAlchemy session-maker used
    to write `pending_reviews` rows. `default_agent` is the
    fallback used when a `tools/call` payload omits the `agent`
    field; orchestrator sets `AI_TEAM_AGENT_ROLE` per invocation
    (see iter-18 plan §6 — defense-in-depth for LLMs that forget
    to pass identity fields).
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


async def handle_request_human_review(
    ctx: Context, args: dict[str, Any]
) -> dict[str, Any]:
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
        target_artifact = str(target_artifact)[:500]  # match schema width

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
    """STUB — deferred per iter-18 handoff §2 (audit prompts first)."""
    return _ok_text("[stub] mark_task_done not implemented yet (deferred per iter-18)")


async def handle_update_task_status(_ctx: Context, _args: dict[str, Any]) -> dict[str, Any]:
    """STUB — deferred per iter-18 handoff §2."""
    return _ok_text(
        "[stub] update_task_status not implemented yet (deferred per iter-18)"
    )


HANDLERS = {
    "request_human_review": handle_request_human_review,
    "mark_task_done": handle_mark_task_done,
    "update_task_status": handle_update_task_status,
}
```

- [ ] **Step 1.5: Run the unit tests; expect all green.**

```bash
uv run pytest tests/unit/test_mcp_ai_team_tasks_handlers.py -v
```

Expected: 8 passed.

- [ ] **Step 1.6: Commit**

```bash
git add tools/mcp_servers/ai_team_tasks/handlers.py \
        tests/unit/test_mcp_ai_team_tasks_handlers.py \
        pyproject.toml uv.lock
git commit -m "feat(mcp-tasks): real request_human_review handler + Context"
```

### Phase 2 — wire `tools/call` dispatch + tighten inputSchemas

**Files**:
- Modify: `tools/mcp_servers/ai_team_tasks/__main__.py`
- Modify: `tests/unit/test_mcp_server_handshake.py` (drop
  the `tools/call` branch off `_build_response` for
  `ai_team_tasks` — same as `ai_team_repo` now handles it
  out-of-loop).
- Create: `tests/unit/test_mcp_ai_team_tasks_main.py` (the
  inputSchema regression guard).

**2.1 RED — write the failing test first.**

`tests/unit/test_mcp_ai_team_tasks_main.py`:

```python
"""iter-18: __main__ inputSchema regression guard for ai_team_tasks.

Pins the request_human_review inputSchema so a future PR
that broadens additionalProperties or drops a required
field has to update this test.
"""

from __future__ import annotations

from tools.mcp_servers.ai_team_tasks.__main__ import _TOOL_LIST


def test_request_human_review_schema_requires_summary_and_correlation() -> None:
    tool = next(t for t in _TOOL_LIST if t["name"] == "request_human_review")
    schema = tool["inputSchema"]
    assert schema["type"] == "object"
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == {"summary", "correlation_id"}
    props = schema["properties"]
    assert props["summary"]["type"] == "string"
    assert props["correlation_id"]["type"] == "string"
    assert props["agent"]["type"] == "string"
    assert props["task_id"]["type"] == "string"
    assert props["target_artifact"]["type"] == "string"
```

Also extend `tests/unit/test_mcp_server_handshake.py`'s
`tools/call` expectation to skip the parametric case for
`ai_team_tasks` (which now returns None from `_build_response`
for `tools/call`, dispatching async like `ai_team_repo` does).
After iter-18 the assertion `tools/call → None for ai_team_repo
only` becomes `tools/call → None for ai_team_repo + ai_team_tasks`.

(Iter-17 didn't add a `tools/call → text envelope` test for the
stub case in `_build_response`. The existing handshake suite
covers `initialize / notifications/initialized / tools/list /
unknown method`. Iter-18 reuses the same parametric ladder; no
change needed beyond confirming the `unknown method` test still
passes for `ai_team_tasks` after the refactor.)

- [ ] **Step 2.1: Write the failing schema test**
- [ ] **Step 2.2: Run it to verify failure**

```bash
uv run pytest tests/unit/test_mcp_ai_team_tasks_main.py -v
```

Expected: AssertionError on `additionalProperties is False`
(currently `True`) and `required` (currently missing).

- [ ] **Step 2.3: Rewrite `tools/mcp_servers/ai_team_tasks/__main__.py`**

Full replacement (mirrors `ai_team_repo/__main__.py`):

```python
"""MCP server: `ai_team_tasks` — task lifecycle ops for agents.

iter-18: `request_human_review` is now a real handler — it
INSERTs a `pending_reviews` row that the owner approves via
`POST /api/reviews/{id}/approve`. `mark_task_done` and
`update_task_status` remain STUBS pending a prompt audit
(handoff §2).

iter-17: added `initialize` handler (commit `8022b9e`).

Exposes:
- mcp__ai_team_tasks__mark_task_done(task_id, summary, artifacts)  STUB
- mcp__ai_team_tasks__request_human_review(summary, correlation_id, agent?, task_id?, target_artifact?)
- mcp__ai_team_tasks__update_task_status(task_id, status, progress_pct)  STUB
"""

from __future__ import annotations

import asyncio
import json
import sys
from typing import Any

from tools.mcp_servers.ai_team_tasks.handlers import HANDLERS, Context

_SERVER_NAME = "ai_team_tasks"
_SERVER_VERSION = "0.2.0"
_DEFAULT_PROTOCOL_VERSION = "2025-06-18"

_TOOL_LIST: list[dict[str, Any]] = [
    {
        "name": "mark_task_done",
        "description": "Mark a task as done and emit a task_report. STUB (iter-18 deferred).",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": True},
    },
    {
        "name": "request_human_review",
        "description": (
            "Create a pending_review row awaiting owner approval. "
            "Required: summary (≤2000 chars), correlation_id (UUID string). "
            "Optional: agent (defaults to AI_TEAM_AGENT_ROLE env), "
            "task_id (UUID), target_artifact (path/branch/PR-url, ≤500 chars)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "summary": {"type": "string", "minLength": 1, "maxLength": 2000},
                "correlation_id": {"type": "string"},
                "agent": {"type": "string"},
                "task_id": {"type": "string"},
                "target_artifact": {"type": "string", "maxLength": 500},
            },
            "required": ["summary", "correlation_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "update_task_status",
        "description": "Update a task's status/progress. STUB (iter-18 deferred).",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": True},
    },
]


def _build_response(msg: dict[str, Any]) -> dict[str, Any] | None:
    """Build the JSON-RPC response for one client message.

    Same shape as `ai_team_repo/__main__.py:_build_response`.
    Returns None for notifications, unknown methods, AND
    `tools/call` (which dispatches async with Context in the
    stdio loop). See iter-17 rationale.
    """
    method = msg.get("method")
    msg_id = msg.get("id")

    if method == "initialize":
        params = msg.get("params") or {}
        client_version = params.get("protocolVersion") or _DEFAULT_PROTOCOL_VERSION
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "protocolVersion": client_version,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": _SERVER_NAME, "version": _SERVER_VERSION},
            },
        }

    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {"tools": _TOOL_LIST},
        }

    # tools/call + notifications + unknown methods → None.
    return None


async def _stdio_loop() -> None:  # pragma: no cover - integration-tested
    ctx = Context.from_env()
    loop = asyncio.get_event_loop()
    reader = asyncio.StreamReader()
    protocol = asyncio.StreamReaderProtocol(reader)
    await loop.connect_read_pipe(lambda: protocol, sys.stdin)
    while True:
        line = await reader.readline()
        if not line:
            return
        try:
            msg = json.loads(line.decode())
        except json.JSONDecodeError:
            continue

        response = _build_response(msg)
        if response is not None:
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()
            continue

        if msg.get("method") == "tools/call":
            params = msg.get("params") or {}
            name = params.get("name", "")
            arguments = params.get("arguments") or {}
            handler = HANDLERS.get(name)
            if handler is None:
                result = {
                    "isError": True,
                    "content": [{"type": "text", "text": f"unknown tool: {name!r}"}],
                }
            else:
                result = await handler(ctx, arguments)
            sys.stdout.write(
                json.dumps({"jsonrpc": "2.0", "id": msg.get("id"), "result": result}) + "\n"
            )
            sys.stdout.flush()


def main() -> None:  # pragma: no cover
    asyncio.run(_stdio_loop())


if __name__ == "__main__":  # pragma: no cover
    main()
```

- [ ] **Step 2.4: Run the schema regression test**

```bash
uv run pytest tests/unit/test_mcp_ai_team_tasks_main.py -v
```

Expected: 1 passed.

- [ ] **Step 2.5: Re-run the full MCP handshake suite**

```bash
uv run pytest tests/unit/test_mcp_server_handshake.py \
              tests/integration/test_mcp_handshake_real_subprocess.py -v
```

Expected: 18 passed (12 unit + 6 integration). The
handshake tests parametrize over the 3 servers × 4
scenarios; the unknown-method test exercises
`resources/list` (not `tools/call`), so the refactor
doesn't break them.

- [ ] **Step 2.6: Commit**

```bash
git add tools/mcp_servers/ai_team_tasks/__main__.py \
        tests/unit/test_mcp_ai_team_tasks_main.py
git commit -m "feat(mcp-tasks): wire tools/call dispatch + tight inputSchema"
```

### Phase 3 — QA prompt update

**Files**:
- Modify: `prompts/qa_engineer.md`

The prompt currently ends QA's workflow at "respond with
JSON". Iter-18 inserts a step 4: "call
`mcp__ai_team_tasks__request_human_review` before the
final JSON." The correlation_id is sourced from the
message header (already visible in QA's user message
per `agents/_base/agent.py:_user_message_for`).

- [ ] **Step 3.1: Edit `prompts/qa_engineer.md`**

Replace the existing `## Workflow` section with:

```markdown
## Workflow

1. Run the test suite. Typical first call:
   `run_shell(command_class="pytest", args=["-q", "tests/unit"])`.
   If the target_repo is an example sub-tree, scope to its tests dir.
2. If pytest reports failures, open the failing test files via `Read`
   and capture the first 3 distinctive failure messages.
3. Optionally run `ruff check` and `mypy` for static-analysis
   regressions — surface only if they're new.
4. **Call `mcp__ai_team_tasks__request_human_review`** to create
   the owner-approval gate row. Required args:
   - `summary`: 1–2 sentence verdict (same content you put in
     the JSON `summary` field below).
   - `correlation_id`: copy the UUID labelled `correlation` from
     the message header verbatim — DO NOT invent a new one.
   Optional but recommended:
   - `agent`: `"qa_engineer"` (so the row's `requesting_agent`
     is right even if the dispatcher env isn't set).
   - `target_artifact`: the branch ref or PR URL Backend produced
     (you can read it from the previous task_report payload in
     the message history, or omit).
5. Respond with the JSON object below.
```

Also append to the `## Discipline` block:

```markdown
- **`request_human_review` is REQUIRED on every QA run**, even
  when the suite passes. The pending_review row is the
  owner-approval gate; without it the chain doesn't close.
  Pass `correlation_id` exactly as shown in the message header
  — the handler validates UUID format and will reject a
  malformed value.
```

- [ ] **Step 3.2: Commit**

```bash
git add prompts/qa_engineer.md
git commit -m "feat(prompts): QA must call request_human_review before final JSON"
```

### Phase 4 — integration test against real Postgres

**Files**:
- Create: `tests/integration/test_mcp_ai_team_tasks_pending_review.py`

- [ ] **Step 4.1: Write the failing test**

```python
"""iter-18: integration test for ai_team_tasks request_human_review.

Real Postgres via testcontainers (session-scoped fixture from
tests/integration/conftest.py). Calls the handler directly
(not via subprocess JSON-RPC — that's already proven by
the iter-17 handshake suite); verifies the row lands in
Postgres + reads back through the same shape as `/api/reviews`.
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
    ctx = Context(session_factory=session_factory, default_agent="qa_engineer")

    result = await handle_request_human_review(
        ctx,
        {
            "correlation_id": str(cid),
            "agent": "qa_engineer",
            "summary": "54/54 tests pass; 90.6% coverage on idea_validator",
            "target_artifact": "agent/backend_developer/idea-validator-v2",
            "task_id": str(uuid4()),
        },
    )
    assert result["isError"] is False
    payload = json.loads(result["content"][0]["text"])
    review_id = payload["review_id"]

    async with session_factory() as s:
        row = (
            await s.execute(select(PendingReview).where(PendingReview.correlation_id == cid))
        ).scalar_one()
    assert str(row.id) == review_id
    assert row.requesting_agent == "qa_engineer"
    assert row.status == "pending"
    assert row.target_artifact == "agent/backend_developer/idea-validator-v2"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_request_human_review_two_calls_two_rows(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    ctx = Context(session_factory=session_factory, default_agent="frontend_developer")
    cid_a, cid_b = uuid4(), uuid4()
    for cid, summary in ((cid_a, "first"), (cid_b, "second")):
        result = await handle_request_human_review(
            ctx, {"correlation_id": str(cid), "summary": summary}
        )
        assert result["isError"] is False

    async with session_factory() as s:
        rows = (
            (await s.execute(select(PendingReview).order_by(PendingReview.created_at)))
            .scalars()
            .all()
        )
    summaries = [r.summary for r in rows]
    assert "first" in summaries and "second" in summaries
    assert all(r.requesting_agent == "frontend_developer" for r in rows if r.summary in ("first", "second"))
```

- [ ] **Step 4.2: Run integration test**

```bash
uv run pytest tests/integration/test_mcp_ai_team_tasks_pending_review.py -v -m integration
```

Expected: 2 passed (testcontainers boots Postgres on
first run; ~10 s).

- [ ] **Step 4.3: Commit**

```bash
git add tests/integration/test_mcp_ai_team_tasks_pending_review.py
git commit -m "test(mcp-tasks): integration test against real Postgres"
```

### Phase 5 — local validation gates

- [ ] **Step 5.1: Lint + types + security + tests**

```bash
make lint && make typecheck && make sec && make test
```

Expected: all green. 396+ unit tests, 50+ integration
tests pass (390+8 unit + 48+2 integration = 446 from
iter-17 + new test counts).

- [ ] **Step 5.2: smoke-llm substrate check**

```bash
make smoke-llm
```

Expected: ADR-008 smoke passes (parses `structured_output`,
`--session-id` set-once, `--resume` re-resumes).

- [ ] **Step 5.3: diff-cover**

CI runs this automatically once we push, but for local
sanity:

```bash
uv run pytest --cov=tools.mcp_servers.ai_team_tasks --cov-report=term-missing tests/unit/test_mcp_ai_team_tasks_handlers.py tests/unit/test_mcp_ai_team_tasks_main.py
```

Expected: 100% on `handlers.py` minus the
`# pragma: no cover` lines (`_stdio_loop`), 100% on
the `_TOOL_LIST` const path. Diff-cover gate is 80%
on changed tracked lines.

### Phase 6 — real-LLM demo re-run + report

**Files**:
- Create: `scripts/demo_iter_18.sh` (clone of
  `demo_iter_17.sh` with iter-18 narrative). Make-target
  `make demo` already aliases the latest demo; iter-18
  updates the alias.
- Modify: `Makefile` (one-line: `demo` target points at
  `scripts/demo_iter_18.sh`).
- Create: `docs/iterations/iter_18_demo_report.md` after
  the run.

- [ ] **Step 6.1: Clone the demo script**

```bash
cp scripts/demo_iter_17.sh scripts/demo_iter_18.sh
chmod +x scripts/demo_iter_18.sh
```

Edit the header narrative + the `MCP_CONFIG="$(pwd)/.iter18-mcp.json"`
variable + the EXIT trap + the submitted task title
("iter-18 demo:" prefix). Functional polling logic
unchanged — the demo already polls `/api/reviews` for
`review_count >= 1`, which now succeeds for the first
time.

- [ ] **Step 6.2: Update Makefile alias**

```bash
sed -i.bak 's|scripts/demo_iter_17.sh|scripts/demo_iter_18.sh|' Makefile && rm Makefile.bak
```

- [ ] **Step 6.3: Run the demo with the real LLM**

```bash
AI_TEAM_DEMO_NON_INTERACTIVE=1 bash scripts/demo_iter_18.sh 2>&1 | tee /tmp/iter18-demo-run1.log
```

Expected (within 30 min wall-clock):
- `review_count` poll succeeds (1 row).
- Auto-approve step succeeds via
  `POST /api/reviews/{id}/approve`.
- Cost ≤ $5 (chain caching effects help since
  Backend's tree is committed from iter-17).

If the chain BLOCKEDs partway, run
`ai-team retry-blocked <task_id>` per the iter-11 CLI
recipe — capped at 5 attempts per the iter-11 retro.

- [ ] **Step 6.4: Write `docs/iterations/iter_18_demo_report.md`**

Capture (same shape as iter-17 demo report):
- Correlation ID of the run.
- Outcome verdict in one line.
- Tasks/audit_log table state.
- QA's row verbatim summary.
- Pending_review row content (via
  `curl /api/reviews | jq`).
- Auto-approve curl response.
- Cost figure.
- What worked / what didn't.

- [ ] **Step 6.5: Commit**

```bash
git add scripts/demo_iter_18.sh Makefile docs/iterations/iter_18_demo_report.md
git commit -m "docs(iter-18): real-LLM demo + first pending_review row + auto-approve"
```

### Phase 7 — PR, self-merge, retro + handoff

- [ ] **Step 7.1: Push the branch**

```bash
git push -u origin worktree-iter-18
```

- [ ] **Step 7.2: Open the PR**

```bash
gh pr create --title "iter-18: real request_human_review handler — formal loop close" \
             --body "$(cat <<'EOF'
## Summary
- Replaces iter-0 stub `mcp__ai_team_tasks__request_human_review`
  with a real handler that INSERTs `pending_reviews` rows.
- Updates QA prompt to call the tool before emitting final JSON.
- Demo run #1 produces the **first `pending_review` row + auto-
  approve across 18 iterations** — formal owner-approval loop
  closes end-to-end.

## Test plan
- [x] `make lint typecheck test test-integration sec` all green
- [x] 8 new unit tests on `handlers.py` (happy path, error paths,
      Context.from_env, stub regression guards)
- [x] 1 schema regression test on `__main__._TOOL_LIST`
- [x] 2 integration tests against real Postgres
- [x] `make smoke-llm` confirms ADR-008 substrate
- [x] Real-LLM demo run reaches `review_count >= 1` + auto-approve
- [x] 80% diff-cover on changed tracked lines

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 7.3: Wait for CI green, squash-merge**

```bash
gh pr view --json statusCheckRollup
# Once green:
gh pr merge --squash --delete-branch
```

(Self-approve OK per CLAUDE.md "Two distinct approval
layers": this is a dev-PR layer, not an agent task_report.)

- [ ] **Step 7.4: Write retro + handoff**

`docs/iterations/iter_18_retro.md`:
- What shipped
- What went well
- What didn't (cost overshoot if any; carry-overs that
  surfaced)
- Surprises
- Action items for iter-19
- Stats (commits / LOC / tests / cost / diff-cover /
  wall-clock)

`docs/iterations/iter_18_handoff.md`:
- Updated carry-over list (item 1 = TL Backend
  decomposition since this iter's #1 is closed).
- Ready-to-paste prompt for iter-19.

- [ ] **Step 7.5: Commit retro + handoff**

```bash
git checkout main && git pull
git checkout -b chore/iter-18-retro
git add docs/iterations/iter_18_retro.md docs/iterations/iter_18_handoff.md
git commit -m "docs(iter-18): retro + iter-19 handoff"
git push -u origin chore/iter-18-retro
gh pr create --title "docs(iter-18): retro + iter-19 handoff" --body "Retro and handoff for iter-18 — formal loop close."
# wait for CI, squash-merge
```

## Risk / mitigation

| Risk | Mitigation |
|------|-----------|
| `aiosqlite` missing → handler unit tests can't run | Step 1.3 adds it via `uv add --dev` if absent. Also acceptable: write the unit tests against `testcontainers` Postgres and skip the sqlite fallback. Sqlite is preferred for unit-test speed (~50 ms vs 10 s container startup). |
| LLM doesn't actually call the new tool despite prompt update | The Discipline section is REPEATED ("REQUIRED on every QA run") and explicit ("Pass `correlation_id` exactly as shown"). If the first demo run shows QA emits JSON without calling the tool, the fallback is a prompt iteration; the handler+test work still stands. |
| `task_id` from QA's LLM is a synthetic UUID, not a real one | Handler accepts ANY valid UUID; the `task_id` field on `pending_reviews` is nullable per schema (`models.py:120`). Worst case: row has a UUID that doesn't FK anywhere. Not a correctness problem because the model has no FK constraint to `tasks`. |
| Demo's wall-clock overruns the 30 min poll deadline | Same risk as iter-17. iter-18 has LESS work for Backend (its tree is already on disk from iter-17), so Backend's session length should drop. If overrun: extend deadline + restart, log retry in demo report. |
| Real-LLM run cost overshoots $5 | iter-17 run #3 was $5.69 with full Backend reimplementation. iter-18 expects Backend to find the tree already present → much less work → ~$2–3 estimate. Hard ceiling: stop after 1 run unless required for diagnosis. |
| Concurrent `request_human_review` calls from different agents create duplicate-ish rows | The `pending_reviews` schema has no uniqueness constraint on `(correlation_id, requesting_agent)` (correct — different agents within the same correlation legitimately may each request review). No mitigation needed; surface as a possible iter-19 cleanup if it produces noise. |
| Real-LLM session-window 429 like iter-17 run #2 | iter-15's BLOCKED(budget) routing is production-validated. Demo's `retry-blocked` step handles it. Recoverable. |

## Out of scope for iter-18 (explicitly)

- **`mark_task_done` real impl**: stub stays. Audit
  prompts in iter-19 to see which agents call it; if
  none → mark deprecated. If some → implement.
- **`update_task_status` real impl**: same as above.
- **TL Backend decomposition** (carry-over #3): defer
  unless iter-18 demo's Backend hits the 600 s timeout.
- **HoldQueue persistence** (carry-over #4).
- **`pytest-rerunfailures` plugin pin** (carry-over #5):
  defer; CI flake is annoying but not blocking.
- **Agents'-branch-isolation** (carry-over #6): defer;
  iter-18's Backend likely doesn't re-push since the
  branch already exists on origin.
- **`AI_TEAM_CORRELATION_ID` per-message env var**:
  considered, deferred. The LLM-passes-it-in-args
  approach in this iter is simpler. If LLM forgets the
  arg empirically, iter-19 adds the env injection in
  `BaseAgent.handle()`.

## File map (all touched files in iter-18)

| Path | Action | LOC delta |
|------|--------|-----------|
| `tools/mcp_servers/ai_team_tasks/handlers.py` | create | +~110 |
| `tools/mcp_servers/ai_team_tasks/__main__.py` | modify | +30 −20 |
| `tests/unit/test_mcp_ai_team_tasks_handlers.py` | create | +~170 |
| `tests/unit/test_mcp_ai_team_tasks_main.py` | create | +~25 |
| `tests/integration/test_mcp_ai_team_tasks_pending_review.py` | create | +~60 |
| `prompts/qa_engineer.md` | modify | +20 −5 |
| `scripts/demo_iter_18.sh` | create (clone) | +~280 |
| `Makefile` | modify | +1 −1 |
| `docs/iterations/iter_18.md` | this file | +~600 |
| `docs/iterations/iter_18_demo_report.md` | create after run | +~250 |
| `docs/iterations/iter_18_retro.md` | create end | +~150 |
| `docs/iterations/iter_18_handoff.md` | create end | +~200 |
| `pyproject.toml` + `uv.lock` | modify (aiosqlite) | +3 −0 |

Total: ~1700 LOC including docs. Code-only delta ~250
LOC across 6 files. Tests ~255 LOC across 3 files. The
"~50 LOC + 5-7 tests" estimate in the handoff was just
the handler; the wiring + prompt + demo + docs are
real-but-modest additions.

## Anchors for the executing session

- ADR-001 (`docs/adr/0001-orchestrator-choice.md`):
  `pending_review` queue is **mentioned by name** as a
  first-class deliverable of the orchestrator. iter-18
  is implementing what ADR-001 promised in iter-0.
- ADR-008 (`docs/adr/0008-llm-access-strategy.md`):
  subscription-only LLM substrate. iter-18 does not
  touch this — but every test that exercises an LLM
  uses MockLLMClient, never claude -p.
- iter-17 retro (`docs/iterations/iter_17_retro.md`):
  the "7-agent chain completed cleanly; only the
  formal owner-approval gate is missing" framing
  exactly matches iter-18's scope.

## Open questions (resolve before Phase 1)

None known. The handler shape is fully specified in
the iter-17 demo report. The QA prompt update is a
mechanical addition. The integration test plumbs into
existing fixtures.

If anything surprises us during execution: stop, write
to the retro's "what didn't" section, and revisit.
