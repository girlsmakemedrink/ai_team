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


# === iter-6 Phase 3: TaskStateReducer.on_drop signature ===


async def test_on_drop_returns_immediately_on_empty_list() -> None:
    """The dispatcher passes an empty list when HoldQueue dropped no
    messages (i.e. predecessor failed but had no dependents). on_drop
    must early-return without opening a session — a fake session
    factory whose call would raise proves we never hit the DB path."""
    from unittest.mock import Mock

    from core.persistence.task_state import TaskStateReducer

    def _raise_on_call() -> None:
        raise AssertionError("on_drop must early-return on empty list")

    reducer = TaskStateReducer(session_factory=Mock(side_effect=_raise_on_call))
    await reducer.on_drop([])  # would raise if session_factory got called


def test_on_drop_is_async_method_on_reducer() -> None:
    """Sanity: TaskStateReducer.on_drop exists as an async method that
    accepts a list[UUID] of dropped child task ids. Full DB-side
    behaviour is covered in tests/integration/test_dispatcher_e2e.py
    (the three-stage dependency test was extended to exercise the
    failed-predecessor → dropped-dependent → rolled-up path).
    See iter_5_demo_report.md Failure 3 and iter_6.md Phase 3."""
    import inspect

    from core.persistence.task_state import TaskStateReducer

    method = inspect.getattr_static(TaskStateReducer, "on_drop")
    assert inspect.iscoroutinefunction(method), "TaskStateReducer.on_drop must be `async def`"
    sig = inspect.signature(method)
    # Param names: self, task_ids (single positional after self).
    params = list(sig.parameters.values())
    assert params[0].name == "self"
    assert params[1].name == "task_ids", (
        f"expected (self, task_ids), got {[p.name for p in params]}"
    )
