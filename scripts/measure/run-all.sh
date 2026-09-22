#!/usr/bin/env bash
# =============================================================================
# Scenario A — Step 3: run baseline + degraded conditions end to end.
# Resets summary.csv, then for each condition applies NetEm and measures.
# Usage:  sudo ./scripts/measure/run-all.sh
# =============================================================================
set -uo pipefail

ROOT=$(cd "$(dirname "$0")/../.." && pwd)
cd "$ROOT"
SUMMARY="$ROOT/results/step3/summary.csv"
mkdir -p "$ROOT/results/step3"
echo "condition,metric,run,value,unit" > "$SUMMARY"

for cond in baseline delay loss rate; do
    ./scripts/measure/impair.sh "$cond" | tee "$ROOT/results/step3/tc-$cond.txt"
    ./scripts/measure/measure.sh "$cond"
done

# leave the network clean
./scripts/measure/impair.sh baseline > "$ROOT/results/step3/tc-final-clean.txt"

echo
echo "[run-all] comparative summary:"
column -s, -t "$SUMMARY" 2>/dev/null || cat "$SUMMARY"
