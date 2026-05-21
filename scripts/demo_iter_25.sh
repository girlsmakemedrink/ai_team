#!/usr/bin/env bash
# Iter-25 demo: same 6-stage DAG as iter-10..24 (PM → Architect
# → Backend | Designer → Frontend → QA). iter-25 is a
# REPRODUCIBILITY iteration — same shape as iter-25 demo
# (which produced the first-ever clean chain), with a single
# operational improvement: a 60-second post-success drain so
# QA's `task_report` audit row gets written before EXIT trap
# shutdown.
#
# iter-25 ran ONCE and produced the criterion. iter-25 runs
# this script 2 more times to confirm Backend DONE is stable
# across LLM samples — N=3 total counting iter-25.
#
# Inherits all iter-25 architecture:
#
#   1. iter-25 Phase 2: TL summary-prefix scope detection.
#      _maybe_route_blocked now treats `summary.startswith(
#      "Scope pre-flight")` as the canonical self-eject signal,
#      regardless of `blocked_on` content. Backend's prompt
#      template structurally enforces that prefix; the
#      `blocked_on` field stays as a fallback for legacy
#      messages. iter-23 R#1 stalled because the LLM filled
#      blocked_on with a free-form sentence; this signal is
#      immune to that drift.
#
#   2. iter-25 Phase 3: Backend prompt instructs the LLM that
#      a missing target directory is NORMAL and should be
#      created via write_file_in_scope — not treated as a
#      scope-too-large self-eject. iter-23 R#1's Backend
#      ejected partly because `examples/` was absent.
#
#   3. iter-25 Phase 1: A/B test proved the iter-23 enum
#      retry-loop theory WRONG. claude -p with enum constraint
#      does not retry/burn budget; it remaps to the nearest
#      valid value. iter-23 R#2's BLOCKED(budget) had a
#      different cause (likely tool-call loop on real work).
#
#   4. iter-25 Phase 4 (this script): demo EXIT trap MOVES
#      the API log to docs/iterations/iter_25_demo_logs/ instead
#      of deleting it. iter-23 lost both runs' logs to the rm.
#
#   5. Inherits all prior iterations' contracts. The iter-23
#      QA safety net (proven 3/3 in e2e) catches any LLM that
#      fails to invoke request_human_review.
#
#   6. Expected outcome: chain reaches QA → QA produces a
#      pending_reviews row (via the iter-23 safety net since
#      the LLM doesn't reliably call the tool) → 5-iteration
#      criterion finally met.
#
# Wall-clock budget: 45 min initial chain + 15 min retry
# window = 60 min total worst case. Cost ceiling: $5.00.
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

step "1.5/7 — Prune stale agent worktrees (iter-25)"
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
MCP_CONFIG="$(pwd)/.iter25-mcp.json"
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
_cleanup_iter25() {
    kill "$API_PID" 2>/dev/null || true
    # iter-25: preserve the API log for post-mortem instead of deleting it.
    # iter-25 demos lost both runs' logs to `rm -f "$API_LOG"`, denying
    # any forensic analysis of the BLOCKED(budget) mystery. Now we MOVE
    # the log into the repo so retro reviewers can read it.
    LOG_DIR="docs/iterations/iter_25_demo_logs"
    mkdir -p "$LOG_DIR"
    if [[ -f "$API_LOG" ]]; then
        SHORT_CID="${CORRELATION:0:8}"
        DEST="$LOG_DIR/${SHORT_CID:-unknown}.log"
        mv "$API_LOG" "$DEST" 2>/dev/null || cp "$API_LOG" "$DEST" 2>/dev/null || true
        echo "API log preserved: $DEST"
    fi
    rm -f "$MCP_CONFIG"
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
trap _cleanup_iter25 EXIT
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
        "title": "iter-25 demo: idea-validator v2 (CLI + landing page + UX brief)",
        "description": "Implement idea-validator per docs/sandbox/idea_validator_v2_spec.md. Decompose into 6 subtasks with depends_on: pm_clarify (PM) → arch (Architect) → {be (Backend), design (Designer)} → fe (Frontend, depends_on=design) → qa (QA, depends_on=[be,fe]). The dispatcher will hold dependent subtasks until predecessors report done. Pass depends_on as slug references in the decomposition JSON.",
        "target_repo": "examples/sandbox/idea-validator"
    }')
CORRELATION=$(echo "$RESP" | python3 -c 'import sys, json; print(json.load(sys.stdin)["correlation_id"])')
ok "submitted (correlation $CORRELATION)"

step "6/7 — Wait for the chain (up to 45 min — iter-25 bump) and surface artifacts"
ADR_DIR="docs/adr"
BACKEND_DIR="examples/sandbox/idea-validator"
DESIGN_BRIEF="docs/design/idea-validator.md"
LANDING_PAGE="apps/web/idea-validator/index.html"
# iter-25 Phase 4: poll window bumped from 30 → 45 min. Matches the
# CLAUDE.md-documented "30 min initial chain + 15 min retry window = 45
# min total" budget. iter-22 demo's poll expired with Backend recovery
# in flight at minute 30 (audit row 342 dispatched at T0+352s, no row
# 344+). The Phase 2 safety net guarantees QA produces the row when
# its turn runs; this extension just gives the chain enough headroom
# to actually reach QA.
deadline=$((SECONDS + 2700))   # 45 minutes (was 30 in iter-22)
qa_review_count=0
loop_minute=0
while (( SECONDS < deadline )); do
    latest_adr=$(ls -1t "$ADR_DIR"/0*.md 2>/dev/null | head -1 || true)
    # iter-19 fix (iter-18 demo Caveat 3): poll for a SPECIFIC
    # QA-emitted review rather than any review.
    qa_review_count=$(curl -sf -H "Authorization: Bearer $OWNER_TOKEN" \
        http://127.0.0.1:8000/api/reviews 2>/dev/null \
        | python3 -c 'import sys, json; data = json.load(sys.stdin); print(sum(1 for r in data if r.get("requesting_agent") == "qa_engineer"))' 2>/dev/null \
        || echo 0)
    if [[ "$qa_review_count" -ge 1 ]]; then
        ok "QA produced a pending_review (qa_engineer count=$qa_review_count)"
        # iter-25: post-success drain. iter-24 demo broke the loop at
        # the moment QA's safety net INSERTed the pending_reviews row;
        # the dispatcher was killed by the EXIT trap before QA's
        # outbound `task_report` reached the audit_writer. Result:
        # missing row 385 in audit_log. The 60-second drain lets the
        # outbound publish + audit_log INSERT complete before shutdown.
        echo "Draining 60s for QA task_report audit write..."
        sleep 60
        rows=$(docker exec ai_team_postgres psql -U ai_team -d ai_team -t -A -c \
            "SELECT count(*) FROM audit_log WHERE correlation_id='$CORRELATION';" 2>/dev/null \
            | tr -d '[:space:]' || echo "?")
        echo "[drain complete] audit_rows=${rows}"
        break
    fi
    # iter-25 Phase 4: per-minute status line so the demo report can
    # reconstruct "what was in flight when the poll expired" without
    # forensic audit_log reverse-engineering (iter-22 retro pain).
    elapsed=$SECONDS
    minute=$(( elapsed / 60 ))
    if (( minute > loop_minute )); then
        loop_minute=$minute
        rows=$(docker exec ai_team_postgres psql -U ai_team -d ai_team -t -A -c \
            "SELECT count(*) FROM audit_log WHERE correlation_id='$CORRELATION';" 2>/dev/null \
            | tr -d '[:space:]' || echo "?")
        echo "[t+${minute}m] audit_rows=${rows} qa_reviews=${qa_review_count}"
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
# iter-21 fix (3-iteration carry-over: iter-18 -> iter-19 -> iter-20).
# Real root cause finally identified post-iter-20: the pattern
#     printf '%s' "$JSON" | python3 <<'PY' ... PY
# is a heredoc-vs-pipe conflict. Bash routes python's stdin to the
# HEREDOC (source code), NOT to the piped JSON, so
# json.load(sys.stdin) parses python source and fails on char 0
# with JSONDecodeError("Expecting value: line 1 column 1 (char 0)").
# iter-18 and iter-19 fix attempts (echo fallback, ${VAR:-[]} +
# printf) both patched the wrong layer.
#
# The fix below: `python3 - "$JSON" <<'PY' ... sys.argv[1]`. The
# `-` arg makes python read source from stdin (the heredoc), and
# the JSON arrives via sys.argv[1]. No conflict.
#
# See docs/iterations/iter_20_demo_report.md §Caveat B and
# docs/iterations/iter_21.md Phase 3. Do NOT re-introduce the
# pipe-into-heredoc pattern in new demo scripts.
REVIEWS_JSON=$(curl -sf -H "Authorization: Bearer $OWNER_TOKEN" \
    http://127.0.0.1:8000/api/reviews 2>/dev/null || true)
REVIEWS_JSON="${REVIEWS_JSON:-[]}"
python3 - "$REVIEWS_JSON" <<'PY' || true
import json, subprocess, sys
data = json.loads(sys.argv[1])
if not data:
    print("(no pending_reviews — chain didn't reach QA)")
else:
    for r in data:
        rid = r["id"]
        print(f"approving {rid} ({r.get('requesting_agent','?')}: {r.get('summary','')[:80]})")
        subprocess.run(
            ["uv", "run", "ai-team", "approve", rid,
             "--comment", "iter-25 demo auto-approve"],
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
echo "--- iter-25 ACCEPTANCE CRITERION: QA-emitted pending_reviews row ---"
# iter-25 demo run #1 found that /api/reviews only returns rows with
# status='pending'. By this step (after 6.6/7 auto-approve) all rows
# are status='approved' and the endpoint shows count=0 — false negative.
# Query the DB directly for ANY qa_engineer-authored row for this
# correlation, regardless of status.
final_qa_count=$(docker exec ai_team_postgres psql -U ai_team -d ai_team -t -A -c \
    "SELECT count(*) FROM pending_reviews WHERE requesting_agent='qa_engineer' AND correlation_id='$CORRELATION';" \
    2>/dev/null | tr -d '[:space:]' || echo 0)
if [[ "$final_qa_count" -ge 1 ]]; then
    ok "iter-25 CRITERION MET — qa_engineer pending_reviews count=$final_qa_count for correlation ${CORRELATION:0:8} (5-iteration deferred row finally landed)"
else
    printf "\033[1;31m✗ iter-25 CRITERION NOT MET — qa_engineer pending_reviews count=%s for correlation %s\033[0m\n" "$final_qa_count" "${CORRELATION:0:8}"
fi
echo
echo "--- Pending reviews (full list, all statuses): ---"
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
