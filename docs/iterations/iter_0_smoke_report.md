# Iteration 0 — `claude -p` smoke report

Date: 2026-05-19 09:50:26 UTC
Result: **PASS ✓**

See [ADR-008](../adr/0008-llm-access-strategy.md) for the validation contract.

## ✓ concurrent
```json
{
  "passed": true,
  "concurrent_n": 5,
  "successes": 5,
  "errors": 0,
  "total_wall_s": 12.09,
  "max_ms": 12089,
  "median_ms": 8387,
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
  "tokens_output": 236,
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
  "second_cached_input_tokens": 40721,
  "cache_pct": 100.0
}
```

## ✓ latency
```json
{
  "passed": true,
  "latencies_ms": [
    5522,
    7556,
    5669,
    5947,
    7009
  ],
  "median_ms": 5947,
  "max_ms": 7556
}
```
