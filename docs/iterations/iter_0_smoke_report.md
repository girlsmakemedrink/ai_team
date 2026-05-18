# Iteration 0 — `claude -p` smoke report

Date: 2026-05-18 15:03:42 UTC
Result: **PASS ✓**

See [ADR-008](../adr/0008-llm-access-strategy.md) for the validation contract.

## ✓ concurrent
```json
{
  "passed": true,
  "concurrent_n": 5,
  "successes": 5,
  "errors": 0,
  "total_wall_s": 5.04,
  "max_ms": 5042,
  "median_ms": 4614,
  "error_samples": []
}
```

## ✓ allowed_tools
```json
{
  "passed": true,
  "text_preview": "BLOCKED.",
  "tools_used": []
}
```

## ✓ usage_field
```json
{
  "passed": true,
  "tokens_input": 10,
  "tokens_output": 38,
  "cached_input": 24636,
  "cost_cents_estimated": 0,
  "session_id_present": true
}
```

## ✓ resume_caching
```json
{
  "passed": true,
  "first_input_tokens": 10,
  "second_input_tokens": 10,
  "second_cached_input_tokens": 32137,
  "cache_pct": 100.0
}
```

## ✓ latency
```json
{
  "passed": true,
  "latencies_ms": [
    2874,
    4500,
    4214
  ],
  "median_ms": 4214,
  "max_ms": 4500
}
```
