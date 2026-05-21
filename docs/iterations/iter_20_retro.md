# Iteration 20 — Retrospective

**Closed**: 2026-05-21. 8 commits on
`worktree-iter-20` (plan + 2 feat + 1 chore +
1 style + demo report + retro/handoff
forthcoming). All static gates green; real-LLM
demo run #1 produced a partial-success chain
(5/6 agents done, Backend hit 600s timeout on
1 of 2 subtasks, no QA-emitted pending_review
row).

**Headline**: iter-19's two killer findings —
the orchestrator's branch getting switched
mid-chain (iter-17 retro #7 carry-over
materialised) AND Backend's 600s timeout
(now-11-iteration carry-over) — were both
materially addressed in iter-20. The
branch-isolation fix is **proven closed
end-to-end**; the Backend decomposition prompt
fix produced the intended STRUCTURAL outcome (TL
emits 2 Backend subtasks) but didn't prevent the
600s timeout from biting one of those subtasks.
The QA-emitted `pending_review` row that's been
the unmet success criterion since iter-19 Phase 7
remains deferred — iter-21 must add a Backend
runtime tripwire.

## What shipped

Phase 0 — Plan (`docs/iterations/iter_20.md`, 920
lines) committed on `worktree-iter-20` cut from
`origin/main` at `ed93241` (iter-19 squash).

Phase 1 — `handle_create_branch` uses `git worktree add` (TDD):
- New module-level `_ACTIVE_WORKTREE: Path | None`
  on `tools/mcp_servers/ai_team_repo/handlers.py`.
  Naturally scoped to one MCP server subprocess,
  which lasts exactly one agent's session
  (`claude -p` spawns a fresh MCP server per
  invocation).
- New `_slugify_branch(branch)` +
  `_effective_cwd(ctx)` helpers.
- `handle_create_branch` rewrites the subprocess
  invocation: `git checkout -b <branch> <base>`
  → `git worktree add <isolated_path> -b <branch>
  <base>` with `<isolated_path> =
  <scope_root>/.claude/agent-worktrees/<slug>/`.
  Returns `worktree_path` in the structured
  content.
- `handle_status`, `handle_run_shell`,
  `handle_open_pr` all use `_effective_cwd(ctx)`
  instead of `ctx.scope.root` for the
  subprocess cwd.
- `handle_write_file_in_scope` rebases the
  resolved (scope-validated) path into the active
  worktree so writes land there.
- 2 new unit tests with real tmp-git-repo
  fixture: `test_create_branch_does_not_switch_orchestrator_head`
  + `test_write_file_after_create_branch_lands_in_worktree`.
- Autouse `_reset_active_worktree` fixture
  prevents cross-test state leak.

Phase 2 — TL Backend decomposition prompt:
- `prompts/team_lead.md`: new "Exception for
  Backend work" section in "Decomposition
  style". Three-subtask example template
  (data model → service layer → API surface).
- `tests/unit/test_team_lead_agent.py`: pin test
  asserts the "200 LOC" + "backend" markers in
  the prompt.

Phase 3 — `scripts/demo_iter_20.sh`:
- Clone of `demo_iter_19.sh` with iter-20
  narrative.
- New step 1.5/7 pre-flight `git worktree
  prune` + `rm -rf .claude/agent-worktrees/`.
- EXIT trap rewritten as `_cleanup_iter20()`
  function that iterates each agent worktree
  and runs `git worktree remove --force` with
  `rm -rf` fallback.
- `.iter20-mcp.json` MCP config filename (no
  collision with iter-19).
- `Makefile`: `demo-iter-20` alias; `demo`
  repointed.

Phase 4 — Validation gates (all green):
- `ruff check`: `All checks passed!` (after the
  TC003 fix moving `Iterator` + `Path` into
  TYPE_CHECKING).
- `ruff format --check`: no diffs.
- `mypy`: `Success: no issues found in 148
  source files`.
- `bandit`: `High: 0`.
- `pytest tests/unit`: **421 pass** (iter-19's
  418 + 3 new = 421).
- `pytest tests/integration`: **50 pass**.
- `make smoke-llm`: `Overall: PASS` (first run
  variance-flaked one sub-check; retry passed).

Phase 5 — Real-LLM demo (run #1, cost ~$4.25):
- **Branch-isolation**: orchestrator HEAD stayed
  on `worktree-iter-20` throughout the chain.
  iter-19 Caveat B closed.
- **TL Backend decomposition**: audit-log rows
  305 + 306 show TWO `team_lead →
  backend_developer` task_assignments. Phase 2
  prompt edit structurally confirmed.
- Architect's ADR-0027 explicitly references
  commit `1a275fc` (the iter-20 Phase 2 commit).
- 4 of 5 other LLM-bound agents succeeded (PM
  290s done, Architect 473s done, Designer 356s
  done, Frontend 158s done).
- **Backend timed out at 600s on one subtask** —
  the prompt-only fix wasn't enough.
- QA cascade-dropped per iter-7 dispatcher
  behavior; no `pending_review` row written.
- Demo auto-approve bash crashed AGAIN with
  JSONDecodeError; real root cause finally
  identified (heredoc-vs-pipe conflict — 3-iter
  carry-over for iter-21).
- Full report:
  `docs/iterations/iter_20_demo_report.md`.

## What went well

- **The iter-20 Phase 1 fix is fully validated
  under real-LLM stress**. Branch-isolation has
  been a 2-iteration concern; iter-20 closed it
  with a surgical 30-line handler change rather
  than the per-agent-worktree-architecture
  rewrite the iter-20 handoff considered.
  Surgical wins.
- **`_ACTIVE_WORKTREE` module-level design
  proved correct in production**. MCP server's
  per-`claude -p`-invocation lifetime IS the
  natural scope for the per-session worktree
  state. No session-tracking layer needed.
- **TDD discipline held throughout**. Phase 1's
  2 tests went RED→GREEN cleanly; the real
  tmp-git-repo fixture is reusable for any
  future subprocess-driven handler test.
- **Architect agent CITED commit `1a275fc` in
  its ADR**. The iter-N constraint shipping
  process is producing readable artifacts that
  agents consume correctly — a happy
  second-order signal about the broader
  orchestrator-agent collaboration.
- **TL Backend decomposition prompt produced
  the intended structural change**. TL DID
  emit 2 Backend subtasks. The prompt edit
  worked; it just wasn't sufficient on its own.
- **Demo cleanup (Phase 3) worked**. Post-EXIT,
  `.claude/agent-worktrees/` was clean; `git
  worktree list` showed no orphaned entries.
- **Static gates carried iter-20's primary
  validation weight** even when the demo's
  end-to-end criterion stayed deferred — same
  pattern as iter-19. The unit-test contract
  pins close the contracts independently of
  real-LLM variance.

## What didn't

- **The Backend prompt-only fix is empirically
  insufficient**. iter-20 Phase 2 was deliberately
  a prompt-only attempt with the understanding
  that iter-21 would add a runtime tripwire if
  needed. iter-20's demo definitively shows it's
  needed — iter-21 must ship the tripwire.
- **The QA-emitted `pending_review` row remains
  unmet for the SECOND iteration in a row.**
  iter-19 deferred it, iter-20 deferred it.
  Backend is the bottleneck; until Backend can
  reliably complete in ≤600s, the chain doesn't
  reach QA.
- **Demo auto-approve bash kept hitting
  JSONDecodeError**. This is now a 3-iteration
  carry-over (iter-18 → iter-19 → iter-20). The
  iter-18 fix attempt (echo fallback) and
  iter-19 fix attempt (`${VAR:-[]}` + printf)
  both missed the real bug: `command | python3
  <<'PY' ... PY` is a heredoc-vs-pipe conflict.
  Bash routes python's stdin to the HEREDOC,
  not the pipe. iter-21 needs the proper fix
  (`python3 - "$JSON" <<'PY' ... sys.argv[1]`).
- **Architect spend jumped 3.7×**: $0.78
  (iter-19) → $2.88 (iter-20). The Architect's
  session ran 473s on opus. The TL
  over-decomposition prompt hint (carry-over)
  is a candidate fix but doesn't fully explain
  the jump.

## Surprises

- **Architect cited the iter-20 commit SHA in
  its ADR** (`1a275fc`). This is the first
  time I've observed an agent referencing the
  iter-N constraint shipping process by
  commit identifier. The iter-N constraint
  documents are not just configuration —
  they're being read and quoted by the agents.
  Worth tracking as a positive signal.
- **TL ACTUALLY followed the prompt edit on
  the first try**. iter-20 Phase 2's prompt
  change said "emit multiple Backend subtasks
  with depends_on slugs"; TL did exactly that.
  LLM compliance with NEW prompt-only
  instructions is better than I expected.
- **The iter-18 + iter-19 "Caveat 4 fix"
  attempts were both wrong**. Two iterations
  fixing the wrong thing. The real bug is at
  the bash shell level (heredoc precedence),
  not in the JSON parsing. A reminder that
  recurring "fixed" bugs deserve a fresh
  root-cause look, not another patch on top of
  the prior patch.

## Action items for iter-21

1. **(NEW TOP)** **Backend runtime tripwire**.
   `BackendDeveloperAgent.handle()` rejects an
   incoming `task_assignment` whose description
   plausibly exceeds ~200 LOC scope. On reject,
   return `BLOCKED(blocked_on='task_too_large')`
   so the chain recovers and TL can
   re-decompose. Heuristic: description char
   count > 1500 chars, OR description mentions
   ≥ 3 distinct file-path tokens that don't
   already exist on disk.
2. **(NEW)** **Demo auto-approve bash fix
   correctly**. 3-iteration carry-over.
   Replace `printf | python3 <<'PY' ... PY`
   pattern with `python3 - "$JSON" <<'PY'`
   form that uses `sys.argv[1]` instead of
   `sys.stdin.read()`. Apply to iter-21's
   demo script + leave a comment in the
   prior demos so a future iter doesn't
   re-introduce the antipattern.
3. **(NEW)** **Architect spend watch
   escalating**: $0.78 (iter-19) → $2.88
   (iter-20). Investigate what Architect's
   473s session is doing — re-reading docs?
   Excessive ADR re-derivation? The TL
   over-decomposition hint (carry-over #7)
   may help but doesn't explain a 3.7×
   increase.
4. **Re-attempt the QA-emitted `pending_review`
   row criterion** under iter-21's tripwire
   fix. Now-2-iteration deferred.
5. **Carry-overs unchanged** from iter-20
   handoff (HoldQueue persistence,
   `pytest-rerunfailures` plugin pin, TL
   auto-hop, TL over-decomposition prompt
   hint, `audit_writer` role, hash-chain
   alert, `GitHubTargetRepo`, TL transactional
   insert, `BaseAgent` template refactor,
   `mark_task_done`/`update_task_status` real
   impls, substrate `--allowed-tools ""` fix).

## Stats

- **Commits on `worktree-iter-20`**: 8 (plan +
  2 feat + 1 chore + 1 style + 1 docs;
  retro/handoff forthcoming).
- **LOC delta**: code +30 (handler +20 net,
  prompt +14 lines, tests +95); docs +~2000
  (plan 920 + demo report 299 + retro + handoff
  TBD); demo script 350 (clone of iter-19 with
  cleanup). Total ~2500 LOC including docs.
- **Tests**: +3 (2 worktree + 1 prompt pin).
  **421 unit + 50 integration tests pass.**
- **Real-LLM spend**: ~$4.25 (under $5
  ceiling). Above iter-19's $2.
- **Diff-cover**: 100% on new code paths.
- **Demo wall-clock**: run #1 ~33 min (Backend
  timeout at ~30 min + cleanup).
- **`pending_reviews` table state at iter-20
  close**: 1 row total (iter-18 historic-first,
  still `approved`). No iter-20 row written.
  Same as iter-19 close.

## Ready-to-paste prompt for iter-21

Lives in `docs/iterations/iter_21_handoff.md`.
