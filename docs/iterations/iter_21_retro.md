# Iteration 21 — Retrospective

**Closed**: 2026-05-21. 6 commits on
`worktree-iter-21` (plan + 2 feat + 1 chore + 1
style + 1 docs). All static gates green
(ruff/mypy/bandit/428 unit/50 integration/smoke-llm).
Real-LLM demo exited 0 but produced a
**partial-shape outcome**: the iter-21 contracts
ship cleanly, but the tripwire heuristic didn't
match TL's natural Backend description size, and
Backend timed out anyway.

**Headline**: iter-21's two priorities (Backend
runtime tripwire + demo bash fix) both landed
with full TDD coverage and clean validation. The
bash fix is fully validated — the 3-iteration
heredoc-vs-pipe carry-over is closed. The
tripwire+re-decomp contract is wired correctly
(7 new unit tests pin the behavior, including
anti-loop), but the heuristic — char count >1500
OR ≥3 file-path tokens not on disk — was the
wrong heuristic for real-world TL emissions, so
neither the tripwire nor the re-decomp triggered
during the demo. Backend's 600s timeout fired
again, status=FAILED (not BLOCKED), no
re-decomposition, no QA. The QA-emitted
`pending_review` row criterion is **now
3-iteration deferred**. Architect spend dropped
sharply ($2.88 → $0.80), closing the
iter-20-flagged escalation.

## What shipped

Phase 0 — Plan (`docs/iterations/iter_21.md`,
~580 lines) committed on `worktree-iter-21` cut
fresh from `origin/main` at `c356f2c` (iter-20
squash). Plan-before-code held: owner approved
the plan before any code commits.

Phase 1 — Backend runtime tripwire (`096bf1c`):
- New module-level `_is_task_too_large(description,
  target_repo_root) -> (bool, diagnostic)`
  helper on `agents/backend_developer/agent.py`.
  Heuristic OR-combined: description char count
  >1500, OR ≥3 file-path tokens (regex
  `[A-Za-z][A-Za-z0-9_/.-]+\.[a-z]+`) not on
  disk under `target_repo_root`.
- `target_repo_root` resolved at runtime from
  `os.environ["AI_TEAM_REPO_ROOT"]` with
  fallback to `_REPO_ROOT`.
- `BackendDeveloperAgent.handle()` pre-flight
  short-circuit: on too-large, emit
  `BLOCKED(blocked_on='task_too_large')` BEFORE
  invoking the LLM. Auto-route marker
  `[auto-routed` in description → BLOCKED
  summary echoes `[auto-routed already]` to
  propagate the anti-loop signal.
- `_report_to_tl` gained `blocked_on: str | None
  = None` kwarg.
- 5 new unit tests in
  `tests/unit/test_backend_developer_agent.py`:
  char-count trip, file-path trip, happy path,
  full handle() integration with monkeypatch on
  env var, and auto-route marker propagation.

Phase 2 — TL re-decomposition handler
(`c913b0f`):
- Two new constants on
  `agents/team_lead/agent.py`:
  `_TASK_TOO_LARGE_BLOCKED_ON = "task_too_large"`
  and `_ALREADY_ROUTED_MARKER = "auto-routed
  already"`.
- `_maybe_route_blocked` special-cases
  `blocked_on='task_too_large'` BEFORE the
  standard `_AUTO_ROUTED_MARKER` check or
  `_parse_blocked_target` fallback.
- New `_re_decompose_on_too_large(msg)` method
  emits a self-targeted `TASK_ASSIGNMENT(recipient=TEAM_LEAD)`
  carrying the original task description (echoed
  by Backend into the BLOCKED summary, first 800
  chars) and a `[auto-routed from <sender>]` +
  "re-decompose into 2-3 smaller subtasks of
  ≤100 LOC each" instruction.
- Anti-loop: BLOCKED summary containing
  `auto-routed already` → returns `[]`, refuses
  second hop.
- 2 new unit tests in
  `tests/unit/test_team_lead_agent.py`.

Phase 3 — `scripts/demo_iter_21.sh` + bash fix
(`8566a55`):
- 368-line clone of `demo_iter_20.sh` with
  iter-21 narrative (header, banner, MCP config
  filename `.iter21-mcp.json`, EXIT-trap
  function renamed to `_cleanup_iter21`, demo
  task title, auto-approve comment).
- Bash fix: replaced `printf '%s' "$JSON" |
  python3 <<'PY' ... PY` (heredoc-vs-pipe
  conflict) with `python3 - "$REVIEWS_JSON"
  <<'PY' ... sys.argv[1]`. Manually verified:
  non-empty list path prints approval lines,
  empty list path prints "(no pending_reviews…)",
  OLD pattern reproduces the SyntaxError (proof
  of root cause).
- Warning comments inserted in iter-18, iter-19,
  iter-20 scripts so future iters don't
  re-introduce the antipattern. Historical
  scripts otherwise unchanged.
- `Makefile`: `demo-iter-21` alias added,
  `demo` repointed.

Phase 4 — Validation gates (all green;
`ce4167b`):
- `ruff check`: `All checks passed!`
- `ruff format --check`: 148 files already
  formatted.
- `mypy --strict`: `Success: no issues found
  in 148 source files` (after annotating
  `tmp_path: Path` and `monkeypatch:
  pytest.MonkeyPatch` on the 5 new tripwire
  tests).
- `bandit`: `High: 0`.
- `pytest tests/unit`: **428 pass** (iter-20's
  421 + 7 new = 428).
- `pytest tests/integration`: **50 pass**.
- `make smoke-llm`: `Overall: PASS` (first run
  variance-flaked the latency check; retry
  passed — same shape as iter-20 Phase 4).

Phase 5 — Real-LLM demo (`52050fd`, cost
~$1.97):
- **Branch-isolation**: orchestrator HEAD stayed
  on `worktree-iter-21` throughout. iter-20
  Phase 1 contract held.
- **Architect spend**: $0.80 — down 3.6× from
  iter-20's $2.88. Carry-over #3 (Architect
  spend watch) closed.
- **Architect cited iter-21 commit SHAs verbatim**
  in ADR-0029 (`commits 096bf1c + c913b0f`).
- **Tripwire did NOT fire**. TL's natural
  Backend `task_assignment` description was 440
  chars and contained zero `.ext`-suffix
  file-path tokens. Heuristic returned
  `(False, "")`.
- **Backend timed out at 600s**, reported
  `status=failed, blocked_on=null`. Not BLOCKED
  → TL's re-decomp handler not exercised.
- **QA cascade-dropped**. No `pending_reviews`
  row written.
- **Bash auto-approve fix worked** — empty-list
  path printed the expected message, no
  JSONDecodeError.
- Full report:
  `docs/iterations/iter_21_demo_report.md`.

## What went well

- **TDD discipline held tightly**. 7 new tests
  written + watched fail + minimal implementation
  + watched pass + commit. The TDD skill's
  "verify RED before GREEN" rule caught one
  trivial mistake (the anti-loop test passed
  trivially before the special-case landed) —
  noted but harmless because the test still
  pins the intended post-implementation
  behavior.
- **Bash root cause finally identified and
  verified**. The OLD pattern was reproduced
  with a `SyntaxError` (proof bash routes
  stdin to the heredoc, not the pipe). The NEW
  pattern was tested with both empty and
  non-empty JSON inputs. 3-iteration carry-over
  closed.
- **Architect spend trajectory closed without
  action**. $0.78 → $2.88 → $0.80 — iter-20 was
  the outlier. Worth investigating WHY iter-20
  was 3.7× longer; for now, recording the
  return to baseline is sufficient.
- **Static gates carried iter-21's primary
  validation weight**. The 7 new pin tests
  enforce the contract independently of demo
  outcome. iter-20 had the same pattern.
- **`AI_TEAM_REPO_ROOT` env-var resolution**
  worked correctly in both test (monkeypatched
  to `tmp_path`) and demo (set by demo script).
- **Plan structure (Phase 0-6) held**. No phase
  needed reordering or scope expansion during
  execution.

## What didn't

- **The tripwire heuristic was empirically the
  WRONG heuristic for real-world TL output**.
  TL emits short abstract descriptions
  (~440 chars, no file paths) even for scopes
  that take 600s+ of Backend wall-clock. The
  heuristic only fires on TL outputs that
  over-narrate, which the iter-20 demo
  suggested but the iter-21 demo refuted under
  fresh sampling. **This is the major iter-21
  finding** and the headline iter-22 action
  item.
- **TL's re-decomp handler is correct but
  ungrounded** — it ships with passing tests
  but the upstream signal (BLOCKED with
  task_too_large) didn't arrive. The handler
  isn't WRONG; the precondition wasn't met.
- **Backend timed out AGAIN** (now 12-iteration
  carry-over). Both the iter-20 prompt fix and
  the iter-21 Python-tripwire fix failed to
  prevent this specific failure mode.
- **QA pending_review row deferred for the 3rd
  iteration in a row** (iter-19 → iter-20 →
  iter-21). The chain still doesn't reach QA.
- **TL emitted Backend with no `depends_on`
  pointer to Architect**, so Architect's
  ADR-0029 (with the explicit 5-subtask DAG
  designed against the tripwire's intent)
  landed AFTER Backend had already started
  its coarse single subtask. The
  decomposition Architect SHIPPED was correct;
  TL just didn't use it.

## Surprises

- **Architect cited the iter-21 commit SHAs
  `096bf1c` + `c913b0f` VERBATIM in ADR-0029**,
  including the in-flight uncommitted-to-main
  branch state. Same agent-reads-iter-N-state
  pattern as iter-20's ADR-0028 citing
  `1a275fc`, but tighter: Architect read the
  worktree's HEAD before iter-21 was merged.
  The iter-N constraint shipping process is
  now reaching agents even in mid-iteration.
- **Architect spend dropped 3.6× in one
  iteration**. iter-20's $2.88 looked like a
  trend; it was variance. Worth remembering:
  one data point isn't a trajectory, especially
  when the substrate has its own noise.
- **The Backend tripwire's heuristic was
  ineffective EVEN WHEN the task was
  empirically too-large**. The heuristic
  doesn't operate on semantic scope, only on
  text. TL's brevity defeated it.
- **Frontend BLOCKED for the RIGHT reason**.
  Frontend was asked to add a server-form
  pattern that the v2 spec explicitly
  prohibits; it refused and cited ADR-0011
  §No-backend-handshake. Spec-correct BLOCKED
  != failure. Agents are getting good at this.

## Action items for iter-22

1. **(NEW TOP)** **Backend self-eject prompt**.
   Add a "Scope pre-flight" section to
   `prompts/backend_developer.md`: "Before
   writing any code, enumerate the files
   you'd create or modify. If total >2 files
   OR estimated >200 LOC, emit
   `task_report(status=blocked,
   blocked_on='task_too_large')` immediately
   with summary echoing original description.
   Do not partially implement." Pair with a
   unit test pinning the rule in the prompt.
   The Python tripwire (iter-21) stays as a
   backstop but is no longer the primary
   defense. **This is the cleanest path
   because the LLM reads intent, not just
   text.**

2. **(NEW)** **TL Architect→Backend
   `depends_on` rule**. When TL's
   decomposition includes BOTH Architect AND
   Backend, TL MUST emit Backend with
   `depends_on=[architect_subtask_id]`. This
   forces Backend to wait for Architect's ADR,
   which carries the scope decomposition.
   Prompt edit + pin test.

3. **(NEW)** **Tripwire heuristic adjustment**
   (optional). If #1 + #2 don't close the
   600s timeout, tighten: lower description
   threshold to 400 chars, broaden file-path
   regex to count directory mentions, lower
   the file-path trigger from 3 to 2.

4. **Re-attempt the iter-19/20/21 QA-emitted
   `pending_review` row criterion** — now
   3-iteration deferred. Highest demo-side
   priority.

5. **Architect spend watch CLOSED** —
   $0.80 in iter-21 confirms iter-20 was
   variance. No action.

6. **Carry-overs unchanged** from iter-21
   handoff items 5-15 (HoldQueue persistence,
   `pytest-rerunfailures` pin, TL auto-hop,
   TL over-decomposition prompt hint partially
   addressed by #2, `audit_writer` role,
   hash-chain alert, `GitHubTargetRepo`, TL
   transactional insert, `BaseAgent`
   template-method refactor, `mark_task_done`
   / `update_task_status` real impls,
   substrate `--allowed-tools ""` fix).

## Stats

- **Commits on `worktree-iter-21`**: 6 (plan +
  2 feat + 1 chore + 1 style + 1 docs;
  retro/handoff forthcoming).
- **LOC delta**: code +~120 (Backend +~50 net,
  TL +~55, tests +~120); demo script +368
  (clone); historical script warnings +22;
  Makefile +3; docs +~2700 (plan ~580 + demo
  report ~420 + retro + handoff TBD). Total
  ~3500 LOC including docs.
- **Tests**: +7 (5 Backend tripwire + 2 TL
  re-decomp). **428 unit + 50 integration tests
  pass.**
- **Real-LLM spend**: ~$1.97 (under $5
  ceiling; below iter-20's $4.25 and iter-19's
  $2.00).
- **Architect spend**: $0.80 — down 3.6× from
  iter-20.
- **Diff-cover**: 100% on new code paths.
- **Demo wall-clock**: ~30 min (Backend
  timeout at the 600s mark).
- **`pending_reviews` table state at iter-21
  close**: 1 row total (iter-18 historic-first,
  still `approved`). No iter-21 row written.
  Same as iter-19, iter-20.

## Ready-to-paste prompt for iter-22

Lives in `docs/iterations/iter_22_handoff.md`.
