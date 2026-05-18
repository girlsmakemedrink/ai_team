#!/usr/bin/env bash
# Iteration 1 demo: TL + PM live, end-to-end submit → decompose → user stories → approve.
#
# Prerequisites:
#   - .env populated (make dev does this once)
#   - `claude` CLI authenticated (Claude Code subscription)
#   - Docker Desktop running
#
# Walks through:
#   1. `make up` infra
#   2. `alembic upgrade head` schema
#   3. start API + dispatcher in background
#   4. open `ai-team watch` for the owner to see the live feed
#   5. submit a real task
#   6. wait for PM to emit user stories
#   7. show resulting backlog file
#   8. clean up

set -euo pipefail
cd "$(dirname "$0")/.."

step() { printf "\n\033[1;34m▶ %s\033[0m\n" "$*"; }
ok()   { printf "\033[1;32m✓ %s\033[0m\n" "$*"; }
bail() { printf "\033[1;31m✗ %s\033[0m\n" "$*" >&2; exit 1; }

if [ ! -f .env ]; then
    bail ".env not found. Run \`make dev\` first."
fi

if ! command -v claude >/dev/null 2>&1; then
    bail "claude CLI not on PATH. Install Claude Code + log in (subscription auth)."
fi

step "1/6 — Start infra"
make up >/dev/null
deadline=$((SECONDS + 60))
while (( SECONDS < deadline )); do
    running=$(docker compose -f infra/docker-compose.yml ps --status running --format '{{.Name}}' | wc -l | tr -d ' ')
    if [[ "$running" -ge 4 ]]; then
        ok "$running services healthy"
        break
    fi
    sleep 2
done

step "2/6 — Apply migrations"
uv run alembic upgrade head >/dev/null
ok "schema applied"

step "3/6 — Start API + dispatcher in background"
API_LOG=$(mktemp)
uv run uvicorn apps.api.main:app --host 127.0.0.1 --port 8000 >"$API_LOG" 2>&1 &
API_PID=$!
trap 'kill $API_PID 2>/dev/null || true; rm -f "$API_LOG"' EXIT
until curl -sf http://127.0.0.1:8000/health >/dev/null 2>&1; do sleep 1; done
ok "API ready (pid $API_PID, logs: $API_LOG)"

cat <<NOTE

  In another terminal, watch the feed live:
    uv run ai-team watch

  Then come back here and press ENTER to submit the demo task.

NOTE
read -r

step "4/6 — Submit demo task"
OWNER_TOKEN=$(grep '^OWNER_TOKEN=' .env | cut -d'=' -f2-)
RESP=$(curl -sf -X POST http://127.0.0.1:8000/api/tasks \
    -H "Authorization: Bearer $OWNER_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{
        "title": "iter-1 demo: idea-validator user stories",
        "description": "Produce a focused set of user stories for the idea-validator CLI described in docs/sandbox/idea_validator_spec.md."
    }')
CORRELATION=$(echo "$RESP" | python3 -c 'import sys, json; print(json.load(sys.stdin)["correlation_id"])')
ok "submitted (correlation $CORRELATION)"

step "5/6 — Wait for PM to emit user stories (up to 90s)"
BACKLOG="docs/backlog/$CORRELATION.md"
deadline=$((SECONDS + 90))
while (( SECONDS < deadline )); do
    if [[ -f "$BACKLOG" ]]; then
        ok "user stories landed: $BACKLOG"
        break
    fi
    sleep 2
done
if [[ ! -f "$BACKLOG" ]]; then
    bail "no backlog file after 90s. Check $API_LOG and feed."
fi

step "6/6 — Result"
echo
cat "$BACKLOG"
echo
echo "Audit + feed are queryable via psql / Grafana / ai-team digest."
echo "When you're done: Ctrl+C the watch terminal; this script will clean up."
NOTE
