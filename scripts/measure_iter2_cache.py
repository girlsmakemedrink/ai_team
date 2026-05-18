"""Iter-2 Day-1A — measure prompt-cache savings across reused sessions.

Iter-0 smoke verified ~100% cache hit using `--resume <sid>`. PR #3
moved every adapter call to `--session-id <sid>` to fix a different
real-LLM bug, and the cache savings hadn't been re-verified since.
This script runs three turns of a realistic agent loop (one big
system prompt loaded from `prompts/team_lead.md`, three trivial user
messages sharing one session id) and writes the result to
`docs/iterations/iter_2_cache_report.md`. ADR-008 sets the floor at
≥ 30% input-token cache on turns 2+; exit code 0 if cleared, 1
otherwise (at which point iter-2 halts and we revisit ADR-001/008).

Usage:
    uv run python scripts/measure_iter2_cache.py
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
import uuid
from pathlib import Path
from typing import Any

from core.llm.base import LLMInvocationError, LLMResponse, LLMTimeoutError
from core.llm.claude_code_headless import ClaudeCodeHeadlessClient

REPORT_PATH = Path("docs/iterations/iter_2_cache_report.md")
SYSTEM_PROMPT_PATH = Path("prompts/team_lead.md")
THRESHOLD_PCT = 30.0
TURNS = 3


def cache_pct(r: LLMResponse) -> float:
    total = r.tokens.input + r.tokens.cached_input
    return (r.tokens.cached_input / total) * 100 if total else 0.0


async def measure(client: ClaudeCodeHeadlessClient, system_prompt: str) -> list[dict[str, Any]]:
    session_id = str(uuid.uuid4())
    user_messages = [
        "Acknowledge by replying exactly 'ack 1'.",
        "Acknowledge by replying exactly 'ack 2'.",
        "Acknowledge by replying exactly 'ack 3'.",
    ]
    turns: list[dict[str, Any]] = []
    for i, msg in enumerate(user_messages[:TURNS], start=1):
        start = time.perf_counter()
        try:
            r = await client.invoke(
                system_prompt=system_prompt,
                user_message=msg,
                model="haiku",
                session_id=session_id,
                timeout_s=60,
            )
        except (LLMTimeoutError, LLMInvocationError) as e:
            turns.append({"turn": i, "passed": False, "error": str(e)[:300]})
            return turns
        elapsed = round(time.perf_counter() - start, 2)
        turns.append(
            {
                "turn": i,
                "input_tokens": r.tokens.input,
                "cached_input_tokens": r.tokens.cached_input,
                "output_tokens": r.tokens.output,
                "cache_pct": round(cache_pct(r), 1),
                "duration_s": elapsed,
                "cost_cents": r.cost_estimate_cents,
                "session_id_echoed": r.session_id == session_id,
            }
        )
        print(
            f"  turn {i}: input={r.tokens.input} cached={r.tokens.cached_input} "
            f"({cache_pct(r):.1f}%) duration={elapsed}s",
            flush=True,
        )
    return turns


def verdict(turns: list[dict[str, Any]]) -> tuple[bool, str]:
    if any("error" in t for t in turns):
        return False, "one or more turns errored — see report"
    if len(turns) < TURNS:
        return False, f"expected {TURNS} turns, got {len(turns)}"
    # Turn 1 cannot be cached (cache is being populated). Turns 2+ must hit threshold.
    misses = [t for t in turns[1:] if t["cache_pct"] < THRESHOLD_PCT]
    if misses:
        worst = min(t["cache_pct"] for t in turns[1:])
        return False, (f"cache pct below {THRESHOLD_PCT}% on later turn(s): worst={worst}%")
    return True, "all later turns clear the threshold"


def write_report(
    turns: list[dict[str, Any]],
    passed: bool,
    note: str,
    system_prompt_chars: int,
) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    out: list[str] = []
    out.append("# Iter-2 — `--session-id` cache report")
    out.append("")
    out.append(f"Date: {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}")
    out.append(f"Result: **{'PASS ✓' if passed else 'FAIL ✗'}**")
    out.append("")
    out.append(f"Threshold: ≥ {THRESHOLD_PCT}% input-token cache on turn 2+.")
    out.append(f"System prompt used: `prompts/team_lead.md` ({system_prompt_chars} chars).")
    out.append(f"Turns: {TURNS} sequential calls reusing one `--session-id`.")
    out.append("")
    out.append("## Per-turn measurements")
    out.append("```json")
    out.append(json.dumps(turns, indent=2, default=str))
    out.append("```")
    out.append("")
    out.append("## Verdict")
    out.append("")
    out.append(note)
    out.append("")
    out.append("## Context")
    out.append("")
    out.append(
        "This re-measurement was prompted by iter-1 retro action: PR #3 had "
        "switched from `--resume` to `--session-id` after a real-LLM bug "
        "report, and the cache savings hadn't been re-verified. Running this "
        "script on a fresh adapter exposed a second bug: `--session-id` is "
        "set-once (errors on the second call with the same id), so passing "
        "it on every call meant we never cached anything across turns. The "
        "adapter now uses `--session-id` on the first call with an id and "
        "`--resume` on subsequent ones; see "
        "`core/llm/claude_code_headless.py`."
    )
    out.append("")
    out.append(
        "Note on turn-1 numbers: claude -p reports a non-zero "
        "`cache_read_input_tokens` even on the first call because the "
        "Claude Code harness itself caches CLAUDE.md and common context "
        "before our session starts. The meaningful signal is that turns 2+ "
        "reuse the same large cache — they cost no more than turn 1 in "
        "input-token terms despite the conversation growing."
    )
    out.append("")
    if not passed:
        out.append("### Required follow-up")
        out.append("")
        out.append(
            "Cache savings under `--session-id` are below the floor set by "
            "ADR-008. Iter-2 must halt before any agent code lands: the "
            "cost envelope in `docs/iterations/iter_2.md` assumes a working "
            "cache. Revisit ADR-001 / ADR-008 with these numbers and decide "
            "whether to (a) tune the adapter, (b) accept higher per-task "
            "cost and revise the cost table, or (c) switch backends."
        )
    REPORT_PATH.write_text("\n".join(out) + "\n")


async def run(system_prompt: str) -> int:
    sys_chars = len(system_prompt)
    print(
        f"Measuring `--session-id` cache savings over {TURNS} turns "
        f"(haiku model, {sys_chars}-char system prompt).\n"
    )
    client = ClaudeCodeHeadlessClient()
    turns = await measure(client, system_prompt)
    passed, note = verdict(turns)
    write_report(turns, passed, note, sys_chars)
    print(f"\nReport: {REPORT_PATH}")
    print(f"Overall: {'PASS' if passed else 'FAIL'} — {note}")
    return 0 if passed else 1


if __name__ == "__main__":
    # Synchronous file read here to keep ruff's ASYNC240 happy and so the
    # event loop only handles awaitable work.
    sys.exit(asyncio.run(run(SYSTEM_PROMPT_PATH.read_text())))
