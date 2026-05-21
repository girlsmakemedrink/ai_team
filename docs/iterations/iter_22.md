# Iteration 22 — Plan

- **Status**: Draft (awaiting owner approval)
- **Plan author**: Claude (Opus 4.7)
- **Date drafted**: 2026-05-21
- **Base commit**: iter-21 squash on `main` —
  `d95c69e` (`iter-21: Backend tripwire + TL
  re-decomp + heredoc-vs-pipe bash fix (#28)`).
- **Branch**: `worktree-iter-22` (already cut
  from `origin/main`).
- **Anchors (do not contradict)**: ADR-0001
  (orchestrator), ADR-0004 (per-agent tool
  allowlist), ADR-0006 (model tier per agent),
  ADR-0008 (LLMClient adapter / subscription),
  ADR-0009 (target-repo), iter-21 retro + demo
  report + handoff.
- **Carry-overs addressed**: items 1–4 of
  `iter_22_handoff.md` — Backend self-eject
  prompt edit, TL Architect→Backend hard
  `depends_on` rule, optional tripwire
  tightening (deferred unless 1+2 don't close
  the timeout), and re-attempt the 3-iteration
  deferred QA `pending_review` row criterion.
- **Deferred unchanged**: carry-overs 5–15 from
  `iter_22_handoff.md` (HoldQueue persistence,
  `pytest-rerunfailures` pin, TL auto-hop
  investigation, TL over-decomposition prompt
  hint partially addressed by Phase 2,
  `audit_writer` role, hash-chain alert,
  `GitHubTargetRepo`, TL transactional insert,
  `BaseAgent` template-method refactor,
  `mark_task_done`/`update_task_status` real
  impls, substrate `--allowed-tools ""` fix).

## Goal in one sentence

**Move scope judgment from a Python regex
(iter-21 tripwire, ineffective on TL's natural
~440-char Backend descriptions) to the LLM —
Backend's prompt instructs the model to
self-eject as `BLOCKED(task_too_large)` on
turn 1 when it estimates >2 files or >200 LOC
of work — paired with a TL prompt rule that
forces Backend to `depends_on` Architect when
both roles are in the same decomposition, so
Architect's ADR lands BEFORE Backend dispatches,
finally allowing the chain to produce the
QA-emitted `pending_review` row that has been
deferred since iter-19.**

## Investigation evidence (already gathered)

1. **iter-21 demo definitively showed the Python
   heuristic is the wrong layer.** Audit row 318
   (`team_lead → backend_developer
   task_assignment`) had a 440-char description
   with zero `.ext`-suffix tokens. The tripwire
   returned `(False, "")` and Backend's LLM call
   ran for the full 600s before timing out.
   The heuristic's text-only view cannot see the
   semantic scope ("implement CLI entry point +
   scoring/validation core + unit tests") that
   the LLM can read from intent.

2. **Backend's `BACKEND_REPORT_SCHEMA` currently
   has no way for the LLM to emit BLOCKED**
   (`agents/backend_developer/agent.py:40-54`).
   Schema fields: `branch`, `summary`,
   `files_written`, `tests_passed`, `pr_url`.
   `build_outputs` maps `tests_passed=true` →
   DONE, anything else → FAILED. There is no
   `status` field. iter-22 Phase 1 must extend
   the schema with optional `status` +
   `blocked_on` fields and update
   `build_outputs` to honor them when present
   (with the legacy `tests_passed`-only path
   still working for the happy case).

3. **The TL prompt ALREADY says "Backend
   depends_on Architect because Backend reads
   the ADR"** as an EXAMPLE in
   `prompts/team_lead.md:42`. But this is
   framed as advisory under the broader "only
   declare depends_on when truly needed" rule
   at lines 40-45. iter-21's TL didn't apply
   it — audit row 318 emitted Backend with
   `depends_on=[]` despite Architect being in
   the same decomposition. iter-22 Phase 2 must
   promote this from advisory example to
   MANDATORY rule when both roles co-occur.

4. **The iter-20 "Exception for Backend work"
   section at `prompts/team_lead.md:71-83`**
   already teaches the ≤200 LOC subtask
   pattern. iter-22 Phase 2's
   Architect→Backend rule complements it; both
   stay in the prompt.

5. **The existing prompt-pin test pattern**
   (`tests/unit/test_team_lead_agent.py:test_tl_prompt_teaches_backend_decomposition`)
   uses substring assertion on the prompt
   file. iter-22 Phases 1 and 2 each get a
   parallel pin test.

6. **The iter-21 Python tripwire stays as
   defense-in-depth** — it costs ~1ms when
   it doesn't fire and short-circuits an
   obvious 1500+-char description without an
   LLM turn. The prompt edit becomes the
   primary defense; the Python check is the
   backstop for the case where the LLM
   ignores the prompt instruction (which the
   iter-21 demo suggests is the dominant
   failure mode anyway, since TL didn't
   follow iter-20's "≤200 LOC" instruction
   either).

7. **Architect's iter-21 ADR-0029 explicitly
   defined a 5-subtask DAG** (be_core-anchor,
   be_core-data, be_core-clients,
   be_core-engine, be_cli) WITH per-subtask
   LOC budgets — exactly the shape iter-22's
   Architect→Backend rule will let TL
   consume. Architect already produces the
   right output; the rule unblocks TL from
   using it.

8. **Bandit posture**: Phase 1 changes
   the report-schema and `build_outputs`
   logic (pure Python). Phase 2 is a prompt
   edit (pure markdown). No new subprocess
   calls, no new shell-out. Same bandit
   surface area.

## Phases — bite-sized TDD steps with exact paths

### Phase 0 — Pre-flight worktree + plan commit

**Goal**: Land this plan; await owner approval
before any code change.

**Files**:
- Create: `docs/iterations/iter_22.md` (this
  file).

- [ ] **Step 0.1**: Confirm `worktree-iter-22`
  is cut from `origin/main` at `d95c69e`. Done
  pre-plan (`git rev-parse --abbrev-ref HEAD`
  → `worktree-iter-22`).

- [ ] **Step 0.2**: Commit this plan.

  ```bash
  git add docs/iterations/iter_22.md
  git commit -m "$(cat <<'EOF'
  docs(iter-22): plan — Backend self-eject prompt + TL Architect→Backend depends_on

  Phase 1: extend BACKEND_REPORT_SCHEMA with optional
  status/blocked_on fields; update build_outputs to emit
  BLOCKED when LLM self-ejects on scope pre-flight.
  Phase 2: TL prompt makes Backend depends_on Architect
  MANDATORY when both roles co-occur in a decomposition.
  Phase 3: scripts/demo_iter_22.sh.
  Phase 4: gates. Phase 5: real-LLM demo, expect QA
  pending_review row (3-iteration deferred). Phase 6:
  retro + handoff + PR.

  Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
  EOF
  )"
  ```

- [ ] **Step 0.3**: STOP. Do not proceed to
  Phase 1 until owner approves.

### Phase 1 — Backend self-eject prompt + schema extension (TDD)

**Goal**: The LLM can return
`status='blocked'` with `blocked_on='task_too_large'`
in its structured output. Backend's prompt
instructs it to do so when scope pre-flight
identifies >2 files OR >200 LOC of work. The
existing Python tripwire (iter-21) stays as
defense-in-depth.

**Files**:
- Modify: `agents/backend_developer/agent.py`
- Modify: `prompts/backend_developer.md`
- Modify: `tests/unit/test_backend_developer_agent.py`

#### Step 1.1 — Write the failing tests

- [ ] Add four tests:

  ```python
  # In tests/unit/test_backend_developer_agent.py

  def _backend_blocked_response(
      *,
      blocked_on: str = "task_too_large",
      summary: str = "Scope pre-flight: 3 files / 250 LOC estimated; emitting BLOCKED.",
  ) -> LLMResponse:
      structured = {
          "branch": "",
          "summary": summary,
          "files_written": [],
          "tests_passed": False,
          "pr_url": "",
          "status": "blocked",
          "blocked_on": blocked_on,
      }
      return LLMResponse(
          text=json.dumps(structured),
          structured=structured,
          tools_used=[],
          session_id="be-blocked-sess",
          tokens=TokensUsage(input=50, output=80, model="claude-sonnet-4-6"),
          cost_estimate_cents=3,
          duration_ms=4_000,
          validated_against_schema=True,
          raw={},
      )


  @pytest.mark.asyncio
  async def test_handle_emits_blocked_when_llm_self_ejects() -> None:
      agent = BackendDeveloperAgent(llm=_StubLLM(_backend_blocked_response()))
      outputs = await agent.handle(_task_assignment())

      assert len(outputs) == 1
      report = outputs[0]
      assert isinstance(report.payload, TaskReportPayload)
      assert report.payload.status == TaskStatus.BLOCKED
      assert report.payload.blocked_on == "task_too_large"
      assert "scope" in report.payload.summary.lower()


  @pytest.mark.asyncio
  async def test_handle_emits_blocked_passes_blocked_on_through() -> None:
      agent = BackendDeveloperAgent(
          llm=_StubLLM(_backend_blocked_response(blocked_on="custom_reason"))
      )
      outputs = await agent.handle(_task_assignment())

      report = outputs[0]
      assert isinstance(report.payload, TaskReportPayload)
      assert report.payload.status == TaskStatus.BLOCKED
      assert report.payload.blocked_on == "custom_reason"


  @pytest.mark.asyncio
  async def test_handle_legacy_tests_passed_path_still_works() -> None:
      """Backward compat: LLM that returns the old schema (no `status`
      field) is mapped to DONE/FAILED via `tests_passed` as before."""
      agent = BackendDeveloperAgent(llm=_StubLLM(_backend_response()))
      outputs = await agent.handle(_task_assignment())

      report = outputs[0]
      assert isinstance(report.payload, TaskReportPayload)
      assert report.payload.status == TaskStatus.DONE


  def test_backend_prompt_teaches_scope_preflight() -> None:
      from pathlib import Path

      prompt_path = Path("prompts/backend_developer.md")
      text = prompt_path.read_text()
      assert "Scope pre-flight" in text
      assert "task_too_large" in text
      assert "200 LOC" in text or "≤200 LOC" in text or "<=200 LOC" in text
      assert ">2 files" in text or "> 2 files" in text or "more than 2 files" in text.lower()
  ```

- [ ] Run — all 4 should FAIL.

  ```bash
  uv run pytest tests/unit/test_backend_developer_agent.py -k "self_eject or blocked_passes or legacy_tests_passed or scope_preflight" -v
  ```

  Expected: 3 FAIL on schema (LLM emits unknown
  fields → `build_outputs` ignores them), 1
  FAIL on prompt assertion.

#### Step 1.2 — Extend `BACKEND_REPORT_SCHEMA`

- [ ] Edit `agents/backend_developer/agent.py`.
  Add optional `status` + `blocked_on` fields:

  ```python
  BACKEND_REPORT_SCHEMA: dict[str, object] = {
      "type": "object",
      "required": ["branch", "summary", "files_written", "tests_passed", "pr_url"],
      "additionalProperties": False,
      "properties": {
          "branch": {
              "type": "string",
              "pattern": r"^(agent/backend_developer/[a-zA-Z0-9._\-/]+)?$",
          },
          "summary": {"type": "string", "minLength": 1, "maxLength": 2_000},
          "files_written": {"type": "array", "items": {"type": "string"}},
          "tests_passed": {"type": "boolean"},
          "pr_url": {"type": "string"},
          # iter-22: optional self-eject path. When status='blocked',
          # build_outputs emits a BLOCKED task_report with blocked_on
          # forwarded; the other fields can be empty/defaults.
          "status": {"type": "string", "enum": ["done", "failed", "blocked"]},
          "blocked_on": {"type": ["string", "null"]},
      },
  }
  ```

  Note: `branch` regex relaxed to allow empty
  string (when the LLM self-ejects without
  creating a branch).

#### Step 1.3 — Update `build_outputs` to honor `status`

- [ ] Modify
  `BackendDeveloperAgent.build_outputs`:

  ```python
  def build_outputs(self, response: LLMResponse, incoming: AgentMessage) -> list[AgentMessage]:
      if not isinstance(incoming.payload, TaskAssignmentPayload):
          return []

      report = response.structured
      if not report:
          return [
              self._report_to_tl(
                  incoming,
                  status=TaskStatus.FAILED,
                  summary="Backend Developer: LLM did not return a parseable task_report",
                  artifacts=[],
              )
          ]

      # iter-22: honor explicit `status` if the LLM emitted one (self-eject path).
      explicit_status = str(report.get("status", "") or "").lower()
      if explicit_status == "blocked":
          blocked_on = report.get("blocked_on") or "task_too_large"
          summary = str(report.get("summary", "")).strip() or "Backend self-eject: scope too large"
          return [
              self._report_to_tl(
                  incoming,
                  status=TaskStatus.BLOCKED,
                  summary=summary[:2_000],
                  artifacts=[],
                  blocked_on=str(blocked_on),
              )
          ]

      # Legacy path: tests_passed maps to DONE/FAILED.
      if "tests_passed" not in report:
          return [
              self._report_to_tl(
                  incoming,
                  status=TaskStatus.FAILED,
                  summary="Backend Developer: LLM did not return a parseable task_report",
                  artifacts=[],
              )
          ]
      # ... rest unchanged (tests_passed -> DONE/FAILED)
  ```

#### Step 1.4 — Edit `prompts/backend_developer.md`

- [ ] Add a new "## Scope pre-flight (turn 1)"
  section near the top, BEFORE the workflow
  steps:

  ```markdown
  ## Scope pre-flight (turn 1)

  Before writing any code, enumerate the files you would
  create or modify to complete the task. If the total
  exceeds either of these thresholds, **self-eject as
  blocked** on turn 1 — do not write any code, do not
  create a branch:

  - More than 2 files to create/modify, OR
  - More than 200 LOC of new/modified code (excluding tests)

  When self-ejecting, respond with exactly this JSON
  shape (no other fields populated):

  ```json
  {
    "branch":        "",
    "summary":       "Scope pre-flight: <N files> / <K LOC> estimated. Echoing original task description: <first 500 chars>",
    "files_written": [],
    "tests_passed":  false,
    "pr_url":        "",
    "status":        "blocked",
    "blocked_on":    "task_too_large"
  }
  ```

  The Team Lead receives the BLOCKED report and emits a
  smaller re-decomposition. **Do not partial-implement.**
  A 50 % implementation that runs out of turn time is
  worse than a clean BLOCKED on turn 1 — the team can
  recover the latter; the former leaves the chain in an
  ambiguous half-done state.
  ```

- [ ] Update the "## Discipline" section's
  existing "Keep diff small" line (currently
  references "~300 LOC") to align:

  ```markdown
  - **Self-eject on scope.** See "Scope pre-flight" above:
    if the task plausibly exceeds 2 files OR 200 LOC,
    return BLOCKED on turn 1. The Team Lead splits and
    re-dispatches.
  ```

  Remove the conflicting "~300 LOC" line.

#### Step 1.5 — Update the workflow output spec

- [ ] In `prompts/backend_developer.md` "## What
  you produce", expand the JSON example so the
  LLM sees BOTH the DONE shape AND the BLOCKED
  shape:

  ```markdown
  ## What you produce

  After all of the above, respond with exactly one of
  these JSON objects.

  **On success** (tests pass, PR opened):
  ```json
  {
    "branch":         "agent/backend_developer/<slug>",
    "summary":        "1–2 sentence description of what you built",
    "files_written":  ["repo/relative/path1.py", "..."],
    "tests_passed":   true,
    "pr_url":         "https://github.com/.../pull/<n>"
  }
  ```

  **On scope too large (self-eject)**:
  ```json
  {
    "branch":        "",
    "summary":       "Scope pre-flight: <N files> / <K LOC> estimated. ...",
    "files_written": [],
    "tests_passed":  false,
    "pr_url":        "",
    "status":        "blocked",
    "blocked_on":    "task_too_large"
  }
  ```
  ```

#### Step 1.6 — Run the tests

- [ ] All 4 new tests + the existing 13
  Backend agent tests must pass.

  ```bash
  uv run pytest tests/unit/test_backend_developer_agent.py -v
  ```

  Expected: 17 PASS.

#### Step 1.7 — Commit Phase 1

- [ ] ```bash
  git add agents/backend_developer/agent.py \
          prompts/backend_developer.md \
          tests/unit/test_backend_developer_agent.py
  git commit -m "$(cat <<'EOF'
  feat(backend): LLM self-eject path on scope pre-flight

  iter-22 Phase 1. iter-21's Python tripwire (regex on description
  text) didn't fire on TL's natural ~440-char Backend descriptions.
  Move scope judgment to the LLM: prompt instructs Backend to
  self-eject as BLOCKED(task_too_large) on turn 1 when >2 files OR
  >200 LOC of work is needed. BACKEND_REPORT_SCHEMA grows optional
  `status`/`blocked_on` fields; build_outputs honors them when
  present, falls back to the legacy `tests_passed` mapping for
  back-compat. iter-21's Python tripwire stays as defense-in-depth.

  4 new tests: self-eject path emits BLOCKED, blocked_on
  passthrough, legacy tests_passed path unchanged, prompt teaches
  Scope pre-flight (substring pin).

  Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
  EOF
  )"
  ```

### Phase 2 — TL Architect→Backend mandatory `depends_on` (TDD)

**Goal**: When TL's decomposition includes BOTH
Architect AND Backend, every Backend subtask
must carry `depends_on=[architect_subtask_id]`.
This forces the orchestrator's HoldQueue to
keep Backend off the bus until Architect's
TASK_REPORT(done) lands — so Architect's ADR
exists before Backend's LLM turn starts.

**Files**:
- Modify: `prompts/team_lead.md`
- Modify: `tests/unit/test_team_lead_agent.py`

#### Step 2.1 — Write the failing pin test

- [ ] Add to
  `tests/unit/test_team_lead_agent.py`:

  ```python
  def test_tl_prompt_teaches_mandatory_architect_backend_depends_on() -> None:
      """iter-22 Phase 2: when both architect and backend_developer
      are in the same decomposition, Backend MUST depends_on Architect."""
      from pathlib import Path

      text = Path("prompts/team_lead.md").read_text()
      assert "Architect" in text and "Backend" in text
      # Pin substrings from the new rule:
      assert "MUST" in text or "mandatory" in text.lower()
      assert "depends_on" in text
      # The rule is conditional ("when both roles co-occur"):
      assert "co-occur" in text.lower() or "both" in text.lower()
  ```

- [ ] Run — should FAIL (no such language in
  current prompt).

  ```bash
  uv run pytest tests/unit/test_team_lead_agent.py -k "mandatory_architect_backend" -v
  ```

#### Step 2.2 — Edit `prompts/team_lead.md`

- [ ] In the existing "## Decomposition style"
  section, AFTER the "Exception for Backend
  work" subsection (around line 83), add:

  ```markdown
  - **Mandatory rule: Architect→Backend depends_on
    when both roles co-occur.** If your decomposition
    includes BOTH `architect` AND `backend_developer`
    subtasks, every `backend_developer` subtask MUST
    list at least one `architect` subtask in its
    `depends_on`. This is non-negotiable. Backend
    reads the ADR; without this, Backend dispatches
    in parallel with Architect, runs without the ADR,
    and either fabricates a structure (wrong) or
    times out exploring (also wrong). iter-21's demo
    audit row 318 showed exactly this failure:
    Backend dispatched in the same broadcast turn as
    Architect and timed out at 600s; Architect's
    ADR-0029 (with the explicit decomposition DAG
    Backend needed) landed too late.

    Example:
    ```json
    {"subtasks": [
      {"slug": "arch", "recipient": "architect", "depends_on": []},
      {"slug": "be1",  "recipient": "backend_developer", "depends_on": ["arch"]},
      {"slug": "be2",  "recipient": "backend_developer", "depends_on": ["arch", "be1"]}
    ]}
    ```

    If your decomposition has Backend but no Architect,
    this rule does not apply (Backend works from the
    spec directly).
  ```

#### Step 2.3 — Run the pin test

- [ ] Test should now PASS.

  ```bash
  uv run pytest tests/unit/test_team_lead_agent.py -k "mandatory_architect_backend" -v
  ```

#### Step 2.4 — Commit Phase 2

- [ ] ```bash
  git add prompts/team_lead.md tests/unit/test_team_lead_agent.py
  git commit -m "$(cat <<'EOF'
  feat(team_lead): mandatory Architect→Backend depends_on rule

  iter-22 Phase 2. iter-21 demo audit row 318 showed TL emits Backend
  in the same broadcast turn as Architect (depends_on=[]) — Backend's
  LLM call ran without ADR context and timed out at 600s; Architect's
  ADR-0029 landed too late to help. Promote the existing advisory
  example ("Backend depends_on Architect because Backend reads the
  ADR", lines 42-43) to a MANDATORY rule when both roles co-occur.

  Pairs with Phase 1 Backend self-eject path: with both rules
  active, Backend (a) waits for Architect's ADR before its turn
  starts, and (b) self-ejects if the resulting scope is still too
  large after architectural decomposition.

  Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
  EOF
  )"
  ```

### Phase 3 — `scripts/demo_iter_22.sh`

**Goal**: clone iter-21 demo with iter-22
narrative. No bash-pattern changes — iter-21's
fix is in place.

**Files**:
- Create: `scripts/demo_iter_22.sh` (clone of
  `demo_iter_21.sh`).
- Modify: `Makefile` (alias `demo-iter-22`,
  repoint `demo`).

#### Step 3.1 — Clone

- [ ] ```bash
  cp scripts/demo_iter_21.sh scripts/demo_iter_22.sh
  chmod +x scripts/demo_iter_22.sh
  ```

#### Step 3.2 — Update narrative

- [ ] In `scripts/demo_iter_22.sh`, replace
  iter-21 references with iter-22:
  - Header banner / comment.
  - MCP config filename
    (`.iter21-mcp.json` → `.iter22-mcp.json`).
  - `_cleanup_iter21` → `_cleanup_iter22`.
  - Step narrative strings.
  - Demo task title `"iter-21 demo: ..."` →
    `"iter-22 demo: ..."`.
  - Auto-approve comment.

  The bash auto-approve block (`python3 - "$JSON"
  <<'PY' ... sys.argv[1]`) stays unchanged.

#### Step 3.3 — Makefile

- [ ] ```make
  demo: demo-iter-22 ## Alias for the current iteration's demo

  demo-iter-22: ## Run iter-22 e2e (Backend self-eject + Architect→Backend depends_on)
  	bash scripts/demo_iter_22.sh

  demo-iter-21: ## Run iter-21 e2e (Backend runtime tripwire + TL re-decomp + auto-approve bash fix)
  	bash scripts/demo_iter_21.sh
  ```

  Also add `demo-iter-22` to the `.PHONY` list
  on line 6.

#### Step 3.4 — Syntax check

- [ ] ```bash
  bash -n scripts/demo_iter_22.sh
  ```

#### Step 3.5 — Commit

- [ ] ```bash
  git add scripts/demo_iter_22.sh Makefile
  git commit -m "chore(demo): iter-22 demo script + Makefile alias"
  ```

### Phase 4 — Validation gates

**Goal**: all static gates green before the
real-LLM demo.

- [ ] **Step 4.1** — `uv run ruff check .`
  (NOTE: the dot is required — iter-21 CI
  caught a TC003 that local `ruff check`
  without `.` missed).
- [ ] **Step 4.2** — `uv run ruff format --check`.
- [ ] **Step 4.3** — `make typecheck`.
- [ ] **Step 4.4** — `make sec` (High = 0).
- [ ] **Step 4.5** — `make test-unit` —
  expected 428 + 5 (4 Backend self-eject + 1
  TL pin) = 433 PASS.
- [ ] **Step 4.6** — `make test-integration`
  — 50 PASS.
- [ ] **Step 4.7** — `make smoke-llm` — PASS
  (retry once on latency variance per iter-20
  precedent).
- [ ] **Step 4.8** — If any gate fails, STOP
  and surface before Phase 5.

### Phase 5 — Real-LLM end-to-end demo + report

**Goal**: produce the QA-emitted
`pending_reviews` row criterion that has been
deferred since iter-19.

**Files**:
- Create: `docs/iterations/iter_22_demo_report.md`

#### Step 5.1 — Pre-flight

- [ ] `make up` running, `.claude/agent-worktrees/`
  clean. Demo script's EXIT trap from iter-21
  should have left it so.

#### Step 5.2 — Run

- [ ] ```bash
  AI_TEAM_DEMO_NON_INTERACTIVE=1 bash scripts/demo_iter_22.sh 2>&1 \
      | tee docs/iterations/iter_22_demo_raw.log
  ```

#### Step 5.3 — Verify the success criterion

- [ ] Query `pending_reviews` directly:

  ```bash
  PGPASSWORD=changeme-local-only psql -h 127.0.0.1 -U ai_team ai_team -c "
    SELECT id, requesting_agent, status, created_at
    FROM pending_reviews
    ORDER BY created_at DESC LIMIT 5;
  "
  ```

  Expected: at least one row with
  `requesting_agent='qa_engineer'` from this
  demo's correlation window. **If yes, this is
  the iter-22 headline win** — the
  4-iteration-deferred criterion closes.

#### Step 5.4 — Audit log evidence

- [ ] Query the chain shape:

  ```bash
  PGPASSWORD=changeme-local-only psql -h 127.0.0.1 -U ai_team ai_team -c "
    SELECT id, sender, recipient, message_type,
           payload_json -> 'payload' ->> 'status' AS status,
           payload_json -> 'payload' ->> 'blocked_on' AS blocked_on,
           payload_json -> 'payload' -> 'depends_on' AS depends_on
    FROM audit_log
    WHERE correlation_id = '<CORR>'
    ORDER BY id;
  "
  ```

  Look for:
  - Backend `task_assignment` rows with
    non-empty `depends_on` referencing
    Architect's subtask slug.
  - If Backend self-ejected on scope: one or
    more rows with `status=blocked,
    blocked_on='task_too_large'` →
    auto-recovery via TL re-decomp (iter-21
    Phase 2 path).
  - `qa_engineer → team_lead task_report
    status=done`.
  - `pending_reviews` row inserted.

#### Step 5.5 — Write the report

- [ ] Mirror `iter_21_demo_report.md` structure:
  Verdict, What worked, What didn't, Cost,
  Artifacts, Why this matters, Action items
  for iter-23, Stats.

#### Step 5.6 — Commit

- [ ] ```bash
  git add docs/iterations/iter_22_demo_report.md
  git commit -m "docs(iter-22): real-LLM demo report — <verdict>"
  ```

### Phase 6 — Retro + iter-23 handoff + PR merge

#### Step 6.1 — Retro

- [ ] `docs/iterations/iter_22_retro.md`.

#### Step 6.2 — Handoff

- [ ] `docs/iterations/iter_23_handoff.md`
  with ready-to-paste prompt and carry-over
  priority order.

#### Step 6.3 — Commit + push + PR

- [ ] ```bash
  git add docs/iterations/iter_22_retro.md \
          docs/iterations/iter_23_handoff.md
  git commit -m "docs(iter-22): retro + iter-23 handoff"
  git push -u origin worktree-iter-22
  gh pr create --base main --head worktree-iter-22 \
      --title "iter-22: Backend self-eject + Architect→Backend depends_on" \
      --body "<PR body per Phase 6 template>"
  ```

- [ ] Wait for CI; squash-merge via
  `gh api -X PUT repos/.../pulls/<N>/merge -f
  merge_method=squash` (local-checkout
  workaround per iter-21 Phase 6).

## Risks + open questions

1. **The LLM may ignore the scope pre-flight
   instruction**. Soft constraints in prompts
   are imperfectly followed (iter-20's "≤200
   LOC" exception was structurally honored but
   not in every case). Mitigation: iter-21's
   Python tripwire stays. If the LLM ignores
   the prompt AND TL emits a >1500-char
   description, the Python check fires. If
   neither catches it, the 600s timeout fires
   (iter-21 baseline).

2. **Backend self-eject may over-fire**.
   The LLM may interpret "200 LOC" too
   conservatively and reject reasonably-sized
   tasks. Mitigation: the TL re-decomp
   handler (iter-21 Phase 2) recovers
   automatically. If over-firing becomes
   excessive in the demo, the prompt can be
   tuned in iter-23.

3. **The hard depends_on rule may slow the
   chain**. Architect ~150-470s + Backend
   ~600s now serialized instead of parallel.
   For the v2 demo's specific shape this is
   fine (Backend was always blocking the
   chain anyway). For future workflows where
   Architect's input doesn't materially help
   Backend, the rule may add latency without
   benefit.

4. **The schema extension may break clients
   that expected the old shape**. iter-22
   keeps the legacy `tests_passed` path
   working, but agents/integrations relying
   on `additionalProperties: false` strict
   shape (none in current codebase) would
   break. The Python schema now allows
   `status` and `blocked_on` explicitly.

## What iter-22 explicitly does NOT do

- **Does not remove the iter-21 Python
  tripwire.** It stays as defense-in-depth.
- **Does not change TL's iter-20 "≤200 LOC
  Backend decomposition" exception.** That
  stays; iter-22 adds the depends_on rule
  on top.
- **Does not refactor `BaseAgent.handle()`
  template-method.** Carry-over #13 still
  deferred.
- **Does not add a Backend turn-time
  mid-flight monitor.** If the LLM self-eject
  + depends_on + Python tripwire are
  insufficient, iter-23 candidates include
  reducing Backend `llm_timeout_s` to 300s
  to force smaller turns.
- **Does not address HoldQueue persistence,
  pytest-rerunfailures, GitHubTargetRepo, or
  any other carry-over ≥ 5.**

## Stats target

- LOC delta: code +~30 (Backend agent +~20,
  schema +~5, prompt +~50, TL prompt +~20),
  tests +~70, demo script +368 (clone), docs
  +~1500.
- Tests added: 5 (4 Backend self-eject + 1 TL
  pin).
- Cost target: ≤ $5 for the real-LLM demo.
- Wall-clock target: 30-45 min for the demo.
- **Success criterion**: QA-emitted
  `pending_reviews` row with
  `requesting_agent='qa_engineer'` appears
  for the first time in 22+ iterations.
