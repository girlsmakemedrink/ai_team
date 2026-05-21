# Iteration 0 — `claude -p` smoke report

Date: 2026-05-21 08:54:25 UTC
Result: **PASS ✓**

See [ADR-008](../adr/0008-llm-access-strategy.md) for the validation contract.

## ✓ concurrent
```json
{
  "passed": true,
  "concurrent_n": 5,
  "successes": 5,
  "errors": 0,
  "total_wall_s": 12.48,
  "max_ms": 12468,
  "median_ms": 11419,
  "error_samples": []
}
```

## ✓ allowed_tools
```json
{
  "passed": true,
  "text_preview": "BLOCKED",
  "tools_used": []
}
```

## ✓ usage_field
```json
{
  "passed": true,
  "tokens_input": 20,
  "tokens_output": 435,
  "cached_input": 66584,
  "cost_cents_estimated": 0,
  "session_id_present": true
}
```

## ✓ session_id_caching
```json
{
  "passed": true,
  "first_input_tokens": 10,
  "second_input_tokens": 10,
  "second_cached_input_tokens": 41563,
  "cache_pct": 100.0
}
```

## ✓ latency
```json
{
  "passed": true,
  "latencies_ms": [
    6337,
    6796,
    19273,
    6586,
    7267
  ],
  "median_ms": 6796,
  "max_ms": 19273
}
```
