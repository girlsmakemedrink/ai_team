#!/usr/bin/env bash
# Regenerate the committed sample report used by the landing page.
# ADR-0012: deterministic via --frozen-timestamp; IDEA_VALIDATOR_REAL_LLM=0 (mock LLM).
# Usage: scripts/refresh_sample.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SAMPLE_DIR="$REPO_ROOT/sample"
TMP_DIR="$(mktemp -d)"

cleanup() { rm -rf "$TMP_DIR"; }
trap cleanup EXIT

cd "$REPO_ROOT"

IDEA_VALIDATOR_REAL_LLM=0 uv run idea-validator analyze \
  --idea "AI tutoring marketplace" \
  --depth quick \
  --frozen-timestamp "2026-01-01T00:00:00" \
  --output-dir "$TMP_DIR"

REPORT_DIR="$(find "$TMP_DIR" -mindepth 1 -maxdepth 1 -type d | head -1)"

mkdir -p "$SAMPLE_DIR"
cp "$REPORT_DIR"/{input.json,competitors.json,market.md,risks.md,differentiators.md,score.json,report.md} "$SAMPLE_DIR/"

echo "Sample refreshed at $SAMPLE_DIR"
