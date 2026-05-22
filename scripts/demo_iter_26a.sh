#!/usr/bin/env bash
# iter-26a demo — uses the team to brainstorm 5 product candidates per
# niche across dev_tools / b2b_smb / creator_tools, then QA ranks and
# requests owner review.
#
# Spec: docs/superpowers/specs/2026-05-22-iter-26a-mr-brainstorm-design.md
# Plan: docs/iterations/iter_26a.md
#
# Run:  ./scripts/demo_iter_26a.sh
# Stop: Ctrl-C; the post-success drain (60s after success-detection)
#       must complete before reporting metrics.
#
# Prerequisites:
#   - .env populated (make dev does this)
#   - `claude` CLI authenticated (Claude Code subscription)
#   - Docker Desktop running
#   - .venv exists (uv sync has been run)

set -euo pipefail
cd "$(dirname "$0")/.."

step() { printf "\n\033[1;34m▶ %s\033[0m\n" "$*"; }
ok()   { printf "\033[1;32m✓ %s\033[0m\n" "$*"; }
bail() { printf "\033[1;31m✗ %s\033[0m\n" "$*" >&2; exit 1; }

[ -f .env ]                               || bail ".env not found. Run \`make dev\` first."
command -v claude >/dev/null 2>&1         || bail "claude CLI not on PATH."
command -v docker >/dev/null 2>&1         || bail "docker not on PATH."
[ -x ".venv/bin/python" ]                 || bail ".venv/bin/python not found. Run \`uv sync\` (or \`make dev\`) first."

LOG_DIR="docs/iterations/iter_26a_demo_logs"
mkdir -p "$LOG_DIR"
RUN_TS="$(date +%Y%m%d_%H%M%S)"
API_LOG=$(mktemp)

step "1/7 — Preflight quota check"
./scripts/preflight_quota_check.sh

step "2/7 — Start infra"
make up >/dev/null
deadline=$((SECONDS + 60))
while (( SECONDS < deadline )); do
    running=$(docker compose -f infra/docker-compose.yml ps --status running --format '{{.Name}}' | wc -l | tr -d ' ')
    if [[ "$running" -ge 4 ]]; then ok "$running services healthy"; break; fi
    sleep 2
done

step "3/7 — Apply migrations"
uv run alembic upgrade head >/dev/null
ok "schema applied"

step "4/7 — Start API + dispatcher in background"
OWNER_TOKEN=$(grep '^OWNER_TOKEN=' .env | cut -d'=' -f2-)
uv run uvicorn apps.api.main:app --host 127.0.0.1 --port 8000 >"$API_LOG" 2>&1 &
API_PID=$!
CORRELATION=""
_cleanup_iter26a() {
    kill "$API_PID" 2>/dev/null || true
    # Preserve the API log for post-mortem (iter-25 lesson: never rm -f the log).
    if [[ -f "$API_LOG" ]]; then
        SHORT_CID="${CORRELATION:0:8}"
        DEST="$LOG_DIR/${SHORT_CID:-unknown}_api_$RUN_TS.log"
        mv "$API_LOG" "$DEST" 2>/dev/null || cp "$API_LOG" "$DEST" 2>/dev/null || true
        echo "API log preserved: $DEST"
    fi
}
trap _cleanup_iter26a EXIT
until curl -sf http://127.0.0.1:8000/health >/dev/null 2>&1; do sleep 1; done
ok "API ready (pid $API_PID)"

if [[ "${AI_TEAM_DEMO_NON_INTERACTIVE:-0}" != "1" ]] && [[ -t 0 ]]; then
    cat <<NOTE

  In another terminal, watch the feed:
    uv run ai-team watch

  Press ENTER to submit the brainstorm task. (Set
  AI_TEAM_DEMO_NON_INTERACTIVE=1 or close stdin to skip this prompt.)

NOTE
    # `|| true` so EOF on stdin doesn't trip `set -e` (autonomous-loop runs
    # without a tty pipe stdin from /dev/null; that yields exit 1 from read).
    read -r || true
fi

step "5/7 — Submit brainstorm-products task"
RESP=$(curl -sf -X POST http://127.0.0.1:8000/api/tasks \
    -H "Authorization: Bearer $OWNER_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{
        "title": "Brainstorm monetizable product candidates",
        "description": "Decompose into 3 parallel market_researcher sub-tasks (one per niche: dev_tools, b2b_smb, creator_tools), then route a qa_engineer sub-task to merge and rank. Constraints in inputs.constraints.",
        "inputs": {
            "intent": "brainstorm_products",
            "niches": ["dev_tools", "b2b_smb", "creator_tools"],
            "candidates_per_niche": 5,
            "constraints": '"$(python3 -c 'import json, sys; print(json.dumps(json.load(open("scripts/iter_26a_constraints.json"))))')"'
        }
    }')
CORRELATION=$(echo "$RESP" | python3 -c 'import sys, json; print(json.load(sys.stdin)["correlation_id"])')
ok "submitted (correlation $CORRELATION)"

step "6/7 — Poll for QA pending_review (≤40 min)"
# QA's safety net always writes a pending_reviews row with
# requesting_agent='qa_engineer' once the brainstorm chain completes.
# We poll /api/reviews for a qa_engineer-authored row rather than
# hitting psql directly, matching the iter-25 polling pattern.
#
# 40 min budget: dispatcher currently serializes per-role (one consumer
# per AgentId — see core/dispatcher/dispatcher.py:96). The 3 MR runs
# execute sequentially, so worst case is 3 × MR_timeout (600s) + QA
# (~60s) = ~31 min. Add slack for WebFetch retries.
deadline=$((SECONDS + 2400))
qa_review_count=0
loop_minute=0
while (( SECONDS < deadline )); do
    qa_review_count=$(curl -sf -H "Authorization: Bearer $OWNER_TOKEN" \
        http://127.0.0.1:8000/api/reviews 2>/dev/null \
        | python3 -c 'import sys, json; data = json.load(sys.stdin); print(sum(1 for r in data if r.get("requesting_agent") == "qa_engineer"))' 2>/dev/null \
        || echo 0)
    if [[ "${qa_review_count:-0}" -ge 1 ]]; then
        ok "QA produced a pending_review (qa_engineer count=$qa_review_count)"
        # iter-25 lesson: post-success drain — let QA's task_report audit
        # row complete before the EXIT trap kills the dispatcher.
        echo "Draining 60s for QA task_report audit write..."
        sleep 60
        rows=$(docker exec ai_team_postgres psql -U ai_team -d ai_team -t -A -c \
            "SELECT count(*) FROM audit_log WHERE correlation_id='$CORRELATION';" 2>/dev/null \
            | tr -d '[:space:]' || echo "?")
        echo "[drain complete] audit_rows=${rows}"
        break
    fi
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

if [[ "${qa_review_count:-0}" -lt 1 ]]; then
    echo "DEMO FAILED — no QA pending_review after 15 min." >&2
    echo "Run log: $LOG_DIR"
    exit 1
fi

step "6.5/7 — List pending_reviews (DO NOT auto-approve)"
# iter-26a contract: owner reviews the brainstorm output and picks the
# top-3 candidate slugs in the approval comment. iter-26b parses that
# comment to seed its idea-validator runs. An auto-approve with a
# generic message would defeat the purpose of the iteration. The list
# below is informational only — Task 13 (owner-manual) closes the loop.
REVIEWS_JSON=$(curl -sf -H "Authorization: Bearer $OWNER_TOKEN" \
    http://127.0.0.1:8000/api/reviews 2>/dev/null || true)
REVIEWS_JSON="${REVIEWS_JSON:-[]}"
python3 - "$REVIEWS_JSON" <<'PY' || true
import json, sys
data = json.loads(sys.argv[1])
if not data:
    print("(no pending_reviews — chain did not reach QA)")
else:
    for r in data:
        rid = r["id"]
        print(f"pending: {rid} ({r.get('requesting_agent','?')}: {r.get('summary','')[:120]})")
    print()
    print("Owner: review _combined_ranking.md, then approve with top-3 slugs, e.g.")
    print("   uv run ai-team approve <id> --comment \"top-3: <slug-1>, <slug-2>, <slug-3>\"")
PY

step "7/7 — Collect demo report"
REPORT="$LOG_DIR/demo_report_$RUN_TS.md"
{
    echo "# iter-26a demo report — $RUN_TS"
    echo
    echo "- correlation_id: $CORRELATION"
    echo
    echo "## Per-message audit"
    echo
    if command -v psql >/dev/null 2>&1; then
        PGPASSWORD=ai_team psql -h 127.0.0.1 -U ai_team ai_team -c "
            SELECT id, sender, recipient, message_type,
                   payload_json -> 'metadata' -> 'llm' ->> 'model'                       AS model,
                   (payload_json -> 'metadata' -> 'llm' ->> 'tokens_in')::int            AS tokens_in,
                   (payload_json -> 'metadata' -> 'llm' ->> 'tokens_out')::int           AS tokens_out,
                   (payload_json -> 'metadata' -> 'llm' ->> 'cached_input')::int         AS cached_input,
                   (payload_json -> 'metadata' -> 'llm' ->> 'cost_cents')::int           AS cost_cents,
                   (payload_json -> 'metadata' -> 'llm' ->> 'duration_ms')::int          AS duration_ms
            FROM audit_log WHERE correlation_id = '$CORRELATION' ORDER BY id;
        " 2>/dev/null || echo "(psql query failed)"
    else
        docker exec ai_team_postgres psql -U ai_team -d ai_team -c "
            SELECT id, sender, recipient, message_type,
                   payload_json -> 'metadata' -> 'llm' ->> 'model'                       AS model,
                   (payload_json -> 'metadata' -> 'llm' ->> 'tokens_in')::int            AS tokens_in,
                   (payload_json -> 'metadata' -> 'llm' ->> 'tokens_out')::int           AS tokens_out,
                   (payload_json -> 'metadata' -> 'llm' ->> 'cached_input')::int         AS cached_input,
                   (payload_json -> 'metadata' -> 'llm' ->> 'cost_cents')::int           AS cost_cents,
                   (payload_json -> 'metadata' -> 'llm' ->> 'duration_ms')::int          AS duration_ms
            FROM audit_log WHERE correlation_id = '$CORRELATION' ORDER BY id;
        " 2>/dev/null || echo "(docker exec psql failed)"
    fi
    echo
    for f in docs/products/_candidates/_brainstorm_dev_tools.md \
             docs/products/_candidates/_brainstorm_b2b_smb.md \
             docs/products/_candidates/_brainstorm_creator_tools.md \
             docs/products/_candidates/_combined_ranking.md; do
        echo "## $f"
        echo
        if [ -f "$f" ]; then
            cat "$f"
        else
            echo "_(missing)_"
        fi
        echo
    done
} > "$REPORT"

echo
echo "--- iter-26a ACCEPTANCE CRITERION: QA-emitted pending_reviews row ---"
final_qa_count=$(docker exec ai_team_postgres psql -U ai_team -d ai_team -t -A -c \
    "SELECT count(*) FROM pending_reviews WHERE requesting_agent='qa_engineer' AND correlation_id='$CORRELATION';" \
    2>/dev/null | tr -d '[:space:]' || echo 0)
if [[ "${final_qa_count:-0}" -ge 1 ]]; then
    ok "iter-26a CRITERION MET — qa_engineer pending_reviews count=$final_qa_count for correlation ${CORRELATION:0:8}"
else
    printf "\033[1;31m✗ iter-26a CRITERION NOT MET — qa_engineer pending_reviews count=%s for correlation %s\033[0m\n" \
        "${final_qa_count:-0}" "${CORRELATION:0:8}"
fi

echo
echo "--- Pending reviews (full list, all statuses): ---"
uv run ai-team list-pending 2>/dev/null || true
echo
echo "--- Latest checkpoint digest: ---"
uv run ai-team digest --history --limit 5 2>/dev/null || true
echo
echo "--- Candidate output files: ---"
ls -la docs/products/_candidates/ 2>/dev/null || echo "(no candidate files yet)"
echo
echo "==> Done. Report: $REPORT"
cat <<NOTE

To approve the QA ranking and pick your top products:
   uv run ai-team approve <id> --comment "top-3: <candidate names>"

NOTE
