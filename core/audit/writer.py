"""Append-only audit log writer with HMAC + prev_hash chain. See ADR-003.

NOTE on least-privilege: ADR-003 specifies that writes should go through
the `audit_writer` Postgres role (INSERT-only grant). For Iteration 1 we
use the same DB engine as the rest of the app — the role separation is
applied in Iteration 3 (security harden) by introducing a dedicated
engine bound to `audit_writer`. The role is already created in the
initial migration; we're just not connecting as it yet.
"""

from __future__ import annotations

import hmac as _hmac
import json
from hashlib import sha256
from typing import TYPE_CHECKING

import structlog
from sqlalchemy import select

from core.observability.metrics import audit_log_write_failures_total
from core.persistence.models import AuditLog

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from core.messaging.schemas import AgentMessage

_MIN_SECRET_BYTES = 32

_log = structlog.get_logger(__name__)


def _canonical_from_payload_json(payload_json: dict[str, object]) -> bytes:
    """Rebuild the canonical (signature-free) bytes from the stored JSONB."""
    data = dict(payload_json)
    data.pop("hmac_signature", None)
    return json.dumps(data, sort_keys=True, separators=(",", ":")).encode()


class AuditLogWriter:
    """Single-writer, append-only audit-log sink.

    `write_message` signs, chains, and persists one `AgentMessage`.
    `verify_chain` recomputes hashes over a window and reports breaks.
    Both raise on infra failures; the caller is expected to surface alerts.
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        hmac_secret: bytes,
    ) -> None:
        if len(hmac_secret) < _MIN_SECRET_BYTES:
            raise ValueError(f"hmac_secret must be at least {_MIN_SECRET_BYTES} bytes")
        self._session_factory = session_factory
        self._secret = hmac_secret

    async def write_message(
        self,
        msg: AgentMessage,
        *,
        iteration: int | None = None,
    ) -> int:
        """Sign, chain, INSERT one message. Returns the new audit_log.id."""
        try:
            return await self._write_once(msg, iteration)
        except Exception:
            _log.exception("audit.write.failed", message_id=str(msg.message_id))
            audit_log_write_failures_total.inc()
            raise

    async def _write_once(self, msg: AgentMessage, iteration: int | None) -> int:
        canonical = msg.canonical_json(include_signature=False)
        msg_sig = _hmac.new(self._secret, canonical, sha256).hexdigest()

        async with self._session_factory() as session:
            # Read tip of the chain. Single-writer model → no FOR UPDATE.
            prev_hash = (
                await session.execute(
                    select(AuditLog.hmac_hash).order_by(AuditLog.id.desc()).limit(1)
                )
            ).scalar_one_or_none()

            chain_input = canonical + (prev_hash or "").encode()
            chain_hash = _hmac.new(self._secret, chain_input, sha256).hexdigest()

            row = AuditLog(
                correlation_id=msg.correlation_id,
                sender=msg.sender.value,
                recipient=msg.recipient.value,
                message_type=msg.message_type.value,
                priority=msg.priority.value,
                iteration=iteration,
                payload_json=msg.model_dump(mode="json"),
                hmac_sig=msg_sig,
                prev_hash=prev_hash,
                hmac_hash=chain_hash,
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return row.id

    async def verify_chain(
        self,
        *,
        start_id: int = 1,
        end_id: int | None = None,
    ) -> tuple[bool, list[int]]:
        """Recompute the chain over a window. Returns (intact, broken_row_ids)."""
        async with self._session_factory() as session:
            q = select(AuditLog).where(AuditLog.id >= start_id).order_by(AuditLog.id)
            if end_id is not None:
                q = q.where(AuditLog.id <= end_id)
            rows = (await session.execute(q)).scalars().all()

            # Seed `prev_hash` from the row before start_id (if any).
            seed: str | None = None
            if start_id > 1:
                seed = (
                    await session.execute(
                        select(AuditLog.hmac_hash).where(AuditLog.id == start_id - 1)
                    )
                ).scalar_one_or_none()

        broken: list[int] = []
        prev = seed
        for row in rows:
            if row.prev_hash != prev:
                broken.append(row.id)
                prev = row.hmac_hash
                continue
            canonical = _canonical_from_payload_json(row.payload_json)
            expected_chain = _hmac.new(
                self._secret, canonical + (prev or "").encode(), sha256
            ).hexdigest()
            if row.hmac_hash != expected_chain:
                broken.append(row.id)
            prev = row.hmac_hash

        return (len(broken) == 0, broken)
