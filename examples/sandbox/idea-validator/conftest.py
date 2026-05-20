"""Root conftest — injects src/ into sys.path for pytest invoked from repo root."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))
