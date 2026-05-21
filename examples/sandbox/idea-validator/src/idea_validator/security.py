"""Sanitization helpers (ADR-0018, ADR-0019 US-6)."""
from __future__ import annotations

_OPEN = "<UNTRUSTED_INPUT>"
_CLOSE = "</UNTRUSTED_INPUT>"
_STORM_LIMIT = 16


def sanitize(text: str) -> str:
    """Wrap text in UNTRUSTED_INPUT markers, stripping existing markers first.

    Raises ValueError if the input contains more than _STORM_LIMIT marker occurrences
    (ADR-0021 code 22 — marker storm defence).
    """
    if text.lower().count("<untrusted_input>") > _STORM_LIMIT:
        raise ValueError("idea text contains marker storm; refusing to sanitize")
    cleaned = text
    for m in (_OPEN, _CLOSE, _OPEN.lower(), _CLOSE.lower()):
        cleaned = cleaned.replace(m, "")
    return f"{_OPEN}\n{cleaned}\n{_CLOSE}"
