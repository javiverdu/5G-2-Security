#!/usr/bin/env bash
# =============================================================================
# Scenario B — page 5: run baseline + degraded conditions end to end.
#
# Usage:  sudo ./scripts/run-all.sh
# =============================================================================
set -uo pipefail
HERE=$(cd "$(dirname "$0")/.." && pwd)          # scenario-b
ROOT=$(cd "$(dirname "$0")/../.." && pwd)       # repo root
OUT="$ROOT/results/scenario-b"
[[ $EUID -eq 0 ]] || { echo "run with sudo"; exit 1; }
mkdir -p "$OUT"
echo "condition,metric,run,value,unit" > "$OUT/summary.csv"

for cond in baseline delay loss rate; do
    "$HERE/scripts/impair.sh" "$cond" | tee "$OUT/tc-$cond.txt"
    "$HERE/scripts/measure.sh" "$cond"
done

"$HERE/scripts/impair.sh" baseline > "$OUT/tc-final-clean.txt"

echo
echo "[run-all] comparative summary:"
column -s, -t "$OUT/summary.csv" 2>/dev/null || cat "$OUT/summary.csv"
