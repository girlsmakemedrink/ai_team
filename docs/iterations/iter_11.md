# Iteration 11 — Plan

- **Status**: Draft (awaiting owner approval)
- **Plan author**: Claude (Opus 4.7)
- **Date drafted**: 2026-05-20
- **Base commit**: `9d02160` on `main` (iter-10 squash)
- **Branch**: `worktree-iter-11` (cut from `origin/main` at plan commit)
- **Anchors (do not contradict)**: ADR-001 (orchestrator),
  ADR-002 (message schema), ADR-004 (per-agent tool
  allowlist), ADR-007 (visibility & checkpoints), ADR-008
  (LLM access), iter-10 retro + demo report
- **Carry-overs addressed**: items 1–4 of
  `docs/iterations/iter_11_handoff.md` — retry mechanism
  for BLOCKED tasks (load-bearing), Backend Bash gating
  defense-in-depth, `BaseAgent.llm_timeout_s` default
  300 → 600 refactor (three iterations overdue), and the
  re-run that should finally close the `pending_review`
  loop iter-3..10 all reached for.
- **Deferred unchanged** (carry-over items 5–12 from iter-11
  handoff): TL Backend decomposition, HoldQueue persistence,
  `audit_writer` Postgres role, hash-chain alert,
  `GitHubTargetRepo`, TL transactional decomposition,
  `pytest-rerunfailures` plugin pin, `BaseAgent`
  template-method refactor.

## Goal — one sentence

Make iter-10's recoverable BLOCKED state actually recoverable
by adding an owner-initiated `ai-team retry-blocked <task_id>`
CLI (plus matching API endpoint) that re-emits the original
task_assignment for the same task_id back onto the bus,
preserving HoldQueue dependents; plus Backend Bash
defense-in-depth via `--disallowed-tools "Bash"` and the
overdue `BaseAgent.llm_timeout_s` 300 → 600 refactor; then
re-run the demo to finally close the `pending_review` loop.

## Success criteria (binary, measurable)

1. **`POST /api/tasks/{task_id}/retry` endpoint lands** (authed
   via `require_owner_token`). Reads the most recent
   `task_report` audit row for `task_id` and asserts
   `status='blocked'` AND `blocked_on in {'mcp_unhealthy',
   'budget'}` (the two recoverable shapes). Reads the most
   recent `task_assignment` audit row for the same `task_id`,
   rebuilds the `AgentMessage` with **the same `correlation_id`
   and the same `task_id`** (load-bearing: HoldQueue's
   in-memory `_done`/`_held` keys match) but a **fresh
   `message_id`** and `metadata["retry_attempt"] = N+1`. Signs,
   audits, feed-publishes, publishes to the bus. Returns
   `{task_id, correlation_id, retry_attempt, status: "requeued"}`.
   Rejects with 409 if the task isn't currently BLOCKED, 404
   if no such task, 422 if `blocked_on` isn't recoverable,
   429 if `retry_attempt >= 5`.
2. **`ai-team retry-blocked <task_id> [--comment "..."]` CLI**.
   POSTs to the new endpoint, prints a Rich panel with
   `task_id`, `correlation_id`, `retry_attempt`, and a hint
   to `ai-team watch --correlation <id>` for live feedback.
   Surfaces 4xx errors with the API's detail string.
3. **`tasks` row flip is part of the retry path.** After
   the retry message is published, the API flips the
   `tasks.status` for `task_id` from `blocked` to
   `in_progress` (single UPDATE, same transaction as
   the audit write). Same column the iter-3 reducer
   manipulates; no schema change.
4. **Retry-loop guard.** The endpoint counts prior
   `task_assignment` audit rows for the same `task_id` and
   rejects with 429 once the count is `>= 5`. Counts
   include the initial assignment, so the owner gets 4
   retries (initial + 4 retries = 5 rows). Capped low to
   prevent quota burn on persistently broken MCPs; the
   owner can always issue a new root task instead.
5. **Backend Bash defense-in-depth.** `BackendDeveloperAgent`
   declares `disallowed_tools: ClassVar[tuple[str, ...]] =
   ("Bash",)`. The `_invoke_with_retries` already forwards
   `disallowed_tools` to `LLMClient.invoke()`, which forwards
   it to `claude -p --disallowed-tools Bash` (already wired
   in `core/llm/claude_code_headless.py:146-147`). Unit test
   pins the CLI flag rendering: stub LLM client captures
   the kwargs, asserts `("Bash",)` is present.
6. **`BaseAgent.llm_timeout_s` default flipped to 600.**
   `agents/_base/agent.py:67` `llm_timeout_s: ClassVar[int]
   = 600`. The five subclasses currently overriding to 600
   (`architect`, `backend_developer`, `designer`, `devops`,
   `frontend_developer`) drop the redundant override.
   Subclasses that genuinely need a shorter timeout
   (`team_lead`, `product_manager`) keep their explicit
   override; the four currently relying on the 300 default
   (`qa_engineer`, `sre_support`, `market_researcher`) get
   an explicit `llm_timeout_s: ClassVar[int] = 300` to
   preserve current behavior. **Net effect**: zero
   behavior change on any existing agent; the only thing
   that changes is which agent's class-level config is
   "redundant" vs "explicit". Closes the iter-8/9/10 retro
   carry-over by anchoring the default at the value Backend
   has been overriding to since iter-7.
7. **Real-LLM demo finally closes the `pending_review`
   loop.** `scripts/demo_iter_11.sh` runs the iter-10 demo
   (same 30-min wall-clock), and within the same script
   issues `ai-team retry-blocked <backend_task_id>` once
   Backend lands BLOCKED. Expected outcome: Backend's
   second attempt succeeds (MCP race is intermittent),
   chain completes, QA runs, QA emits
   `mcp__ai_team_tasks__request_human_review`, a row
   appears in `pending_reviews`, owner runs
   `ai-team approve <id>`, the chain closes. If Backend
   BLOCKED a second time, the demo report documents
   what happened and iter-12 picks up. Either way, the
   demo report names the outcome explicitly.
8. **All gates green on PR.** `make lint typecheck sec
   test test-integration smoke-llm` all pass.
   `uv run ruff format --check .` clean. Diff-cover ≥ 80 %.
   0 high-severity bandit findings.

## Phases

Plan-before-code: this document lands as Phase 0's commit.
No Phase 1+ work until the owner approves.

### Phase 0 — Plan + branch setup

- [ ] **Cut branch from origin/main**

  ```bash
  git fetch origin
  git checkout -b worktree-iter-11 origin/main
  ```

- [ ] **Commit this plan**

  ```bash
  git add docs/iterations/iter_11.md
  git commit -m "docs(iter-11): plan — retry-blocked CLI + Bash defense + timeout refactor"
  ```

- [ ] **Open draft PR + post plan for owner approval**

  ```bash
  gh pr create --draft --title "iter-11: retry-blocked + Bash defense + timeout refactor" \
    --body "$(cat <<'EOF'
## Plan

See `docs/iterations/iter_11.md`.

Iter-11 priorities (from iter-10 retro + iter-11 handoff):
1. **Retry mechanism** for BLOCKED tasks — `ai-team retry-blocked <task_id>` CLI + `POST /api/tasks/{task_id}/retry` endpoint. Re-emits original task_assignment with same task_id (HoldQueue dependents match); retry_attempt metadata + 5-attempt cap.
2. **Backend Bash defense-in-depth** — add `disallowed_tools=("Bash",)` to BackendDeveloperAgent.
3. **`BaseAgent.llm_timeout_s` 300→600 refactor** — zero behavior change, three iterations overdue.
4. **Real-LLM demo** with retry — finally close the pending_review loop.

Awaiting owner approval before Phase 1+.
EOF
)"
  ```

### Phase 1 — Retry endpoint + CLI + integration test

**Files:**
- Create: `core/retry/retry_blocked.py` — pure logic helper:
  reads audit_log rows, validates retry eligibility, builds
  the re-emit `AgentMessage`. Pure-function, no I/O on the
  bus.
- Modify: `apps/api/main.py` — add the `/api/tasks/{task_id}/retry`
  endpoint that calls the helper, then audits + publishes.
- Modify: `apps/cli/main.py` — add the `retry-blocked` command.
- Create: `tests/unit/test_retry_blocked.py` — 6 unit tests on
  the helper (eligible blocked_on values, ineligible
  blocked_on, missing task, not-currently-blocked, retry
  count cap, fresh message_id but same task_id).
- Create: `tests/integration/test_retry_endpoint.py` — 1
  integration test that submits a task, has a stub Backend
  emit BLOCKED, calls the endpoint, asserts a fresh
  `task_assignment` audit row exists with same task_id +
  retry_attempt=2.

#### Step 1.1 — Failing unit tests for the helper

- [ ] **Write the 6 failing unit tests**

  ```python
  # tests/unit/test_retry_blocked.py
  """Unit tests for retry_blocked helper. iter-11 Phase 1."""
  from __future__ import annotations

  import pytest
  from uuid import UUID, uuid4

  from core.messaging.schemas import (
      AgentId, AgentMessage, MessageType, Priority,
      TaskAssignmentPayload, TaskReportPayload, TaskStatus,
  )
  from core.retry.retry_blocked import (
      RetryEligibility, RetryNotEligible, build_retry_message,
      check_retry_eligibility,
  )


  def _assignment(task_id: UUID, correlation_id: UUID, recipient: AgentId,
                  retry_attempt: int | None = None) -> AgentMessage:
      meta: dict[str, object] = {}
      if retry_attempt is not None:
          meta["retry_attempt"] = retry_attempt
      return AgentMessage(
          correlation_id=correlation_id,
          sender=AgentId.TEAM_LEAD,
          recipient=recipient,
          message_type=MessageType.TASK_ASSIGNMENT,
          priority=Priority.P2,
          payload=TaskAssignmentPayload(
              task_id=task_id, title="Build X", description="Do the thing",
              target_repo="examples/sandbox/idea-validator",
          ),
          metadata=meta,
      )


  def _report(task_id: UUID, correlation_id: UUID, status: TaskStatus,
              blocked_on: str | None = None) -> AgentMessage:
      return AgentMessage(
          correlation_id=correlation_id,
          sender=AgentId.BACKEND_DEVELOPER,
          recipient=AgentId.TEAM_LEAD,
          message_type=MessageType.TASK_REPORT,
          priority=Priority.P2,
          payload=TaskReportPayload(
              task_id=task_id, status=status, progress_pct=0,
              summary="x", blocked_on=blocked_on,
          ),
      )


  class TestEligibility:
      def test_blocked_mcp_unhealthy_is_eligible(self) -> None:
          task_id = uuid4()
          cid = uuid4()
          rows = [
              _assignment(task_id, cid, AgentId.BACKEND_DEVELOPER),
              _report(task_id, cid, TaskStatus.BLOCKED, "mcp_unhealthy"),
          ]
          result = check_retry_eligibility(task_id, rows)
          assert isinstance(result, RetryEligibility)
          assert result.retry_attempt == 2  # 1 prior assignment + this retry
          assert result.original_assignment.payload.task_id == task_id

      def test_blocked_budget_is_eligible(self) -> None:
          task_id = uuid4()
          cid = uuid4()
          rows = [
              _assignment(task_id, cid, AgentId.BACKEND_DEVELOPER),
              _report(task_id, cid, TaskStatus.BLOCKED, "budget"),
          ]
          result = check_retry_eligibility(task_id, rows)
          assert isinstance(result, RetryEligibility)

      def test_blocked_unknown_blocked_on_not_eligible(self) -> None:
          task_id = uuid4()
          cid = uuid4()
          rows = [
              _assignment(task_id, cid, AgentId.BACKEND_DEVELOPER),
              _report(task_id, cid, TaskStatus.BLOCKED, "unknown_reason"),
          ]
          with pytest.raises(RetryNotEligible, match="not recoverable"):
              check_retry_eligibility(task_id, rows)

      def test_not_currently_blocked_not_eligible(self) -> None:
          task_id = uuid4()
          cid = uuid4()
          rows = [
              _assignment(task_id, cid, AgentId.BACKEND_DEVELOPER),
              _report(task_id, cid, TaskStatus.DONE),
          ]
          with pytest.raises(RetryNotEligible, match="not currently blocked"):
              check_retry_eligibility(task_id, rows)

      def test_no_task_rows_not_eligible(self) -> None:
          task_id = uuid4()
          with pytest.raises(RetryNotEligible, match="no such task"):
              check_retry_eligibility(task_id, [])

      def test_retry_attempt_cap(self) -> None:
          task_id = uuid4()
          cid = uuid4()
          rows = (
              [_assignment(task_id, cid, AgentId.BACKEND_DEVELOPER, retry_attempt=n)
               for n in (None, 2, 3, 4, 5)]
              + [_report(task_id, cid, TaskStatus.BLOCKED, "mcp_unhealthy")]
          )
          with pytest.raises(RetryNotEligible, match="retry cap reached"):
              check_retry_eligibility(task_id, rows)


  class TestBuildRetryMessage:
      def test_same_task_id_and_correlation_id(self) -> None:
          task_id = uuid4()
          cid = uuid4()
          original = _assignment(task_id, cid, AgentId.BACKEND_DEVELOPER)
          retry = build_retry_message(original=original, retry_attempt=2)
          assert retry.payload.task_id == task_id
          assert retry.correlation_id == cid
          assert retry.recipient == AgentId.BACKEND_DEVELOPER
          assert retry.metadata["retry_attempt"] == 2
          assert retry.message_id != original.message_id  # fresh id
  ```

- [ ] **Run tests to confirm they fail**

  ```bash
  uv run pytest tests/unit/test_retry_blocked.py -v
  ```

  Expected: `ModuleNotFoundError: No module named 'core.retry'`.

#### Step 1.2 — Implement the helper

- [ ] **Create `core/retry/__init__.py`**

  ```python
  """Retry helpers for BLOCKED tasks. See iter_11.md Phase 1."""
  ```

- [ ] **Create `core/retry/retry_blocked.py`**

  ```python
  """Owner-initiated retry of BLOCKED task_assignments.

  iter-11: when a task reaches BLOCKED with a recoverable
  `blocked_on` value (currently 'mcp_unhealthy' or 'budget'),
  the owner can issue `ai-team retry-blocked <task_id>` to
  re-emit the original task_assignment with the same
  task_id and correlation_id (load-bearing — HoldQueue
  dependents key off task_id, so a fresh task_id would
  orphan QA + friends). A `retry_attempt` counter rides
  on the envelope metadata to cap at 5 attempts total.

  Pure logic; the FastAPI endpoint does the I/O (audit
  log read, bus publish, tasks-row update).
  """

  from __future__ import annotations

  from dataclasses import dataclass
  from typing import TYPE_CHECKING
  from uuid import uuid4

  from core.messaging.schemas import (
      AgentMessage,
      MessageType,
      TaskAssignmentPayload,
      TaskReportPayload,
      TaskStatus,
  )

  if TYPE_CHECKING:
      from collections.abc import Sequence
      from uuid import UUID


  RECOVERABLE_BLOCKED_ON: frozenset[str] = frozenset({"mcp_unhealthy", "budget"})
  RETRY_ATTEMPT_CAP: int = 5  # initial assignment counts as attempt 1


  class RetryNotEligible(Exception):
      """The task is not in a retryable state."""


  @dataclass(slots=True)
  class RetryEligibility:
      original_assignment: AgentMessage
      latest_report: AgentMessage
      retry_attempt: int  # the attempt number this retry will be (>=2)


  def check_retry_eligibility(
      task_id: UUID, rows: Sequence[AgentMessage]
  ) -> RetryEligibility:
      """Inspect audit_log rows for `task_id`. Raise if not retryable."""
      assignments = [
          r for r in rows
          if r.message_type == MessageType.TASK_ASSIGNMENT
          and isinstance(r.payload, TaskAssignmentPayload)
          and r.payload.task_id == task_id
      ]
      reports = [
          r for r in rows
          if r.message_type == MessageType.TASK_REPORT
          and isinstance(r.payload, TaskReportPayload)
          and r.payload.task_id == task_id
      ]
      if not assignments:
          raise RetryNotEligible(f"no such task: {task_id}")
      if not reports:
          raise RetryNotEligible(f"task {task_id} has no report yet")

      latest_report = reports[-1]
      payload = latest_report.payload
      assert isinstance(payload, TaskReportPayload)  # narrowing
      if payload.status != TaskStatus.BLOCKED:
          raise RetryNotEligible(
              f"task {task_id} not currently blocked (status={payload.status.value})"
          )
      if payload.blocked_on not in RECOVERABLE_BLOCKED_ON:
          raise RetryNotEligible(
              f"task {task_id} blocked_on={payload.blocked_on!r} not recoverable"
          )

      attempt_number = len(assignments) + 1  # the retry we're about to emit
      if attempt_number > RETRY_ATTEMPT_CAP:
          raise RetryNotEligible(
              f"task {task_id} retry cap reached ({RETRY_ATTEMPT_CAP} attempts)"
          )
      return RetryEligibility(
          original_assignment=assignments[0],
          latest_report=latest_report,
          retry_attempt=attempt_number,
      )


  def build_retry_message(
      *, original: AgentMessage, retry_attempt: int
  ) -> AgentMessage:
      """Build the re-emit. Fresh message_id, same task_id+correlation_id."""
      return original.model_copy(
          update={
              "message_id": uuid4(),
              "metadata": {**original.metadata, "retry_attempt": retry_attempt},
              "hmac_signature": None,  # caller re-signs
          }
      )
  ```

- [ ] **Run tests to confirm they pass**

  ```bash
  uv run pytest tests/unit/test_retry_blocked.py -v
  ```

  Expected: 7 passed (the 6 named tests + parametrize on
  `test_blocked_*_is_eligible` if pytest auto-collects).

- [ ] **Commit**

  ```bash
  git add core/retry/ tests/unit/test_retry_blocked.py
  git commit -m "feat(retry): pure-function retry eligibility + message builder"
  ```

#### Step 1.3 — Wire up the API endpoint

- [ ] **Read audit_log rows by task_id helper**

  Add a small helper inside `apps/api/main.py` (or a new
  `core/audit/reader.py` if we already have one):

  ```python
  async def _audit_rows_for_task(
      session: AsyncSession, task_id: UUID
  ) -> list[AgentMessage]:
      """Reconstruct AgentMessages from audit_log rows mentioning task_id."""
      rows = (await session.execute(
          select(AuditLog)
          .where(AuditLog.payload_json["payload"]["task_id"].astext == str(task_id))
          .order_by(AuditLog.id.asc())
      )).scalars().all()
      return [AgentMessage.model_validate(r.payload_json) for r in rows]
  ```

  (The JSON path query works because every payload variant
  shares `task_id` at the same depth for task_assignment +
  task_report.)

- [ ] **Add the endpoint**

  ```python
  class RetryBlockedBody(BaseModel):
      comment: str | None = None


  class RetryBlockedResponse(BaseModel):
      task_id: UUID
      correlation_id: UUID
      retry_attempt: int
      status: str


  @app.post(
      "/api/tasks/{task_id}/retry",
      response_model=RetryBlockedResponse,
      dependencies=[Depends(require_owner_token)],
  )
  async def retry_blocked_task(
      task_id: UUID, body: RetryBlockedBody, request: Request
  ) -> RetryBlockedResponse:
      session_factory: async_sessionmaker[Any] = request.app.state.session_factory
      async with session_factory() as session:
          rows = await _audit_rows_for_task(session, task_id)
      try:
          eligibility = check_retry_eligibility(task_id, rows)
      except RetryNotEligible as e:
          msg = str(e)
          if "no such task" in msg:
              raise HTTPException(status_code=404, detail=msg) from e
          if "not currently blocked" in msg:
              raise HTTPException(status_code=409, detail=msg) from e
          if "retry cap reached" in msg:
              raise HTTPException(status_code=429, detail=msg) from e
          raise HTTPException(status_code=422, detail=msg) from e

      retry_msg = build_retry_message(
          original=eligibility.original_assignment,
          retry_attempt=eligibility.retry_attempt,
      )
      signer: HMACSigner = request.app.state.signer
      signed = signer.with_signature(retry_msg)

      audit: AuditLogWriter = request.app.state.audit
      await audit.write_message(signed, iteration=1)
      feed: FeedPublisher = request.app.state.feed
      await feed.publish(signed)
      bus: MessageBus = request.app.state.bus
      await bus.publish(signed)

      # Flip tasks.status from blocked back to in_progress so the rollup
      # state matches reality.
      async with session_factory() as session:
          row = (
              await session.execute(select(Task).where(Task.id == task_id))
          ).scalar_one_or_none()
          if row is not None and row.status == "blocked":
              row.status = "in_progress"
              await session.commit()

      _log.info(
          "api.task.retry",
          task_id=str(task_id),
          retry_attempt=eligibility.retry_attempt,
          comment=body.comment,
      )
      return RetryBlockedResponse(
          task_id=task_id,
          correlation_id=signed.correlation_id,
          retry_attempt=eligibility.retry_attempt,
          status="requeued",
      )
  ```

  Add the imports at the top of `apps/api/main.py`:

  ```python
  from core.persistence.models import AuditLog  # NEW
  from core.retry.retry_blocked import (
      RetryNotEligible, build_retry_message, check_retry_eligibility,
  )  # NEW
  ```

- [ ] **Sanity-check: lint + typecheck**

  ```bash
  uv run ruff check apps/api/main.py core/retry/
  uv run mypy apps/api/main.py core/retry/
  ```

  Expected: clean.

- [ ] **Commit**

  ```bash
  git add apps/api/main.py
  git commit -m "feat(api): POST /api/tasks/{task_id}/retry endpoint"
  ```

#### Step 1.4 — Wire up the CLI

- [ ] **Add the CLI command** to `apps/cli/main.py`:

  ```python
  @cli.command(name="retry-blocked")
  @click.argument("task_id", type=click.UUID)
  @click.option("--comment", default=None, help="Optional comment to attach.")
  @click.pass_context
  def retry_blocked(ctx: click.Context, task_id: UUID, comment: str | None) -> None:
      """Re-emit a BLOCKED task_assignment so the agent retries."""
      resp = httpx.post(
          f"{_api_base(ctx)}/api/tasks/{task_id}/retry",
          json={"comment": comment},
          headers=_token_header(ctx),
          timeout=15.0,
      )
      if resp.status_code != 200:
          console.print(f"[red]Failed: {resp.status_code} {resp.text}[/]")
          sys.exit(1)
      data = resp.json()
      console.print(
          Panel(
              f"[bold]Task requeued.[/]\n"
              f"  task_id:        {data['task_id']}\n"
              f"  correlation_id: {data['correlation_id']}\n"
              f"  retry_attempt:  {data['retry_attempt']}\n"
              f"  status:         {data['status']}\n\n"
              f"[dim]Tail with:[/] ai-team watch --correlation {data['correlation_id'][:8]}",
              title="Retry submitted",
              style="green",
          )
      )
  ```

- [ ] **Manual smoke (against a local API)**

  ```bash
  ai-team retry-blocked 00000000-0000-0000-0000-000000000000 || true
  ```

  Expected: prints the 404 from the API (no such task).

- [ ] **Commit**

  ```bash
  git add apps/cli/main.py
  git commit -m "feat(cli): ai-team retry-blocked command"
  ```

#### Step 1.5 — Integration test

- [ ] **Write the integration test**

  ```python
  # tests/integration/test_retry_endpoint.py
  """End-to-end retry-blocked flow. iter-11 Phase 1."""
  from __future__ import annotations

  import pytest
  from uuid import UUID

  pytestmark = pytest.mark.integration


  async def test_retry_emits_fresh_assignment_with_same_task_id(
      api_client, write_audit_message, session_factory
  ) -> None:
      """End-to-end: submit, stub-blocked, retry — second assignment lands.

      `api_client`: lift the existing per-test fixture from
      `tests/integration/test_apps_api_live.py:34-72` (httpx.ASGITransport
      over the real FastAPI app with bus/feed/signer/audit wired to
      testcontainers) into `tests/integration/conftest.py` as a shared
      fixture in this same commit.

      `write_audit_message`: a new helper fixture added to
      `tests/integration/conftest.py` that takes a built `AgentMessage`,
      HMAC-signs it via the test signer, and writes via the same
      `AuditLogWriter`. Two thin wrappers `_blocked(...)` and
      `_done(...)` build the report payloads.
      """
      # 1. Submit a task → root assignment in audit_log
      resp = await api_client.post(
          "/api/tasks",
          json={"title": "x", "description": "y", "priority": "P2"},
          headers={"Authorization": "Bearer test-owner-token"},
      )
      assert resp.status_code == 200
      data = resp.json()
      task_id = UUID(data["task_id"])

      # 2. Simulate a BLOCKED report from a downstream agent
      await write_audit_message(
          _blocked(task_id, UUID(data["correlation_id"]), "mcp_unhealthy")
      )

      # 3. Hit the retry endpoint
      resp = await api_client.post(
          f"/api/tasks/{task_id}/retry",
          json={"comment": "test"},
          headers={"Authorization": "Bearer test-owner-token"},
      )
      assert resp.status_code == 200
      retry_data = resp.json()
      assert retry_data["task_id"] == str(task_id)
      assert retry_data["retry_attempt"] == 2
      assert retry_data["status"] == "requeued"

      # 4. The audit_log now has a second task_assignment row
      from core.persistence.models import AuditLog
      from sqlalchemy import select
      async with session_factory() as session:
          assignments = (await session.execute(
              select(AuditLog)
              .where(AuditLog.message_type == "task_assignment")
              .where(AuditLog.payload_json["payload"]["task_id"].astext == str(task_id))
              .order_by(AuditLog.id.asc())
          )).scalars().all()
      assert len(assignments) == 2
      assert assignments[1].payload_json["metadata"]["retry_attempt"] == 2

      # 5. tasks.status flipped back to in_progress
      from core.persistence.models import Task
      async with session_factory() as session:
          task_row = (await session.execute(
              select(Task).where(Task.id == task_id)
          )).scalar_one()
      assert task_row.status == "in_progress"


  async def test_retry_rejects_done_task(
      api_client, write_audit_message
  ) -> None:
      """409 when the task is DONE, not BLOCKED."""
      resp = await api_client.post(
          "/api/tasks",
          json={"title": "x", "description": "y", "priority": "P2"},
          headers={"Authorization": "Bearer test-owner-token"},
      )
      data = resp.json()
      task_id = UUID(data["task_id"])
      await write_audit_message(
          _done(task_id, UUID(data["correlation_id"]))
      )

      resp = await api_client.post(
          f"/api/tasks/{task_id}/retry",
          json={"comment": None},
          headers={"Authorization": "Bearer test-owner-token"},
      )
      assert resp.status_code == 409
      assert "not currently blocked" in resp.json()["detail"]


  async def test_retry_rejects_nonexistent_task(api_client) -> None:
      """404 when there's no such task."""
      resp = await api_client.post(
          "/api/tasks/00000000-0000-0000-0000-000000000000/retry",
          json={"comment": None},
          headers={"Authorization": "Bearer test-owner-token"},
      )
      assert resp.status_code == 404
  ```

  `_blocked(task_id, cid, blocked_on)` and `_done(task_id, cid)`
  are small builder helpers at the top of the test file that
  return a fully-built `AgentMessage` with a
  `TaskReportPayload`. The fixture `write_audit_message`
  HMAC-signs and writes the message via `AuditLogWriter`
  (the same writer the API already uses). One commit;
  ~25 LOC of fixture + helpers.

- [ ] **Run test**

  ```bash
  uv run pytest tests/integration/test_retry_endpoint.py -v
  ```

  Expected: PASS.

- [ ] **Commit**

  ```bash
  git add tests/integration/test_retry_endpoint.py
  git commit -m "test(retry): integration test for /api/tasks/{id}/retry"
  ```

### Phase 2 — Backend Bash defense-in-depth

**Files:**
- Modify: `agents/backend_developer/agent.py` — add
  `disallowed_tools` ClassVar.
- Create: `tests/unit/test_backend_disallowed_bash.py` —
  pin the kwarg forwarding through `_invoke_with_retries`
  to `LLMClient.invoke`.

- [ ] **Write the failing test**

  ```python
  # tests/unit/test_backend_disallowed_bash.py
  """Backend agent must forward disallowed_tools=('Bash',) to claude -p.

  iter-10 demo Backend's task_report still mentioned 'Bash hooks
  blocked the pytest command' despite the prompt edit. Defense in
  depth: tell claude -p explicitly to refuse Bash via
  --disallowed-tools, on top of leaving Bash out of --allowed-tools.
  """
  from __future__ import annotations

  from agents.backend_developer.agent import BackendDeveloperAgent


  def test_backend_declares_bash_disallowed() -> None:
      assert "Bash" in BackendDeveloperAgent.disallowed_tools
  ```

- [ ] **Run test to confirm it fails**

  ```bash
  uv run pytest tests/unit/test_backend_disallowed_bash.py -v
  ```

  Expected: FAIL — `disallowed_tools` is the empty default.

- [ ] **Make the change** to
  `agents/backend_developer/agent.py` — add right under the
  existing `allowed_tools` tuple (around line 76):

  ```python
  # iter-11: --allowed-tools already excludes Bash, but
  # iter-10 demo Backend reported "Bash hooks blocked the
  # pytest command" anyway — the LLM was perceiving Bash as
  # available and trying it. Belt-and-suspenders: name Bash
  # in --disallowed-tools so claude -p denies it explicitly
  # before the LLM even tries. See iter_10_demo_report.md
  # Failure 1.
  disallowed_tools: ClassVar[tuple[str, ...]] = ("Bash",)
  ```

- [ ] **Run test to confirm it passes**

  ```bash
  uv run pytest tests/unit/test_backend_disallowed_bash.py -v
  ```

  Expected: PASS.

- [ ] **Verify the CLI flag actually reaches `claude -p`**

  Spot-check `core/llm/claude_code_headless.py:146-147`:

  ```bash
  uv run grep -n "disallowed-tools" core/llm/claude_code_headless.py
  ```

  Expected: confirms `--disallowed-tools` is passed when
  the kwarg is non-empty. No code change needed; the
  forwarding was wired in earlier iterations.

- [ ] **Commit**

  ```bash
  git add agents/backend_developer/agent.py tests/unit/test_backend_disallowed_bash.py
  git commit -m "feat(backend): disallow Bash via --disallowed-tools"
  ```

### Phase 3 — `BaseAgent.llm_timeout_s` default 300 → 600

**Files:**
- Modify: `agents/_base/agent.py` — flip default to 600.
- Modify: `agents/architect/agent.py`,
  `agents/backend_developer/agent.py`,
  `agents/designer/agent.py`,
  `agents/devops/agent.py`,
  `agents/frontend_developer/agent.py` — drop the
  redundant `llm_timeout_s = 600` override.
- Modify: `agents/qa_engineer/agent.py`,
  `agents/sre_support/agent.py`,
  `agents/market_researcher/agent.py`,
  `agents/product_manager/agent.py` — add explicit
  `llm_timeout_s: ClassVar[int] = 300` if they were
  relying on the old default (verify per-file before
  editing).
- Modify: `tests/unit/test_base_agent.py` (or create
  `tests/unit/test_agent_timeouts.py`) — pin the new
  defaults explicitly so a future change is caught.

- [ ] **Audit current per-agent timeouts**

  ```bash
  uv run grep -nA1 "llm_timeout_s" agents/*/agent.py
  ```

  Expected output records the current value per agent.
  iter-10 retro lists:

  | Agent       | Current | New     | Action            |
  |-------------|---------|---------|-------------------|
  | architect   | 600     | inherits | drop override    |
  | backend     | 600     | inherits | drop override    |
  | designer    | 600     | inherits | drop override    |
  | devops      | 600     | inherits | drop override    |
  | frontend    | 600     | inherits | drop override    |
  | qa          | 300     | 300     | add explicit     |
  | sre_support | (300)   | 300     | add explicit     |
  | market      | 300     | 300     | add explicit     |
  | pm          | (300)   | (?)     | inspect first    |
  | team_lead   | (300)   | (?)     | inspect first    |

  For PM and TL: read their agent files; if a 300 timeout
  was chosen deliberately (e.g. iter-3 PM 150 s decomposition
  observation), keep at 300 with explicit override. If
  they're just inheriting the default, the right answer
  is also explicit 300.

- [ ] **Write the pinning test FIRST**

  ```python
  # tests/unit/test_agent_timeouts.py
  """Pin the per-agent llm_timeout_s values so iter-11's
  default-flip doesn't silently regress anyone. iter-11 Phase 3."""

  import pytest

  from agents.architect import ArchitectAgent
  from agents.backend_developer import BackendDeveloperAgent
  from agents.designer import DesignerAgent
  from agents.devops import DevOpsAgent
  from agents.frontend_developer import FrontendDeveloperAgent
  from agents.market_researcher import MarketResearcherAgent
  from agents.product_manager import ProductManagerAgent
  from agents.qa_engineer import QAEngineerAgent
  from agents.sre_support import SRESupportAgent
  from agents.team_lead import TeamLeadAgent
  from agents._base.agent import BaseAgent


  @pytest.mark.parametrize(
      "cls,expected",
      [
          (BaseAgent, 600),
          (ArchitectAgent, 600),
          (BackendDeveloperAgent, 600),
          (DesignerAgent, 600),
          (DevOpsAgent, 600),
          (FrontendDeveloperAgent, 600),
          (QAEngineerAgent, 300),
          (SRESupportAgent, 300),
          (MarketResearcherAgent, 300),
          (ProductManagerAgent, 300),
          (TeamLeadAgent, 300),
      ],
  )
  def test_llm_timeout_s(cls, expected) -> None:
      assert cls.llm_timeout_s == expected
  ```

- [ ] **Run test — expect a FAIL for `BaseAgent`** (currently 300)

  ```bash
  uv run pytest tests/unit/test_agent_timeouts.py -v
  ```

- [ ] **Flip the default** in `agents/_base/agent.py:67`:

  ```python
  # 600 s default (was 300 in iter-3..10). iter-11 retro:
  # five subclasses were already overriding to 600 (Backend,
  # Frontend, Architect, Designer, DevOps) — the LLM-bound
  # tier of the team is the majority case. Move the default
  # to the majority value and let the four agents that still
  # need ≤300 s (QA, SRE, Market, PM, TL) declare it
  # explicitly. See iter_10_retro.md action item 4.
  llm_timeout_s: ClassVar[int] = 600
  ```

- [ ] **Drop the redundant overrides** in the five 600-second
  subclasses. For each of `architect`, `backend_developer`,
  `designer`, `devops`, `frontend_developer`, delete the
  `llm_timeout_s: ClassVar[int] = 600` line.

- [ ] **Add explicit 300-second overrides** to the four
  subclasses that need the old default. For each of
  `qa_engineer`, `sre_support`, `market_researcher`,
  `product_manager`, `team_lead`, add:

  ```python
  # Inherits the iter-11 base default of 600 by removing
  # this would be wrong — <agent_name>'s call is bounded
  # by <reason from existing code/comments>.
  llm_timeout_s: ClassVar[int] = 300
  ```

  (Pull the reason from each file's existing comment or
  the iter-3..8 retro that justified the timeout.)

- [ ] **Run the pinning test**

  ```bash
  uv run pytest tests/unit/test_agent_timeouts.py -v
  ```

  Expected: 11 PASS.

- [ ] **Run the full suite** to make sure nothing else
  regresses

  ```bash
  uv run pytest tests/unit -x
  ```

  Expected: green.

- [ ] **Commit**

  ```bash
  git add agents/_base/agent.py agents/*/agent.py tests/unit/test_agent_timeouts.py
  git commit -m "refactor(agents): flip BaseAgent.llm_timeout_s default to 600"
  ```

### Phase 4 — Demo script + real-LLM run + report

**Files:**
- Create: `scripts/demo_iter_11.sh` — clone of
  `demo_iter_10.sh`, with a header noting the retry
  invocation pattern, and a `retry-blocked` invocation
  if Backend lands BLOCKED mid-run.
- Modify: `Makefile` — `make demo` aliases to
  `demo-iter-11`; `make demo-iter-10` stays.
- Create: `docs/iterations/iter_11_demo_report.md` —
  same shape as iter_10_demo_report.md.

#### Step 4.1 — Demo script

- [ ] **Copy + adapt**

  ```bash
  cp scripts/demo_iter_10.sh scripts/demo_iter_11.sh
  chmod +x scripts/demo_iter_11.sh
  ```

  Edit the header to say `iter-11`, and add a documented
  pattern: after the 30-min wall-clock, the operator
  runs `ai-team retry-blocked <task_id>` against any
  surviving BLOCKED Backend report. (Not automated in the
  script — leaving the retry as an explicit owner action
  matches ADR-001's posture.)

- [ ] **Update Makefile** `demo` target

  ```makefile
  demo: demo-iter-11

  demo-iter-11:
  	bash scripts/demo_iter_11.sh
  ```

- [ ] **Commit**

  ```bash
  git add scripts/demo_iter_11.sh Makefile
  git commit -m "chore(demo): demo_iter_11.sh + Makefile alias"
  ```

#### Step 4.2 — Pre-flight + real-LLM run

- [ ] **Pre-flight check**

  ```bash
  make smoke-llm
  ```

  Expected: PASS (ADR-008 §Smoke validation).

- [ ] **Run the demo**

  ```bash
  AI_TEAM_DEMO_NON_INTERACTIVE=1 bash scripts/demo_iter_11.sh
  ```

  Wall-clock budget 30 min; cost ceiling $5.00 (per iter-6+).

- [ ] **If Backend lands BLOCKED**: issue the retry

  ```bash
  ai-team retry-blocked <backend_task_id>
  ```

  Tail with `ai-team watch --correlation <cid>`. Document
  whether the second attempt succeeds (closes loop) or
  BLOCKED again (cap-at-5 prevents infinite loop).

#### Step 4.3 — Demo report

- [ ] **Write `docs/iterations/iter_11_demo_report.md`**

  Mirror `iter_10_demo_report.md`'s layout exactly:

  - Outcome paragraph naming which success criterion (#7's
    `pending_review` close OR #7's BLOCKED-again branch)
    the run hit.
  - "What worked" / "What didn't" sections.
  - Audit-log timeline table (the SQL query in iter-10's
    report still works).
  - Cost / quota table from `metadata.llm`.
  - Artifacts produced.
  - Action items for iter-12 (if any).
  - "Why this demo is a net win" closing.

- [ ] **Commit**

  ```bash
  git add docs/iterations/iter_11_demo_report.md
  git commit -m "docs(iter-11): real-LLM demo report"
  ```

### Phase 5 — Retro + iter-12 handoff + gates + merge

#### Step 5.1 — Final gate sweep

- [ ] **Run every gate**

  ```bash
  make lint typecheck sec test test-integration smoke-llm
  uv run ruff format --check .
  ```

  Expected: all green; 0 high-severity bandit; 382 + N new
  tests pass.

- [ ] **Diff-cover ≥ 80 %**

  ```bash
  uv run diff-cover coverage.xml --compare-branch=origin/main --fail-under=80
  ```

  Expected: PASS. Phase 1 retry helper is pure logic with
  6 unit tests + 1 integration test → near 100 % on those
  lines. Phase 2 Backend change is one-line behind one
  test. Phase 3 is config + pin test. Phase 4 is shell +
  docs (no Python diff).

#### Step 5.2 — Retro

- [ ] **Write `docs/iterations/iter_11_retro.md`** mirroring
  iter_10_retro.md's structure exactly:

  - "What shipped" — phase-by-phase summary with commit
    references.
  - "What went well" / "What didn't" / "Surprises" —
    short bullets, evidence-anchored.
  - "Action items for iter-12" — top-priority item is
    determined by Phase 4's outcome:
    - If chain reached `pending_review` and owner
      approved: iter-12 focus is **TL Backend
      decomposition** + carry-over cleanup.
    - If Backend BLOCKED a second time: iter-12 focus
      is **MCP race root-cause investigation** + TL
      Backend decomposition (the long Backend session
      is the likely culprit).
  - "Stats" — commits, tests, real-LLM spend, diff-cover.
  - "Ready-to-paste prompt for iter-12" → points to
    handoff doc.

- [ ] **Write `docs/iterations/iter_12_handoff.md`** — same
  structure as iter_11_handoff.md.

- [ ] **Commit**

  ```bash
  git add docs/iterations/iter_11_retro.md docs/iterations/iter_12_handoff.md
  git commit -m "docs(iter-11): retro + iter-12 handoff"
  ```

#### Step 5.3 — Mark PR ready, watch CI, squash-merge

- [ ] **Mark draft PR ready**

  ```bash
  gh pr ready
  ```

- [ ] **Watch CI**

  ```bash
  gh pr checks --watch
  ```

  Expected: green. If anything red, diagnose and fix (no
  --no-verify, no skip-hooks).

- [ ] **Squash-merge** once CI is green

  ```bash
  gh pr merge --squash --delete-branch
  ```

  Per CLAUDE.md: dev PRs on `ai_team` can self-approve and
  self-merge.

## What we are NOT doing this iteration

- **TL auto-hop on `BLOCKED(mcp_unhealthy)`.** Owner-in-the-
  loop CLI (Phase 1) is simpler, lands faster, and aligns
  with ADR-001's posture. Auto-hop can be a later
  optimization once we know MCP races are reliably
  transient. The per-correlation retry counter that
  auto-hop would need is the same accounting Phase 1
  already maintains (via `metadata["retry_attempt"]`), so
  iter-12 can lift the logic into TL with no new state.
- **TL Backend decomposition.** Carry-over from iter-9/10
  retros. Touches TL's `build_outputs` and the team-lead
  system prompt; large enough surface that bundling with
  Phase 1's retry mechanism would make the PR hard to
  review. iter-12 if Backend keeps hitting MCP races
  even with retry.
- **HoldQueue persistence to Postgres.** Still in-memory.
  iter-11's retry path doesn't make this worse — a
  restart still drops the queue. iter-13+.
- **`audit_writer` Postgres-role enforcement, hash-chain
  alert job, GitHubTargetRepo, transactional TL
  decomposition, `pytest-rerunfailures` plugin pin,
  BaseAgent template-method refactor.** All deferred from
  iter-2..10. None are load-bearing for iter-11's goal;
  pick up as a cluster in a "carry-over cleanup"
  iteration after iter-12.

## Risks

- **Retry re-races the MCP server.** If the MCP race is
  caused by the long Backend session itself (~370 s
  iter-10), retrying produces another long session that
  may race again. Mitigation: the 5-attempt cap. If a
  Backend task burns all 5 attempts, the owner should
  treat that as evidence that decomposition (deferred
  carry-over) is needed.
- **`audit_log` JSON-path query performance.** The
  `payload_json["payload"]["task_id"].astext` filter is
  not indexed in iter-11. Audit table is small (~140 rows
  after ten demos); a sequential scan per retry is fine
  at this scale. iter-15+ might add a GIN index when the
  table grows past 10K rows.
- **Renaming `metadata["retry_attempt"]` accidentally
  conflicts** with existing metadata keys. iter-1..10
  audit reveals no agent or dispatcher path writes a
  `retry_attempt` key; namespace is clear.
- **Phase 3 timeout flip on a 300-second-bound agent.**
  If we miss an agent that was relying on the 300 s
  default for a legitimate reason, it gains a 600 s
  budget. Net effect is a higher upper bound on a
  long-running call, never a regression on a finishing
  one. The pinning test in Phase 3 catches the off-by-
  one before merge.
- **HoldQueue `_done` doesn't have a "retry pending" entry**
  for the BLOCKED task_id. QA's hold is still waiting on
  the *original* task_id, so when the retry's
  `task_report(done)` lands, `mark_done(correlation, task_id)`
  will release QA — same code path as the initial
  completion. No new HoldQueue API needed. Pinned by the
  Phase 1 integration test.

## Cost projection

| Phase | Type                          | Estimate                  |
|-------|-------------------------------|---------------------------|
| 0     | docs                          | $0                        |
| 1     | code + 7 unit + 1 integration | $0                        |
| 2     | code + 1 unit test            | $0                        |
| 3     | refactor + 1 pin test         | $0                        |
| 4     | shell + real-LLM demo + retry | ~$1.50 expected, +$0.30 second attempt |
| 5     | docs + CI                     | $0                        |
| **Total** |                           | **~$1.80 expected, $5 ceiling** |

Quota check before Phase 4. iter-9 spent $1.23, iter-10
$1.24; iter-11 may come in higher if the retry runs
Backend a second time (≈ $0.25 + ≈ $0.20 cached). Stays
well under $5 ceiling.

## Workflow

- Plan-before-code: this file lands as Phase 0's commit;
  no Phase-1+ code until owner approves.
- Conventional commits; squash-merge on the iter-11 PR.
- Each phase's "Commit" row is one (and only one) commit.
- Run `make lint typecheck sec test` and
  `uv run ruff format --check .` after each phase.
- Final demo report goes in the same PR.

## Ready-to-paste prompt for iter-12

Lives in `docs/iterations/iter_12_handoff.md` (Phase 5.2).
