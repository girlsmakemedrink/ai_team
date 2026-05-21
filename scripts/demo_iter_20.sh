#!/usr/bin/env bash
# Iter-20 demo: same 6-stage DAG as iter-10..19 (PM → Architect
# → Backend | Designer → Frontend → QA per
# docs/sandbox/idea_validator_v2_spec.md). iter-20 closes the
# TWO killer findings from iter-19's demo so the chain can
# finally reach QA and produce a `pending_reviews` row with
# requesting_agent='qa_engineer'.
#
#   1. iter-19 demo Caveat B (branch-isolation) — Backend agent
#      ran handle_create_branch which executed
#      `git checkout -b <branch> <base>` against the
#      orchestrator's own worktree, switching HEAD to the
#      agent's branch mid-chain. iter-20 Phase 1 replaces the
#      call with `git worktree add` so the orchestrator's HEAD
#      is unaffected. A module-level _ACTIVE_WORKTREE on the
#      MCP server tracks the isolated worktree for subsequent
#      handler calls.
#
#   2. iter-19 demo Caveat A (Backend 600s timeout —
#      10-iteration carry-over) — iter-20 Phase 2 adds a TL
#      prompt edit instructing decomposition of Backend work
#      over ~200 LOC into multiple subtasks with depends_on
#      slugs. Prompt-only; runtime tripwire deferred to
#      iter-21+ if this doesn't fix the timeout.
#
#   3. iter-20 Phase 3 (this script) — pre-flight
#      `git worktree prune` + .claude/agent-worktrees/ rm
#      ensures stale paths from prior demo runs don't confuse
#      `git worktree add`. EXIT trap removes each agent
#      worktree on cleanup.
#
#   4. Expected outcome: orchestrator HEAD stays on
#      worktree-iter-20 throughout; chain reaches QA done; QA
#      writes the pending_review row that iter-19 deferred.
#
# Wall-clock budget: 30 min initial chain + 15 min retry window
# = 45 min total. Cost ceiling: $5.00 (iter-19 was ~$2.00).
#
# Prerequisites:
#   - .env populated (make dev does this)
#   - `claude` CLI authenticated (Claude Code subscription)
#   - Docker Desktop running
#   - .venv exists (uv sync has been run)
#   - `gh` CLI authenticated (only needed for the open_pr step)

set -euo pipefail
cd "$(dirname "$0")/.."

step() { printf "\n\033[1;34m▶ %s\033[0m\n" "$*"; }
ok()   { printf "\033[1;32m✓ %s\033[0m\n" "$*"; }
bail() { printf "\033[1;31m✗ %s\033[0m\n" "$*" >&2; exit 1; }

[ -f .env ]                                    || bail ".env not found. Run \`make dev\` first."
command -v claude >/dev/null 2>&1              || bail "claude CLI not on PATH."
command -v docker >/dev/null 2>&1              || bail "docker not on PATH."
[ -x ".venv/bin/python" ]                      || bail ".venv/bin/python not found. Run \`uv sync\` (or \`make dev\`) first."

step "1/7 — Start infra"
make up >/dev/null
deadline=$((SECONDS + 60))
while (( SECONDS < deadline )); do
    running=$(docker compose -f infra/docker-compose.yml ps --status running --format '{{.Name}}' | wc -l | tr -d ' ')
    if [[ "$running" -ge 4 ]]; then ok "$running services healthy"; break; fi
    sleep 2
done

step "1.5/7 — Prune stale agent worktrees (iter-20)"
# iter-20: handle_create_branch now creates isolated worktrees under
# .claude/agent-worktrees/. Stale ones from prior demo runs would
# confuse `git worktree add`. Prune first.
if [[ -d .claude/agent-worktrees ]]; then
    for wt in .claude/agent-worktrees/*/; do
        [[ -d "$wt" ]] || continue
        git worktree remove --force "$wt" 2>/dev/null || rm -rf "$wt"
    done
    rmdir .claude/agent-worktrees 2>/dev/null || true
fi
git worktree prune
ok "agent worktrees pruned"

step "2/7 — Apply migrations"
uv run alembic upgrade head >/dev/null
ok "schema applied"

step "3/7 — Write MCP config (direct .venv/bin/python)"
MCP_CONFIG="$(pwd)/.iter20-mcp.json"
REPO_ROOT="$(pwd)"
VENV_PY="${REPO_ROOT}/.venv/bin/python"
cat >"$MCP_CONFIG" <<JSON
{
  "mcpServers": {
    "ai-team-bus": {
      "command": "$VENV_PY",
      "args": ["-m", "tools.mcp_servers.ai_team_bus"]
    },
    "ai-team-tasks": {
      "command": "$VENV_PY",
      "args": ["-m", "tools.mcp_servers.ai_team_tasks"]
    },
    "ai-team-repo": {
      "command": "$VENV_PY",
      "args": ["-m", "tools.mcp_servers.ai_team_repo"],
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
_cleanup_iter20() {
    kill "$API_PID" 2>/dev/null || true
    rm -f "$API_LOG" "$MCP_CONFIG"
    # iter-20: clean up isolated agent worktrees so the next run starts fresh
    if [[ -d .claude/agent-worktrees ]]; then
        for wt in .claude/agent-worktrees/*/; do
            [[ -d "$wt" ]] || continue
            git worktree remove --force "$wt" 2>/dev/null || rm -rf "$wt"
        done
        rmdir .claude/agent-worktrees 2>/dev/null || true
    fi
    git worktree prune 2>/dev/null || true
}
trap _cleanup_iter20 EXIT
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
        "title": "iter-20 demo: idea-validator v2 (CLI + landing page + UX brief)",
        "description": "Implement idea-validator per docs/sandbox/idea_validator_v2_spec.md. Decompose into 6 subtasks with depends_on: pm_clarify (PM) → arch (Architect) → {be (Backend), design (Designer)} → fe (Frontend, depends_on=design) → qa (QA, depends_on=[be,fe]). The dispatcher will hold dependent subtasks until predecessors report done. Pass depends_on as slug references in the decomposition JSON.",
        "target_repo": "examples/sandbox/idea-validator"
    }')
CORRELATION=$(echo "$RESP" | python3 -c 'import sys, json; print(json.load(sys.stdin)["correlation_id"])')
ok "submitted (correlation $CORRELATION)"

step "6/7 — Wait for the chain (up to 30 min) and surface artifacts"
ADR_DIR="docs/adr"
BACKEND_DIR="examples/sandbox/idea-validator"
DESIGN_BRIEF="docs/design/idea-validator.md"
LANDING_PAGE="apps/web/idea-validator/index.html"
deadline=$((SECONDS + 1800))   # 30 minutes (iter-5 was 20)
qa_review_count=0
while (( SECONDS < deadline )); do
    latest_adr=$(ls -1t "$ADR_DIR"/0*.md 2>/dev/null | head -1 || true)
    # iter-19 fix (iter-18 demo Caveat 3): poll for a SPECIFIC
    # QA-emitted review rather than any review. iter-18 demo run #2
    # broke the loop the moment PM unprompted-wrote a row, killing
    # the dispatcher before Architect/Backend/Designer/Frontend/QA
    # finished. After iter-19 Phase 3 (PM/TL allow-list hardening),
    # PM can no longer call request_human_review at all — this
    # filter is belt-and-braces for that fix.
    qa_review_count=$(curl -sf -H "Authorization: Bearer $OWNER_TOKEN" \
        http://127.0.0.1:8000/api/reviews 2>/dev/null \
        | python3 -c 'import sys, json; data = json.load(sys.stdin); print(sum(1 for r in data if r.get("requesting_agent") == "qa_engineer"))' 2>/dev/null \
        || echo 0)
    if [[ "$qa_review_count" -ge 1 ]]; then
        ok "QA produced a pending_review (qa_engineer count=$qa_review_count)"
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

step "6.5/7 — Auto-retry any BLOCKED Backend tasks (iter-17 defense-in-depth — should not fire if iter-17's MCP fix held)"
if [[ "$qa_review_count" -lt 1 ]]; then
    # Query via `docker exec` against the postgres container so we
    # don't depend on the host having a compatible psql client
    # (iter-13 demo first run hit "password authentication failed"
    # against the host's homebrew psql). `|| true` is defensive — any
    # error here just leaves BLOCKED_TASK_ID empty and we skip the
    # retry path.
    BLOCKED_TASK_ID=$(docker exec ai_team_postgres psql -U ai_team -d ai_team -t -A -c "
        SELECT payload_json -> 'payload' ->> 'task_id'
        FROM audit_log
        WHERE correlation_id = '$CORRELATION'
          AND sender = 'backend_developer'
          AND payload_json -> 'payload' ->> 'status' = 'blocked'
        ORDER BY id DESC LIMIT 1;
    " 2>/dev/null | tr -d '[:space:]' || true)
    if [[ -n "$BLOCKED_TASK_ID" ]]; then
        ok "Backend is BLOCKED on task $BLOCKED_TASK_ID — issuing ai-team retry-blocked"
        uv run ai-team retry-blocked "$BLOCKED_TASK_ID" || true
        # Wait up to 15 more minutes for Backend's retry to produce a terminal
        # report + QA's pending_review to materialise. Backend's retry uses
        # the SAME dispatcher process so --resume is selected from the
        # in-memory cache (no iter-13 fix path needed here; the fix protects
        # against restart-between-attempts which is harder to script).
        deadline=$((SECONDS + 900))
        while (( SECONDS < deadline )); do
            qa_review_count=$(curl -sf -H "Authorization: Bearer $OWNER_TOKEN" \
                http://127.0.0.1:8000/api/reviews 2>/dev/null \
                | python3 -c 'import sys, json; data = json.load(sys.stdin); print(sum(1 for r in data if r.get("requesting_agent") == "qa_engineer"))' 2>/dev/null \
                || echo 0)
            if [[ "$qa_review_count" -ge 1 ]]; then
                ok "QA produced pending_review after Backend retry (qa_engineer count=$qa_review_count)"
                break
            fi
            sleep 10
        done
    else
        echo "(no BLOCKED Backend task — chain may have closed without needing retry)"
    fi
else
    echo "(chain already closed OR psql not available)"
fi

step "6.6/7 — Auto-approve any pending_reviews (close the loop)"
# iter-19 fix (iter-18 demo Caveat 4): belt-and-braces fallback.
# iter-18 run #2 hit JSONDecodeError on empty stdin even though the
# API was responsive — bash precedence on `$(... || echo '[]')` is
# fragile under `set -u -o pipefail`. Assign curl output (allowing
# failure via `|| true`), then `${VAR:-[]}` to guarantee non-empty
# input to python. `printf '%s'` avoids `echo`'s leading-hyphen /
# backslash-interpretation quirks on some platforms.
REVIEWS_JSON=$(curl -sf -H "Authorization: Bearer $OWNER_TOKEN" \
    http://127.0.0.1:8000/api/reviews 2>/dev/null || true)
REVIEWS_JSON="${REVIEWS_JSON:-[]}"
printf '%s' "$REVIEWS_JSON" | python3 <<'PY' || true
import json, subprocess, sys
data = json.load(sys.stdin)
if not data:
    print("(no pending_reviews — chain didn't reach QA)")
else:
    for r in data:
        rid = r["id"]
        print(f"approving {rid} ({r.get('requesting_agent','?')}: {r.get('summary','')[:80]})")
        subprocess.run(
            ["uv", "run", "ai-team", "approve", rid,
             "--comment", "iter-20 demo auto-approve"],
            check=False,
        )
PY

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

echo
echo "--- BLOCKED tasks (iter-11: candidates for retry-blocked): ---"
if command -v psql >/dev/null 2>&1; then
    PGPASSWORD=ai_team psql -h 127.0.0.1 -U ai_team ai_team -t -c "
        SELECT payload_json -> 'payload' ->> 'task_id'    AS task_id,
               sender                                      AS agent,
               payload_json -> 'payload' ->> 'blocked_on'  AS blocked_on
        FROM audit_log
        WHERE correlation_id = '$CORRELATION'
          AND message_type = 'task_report'
          AND payload_json -> 'payload' ->> 'status' = 'blocked'
        ORDER BY id;
    " 2>/dev/null || echo "(no BLOCKED tasks)"
fi

cat <<NOTE

If a Backend BLOCKED row appeared above, retry it with:
   uv run ai-team retry-blocked <task_id>
Then run \`uv run ai-team watch --correlation ${CORRELATION:0:8}\`
in another terminal to see the chain continue. The retry counter
caps at 5 attempts per task_id.

To approve the QA result and close the loop:
   uv run ai-team approve <id>

Ctrl+C the watch terminal when done; this script will clean up.
NOTE
