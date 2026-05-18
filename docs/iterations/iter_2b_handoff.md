# Iteration 2b handoff

> Read **after** `CLAUDE.md` and `docs/iterations/iter_2_retro.md`.
> Together they're ~12 KB and replace re-reading the prior conversation.

## Where we are (2026-05-18 EOD, iter-2 closed)

`worktree-iter-2` carries 9 commits since iter-1's `aea9ff7`:

| Commit | Title |
|--------|-------|
| `a3a3694` | docs(iter-2): plan + 3 resolved decisions |
| `ecfd80e` | fix(llm): split --session-id (create) vs --resume (reuse) |
| `6201b35` | feat(iter-2): Day-1A cache measurement + report |
| `af85c1e` | feat(llm): LLMResponse.validated_against_schema + structlog |
| `ced5331` | build: pre-push hook + install-hooks target |
| `1e19bba` | feat(mcp): ai-team-repo server — path-scoped repo ops |
| `b555b59` | feat(target-repo): SelfBootstrap + InRepoExample + registry |
| `7482936` | feat(architect): Opus agent emitting ADRs |
| `390962b` | feat(agents): Backend Developer + QA Engineer |
| `e1e311a` | feat(iter-2): e2e demo wiring (dispatcher, MCP, demo script) |

Phase-2 agent set (Architect / Backend / QA) is wired into the
dispatcher. 198/198 unit tests green. `make smoke-llm` 5/5 PASS.

**The end-to-end real-LLM demo has not yet been executed** — that is
iter-2b's first task.

## Carry-over items (priority order)

1. **Run the real-LLM e2e demo.** Wiring complete; preconditions in
   `iter_2_retro.md` "Open at handoff". Expected to either (a) succeed
   end-to-end with a real PR on GitHub, or (b) fail at
   `gh_pr_create` because the command-class validator refuses `main`
   as a base. If (b), apply the env-driven forbidden-base fix below
   and re-run. Capture in `docs/iterations/iter_2_demo_report.md`.
2. **Forbidden-PR-base goes env-driven.** Move the regex out of
   `tools/mcp_servers/ai_team_repo/commands.py:_validate_gh_pr_create`
   and into `AI_TEAM_FORBID_BRANCH_RE` (already consumed by
   `handlers.py`). The demo's MCP config sets it to
   `^(main|master|release/.*)$` by default; the ai_team self-repo
   variant overrides it to `^(master|release/.*)$` (i.e. allows `main`).
3. **Per-role MCP path-scope at spawn time.** Thread
   `env: dict[str,str] | None` through `LLMClient.invoke` →
   `ClaudeCodeHeadlessClient` (merged into subprocess env, not
   `os.environ`). Architect/Backend/QA each set their own
   `mcp_env: ClassVar[dict[str,str]]` so the MCP server spawns with
   the right narrow `AI_TEAM_PATH_PREFIXES`. ADR-004's least-privilege
   matrix becomes enforceable.
4. **`TargetRepo` active methods.** Currently NotImplementedError
   because no Python call-site reaches them. Fill in subprocess-based
   impls and test against a real tmp git repo. The security guards
   stay where they are.
5. **ADR-008 latency table.** Replace original p50<3s / p99<6s with
   measured reality (median≤10s, max≤25s for cold haiku). Or drop
   latency to "informational only" — per-agent timeouts are the hard
   cap that matters.
6. **Iter-2b agents.** Designer (Sonnet, design notes →
   `docs/design/`), Frontend Developer (Sonnet, web app),
   DevOps-as-agent (Sonnet, infra/.github), SRE/Support (Sonnet,
   runbooks), Market Researcher (Sonnet, market analysis). Per ADR-004
   each has its own `allowed_tools` row.

## Hard constraints unchanged from iter-2

- **LLM substrate is `claude -p` via subscription.** Never set
  `ANTHROPIC_API_KEY`. Never use Agent SDK with API key.
- **`--json-schema` validated output lives in `structured_output`**,
  not `result`. (Iter-1 retro #1.)
- **`--session-id` is set-once, `--resume` is resume.** Adapter
  switches automatically — DO NOT pass either flag from agent code.
  Use `LLMClient.invoke(session_id=…)`. (Iter-2 retro.)
- **Boring stack only.** Re-read ADR-001 before considering any new
  framework.
- **Diff-cover gate is 80 %.** Bandit gates only on high.
- **Conventional commits, squash-merge, plan-before-code, owner
  approval on every agent task completion.**
- **Bash never raw on agents.** Use `mcp__ai_team_repo__run_shell`
  with its command-class enum.

## Decisions inherited (do not contradict without revisiting)

- Agent PRs may target `main` on `ai_team` only (single-repo
  exception). All other repos use `develop` per ADR-009.
- Architect is **advisory**, not gating. TL is the only gating
  router. Backend reads Architect's ADR via `Read`.
- `idea-validator`'s own LLM calls go through the same `claude -p`
  substrate as `ai_team` itself; they share the owner's subscription
  quota. Honest cost accounting.

## Ready-to-paste prompt for the new session

Copy into the first message of a new Claude Code session at
`/Users/kirillterskih/ai_team/`:

---

```
Starting Iteration 2b on the ai_team project.

First, read these in this order:

1. `CLAUDE.md`
2. `docs/iterations/iter_2_retro.md` (what just shipped, what's still open)
3. `docs/iterations/iter_2b_handoff.md` (this file — full handoff context)
4. `docs/adr/0001-orchestrator-choice.md`, `0004-tool-inventory.md`,
   `0008-llm-access-strategy.md`, `0009-target-repo-abstraction.md`

Iter-2b goal: close iter-2's open items (the real-LLM e2e demo run +
the iter-2b carry-overs in the retro), then add Designer, Frontend,
DevOps-as-agent, SRE, Market Researcher.

Workflow: plan-before-code. Draft `docs/iterations/iter_2b.md` first,
surface for review, then code. Run `make smoke-llm` + `make demo-iter-2`
against real `claude -p` before declaring done. Run validation checks +
PR merges yourself (autonomy preference is in memory).

Constraints unchanged from iter-2 — see CLAUDE.md gotchas #1–#3 and
the "Hard constraints" section of iter_2b_handoff.md.

When ready, create the iter-2b task list and surface the plan.
```

---

Save your quota: that prompt + the three required docs is ~12 KB of
input, ~3 K tokens. Should be well under 10 K input on the first round
trip.
