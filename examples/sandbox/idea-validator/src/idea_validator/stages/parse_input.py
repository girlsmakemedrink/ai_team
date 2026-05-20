from __future__ import annotations
from datetime import datetime
from typing import Literal

from idea_validator.models import IdeaInput


def run(
    idea: str,
    depth: Literal["quick", "standard", "deep"] = "quick",
    created_at: datetime | None = None,
) -> IdeaInput:
    kwargs: dict = {"idea": idea.strip(), "depth": depth}
    if created_at is not None:
        kwargs["created_at"] = created_at
    return IdeaInput(**kwargs)
