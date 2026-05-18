# ADR-0002 — Message schema & protocol

- **Status**: Accepted
- **Date**: 2026-05-18

## Context

Agents in `ai_team` exchange messages through Redis Streams ([ADR-001]).
Every message must be:

- Strongly typed (validated at the boundary).
- Versioned (so we can evolve the protocol without breaking persisted
  history).
- HMAC-signed by the sender (so the audit log proves provenance — see
  [ADR-003] and [ADR-005]).
- Self-describing (sender, recipient, priority, correlation, timestamps).
- Routable to a single agent OR broadcastable.
- Carrying typed payloads per `message_type`, not a free-form `dict`.

We pick Pydantic v2 because it ships with the project, generates fast
validators, and integrates cleanly with FastAPI.

## Decision

A single `AgentMessage` envelope, with a discriminated-union `payload` keyed
on `message_type`. Schema version is stamped on every message; consumers
refuse to decode unknown major versions.

```python
# core/messaging/schemas.py

SCHEMA_VERSION = "1.0"  # major.minor; bump major on breaking change

class AgentId(str, Enum):
    USER = "user"
    TEAM_LEAD = "team_lead"
    PRODUCT_MANAGER = "product_manager"
    DESIGNER = "designer"
    ARCHITECT = "architect"
    BACKEND_DEVELOPER = "backend_developer"
    FRONTEND_DEVELOPER = "frontend_developer"
    DEVOPS = "devops"
    QA_ENGINEER = "qa_engineer"
    SRE_SUPPORT = "sre_support"
    MARKET_RESEARCHER = "market_researcher"
    BROADCAST = "broadcast"          # recipient only


class Priority(str, Enum):
    P1 = "P1"  # critical incident / blocked owner approval
    P2 = "P2"  # active user task
    P3 = "P3"  # routine work
    P4 = "P4"  # monitoring / background


class MessageType(str, Enum):
    TASK_ASSIGNMENT = "task_assignment"
    TASK_REPORT = "task_report"
    QUESTION = "question"
    ANSWER = "answer"
    REVIEW_REQUEST = "review_request"
    ALERT = "alert"
    BROADCAST = "broadcast"
    CHECKPOINT_DIGEST = "checkpoint_digest"   # TL → owner summary
    HEARTBEAT = "heartbeat"                   # filtered out of feed by default


# Per-type payloads (each a Pydantic BaseModel):
class TaskAssignmentPayload(BaseModel):
    task_id: UUID
    title: str
    description: str
    target_repo: str | None            # default: ai_team itself
    deadline: datetime | None
    inputs: dict[str, Any] = {}

class TaskReportPayload(BaseModel):
    task_id: UUID
    status: Literal["in_progress", "blocked", "done", "failed"]
    progress_pct: int = Field(ge=0, le=100)
    summary: str
    artifacts: list[str] = []          # e.g. PR URLs, file paths
    blocked_on: str | None = None

# ... (full list in code; see core/messaging/schemas.py)

PayloadT = Union[
    TaskAssignmentPayload,
    TaskReportPayload,
    # ... one per MessageType
]


class AgentMessage(BaseModel):
    schema_version: str = SCHEMA_VERSION
    message_id: UUID = Field(default_factory=uuid4)
    correlation_id: UUID                # ties messages within one task tree
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))

    sender: AgentId
    recipient: AgentId                  # USER / agent / BROADCAST

    message_type: MessageType
    priority: Priority = Priority.P3

    payload: PayloadT = Field(discriminator="kind")  # tagged via Literal field
    metadata: dict[str, Any] = {}

    requires_human_approval: bool = False
    hmac_signature: str | None = None   # filled by sender, verified by bus

    model_config = ConfigDict(frozen=True, extra="forbid")
```

### Versioning rules

- `schema_version` is `"major.minor"`. Minor bumps are additive (new optional
  fields, new `MessageType` values).
- Breaking changes bump the major and ship a migration: a script that reads
  v1 messages from Postgres `audit_log` and emits v2-compatible re-encodings
  written to a new partition. Old messages are *never* mutated in place
  (see [ADR-003]).
- Every consumer (agent, bus, dispatcher) checks the major on receive. Major
  mismatch → message routed to a dead-letter stream `bus.dlq.v<incoming>` and
  raises a `P2` alert.

### HMAC signature

- Computed by sender over `canonical_json(message_without_signature)` with
  `HMAC_SECRET` (server-side key, see [ADR-005]).
- Verified by the bus *before* enqueue. Mismatch → drop + `P1` alert.
- Owner-originated messages additionally carry `OWNER_TOKEN` (HMAC-equivalent
  but a separate key, see [ADR-005]).

### Tests

- A `tests/contract/test_message_schema.py` snapshot suite locks the JSON
  Schema for v1.x. Any unintended change fails CI.
- Backward-compat suite: a fixed corpus of v1 messages round-trips through
  the latest decoder.

## Consequences

### Positive

- All cross-agent contracts are typed, self-validating, and machine-readable.
- Versioning is built in from day one — schema migration is a routine
  operation, not a panic.
- Pydantic generates JSON Schema we can publish to the owner (and future
  external integrations).

### Negative

- Adding a new `MessageType` requires adding a payload class, updating the
  union, and writing a migration if it ships with new schema fields.
- Discriminated unions on Pydantic v2 require a `kind` literal field on
  every payload class — small boilerplate cost.

## Alternatives considered

- **Free-form `dict[str, Any]` payloads.** Rejected — no validation, no
  documentation, no contract tests.
- **Protobuf or Avro.** Rejected — adds a build step and a separate IDL
  for marginal benefit; Pydantic + JSON is enough at our scale.
- **Per-edge schemas (one schema per sender→recipient pair).** Rejected —
  combinatorial explosion (11 agents × 11 recipients × 8 types).

## References

- [ADR-001 — Orchestrator choice][ADR-001]
- [ADR-003 — Audit log strategy][ADR-003]
- [ADR-005 — Auth & secrets][ADR-005]

[ADR-001]: 0001-orchestrator-choice.md
[ADR-003]: 0003-audit-log-strategy.md
[ADR-005]: 0005-auth-secrets.md
