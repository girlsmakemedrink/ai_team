"""Unit tests for pure status-derivation helpers in core.persistence.task_state.

The DB-side TaskStateReducer is covered in
tests/integration/test_task_state_reducer.py.
"""

from __future__ import annotations

from core.persistence.task_state import (
    TERMINAL_STATUSES,
    derive_parent_status,
    is_terminal,
)


def test_terminal_statuses_includes_done_and_failed() -> None:
    assert "done" in TERMINAL_STATUSES
    assert "failed" in TERMINAL_STATUSES
    assert "in_progress" not in TERMINAL_STATUSES
    assert "pending" not in TERMINAL_STATUSES
    assert "blocked" not in TERMINAL_STATUSES


def test_is_terminal() -> None:
    assert is_terminal("done") is True
    assert is_terminal("failed") is True
    assert is_terminal("in_progress") is False
    assert is_terminal("pending") is False
    assert is_terminal("blocked") is False
    assert is_terminal("anything_else") is False


def test_derive_parent_status_returns_none_when_no_children() -> None:
    assert derive_parent_status([]) is None


def test_derive_parent_status_returns_none_when_any_child_pending() -> None:
    assert derive_parent_status(["in_progress", "done"]) is None
    assert derive_parent_status(["pending"]) is None
    assert derive_parent_status(["blocked", "done"]) is None


def test_derive_parent_status_done_when_all_children_done() -> None:
    assert derive_parent_status(["done"]) == "done"
    assert derive_parent_status(["done", "done", "done"]) == "done"


def test_derive_parent_status_failed_when_any_child_failed() -> None:
    """Any child FAILED dominates — the parent fails even if other children are done."""
    assert derive_parent_status(["done", "failed"]) == "failed"
    assert derive_parent_status(["failed", "done", "done"]) == "failed"
    assert derive_parent_status(["failed"]) == "failed"


def test_derive_parent_status_failed_dominates_pending() -> None:
    """A failed child terminates the parent immediately — siblings still
    in progress can't recover the root."""
    assert derive_parent_status(["failed", "in_progress"]) == "failed"
    assert derive_parent_status(["in_progress", "failed", "pending"]) == "failed"
