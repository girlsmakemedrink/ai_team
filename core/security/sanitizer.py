"""Untrusted-input sanitiser. See ADR-005."""

from __future__ import annotations

_OPEN = "<UNTRUSTED_INPUT>"
_CLOSE = "</UNTRUSTED_INPUT>"

# What we substitute for occurrences of the closing tag *inside* the
# untrusted content, so the model can't be tricked into "closing" the
# marker early.
_CLOSE_ESCAPE = "<​/UNTRUSTED_INPUT>"
_OPEN_ESCAPE = "<​UNTRUSTED_INPUT>"


def wrap_untrusted(text: str) -> str:
    """Wrap arbitrary external text so the model treats it as data.

    Idempotency: wrapping an already-wrapped string yields the same string
    (we detect the leading/trailing markers). This lets the function be
    called defensively at multiple layers without compounding.

    Marker injection inside the input is neutralised by inserting a
    zero-width space inside the angle brackets — invisible to humans,
    breaks the tag for the parser.
    """
    if text.startswith(_OPEN) and text.endswith(_CLOSE):
        # Already wrapped; trust that the inner content was sanitised
        # at the point of wrapping.
        return text

    # Escape any attempt to close the marker prematurely or open a new one.
    safe = text.replace(_CLOSE, _CLOSE_ESCAPE).replace(_OPEN, _OPEN_ESCAPE)
    return f"{_OPEN}{safe}{_CLOSE}"


def is_wrapped(text: str) -> bool:
    return text.startswith(_OPEN) and text.endswith(_CLOSE)
