"""Central orchestration package.

See ADR-001. Re-exports `AgentDispatcher` from `dispatcher.py` so the
historical `from core.dispatcher import AgentDispatcher` import path
keeps working after the iter-3 package split.
"""

from core.dispatcher.dispatcher import AgentDispatcher
from core.dispatcher.hold_queue import HoldQueue

__all__ = ["AgentDispatcher", "HoldQueue"]
