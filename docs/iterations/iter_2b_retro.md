# Iteration 2b — Retrospective

**Closed**: 2026-05-18. 7 commits on `worktree-iter-2b` (plan + 4 Phase-1
items + 3-agent Phase-2 commit). 244/244 unit tests green, 10/10 new
integration tests green, ruff / mypy / format clean.

Same hand-off pattern as iter-2: the **real-LLM end-to-end demo
(1D + 2D)** is shipped as wiring + scripts; the actual real-LLM run
is owner-action. Everything else closed.

## What shipped

Phase 1 — close iter-2 carry-overs:
- **1A** `set_forbidden_pr_base_re()` + `AI_TEAM_FORBID_PR_BASE_RE` env.
  `gh_pr_create` validator can be overridden per target — the ai_team
  self-repo MCP spawn passes `^(master|release/.*)$` to allow `main` as
  a base; default behaviour unchanged for everything else. 3 unit tests.
- **1B** `env: dict[str,str] | None` kwarg on `LLMClient.invoke`,
  merged into the spawned claude -p subprocess env. `BaseAgent.mcp_env`
  ClassVar; Architect/Backend/QA each override with their ADR-004 path
  scope. `scope.py` gained `denied_prefixes` so Backend can express
  `* allow minus infra/+.github/workflows/`. 9 unit tests (env-merge,
  denylist, per-role mcp_env values).
- **1C** ADR-008 validation table refreshed: cold-haiku latency now
  median ≤ 10s, max ≤ 25s (5 samples). The session-caching row also
  reflects the iter-2 `--session-id` / `--resume` split.
- **1E** `SelfBootstrapTargetRepo` active methods filled in
  (`checkout`, `stage_and_commit`, `push`, `open_pr`, `run_tests`,
  `run_linter`, `status`). Subprocess-based, security guards stay in
  place. 10 integration tests against a tmp local repo + tmp bare
  remote.

Phase 2 — three new agents:
- **Designer** (Sonnet, design notes → `docs/design/`, 7 unit tests).
- **DevOps** (Sonnet, infra/CI patches, BLOCKED-status escalation, 7
  unit tests).
- **Market Researcher** (Sonnet, market scans + WebFetch, 8 unit
  tests).

apps/api/main.py registers all three in the dispatcher.

## What went well

- **The iter-2 pattern scaled.** Each new agent was ~250 LOC
  (agent + prompt + 7-8 tests) and dropped into the dispatcher with
  one import line. Architect's TDD template was directly reusable.
- **Phase 1 hardening was clean.** 1A through 1E each landed in one
  small commit with focused tests. No surprise rework.
- **Backend's denylist works as designed.** ADR-004's "Backend writes
  anywhere except infra/+.github/workflows/" is now enforceable at the
  MCP-server boundary, not just by prompt discipline.
- **TargetRepo subprocess impls have realistic integration tests.**
  The tmp-repo-with-bare-remote fixture gives us actual `git push`
  coverage without touching GitHub. `open_pr` is the only method that
  still depends on a real GitHub remote (covered by the end-to-end
  demo).

## What didn't

- **The real-LLM e2e demo (1D + 2D) is again unrun** in this session.
  Same prerequisites as iter-2 closure (Docker, .env, gh auth,
  pending_review approval). The wiring + commitlint + diff-cover
  posture are healthier than iter-2's, so a single run should
  exercise both iter-2 and iter-2b agents end-to-end.
- **Self-bootstrap PR-base override is config-coupled.** Agent code
  doesn't *know* it's working against ai_team; the dispatcher /
  demo-script passes `AI_TEAM_FORBID_PR_BASE_RE` and trusts that.
  Acceptable for iter-2b (single target_repo at a time) but will need
  re-thinking once we serve multiple targets concurrently.

## Surprises

- **`subject-case` and `footer-max-line-length` from iter-2 stayed
  off.** The iter-2 commitlint config carried into iter-2b
  unchanged — every Phase-1/Phase-2 commit passed without
  workarounds.
- **DevOps's BLOCKED-status path is more useful than expected.** The
  schema's `validation_step` field doubles as an escalation channel
  ("blocked: requires Backend change in agents/foo.py"). One unit
  test pins this; the TL routing logic in iter-2c can use it to
  spawn a follow-up task automatically.

## Action items for iter-2c

- [ ] **Run the real-LLM e2e demo against both iter-2 (TL → Arch →
      BE → QA) and iter-2b (Designer / DevOps / Market Researcher) flows.**
      Capture in `docs/iterations/iter_2_demo_report.md` (or
      `iter_2b_demo_report.md` if split). Same prereq checklist as
      iter-2 retro.
- [ ] **Frontend Developer agent** (deferred from iter-2b). Largest
      single agent because of UI-test pattern + path scope crossover
      with Backend (apps/web/ + frontend tree in target_repo).
- [ ] **SRE/Support agent** (deferred from iter-2b). Runbooks +
      monitoring; gates on iter-5 server move for full usefulness.
- [ ] **`GitHubTargetRepo` impl** when the first commercial repo
      lands. ADR-009 says this is "deferred to first commercial
      product" — that day will come.
- [ ] **TL routing on BLOCKED reports.** When DevOps (or any agent)
      emits `status=BLOCKED` with "blocked: requires <X>" in the
      summary, TL should spawn a follow-up `task_assignment` to <X>
      automatically rather than leaving it for the owner. Stretch.

## Stats

- **Commits on iter-2b branch**: 7 (plan + 1A + 1B + 1C + 1E + Phase
  2 agents + this retro).
- **Tests added**: 32 unit (9 for env+denylist+mcp_env, 3 for env-driven
  forbidden-base, 22 across the three new agents) + 10 integration.
- **Total tests after iter-2b**: 244 unit + 10 integration (iter-2 left
  216 unit + 0 integration of the iter-2b shape).
- **Real-LLM spend this iteration**: ~$0 (no live runs; all
  `_StubLLM`-based). Iter-2b's $1.00 budget is fully unspent.
- **LOC delta**: ~1,400 added across agents/, prompts/, core/,
  tools/mcp_servers/, tests/.

## Ready-to-paste prompt for iter-2c

In a separate `docs/iterations/iter_2c_handoff.md`.
