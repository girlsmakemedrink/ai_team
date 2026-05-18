# Iter-2 — `--session-id` cache report

Date: 2026-05-18 18:47:37 UTC
Result: **PASS ✓**

Threshold: ≥ 30.0% input-token cache on turn 2+.
System prompt used: `prompts/team_lead.md` (2169 chars).
Turns: 3 sequential calls reusing one `--session-id`.

## Per-turn measurements
```json
[
  {
    "turn": 1,
    "input_tokens": 10,
    "cached_input_tokens": 26958,
    "output_tokens": 176,
    "cache_pct": 100.0,
    "duration_s": 6.23,
    "cost_cents": 0,
    "session_id_echoed": true
  },
  {
    "turn": 2,
    "input_tokens": 10,
    "cached_input_tokens": 37193,
    "output_tokens": 41,
    "cache_pct": 100.0,
    "duration_s": 7.0,
    "cost_cents": 0,
    "session_id_echoed": true
  },
  {
    "turn": 3,
    "input_tokens": 10,
    "cached_input_tokens": 37420,
    "output_tokens": 41,
    "cache_pct": 100.0,
    "duration_s": 4.57,
    "cost_cents": 0,
    "session_id_echoed": true
  }
]
```

## Verdict

all later turns clear the threshold

## Context

This re-measurement was prompted by iter-1 retro action: PR #3 had switched from `--resume` to `--session-id` after a real-LLM bug report, and the cache savings hadn't been re-verified. Running this script on a fresh adapter exposed a second bug: `--session-id` is set-once (errors on the second call with the same id), so passing it on every call meant we never cached anything across turns. The adapter now uses `--session-id` on the first call with an id and `--resume` on subsequent ones; see `core/llm/claude_code_headless.py`.

Note on turn-1 numbers: claude -p reports a non-zero `cache_read_input_tokens` even on the first call because the Claude Code harness itself caches CLAUDE.md and common context before our session starts. The meaningful signal is that turns 2+ reuse the same large cache — they cost no more than turn 1 in input-token terms despite the conversation growing.

