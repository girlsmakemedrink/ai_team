#!/usr/bin/env bash
# iter-28 smoke: clone girlsmakemedrink/telegram-tech-publisher via
# GitHubTargetRepo, then run status() / run_linter() / run_tests().
# Does not push. Prints all three results.

set -euo pipefail

cd "$(dirname "$0")/.."

# `gh auth status` must pass — clone uses SSH but we also need gh for any
# follow-up open_pr() (not exercised here, but the smoke validates the
# auth substrate).
if ! gh auth status >/dev/null 2>&1; then
  echo "ERROR: gh auth status failed. Run 'gh auth login' first." >&2
  exit 1
fi

uv run python -c "
import asyncio
from core.target_repo.github import GitHubTargetRepo


async def main() -> None:
    repo = GitHubTargetRepo('girlsmakemedrink/telegram-tech-publisher')
    print(f'workspace: {repo.root}')
    root = await repo.ensure_local_clone()
    print(f'cloned/fetched at: {root}')
    st = await repo.status()
    print(f'status: branch={st.branch} dirty={st.is_dirty} untracked={len(st.untracked_files)}')
    lint = await repo.run_linter()
    print(f'linter: passed={lint.passed} issues={lint.issues_count} -- {lint.summary}')
    # Use uv run pytest since the product repo is uv-managed.
    tests = await repo.run_tests('uv run pytest -q')
    print(f'tests: passed={tests.passed} duration={tests.duration_s}s -- {tests.summary}')


asyncio.run(main())
"
