# Iteration 0 — `claude -p` smoke report

Date: 2026-05-21 10:04:01 UTC
Result: **PASS ✓**

See [ADR-008](../adr/0008-llm-access-strategy.md) for the validation contract.

## ✓ concurrent
```json
{
  "passed": true,
  "concurrent_n": 5,
  "successes": 5,
  "errors": 0,
  "total_wall_s": 17.81,
  "max_ms": 17806,
  "median_ms": 11611,
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
  "tokens_output": 409,
  "cached_input": 27029,
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
  "second_cached_input_tokens": 41576,
  "cache_pct": 100.0
}
```

## ✓ latency
```json
{
  "passed": true,
  "latencies_ms": [
    9941,
    9387,
    7518,
    13506,
    7685
  ],
  "median_ms": 9387,
  "max_ms": 13506
}
```
