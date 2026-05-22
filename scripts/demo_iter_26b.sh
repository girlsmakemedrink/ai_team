#!/usr/bin/env bash
# iter-26b demo — single-candidate validator runs MR validate_competitors +
# Architect validate_tech_risk + PM validate_revenue_model in parallel, then
# QA synthesize_validation gates on all three and emits a go/pivot/kill
# pending_review.
#
# Spec: docs/superpowers/specs/2026-05-22-iter-26b-single-candidate-validator-design.md
# Plan: docs/iterations/iter_26b.md
#
# Run:    ./scripts/demo_iter_26b.sh [slug] [depth]
#         (defaults: telegram-tech-publisher / standard)
# Stop:   Ctrl-C; the post-success drain (60s after success-detection)
#         must complete before reporting metrics.
#
# Prerequisites:
#   - .env populated (make dev does this)
#   - `claude` CLI authenticated (Claude Code subscription)
#   - Docker Desktop running
#   - .venv exists (uv sync has been run)
#
# Cost envelope (depth=standard): $8-14 expected, $16 worst case.
# Wall-clock: 15-25 min (3 parallel + 1 gated QA).

set -euo pipefail
cd "$(dirname "$0")/.."

step() { printf "\n\033[1;34m▶ %s\033[0m\n" "$*"; }
ok()   { printf "\033[1;32m✓ %s\033[0m\n" "$*"; }
bail() { printf "\033[1;31m✗ %s\033[0m\n" "$*" >&2; exit 1; }

SLUG="${1:-telegram-tech-publisher}"
DEPTH="${2:-standard}"
CANDIDATE_FILE="${CANDIDATE_FILE:-docs/products/_candidates/_brainstorm_creator_tools.md}"
CONSTRAINTS_JSON="${CONSTRAINTS_JSON:-scripts/iter_26b_constraints.json}"

[ -f .env ]                               || bail ".env not found. Run \`make dev\` first."
command -v claude >/dev/null 2>&1         || bail "claude CLI not on PATH."
command -v docker >/dev/null 2>&1         || bail "docker not on PATH."
[ -x ".venv/bin/python" ]                 || bail ".venv/bin/python not found. Run \`uv sync\` (or \`make dev\`) first."
[ -f "$CANDIDATE_FILE" ]                  || bail "candidate file not found: $CANDIDATE_FILE"
[ -f "$CONSTRAINTS_JSON" ]                || bail "constraints JSON not found: $CONSTRAINTS_JSON"

LOG_DIR="docs/iterations/iter_26b_demo_logs"
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
_cleanup_iter26b() {
    kill "$API_PID" 2>/dev/null || true
    # Preserve the API log for post-mortem (iter-25 lesson: never rm -f the log).
    if [[ -f "$API_LOG" ]]; then
        SHORT_CID="${CORRELATION:0:8}"
        DEST="$LOG_DIR/${SHORT_CID:-unknown}_${SLUG}_api_$RUN_TS.log"
        mv "$API_LOG" "$DEST" 2>/dev/null || cp "$API_LOG" "$DEST" 2>/dev/null || true
        echo "API log preserved: $DEST"
    fi
}
trap _cleanup_iter26b EXIT
until curl -sf http://127.0.0.1:8000/health >/dev/null 2>&1; do sleep 1; done
ok "API ready (pid $API_PID)"

if [[ "${AI_TEAM_DEMO_NON_INTERACTIVE:-0}" != "1" ]] && [[ -t 0 ]]; then
    cat <<NOTE

  Demo will validate slug='$SLUG' at depth='$DEPTH'.
  Cost envelope: \$8-14 (standard) / \$4-7 (quick) / \$14-22 (deep).

  In another terminal, watch the feed:
    uv run ai-team watch

  Press ENTER to submit the validation task. (Set
  AI_TEAM_DEMO_NON_INTERACTIVE=1 or close stdin to skip this prompt.)

NOTE
    # `|| true` so EOF on stdin doesn't trip `set -e` (autonomous-loop runs
    # without a tty pipe stdin from /dev/null; that yields exit 1 from read).
    read -r || true
fi

step "5/7 — Submit validate-product task"
SUBMIT_OUT=$(uv run ai-team validate-product \
    --slug "$SLUG" \
    --candidate-file "$CANDIDATE_FILE" \
    --depth "$DEPTH" \
    --constraints-json "$CONSTRAINTS_JSON" 2>&1)
echo "$SUBMIT_OUT"
CORRELATION=$(echo "$SUBMIT_OUT" | grep -oE '[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}' | head -1)
[ -n "$CORRELATION" ] || bail "could not parse correlation_id from CLI output"
ok "submitted (correlation $CORRELATION)"

step "6/7 — Poll for QA pending_review (≤30 min)"
# QA's safety net writes a pending_reviews row with requesting_agent='qa_engineer'
# once the validate chain completes. iter-26b's 3 parallel agents target three
# different roles (MR/Architect/PM), so the dispatcher per-role serialization
# issue does NOT apply — max wall-clock is max(MR, Arch, PM) + QA, ~15-25 min.
# Budget 30 min for slack on real-LLM variance.
deadline=$((SECONDS + 1800))
qa_review_count=0
loop_minute=0
while (( SECONDS < deadline )); do
    qa_review_count=$(curl -sf -H "Authorization: Bearer $OWNER_TOKEN" \
        http://127.0.0.1:8000/api/reviews 2>/dev/null \
        | python3 -c 'import sys, json; data = json.load(sys.stdin); print(sum(1 for r in data if r.get("requesting_agent") == "qa_engineer"))' 2>/dev/null \
        || echo 0)
    if [[ "${qa_review_count:-0}" -ge 1 ]]; then
        ok "QA produced a pending_review (qa_engineer count=$qa_review_count)"
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
    echo "DEMO FAILED — no QA pending_review after 30 min." >&2
    echo "Run log: $LOG_DIR"
    exit 1
fi

step "6.5/7 — Validation summary preview"
SUMMARY_MD="docs/products/$SLUG/_validation_summary.md"
if [[ -f "$SUMMARY_MD" ]]; then
    echo "--- $SUMMARY_MD (YAML block + first ~20 lines) ---"
    head -25 "$SUMMARY_MD" || true
    echo
    REC=$(grep -E '^recommendation: ' "$SUMMARY_MD" | head -1 | sed 's/^recommendation: //')
    [ -n "$REC" ] && ok "QA recommendation: $REC"
else
    echo "(no _validation_summary.md found at $SUMMARY_MD — chain may be incomplete)"
fi

step "6.6/7 — List pending_reviews (DO NOT auto-approve)"
# iter-26b contract: owner reviews _validation_summary.md and decides go/pivot/
# kill in the approval comment. Auto-approve would defeat the purpose.
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
    print("Owner: review _validation_summary.md, then approve with a decision, e.g.")
    print("   uv run ai-team approve <id> --comment 'decision: go — <rationale>'")
    print("   uv run ai-team approve <id> --comment 'decision: pivot to <next-slug> — <why>'")
    print("   uv run ai-team approve <id> --comment 'decision: kill — <what changed>'")
PY

step "7/7 — Collect demo report"
REPORT="$LOG_DIR/demo_report_${SLUG}_$RUN_TS.md"
{
    echo "# iter-26b demo report — $RUN_TS"
    echo
    echo "- slug: $SLUG"
    echo "- depth: $DEPTH"
    echo "- correlation_id: $CORRELATION"
    echo
    echo "## Per-message audit"
    echo
    docker exec ai_team_postgres psql -U ai_team -d ai_team -c "
        SELECT id, sender, recipient, message_type,
               payload_json -> 'metadata' -> 'llm' ->> 'model'                       AS model,
               (payload_json -> 'metadata' -> 'llm' ->> 'tokens_in')::int            AS tokens_in,
               (payload_json -> 'metadata' -> 'llm' ->> 'tokens_out')::int           AS tokens_out,
               (payload_json -> 'metadata' -> 'llm' ->> 'cached_input')::int         AS cached_input,
               (payload_json -> 'metadata' -> 'llm' ->> 'cost_cents')::int           AS cost_cents,
               (payload_json -> 'metadata' -> 'llm' ->> 'duration_ms')::int          AS duration_ms
        FROM audit_log WHERE correlation_id = '$CORRELATION' ORDER BY id;
    " 2>/dev/null || echo "(psql query failed)"
    echo
    for f in "docs/products/$SLUG/competitors.md" \
             "docs/products/$SLUG/tech_risk.md" \
             "docs/products/$SLUG/revenue.md" \
             "docs/products/$SLUG/_validation_summary.md"; do
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
echo "--- iter-26b ACCEPTANCE CRITERION: QA-emitted pending_reviews row + 4 artifacts ---"
final_qa_count=$(docker exec ai_team_postgres psql -U ai_team -d ai_team -t -A -c \
    "SELECT count(*) FROM pending_reviews WHERE requesting_agent='qa_engineer' AND correlation_id='$CORRELATION';" \
    2>/dev/null | tr -d '[:space:]' || echo 0)
artifact_count=0
for f in "docs/products/$SLUG/competitors.md" \
         "docs/products/$SLUG/tech_risk.md" \
         "docs/products/$SLUG/revenue.md" \
         "docs/products/$SLUG/_validation_summary.md"; do
    [ -f "$f" ] && artifact_count=$((artifact_count + 1))
done
if [[ "${final_qa_count:-0}" -ge 1 ]] && [[ "$artifact_count" -eq 4 ]]; then
    ok "iter-26b CRITERION MET — qa_review=$final_qa_count, artifacts=$artifact_count/4 for correlation ${CORRELATION:0:8}"
else
    printf "\033[1;31m✗ iter-26b CRITERION NOT MET — qa_review=%s, artifacts=%s/4 for correlation %s\033[0m\n" \
        "${final_qa_count:-0}" "$artifact_count" "${CORRELATION:0:8}"
fi

echo
echo "--- Pending reviews (full list, all statuses): ---"
uv run ai-team list-pending 2>/dev/null || true
echo
echo "--- Latest checkpoint digest: ---"
uv run ai-team digest --history --limit 5 2>/dev/null || true
echo
echo "--- Candidate output files: ---"
ls -la "docs/products/$SLUG/" 2>/dev/null || echo "(no candidate dir yet)"
echo
echo "==> Done. Report: $REPORT"
cat <<NOTE

To record your decision and seed the next iteration:
   uv run ai-team approve <id> --comment "decision: go|pivot|kill — <rationale>"

NOTE
