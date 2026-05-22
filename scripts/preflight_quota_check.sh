#!/usr/bin/env bash
# Pre-demo quota check (iter-26 handoff P2).
#
# Sends a trivial prompt to `claude -p` and checks the result.
# Exits 0 on success.
# Exits 1 if the response contains api_error_status=429 or is empty;
# prints the 429 reset time line if available so the operator
# knows when to retry.
#
# Used by scripts/demo_iter_26a.sh and any later demo that wants to
# avoid burning 15 minutes on a doomed chain.

set -euo pipefail

if ! command -v claude >/dev/null 2>&1; then
  echo "preflight: claude CLI not found in PATH" >&2
  exit 2
fi

tmp=$(mktemp)
trap 'rm -f "$tmp"' EXIT

if ! claude -p "Reply with exactly: pong" --output-format json --max-turns 1 > "$tmp" 2>&1; then
  echo "preflight: claude -p invocation failed" >&2
  cat "$tmp" >&2
  exit 1
fi

if grep -q '"api_error_status": *429' "$tmp"; then
  echo "preflight: Max-5x session quota hit (429)." >&2
  grep -oE '"resets [^"]+"' "$tmp" | head -1 >&2 || true
  echo "preflight: wait for the reset time above, then re-run." >&2
  exit 1
fi

# Heuristic — `result` or `structured_output` should contain "pong".
if ! grep -qi 'pong' "$tmp"; then
  echo "preflight: response did not contain 'pong'. Sample:" >&2
  head -c 1000 "$tmp" >&2
  exit 1
fi

echo "preflight: OK (quota available)."
exit 0
