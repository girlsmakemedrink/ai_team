"""Redaction layer for team_feed publication. See ADR-007."""

from __future__ import annotations

import hashlib
import re
from typing import Any

_SENSITIVE_KEY = re.compile(
    r"(?i)(token|secret|password|api[_-]?key|authorization|credentials?|private[_-]?key)"
)
_TRUNCATE_AT = 2_000
_BLOB_THRESHOLD = 8_000  # chars; above this, replace with [BLOB:...] descriptor


def redact_for_feed(payload: Any) -> Any:
    """Recursively redact a payload for team_feed publication.

    Rules:
    - Keys matching the sensitive pattern → value replaced with "[REDACTED]".
    - String values > _BLOB_THRESHOLD chars → replaced with a descriptor
      "[BLOB:size=N,sha256=...]".
    - String values in (_TRUNCATE_AT, _BLOB_THRESHOLD] → truncated with marker.
    - All other values: unchanged structure.
    """
    if isinstance(payload, dict):
        return {k: _redact_value(k, v) for k, v in payload.items()}
    if isinstance(payload, list):
        return [redact_for_feed(item) for item in payload]
    if isinstance(payload, str):
        return _redact_string(payload)
    return payload


def _redact_value(key: str, value: Any) -> Any:
    if _SENSITIVE_KEY.search(key):
        return "[REDACTED]"
    return redact_for_feed(value)


def _redact_string(value: str) -> str:
    if len(value) > _BLOB_THRESHOLD:
        digest = hashlib.sha256(value.encode()).hexdigest()[:16]
        return f"[BLOB:size={len(value)},sha256={digest}]"
    if len(value) > _TRUNCATE_AT:
        return value[:_TRUNCATE_AT] + "…[TRUNCATED]"
    return value
