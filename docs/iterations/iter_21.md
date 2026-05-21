# Iteration 21 — Plan

- **Status**: Draft (awaiting owner approval)
- **Plan author**: Claude (Opus 4.7)
- **Date drafted**: 2026-05-21
- **Base commit**: iter-20 squash on `main`
  (will be confirmed at worktree-cut time via
  `git rev-parse origin/main`).
- **Branch**: `worktree-iter-21` (already
  present via the iter-2c worktree —
  `git rev-parse --abbrev-ref HEAD` ==
  `worktree-iter-20`; iter-21 work renames it
  before any commit or cuts a fresh branch
  from `origin/main`).
- **Anchors (do not contradict)**: ADR-0001
  (orchestrator), ADR-0004 (per-agent tool
  allowlist), ADR-0006 (model tier per agent),
  ADR-0009 (target-repo), iter-20 retro + demo
  report + handoff.
- **Carry-overs addressed**: items 1–4 of
  `iter_21_handoff.md` — Backend runtime
  tripwire, demo auto-approve bash fix done
  right, Architect spend investigation, and
  re-attempt the QA-emitted `pending_reviews`
  row criterion.
- **Deferred unchanged**: carry-overs 5–15 from
  `iter_21_handoff.md` (HoldQueue persistence,
  `pytest-rerunfailures` plugin pin, TL
  auto-hop investigation, TL over-decomposition
  prompt hint, `audit_writer` role, hash-chain
  alert, `GitHubTargetRepo`, TL transactional
  insert, `BaseAgent` template refactor,
  `mark_task_done`/`update_task_status` real
  impls, substrate `--allowed-tools ""` fix).

## Goal in one sentence

**Close iter-20's #1 carry-over (Backend
runtime tripwire) and #2 carry-over (demo
auto-approve bash fix done right) so the
iter-19/20-shape demo can finally produce a
QA-emitted `pending_reviews` row with
`requesting_agent='qa_engineer'` — the success
criterion deferred for two iterations in a
row.**

## Investigation evidence (already gathered)

1. **iter-20 demo definitively confirms the
   prompt-only Backend decomposition is
   insufficient.** TL DID emit 2 Backend
   subtasks (audit rows 305 + 306, both
   `team_lead → backend_developer
   task_assignment`). The prompt edit worked
   structurally; one subtask still hit 600s.
   The LLM-side compliance with the "≤200 LOC"
   soft instruction is imperfect under stress.
   See `iter_20_demo_report.md` §Caveat A.

2. **`BackendDeveloperAgent.handle()` is the
   right place for the tripwire**
   (`agents/backend_developer/agent.py:136-150`).
   It runs on every `TASK_ASSIGNMENT`, BEFORE
   the `self._llm.invoke()` call that burns the
   600s. A pre-flight check that returns a
   BLOCKED `task_report` short-circuits the LLM
   turn entirely — the rejection costs zero
   dollars and zero wall-clock seconds.

3. **The existing TL auto-route plumbing
   already handles BLOCKED → routed
   `task_assignment`** in
   `agents/team_lead/agent.py:251-302`
   (`_maybe_route_blocked`). Today it routes
   when `blocked_on` parses to a valid
   `AgentId`. For `blocked_on='task_too_large'`
   (NOT a valid `AgentId`), the current code
   falls through and returns `[]` — the chain
   stops and surfaces in the digest. We extend
   the routing so `task_too_large` triggers a
   **self-targeted** `task_assignment` (TL →
   TL) carrying the original task description
   (which Backend echoes into the BLOCKED
   summary) and a "re-decompose into ≤100 LOC
   subtasks" instruction.

4. **Anti-loop reuses the existing
   `_AUTO_ROUTED_MARKER = "auto-routed"`**
   string + `payload.summary.lower()` check at
   `agents/team_lead/agent.py:266`. Backend's
   tripwire summary echoes the marker if the
   incoming task description already carries
   it; second-hop trips refuse re-routing and
   surface to the owner. Aligns with the
   existing one-auto-hop rule.

5. **The real auto-approve bash bug**: the
   pattern at `scripts/demo_iter_20.sh:258`
   (`printf '%s' "$REVIEWS_JSON" | python3 <<'PY'`)
   is a **heredoc-vs-pipe conflict**, not a
   JSON parsing or precedence bug. Bash routes
   python's stdin to the HEREDOC source code,
   not the piped JSON. The iter-18 and iter-19
   fix attempts (`|| echo '[]'`, `${VAR:-[]}`
   + `printf`) both patched the wrong layer.
   The proven fix shape: `python3 - "$JSON"
   <<'PY' ... sys.argv[1]` — the `-` arg makes
   python read source from stdin (the heredoc),
   and the JSON arrives via `sys.argv[1]`. No
   conflict.

6. **Architect spend trajectory**: $0.78
   (iter-19) → $2.88 (iter-20), 3.7× jump in
   one iteration. iter-20 Architect session
   was 473s wall-clock on opus, producing
   `docs/adr/0027-idea-validator-v2-iter-19-architecture-pointer.md`
   plus `docs/adr/0028-idea-validator-v2-iter-20-be-core-be-cli-split.md`
   (visible via `ls docs/adr/`). Hypothesis: the
   "iter-N pointer ADR" pattern is producing
   long ADRs that re-derive context from prior
   ADRs every iteration. Phase 4 is an
   investigation-only audit; no code change
   unless the audit produces a clear win
   (likely a follow-up prompt edit in iter-22).

7. **`AI_TEAM_REPO_ROOT` env var IS the
   target-repo root** used by all ai_team_repo
   handlers (`tools/mcp_servers/ai_team_repo/handlers.py:63`).
   The Backend agent's python process inherits
   the same env via the dispatcher, so the
   tripwire can resolve `os.environ.get(
   "AI_TEAM_REPO_ROOT")` for the
   file-existence check. Fallback to
   `_REPO_ROOT` (orchestrator dir) for unit
   tests that run without the env set.

8. **Bandit surface area**: the tripwire is a
   pure-python regex + filesystem-read check
   with no shell-out and no untrusted exec.
   Same bandit posture as `_user_message_for`.
   No new high-severity findings expected.

9. **All carry-overs ≥5 stay deferred** —
   iter-21's three priorities + demo re-run
   are enough scope for one iteration. The
   handoff says so. iter-21 will surface its
   own carry-over list in
   `iter_21_retro.md` + `iter_22_handoff.md`.

## Phases — bite-sized TDD steps with exact paths

### Phase 0 — Pre-flight worktree + plan commit

**Goal**: Establish the iter-21 working branch,
land this plan, await owner approval before
touching code.

**Files**:
- Create: `docs/iterations/iter_21.md` (this
  file).

- [ ] **Step 0.1**: Confirm we are on
  `worktree-iter-20` and that iter-20 is
  merged to main. If iter-21's worktree
  doesn't yet exist, follow the iter-20
  pattern: rename branch `worktree-iter-20`
  → `worktree-iter-21` after merge OR cut
  fresh from `origin/main`. Surface the
  decision to the owner before pushing any
  iter-21 commit.

  ```bash
  git fetch origin
  git status
  git rev-parse --abbrev-ref HEAD
  git log -1 --oneline origin/main
  ```

  Expected: `worktree-iter-20` checked out;
  `main` HEAD includes the iter-20 squash.

- [ ] **Step 0.2**: Write the plan (this
  document). DO NOT proceed past Phase 0
  until the owner approves.

- [ ] **Step 0.3**: Commit the plan.

  ```bash
  git add docs/iterations/iter_21.md
  git commit -m "$(cat <<'EOF'
  docs(iter-21): plan — Backend runtime tripwire + demo bash fix

  Phase 1: Backend pre-flight rejects too-large
  task_assignments → BLOCKED(blocked_on='task_too_large').
  Phase 2: TL re-decomposes via self-targeted
  task_assignment with anti-loop guard.
  Phase 3: scripts/demo_iter_21.sh fixes the
  heredoc-vs-pipe auto-approve bug for real.
  Phase 4: Architect spend audit ($0.78 → $2.88).
  Phase 5: Re-run iter-19/20-shape demo; expect
  QA-emitted pending_review row.

  Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
  EOF
  )"
  ```

### Phase 1 — Backend runtime tripwire (TDD)

**Goal**: `BackendDeveloperAgent.handle()`
rejects an incoming `TASK_ASSIGNMENT` whose
description plausibly exceeds ~200 LOC scope,
returning `BLOCKED(blocked_on='task_too_large')`
BEFORE the LLM is invoked. Cost of rejection:
~1ms, ~0 dollars.

**Files**:
- Modify: `agents/backend_developer/agent.py`
- Modify: `tests/unit/test_backend_developer_agent.py`

#### Step 1.1 — Write the failing tests

- [ ] Add four tests to
  `tests/unit/test_backend_developer_agent.py`
  covering:
  1. Long-description trip (>1500 chars).
  2. File-path trip (≥3 file-path tokens not
     on disk).
  3. Happy path (short description, no trip).
  4. Auto-route marker propagation (incoming
     description contains `[auto-routed`, so
     BLOCKED summary echoes
     `[auto-routed already]`).

  ```python
  # tests/unit/test_backend_developer_agent.py
  # (additions; existing tests untouched)

  import pytest
  from uuid import uuid4

  from agents.backend_developer.agent import (
      BackendDeveloperAgent,
      _is_task_too_large,
  )
  from core.messaging.schemas import (
      AgentId,
      AgentMessage,
      MessageType,
      Priority,
      TaskAssignmentPayload,
      TaskReportPayload,
      TaskStatus,
  )


  def _build_assignment(description: str) -> AgentMessage:
      return AgentMessage(
          correlation_id=uuid4(),
          sender=AgentId.TEAM_LEAD,
          recipient=AgentId.BACKEND_DEVELOPER,
          message_type=MessageType.TASK_ASSIGNMENT,
          priority=Priority.P1,
          payload=TaskAssignmentPayload(
              task_id=uuid4(),
              title="too-large probe",
              description=description,
          ),
      )


  def test_tripwire_fires_on_long_description(tmp_path):
      description = "create core/foo.py and tests/unit/test_foo.py\n\n" + ("x" * 1600)
      too_large, diag = _is_task_too_large(description, tmp_path)
      assert too_large is True
      assert "1500" in diag or "chars" in diag.lower()


  def test_tripwire_fires_on_three_unknown_file_paths(tmp_path):
      description = (
          "Implement the data-model layer.\n\n"
          "Write core/foo/alpha.py, core/foo/beta.py, "
          "and tests/unit/test_foo_alpha.py."
      )
      too_large, diag = _is_task_too_large(description, tmp_path)
      assert too_large is True
      assert "file" in diag.lower() or "path" in diag.lower()


  def test_tripwire_does_not_fire_on_small_task(tmp_path):
      (tmp_path / "core").mkdir()
      (tmp_path / "core" / "existing.py").write_text("# stub")
      description = "Edit core/existing.py to add the validate() helper."
      too_large, diag = _is_task_too_large(description, tmp_path)
      assert too_large is False, diag


  @pytest.mark.asyncio
  async def test_tripwire_emits_blocked_with_task_too_large(monkeypatch, tmp_path):
      from unittest.mock import AsyncMock

      monkeypatch.setenv("AI_TEAM_REPO_ROOT", str(tmp_path))
      llm = AsyncMock()
      agent = BackendDeveloperAgent(llm=llm)
      msg = _build_assignment("x" * 1700)

      out = await agent.handle(msg)

      assert llm.invoke.await_count == 0, "LLM must not be invoked on tripwire"
      assert len(out) == 1
      report = out[0]
      assert isinstance(report.payload, TaskReportPayload)
      assert report.payload.status == TaskStatus.BLOCKED
      assert report.payload.blocked_on == "task_too_large"
      assert report.recipient == AgentId.TEAM_LEAD


  @pytest.mark.asyncio
  async def test_tripwire_summary_echoes_auto_route_marker(monkeypatch, tmp_path):
      from unittest.mock import AsyncMock

      monkeypatch.setenv("AI_TEAM_REPO_ROOT", str(tmp_path))
      llm = AsyncMock()
      agent = BackendDeveloperAgent(llm=llm)
      msg = _build_assignment(
          "[auto-routed from team_lead] re-decompose this work.\n\n" + ("x" * 1600)
      )

      out = await agent.handle(msg)

      assert len(out) == 1
      report = out[0]
      assert isinstance(report.payload, TaskReportPayload)
      assert "auto-routed already" in report.payload.summary.lower()
  ```

- [ ] Run them — all 5 should FAIL with
  `ImportError` (no `_is_task_too_large`).

  ```bash
  uv run pytest tests/unit/test_backend_developer_agent.py -k tripwire -v
  ```
  Expected: 5 FAIL (ImportError) or 4 FAIL +
  1 collection error.

#### Step 1.2 — Implement `_is_task_too_large`

- [ ] Edit `agents/backend_developer/agent.py`.
  Add at module level (above
  `BACKEND_REPORT_SCHEMA`):

  ```python
  import os
  import re

  # iter-21: runtime tripwire. The TL prompt edit shipped in iter-20
  # Phase 2 makes TL emit smaller Backend subtasks structurally, but
  # LLM compliance on the "≤200 LOC" soft instruction is imperfect.
  # iter-20 demo: 1 of 2 subtasks still hit 600s. The pre-flight check
  # below catches obviously-too-large work before burning the LLM turn.
  # See docs/iterations/iter_20_demo_report.md §Caveat A.
  _MAX_DESCRIPTION_CHARS = 1500
  _MAX_UNKNOWN_FILE_PATHS = 3
  _FILE_PATH_RE = re.compile(r"[A-Za-z][A-Za-z0-9_/.-]+\.[a-z]+")
  _AUTO_ROUTED_HINT = "[auto-routed"


  def _is_task_too_large(description: str, target_repo_root: Path) -> tuple[bool, str]:
      """Pre-flight heuristic for the Backend tripwire.

      Returns (True, diagnostic) when the description plausibly
      exceeds ~200 LOC scope, (False, "") otherwise.

      Heuristics (OR-combined):
      - Description char count > 1500.
      - ≥ 3 distinct file-path-shaped tokens that don't already exist
        on disk under `target_repo_root`.

      The thresholds are deliberately conservative — false negatives
      (oversized tasks slip through) just mean we fall back to the
      existing 600s timeout, which is the iter-20 baseline. False
      positives (small tasks rejected) trigger the TL auto-hop
      re-decomposition path; the anti-loop guard caps that to one
      hop.
      """
      char_count = len(description)
      if char_count > _MAX_DESCRIPTION_CHARS:
          return True, f"description {char_count} chars > {_MAX_DESCRIPTION_CHARS} threshold"
      tokens = set(_FILE_PATH_RE.findall(description))
      unknown = sorted(t for t in tokens if not (target_repo_root / t).exists())
      if len(unknown) >= _MAX_UNKNOWN_FILE_PATHS:
          sample = ", ".join(unknown[:5])
          return True, (
              f"{len(unknown)} file-path tokens not on disk "
              f"(>= {_MAX_UNKNOWN_FILE_PATHS} threshold): {sample}"
          )
      return False, ""
  ```

  Notes:
  - `target_repo_root` is passed by the caller —
    the test can use `tmp_path` directly; the
    runtime call uses
    `Path(os.environ.get("AI_TEAM_REPO_ROOT", str(_REPO_ROOT)))`.
  - Token uniqueness via `set()` avoids
    multiple references to the same path
    inflating the count.
  - Sorting `unknown` makes the diagnostic
    deterministic for snapshot-style tests.

#### Step 1.3 — Wire the tripwire into `handle()`

- [ ] Modify `BackendDeveloperAgent.handle()`
  to add a pre-flight check:

  ```python
  async def handle(self, msg: AgentMessage) -> list[AgentMessage]:
      if msg.message_type != MessageType.TASK_ASSIGNMENT:
          return []
      if not isinstance(msg.payload, TaskAssignmentPayload):
          return []
      # iter-21: tripwire short-circuit BEFORE LLM invocation.
      target_root = Path(os.environ.get("AI_TEAM_REPO_ROOT", str(_REPO_ROOT)))
      too_large, diag = _is_task_too_large(msg.payload.description, target_root)
      if too_large:
          already_routed = _AUTO_ROUTED_HINT in msg.payload.description.lower()
          marker = "[auto-routed already] " if already_routed else ""
          summary = (
              f"{marker}task too large: {diag}\n\n"
              f"original task description (first 800 chars):\n"
              f"{msg.payload.description[:800]}"
          )[:2_000]
          self._log.info(
              "backend.tripwire_blocked",
              diag=diag,
              char_count=len(msg.payload.description),
              already_routed=already_routed,
              correlation_id=str(msg.correlation_id),
          )
          return [
              self._report_to_tl(
                  msg,
                  status=TaskStatus.BLOCKED,
                  summary=summary,
                  artifacts=[],
                  blocked_on="task_too_large",
              )
          ]
      response = await self._llm.invoke(
          system_prompt=self.system_prompt(),
          user_message=self._user_message_for(msg),
          model=self.model_tier,
          allowed_tools=self.allowed_tools,
          session_id=str(msg.correlation_id),
          timeout_s=self.llm_timeout_s,
          max_turns=self.max_turns,
          json_schema=BACKEND_REPORT_SCHEMA,
          env=dict(self.mcp_env) if self.mcp_env else None,
      )
      return self._stamp_metrics(self.build_outputs(response, msg), response)
  ```

#### Step 1.4 — Extend `_report_to_tl` with `blocked_on`

- [ ] Modify `_report_to_tl` to accept and
  forward `blocked_on`:

  ```python
  def _report_to_tl(
      self,
      incoming: AgentMessage,
      *,
      status: TaskStatus,
      summary: str,
      artifacts: list[str],
      blocked_on: str | None = None,
  ) -> AgentMessage:
      assert isinstance(incoming.payload, TaskAssignmentPayload)
      return AgentMessage(
          correlation_id=incoming.correlation_id,
          sender=AgentId.BACKEND_DEVELOPER,
          recipient=AgentId.TEAM_LEAD,
          message_type=MessageType.TASK_REPORT,
          priority=incoming.priority,
          payload=TaskReportPayload(
              task_id=incoming.payload.task_id,
              status=status,
              progress_pct=100 if status == TaskStatus.DONE else 0,
              summary=summary,
              artifacts=artifacts,
              blocked_on=blocked_on,
          ),
      )
  ```

#### Step 1.5 — Run the tests

- [ ] All 5 tripwire tests + the existing 14
  Backend agent tests must pass.

  ```bash
  uv run pytest tests/unit/test_backend_developer_agent.py -v
  ```
  Expected: 19 PASS (14 existing + 5 new).

#### Step 1.6 — Commit Phase 1

- [ ] ```bash
  git add agents/backend_developer/agent.py \
          tests/unit/test_backend_developer_agent.py
  git commit -m "$(cat <<'EOF'
  feat(backend): runtime tripwire — reject task_too_large pre-LLM

  iter-21 Phase 1. The TL prompt edit shipped in iter-20 makes TL
  decompose Backend work structurally, but the iter-20 demo showed
  LLM compliance on the soft "≤200 LOC" instruction is imperfect —
  one of two Backend subtasks still hit the 600s timeout. The
  pre-flight check here short-circuits oversized work into a BLOCKED
  report (blocked_on='task_too_large') before the LLM is invoked,
  saving ~$0.50 + 10 min per failure. TL Phase 2 handler re-routes.

  Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
  EOF
  )"
  ```

### Phase 2 — TL re-decomposition handler (TDD)

**Goal**: When TL receives a BLOCKED report
with `blocked_on='task_too_large'`, it emits a
self-targeted `TASK_ASSIGNMENT(recipient=TEAM_LEAD)`
carrying the original task description (echoed
in the BLOCKED summary) and a "re-decompose
into smaller subtasks" instruction. The
anti-loop guard refuses a second hop.

**Files**:
- Modify: `agents/team_lead/agent.py`
- Modify: `tests/unit/test_team_lead_agent.py`

#### Step 2.1 — Write the failing tests

- [ ] Add three tests to
  `tests/unit/test_team_lead_agent.py`:

  ```python
  # tests/unit/test_team_lead_agent.py
  # (additions; existing tests untouched)

  import pytest
  from uuid import uuid4

  from agents.team_lead.agent import TeamLeadAgent
  from core.messaging.schemas import (
      AgentId,
      AgentMessage,
      MessageType,
      Priority,
      TaskAssignmentPayload,
      TaskReportPayload,
      TaskStatus,
  )


  def _build_blocked_too_large(summary: str) -> AgentMessage:
      return AgentMessage(
          correlation_id=uuid4(),
          sender=AgentId.BACKEND_DEVELOPER,
          recipient=AgentId.TEAM_LEAD,
          message_type=MessageType.TASK_REPORT,
          priority=Priority.P1,
          payload=TaskReportPayload(
              task_id=uuid4(),
              status=TaskStatus.BLOCKED,
              progress_pct=0,
              summary=summary,
              artifacts=[],
              blocked_on="task_too_large",
          ),
      )


  @pytest.mark.asyncio
  async def test_tl_re_decomposes_on_task_too_large(scripted_llm):
      agent = TeamLeadAgent(llm=scripted_llm)
      msg = _build_blocked_too_large(
          "task too large: description 1800 chars > 1500 threshold\n\n"
          "original task description (first 800 chars):\n"
          "Implement the idea-validator pipeline including the "
          "data-model layer, the service layer, and the API surface."
      )

      out = await agent.handle(msg)

      assert len(out) == 1
      followup = out[0]
      assert followup.message_type == MessageType.TASK_ASSIGNMENT
      assert followup.recipient == AgentId.TEAM_LEAD
      assert isinstance(followup.payload, TaskAssignmentPayload)
      assert "auto-routed" in followup.payload.description.lower()
      assert "re-decompose" in followup.payload.description.lower()
      assert "idea-validator pipeline" in followup.payload.description


  @pytest.mark.asyncio
  async def test_tl_refuses_second_re_decomp_when_already_routed(scripted_llm):
      agent = TeamLeadAgent(llm=scripted_llm)
      msg = _build_blocked_too_large(
          "[auto-routed already] task too large: 1700 chars > 1500 threshold\n\n"
          "original task description (first 800 chars):\n"
          "second re-decomp attempt should refuse."
      )

      out = await agent.handle(msg)

      assert out == [], "anti-loop must refuse second auto-hop"


  @pytest.mark.asyncio
  async def test_tl_passes_through_unknown_blocked_on(scripted_llm):
      """Sanity check: blocked_on values other than task_too_large or
      valid AgentIds still surface to owner (no auto-route)."""
      agent = TeamLeadAgent(llm=scripted_llm)
      msg = AgentMessage(
          correlation_id=uuid4(),
          sender=AgentId.BACKEND_DEVELOPER,
          recipient=AgentId.TEAM_LEAD,
          message_type=MessageType.TASK_REPORT,
          priority=Priority.P1,
          payload=TaskReportPayload(
              task_id=uuid4(),
              status=TaskStatus.BLOCKED,
              progress_pct=0,
              summary="Backend blocked: requires unknown_thing",
              artifacts=[],
              blocked_on="unknown_thing",
          ),
      )

      out = await agent.handle(msg)
      assert out == []
  ```

  `scripted_llm` is the existing fixture in
  `tests/unit/test_team_lead_agent.py` (used by
  other TL tests). If it lives in a
  `conftest.py`, the new tests pick it up
  automatically.

- [ ] Run — all 3 should FAIL.

  ```bash
  uv run pytest tests/unit/test_team_lead_agent.py -k "task_too_large or re_decomp" -v
  ```
  Expected: 2 FAIL (re-decomp not implemented),
  1 PASS (pass-through case already works since
  `_parse_blocked_target` returns None for
  unknown `blocked_on`).

#### Step 2.2 — Implement `_re_decompose_on_too_large`

- [ ] Edit `agents/team_lead/agent.py`. Add a
  module-level constant:

  ```python
  _TASK_TOO_LARGE_BLOCKED_ON = "task_too_large"
  _ALREADY_ROUTED_MARKER = "auto-routed already"
  ```

  Add a helper method on `TeamLeadAgent`:

  ```python
  def _re_decompose_on_too_large(self, msg: AgentMessage) -> list[AgentMessage]:
      """Self-targeted task_assignment that triggers a TL re-decomp.

      Backend's tripwire embeds the original task description (first
      800 chars) in the BLOCKED summary; we forward that into the new
      task_assignment. TL's standard handle() runs the decomposition
      LLM and emits smaller Backend subtasks.

      Anti-loop: refuse if the BLOCKED summary already carries the
      'auto-routed already' marker.
      """
      assert isinstance(msg.payload, TaskReportPayload)
      summary = msg.payload.summary
      if _ALREADY_ROUTED_MARKER in summary.lower():
          self._log.info(
              "tl.task_too_large_anti_loop_refused",
              sender=msg.sender.value,
              correlation_id=str(msg.correlation_id),
          )
          return []
      self._log.info(
          "tl.task_too_large_re_decompose",
          sender=msg.sender.value,
          correlation_id=str(msg.correlation_id),
      )
      return [
          AgentMessage(
              correlation_id=msg.correlation_id,
              sender=AgentId.TEAM_LEAD,
              recipient=AgentId.TEAM_LEAD,
              message_type=MessageType.TASK_ASSIGNMENT,
              priority=msg.priority,
              payload=TaskAssignmentPayload(
                  task_id=uuid4(),
                  title=f"Re-decompose: {summary[:80]}",
                  description=(
                      f"[{_AUTO_ROUTED_MARKER} from {msg.sender.value}] "
                      f"{msg.sender.value} reported BLOCKED(task_too_large). "
                      "Re-decompose the original work into 2-3 smaller "
                      "subtasks of ≤100 LOC each (or fewer if that's "
                      "still too large), and dispatch them to backend_developer "
                      "with explicit depends_on slugs where needed. "
                      "Backend's original BLOCKED report follows:\n\n"
                      f"{summary}"
                  )[:10_000],
              ),
          )
      ]
  ```

  The `[:10_000]` slice respects
  `TaskAssignmentPayload.description`'s
  `max_length=10_000`.

#### Step 2.3 — Wire into `_maybe_route_blocked`

- [ ] Modify `_maybe_route_blocked`:

  ```python
  def _maybe_route_blocked(self, msg: AgentMessage) -> list[AgentMessage]:
      """Route a BLOCKED task_report to the indicated role.

      iter-21: special-case blocked_on='task_too_large' →
      self-targeted re-decomposition via _re_decompose_on_too_large.
      """
      if not isinstance(msg.payload, TaskReportPayload):
          return []
      if msg.payload.status != TaskStatus.BLOCKED:
          return []

      # iter-21: too-large work routes to TL itself (re-decompose).
      if msg.payload.blocked_on == _TASK_TOO_LARGE_BLOCKED_ON:
          return self._re_decompose_on_too_large(msg)

      # Anti-loop: if the BLOCKED report was already an auto-routed
      # follow-up, refuse to re-route a second time. The chain stops
      # and the owner sees it in the digest.
      if _AUTO_ROUTED_MARKER in msg.payload.summary.lower():
          self._log.info(
              "tl.blocked_route_skipped_already_routed",
              sender=msg.sender.value,
              correlation_id=str(msg.correlation_id),
          )
          return []

      target = self._parse_blocked_target(msg.payload)
      if target is None or target == AgentId.TEAM_LEAD:
          return []
      # ... rest unchanged
  ```

#### Step 2.4 — Run the tests

- [ ] All 3 new tests + the existing TL agent
  test suite must pass.

  ```bash
  uv run pytest tests/unit/test_team_lead_agent.py -v
  ```
  Expected: existing TL count + 3 = all PASS.

#### Step 2.5 — Commit Phase 2

- [ ] ```bash
  git add agents/team_lead/agent.py tests/unit/test_team_lead_agent.py
  git commit -m "$(cat <<'EOF'
  feat(team_lead): re-decompose on BLOCKED(task_too_large)

  iter-21 Phase 2. Pairs with the Backend tripwire shipped in Phase 1.
  When Backend rejects a task as too-large, TL emits a self-targeted
  TASK_ASSIGNMENT with the original description forwarded in the body
  and an "≤100 LOC subtasks" instruction. TL's normal handle() runs
  the decomposition LLM and dispatches smaller Backend subtasks.
  Anti-loop: second-hop trips surface to owner via digest.

  Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
  EOF
  )"
  ```

### Phase 3 — Demo auto-approve bash fix done right

**Goal**: Replace the heredoc-vs-pipe
antipattern in the demo's auto-approve block
with the `python3 - "$JSON" <<'PY' ... sys.argv[1]`
form. Leave inline warnings in iter-18/19/20
scripts so a future iter doesn't re-introduce
the bug.

**Files**:
- Create: `scripts/demo_iter_21.sh` (clone of
  `demo_iter_20.sh`).
- Modify: `scripts/demo_iter_18.sh`,
  `scripts/demo_iter_19.sh`,
  `scripts/demo_iter_20.sh` (inline comment
  only; do NOT re-fix them — historical scripts
  stay frozen).
- Modify: `Makefile` (alias `demo-iter-21`,
  repoint `demo`).

#### Step 3.1 — Clone demo script

- [ ] ```bash
  cp scripts/demo_iter_20.sh scripts/demo_iter_21.sh
  chmod +x scripts/demo_iter_21.sh
  ```

#### Step 3.2 — Update iter-21 narrative

- [ ] In `scripts/demo_iter_21.sh`, replace
  "iter-20" references with "iter-21" in:
  - The header banner.
  - The MCP config filename
    (`.iter20-mcp.json` → `.iter21-mcp.json`).
  - The narrative `step` calls.
  - The auto-approve comment ("iter-20 demo
    auto-approve" → "iter-21 demo
    auto-approve").

#### Step 3.3 — Apply the bash fix

- [ ] Replace the auto-approve block in
  `scripts/demo_iter_21.sh` (the heredoc-vs-pipe
  block around line 247-272 of the iter-20
  clone):

  ```bash
  step "6.6/7 — Auto-approve any pending_reviews (close the loop)"
  # iter-21 fix (carry-over from iter-18 → iter-19 → iter-20).
  # Real root cause: `printf '%s' "$JSON" | python3 <<'PY' ... PY`
  # is a heredoc-vs-pipe conflict — bash routes python's stdin to
  # the HEREDOC (source code), NOT to the piped JSON, so
  # json.load(sys.stdin) parses python source and fails on char 0.
  # The fix: `python3 - "$JSON" <<'PY' ... sys.argv[1]`. The `-`
  # arg makes python read source from stdin (the heredoc), and the
  # JSON arrives via sys.argv[1]. No conflict.
  #
  # See docs/iterations/iter_20_demo_report.md §Caveat B and
  # docs/iterations/iter_21.md Phase 3.
  REVIEWS_JSON=$(curl -sf -H "Authorization: Bearer $OWNER_TOKEN" \
      http://127.0.0.1:8000/api/reviews 2>/dev/null || true)
  REVIEWS_JSON="${REVIEWS_JSON:-[]}"
  python3 - "$REVIEWS_JSON" <<'PY' || true
  import json, subprocess, sys
  data = json.loads(sys.argv[1])
  if not data:
      print("(no pending_reviews — chain didn't reach QA)")
  else:
      for r in data:
          rid = r["id"]
          print(f"approving {rid} ({r.get('requesting_agent','?')}: {r.get('summary','')[:80]})")
          subprocess.run(
              ["uv", "run", "ai-team", "approve", rid,
               "--comment", "iter-21 demo auto-approve"],
              check=False,
          )
  PY
  ```

#### Step 3.4 — Add warning comments to prior demos

- [ ] In each of `scripts/demo_iter_18.sh`,
  `scripts/demo_iter_19.sh`,
  `scripts/demo_iter_20.sh`, add a single
  comment line immediately above the
  `REVIEWS_JSON=$(curl ...` line:

  ```bash
  # WARNING (added in iter-21): the printf '%s' "$JSON" | python3 <<'PY'
  # pattern below is a heredoc-vs-pipe conflict. python's stdin gets the
  # heredoc, not the piped JSON. Fixed in scripts/demo_iter_21.sh — do
  # NOT copy this pattern into new demo scripts. See
  # docs/iterations/iter_21.md Phase 3.
  ```

  Do not modify the broken code itself — these
  scripts are historical demo artifacts.

#### Step 3.5 — Makefile alias + repoint demo

- [ ] In `Makefile`, find the
  `demo-iter-20` block and the `demo` target.
  Add:

  ```make
  .PHONY: demo-iter-21
  demo-iter-21:
  	AI_TEAM_DEMO_NON_INTERACTIVE=$${AI_TEAM_DEMO_NON_INTERACTIVE:-} bash scripts/demo_iter_21.sh
  ```

  And repoint `demo` to call `demo-iter-21`.

#### Step 3.6 — Smoke check the bash fix

- [ ] Run the auto-approve block in isolation
  against a stub server (or skip if no
  running API) — at minimum confirm the bash
  syntax parses with `bash -n`:

  ```bash
  bash -n scripts/demo_iter_21.sh
  ```
  Expected: no output (syntax OK).

  Optional manual check (no API running):

  ```bash
  REVIEWS_JSON='[{"id":"abc","requesting_agent":"qa_engineer","summary":"test"}]'
  python3 - "$REVIEWS_JSON" <<'PY'
  import json, sys
  print(json.loads(sys.argv[1]))
  PY
  ```
  Expected output:
  `[{'id': 'abc', 'requesting_agent': 'qa_engineer', 'summary': 'test'}]`.

#### Step 3.7 — Commit Phase 3

- [ ] ```bash
  git add scripts/demo_iter_21.sh \
          scripts/demo_iter_18.sh \
          scripts/demo_iter_19.sh \
          scripts/demo_iter_20.sh \
          Makefile
  git commit -m "$(cat <<'EOF'
  chore(demo): iter-21 demo + heredoc-vs-pipe bash fix done right

  3-iteration carry-over (iter-18 → iter-19 → iter-20). Real root
  cause: `printf '%s' "$JSON" | python3 <<'PY' ... PY` routes
  python's stdin to the HEREDOC source, not the piped JSON.
  iter-21 fix: `python3 - "$JSON" <<'PY' ... sys.argv[1]`. Warning
  comments added to iter-18/19/20 scripts so future iters don't
  re-introduce the antipattern.

  Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
  EOF
  )"
  ```

### Phase 4 — Validation gates

**Goal**: All static gates green before the
real-LLM demo.

- [ ] **Step 4.1** — `ruff check`:

  ```bash
  uv run ruff check
  ```
  Expected: `All checks passed!`

- [ ] **Step 4.2** — `ruff format --check`:

  ```bash
  uv run ruff format --check
  ```
  Expected: no diffs.

- [ ] **Step 4.3** — `mypy --strict`:

  ```bash
  make typecheck
  ```
  Expected: `Success: no issues found in N source files`.

- [ ] **Step 4.4** — bandit:

  ```bash
  make sec
  ```
  Expected: `High: 0`.

- [ ] **Step 4.5** — full unit suite:

  ```bash
  make test-unit
  ```
  Expected: 421 + 5 + 3 = 429 PASS.

- [ ] **Step 4.6** — integration suite:

  ```bash
  make up
  make test-integration
  ```
  Expected: 50 PASS (no integration tests
  added in iter-21).

- [ ] **Step 4.7** — smoke-llm against real
  `claude -p`:

  ```bash
  make smoke-llm
  ```
  Expected: `Overall: PASS`. (Variance may
  flake; retry once if it does.)

- [ ] **Step 4.8** — If any gate fails, STOP
  and surface to owner before proceeding to
  Phase 5. Do NOT chase green by relaxing the
  tripwire heuristic — the heuristic is the
  load-bearing contract.

### Phase 5 — Real-LLM end-to-end demo + report

**Goal**: Re-run the iter-19/20-shape demo
under iter-21's fixes. Expect a QA-emitted
`pending_reviews` row with
`requesting_agent='qa_engineer'` — the
2-iteration-deferred success criterion.

**Files**:
- Create: `docs/iterations/iter_21_demo_report.md`

#### Step 5.1 — Pre-flight

- [ ] Confirm `make up` is running (postgres +
  redis); confirm `.claude/agent-worktrees/` is
  empty (demo's EXIT trap from iter-20 should
  have left it so).

  ```bash
  docker ps --filter "name=ai_team"
  ls -la .claude/agent-worktrees/ 2>/dev/null || echo "(clean)"
  ```

#### Step 5.2 — Run the demo

- [ ] ```bash
  AI_TEAM_DEMO_NON_INTERACTIVE=1 bash scripts/demo_iter_21.sh 2>&1 \
      | tee docs/iterations/iter_21_demo_raw.log
  ```

  Expected wall-clock: 30-45 min. Expected
  cost: ≤ $5 (under the per-demo ceiling).
  Backend may emit BLOCKED(task_too_large) +
  TL re-decomposes → smaller Backend subtasks
  succeed → QA runs.

#### Step 5.3 — Capture audit evidence

- [ ] Query `audit_log` for the demo's
  correlation_id. Verify:

  ```bash
  PGPASSWORD=ai_team psql -h 127.0.0.1 -U ai_team ai_team -c "
    SELECT id, sender, recipient, message_type,
           payload_json -> 'payload' ->> 'status' AS status,
           payload_json -> 'payload' ->> 'blocked_on' AS blocked_on
    FROM audit_log
    WHERE correlation_id = '<CORR>'
    ORDER BY id;
  "
  ```

  Look for:
  - A row `backend_developer → team_lead
    task_report status=blocked
    blocked_on=task_too_large` (tripwire fired).
  - A row `team_lead → team_lead
    task_assignment` (re-decomp request).
  - 2-3 subsequent rows `team_lead →
    backend_developer task_assignment` (TL's
    re-decomposition output).
  - `backend_developer → team_lead task_report
    status=done` for those smaller subtasks.
  - `qa_engineer → team_lead task_report` row.
  - **`pending_reviews` table has a new row
    with `requesting_agent='qa_engineer'`** —
    this is THE success criterion.

  ```bash
  PGPASSWORD=ai_team psql -h 127.0.0.1 -U ai_team ai_team -c "
    SELECT id, requesting_agent, status, created_at
    FROM pending_reviews
    ORDER BY created_at DESC LIMIT 5;
  "
  ```

#### Step 5.4 — Investigate Architect spend

- [ ] Query the Architect's audit row for
  iter-21:

  ```bash
  PGPASSWORD=ai_team psql -h 127.0.0.1 -U ai_team ai_team -c "
    SELECT id,
           payload_json -> 'metadata' -> 'llm' ->> 'duration_ms' AS dur_ms,
           payload_json -> 'metadata' -> 'llm' ->> 'cost_cents'  AS cost,
           payload_json -> 'metadata' -> 'llm' ->> 'tokens_in'   AS tin,
           payload_json -> 'metadata' -> 'llm' ->> 'tokens_out'  AS tout
    FROM audit_log
    WHERE correlation_id = '<CORR>'
      AND sender = 'architect'
    ORDER BY id;
  "
  ```

  Compare to iter-19 ($0.78) and iter-20
  ($2.88). Capture the trajectory + hypothesis
  in the demo report. If Architect spend is
  still climbing, name the carry-over for
  iter-22.

#### Step 5.5 — Write the demo report

- [ ] Mirror the iter_20_demo_report.md
  structure: Verdict in one line; What worked;
  What didn't; Cost/quota; Artifacts; Why this
  demo matters; Action items for iter-22;
  Stats.

  Specifically call out:
  - Did the Backend tripwire fire? Yes/no, on
    which subtask, with what diagnostic.
  - Did TL re-decompose? How many subtasks
    emerged from the re-decomposition?
  - Did the smaller subtasks complete?
  - Did QA emit a pending_reviews row? THIS
    is the headline pass/fail.
  - Architect spend trajectory.

- [ ] Commit:

  ```bash
  git add docs/iterations/iter_21_demo_report.md \
          docs/iterations/iter_21_demo_raw.log
  git commit -m "$(cat <<'EOF'
  docs(iter-21): real-LLM demo report — <verdict>

  <one-line summary>

  Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
  EOF
  )"
  ```

### Phase 6 — Retro + iter-22 handoff + PR merge

#### Step 6.1 — Write retro

- [ ] `docs/iterations/iter_21_retro.md` —
  mirror iter_20_retro.md structure: What
  shipped, What went well, What didn't,
  Surprises, Action items for iter-22, Stats.

#### Step 6.2 — Write handoff

- [ ] `docs/iterations/iter_22_handoff.md` —
  mirror iter_21_handoff.md structure.
  Carry-over list ordered by priority. Include
  ready-to-paste prompt.

#### Step 6.3 — Commit retro + handoff

- [ ] ```bash
  git add docs/iterations/iter_21_retro.md \
          docs/iterations/iter_22_handoff.md
  git commit -m "docs(iter-21): retro + iter-22 handoff"
  ```

#### Step 6.4 — Open PR, run CI, squash-merge

- [ ] Push branch:

  ```bash
  git push -u origin worktree-iter-21
  ```

- [ ] Open PR:

  ```bash
  gh pr create --base main --head worktree-iter-21 \
      --title "iter-21: Backend tripwire + demo bash fix + QA-row demo" \
      --body "$(cat <<'EOF'
  ## Summary

  - Backend runtime tripwire rejects too-large task_assignments before
    burning 600s on the LLM (carry-over #1 from iter-21 handoff).
  - TL re-decomposition handler routes BLOCKED(task_too_large) into a
    self-targeted re-decomp turn, with anti-loop guard.
  - Demo auto-approve bash fix done right — replaces 3-iteration
    heredoc-vs-pipe antipattern with `python3 - "$JSON" <<'PY' ...
    sys.argv[1]`.
  - Real-LLM demo re-run produces <PASS/FAIL on QA pending_review row>.

  ## Test plan

  - [x] `make test-unit` — 429 PASS
  - [x] `make test-integration` — 50 PASS
  - [x] `make smoke-llm` — PASS
  - [x] Real-LLM demo (`scripts/demo_iter_21.sh`) — see
    `docs/iterations/iter_21_demo_report.md`

  🤖 Generated with [Claude Code](https://claude.com/claude-code)
  EOF
  )"
  ```

- [ ] Wait for CI; if green, squash-merge:

  ```bash
  gh pr merge --squash --delete-branch
  ```

- [ ] Confirm `main` HEAD now includes the
  iter-21 squash; mark all iter-21 tasks
  complete.

## Risks + open questions

1. **The file-path heuristic may fire on
   small task descriptions that happen to
   mention several green-field paths.** Char
   count is the primary fence; file-path is
   the OR-fallback. If false-positives prove
   noisy, iter-22 can raise the threshold or
   add an `^[a-zA-Z_]+\.(py|md)$`-style
   filter to skip non-path tokens. iter-21
   ships the simple version.

2. **TL's re-decomp LLM call is an extra Opus
   turn.** Adds ~$0.30-0.50 to demo cost when
   the tripwire fires. Acceptable in exchange
   for not burning $0.50 + 10 min on the
   doomed Backend turn.

3. **The bash fix is testable but the
   "Architect spend audit" is observational —
   we can't fix Architect spend in iter-21
   without a prompt change, and Architect's
   prompt is out of scope.** If the audit
   reveals a clear win (e.g. Architect is
   re-reading 20 ADRs on every turn), iter-22
   can ship a prompt edit.

4. **The success criterion (QA pending_review
   row)** is still empirical — even with the
   tripwire and re-decomp wired, an LLM-side
   QA failure could still cascade-drop the
   row. iter-21's contract: the tripwire +
   re-decomp PATHS exist and are exercised.
   The pending_review row materialising is
   the demo's job, not the unit suite's.

## What iter-21 explicitly does NOT do

- **Does not change Backend's prompt.** The
  prompt is fine; the tripwire is at the
  runtime layer.
- **Does not change TL's decomposition
  prompt.** The iter-20 "≤200 LOC Backend"
  instruction stays. The TL re-decomp turn
  inherits the same prompt; the re-decomp
  request's body asks for "≤100 LOC each".
- **Does not refactor `BaseAgent.handle()`
  template-method** (carry-over #13). Backend
  needs an `handle()` override anyway because
  of the pre-flight check; the refactor stays
  deferred.
- **Does not address HoldQueue persistence,
  pytest-rerunfailures, GitHubTargetRepo, or
  any other carry-over ≥ 5.**

## Stats target

- LOC delta: code +~80 (Backend ~30, TL ~40,
  schema-untouched), tests +~100, demo script
  ~350 (clone), docs +~1500.
- Tests added: 8 (5 Backend tripwire + 3 TL
  re-decomp).
- Cost target: ≤ $5 for the real-LLM demo.
- Wall-clock target: 30-45 min for the demo.
- Success: QA-emitted `pending_reviews` row
  with `requesting_agent='qa_engineer'`
  appears for the first time in 20+
  iterations.
