# Iteration 0 — `claude -p` smoke report

Date: 2026-05-21 12:15:26 UTC
Result: **PASS ✓**

See [ADR-008](../adr/0008-llm-access-strategy.md) for the validation contract.

## ✓ concurrent
```json
{
  "passed": true,
  "concurrent_n": 5,
  "successes": 5,
  "errors": 0,
  "total_wall_s": 13.94,
  "max_ms": 13924,
  "median_ms": 7713,
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
  "tokens_output": 677,
  "cached_input": 66816,
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
  "second_cached_input_tokens": 41795,
  "cache_pct": 100.0
}
```

## ✓ latency
```json
{
  "passed": true,
  "latencies_ms": [
    4493,
    7398,
    5751,
    6325,
    9280
  ],
  "median_ms": 6325,
  "max_ms": 9280
}
```
