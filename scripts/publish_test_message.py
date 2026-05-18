"""Demo helper — publish one test AgentMessage to the team_feed."""

from __future__ import annotations

import asyncio
from uuid import uuid4

from core.config import get_settings
from core.messaging.feed import FeedPublisher
from core.messaging.schemas import (
    AgentId,
    AgentMessage,
    MessageType,
    Priority,
    TaskReportPayload,
    TaskStatus,
)


async def main() -> None:
    settings = get_settings()
    pub = FeedPublisher.from_url(settings.redis_url)
    msg = AgentMessage(
        correlation_id=uuid4(),
        sender=AgentId.TEAM_LEAD,
        recipient=AgentId.USER,
        message_type=MessageType.TASK_REPORT,
        priority=Priority.P3,
        payload=TaskReportPayload(
            task_id=uuid4(),
            status=TaskStatus.DONE,
            progress_pct=100,
            summary="Iteration 0 foundation demo — feed roundtrip works.",
        ),
    )
    event = await pub.publish(msg)
    assert event is not None
    print(f"Published feed event {event['message_id']}")
    await pub.close()


if __name__ == "__main__":
    asyncio.run(main())
