# Iteration 0 — `claude -p` smoke report

Date: 2026-05-18 20:08:32 UTC
Result: **PASS ✓**

See [ADR-008](../adr/0008-llm-access-strategy.md) for the validation contract.

## ✓ concurrent
```json
{
  "passed": true,
  "concurrent_n": 5,
  "successes": 5,
  "errors": 0,
  "total_wall_s": 16.98,
  "max_ms": 16982,
  "median_ms": 13214,
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
  "tokens_input": 10,
  "tokens_output": 159,
  "cached_input": 26958,
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
  "second_cached_input_tokens": 40707,
  "cache_pct": 100.0
}
```

## ✓ latency
```json
{
  "passed": true,
  "latencies_ms": [
    5070,
    5628,
    9437,
    3846,
    5582
  ],
  "median_ms": 5582,
  "max_ms": 9437
}
```
