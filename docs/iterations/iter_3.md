# Iteration 3 — Plan

- **Status**: Draft (awaiting owner approval)
- **Plan author**: Claude (Opus 4.7)
- **Date drafted**: 2026-05-19
- **Base commit**: `3d771f2` on `main` (iter-2c squash)
- **Branch**: `worktree-iter-3` (cut from `origin/main` at plan commit)
- **Anchors (do not contradict)**: ADR-001 (orchestrator), ADR-002
  (message schema), ADR-003 (audit log), ADR-006 (tier per agent),
  ADR-008 (LLM access), ADR-009 (target repo)
- **Carry-overs addressed**: items 1–6 of
  `docs/iterations/iter_3_handoff.md`
- **Deferred unchanged**: `audit_writer` Postgres role enforcement
  (#7), hash-chain alert job (#8), `GitHubTargetRepo` (#9)

## Goal — one sentence

Make the real-LLM e2e demo close the full chain — by giving TL
**dependency ordering** so Architect → Backend → QA actually runs in
order, **rolling root-task state** when sub-tasks finish, **persisting
per-message tokens/cost/duration to the audit log** so the next demo
report is a single SQL query, fixing the **`ai-team digest` 401 bug**,
and bumping the **demo wall-clock** before re-running to exercise
Designer → Frontend → QA for the first time.

## Success criteria (binary, measurable)

1. **TL decomposition supports `depends_on`.** New per-subtask `id`
   slug + `depends_on: list[str]` field in `DECOMPOSITION_SCHEMA`. TL
   resolves slugs → UUIDs and stamps the predecessor `task_id`s into
   each outbound `AgentMessage.metadata["depends_on"]`.
2. **Dispatcher holds dependent sub-tasks until predecessors report
   DONE.** New `HoldQueue` component, in-memory per-correlation_id.
   Held messages are audited at creation (intent recorded) but withheld
   from the bus until released. Released atomically when the last
   predecessor's `TASK_REPORT(status=DONE)` is processed.
3. **Root-task state rollup.** Dispatcher writes child `Task` rows
   when TL emits sub-task assignments and marks each child `done`
   when its `TASK_REPORT(DONE)` lands. When every child of a root is
   `done`, the root flips `in_progress → done`. Any child `FAILED`
   flips the root `failed`.
4. **Per-message tokens / cost / duration / schema-validation
   persisted to `audit_log.payload_json.metadata`.** Every outbound
   `AgentMessage` from `BaseAgent.handle()` (and `TeamLeadAgent.handle()`)
   carries `metadata["llm"] = {tokens_in, tokens_out, cached_input,
   cost_cents, duration_ms, model, validated_against_schema}` — pulled
   from the `LLMResponse`. The next demo report can be produced with
   one `SELECT` over `audit_log`.
5. **`ai-team digest` 401 fixed.** CLI loads `.env` from cwd before
   reading `envvar="OWNER_TOKEN"`; `Authorization: Bearer <token>` is
   present on every authed endpoint call. Unit pin asserts the header.
6. **Demo wall-clock bumped to 20 minutes.** `scripts/demo_iter_3.sh`
   forks `demo_iter_2.sh` with a 1200 s wait window and a description
   that nudges TL into a 5-subtask plan exercising
   Designer → Frontend → QA in dependency order.
7. **Real-LLM e2e demo report at
   `docs/iterations/iter_3_demo_report.md`** — pre-flight green,
   chain runs to a `pending_review`, owner approves, full per-agent
   table (tokens / cost / duration / schema_validated) produced from
   a single SQL query over `audit_log` (no structlog grep).
8. **All gates green**: `make lint`, `make typecheck`, `make sec`
   (high-only), `make test-unit`, `make test-integration`,
   `make smoke-llm`. Diff-cover ≥ 80 %.
9. **`docs/iterations/iter_3_retro.md` + `iter_4_handoff.md`** stub.

## Non-goals (explicitly deferred)

- **Persisting `HoldQueue` across dispatcher restarts.** In-memory is
  fine for iter-3 — the only existing single-process dispatcher dies
  cleanly with the API. Persistence is iter-4 once the second product
  arrives or we hit a real outage. Document the limit in the
  `HoldQueue` docstring.
- **`depends_on` cycles.** TL is prompted to produce DAGs only; we
  validate "every `depends_on` slug references an earlier `id`" in
  `build_outputs` and reject the decomposition otherwise. Full cycle
  detection (SCC) is overkill for the 3–5-node DAGs TL emits.
- **Cross-correlation `depends_on`.** A sub-task can only depend on a
  sibling in the same decomposition. Architect's ADR triggering a
  separate spawned task chain is out of scope.
- **`AgentMessage` schema major bump.** All new fields ride in
  `metadata` (`dict[str, Any]`) which is already on the envelope.
  No breaking change to v1.x; backwards compatibility tests stay
  green.
- **`audit_writer` Postgres role** — still iter-4 or 5.
- **Hash-chain alert job** — still iter-4 or 5.
- **`GitHubTargetRepo` impl** — still waiting on first commercial
  product (ADR-009).

## Decisions to confirm with owner (defaults below in **bold**)

1. **HoldQueue state — in-memory vs. Postgres-backed for iter-3?**
   In-memory is ~80 LOC + a per-correlation dict; Postgres-backed is
   ~200 LOC + a new table + an Alembic migration + a recovery path on
   startup. **Default: in-memory.** Iter-4 lifts it to Postgres if
   the demo (or any real run) ever crashes mid-chain.
2. **Where does `metadata["llm"]` get stamped — `BaseAgent.handle()`
   or each agent's `build_outputs`?** `BaseAgent.handle()` keeps the
   change centralised but requires the TL override to call a helper
   too. `build_outputs` distributes it (one line per agent). **Default:
   `BaseAgent.handle()` with a single `_stamp_metrics(outputs, response)`
   helper that TL also calls** — keeps every agent on the same
   contract.
3. **Demo task description — extend idea-validator or write a new
   spec?** Designer + Frontend aren't natural fits for a CLI
   idea-validator. Extending the spec to mention "a one-page web docs
   landing page + a designed CLI UX" is the lightest touch.
   **Default: extend in-place via a new `idea_validator_v2_spec.md`,
   used only by `scripts/demo_iter_3.sh`.** Keeps the iter-2 spec
   intact as a regression baseline.

## Plan — seven phases

### Phase 0 — Branch + plan commit

`git checkout -b worktree-iter-3 origin/main` from the current cwd
(`.claude/worktrees/iter-2c`). Commit this plan as
`docs(iter-3): plan`. Surface for owner review **before** any code
changes — Phase 1 starts only after approval (per CLAUDE.md
"plan-before-code"). Cost: $0.

### Phase 1 — `ai-team digest` 401 fix (trivial, smallest blast radius)

The fix is one line. Done first to validate the iter-3 branch / CI
loop end-to-end before larger changes.

| # | Task | Files | Cost |
|---|------|-------|------|
| 1A | Unit test: CLI sends `Authorization: Bearer ...` when `OWNER_TOKEN` lives in `.env` (not shell env) | `tests/unit/test_apps_cli.py` (extend) | $0 |
| 1B | Load `.env` from cwd at the top of the CLI's `cli()` group callback using `python-dotenv.load_dotenv(override=False)` | `apps/cli/main.py` | $0 |
| 1C | Run the new test → green; run the full unit suite to make sure nothing regressed | local | $0 |
| 1D | Conventional commit `fix(cli): load .env before resolving OWNER_TOKEN envvar` | git | $0 |

**Why `load_dotenv` and not pydantic-settings on the CLI side**: the
CLI is a thin HTTP client, no pydantic-settings instance to hang off.
`python-dotenv` is already a dep (used transitively by
`pydantic-settings` in `core/config.py`). One import, one call.

**`override=False`** so a real shell `OWNER_TOKEN=...` still wins over
`.env` — matches how `pydantic-settings` behaves on the API side.

### Phase 2 — TL `depends_on` + dispatcher `HoldQueue`

The biggest single deliverable; the blocker for any meaningful e2e
chain. Strictly TDD — unit tests for the queue, then for TL emitting
correct metadata, then an integration test that runs Architect →
Backend → QA in order with a scripted LLM.

#### 2A — Schema additions (TL decomposition)

```python
# agents/team_lead/agent.py
DECOMPOSITION_SCHEMA = {
    "type": "object",
    "required": ["summary", "subtasks"],
    "additionalProperties": False,
    "properties": {
        "summary": {"type": "string"},
        "subtasks": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "required": ["id", "recipient", "title", "description", "priority"],
                "additionalProperties": False,
                "properties": {
                    "id": {"type": "string", "pattern": r"^[a-z][a-z0-9_]{0,31}$"},
                    "recipient": {"type": "string", "enum": [...same 9 roles...]},
                    "title": {"type": "string", "minLength": 1, "maxLength": 200},
                    "description": {"type": "string", "minLength": 1, "maxLength": 10000},
                    "priority": {"type": "string", "enum": ["P1", "P2", "P3", "P4"]},
                    "depends_on": {
                        "type": "array",
                        "items": {"type": "string", "pattern": r"^[a-z][a-z0-9_]{0,31}$"},
                        "default": []
                    }
                }
            }
        }
    }
}
```

#### 2B — TL `build_outputs` resolves slugs → UUIDs and stamps metadata

```python
# Pseudocode; final code in 2B commit.
slug_to_uuid: dict[str, UUID] = {}
for sub in plan["subtasks"]:
    slug_to_uuid[sub["id"]] = uuid4()

outputs = []
for sub in plan["subtasks"]:
    depends_on_uuids = [
        str(slug_to_uuid[dep])
        for dep in sub.get("depends_on", [])
        if dep in slug_to_uuid  # reject forward refs / unknown slugs silently
    ]
    # Reject the whole decomposition if any depends_on slug is unknown
    # (LLM-side bug → fail loudly).
    if len(depends_on_uuids) != len(sub.get("depends_on", [])):
        return [self._fail_report(incoming, f"unknown depends_on in {sub['id']}")]

    outputs.append(AgentMessage(
        ...,
        payload=TaskAssignmentPayload(task_id=slug_to_uuid[sub["id"]], ...),
        metadata={"depends_on": depends_on_uuids, "subtask_id": sub["id"],
                  "parent_task_id": str(incoming.payload.task_id)},
    ))
return outputs
```

Notes on the metadata shape:
- `depends_on: list[str]` — UUIDs of predecessor task_ids (stringified
  for JSON-friendliness; the dispatcher rehydrates).
- `subtask_id: str` — the LLM-side slug, useful for digest readability
  only; **not** load-bearing.
- `parent_task_id: str` — used by Phase 3 (root rollup) so the
  dispatcher can insert the child `Task` row with the right
  `parent_task_id` FK without re-deriving it.

#### 2C — `HoldQueue` component (new file)

```python
# core/dispatcher/hold_queue.py
from __future__ import annotations
import asyncio
from collections import defaultdict
from dataclasses import dataclass, field
from uuid import UUID

from core.messaging.schemas import AgentMessage


@dataclass(slots=True)
class _Held:
    msg: AgentMessage
    depends_on: set[UUID]


class HoldQueue:
    """In-memory dependency queue. One per dispatcher process.

    Not persisted: a dispatcher restart drops every held message. For
    iter-3 the dispatcher is single-process so this is acceptable.
    See iter_3.md Non-goals for the upgrade path.
    """

    def __init__(self) -> None:
        # correlation_id -> done task_ids
        self._done: dict[UUID, set[UUID]] = defaultdict(set)
        # correlation_id -> list of held messages
        self._held: dict[UUID, list[_Held]] = defaultdict(list)
        self._lock = asyncio.Lock()

    async def hold(self, msg: AgentMessage, depends_on: set[UUID]) -> bool:
        """Hold msg if any predecessor is not yet done.

        Returns True if held, False if all predecessors were already
        done at call time (caller should publish immediately).
        """
        async with self._lock:
            outstanding = depends_on - self._done[msg.correlation_id]
            if not outstanding:
                return False
            self._held[msg.correlation_id].append(_Held(msg=msg, depends_on=outstanding))
            return True

    async def mark_done(self, correlation_id: UUID, task_id: UUID) -> list[AgentMessage]:
        """Record DONE and return any newly released messages."""
        async with self._lock:
            self._done[correlation_id].add(task_id)
            released: list[AgentMessage] = []
            still_held: list[_Held] = []
            for h in self._held[correlation_id]:
                h.depends_on.discard(task_id)
                if not h.depends_on:
                    released.append(h.msg)
                else:
                    still_held.append(h)
            self._held[correlation_id] = still_held
            return released
```

Unit tests (target ~8):
- `test_hold_returns_false_when_no_predecessors`
- `test_hold_returns_true_when_predecessor_missing`
- `test_mark_done_releases_dependent`
- `test_mark_done_releases_only_when_all_predecessors_done`
- `test_mark_done_isolated_per_correlation`
- `test_mark_done_idempotent_on_unknown_task_id`
- `test_concurrent_hold_and_mark_done_under_asyncio_gather` (race-free
  under the lock)
- `test_released_messages_removed_from_held_queue`

#### 2D — Dispatcher wiring (`core/dispatcher.py`)

```python
# Inside _handle_one, replace the existing publish loop:

for out in outputs:
    signed = self._signer.with_signature(out)
    await self._audit.write_message(signed, iteration=self._iteration)
    # Always feed-publish (intent is observable to owner even if held).
    await self._feed.publish(signed)

    # Dependency-aware bus publish.
    depends_on_raw = signed.metadata.get("depends_on") or []
    depends_on = {UUID(s) for s in depends_on_raw}
    held = await self._hold_queue.hold(signed, depends_on) if depends_on else False
    if not held:
        await self._bus.publish(signed)

    # If this output is a TASK_REPORT(DONE), release dependents.
    if (isinstance(signed.payload, TaskReportPayload)
            and signed.payload.status == TaskStatus.DONE):
        released = await self._hold_queue.mark_done(
            signed.correlation_id, signed.payload.task_id
        )
        for r in released:
            # Releases skip re-audit (already audited at creation)
            # and re-feed (already feed-published).
            await self._bus.publish(r)
```

Edge: a TASK_REPORT(FAILED) on a predecessor should **also** release
dependents — but releasing them to chase a failed dep is wrong. **For
iter-3, FAILED on a predecessor abandons the held dependents.** Add a
`HoldQueue.mark_failed(correlation_id, task_id)` that drops held
messages whose `depends_on` contains the failed task_id (logged at
`warning`, surfaced in the digest via the existing P2 alert path).

Integration test (extend `tests/integration/test_dispatcher_e2e.py`):
- `_StubLLM` returns a TL decomposition with `[arch (no deps), be
  (depends_on=arch), qa (depends_on=be)]`.
- Stub agents return TASK_REPORT(DONE) on receipt.
- Assert ordering: arch's TASK_ASSIGNMENT lands on bus first; be's
  only after arch's DONE is processed; qa's only after be's DONE.
- Assert: no messages in `_held` at end of test.

#### 2E — Commits

- `feat(tl): depends_on in decomposition schema; outputs stamp metadata`
- `feat(dispatcher): HoldQueue for dependency-ordered publish`
- `test(integration): three-stage dependency chain end-to-end`

### Phase 3 — Root-task state rollup

Once 2D's `parent_task_id` metadata lands, this becomes mostly
bookkeeping.

| # | Task | Files | Cost |
|---|------|-------|------|
| 3A | Unit tests for a `TaskStateReducer` helper (in `core/persistence/task_state.py`) | `tests/unit/test_task_state.py` (new) | $0 |
| 3B | `TaskStateReducer.on_assignment(child_task_id, parent_task_id, recipient, correlation_id)` inserts a `Task` row with parent FK and `status="in_progress"` | `core/persistence/task_state.py` (new) | $0 |
| 3C | `TaskStateReducer.on_report(task_id, status)` updates the child row; if `status in {done, failed}` and the change brings parent's children all-terminal, updates the parent row | same | $0 |
| 3D | Dispatcher calls the reducer at the same point it gates HoldQueue (just after audit, just before / after publish) | `core/dispatcher.py` | $0 |
| 3E | Integration assertion in the same Phase-2D e2e test: at the end, the root task row is `done` | `tests/integration/test_dispatcher_e2e.py` | $0 |
| 3F | Commit `feat(persistence): root-task state rollup from sub-task reports` | git | $0 |

**Race**: TL emits 3 subtasks in one batch; the dispatcher writes 3
`Task` rows. Since `_handle_one` is serial per agent and the TL is one
agent, the 3 inserts are sequential under one Postgres connection.
No race within a single TL turn.

**Cross-agent race**: child A reports DONE while child B is still
being inserted (TL is slow). Not possible — TL emits all subtasks
synchronously in `build_outputs`, and the loop over outputs in
`_handle_one` runs to completion before the next message is consumed.
All child rows exist before any child can report.

**The TL-decomposition-fails-after-N-inserts edge** (TL's `handle()`
crashes after writing rows 1 and 2 of 3): the partially-inserted
children are orphans (parent stays `in_progress` forever because no
child #3 exists). Iter-3 ships with that risk documented in the
reducer's docstring; iter-4 wraps the TL batch in a single
transaction.

### Phase 4 — Per-message metrics in `metadata["llm"]`

| # | Task | Files | Cost |
|---|------|-------|------|
| 4A | Unit test: `BaseAgent.handle()` stamps `metadata["llm"]={tokens_in, tokens_out, cached_input, cost_cents, duration_ms, model, validated_against_schema}` on every output, with values pulled from a stub `LLMResponse` | `tests/unit/test_base_agent.py` (extend) | $0 |
| 4B | Implement `_stamp_metrics(outputs, response)` in `BaseAgent`; call from `handle()` after `build_outputs()` | `agents/_base/agent.py` | $0 |
| 4C | TL's overridden `handle()` calls `_stamp_metrics(outputs, response)` too | `agents/team_lead/agent.py` | $0 |
| 4D | Demo-report SQL query — added to a comment in `scripts/demo_iter_3.sh` and to `docs/iterations/iter_3_demo_report.md` | scripts + docs | $0 |
| 4E | Commit `feat(agents): persist per-message llm metrics to audit metadata` | git | $0 |

The stamping uses Pydantic's `model_copy(update=...)`:

```python
def _stamp_metrics(self, outputs: list[AgentMessage], r: LLMResponse) -> list[AgentMessage]:
    metrics = {
        "tokens_in": r.tokens.input,
        "tokens_out": r.tokens.output,
        "cached_input": r.tokens.cached_input,
        "cost_cents": r.cost_estimate_cents,
        "duration_ms": r.duration_ms,
        "model": r.tokens.model,
        "validated_against_schema": r.validated_against_schema,
    }
    return [
        out.model_copy(update={"metadata": {**out.metadata, "llm": metrics}})
        for out in outputs
    ]
```

Audit's `payload_json` already serialises the whole `AgentMessage`
including `metadata`, so the metrics persist for free. No migration.
No new table. One SQL query to extract per-agent stats:

```sql
SELECT
    sender,
    message_type,
    payload_json -> 'metadata' -> 'llm' ->> 'model'                     AS model,
    (payload_json -> 'metadata' -> 'llm' ->> 'tokens_in')::int          AS tokens_in,
    (payload_json -> 'metadata' -> 'llm' ->> 'tokens_out')::int         AS tokens_out,
    (payload_json -> 'metadata' -> 'llm' ->> 'cached_input')::int       AS cached_input,
    (payload_json -> 'metadata' -> 'llm' ->> 'cost_cents')::int         AS cost_cents,
    (payload_json -> 'metadata' -> 'llm' ->> 'duration_ms')::int        AS duration_ms,
    (payload_json -> 'metadata' -> 'llm' ->> 'validated_against_schema')::bool
                                                                        AS schema_ok
FROM audit_log
WHERE correlation_id = :cid
ORDER BY id;
```

### Phase 5 — Demo wall-clock + sub-task sizing

| # | Task | Files | Cost |
|---|------|-------|------|
| 5A | New spec `docs/sandbox/idea_validator_v2_spec.md` — same CLI core, plus "a one-page web docs landing page (`apps/web/`) and a Designer-written CLI UX brief (`docs/design/`)". 5 subtasks: PM, Architect, Backend, Designer, Frontend, QA — with a DAG: PM → Architect → (Backend, Designer) → Frontend → QA | docs | $0 |
| 5B | `scripts/demo_iter_3.sh` — fork of `demo_iter_2.sh` with `deadline=$((SECONDS + 1200))` (20 min) and the new spec referenced in the task description. Final block prints the per-message SQL query result via `psql` against the running Postgres | scripts | $0 |
| 5C | `make demo` target in `Makefile` points to `scripts/demo_iter_3.sh` (keep `demo_iter_2.sh` for regression) | Makefile | $0 |
| 5D | Commit `chore(demo): iter-3 script + spec extension for Designer/Frontend coverage` | git | $0 |

**Wall-clock budget**: 20 min × Sonnet @ ~$1/Mtok output is well
inside the $2 ceiling even for 5 stages.

### Phase 6 — Real-LLM e2e demo run

Cost budget: ~$0.80 expected (5 agents at Sonnet + Architect at Opus,
one full run); $2.50 ceiling for one debug retry.

| # | Task | Output |
|---|------|--------|
| 6A | Pre-flight: `.env`, `docker info`, `claude --version`, `gh auth status`, `make smoke-llm` green | terminal capture in report appendix |
| 6B | `AI_TEAM_DEMO_NON_INTERACTIVE=1 bash scripts/demo_iter_3.sh` end-to-end | chain completes; `pending_review` row exists |
| 6C | `uv run ai-team list-pending`, capture the review row, `uv run ai-team approve <id> --comment "iter-3 demo close-out"` | review approved |
| 6D | Run the demo report SQL query against the running Postgres; capture rows | per-agent table for the report |
| 6E | Write `docs/iterations/iter_3_demo_report.md` — same shape as `iter_2_demo_report.md`, with the new per-agent table coming from SQL (not structlog grep) | committed report |

**If the chain breaks** mid-run, the report captures the failure mode
and the iter-4 priorities — same posture as iter-2c. Do not paper
over a real failure.

**Designer / Frontend coverage**: required by success criterion #7 of
the iter-3 handoff. The DAG in 5A makes both load-bearing.

### Phase 7 — Validation gates + retro + iter-4 handoff

| # | Task | Output |
|---|------|--------|
| 7A | `make lint typecheck sec test test-integration smoke-llm` all green | local terminal |
| 7B | Diff-cover ≥ 80 % on the iter-3 diff against `origin/main` | coverage report |
| 7C | `docs/iterations/iter_3_retro.md` — what shipped, what didn't, surprises, action items, stats | committed retro |
| 7D | `docs/iterations/iter_4_handoff.md` — same shape as iter-3 handoff: carry-overs, hard constraints, inherited decisions, ready-to-paste prompt | committed handoff |
| 7E | Open PR `feat(iter-3): TL depends_on + root rollup + per-msg metrics + CLI 401 + demo run` on `worktree-iter-3`; squash-merge once CI green (self-approve per CLAUDE.md "dev-PR" layer) | merged PR; main at iter-3 squash |

## Risk register

- **HoldQueue lock contention** — single asyncio lock per queue, but
  the queue is hit on every output. Bounded by per-agent serialisation
  (one `_handle_one` at a time per agent) and by message count
  (5-subtask DAG × ~10 messages total). No realistic contention at
  iter-3 scale.
- **TL emits unknown `depends_on` slug** — `build_outputs` fails the
  decomposition loudly (TASK_REPORT(FAILED) to owner). LLM cost wasted;
  owner re-submits. Acceptable for iter-3; iter-4 might add a TL
  retry-with-feedback loop.
- **Demo script's psql call fails** — write the SQL into the script as
  a heredoc; on failure, the script still prints `tail -50` of the
  audit_log JSONB as a fallback so the report has *something* to
  paste.
- **`load_dotenv` adds startup latency to the CLI** — measured at
  < 5 ms for a 1-KB `.env`. Inside any reasonable budget.
- **Diff-cover dips below 80 %** — the most-skipped lines historically
  are defensive `_fail_report` branches. If we drop below the gate,
  add one more test covering the unknown-slug rejection path before
  shipping. Don't lower the gate.

## Cost projection

| Phase | Type | Estimate |
|-------|------|----------|
| 0     | docs | $0 |
| 1     | code + tests | $0 (no LLM calls) |
| 2     | code + unit + integration | $0 |
| 3     | code + unit + integration | $0 |
| 4     | code + unit | $0 |
| 5     | docs + script | $0 |
| 6     | real-LLM demo | ~$0.80 expected, $2.50 ceiling |
| 7     | docs + CI | $0 |
| **Total** | | **~$0.80 expected, $2.50 ceiling** |

Well under the $2 default Opus tier per-call ceiling and the monthly
quota; no subscription-quota concerns.

## Workflow

- Plan-before-code: this file lands as commit 1; no Phase-1+ code
  until owner approves the plan.
- Conventional commits; squash-merge on the iter-3 PR.
- Each phase's "Commit" row in the tables above is one (and only one)
  commit.
- Run `make lint typecheck sec test` after each phase to keep the
  branch shippable mid-flight.
- Final demo report goes in the same PR (single squash-merge captures
  the whole iteration).

## Ready-to-paste prompt for iter-4

Lives in `docs/iterations/iter_4_handoff.md` (Phase 7D).
