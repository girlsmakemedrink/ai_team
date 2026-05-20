# Iteration 19 — Plan

- **Status**: Draft (awaiting owner approval)
- **Plan author**: Claude (Opus 4.7)
- **Date drafted**: 2026-05-20
- **Base commit**: iter-18 squash on `main` (latest:
  `06cad9c docs(iter-18): retro + iter-19 handoff`,
  cumulative at `51d3fe8`).
- **Branch**: `worktree-iter-19` (cut from
  `origin/main` after plan approval; the current
  worktree sits on `worktree-iter-18` and is reused
  for plan drafting only — no code commits land on
  iter-18's branch).
- **Anchors (do not contradict)**: ADR-0001
  (orchestrator), ADR-0004 (per-agent tool
  allowlist), ADR-0008 (LLM access strategy),
  iter-18 retro + demo report + handoff.
- **Carry-overs addressed**: items 1–5 of
  `iter_19_handoff.md` — PM/TL allow-list
  hardening, per-message env injection, PM timeout
  300→600, demo poll-loop QA-specific, demo
  auto-approve bash fallback.
- **Deferred unchanged** (carry-overs 6–19 from
  `iter_19_handoff.md`): TL Backend decomposition
  (now NINE-iteration carry-over), HoldQueue
  persistence, `pytest-rerunfailures` plugin pin,
  agents'-branch-isolation investigation, TL
  auto-hop investigation, TL over-decomposition
  prompt hint, Architect spend watch, `audit_writer`
  Postgres role, hash-chain alert,
  `GitHubTargetRepo`, transactional TL,
  `BaseAgent` template refactor, `mark_task_done`
  / `update_task_status` real impl.

## Goal in one sentence

**Close the five iter-18 demo caveats so a re-run of
the iter-18-shape demo produces a QA-emitted
`pending_reviews` row with
`requesting_agent='qa_engineer'` (not `'unknown'`,
not PM) — proving the formal owner-approval loop
runs end-to-end through the *intended* agent path
rather than the iter-18 accidental one.**

## Investigation evidence (already gathered)

1. **PM/TL allow-list permissive default confirmed**
   — `agents/product_manager/agent.py:104` and
   `agents/team_lead/agent.py:98` both declare
   `allowed_tools: ClassVar[tuple[str, ...]] = ()`.
   `core/llm/claude_code_headless.py:199-200` omits
   the `--allowed-tools` flag entirely when the
   tuple is empty, which makes `claude -p` fall
   back to "all configured MCP tools + native tools
   allowed" — see iter-18 demo report Caveat 1. This
   is why PM (intended path: TL → PM → TL with one
   structured JSON turn) unprompted-called
   `mcp__ai_team_tasks__request_human_review`
   during the iter-18 demo run #2.

2. **Other 9 agents already declare explicit
   non-empty `allowed_tools`**:
   - Architect, Backend, Designer, DevOps, Frontend,
     QA, SRE, Market — each lists a curated whitelist
     in their `agent.py`.
   - Only TL and PM declare `()` — they're the
     outliers, not the norm.

3. **`requesting_agent='unknown'` root cause** —
   `agents/_base/agent.py:170-180` (current
   `_invoke_with_retries`) passes only
   `env=dict(self.mcp_env) if self.mcp_env else None`
   to `LLMClient.invoke()`. There is no
   per-`AgentMessage` env injection — `mcp_env` is a
   `ClassVar[dict[str, str]]` set once at class
   definition. So `AI_TEAM_AGENT_ROLE` never gets
   set per-invocation, the MCP server subprocess
   inherits whatever was in the dispatcher's env
   (typically nothing), and
   `Context.from_env` defaults to `"unknown"`
   (`tools/mcp_servers/ai_team_tasks/handlers.py:61`).

4. **PM and TL bypass `_invoke_with_retries`** —
   both have custom `handle()` overrides that call
   `self._llm.invoke()` directly
   (`agents/product_manager/agent.py:147-159`,
   `agents/team_lead/agent.py:222-241`) because
   they each pass a tier-specific `json_schema`
   and TL needs to short-circuit BLOCKED routing
   without an LLM call. The env-injection fix must
   land in all three call sites — `_invoke_with_retries`,
   `PM.handle`, and `TL.handle` — or a shared
   helper they all use.

5. **`Context.from_env` already reads
   `AI_TEAM_AGENT_ROLE`** (`handlers.py:61`), but
   the handler never falls back to env for
   `correlation_id`
   (`handlers.py:87-89`): if `args.get("correlation_id")`
   is missing or blank, the handler returns `_err`
   immediately. The iter-19 fix extends the same
   defense-in-depth pattern: read
   `AI_TEAM_CORRELATION_ID` into a new
   `Context.default_correlation_id`, and have
   `handle_request_human_review` consult it when
   args lack the field.

6. **PM timeout history** — `agents/product_manager/agent.py:106-109`
   explicitly pins 300s with a comment that traces
   back to the iter-3 demo's ~150s observation.
   iter-17 demo run #3 measured PM at 277s (92% of
   cap). iter-18 demo run #1 hit the 300s wall and
   tenacity retried 3× — burned $1.75 on the
   timeout cascade. Backend / Architect / Designer
   / Frontend / DevOps all sit at the iter-11
   default of 600s
   (`agents/_base/agent.py:60-68`). The
   `tests/unit/test_agent_timeouts.py` pin would
   need to flip PM's expected from 300 → 600.

7. **Demo poll-loop semantics** —
   `scripts/demo_iter_18.sh:139-152` counts ALL
   pending_reviews via the API and breaks the loop
   the moment `review_count >= 1`. In iter-18 run #2
   this fired the moment PM's row landed (~16 min
   in), killing the dispatcher before Architect /
   Backend / Designer / Frontend / QA finished.
   The fix: filter the JSON list to objects with
   `requesting_agent == "qa_engineer"` so the
   loop only exits when the *intended* row appears.

8. **Demo auto-approve bash fallback** —
   `scripts/demo_iter_18.sh:212-228` chains
   `$(curl ... 2>/dev/null || echo '[]') | python3
   <<PY ... json.load(sys.stdin) ...`. Iter-18 run
   #2 surfaced `JSONDecodeError: Expecting value:
   line 1 column 1 (char 0)` — empty stdin even
   though the API was responsive (the inline
   `ai-team list` rendered the same row two steps
   earlier). The defensive fix: assign curl output
   into `REVIEWS_JSON` separately, then `R="${REVIEWS_JSON:-[]}"`
   before piping. Belt-and-braces against the
   `|| echo '[]'` precedence edge case.

## Phases — bite-sized TDD steps with exact paths

The plan follows the **boring stack + plan-before-code +
TDD + frequent commits** discipline from CLAUDE.md. Every
phase has Red → Green → Refactor → Commit. No phase ships
until its ruff + mypy + bandit gates are green locally.

### Phase 1 — Per-message env injection in `BaseAgent`

**Goal**: When any agent calls `LLMClient.invoke(...)`,
the subprocess env carries `AI_TEAM_AGENT_ROLE`,
`AI_TEAM_CORRELATION_ID`, and `AI_TEAM_TASK_ID`
(when known), merged on top of `mcp_env`.

**Files**:
- Modify: `agents/_base/agent.py` (add `_build_env`
  helper; thread `env` through `_invoke_with_retries`)
- Modify: `agents/product_manager/agent.py` (custom
  `handle` consumes `_build_env`)
- Modify: `agents/team_lead/agent.py` (custom
  `handle` consumes `_build_env`)
- Test: `tests/unit/test_base_agent.py` (new tests)
- Test: `tests/unit/test_team_lead_agent.py` (new
  test asserting env passed)
- Test: `tests/unit/test_agent_env_injection.py` (NEW
  file — parametrized assertion across all agent
  call sites)

#### Step 1.1 — Add a recording LLM stub (test helper)

- [ ] **Step 1.1.1 — Write the helper inline in the
  first test** (don't create a top-level helper yet;
  follow YAGNI):

```python
# tests/unit/test_agent_env_injection.py (NEW)
"""iter-19 Phase 1: per-message env injection in
BaseAgent + PM + TL.

Asserts every concrete agent's invocation path passes
an env dict containing AI_TEAM_AGENT_ROLE +
AI_TEAM_CORRELATION_ID +
AI_TEAM_TASK_ID to LLMClient.invoke. Defense-in-depth
for the MCP server's Context.from_env fallback when
the LLM forgets to pass these fields in tool args.
See iter_18_demo_report.md Caveat 2.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, ClassVar
from uuid import uuid4

import pytest

from agents._base import BaseAgent
from agents.product_manager import ProductManagerAgent
from agents.team_lead import TeamLeadAgent
from core.llm.base import LLMResponse, TokensUsage
from core.messaging.schemas import (
    AgentId,
    AgentMessage,
    MessageType,
    Priority,
    TaskAssignmentPayload,
)


class _RecordingLLM:
    """LLMClient that records the last invoke kwargs.

    Returns a minimal valid LLMResponse so build_outputs
    doesn't crash. Captures `env` so the test can
    assert on it.
    """

    def __init__(self) -> None:
        self.last_kwargs: dict[str, Any] | None = None

    async def invoke(self, **kwargs: Any) -> LLMResponse:
        self.last_kwargs = kwargs
        return LLMResponse(
            text="",
            structured={"summary": "x", "subtasks": []},
            session_id="s",
            tokens=TokensUsage(
                input=0, output=0, model="claude-sonnet-4-6"
            ),
            duration_ms=0,
        )

    async def reset_session(self, session_id: str) -> None:
        del session_id
```

- [ ] **Step 1.1.2 — Run** `uv run pytest
  tests/unit/test_agent_env_injection.py -v` — expect
  collection only, no tests yet.

#### Step 1.2 — Red: assert BaseAgent injects env

- [ ] **Step 1.2.1 — Add the first test**:

```python
class _DummyAgent(BaseAgent):
    role: ClassVar[AgentId] = AgentId.QA_ENGINEER
    system_prompt_path: ClassVar[Path] = Path("/dev/null")
    allowed_tools: ClassVar[tuple[str, ...]] = ("Read",)

    def build_outputs(self, response, incoming):
        del response, incoming
        return []


def _make_assignment() -> AgentMessage:
    return AgentMessage(
        correlation_id=uuid4(),
        sender=AgentId.TEAM_LEAD,
        recipient=AgentId.QA_ENGINEER,
        message_type=MessageType.TASK_ASSIGNMENT,
        priority=Priority.P2,
        payload=TaskAssignmentPayload(
            task_id=uuid4(),
            title="t",
            description="d",
        ),
    )


def test_base_agent_injects_per_message_env(
    tmp_path: Path,
) -> None:
    prompt = tmp_path / "p.md"
    prompt.write_text("stub")
    _DummyAgent.system_prompt_path = prompt
    llm = _RecordingLLM()
    agent = _DummyAgent(llm=llm)
    msg = _make_assignment()

    asyncio.run(agent.handle(msg))

    assert llm.last_kwargs is not None
    env = llm.last_kwargs["env"]
    assert env is not None
    assert env["AI_TEAM_AGENT_ROLE"] == "qa_engineer"
    assert env["AI_TEAM_CORRELATION_ID"] == str(
        msg.correlation_id
    )
    assert env["AI_TEAM_TASK_ID"] == str(
        msg.payload.task_id
    )
```

- [ ] **Step 1.2.2 — Run** `uv run pytest
  tests/unit/test_agent_env_injection.py::test_base_agent_injects_per_message_env
  -v` — expect FAIL (env is `None` because
  `_DummyAgent.mcp_env` is the inherited `{}` and
  current code emits `None`).

#### Step 1.3 — Green: add `_build_env` to BaseAgent

- [ ] **Step 1.3.1 — Edit
  `agents/_base/agent.py`**. Add a helper above
  `_invoke_with_retries`:

```python
    # iter-19: per-message env injection so the MCP
    # subprocess Context.from_env fallback in
    # tools/mcp_servers/ai_team_tasks/handlers.py
    # populates correctly when the LLM forgets to
    # pass identity fields in tool args. iter-18
    # demo Run #2 hit `requesting_agent='unknown'`
    # because no agent role was ever set per-call.
    # See iter_18_demo_report.md Caveat 2.
    def _build_env(self, msg: AgentMessage) -> dict[str, str]:
        env: dict[str, str] = {
            "AI_TEAM_AGENT_ROLE": self.role.value,
            "AI_TEAM_CORRELATION_ID": str(msg.correlation_id),
        }
        # task_id lives on the payload for assignments
        # (and reports), not on the envelope. Read it
        # defensively — broadcasts and other shapes
        # may not have one.
        task_id = getattr(msg.payload, "task_id", None)
        if task_id is not None:
            env["AI_TEAM_TASK_ID"] = str(task_id)
        # Per-class mcp_env wins on key collisions
        # (caller knows best about role-scoped paths).
        env.update(self.mcp_env)
        return env
```

- [ ] **Step 1.3.2 — Edit `_invoke_with_retries`**.
  Add a `msg: AgentMessage` parameter and use
  `_build_env(msg)`:

Change the current signature:
```python
    async def _invoke_with_retries(
        self,
        *,
        system_prompt: str,
        user_message: str,
        session_key: str | None = None,
    ) -> LLMResponse:
```
to:
```python
    async def _invoke_with_retries(
        self,
        *,
        msg: AgentMessage,
        system_prompt: str,
        user_message: str,
        session_key: str | None = None,
    ) -> LLMResponse:
```

Replace the body's `env=dict(self.mcp_env) if self.mcp_env else None,`
with `env=self._build_env(msg),`.

- [ ] **Step 1.3.3 — Update the caller in
  `BaseAgent.handle()`** to pass `msg=msg`:

```python
        response = await self._invoke_with_retries(
            msg=msg,
            system_prompt=self.system_prompt(),
            user_message=user_msg,
            session_key=str(msg.correlation_id),
        )
```

- [ ] **Step 1.3.4 — Run the test** — expect PASS:

```
uv run pytest tests/unit/test_agent_env_injection.py::test_base_agent_injects_per_message_env -v
```

#### Step 1.4 — Red+Green: PM `handle()` injects env

- [ ] **Step 1.4.1 — Append to
  `tests/unit/test_agent_env_injection.py`**:

```python
def test_product_manager_injects_per_message_env(
    tmp_path: Path,
) -> None:
    """PM has a custom handle() that bypasses
    _invoke_with_retries — it must still inject
    per-message env."""
    prompt = tmp_path / "p.md"
    prompt.write_text("stub")
    ProductManagerAgent.system_prompt_path = prompt
    llm = _RecordingLLM()
    agent = ProductManagerAgent(llm=llm)
    msg = AgentMessage(
        correlation_id=uuid4(),
        sender=AgentId.TEAM_LEAD,
        recipient=AgentId.PRODUCT_MANAGER,
        message_type=MessageType.TASK_ASSIGNMENT,
        priority=Priority.P2,
        payload=TaskAssignmentPayload(
            task_id=uuid4(),
            title="t",
            description="d",
        ),
    )

    asyncio.run(agent.handle(msg))

    env = llm.last_kwargs["env"]
    assert env["AI_TEAM_AGENT_ROLE"] == "product_manager"
    assert env["AI_TEAM_CORRELATION_ID"] == str(
        msg.correlation_id
    )
    assert env["AI_TEAM_TASK_ID"] == str(
        msg.payload.task_id
    )
```

- [ ] **Step 1.4.2 — Run** — expect FAIL (PM still
  doesn't pass env). PM's `handle()` currently
  doesn't include `env=...` at all.

- [ ] **Step 1.4.3 — Edit
  `agents/product_manager/agent.py:147-159`**. Add
  `env=self._build_env(msg)` to the `_llm.invoke`
  kwargs:

```python
    async def handle(self, msg: AgentMessage) -> list[AgentMessage]:
        if msg.message_type != MessageType.TASK_ASSIGNMENT:
            return []
        response = await self._llm.invoke(
            system_prompt=self.system_prompt(),
            user_message=self._user_message_for(msg),
            model=self.model_tier,
            allowed_tools=self.allowed_tools,
            session_id=str(msg.correlation_id),
            timeout_s=self.llm_timeout_s,
            max_turns=self.max_turns,
            json_schema=USER_STORIES_SCHEMA,
            env=self._build_env(msg),
        )
        return self._stamp_metrics(self.build_outputs(response, msg), response)
```

- [ ] **Step 1.4.4 — Run** — expect PASS.

#### Step 1.5 — Red+Green: TL `handle()` injects env

- [ ] **Step 1.5.1 — Append the analogous test for
  TL**:

```python
def test_team_lead_injects_per_message_env(
    tmp_path: Path,
) -> None:
    prompt = tmp_path / "p.md"
    prompt.write_text("stub")
    TeamLeadAgent.system_prompt_path = prompt
    llm = _RecordingLLM()
    agent = TeamLeadAgent(llm=llm)
    msg = AgentMessage(
        correlation_id=uuid4(),
        sender=AgentId.USER,
        recipient=AgentId.TEAM_LEAD,
        message_type=MessageType.TASK_ASSIGNMENT,
        priority=Priority.P2,
        payload=TaskAssignmentPayload(
            task_id=uuid4(),
            title="t",
            description="d",
        ),
    )

    asyncio.run(agent.handle(msg))

    env = llm.last_kwargs["env"]
    assert env["AI_TEAM_AGENT_ROLE"] == "team_lead"
    assert env["AI_TEAM_CORRELATION_ID"] == str(
        msg.correlation_id
    )
    assert env["AI_TEAM_TASK_ID"] == str(
        msg.payload.task_id
    )
```

- [ ] **Step 1.5.2 — Run** — expect FAIL.

- [ ] **Step 1.5.3 — Edit
  `agents/team_lead/agent.py:222-241`**. Add
  `env=self._build_env(msg)`:

```python
        response = await self._llm.invoke(
            system_prompt=self.system_prompt(),
            user_message=user_msg,
            model=self.model_tier,
            allowed_tools=self.allowed_tools,
            timeout_s=self.llm_timeout_s,
            max_turns=self.max_turns,
            json_schema=DECOMPOSITION_SCHEMA,
            env=self._build_env(msg),
        )
```

- [ ] **Step 1.5.4 — Run all 3 new tests + the
  existing test_base_agent.py + test_team_lead_agent.py
  suites** — expect all green:

```
uv run pytest tests/unit/test_agent_env_injection.py tests/unit/test_base_agent.py tests/unit/test_team_lead_agent.py -v
```

#### Step 1.6 — Commit Phase 1

- [ ] **Step 1.6.1**:

```bash
git add agents/_base/agent.py agents/product_manager/agent.py agents/team_lead/agent.py tests/unit/test_agent_env_injection.py
git commit -m "feat(iter-19): per-message env injection in BaseAgent + PM/TL handle()

iter-18 demo run #2 wrote a pending_reviews row with
requesting_agent='unknown' because no agent role was
ever set per-invocation; the MCP server's
Context.from_env fallback defaulted to 'unknown'.

This patch adds BaseAgent._build_env(msg) which merges
AI_TEAM_AGENT_ROLE, AI_TEAM_CORRELATION_ID, and (when
present) AI_TEAM_TASK_ID on top of self.mcp_env, then
threads it through every invocation path:
- _invoke_with_retries grows a msg=AgentMessage param
- ProductManagerAgent.handle and TeamLeadAgent.handle
  (custom handle()s that bypass _invoke_with_retries)
  call _build_env(msg) directly

3 new unit tests in test_agent_env_injection.py pin the
contract for each call site."
```

### Phase 2 — `ai_team_tasks` Context correlation_id fallback

**Goal**: When the LLM forgets to pass `correlation_id`
in the `request_human_review` tool args (the same
pattern as iter-18's defense-in-depth for `agent`),
fall back to the env-sourced `AI_TEAM_CORRELATION_ID`
that Phase 1 now sets per-message.

**Files**:
- Modify: `tools/mcp_servers/ai_team_tasks/handlers.py`
- Test: `tests/unit/test_mcp_ai_team_tasks_handlers.py`
  (extend)

#### Step 2.1 — Red: assert correlation_id fallback

- [ ] **Step 2.1.1 — Append to
  `tests/unit/test_mcp_ai_team_tasks_handlers.py`**:

```python
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
    result = await handle_request_human_review(
        ctx, {"summary": "x", "agent": "qa_engineer"}
    )
    assert result["isError"] is False
    payload = json.loads(result["content"][0]["text"])
    assert payload["correlation_id"] == cid


def test_context_from_env_reads_correlation_id() -> None:
    cid = str(uuid4())
    ctx = Context.from_env(
        {"AI_TEAM_CORRELATION_ID": cid}
    )
    assert ctx.default_correlation_id == cid


def test_context_from_env_correlation_id_none_when_unset() -> None:
    ctx = Context.from_env({})
    assert ctx.default_correlation_id is None
```

- [ ] **Step 2.1.2 — Run** — expect FAIL (Context
  has no `default_correlation_id` field).

#### Step 2.2 — Green: add the field + fallback

- [ ] **Step 2.2.1 — Edit
  `tools/mcp_servers/ai_team_tasks/handlers.py`**.
  Extend `Context`:

```python
@dataclass(slots=True, frozen=True)
class Context:
    """Per-process context for ai_team_tasks handlers.

    `session_factory` is the async SQLAlchemy session-maker
    used to write `pending_reviews` rows. `default_agent`
    is the fallback used when a `tools/call` payload omits
    `agent`. `default_correlation_id` is the fallback when
    the payload omits `correlation_id` — iter-19 adds this
    after iter-18 demo Caveat 2 surfaced LLMs forgetting
    the field. Both defaults source from env
    (AI_TEAM_AGENT_ROLE / AI_TEAM_CORRELATION_ID) that
    BaseAgent now sets per-message.
    """

    session_factory: async_sessionmaker[AsyncSession]
    default_agent: str
    default_correlation_id: str | None = None

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> Context:
        e = env if env is not None else dict(os.environ)
        dsn = e.get("POSTGRES_DSN") or get_settings().postgres_dsn
        engine = create_async_engine(dsn, echo=False, future=True)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        return cls(
            session_factory=factory,
            default_agent=e.get("AI_TEAM_AGENT_ROLE", "unknown"),
            default_correlation_id=e.get("AI_TEAM_CORRELATION_ID"),
        )
```

- [ ] **Step 2.2.2 — Edit
  `handle_request_human_review`** to consult the
  fallback. Replace the existing block:

```python
    cid_raw = str(args.get("correlation_id", "")).strip()
    if not cid_raw:
        return _err("correlation_id is required")
```

with:

```python
    cid_raw = str(args.get("correlation_id", "")).strip()
    if not cid_raw and ctx.default_correlation_id:
        cid_raw = ctx.default_correlation_id
    if not cid_raw:
        return _err("correlation_id is required")
```

- [ ] **Step 2.2.3 — Run** — expect PASS:

```
uv run pytest tests/unit/test_mcp_ai_team_tasks_handlers.py -v
```

#### Step 2.3 — Commit Phase 2

- [ ] **Step 2.3.1**:

```bash
git add tools/mcp_servers/ai_team_tasks/handlers.py tests/unit/test_mcp_ai_team_tasks_handlers.py
git commit -m "feat(iter-19): ai_team_tasks Context correlation_id fallback

Defense-in-depth mirror of iter-18's default_agent
fallback. When request_human_review's args omit
correlation_id (the LLM forgot), consult
ctx.default_correlation_id sourced from
AI_TEAM_CORRELATION_ID env — which BaseAgent now
sets per-message in iter-19 Phase 1.

3 new unit tests pin the contract: (a) handler falls
back when args.correlation_id is empty,
(b) Context.from_env reads AI_TEAM_CORRELATION_ID,
(c) Context.from_env leaves the field None when env
is unset."
```

### Phase 3 — PM/TL allow-list hardening

**Goal**: Replace `allowed_tools = ()` on PM and TL with
a minimal explicit whitelist (`Read`, `Glob`, `Grep`),
closing the iter-18 leak where empty meant "all tools."
Add a parametrized regression test asserting no
production agent ever drops back to `()`.

**Decision**: explicit per-agent whitelist (Option B
from `iter_19_handoff.md` §1). Substrate-level fix
(Option A — special-case `()` as `--disallowed-tools "*"`
in `claude_code_headless.py`) was considered and rejected
for iter-19 scope — it changes behavior for any future
agent declaring `()` rather than fixing the existing
two outliers explicitly. The regression test below
guarantees no agent regresses to `()` even without the
substrate change.

**Files**:
- Modify: `agents/product_manager/agent.py:104`
- Modify: `agents/team_lead/agent.py:98`
- Test: `tests/unit/test_agent_allowed_tools_pin.py` (NEW)
- Test: `tests/unit/test_product_manager_agent.py` (NEW
  file if it doesn't exist; otherwise extend)

**Rationale for the chosen whitelist**: ADR-0004's matrix
row marks `Read`/`Glob`/`Grep` as ✅ for every agent
(read-only surveying). PM and TL each perform a single
structured-JSON LLM turn — they don't need write tools,
MCP tools, or Bash. The whitelist is the minimum
viable "safe non-empty set" that excludes
`mcp__ai_team_tasks__request_human_review` (the iter-18
leak) and all other MCP write tools.

#### Step 3.1 — Red: regression pin for non-empty allow-lists

- [ ] **Step 3.1.1 — Create
  `tests/unit/test_agent_allowed_tools_pin.py`**:

```python
"""iter-19 Phase 3: pin every concrete agent's
allowed_tools to a non-empty whitelist.

iter-18 demo Caveat 1 surfaced this: PM and TL both
declared `allowed_tools = ()` which
`core/llm/claude_code_headless.py:199-200` translates
to OMITTING the --allowed-tools flag entirely.
claude -p's default in that mode is permissive (all
configured MCP + native tools allowed). PM
unprompted-called the new
mcp__ai_team_tasks__request_human_review tool during
the iter-18 demo as a result.

This pin is the safety net. A future change that
removes an explicit whitelist by mistake is caught
here at CI time rather than in the next demo run.
"""

from __future__ import annotations

import pytest

from agents._base.agent import BaseAgent
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


# Note: BaseAgent itself keeps `allowed_tools = ()` as the
# class default — concrete agents must override. The pin
# below iterates concrete agents only.
_CONCRETE_AGENTS: list[type[BaseAgent]] = [
    ArchitectAgent,
    BackendDeveloperAgent,
    DesignerAgent,
    DevOpsAgent,
    FrontendDeveloperAgent,
    MarketResearcherAgent,
    ProductManagerAgent,
    QAEngineerAgent,
    SRESupportAgent,
    TeamLeadAgent,
]


@pytest.mark.parametrize("cls", _CONCRETE_AGENTS)
def test_allowed_tools_is_non_empty(
    cls: type[BaseAgent],
) -> None:
    """Empty allowed_tools triggers claude -p's
    permissive default. iter-18 Caveat 1."""
    assert cls.allowed_tools, (
        f"{cls.__name__}.allowed_tools is empty — would "
        f"trigger claude -p permissive default. See "
        f"iter_18_demo_report.md Caveat 1."
    )


@pytest.mark.parametrize(
    "cls", [ProductManagerAgent, TeamLeadAgent]
)
def test_pm_and_tl_exclude_request_human_review(
    cls: type[BaseAgent],
) -> None:
    """PM/TL should not be able to surprise-call
    request_human_review. iter-18 demo run #2 wrote
    a row via PM unprompted; the iter-19 fix forbids
    that path."""
    assert (
        "mcp__ai_team_tasks__request_human_review"
        not in cls.allowed_tools
    ), (
        f"{cls.__name__} can still call "
        f"request_human_review — iter-18 leak not closed"
    )
```

- [ ] **Step 3.1.2 — Run** — expect FAIL on the
  `test_allowed_tools_is_non_empty[ProductManagerAgent]`
  and `[TeamLeadAgent]` cases (both still `()`).
  `test_pm_and_tl_exclude_request_human_review` should
  PASS today (because `()` doesn't contain the tool
  literally — but it's permissively allowed at the
  CLI level; the empty-set check is the actually
  load-bearing assertion).

```
uv run pytest tests/unit/test_agent_allowed_tools_pin.py -v
```

#### Step 3.2 — Green: explicit whitelist for PM and TL

- [ ] **Step 3.2.1 — Edit
  `agents/product_manager/agent.py:104`**:

Change:
```python
    allowed_tools: ClassVar[tuple[str, ...]] = ()
```
to:
```python
    # iter-19: explicit non-empty whitelist replaces
    # iter-3's `()` (which fell back to claude -p's
    # permissive default — see iter_18_demo_report.md
    # Caveat 1). PM emits one structured-JSON turn
    # via --json-schema; Read/Glob/Grep cover the rare
    # case of consulting docs/backlog/ for prior
    # stories. No MCP tools, no Write/Edit, no Bash.
    allowed_tools: ClassVar[tuple[str, ...]] = (
        "Read",
        "Glob",
        "Grep",
    )
```

- [ ] **Step 3.2.2 — Edit
  `agents/team_lead/agent.py:98`**. Same change with
  TL-specific narrative:

```python
    # iter-19: explicit non-empty whitelist replaces
    # iter-1's `()` (which fell back to claude -p's
    # permissive default — see iter_18_demo_report.md
    # Caveat 1). TL emits one structured-JSON
    # decomposition turn; Read/Glob/Grep cover
    # consulting docs/iterations/ or docs/sandbox/
    # for the source spec. No MCP tools, no
    # Write/Edit, no Bash.
    allowed_tools: ClassVar[tuple[str, ...]] = (
        "Read",
        "Glob",
        "Grep",
    )
```

- [ ] **Step 3.2.3 — Run the pin** — expect PASS:

```
uv run pytest tests/unit/test_agent_allowed_tools_pin.py -v
```

- [ ] **Step 3.2.4 — Run the existing unit suite to
  catch fallout**:

```
uv run pytest tests/unit/ -x -q
```

  Expected: all green. Existing PM and TL tests
  (`test_team_lead_agent.py`, integration paths)
  don't assert on `allowed_tools`, so they should be
  unaffected.

#### Step 3.3 — Commit Phase 3

- [ ] **Step 3.3.1**:

```bash
git add agents/product_manager/agent.py agents/team_lead/agent.py tests/unit/test_agent_allowed_tools_pin.py
git commit -m "feat(iter-19): explicit allow-list on PM + TL (close iter-18 Caveat 1)

iter-18 demo Caveat 1: PM and TL both declared
allowed_tools = () which core/llm/claude_code_headless.py
omits the --allowed-tools flag for entirely, triggering
claude -p's permissive default (all configured MCP +
native tools allowed). PM unprompted-called
mcp__ai_team_tasks__request_human_review during the
iter-18 demo as a result, writing the historic-first
pending_review row from the wrong agent.

This patch sets PM and TL allowed_tools to (Read, Glob,
Grep) — the minimal non-empty whitelist that excludes
all MCP tools and all write tools. Both agents emit a
single structured-JSON LLM turn (USER_STORIES_SCHEMA /
DECOMPOSITION_SCHEMA via --json-schema); neither needs
to call MCP tools for the user-story or decomposition
task.

New test file test_agent_allowed_tools_pin.py
parametrizes over all 10 concrete agents asserting
allowed_tools is non-empty, plus an explicit pin that
PM and TL cannot call request_human_review."
```

### Phase 4 — PM `llm_timeout_s` 300 → 600

**Goal**: Align PM with Backend/Architect/Designer/Frontend/DevOps
at the iter-11 default of 600s. iter-17 saw PM at 277s
(92% of cap); iter-18 demo run #1 hit the 300s wall and
burned $1.75 on tenacity retries.

**Files**:
- Modify: `agents/product_manager/agent.py:106-109`
- Modify: `tests/unit/test_agent_timeouts.py:41`

#### Step 4.1 — Red: flip the pin

- [ ] **Step 4.1.1 — Edit
  `tests/unit/test_agent_timeouts.py:41`**:

Change:
```python
        (ProductManagerAgent, 300),
```
to:
```python
        (ProductManagerAgent, 600),
```

- [ ] **Step 4.1.2 — Run** — expect FAIL (PM is
  still 300 in the agent class):

```
uv run pytest tests/unit/test_agent_timeouts.py::test_llm_timeout_s -v
```

#### Step 4.2 — Green: bump the agent

- [ ] **Step 4.2.1 — Edit
  `agents/product_manager/agent.py:106-109`**:

Change:
```python
    # iter-3 demo: PM's user-story decomposition averaged ~150 s on
    # Sonnet for the v2 spec, well inside 300 s. Stays at 300 after
    # iter-11 flipped BaseAgent's default to 600.
    llm_timeout_s: ClassVar[int] = 300
```
to:
```python
    # iter-19: bumped 300 → 600 after iter-18 demo run #1 hit the
    # 300s wall and burned $1.75 on tenacity retries. iter-17 had
    # already measured PM at 277s (92% of cap). Joins the LLM-bound
    # majority (Backend / Architect / Designer / Frontend / DevOps)
    # at the iter-11 default of 600s.
    llm_timeout_s: ClassVar[int] = 600
```

- [ ] **Step 4.2.2 — Run** — expect PASS.

#### Step 4.3 — Commit Phase 4

- [ ] **Step 4.3.1**:

```bash
git add agents/product_manager/agent.py tests/unit/test_agent_timeouts.py
git commit -m "fix(iter-19): bump PM llm_timeout_s 300 → 600 (close iter-18 Caveat 5)

iter-17 saw PM at 277s (92% of the 300s cap); iter-18
demo run #1 hit the 300s wall and burned \$1.75 on
tenacity retries. The 300s value was an iter-3
optimization for the original 150s observation; the
real-LLM variance pushes it past 300s about half the
time on Sonnet.

PM joins the LLM-bound majority (Backend, Architect,
Designer, Frontend, DevOps) at the iter-11 default of
600s. tests/unit/test_agent_timeouts.py pin updated."
```

### Phase 5 — `demo_iter_19.sh` with poll-loop + auto-approve fixes

**Goal**: Clone `scripts/demo_iter_18.sh` to
`scripts/demo_iter_19.sh` with iter-19 narrative, then
apply the two demo-script bug fixes (Caveat 3 + Caveat 4)
inline.

**Files**:
- Create: `scripts/demo_iter_19.sh` (clone of iter-18 +
  iter-19 narrative + fixes)
- Modify: `Makefile` (add `demo-19` alias mirroring
  `demo-18`)

#### Step 5.1 — Clone the iter-18 script

- [ ] **Step 5.1.1**:

```bash
cp scripts/demo_iter_18.sh scripts/demo_iter_19.sh
chmod +x scripts/demo_iter_19.sh
```

#### Step 5.2 — Rewrite the header narrative

- [ ] **Step 5.2.1 — Replace lines 1-44** of
  `scripts/demo_iter_19.sh` with an iter-19 narrative
  that describes the 5 caveats now closed and the
  expected outcome (QA-emitted row with
  `requesting_agent='qa_engineer'`). Keep the
  prerequisites block (`.env`, `claude` CLI, Docker,
  `.venv`, `gh`) verbatim.

  Concrete header diff: change the opening comment
  block to reference iter_19.md + the 5 closed caveats.
  Update the cost-ceiling note (iter-18 was $3.43 — set
  the iter-19 ceiling at $5).

#### Step 5.3 — Fix Caveat 3 (poll-loop QA-specific)

- [ ] **Step 5.3.1 — Edit
  `scripts/demo_iter_19.sh` around line 142-152**.
  Replace:

```bash
    review_count=$(curl -sf -H "Authorization: Bearer $OWNER_TOKEN" http://127.0.0.1:8000/api/reviews 2>/dev/null \
        | python3 -c 'import sys, json; print(len(json.load(sys.stdin)))' 2>/dev/null || echo 0)
    if [[ "$review_count" -ge 1 ]]; then
        ok "QA produced a pending_review (count=$review_count)"
        break
    fi
```

with:

```bash
    # iter-19 fix (iter-18 demo Caveat 3): poll for a
    # SPECIFIC QA-emitted review rather than any
    # review. iter-18 demo run #2 broke the loop the
    # moment PM unprompted-wrote a row, killing the
    # dispatcher before Architect/Backend/Designer/
    # Frontend/QA finished. After iter-19 Phase 3
    # (PM/TL allow-list hardening), PM can no longer
    # call request_human_review at all — this filter
    # is belt-and-braces for that fix.
    qa_review_count=$(curl -sf -H "Authorization: Bearer $OWNER_TOKEN" \
        http://127.0.0.1:8000/api/reviews 2>/dev/null \
        | python3 -c 'import sys, json; data = json.load(sys.stdin); print(sum(1 for r in data if r.get("requesting_agent") == "qa_engineer"))' 2>/dev/null \
        || echo 0)
    if [[ "$qa_review_count" -ge 1 ]]; then
        ok "QA produced a pending_review (qa_engineer count=$qa_review_count)"
        break
    fi
```

  Also update the `if [[ "$review_count" -lt 1 ]]; then`
  guard further down (line 169) to read
  `qa_review_count` instead of `review_count`, and the
  similar check inside the post-retry while loop
  (~lines 193-201).

#### Step 5.4 — Fix Caveat 4 (auto-approve bash fallback)

- [ ] **Step 5.4.1 — Edit
  `scripts/demo_iter_19.sh` around line 212-228**.
  Replace:

```bash
step "6.6/7 — Auto-approve any pending_reviews (close the loop)"
REVIEWS_JSON=$(curl -sf -H "Authorization: Bearer $OWNER_TOKEN" \
    http://127.0.0.1:8000/api/reviews 2>/dev/null || echo '[]')
echo "$REVIEWS_JSON" | python3 <<'PY' || true
```

with:

```bash
step "6.6/7 — Auto-approve any pending_reviews (close the loop)"
# iter-19 fix (iter-18 demo Caveat 4): belt-and-braces
# fallback. iter-18 run #2 hit JSONDecodeError on
# empty stdin even though the API was responsive —
# bash precedence on `$(... || echo '[]')` is
# fragile under `set -u -o pipefail`. Assign curl
# output, then `${VAR:-[]}` to guarantee non-empty
# input to python.
REVIEWS_JSON=$(curl -sf -H "Authorization: Bearer $OWNER_TOKEN" \
    http://127.0.0.1:8000/api/reviews 2>/dev/null || true)
REVIEWS_JSON="${REVIEWS_JSON:-[]}"
printf '%s' "$REVIEWS_JSON" | python3 <<'PY' || true
```

  (Note: `printf '%s'` instead of `echo` — `echo` can
  swallow leading hyphens or interpret backslashes
  on some platforms.)

#### Step 5.5 — Add Makefile alias

- [ ] **Step 5.5.1 — Inspect `Makefile`** for the
  existing `demo-18` target:

```bash
grep -n "demo-18\|demo:" Makefile
```

- [ ] **Step 5.5.2 — Add `demo-19`**. Mirror the
  `demo-18` shape:

```makefile
demo-19:
	AI_TEAM_DEMO_NON_INTERACTIVE=1 bash scripts/demo_iter_19.sh
```

Update the `demo` alias (if it points at iter-18) to
point at iter-19:

```makefile
demo: demo-19
```

#### Step 5.6 — Smoke-test the script syntax

- [ ] **Step 5.6.1**:

```bash
bash -n scripts/demo_iter_19.sh
```

  Expected: silent (no syntax errors).

- [ ] **Step 5.6.2** — quick `shellcheck` if installed:

```bash
shellcheck scripts/demo_iter_19.sh || true
```

  Triage any new warnings the iter-19 edits introduced
  (the iter-18 baseline already has a few — only treat
  iter-19-introduced ones as blockers).

#### Step 5.7 — Commit Phase 5

- [ ] **Step 5.7.1**:

```bash
git add scripts/demo_iter_19.sh Makefile
git commit -m "chore(demo): demo_iter_19.sh with Caveat 3 + Caveat 4 fixes

Clone of scripts/demo_iter_18.sh with iter-19
narrative + two demo-script bug fixes:

- Caveat 3 (poll-loop too eager): poll filters JSON
  for objects where requesting_agent == 'qa_engineer'
  rather than any review. iter-18 demo run #2 broke
  the loop on PM's unprompted row, killing the chain.

- Caveat 4 (auto-approve JSONDecodeError): belt-and-
  braces fallback REVIEWS_JSON=\${REVIEWS_JSON:-[]}
  between curl and python. Bash precedence on
  \$(... || echo '[]') under -u -o pipefail proved
  fragile.

Makefile alias demo-19 added; demo target repointed."
```

### Phase 6 — Validation gates

**Goal**: All CI-equivalent gates green before the
real-LLM demo runs. Catches regressions in agents/tests
that the per-file work might have missed.

#### Step 6.1 — Run each gate

- [ ] **Step 6.1.1 — ruff check**:

```bash
uv run ruff check .
```

  Expected: `All checks passed!`

- [ ] **Step 6.1.2 — ruff format check**:

```bash
uv run ruff format --check .
```

  Expected: no diffs.

- [ ] **Step 6.1.3 — mypy strict**:

```bash
uv run mypy
```

  Expected: `Success: no issues found in N source files`.

- [ ] **Step 6.1.4 — bandit high-only**:

```bash
uv run bandit -ll -q -r core agents apps tools
```

  Expected: `High: 0`.

- [ ] **Step 6.1.5 — full unit suite**:

```bash
uv run pytest tests/unit -q
```

  Expected: all green. Iter-18's 400 unit baseline +
  iter-19's new tests:
  - test_agent_env_injection.py: 3 tests
  - test_mcp_ai_team_tasks_handlers.py: +3 tests
  - test_agent_allowed_tools_pin.py: 12 parametrized
    cases (10 non-empty + 2 PM/TL exclusion)
  ≈ 418 unit tests passing.

- [ ] **Step 6.1.6 — full integration suite**
  (requires `make up`):

```bash
make up >/dev/null && uv run pytest tests/integration -q
```

  Expected: 50 integration tests pass (unchanged
  from iter-18).

- [ ] **Step 6.1.7 — smoke-llm against real
  `claude -p`**:

```bash
make smoke-llm
```

  Expected: `Overall: PASS`. Validates ADR-008
  substrate behavior is intact after the
  `_invoke_with_retries` signature change.

#### Step 6.2 — If any gate fails

- [ ] **Step 6.2.1**: Fix the root cause directly.
  Do NOT skip hooks or downgrade gates. Re-run the
  failing gate after each fix. Do NOT proceed to
  Phase 7 until every gate above is green.

### Phase 7 — Real-LLM iter-19-shape demo + report

**Goal**: Run the iter-18-shape demo with iter-19
fixes against real `claude -p`. The historic-first
QA-emitted `pending_reviews` row with
`requesting_agent='qa_engineer'` is the success
signal.

#### Step 7.1 — Pre-flight checks

- [ ] **Step 7.1.1 — Confirm Docker + .env**:

```bash
docker ps --filter name=ai_team_ --format '{{.Names}} {{.Status}}' \
    && head -1 .env >/dev/null && echo OK
```

- [ ] **Step 7.1.2 — Confirm `claude` auth**:

```bash
claude /status || true
```

  Expected: shows the owner's Max 5x subscription
  status (no API key prompt).

- [ ] **Step 7.1.3 — Reset `pending_reviews` so the
  iter-19 row is unambiguously the new one**:

```bash
docker exec ai_team_postgres psql -U ai_team -d ai_team -c \
    "DELETE FROM pending_reviews WHERE status = 'pending';"
```

  Approved iter-18 row is kept (its `status` is
  `approved`); only stale pendings (if any) get cleared.

#### Step 7.2 — Run the demo

- [ ] **Step 7.2.1**:

```bash
AI_TEAM_DEMO_NON_INTERACTIVE=1 bash scripts/demo_iter_19.sh \
    2>&1 | tee /tmp/iter_19_demo_run_1.log
```

  Expected wall-clock: 30 min initial chain + 15 min
  retry window = 45 min total. Cost ceiling: $5.

- [ ] **Step 7.2.2 — Watch the chain**: in another
  shell, `uv run ai-team watch --correlation <prefix>`
  using the correlation_id printed at step 5/7. Don't
  intervene unless something is structurally wrong
  (e.g. all 7 sub-task assignments dispatched but
  none returned a `task_report` after 15 min).

#### Step 7.3 — Capture results

- [ ] **Step 7.3.1 — Inspect the row**:

```bash
docker exec ai_team_postgres psql -U ai_team -d ai_team -c \
    "SELECT id, correlation_id, requesting_agent, status, summary
     FROM pending_reviews ORDER BY created_at DESC LIMIT 5;"
```

  Expected success row:
  - `requesting_agent = 'qa_engineer'` (NOT
    `'unknown'`, NOT `'product_manager'`)
  - `status = 'pending'` (until the auto-approve
    step runs)
  - `correlation_id` matches the demo's CORRELATION
  - `summary` looks like a QA verdict
    (`"X/Y tests pass"` shape)

- [ ] **Step 7.3.2 — Inspect audit_log**: confirm a
  `qa_engineer → team_lead task_report(status=done)`
  row exists for the same correlation. If yes, the
  iter-17 7-agent chain ran again under iter-19's
  hardened allow-list.

- [ ] **Step 7.3.3 — Cost tally**: pull
  `cost_cents` aggregate:

```bash
docker exec ai_team_postgres psql -U ai_team -d ai_team -c \
    "SELECT SUM((payload_json -> 'metadata' -> 'llm' ->> 'cost_cents')::int) AS total_cents
     FROM audit_log
     WHERE correlation_id = '<CORRELATION>';"
```

#### Step 7.4 — Retry if first run blocks

- [ ] **Step 7.4.1**: If the first run hits a known
  non-iter-19 failure (e.g. iter-17 MCP race, iter-15
  Max-5x session limit), `ai-team retry-blocked <task_id>`
  and continue. Cap at 2 runs total; if the second
  run also fails, write up what happened in the
  demo report and treat the iter-19 gates as
  validated-by-unit-tests-only.

#### Step 7.5 — Write the demo report

- [ ] **Step 7.5.1 — Create
  `docs/iterations/iter_19_demo_report.md`** mirroring
  `iter_18_demo_report.md` shape. Required sections:

```markdown
# Iter-19 real-LLM end-to-end demo — report

- Date, Run by, Script, Task, Correlation IDs, Outcome
- Verdict in one line
- Run #N walkthrough (audit log excerpt + pending_reviews row dump)
- What worked
- What didn't (carry-overs to iter-20)
- Cost / quota table
- Artifacts produced this iteration
- Why this demo matters (one line on the
  requesting_agent='qa_engineer' significance)
- Action items for iter-20
```

#### Step 7.6 — Commit demo artifacts

- [ ] **Step 7.6.1**:

```bash
git add docs/iterations/iter_19_demo_report.md
git commit -m "docs(iter-19): real-LLM demo report — QA-emitted pending_review"
```

### Phase 8 — Retro + iter-20 handoff

**Goal**: Close the loop with a retro that captures
the surprises iter-19 surfaced, and a handoff prompt
the next session can paste verbatim.

**Files**:
- Create: `docs/iterations/iter_19_retro.md`
- Create: `docs/iterations/iter_20_handoff.md`

#### Step 8.1 — Retro

- [ ] **Step 8.1.1 — Write
  `docs/iterations/iter_19_retro.md`** mirroring
  `iter_18_retro.md`. Required sections:

```markdown
# Iteration 19 — Retrospective

- Closed: <date>. N commits on `worktree-iter-19`.
- Headline: <one line>
- What shipped (Phase-by-phase)
- What went well (3-5 bullets)
- What didn't (3-5 bullets, each tagged for iter-20)
- Surprises (3-5 bullets)
- Action items for iter-20 (numbered, top items first)
- Stats (commits / LOC / tests / real-LLM spend /
  diff-cover / demo wall-clock)
- Ready-to-paste prompt for iter-20: pointer to
  `iter_20_handoff.md`
```

#### Step 8.2 — Handoff

- [ ] **Step 8.2.1 — Write
  `docs/iterations/iter_20_handoff.md`** mirroring
  `iter_19_handoff.md`. Required sections:

```markdown
# Iteration 20 handoff

- Where we are (one paragraph, current main commit SHA)
- Carry-over items in priority order (renumber from
  iter_19_handoff.md minus the now-closed items, plus
  whatever new items surfaced in the iter-19 demo
  report)
- Hard constraints unchanged (copy verbatim from
  iter_19_handoff.md and append any iter-19-locked
  decisions)
- Inherited decisions (append iter-19 entries:
  PM/TL allow-list, env-injection contract,
  Context.default_correlation_id, PM 600s timeout)
- Ready-to-paste prompt for the new session
```

#### Step 8.3 — Commit

- [ ] **Step 8.3.1**:

```bash
git add docs/iterations/iter_19_retro.md docs/iterations/iter_20_handoff.md
git commit -m "docs(iter-19): retro + iter-20 handoff"
```

### Phase 9 — Merge to `main`

**Goal**: Squash-merge `worktree-iter-19` into `main`
once all CI green. Per CLAUDE.md the dev-PR path is
self-approve; the AI-agent-task-report path
(`pending_reviews`) is separate and was just
exercised in Phase 7.

#### Step 9.1 — Push the branch

- [ ] **Step 9.1.1**:

```bash
git push -u origin worktree-iter-19
```

#### Step 9.2 — Open the PR

- [ ] **Step 9.2.1**:

```bash
gh pr create --title "iter-19: close iter-18 demo caveats (PM/TL allow-list, env injection, PM timeout, demo fixes)" \
    --body "$(cat <<'EOF'
## Summary

- iter-18 demo's 5 caveats closed; re-run produced
  the historic-first QA-emitted pending_review row
  with requesting_agent='qa_engineer' (not 'unknown',
  not PM).
- Phase 1: per-message env injection in BaseAgent +
  PM/TL handle (AI_TEAM_AGENT_ROLE, _CORRELATION_ID,
  _TASK_ID).
- Phase 2: ai_team_tasks Context fallback for
  correlation_id (defense-in-depth mirror of iter-18's
  default_agent fallback).
- Phase 3: explicit allow-list (Read/Glob/Grep) on PM
  and TL; new pin test asserts no concrete agent
  declares allowed_tools = ().
- Phase 4: PM llm_timeout_s 300 → 600.
- Phase 5: demo_iter_19.sh with QA-specific poll-loop
  + auto-approve bash fallback fix.

## Test plan

- [x] ruff check + ruff format --check pass
- [x] mypy --strict passes
- [x] bandit -ll high-only: 0
- [x] tests/unit: 418 pass
- [x] tests/integration: 50 pass
- [x] make smoke-llm: PASS
- [x] real-LLM demo: QA-emitted pending_review row
      with requesting_agent='qa_engineer' (see
      docs/iterations/iter_19_demo_report.md)

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

#### Step 9.3 — Wait for CI then squash-merge

- [ ] **Step 9.3.1**:

```bash
gh pr checks --watch
```

  Wait for all checks green.

- [ ] **Step 9.3.2**: Squash-merge:

```bash
gh pr merge --squash --delete-branch
```

  Per CLAUDE.md: self-approve OK on dev PRs;
  AI-agent task_report path is independent.

#### Step 9.4 — Verify `main` and confirm worktree cleanup

- [ ] **Step 9.4.1**:

```bash
git fetch origin
git log --oneline origin/main | head -5
```

  Confirm the iter-19 squash commit is on `origin/main`.

- [ ] **Step 9.4.2 — Leave worktree state**: the
  current worktree (`.claude/worktrees/iter-2c`) stays
  in place. The next iteration starts from
  `origin/main` per the `iter_20_handoff.md` ready-to-
  paste prompt.

## Success criteria (definition of done for iter-19)

1. **Phase 1** — `_build_env(msg)` returns the
   expected dict; all 3 invocation paths
   (BaseAgent / PM / TL) pass it as
   `LLMClient.invoke(env=...)`. 3 new unit tests
   pin the contract.
2. **Phase 2** — `Context.default_correlation_id`
   field exists; `handle_request_human_review`
   falls back to it; `Context.from_env` reads
   `AI_TEAM_CORRELATION_ID`. 3 new unit tests pin
   the contract.
3. **Phase 3** — Neither `ProductManagerAgent` nor
   `TeamLeadAgent` declares `allowed_tools = ()`.
   New `test_agent_allowed_tools_pin.py` asserts
   non-empty for all 10 concrete agents +
   request_human_review excluded from PM/TL.
4. **Phase 4** — `ProductManagerAgent.llm_timeout_s == 600`.
   `test_agent_timeouts.py` pin flipped.
5. **Phase 5** — `scripts/demo_iter_19.sh` exists;
   poll filters on `requesting_agent='qa_engineer'`;
   auto-approve uses `${REVIEWS_JSON:-[]}` fallback.
   `make demo-19` runs the script. `bash -n` passes.
6. **Phase 6** — Every gate (ruff / ruff format /
   mypy / bandit / unit / integration / smoke-llm)
   green.
7. **Phase 7** — Real-LLM demo produces a
   `pending_reviews` row with
   `requesting_agent='qa_engineer'` (not 'unknown',
   not PM). Cost under $5. Demo report committed.
8. **Phase 8** — Retro + iter-20 handoff committed.
9. **Phase 9** — Squash-merged to `main` with all
   CI green.

## Out of scope (deferred to iter-20+)

- **TL Backend decomposition** (NINE-iteration
  carry-over). Defer until next chain hits a 600s+
  Backend session.
- **HoldQueue persistence** (Postgres-backed).
  In-memory still loses on restart.
- **`mark_task_done` / `update_task_status` real
  implementations**. iter-19 audits prompts:
  - QA prompt instructs `request_human_review` only
    (no `mark_task_done`).
  - Backend / Architect / Designer / Frontend prompts
    similarly don't call these. Until an agent's
    prompt explicitly does, leave the stubs in
    place. Pinned by regression tests.
- **`pytest-rerunfailures` plugin pin** — CI flake
  carry-over.
- **Agents'-branch-isolation investigation** —
  iter-17 retro #7.
- **TL auto-hop investigation** — iter-17 handoff
  #3.
- **TL over-decomposition prompt hint** — small
  prompt edit, deferred.
- **`audit_writer` Postgres role enforcement**.
- **Hash-chain alert job**.
- **`GitHubTargetRepo` implementation** — waiting
  on first commercial product.
- **TL decomposition transactional insert**.
- **`BaseAgent.handle()` template-method refactor**
  — defer until next agent rolls in.
- **Substrate-level fix to `claude_code_headless.py`
  for empty `allowed_tools`** — Option A in
  `iter_19_handoff.md` §1. Rejected for iter-19
  scope because the pin test guarantees no agent
  regresses to `()`.

## Hard constraints (carry-forward — do not contradict)

Verbatim from `iter_19_handoff.md`. The new
iter-19-locked decisions to append to iter-20's
inherited list:

- **iter-19**: `BaseAgent._build_env(msg)` is the
  canonical helper for per-invocation env injection.
  Sets `AI_TEAM_AGENT_ROLE`, `AI_TEAM_CORRELATION_ID`,
  and (when present) `AI_TEAM_TASK_ID`, merging
  `mcp_env` on top. Both the default `handle()` path
  (via `_invoke_with_retries`) and the custom PM /
  TL `handle()` paths consume it.
- **iter-19**: `ai_team_tasks` `Context` has a
  `default_correlation_id: str | None` field sourced
  from `AI_TEAM_CORRELATION_ID`. `handle_request_human_review`
  falls back to it when args omit `correlation_id`.
  Same defense-in-depth pattern as iter-18's
  `default_agent`.
- **iter-19**: PM and TL `allowed_tools = ("Read",
  "Glob", "Grep")` — explicit non-empty whitelist
  replacing the iter-1/iter-3 `()` permissive-default
  leak. Pin test
  (`tests/unit/test_agent_allowed_tools_pin.py`)
  prevents regression.
- **iter-19**: PM `llm_timeout_s = 600` (was 300).
- **iter-19**: `scripts/demo_iter_19.sh` poll filters
  on `requesting_agent='qa_engineer'`; auto-approve
  uses `${REVIEWS_JSON:-[]}` belt-and-braces
  fallback.

## Risk + mitigations

| Risk | Likelihood | Mitigation |
|------|-----------:|-----------|
| Stripping PM's `request_human_review` access regresses some future "PM flags ambiguous story" workflow | Low | None of the production prompts call this from PM today; ADR-004 still lists it as ✅ for PM, so a future iter can re-add it with deliberate prompt + test work. |
| `_build_env` env dict accidentally overwrites a critical inherited env var (PATH, HOME) | Very low | `claude_code_headless.py:233` merges on top of `os.environ` — `_build_env` only sets `AI_TEAM_*` keys, no overlap with system vars. |
| Phase 1 signature change to `_invoke_with_retries` breaks a downstream caller | Low | Only `BaseAgent.handle()` calls it. PM/TL bypass it entirely (and were already custom). All existing tests stay green or are updated in Phase 1. |
| Real-LLM demo hits Max-5x session-limit (iter-15 carry-over) mid-run | Medium | iter-15 BLOCKED(budget) path catches it; `ai-team retry-blocked` is the recovery action. Capped at 2 retries per Phase 7.4. |
| Demo bash fix introduces new shell-quoting bug | Low | `bash -n` + `shellcheck` in Phase 5.6 + manual re-read of the diff. The fix is mechanical (REVIEWS_JSON assignment + parameter-expansion default). |
| PM 600s timeout masks a real slowness regression | Low | Same risk Backend/Architect/Designer/Frontend/DevOps have lived with for 8+ iterations; the metrics tab in `ai-team digest` surfaces per-agent durations so a 500s+ PM run is still visible. |

## What this plan does NOT do

- **Does not change ADR-0004's tool matrix.** The
  matrix remains the source of truth for what each
  agent *may* have. iter-19 closes the gap between
  the matrix and what each agent *actually has* for
  PM and TL specifically.
- **Does not implement substrate-level `()` →
  `--disallowed-tools "*"` translation.** Considered
  and rejected (see Phase 3 decision). The pin test
  is the safety net.
- **Does not address the 9 deferred carry-overs.**
  They remain on `iter_20_handoff.md`'s priority list.
- **Does not change the QA prompt.** iter-18's
  prompt edit (workflow step 4 with
  `request_human_review`) stays as-is. Phase 7's
  demo will confirm the prompt path now executes
  cleanly under iter-19's env-injection.
