# Iteration 1 — Retrospective

**Closed**: 2026-05-18. PR #2 merged. End-to-end demo against real `claude -p`
succeeded after two hotfixes (PR #3): Opus + Sonnet produced 7 testable user
stories for the idea-validator spec in ~25 s wall-time.

## What we shipped

- TL (Opus) decomposes a user task_assignment into sub-`task_assignment`s
  using `--json-schema`. PM (Sonnet) emits user stories with acceptance
  criteria using `--json-schema`.
- Dispatcher loop with HMAC verification, prev_hash audit chain, Postgres
  feed_events sink, cancellation-safe shutdown.
- Live API: POST /api/tasks publishes to TL stream; /api/reviews,
  /api/digest, /api/digest/history hit real DB.
- CLI: `ai-team digest [--history]` against real endpoints; past-tense
  status from API.
- Testcontainers integration suite (audit chain + feed persistence +
  dispatcher e2e + live API).
- All 4 iter-0 retro carry-overs closed (feed sink / testcontainers /
  --json-schema / max_budget_usd).
- CI diff-cover gate raised back to 80 % (82 % local, 80+ in CI).

## What went well

- The dispatcher + audit chain integration test caught two bugs that
  unit tests couldn't have. testcontainers paid for itself on day one.
- `--json-schema` made TL's decomposition output reliable in JSON shape;
  parse failures dropped to zero on the e2e demo.
- Per-tier `max_budget_usd` defaults caught nothing yet, but a real
  runaway agent would now bounce off it (good defence in depth).
- ADR-008 substrate (validated in iter-0 smoke) held up under real
  multi-agent traffic — concurrent claude -p invocations, --session-id
  reuse, large-prompt Opus calls all worked.

## What didn't

- **Two real-LLM bugs only surfaced when running the actual demo**:
  1. `--json-schema` puts the validated JSON in
     `structured_output`, not in `result`. Our parser read `result`
     and got natural-language text. TL fail-reported every time.
  2. We were passing our `correlation_id` as `--resume <id>`, but
     `--resume` requires an existing claude session. Should have been
     `--session-id <id>` (create-or-reuse). PM crashed on every first
     call. Both fixed by PR #3.
- The integration test using `ScriptedLLM` bypassed these bugs because
  the scripted client doesn't go through `claude -p`. Action: also run
  the full demo manually (or in CI with a self-hosted runner) before
  calling an iteration done — the smoke step in iter-0 had the right
  spirit, expand it.
- CI flaked twice on ruff format check after auto-applied formats by
  my local. Lesson: always run `make format` + `make lint` + `make test`
  before pushing. Adding a pre-push git hook is cheap and will save
  future cycles.

## Surprises

- Opus produced 595 output tokens (~4 cents) for the decomposition in
  ~12 s — well under budget.
- PM with `--session-id` (created on first call) and `--json-schema`
  produced 7 stories with consistent ID numbering, testable criteria,
  shell-level acceptance specs, even noting "Story count is within
  range; no decomposition flag needed". Quality matched what a careful
  human PM would write.

## Prompt-tuning notes (for Iteration 2)

- The PM system prompt's "respond with JSON only" clause works well —
  no extra prose. Keep this discipline for Architect / Backend.
- Add a "Reference the source spec by file path" line to PM so artifact
  links point back to `docs/sandbox/...` when applicable.
- TL prompt produced very clean decomposition. No tuning needed yet.

## Decisions to revisit

- **Session caching**: `--session-id` works but doesn't give us the
  same cache hits we saw in iter-0 smoke (--resume on the *same*
  session). Re-test caching savings under the new scheme.
- **Schema validation in ClaudeCodeHeadlessClient**: store whether
  the response matched the schema (already present as
  `structured_output`); add a `validated_against_schema: bool` to
  `LLMResponse` and surface it.

## Action items for Iteration 2

- [ ] Add a manual `make demo` step to the pre-merge checklist (or
      a `--real-llm` smoke that runs the full TL→PM cycle in CI).
- [ ] Test the cache-hit ratio of `--session-id` over multiple turns.
- [ ] Bring Architect + Backend + QA online; full code-writing cycle
      against `idea-validator` sandbox.
- [ ] Tighten Backend's Bash allowlist when MCP servers wire up (ADR-004).
- [ ] Add a pre-push git hook (lint+format+test) per the CI flake
      observation.
