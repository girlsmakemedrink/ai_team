"""Dispatcher resolves payload.target_repo into a workspace path. iter-29c."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from core.dispatcher.dispatcher import AgentDispatcher
from core.messaging.schemas import (
    AgentId,
    AgentMessage,
    MessageType,
    Priority,
    TaskAssignmentPayload,
    TaskReportPayload,
    TaskStatus,
)

if TYPE_CHECKING:
    from pathlib import Path


def _make_dispatcher(ai_team_root: Path) -> AgentDispatcher:
    """Dispatcher with all collaborators stubbed — only exercises the
    new _maybe_resolve_target_repo_workspace path."""
    return AgentDispatcher(
        bus=AsyncMock(),
        feed=AsyncMock(),
        audit=AsyncMock(),
        signer=AsyncMock(),
        agents={},
        ai_team_root=ai_team_root,
    )


def _assignment(*, target_repo: str | None) -> AgentMessage:
    return AgentMessage(
        correlation_id=uuid4(),
        sender=AgentId.USER,
        recipient=AgentId.TEAM_LEAD,
        message_type=MessageType.TASK_ASSIGNMENT,
        priority=Priority.P2,
        payload=TaskAssignmentPayload(
            task_id=uuid4(),
            title="t",
            description="d",
            target_repo=target_repo,
        ),
    )


def _report() -> AgentMessage:
    return AgentMessage(
        correlation_id=uuid4(),
        sender=AgentId.BACKEND_DEVELOPER,
        recipient=AgentId.TEAM_LEAD,
        message_type=MessageType.TASK_REPORT,
        priority=Priority.P2,
        payload=TaskReportPayload(
            task_id=uuid4(),
            status=TaskStatus.DONE,
            progress_pct=100,
            summary="ok",
        ),
    )


async def test_resolves_and_stashes_workspace_for_assignment_with_target_repo(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()

    fake_repo = AsyncMock()
    fake_repo.ensure_local_clone = AsyncMock(return_value=workspace)

    dispatcher = _make_dispatcher(tmp_path)
    msg = _assignment(target_repo="owner/repo")

    with patch(
        "core.dispatcher.dispatcher.resolve_target_repo",
        return_value=fake_repo,
    ) as mock_resolve:
        await dispatcher._maybe_resolve_target_repo_workspace(msg)

    mock_resolve.assert_called_once_with("owner/repo", ai_team_root=tmp_path)
    assert msg.metadata.get("target_repo_workspace") == str(workspace)


async def test_skips_resolution_when_payload_target_repo_is_none(tmp_path: Path) -> None:
    dispatcher = _make_dispatcher(tmp_path)
    msg = _assignment(target_repo=None)

    with patch(
        "core.dispatcher.dispatcher.resolve_target_repo",
        side_effect=AssertionError("should not be called"),
    ):
        await dispatcher._maybe_resolve_target_repo_workspace(msg)

    assert "target_repo_workspace" not in msg.metadata


async def test_skips_resolution_for_non_assignment_messages(tmp_path: Path) -> None:
    dispatcher = _make_dispatcher(tmp_path)
    msg = _report()

    with patch(
        "core.dispatcher.dispatcher.resolve_target_repo",
        side_effect=AssertionError("should not be called"),
    ):
        await dispatcher._maybe_resolve_target_repo_workspace(msg)

    assert "target_repo_workspace" not in msg.metadata


async def test_resolution_failure_propagates_for_synthesise_catch(tmp_path: Path) -> None:
    """Bad identifier raises; the dispatcher's outer try/except in
    _handle_one will catch and route via _synthesise_failed_report.
    Confirm the exception escapes the resolver helper unchanged."""
    dispatcher = _make_dispatcher(tmp_path)
    msg = _assignment(target_repo="bad-shape")

    with (
        patch(
            "core.dispatcher.dispatcher.resolve_target_repo",
            side_effect=ValueError("unknown target_repo"),
        ),
        pytest.raises(ValueError, match="unknown target_repo"),
    ):
        await dispatcher._maybe_resolve_target_repo_workspace(msg)


async def test_clone_failure_propagates_for_synthesise_catch(tmp_path: Path) -> None:
    fake_repo = AsyncMock()
    fake_repo.ensure_local_clone = AsyncMock(side_effect=RuntimeError("git clone failed"))

    dispatcher = _make_dispatcher(tmp_path)
    msg = _assignment(target_repo="owner/repo")

    with (
        patch(
            "core.dispatcher.dispatcher.resolve_target_repo",
            return_value=fake_repo,
        ),
        pytest.raises(RuntimeError, match="git clone failed"),
    ):
        await dispatcher._maybe_resolve_target_repo_workspace(msg)
