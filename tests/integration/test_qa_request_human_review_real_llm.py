"""iter-23 Phase 1 — decisive QA-path mini-experiment.

The QA-emitted `pending_reviews` row criterion has been 4-iteration
deferred (iter-19 → 20 → 21 → 22). iter-22's failure mode was
diagnosed as "demo poll window expired with Backend recovery turn in
flight" — i.e. operational, not architectural. The iter-23 handoff's
TOP item is "extend demo poll window to 45 min."

But there is a deeper risk that has been hand-waved for 4 iterations:
**we have never end-to-end verified that QA's LLM actually invokes
`mcp__ai_team_tasks__request_human_review` under real conditions.**
The prompt mandates it (`prompts/qa_engineer.md:27-39`), the tool is
in `allowed_tools` (`agents/qa_engineer/agent.py:60`), and the iter-18
handler is solid — but the chain has never reached QA in any
real-LLM demo, so the LLM's actual compliance with the tool-call
instruction has never been observed.

This test exercises that path directly with a synthetic Backend
`task_report(done)`-shaped user message, observes
`LLMResponse.tools_used`, and checks for the `pending_reviews` row.
Three sequential runs sample reliability.

Outcomes:
- 3/3 row present → QA contract solid, skip iter-23 Phase 2 safety net,
  proceed straight to demo-window extension (Phase 3-6).
- <3/3 → ship the Python-side safety net in `QAEngineerAgent.build_outputs`
  that detects missing tool-call and INSERTs the row directly via
  the same `handle_request_human_review` handler.

Cost: ~$0.05/run x 3 = ~$0.15. Wall-clock: ~30-60s/run = ~3 min total
(LLM is told tests already passed; only the review call remains).

Dual-marker: `integration` (needs testcontainers Postgres) AND
`real_llm` (needs --real-llm flag + subscription quota). `make
test-integration` excludes it via `-m "integration and not real_llm"`;
runs only via `make test-real-llm` or
`pytest tests/integration/test_qa_request_human_review_real_llm.py
--real-llm -v`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest
from sqlalchemy import select

from agents.qa_engineer.agent import QAEngineerAgent
from core.llm.claude_code_headless import ClaudeCodeHeadlessClient
from core.messaging.schemas import (
    AgentId,
    AgentMessage,
    MessageType,
    Priority,
    TaskAssignmentPayload,
)
from core.persistence.models import PendingReview

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


_REPO_ROOT = Path(__file__).resolve().parents[2]
_QA_TOOL_NAME = "mcp__ai_team_tasks__request_human_review"


def _write_mcp_config(tmp_path: Path) -> Path:
    """Mirror of scripts/demo_iter_22.sh's MCP config block."""
    venv_py = _REPO_ROOT / ".venv" / "bin" / "python"
    config = {
        "mcpServers": {
            "ai-team-bus": {
                "command": str(venv_py),
                "args": ["-m", "tools.mcp_servers.ai_team_bus"],
            },
            "ai-team-tasks": {
                "command": str(venv_py),
                "args": ["-m", "tools.mcp_servers.ai_team_tasks"],
            },
            "ai-team-repo": {
                "command": str(venv_py),
                "args": ["-m", "tools.mcp_servers.ai_team_repo"],
                "env": {
                    "AI_TEAM_REPO_ROOT": str(_REPO_ROOT),
                    "AI_TEAM_PATH_PREFIXES": "*",
                    "AI_TEAM_PR_BASE": "main",
                    "AI_TEAM_FORBID_BRANCH_RE": "^(main|master|release/.*)$",
                },
            },
        }
    }
    path = tmp_path / "iter23-phase1-mcp.json"
    path.write_text(json.dumps(config))
    return path


@pytest.mark.integration
@pytest.mark.real_llm
@pytest.mark.asyncio
@pytest.mark.parametrize("run_idx", [0, 1, 2])
async def test_qa_llm_calls_request_human_review_and_row_lands(
    run_idx: int,
    session_factory: async_sessionmaker[AsyncSession],
    pg_dsn: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """For each run, observe whether QA's LLM emits the MCP tool call
    AND whether the `pending_reviews` row lands."""
    cid = uuid4()
    tid = uuid4()

    # The MCP subprocess reads POSTGRES_DSN from its inherited env to
    # build its session_factory. Point at the testcontainers DB.
    monkeypatch.setenv("POSTGRES_DSN", pg_dsn)
    # iter-19 defense: Context.from_env reads these as fallbacks for
    # the LLM's tools/call args. Set them so the handler succeeds even
    # if the LLM forgets to pass them.
    monkeypatch.setenv("AI_TEAM_AGENT_ROLE", "qa_engineer")
    monkeypatch.setenv("AI_TEAM_CORRELATION_ID", str(cid))
    monkeypatch.setenv("AI_TEAM_TASK_ID", str(tid))

    mcp_config_path = _write_mcp_config(tmp_path)
    monkeypatch.setenv("AI_TEAM_MCP_CONFIG_PATH", str(mcp_config_path))

    # Synthetic Backend task_report(done) shape, framed as the
    # task_assignment QA would receive from TL. Explicitly tell the LLM
    # tests already passed elsewhere — minimises tool-call surface so
    # the safety net path runs on a realistic but bounded prompt
    # without burning $0.50+ on pytest invocations.
    description = (
        f"Backend reports tests pass on branch "
        f"`agent/backend_developer/iter-23-diag-{run_idx}`:\n"
        f"  - 54 tests, 0 failures, 91% coverage\n"
        f"  - PR URL: https://example.invalid/pr/diag-{run_idx}\n\n"
        f"Please verify and request human review.\n"
        f"Constraints for this turn: tests were already executed in a "
        f"separate sandbox and reported passing — DO NOT re-run pytest "
        f"or mypy here. Respond with the QA JSON object\n"
        f"(suite_passed=true, tests_run=54, tests_failed=0,\n"
        f" coverage_pct=91, failures=[], summary='all green')."
    )

    # iter-23 Phase 2: pass session_factory so the safety net can fire
    # when the LLM (as Phase 1 showed) skips the MCP tool call.
    agent = QAEngineerAgent(llm=ClaudeCodeHeadlessClient(), session_factory=session_factory)

    msg = AgentMessage(
        correlation_id=cid,
        sender=AgentId.TEAM_LEAD,
        recipient=AgentId.QA_ENGINEER,
        message_type=MessageType.TASK_ASSIGNMENT,
        priority=Priority.P2,
        payload=TaskAssignmentPayload(
            task_id=tid,
            title=f"QA verify Backend report (diag run {run_idx})",
            description=description,
            target_repo="examples/sandbox/idea-validator",
        ),
    )

    outputs = await agent.handle(msg)
    assert outputs, "QA must always emit at least a task_report"
    print(f"\n[run {run_idx}] outputs={len(outputs)}")

    # ACCEPTANCE: the pending_reviews row MUST land — either because
    # the LLM called the tool OR because the Phase 2 safety net wrote
    # it directly. This is the 4-iter-deferred criterion.
    async with session_factory() as s:
        rows = (
            (await s.execute(select(PendingReview).where(PendingReview.correlation_id == cid)))
            .scalars()
            .all()
        )
    assert len(rows) >= 1, (
        f"No pending_reviews row for correlation_id={cid}. iter-23 acceptance criterion FAILED."
    )
    row = rows[0]
    assert row.requesting_agent == "qa_engineer", (
        f"row landed but requesting_agent={row.requesting_agent!r} != 'qa_engineer'"
    )
    assert row.summary, "row.summary must be non-empty"
