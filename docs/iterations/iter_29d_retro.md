# Iter-29d Retro — pre-flight bundle

**Status:** shipped <DATE>.

## Numbers

| Metric | Value |
|---|---|
| Files touched | ~11 |
| LLM invocations | 0 (no `claude -p` run in this iter) |
| Quota burn | $0.00 |
| New tests | <unit + integration count> |

## What shipped

- `TargetRepo.prepare_for_task()` workspace cleanup hook (default no-op on the ABC, real impl in `GitHubTargetRepo`).
- Dispatcher wires the hook between `ensure_local_clone()` and the workspace metadata stash.
- Integration test against a local bare repo (no network, no GitHub).
- Gate-wiring audit: `pending_reviews` confirmed QA-only-by-design (see `iter_29d.md` Addendum A).
- `CLAUDE.md` carries the uv dev-extras gotcha and the pending_reviews design rule.
- `iter_29e_handoff.md` stub with the three preflight items.

## Surprises

<populate from impl — anything unexpected from the audit or the integration test>

## Architectural follow-ups (defer to iter-29e+)

Unchanged from iter-29c handoff §5 + iter-29b carry-overs.

## Closure

iter-29d is shipped. The substrate is ready for iter-29e's multi-role chain exercise.
