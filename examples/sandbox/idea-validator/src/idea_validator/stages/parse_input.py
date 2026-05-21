"""Stage 1: parse and normalise the raw idea string."""
from __future__ import annotations

import re
from datetime import datetime, timezone

from idea_validator.models import IdeaInput

_SLUG_RE = re.compile(r"[^a-z0-9-]+")


def run(
    idea: str,
    depth: str = "standard",
    frozen_timestamp: datetime | None = None,
) -> IdeaInput:
    ts = frozen_timestamp or datetime.now(timezone.utc)
    slug = _SLUG_RE.sub("-", idea.lower()).strip("-")[:40]
    return IdeaInput(idea=idea, depth=depth, created_at=ts.isoformat(), slug=slug)
