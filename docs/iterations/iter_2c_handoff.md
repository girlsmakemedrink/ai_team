# Iteration 2c handoff

> Read **after** `CLAUDE.md` and `docs/iterations/iter_2b_retro.md`.
> Together ~10 KB; replaces re-reading the prior conversation.

## Where we are (2026-05-18 EOD, iter-2b merged)

Iter-2 and iter-2b are both on `main`. Eight agents are live in the
dispatcher: **Team Lead (Opus)**, **Product Manager (Sonnet)**,
**Architect (Opus)**, **Backend Developer (Sonnet)**, **QA Engineer
(Sonnet)**, **Designer (Sonnet)**, **DevOps (Sonnet)**, **Market
Researcher (Sonnet)**. Each has per-role MCP path-scope at
server-spawn time (ADR-004 enforced).

`SelfBootstrapTargetRepo`'s active methods are subprocess-backed and
integration-tested against a tmp local repo + bare remote. `gh_pr_create`
forbidden-base is env-driven so the ai_team self-repo PR exception
works without code change.

**The real-LLM e2e demo has STILL not been executed end-to-end** — same
prereq list as the iter-2 retro had. That's iter-2c's first item.

## Carry-over items (priority order)

1. **Run the real-LLM e2e demo.** Wiring is mature now (iter-2
   forbidden-base unblocking + iter-2b per-role scope). Set
   `AI_TEAM_DEMO_NON_INTERACTIVE=1` and run `make demo-iter-2`. Capture
   per-agent cost + wallclock + schema-validation-rate in
   `docs/iterations/iter_2_demo_report.md`. Budget ~$0.40 / run; spend
   up to ~$2 if needed for debugging.
2. **Frontend Developer agent** (Sonnet). Receives task_assignment,
   writes web UI code via the same MCP write_file_in_scope pattern,
   produces a `task_report` referencing the PR. Path scope:
   `apps/web/,apps/cli/` for ai_team's own CLI, or the target_repo's
   frontend tree (e.g. `app/src/`, `web/src/`). The heaviest single
   agent because of UI-testing semantics (`playwright` MCP shell, or
   reliance on Backend's unit tests).
3. **SRE/Support agent** (Sonnet). Writes runbooks +
   monitoring config. Path scope: `docs/runbooks/,infra/monitoring/`.
   Allowed shell: `curl` (read-only against owner-approved internal
   URLs), `promtool`, `journalctl`. Lower priority — not blocking
   until iter-5 server move.
4. **TL routing on BLOCKED reports.** When DevOps (or any agent)
   reports `status=BLOCKED` with `summary` starting "blocked: requires
   <X>", TL spawns a follow-up `task_assignment` to <X> automatically.
   Lets the team self-route around path-scope limits without owner
   intervention.
5. **`GitHubTargetRepo` impl** when first commercial repo lands.
   ADR-009 says "deferred to first commercial product".

## Hard constraints unchanged from iter-2/2b

- **LLM substrate is `claude -p` via subscription.** Never set
  `ANTHROPIC_API_KEY`. Never use Agent SDK with API key.
- **`--json-schema` validated output lives in `structured_output`**.
- **`--session-id` is set-once, `--resume` is resume.** Adapter
  switches automatically; agents pass `session_id=…` only.
- **Boring stack only.** Re-read ADR-001 before considering any new
  framework.
- **Diff-cover gate is 80 %. Bandit gates on high only.**
- **Conventional commits, squash-merge, plan-before-code, owner
  approval on every agent task completion.**
- **Bash never raw on agents.** Use `mcp__ai_team_repo__run_shell`
  with its command-class enum.

## Inherited decisions (do not contradict without revisiting)

- Agent PRs target `main` on `ai_team` only (single-repo exception).
- Architect is **advisory**, not gating. TL is the only gating router.
- `idea-validator`'s LLM calls share owner quota.
- Backend's path-scope is `* allow + denylist` (infra/,
  .github/workflows/).
- DevOps emits `BLOCKED` when an ask requires Backend territory.

## Ready-to-paste prompt for the new session

```
Starting Iteration 2c on the ai_team project.

First, read these in this order:

1. CLAUDE.md
2. docs/iterations/iter_2b_retro.md (what just shipped, what's still open)
3. docs/iterations/iter_2c_handoff.md (this file — full handoff context)
4. docs/adr/0001-orchestrator-choice.md, 0004-tool-inventory.md,
   0008-llm-access-strategy.md, 0009-target-repo-abstraction.md

Iter-2c goal: run the iter-2/2b real-LLM e2e demo for real (carry-over #1),
then bring Frontend and SRE online; close out TL BLOCKED routing as a
small bonus.

Workflow: plan-before-code. Draft docs/iterations/iter_2c.md first,
surface for review, then code. Run validation checks + PR merges yourself
(autonomy preference in memory).

Constraints unchanged from iter-2b — see CLAUDE.md gotchas + the
"Hard constraints" section of iter_2c_handoff.md.

When ready, create the iter-2c task list and surface the plan.
```
