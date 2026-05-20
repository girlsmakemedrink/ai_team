"""Backend agent must forward disallowed_tools=('Bash',) to claude -p.

iter-11 Phase 2. iter-10 demo Backend's task_report still mentioned
'Bash hooks blocked the pytest command' despite the prompt edit.
Defense in depth: tell claude -p explicitly to refuse Bash via
--disallowed-tools, on top of leaving Bash out of --allowed-tools.

The dispatcher's _invoke_with_retries already forwards
`disallowed_tools` to LLMClient.invoke(), which forwards to
`claude -p --disallowed-tools Bash` (see
core/llm/claude_code_headless.py:146-147). So flipping the
ClassVar is sufficient.
"""

from __future__ import annotations

from agents.backend_developer.agent import BackendDeveloperAgent


def test_backend_declares_bash_disallowed() -> None:
    assert "Bash" in BackendDeveloperAgent.disallowed_tools


def test_backend_disallowed_tools_is_tuple() -> None:
    # ClassVar default in BaseAgent is `tuple[str, ...]`; preserve shape.
    assert isinstance(BackendDeveloperAgent.disallowed_tools, tuple)
