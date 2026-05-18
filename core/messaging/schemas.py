"""AgentMessage envelope and payload schemas. See ADR-002."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Annotated, Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

SCHEMA_VERSION = "1.0"


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
    BROADCAST = "broadcast"  # recipient only


class Priority(str, Enum):
    P1 = "P1"  # critical incident / blocking
    P2 = "P2"  # active user task
    P3 = "P3"  # routine
    P4 = "P4"  # background / monitoring


class MessageType(str, Enum):
    TASK_ASSIGNMENT = "task_assignment"
    TASK_REPORT = "task_report"
    QUESTION = "question"
    ANSWER = "answer"
    REVIEW_REQUEST = "review_request"
    ALERT = "alert"
    BROADCAST = "broadcast"
    CHECKPOINT_DIGEST = "checkpoint_digest"
    HEARTBEAT = "heartbeat"


class TaskStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    DONE = "done"
    FAILED = "failed"


# ---------- Payloads ----------


class _PayloadBase(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TaskAssignmentPayload(_PayloadBase):
    kind: Literal["task_assignment"] = "task_assignment"
    task_id: UUID
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=10_000)
    target_repo: str | None = None
    deadline: datetime | None = None
    inputs: dict[str, Any] = Field(default_factory=dict)


class TaskReportPayload(_PayloadBase):
    kind: Literal["task_report"] = "task_report"
    task_id: UUID
    status: TaskStatus
    progress_pct: int = Field(ge=0, le=100)
    summary: str = Field(max_length=2_000)
    artifacts: list[str] = Field(default_factory=list)
    blocked_on: str | None = None


class QuestionPayload(_PayloadBase):
    kind: Literal["question"] = "question"
    question_id: UUID
    text: str
    requires_answer_by: datetime | None = None


class AnswerPayload(_PayloadBase):
    kind: Literal["answer"] = "answer"
    question_id: UUID
    text: str


class ReviewRequestPayload(_PayloadBase):
    kind: Literal["review_request"] = "review_request"
    review_id: UUID
    target_artifact: str
    summary: str
    reviewers: list[AgentId] = Field(default_factory=list)


class AlertPayload(_PayloadBase):
    kind: Literal["alert"] = "alert"
    severity: Priority
    title: str
    description: str
    runbook_url: str | None = None
    suggested_action: str | None = None


class BroadcastPayload(_PayloadBase):
    kind: Literal["broadcast"] = "broadcast"
    topic: str
    body: str


class CheckpointDigestPayload(_PayloadBase):
    kind: Literal["checkpoint_digest"] = "checkpoint_digest"
    checkpoint_id: UUID
    trigger: Literal[
        "task_done", "manual", "scheduled", "iteration_end", "pre_review", "alert"
    ]
    iteration: int | None = None
    digest_markdown: str = Field(max_length=4_000)
    quota_used_pct: float = Field(ge=0.0, le=200.0)


class HeartbeatPayload(_PayloadBase):
    kind: Literal["heartbeat"] = "heartbeat"
    agent: AgentId
    healthy: bool = True
    note: str | None = None


Payload = Annotated[
    TaskAssignmentPayload
    | TaskReportPayload
    | QuestionPayload
    | AnswerPayload
    | ReviewRequestPayload
    | AlertPayload
    | BroadcastPayload
    | CheckpointDigestPayload
    | HeartbeatPayload,
    Field(discriminator="kind"),
]


# ---------- Envelope ----------


class AgentMessage(BaseModel):
    schema_version: str = SCHEMA_VERSION
    message_id: UUID = Field(default_factory=uuid4)
    correlation_id: UUID
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))

    sender: AgentId
    recipient: AgentId

    message_type: MessageType
    priority: Priority = Priority.P3

    payload: Payload
    metadata: dict[str, Any] = Field(default_factory=dict)

    requires_human_approval: bool = False
    hmac_signature: str | None = None

    model_config = ConfigDict(frozen=True, extra="forbid")

    def canonical_json(self, *, include_signature: bool = False) -> bytes:
        """Stable JSON representation used for HMAC computation."""
        data = self.model_dump(mode="json", exclude_none=False)
        if not include_signature:
            data.pop("hmac_signature", None)
        # Sort keys for stable hashing across runs.
        import json

        return json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
