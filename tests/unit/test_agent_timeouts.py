"""Pin per-agent llm_timeout_s values. iter-11 Phase 3.

iter-3..10 had BaseAgent default = 300 with 5 subclasses overriding
to 600. iter-11 flips the default to 600 (the LLM-bound majority)
and lets the four agents that still need 300 declare it explicitly.

Net behavior change: zero — every agent's effective value is held
constant. This module is the safety net: a future change to one of
these values should be deliberate, and CI catches the typo where
someone deletes an explicit 300 thinking it was redundant.
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


@pytest.mark.parametrize(
    ("cls", "expected"),
    [
        (BaseAgent, 600),
        (ArchitectAgent, 600),
        (BackendDeveloperAgent, 600),
        (DesignerAgent, 600),
        (DevOpsAgent, 600),
        (FrontendDeveloperAgent, 600),
        (QAEngineerAgent, 300),
        (MarketResearcherAgent, 300),
        (ProductManagerAgent, 600),
        (SRESupportAgent, 300),
        (TeamLeadAgent, 300),
    ],
)
def test_llm_timeout_s(cls: type[BaseAgent], expected: int) -> None:
    assert cls.llm_timeout_s == expected
