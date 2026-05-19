#!/usr/bin/env bash
# Iter-3 demo: closes the iter-2 chain end-to-end with TL dependency
# ordering. 6-stage DAG (PM → Architect → Backend|Designer → Frontend →
# QA) per docs/sandbox/idea_validator_v2_spec.md. Wall-clock bumped to
# 20 min (iter-2 demo timed out at 10).
#
# Prerequisites:
#   - .env populated (make dev does this)
#   - `claude` CLI authenticated (Claude Code subscription)
#   - Docker Desktop running
#   - `gh` CLI authenticated (only needed for the open_pr step)

set -euo pipefail
cd "$(dirname "$0")/.."

step() { printf "\n\033[1;34m▶ %s\033[0m\n" "$*"; }
ok()   { printf "\033[1;32m✓ %s\033[0m\n" "$*"; }
bail() { printf "\033[1;31m✗ %s\033[0m\n" "$*" >&2; exit 1; }

[ -f .env ]                                    || bail ".env not found. Run \`make dev\` first."
command -v claude >/dev/null 2>&1              || bail "claude CLI not on PATH."
command -v docker >/dev/null 2>&1              || bail "docker not on PATH."

step "1/7 — Start infra"
make up >/dev/null
deadline=$((SECONDS + 60))
while (( SECONDS < deadline )); do
    running=$(docker compose -f infra/docker-compose.yml ps --status running --format '{{.Name}}' | wc -l | tr -d ' ')
    if [[ "$running" -ge 4 ]]; then ok "$running services healthy"; break; fi
    sleep 2
done

step "2/7 — Apply migrations"
uv run alembic upgrade head >/dev/null
ok "schema applied"

step "3/7 — Write MCP config"
MCP_CONFIG="$(pwd)/.iter3-mcp.json"
REPO_ROOT="$(pwd)"
cat >"$MCP_CONFIG" <<JSON
{
  "mcpServers": {
    "ai-team-bus": {
      "command": "uv",
      "args": ["run", "python", "-m", "tools.mcp_servers.ai_team_bus"]
    },
    "ai-team-tasks": {
      "command": "uv",
      "args": ["run", "python", "-m", "tools.mcp_servers.ai_team_tasks"]
    },
    "ai-team-repo": {
      "command": "uv",
      "args": ["run", "python", "-m", "tools.mcp_servers.ai_team_repo"],
      "env": {
        "AI_TEAM_REPO_ROOT": "$REPO_ROOT",
        "AI_TEAM_PATH_PREFIXES": "*",
        "AI_TEAM_PR_BASE": "main",
        "AI_TEAM_FORBID_BRANCH_RE": "^(main|master|release/.*)$"
      }
    }
  }
}
JSON
ok "wrote $MCP_CONFIG"

step "4/7 — Start API + dispatcher in background"
API_LOG=$(mktemp)
export AI_TEAM_MCP_CONFIG_PATH="$MCP_CONFIG"
uv run uvicorn apps.api.main:app --host 127.0.0.1 --port 8000 >"$API_LOG" 2>&1 &
API_PID=$!
trap 'kill $API_PID 2>/dev/null || true; rm -f "$API_LOG" "$MCP_CONFIG"' EXIT
until curl -sf http://127.0.0.1:8000/health >/dev/null 2>&1; do sleep 1; done
ok "API ready (pid $API_PID, logs: $API_LOG)"

if [[ "${AI_TEAM_DEMO_NON_INTERACTIVE:-0}" != "1" ]]; then
    cat <<NOTE

  In another terminal, watch the feed:
    uv run ai-team watch

  Press ENTER to submit the demo task. (Set
  AI_TEAM_DEMO_NON_INTERACTIVE=1 to skip this prompt for autonomous runs.)

NOTE
    read -r
fi

step "5/7 — Submit demo task (idea-validator v2)"
OWNER_TOKEN=$(grep '^OWNER_TOKEN=' .env | cut -d'=' -f2-)
RESP=$(curl -sf -X POST http://127.0.0.1:8000/api/tasks \
    -H "Authorization: Bearer $OWNER_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{
        "title": "iter-3 demo: idea-validator v2 (CLI + landing page + UX brief)",
        "description": "Implement idea-validator per docs/sandbox/idea_validator_v2_spec.md. Decompose into 6 subtasks with depends_on: pm_clarify (PM) → arch (Architect) → {be (Backend), design (Designer)} → fe (Frontend, depends_on=design) → qa (QA, depends_on=[be,fe]). The dispatcher will hold dependent subtasks until predecessors report done. Pass depends_on as slug references in the decomposition JSON.",
        "target_repo": "examples/sandbox/idea-validator"
    }')
CORRELATION=$(echo "$RESP" | python3 -c 'import sys, json; print(json.load(sys.stdin)["correlation_id"])')
ok "submitted (correlation $CORRELATION)"

step "6/7 — Wait for the chain (up to 20 min) and surface artifacts"
ADR_DIR="docs/adr"
BACKEND_DIR="examples/sandbox/idea-validator"
DESIGN_BRIEF="docs/design/idea-validator.md"
LANDING_PAGE="apps/web/idea-validator/index.html"
deadline=$((SECONDS + 1200))   # 20 minutes
while (( SECONDS < deadline )); do
    latest_adr=$(ls -1t "$ADR_DIR"/0*.md 2>/dev/null | head -1 || true)
    # Done = QA reports DONE = pending_review row appears. Poll the API.
    review_count=$(curl -sf -H "Authorization: Bearer $OWNER_TOKEN" http://127.0.0.1:8000/api/reviews 2>/dev/null \
        | python3 -c 'import sys, json; print(len(json.load(sys.stdin)))' 2>/dev/null || echo 0)
    if [[ "$review_count" -ge 1 ]]; then
        ok "QA produced a pending_review (count=$review_count)"
        break
    fi
    sleep 10
done

echo
echo "--- Latest ADR (Architect): ---"
[[ -n "${latest_adr:-}" ]] && head -40 "$latest_adr" || echo "(none found)"
echo
echo "--- Backend artifacts: ---"
ls -la "$BACKEND_DIR" 2>/dev/null || echo "(none found)"
echo
echo "--- Designer brief: ---"
[[ -f "$DESIGN_BRIEF" ]] && head -20 "$DESIGN_BRIEF" || echo "(missing $DESIGN_BRIEF)"
echo
echo "--- Frontend landing page: ---"
[[ -f "$LANDING_PAGE" ]] && wc -l "$LANDING_PAGE" || echo "(missing $LANDING_PAGE)"
echo

step "7/7 — Pull the per-message demo metrics from audit_log"
echo "Run this to get the single-query demo report:"
cat <<SQL
  PGPASSWORD=ai_team psql -h 127.0.0.1 -U ai_team ai_team -c "
    SELECT id, sender, recipient, message_type,
           payload_json -> 'metadata' -> 'llm' ->> 'model'                       AS model,
           (payload_json -> 'metadata' -> 'llm' ->> 'tokens_in')::int            AS tokens_in,
           (payload_json -> 'metadata' -> 'llm' ->> 'tokens_out')::int           AS tokens_out,
           (payload_json -> 'metadata' -> 'llm' ->> 'cached_input')::int         AS cached_input,
           (payload_json -> 'metadata' -> 'llm' ->> 'cost_cents')::int           AS cost_cents,
           (payload_json -> 'metadata' -> 'llm' ->> 'duration_ms')::int          AS duration_ms,
           (payload_json -> 'metadata' -> 'llm' ->> 'validated_against_schema')  AS schema_ok
    FROM audit_log
    WHERE correlation_id = '$CORRELATION'
    ORDER BY id;
  "
SQL

# Attempt the query inline; ignore errors so the script doesn't fail
# the whole run if psql isn't installed locally.
if command -v psql >/dev/null 2>&1; then
    echo
    echo "--- Inline psql output: ---"
    PGPASSWORD=ai_team psql -h 127.0.0.1 -U ai_team ai_team -c "
        SELECT id, sender, recipient, message_type,
               payload_json -> 'metadata' -> 'llm' ->> 'model'                       AS model,
               (payload_json -> 'metadata' -> 'llm' ->> 'tokens_in')::int            AS tokens_in,
               (payload_json -> 'metadata' -> 'llm' ->> 'tokens_out')::int           AS tokens_out,
               (payload_json -> 'metadata' -> 'llm' ->> 'cost_cents')::int           AS cost_cents,
               (payload_json -> 'metadata' -> 'llm' ->> 'duration_ms')::int          AS duration_ms,
               (payload_json -> 'metadata' -> 'llm' ->> 'validated_against_schema')  AS schema_ok
        FROM audit_log
        WHERE correlation_id = '$CORRELATION'
        ORDER BY id;
    " 2>/dev/null || echo "(psql query failed — paste the SQL above into your DB client)"
fi

echo
echo "--- Pending reviews (QA → owner approval): ---"
uv run ai-team list-pending 2>/dev/null || true
echo
echo "--- Latest checkpoint digest: ---"
uv run ai-team digest --history --limit 5 2>/dev/null || true

cat <<NOTE

To approve the QA result and close the loop:
   uv run ai-team approve <id>

Ctrl+C the watch terminal when done; this script will clean up.
NOTE
