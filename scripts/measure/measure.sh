#!/usr/bin/env bash
# =============================================================================
# Scenario A — Step 3: full measurement set for one network condition.
#
# Measures (UE 10.0.1.10 -> services 10.0.4.x):
#   - ICMP RTT + loss           (ping x20, 3 runs)
#   - HTTP response time        (curl x10, 3 runs)
#   - TCP throughput            (iperf3, 3 runs)
#   - UDP throughput/loss/jitter(iperf3 -u -b 10M, 3 runs)
#   - TCP retransmissions       (rate-capped transfer + capture at ue:eth0)
#
# Results: results/step3/<label>/*  and appended rows in results/step3/summary.csv
# Usage:  sudo ./scripts/measure/measure.sh <label>
# =============================================================================
set -uo pipefail
export LC_ALL=C

LABEL="${1:?usage: measure.sh <label>}"
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
OUT="$ROOT/results/step3/$LABEL"
SUMMARY="$ROOT/results/step3/summary.csv"
mkdir -p "$OUT"
[[ $EUID -eq 0 ]] || { echo "Run as root (sudo)."; exit 1; }

UE() { ip netns exec ue "$@"; }
[[ -f $SUMMARY ]] || echo "condition,metric,run,value,unit" > "$SUMMARY"

# Drop any previous rows for this condition so re-running replaces them
# instead of appending duplicates (lets us re-measure a single condition).
if [[ -f $SUMMARY ]]; then
    tmp=$(mktemp)
    awk -F, -v c="$LABEL" 'NR==1 || $1 != c' "$SUMMARY" > "$tmp" && mv "$tmp" "$SUMMARY"
fi

# Use unconfined tshark under Ubuntu's AppArmor profile; fall back otherwise.
if command -v aa-exec >/dev/null 2>&1; then
    TS() { aa-exec -p unconfined -- tshark "$@"; }
else
    TS() { tshark "$@"; }
fi

# Run one iperf3 measurement, validate the JSON and retry once on failure.
# (The `delay` condition once produced "Connection reset by peer", which used
# to silently shrink the sample to n=2.)
run_tcp() { # <run>
    local run=$1 attempt
    for attempt in 1 2; do
        UE iperf3 -c 10.0.4.20 -t 3 -J > "$OUT/tcp-run$run.json" 2>/dev/null
        if python3 -c 'import json,sys
d=json.load(open(sys.argv[1]))
sys.exit(0 if "sum_received" in d.get("end",{}) else 1)' "$OUT/tcp-run$run.json" 2>/dev/null; then
            return 0
        fi
        echo "[measure] WARN: tcp run $run attempt $attempt failed, retrying" >&2
        sleep 1
    done
    return 1
}

run_udp() { # <run>
    local run=$1 attempt
    for attempt in 1 2; do
        UE iperf3 -c 10.0.4.20 -u -b 10M -t 3 -J > "$OUT/udp-run$run.json" 2>/dev/null
        if python3 -c 'import json,sys
d=json.load(open(sys.argv[1]))
sys.exit(0 if "sum" in d.get("end",{}) else 1)' "$OUT/udp-run$run.json" 2>/dev/null; then
            return 0
        fi
        echo "[measure] WARN: udp run $run attempt $attempt failed, retrying" >&2
        sleep 1
    done
    return 1
}

echo "[measure] condition=$LABEL"

# --- ICMP RTT / loss (3 x 20 probes)
for run in 1 2 3; do
    out=$(UE ping -c 20 -i 0.2 -W 2 10.0.4.10)
    echo "$out" > "$OUT/ping-run$run.txt"
    loss=$(echo "$out" | grep -oE '[0-9]+% packet loss' | grep -oE '^[0-9]+')
    avg=$(echo "$out" | awk -F'/' '/rtt|round-trip/ {print $5}')
    echo "$LABEL,icmp_loss,run$run,${loss:-0},percent" >> "$SUMMARY"
    echo "$LABEL,icmp_rtt_avg,run$run,${avg:-0},ms" >> "$SUMMARY"
done

# --- HTTP response time, connection establishment time and availability
# (3 x 10 requests; each raw line is: time_total time_connect http_code)
for run in 1 2 3; do
    : > "$OUT/http-run$run.txt"
    ok=0; total=0
    for _ in $(seq 1 10); do
        line=$(UE curl -s -o /dev/null \
            -w '%{time_total} %{time_connect} %{http_code}\n' \
            --max-time 5 http://10.0.4.10/ 2>/dev/null || echo "0.000000 0.000000 000")
        echo "$line" >> "$OUT/http-run$run.txt"
        total=$((total + 1))
        [[ "$(echo "$line" | awk '{print $3}')" == "200" ]] && ok=$((ok + 1))
    done
    read -r avg conn < <(awk '{s+=$1;c+=$2;n++} END{if(n) printf "%.4f %.6f", s/n, c/n}' "$OUT/http-run$run.txt")
    avail=$(( total ? ok * 100 / total : 0 ))
    echo "$LABEL,http_time_avg,run$run,${avg:-0},s" >> "$SUMMARY"
    echo "$LABEL,http_connect_avg,run$run,${conn:-0},s" >> "$SUMMARY"
    echo "$LABEL,http_availability,run$run,$avail,percent" >> "$SUMMARY"
done

# --- TCP throughput (3 x 3 s)
for run in 1 2 3; do
    if run_tcp "$run"; then
        bps=$(python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); print(d["end"]["sum_received"]["bits_per_second"])' "$OUT/tcp-run$run.json")
        echo "$LABEL,tcp_throughput,run$run,$bps,bit/s" >> "$SUMMARY"
    else
        echo "$LABEL,tcp_throughput,run$run,NA,failed" >> "$SUMMARY"
    fi
done

# --- UDP throughput / loss / jitter (3 x 3 s at 10 Mbit/s)
for run in 1 2 3; do
    if run_udp "$run"; then
        python3 - "$OUT/udp-run$run.json" "$LABEL" "$run" "$SUMMARY" <<'PY'
import json, sys
path, label, run, summary = sys.argv[1:5]
s = json.load(open(path))["end"]["sum"]
with open(summary, "a") as f:
    f.write(f"{label},udp_throughput,{run},{s['bits_per_second']},bit/s\n")
    f.write(f"{label},udp_loss,{run},{s['lost_percent']},percent\n")
    f.write(f"{label},udp_jitter,{run},{s.get('jitter_ms', 0)},ms\n")
PY
    else
        echo "$LABEL,udp_throughput,$run,NA,failed" >> "$SUMMARY"
        echo "$LABEL,udp_loss,$run,NA,failed" >> "$SUMMARY"
        echo "$LABEL,udp_jitter,$run,NA,failed" >> "$SUMMARY"
    fi
done

# --- TCP retransmissions (rate-capped transfer + capture at ue:eth0)
# timeout bounds the capture so the backgrounded tcpdump always terminates.
ip netns exec ue timeout 8 tcpdump -i eth0 -w "$OUT/retrans.pcap" -U -q tcp port 5201 &
cap=$!
sleep 1
UE iperf3 -c 10.0.4.20 -b 20M -t 5 > "$OUT/tcp-retrans-source.txt" 2>&1
wait "$cap" 2>/dev/null || true
# Count all retransmission kinds (plain + fast), then cross-check with iperf3's
# own sender counter reported in tcp-retrans-source.txt.
n=$(TS -r "$OUT/retrans.pcap" \
      -Y 'tcp.analysis.retransmission or tcp.analysis.fast_retransmission' \
      -T fields -e frame.number 2>/dev/null | grep -c .)
echo "$LABEL,tcp_retransmissions,total,${n:-0},count" >> "$SUMMARY"
src=$(awk '/[[:space:]]sender[[:space:]]*$/{print $(NF-1); exit}' "$OUT/tcp-retrans-source.txt")
echo "$LABEL,tcp_retransmissions_sender,total,${src:-NA},count" >> "$SUMMARY"

[[ -n "${SUDO_USER:-}" ]] && chown -R "$SUDO_USER:$SUDO_USER" "$ROOT/results/step3" 2>/dev/null || true
echo "[measure] done: $OUT"
