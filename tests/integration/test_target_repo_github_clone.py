"""Integration test: real clone of the product repo + status() probe.

Marked `@pytest.mark.integration` — skipped in the default unit run.
Requires `gh auth status` and network access to GitHub. Clones into a tmp
workspace so it doesn't touch `~/.ai_team/workspaces/`.
"""

from __future__ import annotations

import shutil
import subprocess
from typing import TYPE_CHECKING

import pytest

from core.target_repo.github import GitHubTargetRepo

if TYPE_CHECKING:
    from pathlib import Path


def _gh_authed() -> bool:
    try:
        result = subprocess.run(
            ["gh", "auth", "status"],
            capture_output=True,
            check=False,
        )
    except FileNotFoundError:
        return False
    return result.returncode == 0


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not _gh_authed(), reason="requires `gh auth login`"),
    pytest.mark.skipif(shutil.which("git") is None, reason="requires git"),
]


@pytest.mark.asyncio
async def test_clone_and_status_against_real_product_repo(tmp_path: Path) -> None:
    repo = GitHubTargetRepo("girlsmakemedrink/telegram-tech-publisher", workspaces_dir=tmp_path)
    root = await repo.ensure_local_clone()
    assert root.is_dir()
    assert (root / ".git").is_dir()
    assert (root / "pyproject.toml").is_file()
    st = await repo.status()
    assert st.branch == "main"
    assert st.is_dirty is False
