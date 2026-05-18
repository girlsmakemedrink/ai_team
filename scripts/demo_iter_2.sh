#!/usr/bin/env bash
# Iteration 2 demo: TL → Architect → Backend → QA → pending_review → approve.
#
# Prerequisites:
#   - .env populated (make dev does this)
#   - `claude` CLI authenticated (Claude Code subscription)
#   - Docker Desktop running
#   - `gh` CLI authenticated (only needed for the open_pr step)
#
# What this script does:
#   1. `make up` infra
#   2. `alembic upgrade head` schema
#   3. write a concrete MCP config (no env-var substitution; that's iter-2b)
#   4. start API + dispatcher in background with AI_TEAM_MCP_CONFIG_PATH set
#   5. submit the "implement idea-validator" task
#   6. wait for the chain to complete (max 10 min) — produces:
#         - docs/adr/<NNNN>-<slug>.md   (Architect)
#         - examples/sandbox/idea-validator/{src,tests}/  (Backend)
#         - a pending_review row in Postgres (when QA reports back)
#   7. owner runs `ai-team approve <id>` manually to close out

set -euo pipefail
cd "$(dirname "$0")/.."

step() { printf "\n\033[1;34m▶ %s\033[0m\n" "$*"; }
ok()   { printf "\033[1;32m✓ %s\033[0m\n" "$*"; }
bail() { printf "\033[1;31m✗ %s\033[0m\n" "$*" >&2; exit 1; }

[ -f .env ]                                    || bail ".env not found. Run \`make dev\` first."
command -v claude >/dev/null 2>&1              || bail "claude CLI not on PATH."
command -v docker >/dev/null 2>&1              || bail "docker not on PATH."

step "1/6 — Start infra"
make up >/dev/null
deadline=$((SECONDS + 60))
while (( SECONDS < deadline )); do
    running=$(docker compose -f infra/docker-compose.yml ps --status running --format '{{.Name}}' | wc -l | tr -d ' ')
    if [[ "$running" -ge 4 ]]; then ok "$running services healthy"; break; fi
    sleep 2
done

step "2/6 — Apply migrations"
uv run alembic upgrade head >/dev/null
ok "schema applied"

step "3/6 — Write MCP config"
MCP_CONFIG="$(pwd)/.iter2-mcp.json"
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

step "4/6 — Start API + dispatcher in background"
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

step "5/6 — Submit demo task"
OWNER_TOKEN=$(grep '^OWNER_TOKEN=' .env | cut -d'=' -f2-)
RESP=$(curl -sf -X POST http://127.0.0.1:8000/api/tasks \
    -H "Authorization: Bearer $OWNER_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{
        "title": "iter-2 demo: implement idea-validator from spec",
        "description": "Implement the idea-validator CLI per docs/sandbox/idea_validator_spec.md. Architect first writes an ADR specifying the pipeline. Backend then implements the code+tests in examples/sandbox/idea-validator/. QA runs the test suite and reports back.",
        "target_repo": "examples/sandbox/idea-validator"
    }')
CORRELATION=$(echo "$RESP" | python3 -c 'import sys, json; print(json.load(sys.stdin)["correlation_id"])')
ok "submitted (correlation $CORRELATION)"

step "6/6 — Wait for the chain (up to 10 min) and surface the result"
ADR_DIR="docs/adr"
BACKEND_DIR="examples/sandbox/idea-validator"
deadline=$((SECONDS + 600))
while (( SECONDS < deadline )); do
    # Heuristic: Architect's ADR file lands first, then Backend's code.
    latest_adr=$(ls -1t "$ADR_DIR"/0*.md 2>/dev/null | head -1 || true)
    if [[ -d "$BACKEND_DIR/src" ]]; then
        ok "Backend produced $BACKEND_DIR/src/"
        break
    fi
    sleep 5
done

echo
echo "--- Latest ADR (Architect): ---"
[[ -n "${latest_adr:-}" ]] && head -40 "$latest_adr" || echo "(none found)"
echo
echo "--- Backend artifacts: ---"
ls -la "$BACKEND_DIR" 2>/dev/null || echo "(none found)"
echo
echo "--- Pending reviews (QA → owner approval): ---"
uv run ai-team digest --history --limit 5 2>/dev/null || true

cat <<NOTE

To approve the QA result and close the loop:
   uv run ai-team approve <id>

Ctrl+C the watch terminal when done; this script will clean up.
NOTE
