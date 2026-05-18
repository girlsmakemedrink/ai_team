"""Structlog setup with correlation-id context."""

from __future__ import annotations

import logging
import sys
from contextvars import ContextVar, Token
from typing import Any
from uuid import UUID

import structlog

correlation_id_var: ContextVar[str | None] = ContextVar("correlation_id", default=None)


def configure_logging(level: str = "INFO") -> None:
    log_level = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=log_level)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            _add_correlation_id,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def _add_correlation_id(
    _logger: Any, _name: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    cid = correlation_id_var.get()
    if cid:
        event_dict["correlation_id"] = cid
    return event_dict


def bind_correlation_id(value: str | UUID) -> Token[str | None]:
    return correlation_id_var.set(str(value))


def clear_correlation_id(token: Token[str | None]) -> None:
    correlation_id_var.reset(token)
