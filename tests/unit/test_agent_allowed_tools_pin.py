"""iter-19 Phase 3: pin every concrete agent's
allowed_tools to a non-empty whitelist.

iter-18 demo Caveat 1 surfaced this: PM and TL both
declared `allowed_tools = ()` which
`core/llm/claude_code_headless.py:199-200` translates
to OMITTING the --allowed-tools flag entirely.
claude -p's default in that mode is permissive (all
configured MCP + native tools allowed). PM
unprompted-called the new
mcp__ai_team_tasks__request_human_review tool during
the iter-18 demo as a result.

This pin is the safety net. A future change that
removes an explicit whitelist by mistake is caught
here at CI time rather than in the next demo run.
"""

from __future__ import annotations

import pytest

from agents._base.agent import BaseAgent
from agents.architect import ArchitectAgent
from agents.backend_developer import BackendDeveloperAgent
from agents.designer import DesignerAgent
from agents.devops import DevOpsAgent
from agents.frontend_developer import FrontendDeveloperAgent
from agents.market_researcher import MarketResearcherAgent
from agents.product_manager import ProductManagerAgent
from agents.qa_engineer import QAEngineerAgent
from agents.sre_support import SRESupportAgent
from agents.team_lead import TeamLeadAgent

# Note: BaseAgent itself keeps `allowed_tools = ()` as the class
# default — concrete agents must override. The pin below iterates
# concrete agents only.
_CONCRETE_AGENTS: list[type[BaseAgent]] = [
    ArchitectAgent,
    BackendDeveloperAgent,
    DesignerAgent,
    DevOpsAgent,
    FrontendDeveloperAgent,
    MarketResearcherAgent,
    ProductManagerAgent,
    QAEngineerAgent,
    SRESupportAgent,
    TeamLeadAgent,
]


@pytest.mark.parametrize("cls", _CONCRETE_AGENTS)
def test_allowed_tools_is_non_empty(cls: type[BaseAgent]) -> None:
    """Empty allowed_tools triggers claude -p's
    permissive default. iter-18 Caveat 1."""
    assert cls.allowed_tools, (
        f"{cls.__name__}.allowed_tools is empty — would trigger "
        f"claude -p permissive default. See "
        f"iter_18_demo_report.md Caveat 1."
    )


@pytest.mark.parametrize("cls", [ProductManagerAgent, TeamLeadAgent])
def test_pm_and_tl_exclude_request_human_review(
    cls: type[BaseAgent],
) -> None:
    """PM/TL should not be able to surprise-call
    request_human_review. iter-18 demo run #2 wrote
    a row via PM unprompted; the iter-19 fix forbids
    that path."""
    assert (
        "mcp__ai_team_tasks__request_human_review"
        not in cls.allowed_tools
    ), (
        f"{cls.__name__} can still call request_human_review — "
        f"iter-18 leak not closed"
    )
