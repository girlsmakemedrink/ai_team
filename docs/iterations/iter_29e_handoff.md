# Iter-29e Handoff (stub) — multi-role chain exercise

> **Status:** stub. Populated by iter-29e itself. iter-29d landed three pre-flight items the iter-29e spec relies on; this stub records them so the spec doesn't have to re-discover them.

## Preflight (from iter-29d)

- **Workspace cleanup hook:** `TargetRepo.prepare_for_task()` runs before every cross-repo task assignment. `GitHubTargetRepo` resets the workspace to a clean `main` (fetch + dirty-check + checkout + ff-only merge). Dirty workspaces and diverged local mains raise — owner intervenes; nothing is destructively reset.
- **Dev-deps install:** `uv sync --extra dev --all-groups` in any repo with PEP 621 dev extras. `uv sync` alone skips those.
- **Gate-wiring design rule** (from iter-29d Addendum A): `pending_reviews` are produced by QA Engineer only. Chains that skip QA legitimately skip the review record.

## Goal (placeholder, owner to refine)

Submit a task that forces TL to decompose across roles (Architect + Backend + QA), validating the multi-role chain end-to-end. Quota budget: TBD by iter-29e spec.

## Open items inherited from iter-29c/29b carry-overs

See `docs/iterations/iter_29c_handoff.md` §5 and `docs/iterations/iter_29b.md` for the standing list. None addressed in iter-29d.
