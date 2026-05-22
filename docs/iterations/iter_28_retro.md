# Iteration 28 retro

> Read **after** `CLAUDE.md`, `docs/iterations/iter_28.md`, and
> `docs/iterations/iter_27_handoff.md`.

## Outcome (2026-05-22 EOD)

iter-28 shipped per spec. `GitHubTargetRepo` is the third concrete
`TargetRepo` impl (per ADR-009), closing a carry-over that had been
deferred since iter-2. `make smoke-github-target-repo` clones
`girlsmakemedrink/telegram-tech-publisher` end-to-end and runs
`status / run_linter / run_tests` against it via the abstraction —
all three pass on the live product repo.

Three PRs landed in one sitting on 2026-05-22:

| PR  | Phase | Squash SHA  | What                                                       |
|-----|-------|-------------|------------------------------------------------------------|
| #41 | plan  | `78c644d`   | docs/iter-28-plan (spec)                                   |
| #42 | A     | `e713c2a`   | `GitHubTargetRepo` impl + 11 unit tests + registry wiring  |
| #43 | B     | `2fd595a`   | Live smoke + integration test (clone via `gh repo clone`)  |

This wrap PR adds the CLAUDE.md pointer, this retro, and the handoff to
iter-29.

### Verification

- `core/target_repo/github.py` (86 lines) — `GitHubTargetRepo` + `parse_github_identifier`.
- `tests/unit/test_target_repo_github.py` — 11 unit tests pass.
- `tests/unit/test_target_repo_registry.py` — 2 deferred-tests → success.
- `tests/integration/test_target_repo_github_clone.py` — real clone passes locally; CI-skipped by design (integration marker).
- Full unit suite: 538 pass, no regressions.
- `make smoke-github-target-repo` locally: clone, status, linter, tests — all green against the live product repo.

## What went well

- **Inherit-from-`SelfBootstrapTargetRepo` worked as designed.** Only
  two methods needed overriding (`__init__`, `ensure_local_clone`).
  `stage_and_commit`, `push`, `open_pr`, `run_tests`, `run_linter`, and
  `status` were reused as-is. The class-level `name = "ai_team"` on
  the parent had to be instance-overridden in `__init__` — minor leak,
  but caught by a unit test (`test_workspace_path_uses_double_dash_slug`)
  before the smoke ran.
- **TDD on the parser + class pulled the design forward.** Writing the
  identifier-parser tests first surfaced the SSH-URL passthrough case
  that the plan's regex hadn't initially handled; fixed before any
  consumer existed.
- **Lazy registry import — and then un-lazy.** The plan called for a
  lazy `from core.target_repo.github import GitHubTargetRepo` inside
  the matching branch to avoid `Path.home()` at registry import time.
  Once `__init__.py` re-exported `GitHubTargetRepo` eagerly, the
  laziness became dead weight (and ruff `PLC0415` flagged it). Removed
  the inside-function import; clean.
- **Integration test gate worked.** `pytestmark` with two
  `pytest.mark.skipif`s (`gh auth`, `git`) made the integration test
  self-describing — it ran locally, skipped cleanly anywhere it
  shouldn't.

## What was harder than expected

- **SSH-key assumption was wrong.** Phase A coded the clone as
  `git clone <ssh_url>` per the plan. First live smoke ran into
  `Permission denied (publickey)` — the owner's gh auth is HTTPS,
  no SSH key on GitHub. The plan listed this exact failure as
  "Risk 1" with mitigation "owner adds SSH key", but in practice
  pivoting to `gh repo clone <owner>/<repo>` was a 5-line change
  with no setup cost and one fewer auth substrate. The retro lesson
  is upstream: **don't pick the auth substrate from `iter_28.md`
  alone — check `gh auth status` and the owner's existing protocol
  config before locking the design.**
- **CI ruff config differs from local `uv run ruff check`.** First
  Phase A push failed CI on `ruff format --check` even though local
  `ruff check core/target_repo/github.py …` was clean. Lesson: when
  the CI step is `ruff format --check .` (whole-tree, format mode),
  the matching local command is `uv run ruff format --check .`, not
  `uv run ruff check <files>`. Same again for `mypy .` (whole-tree)
  vs `mypy <file>` — caught a `_Call | None` union-attr error in the
  test that the file-scoped mypy let through. Both ate one CI cycle
  each. Cheap, but avoidable next time.
- **Pre-existing dispatcher cascade test is flaky.** PR #42 first CI
  run failed `test_transitive_drops_cascade_through_hold_queue`
  (HoldQueue cascade — `'in_progress' != 'failed'`). Passed locally
  on retry and re-ran clean in CI. Not in the iter-28 diff; same
  test had been flagged in the iter-26b carry-over list (HoldQueue
  Postgres persistence area). Re-running on flake is fine for now,
  but worth flagging in iter-29 priorities.
- **`_run` private-import coupling.** `github.py` imports `_run` from
  `self_bootstrap.py` (leading-underscore by convention is private).
  Worked, and the test patch (`patch("core.target_repo.github._run")`)
  is clean because the symbol re-binds onto the github module. But
  the `_` is a soft warning that this helper should be promoted to
  a module-level `core/target_repo/_subprocess.py` when a third
  impl reuses it. Adding to iter-29 P3.

## Lessons for iter-29

- **Always check `gh auth status` + protocol config when designing
  external-repo plumbing.** Encode in the plan's "Hard constraints"
  section, not as a risk mitigation.
- **Run `make lint format-check typecheck` (whole-tree) locally
  before pushing, not just file-scoped variants.** Add to the
  Phase-{A,B,C} checklist in future iter plans.
- **Workspace path slug works.** `<owner>--<repo>` survived contact
  with real paths; `~/.ai_team/workspaces/girlsmakemedrink--telegram-tech-publisher/`
  cloned and probed without surprises. Keep the convention.
- **`uv run pytest` from a subprocess context works.** The smoke
  script passed `command='uv run pytest -q'` into `run_tests`; the
  product repo's deps were already synced (`uv` recognised the lockfile
  inside the cloned dir without intervention). No PATH or env-var
  gotchas. Note: if a fresh clone hadn't been previously `uv sync`-ed,
  this could surprise — leave the smoke informational rather than
  hard-fail on `run_tests` in iter-29.
- **`gh` is the right auth substrate.** Reusing the same `gh` CLI that
  `open_pr` already needs is one less moving part. Push (inherited
  `git push origin <branch>`) uses whatever `gh repo clone` set
  `origin` to — no extra config.

## Action items

1. **iter-29 P1**: first agent task against the product repo —
   TL → Backend → QA chain that adds a "Run smoke locally" section
   to `telegram-tech-publisher/README.md`. Low blast radius (docs only),
   full pipeline coverage. Detail in `iter_28_handoff.md`.
2. **iter-29 P2**: promote `_run` from `self_bootstrap.py` to
   `core/target_repo/_subprocess.py` (public module-level) before any
   fourth `TargetRepo` impl appears.
3. **iter-29 P3**: investigate `test_transitive_drops_cascade_through_hold_queue`
   flakiness — same pre-existing intermittent flagged in iter-26b
   carry-overs. Either stabilize or quarantine; don't keep re-running.
4. **iter-29 P3**: workspace GC (ADR-009 mention) — defer until a second
   external repo accumulates; manual `rm -rf ~/.ai_team/workspaces/<slug>`
   suffices for one.

## What iter-28 specifically did NOT do (re-stated)

- No agent invocations against the new repo (iter-29).
- No ADR changes; ADR-009 stands.
- No dispatcher, message-schema, or agent-code changes.
- No workspace GC, no PAT-based auth, no `core/config.py` settings.
- No closing of other iter-26/27 carry-overs.
- No product-repo `README.md` "Run smoke locally" section (iter-29 #1).
