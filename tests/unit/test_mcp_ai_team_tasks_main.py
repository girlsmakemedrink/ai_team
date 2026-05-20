"""iter-18: __main__ inputSchema regression guard for ai_team_tasks.

Pins the request_human_review inputSchema so a future PR
that broadens additionalProperties or drops a required
field has to update this test.
"""

from __future__ import annotations

from tools.mcp_servers.ai_team_tasks.__main__ import _TOOL_LIST


def test_request_human_review_schema_requires_summary_and_correlation() -> None:
    tool = next(t for t in _TOOL_LIST if t["name"] == "request_human_review")
    schema = tool["inputSchema"]
    assert schema["type"] == "object"
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == {"summary", "correlation_id"}
    props = schema["properties"]
    assert props["summary"]["type"] == "string"
    assert props["correlation_id"]["type"] == "string"
    assert props["agent"]["type"] == "string"
    assert props["task_id"]["type"] == "string"
    assert props["target_artifact"]["type"] == "string"
