"""Root conftest — ensures src/ is on sys.path for pytest."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))
