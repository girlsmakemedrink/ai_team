"""Sanitizer — strips and wraps untrusted text. See ADR-0018/0021."""
from __future__ import annotations

import re

_OPEN = "<UNTRUSTED_INPUT>"
_CLOSE = "</UNTRUSTED_INPUT>"
_MARKER_STORM_LIMIT = 16


def sanitize(text: str) -> str:
    """Strip literal marker substrings (case-insensitive), then wrap in markers.

    Idempotent: if text is already a properly formed wrapped string, return as-is.
    """
    if text.startswith(_OPEN) and text.endswith(_CLOSE):
        return text
    cleaned = re.sub(re.escape(_OPEN), "", text, flags=re.IGNORECASE)
    cleaned = re.sub(re.escape(_CLOSE), "", cleaned, flags=re.IGNORECASE)
    return f"{_OPEN}\n{cleaned}\n{_CLOSE}"


def marker_storm(text: str) -> bool:
    """Return True when the idea text contains suspiciously many marker literals."""
    return text.lower().count(_OPEN.lower()) > _MARKER_STORM_LIMIT


# Backward-compatible alias used by existing stage modules.
wrap_untrusted = sanitize
