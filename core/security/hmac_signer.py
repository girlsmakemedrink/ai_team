"""HMAC signing & verification for AgentMessage. See ADR-005 and ADR-002."""

from __future__ import annotations

import hmac
from hashlib import sha256

from core.messaging.schemas import AgentMessage


class InvalidSignatureError(Exception):
    """Raised when HMAC verification fails."""


class HMACSigner:
    """Sign and verify AgentMessages with a shared secret.

    The signed bytes are the message's canonical JSON without the
    `hmac_signature` field, so signing is deterministic and verification
    independent of clock or formatting.
    """

    def __init__(self, secret: bytes) -> None:
        if len(secret) < 32:
            raise ValueError("HMAC secret must be at least 32 bytes")
        self._secret = secret

    @classmethod
    def from_string(cls, secret: str) -> HMACSigner:
        return cls(secret.encode())

    def sign(self, message: AgentMessage) -> str:
        digest = hmac.new(
            self._secret, message.canonical_json(include_signature=False), sha256
        )
        return digest.hexdigest()

    def verify(self, message: AgentMessage) -> None:
        if message.hmac_signature is None:
            raise InvalidSignatureError("missing hmac_signature on message")
        expected = self.sign(message)
        if not hmac.compare_digest(expected, message.hmac_signature):
            raise InvalidSignatureError("hmac signature mismatch")

    def with_signature(self, message: AgentMessage) -> AgentMessage:
        """Return a new AgentMessage with hmac_signature filled in.

        AgentMessage is frozen, so we round-trip via model_copy.
        """
        return message.model_copy(update={"hmac_signature": self.sign(message)})
