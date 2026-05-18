#!/usr/bin/env bash
# Iteration 0 demo: bring up infra, migrate, publish a test feed message.
# See docs/iterations/iter_0.md "Definition of Done".

set -euo pipefail

cd "$(dirname "$0")/.."

step() { printf "\n\033[1;34m▶ %s\033[0m\n" "$*"; }
ok()   { printf "\033[1;32m✓ %s\033[0m\n" "$*"; }
bail() { printf "\033[1;31m✗ %s\033[0m\n" "$*" >&2; exit 1; }

step "1/4 — Starting infra (postgres, redis, prometheus, grafana)"
make up
ok "compose up issued"

step "2/4 — Waiting for services to become healthy (max 60s)"
deadline=$((SECONDS + 60))
while (( SECONDS < deadline )); do
    running=$(docker compose -f infra/docker-compose.yml ps --status running --format '{{.Name}}' | wc -l | tr -d ' ')
    if [[ "$running" -ge 4 ]]; then
        ok "$running services running"
        break
    fi
    sleep 2
done
if (( SECONDS >= deadline )); then
    bail "Services didn't all start within 60s. Try: make logs"
fi

step "3/4 — Applying database migrations"
uv run alembic upgrade head
ok "schema applied"

step "4/4 — Publishing a test feed event"
uv run python scripts/publish_test_message.py
ok "event published"

cat <<'NOTE'

To see it live, in another terminal:

    uv run uvicorn apps.api.main:app --reload --port 8000
    uv run ai-team watch

Then re-run this script (or `python scripts/publish_test_message.py`)
to publish more events.

Grafana:    http://localhost:3000  (anonymous viewer)
Prometheus: http://localhost:9090
API docs:   http://localhost:8000/docs

NOTE
