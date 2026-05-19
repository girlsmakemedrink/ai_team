# Iteration 2c — Plan

- **Status**: Draft (awaiting owner approval)
- **Plan author**: Claude (Opus 4.7)
- **Date drafted**: 2026-05-19
- **Base commit**: `5ccdc02` on `main` (iter-2b squash)
- **Branch**: `worktree-iter-2c`
- **Anchors (do not contradict)**: ADR-001, ADR-004, ADR-006, ADR-008,
  ADR-009; iter-2b retro action items; iter-2c handoff carry-overs

## Goal — one sentence

Execute the real-LLM e2e demo against the 8-agent dispatcher and
capture the report (carry-over #1), then bring **Frontend Developer +
SRE/Support** online and close out **TL BLOCKED routing** as a small
bonus.

## Success criteria (binary, measurable)

1. **Real-LLM e2e demo report** at
   `docs/iterations/iter_2_demo_report.md` — owner submits the
   `implement idea-validator from spec` task non-interactively, chain
   runs TL → Architect → Backend → QA → `pending_review`, owner
   approves, PR lands. Captures per-agent cost + wallclock +
   schema-validation rate.
2. **Frontend Developer agent** (Sonnet) — receives `task_assignment`,
   writes UI code in `apps/web/` (or `apps/cli/`) via path-scoped MCP
   write, produces a `task_report` referencing the artifact list, emits
   `BLOCKED` when the ask requires Backend territory (parallel to
   DevOps's pattern).
3. **SRE/Support agent** (Sonnet) — receives `task_assignment`, writes
   runbook / monitoring patch under `docs/runbooks/` or
   `infra/monitoring/`, reports back. Has `WebFetch` (for owner-approved
   internal URLs) but no shell yet (deferred until iter-5 server
   move — full `curl`/`promtool`/`journalctl` allowlist lands then).
4. **TL BLOCKED routing.** When *any* agent emits a `task_report` with
   `status=BLOCKED` and a parseable `blocked_on` role (or a
   `blocked: requires <role>` summary prefix as fallback), TL spawns
   one follow-up `task_assignment` to that role automatically. Owner
   intervention not required to keep the chain moving.
5. **`make test-unit` green; `make test-integration` green;
   `make lint`, `make typecheck`, `make sec` clean;
   diff-cover ≥ 80 %; `make smoke-llm` green.**
6. `docs/iterations/iter_2c_retro.md` + `iter_3_handoff.md` stub.

## Non-goals (explicitly deferred)

- **SRE full shell allowlist** (`curl`/`promtool`/`journalctl`) —
  meaningful only once we're on the iter-5 server; this iteration only
  wires the agent up with `Read`/`Glob`/`Grep`/`WebFetch` + path-scoped
  write, and a stub `run_shell` permission gated behind a feature flag.
- **`GitHubTargetRepo` impl** — still waiting on first commercial
  product.
- **Playwright / real browser tests for Frontend** — Frontend is shipped
  as code-producer only; verification is by Backend's existing unit
  tests + manual run. Browser-driven verification is a separate piece
  of work (and arguably belongs to QA, not Frontend).
- **`audit_writer` Postgres role enforcement** — iter-3.
- **Hash-chain alert job** — iter-3.
- **Splitting API + dispatcher processes** — iter-5.

## Plan — five phases

### Phase 1 — Real-LLM e2e demo (carry-over #1)

**Cost budget**: ~$0.40 expected; up to $2 for debug retries.

| # | Task | Output |
|---|------|--------|
| 1A | Pre-flight checks (`.env`, `docker`, `gh auth status`, `claude` auth, free quota ≥ 30%) | terminal output captured in report appendix |
| 1B | Run `AI_TEAM_DEMO_NON_INTERACTIVE=1 make demo-iter-2` end-to-end | chain completes, pending_review row exists |
| 1C | Owner runs `uv run ai-team approve <id>` on the QA report | task_report status → approved |
| 1D | Capture cost/wallclock/schema-validation rate in `docs/iterations/iter_2_demo_report.md` | committed report |

Why this is first: iter-2 and iter-2b both shipped the *wiring* and
deferred the run. The plumbing is the most mature it's been. If
something breaks here, it's higher leverage to know now than to
discover it after layering on two new agents.

Failure handling: if the chain breaks mid-run, capture the failure mode
+ logs in the report rather than wallpapering over it. A reproducible
failure is a valid iter-2c outcome — it informs iter-3 priorities.

### Phase 2 — Frontend Developer agent

Largest single agent in iter-2c (path-scope crosses Backend territory,
UI-testing semantics are not solved).

**Path scope**: `apps/web,apps/cli` for ai_team's own surfaces; for
target repos with a frontend tree, the agent inherits the same prefix
list scoped to the `TARGET_REPO`'s root (handled at MCP-server spawn
time via `AI_TEAM_PATH_PREFIXES` env, same pattern as Designer).

**Iter-2c shipping choice**: ship the agent against `apps/web` /
`apps/cli` for now. Target-repo frontend-tree scope (e.g. `app/src/`,
`web/src/`) is configurable per-task via the env, same as Backend's
denylist. Don't add a second "frontend tree env var" — keep the
single `AI_TEAM_PATH_PREFIXES` knob.

| # | Task | Files | Cost |
|---|------|-------|------|
| 2A | Frontend system prompt | `prompts/frontend_developer.md` | $0 |
| 2B | `FrontendDeveloperAgent` class | `agents/frontend_developer/{__init__.py,agent.py}` | $0 |
| 2C | Unit tests | `tests/unit/test_frontend_developer_agent.py` | $0 |
| 2D | Register in dispatcher | `apps/api/main.py` | $0 |
| 2E | Update demo script (optional) | `scripts/demo_iter_2c.sh` (optional, see Phase 5) | $0 |

#### 2B detail — `FrontendDeveloperAgent`

Direct copy of the `DevOpsAgent` shape (DevOps is the closest match —
both write code, both can be BLOCKED on Backend territory):

```python
class FrontendDeveloperAgent(BaseAgent):
    role: ClassVar[AgentId] = AgentId.FRONTEND_DEVELOPER
    model_tier: ClassVar = "sonnet"
    allowed_tools: ClassVar[tuple[str, ...]] = (
        "Read",
        "Glob",
        "Grep",
        "mcp__ai_team_repo__status",
        "mcp__ai_team_repo__create_branch",
        "mcp__ai_team_repo__write_file_in_scope",
        "mcp__ai_team_repo__run_shell",          # for `npm test` etc., via command_class
        "mcp__ai_team_repo__open_pr",
        "mcp__ai_team_bus__publish_message",
        "mcp__ai_team_bus__read_team_feed",
        "mcp__ai_team_tasks__mark_task_done",
        "mcp__ai_team_tasks__request_human_review",
    )
    system_prompt_path: ClassVar[Path] = _REPO_ROOT / "prompts" / "frontend_developer.md"
    # Per ADR-004: writes under apps/web or apps/cli (ai_team's own surfaces).
    # For external target repos, callers override via AI_TEAM_PATH_PREFIXES.
    mcp_env: ClassVar[dict[str, str]] = {
        "AI_TEAM_PATH_PREFIXES": "apps/web,apps/cli",
    }
    llm_timeout_s: ClassVar[int] = 600
    max_turns: ClassVar[int] = 20
```

Output schema mirrors DevOps:

```json
{
  "target_files":   ["apps/web/src/Foo.tsx", "..."],
  "changes":        "one-paragraph description of what changed and why",
  "rationale":      "links to ADRs, Designer notes, Backend interfaces this consumes",
  "validation_step": "what you ran (or 'blocked: requires Backend (...)')",
  "pr_url":         "https://github.com/.../pull/<n>",
  "branch":         "agent/frontend/<slug>"
}
```

`build_outputs`: same shape as DevOps — emit `BLOCKED` when
`validation_step.lower().startswith("blocked")`. The `blocked_on` field
on `TaskReportPayload` gets the parsed role (`backend_developer` /
`designer` / etc.); Phase 4 uses it.

#### 2C detail — tests (target 7-9 unit tests, parallel to DesignerAgent's 5 + DevOpsAgent's 7)

- `test_role_and_tier`
- `test_mcp_env_scopes_to_apps_web_and_cli`
- `test_allowed_tools_no_raw_bash_write`
- `test_handle_writes_report_and_emits_done`
- `test_handle_emits_blocked_when_validation_says_blocked` (with
  `blocked_on=AgentId.BACKEND_DEVELOPER`)
- `test_handle_fails_on_missing_structured`
- `test_handle_skips_non_task_assignment`
- `test_branch_pattern_enforced_by_schema`

No cassettes; `_StubLLM` only (consistent with iter-2b).

#### 2D detail — registration

In `apps/api/main.py:lifespan`, after the existing 8-agent dict, add:

```python
AgentId.FRONTEND_DEVELOPER: FrontendDeveloperAgent(llm=llm),
```

Import line near the top alongside the other agents. No other plumbing.

### Phase 3 — SRE/Support agent

Lower priority than Frontend (SRE doesn't become fully useful until
the iter-5 server move when there are runbooks to write *against*
production), but it's the last MVP agent on the matrix and worth
landing cheaply now while the pattern is fresh.

**Path scope**: `docs/runbooks,infra/monitoring`.

**Allowed tools (iter-2c shipping)**:

- `Read`, `Glob`, `Grep`, `WebFetch`
- `mcp__ai_team_repo__write_file_in_scope` (path-scoped per
  `mcp_env`)
- `mcp__ai_team_bus__publish_message`, `read_team_feed`
- `mcp__ai_team_tasks__mark_task_done`, `request_human_review`

**Not yet on the allowlist (deferred to iter-5)**:
`mcp__ai_team_repo__run_shell` (`curl`/`promtool`/`journalctl`). The
underlying `command_class` enum doesn't yet enumerate these and the
target environment they'd touch (Prometheus, journald) doesn't exist
in dev. Wiring them now would be dead code with security exposure.

ADR-004 already documents the full SRE shell intent ("`curl`
read-only, `promtool`, `journalctl`") — we just don't ship it yet.
Acceptable per the same logic as `GitHubTargetRepo` (deferred until
the destination exists).

| # | Task | Files | Cost |
|---|------|-------|------|
| 3A | SRE system prompt | `prompts/sre_support.md` | $0 |
| 3B | `SRESupportAgent` class | `agents/sre_support/{__init__.py,agent.py}` | $0 |
| 3C | Unit tests | `tests/unit/test_sre_support_agent.py` | $0 |
| 3D | Register in dispatcher | `apps/api/main.py` | $0 |

#### 3B detail — `SRESupportAgent`

Closer to the **Designer** shape than DevOps (writes
human-readable artifacts, doesn't open PRs in iter-2c — that comes
when the iter-5 server is online and there's a real on-call rotation):

```python
class SRESupportAgent(BaseAgent):
    role: ClassVar[AgentId] = AgentId.SRE_SUPPORT
    model_tier: ClassVar = "sonnet"
    allowed_tools: ClassVar[tuple[str, ...]] = (
        "Read",
        "Glob",
        "Grep",
        "WebFetch",
        "mcp__ai_team_repo__write_file_in_scope",
        "mcp__ai_team_bus__publish_message",
        "mcp__ai_team_bus__read_team_feed",
        "mcp__ai_team_tasks__mark_task_done",
        "mcp__ai_team_tasks__request_human_review",
    )
    system_prompt_path: ClassVar[Path] = _REPO_ROOT / "prompts" / "sre_support.md"
    mcp_env: ClassVar[dict[str, str]] = {
        "AI_TEAM_PATH_PREFIXES": "docs/runbooks,infra/monitoring",
    }
```

Output schema (one runbook per task — analogous to Designer's
one-design-per-task):

```json
{
  "title":     "Runbook — <symptom>",
  "slug":      "kebab-case",
  "kind":      "runbook" | "alert" | "dashboard",
  "summary":   "1-2 sentence what / when",
  "steps":     "ordered markdown list of recovery steps",
  "metrics":   ["link to Grafana board", "PromQL expr", "..."],
  "owner":     "sre_support",
  "severity":  "P1" | "P2" | "P3" | "P4"
}
```

`build_outputs`: write a markdown file
`docs/runbooks/<slug>.md` (or `infra/monitoring/<slug>.md` for `kind`
in `{"alert", "dashboard"}`), then `TaskReport(status=DONE)` back to
TL. No `BLOCKED` path in this iteration (SRE is consume-only; no
upstream dependency).

#### 3C detail — tests (target 5-7 unit tests)

- `test_role_and_tier`
- `test_mcp_env_scopes_to_runbooks_and_monitoring`
- `test_allowed_tools_no_raw_bash`
- `test_handle_writes_runbook_md_and_reports_to_tl`
- `test_handle_writes_alert_to_monitoring_dir_when_kind_is_alert`
- `test_handle_fails_on_missing_structured`
- `test_handle_skips_non_task_assignment`

### Phase 4 — TL BLOCKED routing (bonus)

When DevOps (or Frontend, now) emits a `TaskReport(status=BLOCKED)`
with `blocked_on=AgentId.<role>`, TL should spawn a follow-up
`TaskAssignment` to that role automatically rather than dropping the
chain on the floor for the owner to notice in the digest.

**Why this matters**: iter-2b shipped DevOps's BLOCKED signal but
nothing consumed it. The system *looks* well-routed in unit tests but
in practice the owner had to read the digest and re-route by hand.
That's a regression vs. the iter-1 goal of "owner-in-the-loop only at
checkpoints, not at every routing hop."

**Why bonus, not Phase 1**: it's a small change to TL, but the value
is only realised once we have ≥ 2 agents that can emit BLOCKED
(currently just DevOps; iter-2c adds Frontend). Doing it after Phase 2
lets us test the routing with a real second source.

#### 4A — TL handle() accepts TASK_REPORT(BLOCKED) and re-routes

Today `TeamLeadAgent.handle()` skips anything that isn't
`TASK_ASSIGNMENT`. Change:

```python
async def handle(self, msg: AgentMessage) -> list[AgentMessage]:
    if msg.message_type == MessageType.TASK_REPORT:
        return self._maybe_route_blocked(msg)
    if msg.message_type != MessageType.TASK_ASSIGNMENT:
        self._log.debug("tl.skip", message_type=msg.message_type.value)
        return []
    # ... existing decomposition path unchanged
```

`_maybe_route_blocked(msg)` is a pure function (no LLM call — saves
budget and latency on the routing hop):

```python
def _maybe_route_blocked(self, msg: AgentMessage) -> list[AgentMessage]:
    if not isinstance(msg.payload, TaskReportPayload):
        return []
    if msg.payload.status != TaskStatus.BLOCKED:
        return []
    target_role = self._parse_blocked_target(msg.payload)
    if target_role is None or target_role == AgentId.TEAM_LEAD:
        return []  # nothing to re-route; owner sees in digest
    return [
        AgentMessage(
            correlation_id=msg.correlation_id,
            sender=AgentId.TEAM_LEAD,
            recipient=target_role,
            message_type=MessageType.TASK_ASSIGNMENT,
            priority=msg.priority,
            payload=TaskAssignmentPayload(
                task_id=uuid4(),
                title=f"Unblock: {msg.payload.summary[:160]}",
                description=(
                    f"{msg.sender.value} reported BLOCKED on this work. "
                    f"Their summary:\n\n{msg.payload.summary}\n\n"
                    f"Resolve the prerequisite, then report back to "
                    f"the Team Lead."
                ),
                # No target_repo — inherits from prior context via the
                # correlation_id (audit log has it).
            ),
        )
    ]

def _parse_blocked_target(self, payload: TaskReportPayload) -> AgentId | None:
    # Preferred: explicit `blocked_on` field on the payload.
    if payload.blocked_on:
        try:
            return AgentId(payload.blocked_on)
        except ValueError:
            pass
    # Fallback: parse "blocked: requires <role>" from the summary.
    m = re.match(r"blocked:\s*requires\s+(\w+)", payload.summary.lower())
    if m:
        try:
            return AgentId(m.group(1))
        except ValueError:
            return None
    return None
```

**Anti-loop guard**: cap blocked-routing at one auto-hop per
correlation. If the unblocking agent *also* emits BLOCKED, TL stops
and the owner sees the chain in the digest. Implemented via a counter
in `TaskReportPayload.summary` ("auto-routed from <X>") or — cleaner —
a counter in `AgentMessage.metadata` (TBD; see Risks). For iter-2c we
ship the simpler check: if the BLOCKED report's `summary` already
contains `"auto-routed"`, TL refuses to re-route a second time.

**No new schema field.** `TaskReportPayload.blocked_on` already
exists (`core/messaging/schemas.py:82`). Iter-2b just didn't use it.

#### 4B — DevOps + Frontend populate `blocked_on`

Small follow-on in `agents/devops/agent.py` and the brand-new
`agents/frontend_developer/agent.py`: when the LLM's
`validation_step` says `blocked: requires <role>`, set
`TaskReportPayload(..., blocked_on=<role>)` rather than only
embedding it in the summary string. This is the contract the TL
routing depends on; the summary parsing is the fallback.

#### 4C detail — tests

- `test_tl_routes_blocked_with_explicit_blocked_on_field`
- `test_tl_routes_blocked_by_parsing_summary_prefix`
- `test_tl_does_not_loop_when_summary_already_auto_routed`
- `test_tl_ignores_blocked_with_no_target` (no `blocked_on`, no
  parseable prefix → no-op)
- `test_tl_skips_non_blocked_task_reports`
- Updated `tests/unit/test_devops_agent.py` to assert
  `blocked_on=AgentId.BACKEND_DEVELOPER` on the payload.

### Phase 5 — Validation, retro, handoff

| # | Task | Output |
|---|------|--------|
| 5A | `make test` (unit + integration) | green |
| 5B | `make lint && make typecheck && make sec` | clean |
| 5C | Diff-cover ≥ 80% on the iter-2c diff | green |
| 5D | `make smoke-llm` | green |
| 5E | `docs/iterations/iter_2c_retro.md` | committed |
| 5F | `docs/iterations/iter_3_handoff.md` stub | committed |

**No iter-2c-specific demo.** The Phase-1 real-LLM run is the demo.
A second demo for Frontend/SRE would need a target_repo with a
frontend tree, and adding one only to demo this would be premature
(see ADR-009). The unit tests + the path-scope MCP wrapper are the
contract; the first real Frontend exercise will be the first
commercial product.

## Cost / quota envelope

- Phase 1 (real-LLM e2e demo): **$0.40** expected, $2 ceiling
  for debug retries.
- Phase 2 / 3 / 4 / 5: **$0** (mocked LLM throughout).
- **Total budget: ≤ $2.00.** Same envelope as iter-2b.

If Phase 1 demo retries blow past $2 (e.g. quota at 80% before the
run, demo flakes 3x), pause and revisit with the owner rather than
spending more.

## Risks & mitigations

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| Real-LLM demo fails on Backend code quality (LLM doesn't produce 200+ LOC of working idea-validator) | medium | Capture the failure mode in the report; that's a valid outcome and informs iter-3 |
| `gh pr create` fails in the demo (auth, branch protection) | low | Pre-flight 1A includes `gh auth status` + the `AI_TEAM_FORBID_PR_BASE_RE` override already shipped in iter-2b |
| Frontend agent's path-scope conflicts with Backend on shared apps/cli/ tree | low | Both agents go through the MCP wrapper; the wrapper's path-prefix check is shared. If two agents try to write the same file in parallel the second one writes the latest copy (last-writer-wins is the existing semantic) |
| TL BLOCKED routing causes a loop (DevOps → Backend → DevOps → ...) | medium | Anti-loop guard: TL refuses to re-route a BLOCKED report whose summary already contains `auto-routed`. Worst case the chain stops and the owner sees it in the digest — same as today |
| SRE agent's empty `docs/runbooks/` dir on first run | trivial | `_RUNBOOK_DIR.mkdir(parents=True, exist_ok=True)` (Designer pattern) |
| LLM response schema-validation rate < 90% in the real-LLM demo | medium | Already reported per-agent in `LLMResponse.validated_against_schema`; the demo report surfaces it. If < 90% that's a prompt tuning task for iter-3, not a blocker for iter-2c closure |

## Decisions to confirm with owner before coding

1. **SRE scope for iter-2c: ship without shell allowlist?** The full
   `curl`/`promtool`/`journalctl` set is meaningful only on the iter-5
   server. Proposal: ship `Read`/`Glob`/`Grep`/`WebFetch` + path-scoped
   write only this iteration. **Default: yes, defer shell to iter-5.**
2. **Frontend path scope: ai_team's `apps/web,apps/cli` only this
   iteration?** Target-repo frontend trees are configurable per-task
   via `AI_TEAM_PATH_PREFIXES` env override (same as Backend's
   denylist). **Default: yes — no second env var.**
3. **TL anti-loop guard: summary-string check vs. message-metadata
   counter?** Summary-string is simpler and ships now; metadata
   counter is cleaner but adds an `AgentMessage` schema bump.
   **Default: summary-string check; revisit if it bites in iter-3.**

If owner accepts these defaults, the plan is approved. Otherwise we
adjust and re-surface.

## Sequencing (one commit = one squash-merge PR)

```
[iter-2c: Phase 1]
  c1  docs(iter-2c): plan
  c2  docs(iter-2): real-LLM e2e demo report (← gates on running it)

[iter-2c: Phase 2]
  c3  feat(frontend): agent + prompt + tests
  c4  feat(api): register Frontend agent in dispatcher

[iter-2c: Phase 3]
  c5  feat(sre): agent + prompt + tests
  c6  feat(api): register SRE agent in dispatcher

[iter-2c: Phase 4]
  c7  feat(tl): route BLOCKED task reports to the indicated role
  c8  feat(devops,frontend): populate blocked_on on BLOCKED reports

[iter-2c: close]
  c9  docs(iter-2c): retro + iter-3 handoff
```

c2 and c1 can flip order if the demo is run *before* the plan lands
on `main` — in practice we'll commit the plan first, run the demo
on the same branch, then commit the report. Either order is fine.

## What I will NOT do without asking

- Add any new framework dependency (LangGraph, CrewAI, OpenAI SDK,
  AgentSDK with API key) — ADR-001 / ADR-008 forbid.
- Lower diff-cover gate below 80%.
- Force-push, drop DB, or skip hooks.
- Wire SRE shell tools (`curl`/`promtool`/`journalctl`) before the
  iter-5 server exists.
- Add Playwright / browser-driven tests for Frontend (deferred — see
  non-goals).
- Bump `AgentMessage` schema for a routing counter (Phase-4 anti-loop
  guard uses summary-string check instead).
- Touch `core/audit/`, `core/security/`, or `core/persistence/` for
  reasons unrelated to the items above.

## Current task

Phase 1 step **1A** — pre-flight checks before running the real-LLM
e2e demo (.env, `docker`, `gh auth status`, `claude` auth, free
quota ≥ 30%). After owner approves this plan.
