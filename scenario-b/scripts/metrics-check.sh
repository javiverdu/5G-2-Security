#!/usr/bin/env bash
# =============================================================================
# Scenario B — page 6: check the observability stack (Prometheus + Grafana)
#
# Prometheus is the upstream 'metrics' container (host port 9090); Grafana is
# the 'grafana' container (host port 3000, open5gs/open5gs). The Open5GS NFs
# expose metrics on :9091 and Prometheus scrapes them.
#
# Usage:  ./scripts/metrics-check.sh
# =============================================================================
set -uo pipefail
HERE=$(cd "$(dirname "$0")/.." && pwd)
set -a; . "$HERE/.env"; set +a
PROM="http://127.0.0.1:${METRICS_BIND_PORT:-9090}"
GRAF="http://127.0.0.1:3000"

echo "== containers =="
for c in metrics grafana; do
    printf '  %-8s %s\n' "$c" "$(docker inspect -f '{{.State.Status}}' "$c" 2>/dev/null || echo missing)"
done

echo
echo "== Prometheus targets ($PROM) =="
if curl -sf "$PROM/api/v1/targets" -o /tmp/opencode_prom_targets.json; then
    python3 - <<'PY'
import json
d = json.load(open("/tmp/opencode_prom_targets.json"))["data"]["activeTargets"]
for t in sorted(d, key=lambda x: x["labels"]["job"]):
    print(f"  {t['labels']['job']:6s} {t['health']:8s} {t['scrapeUrl']}")
PY
else
    echo "  Prometheus not reachable at $PROM (is the 'metrics' container up?)"
fi

echo
echo "== Open5GS metric names (sample) =="
curl -sf "$PROM/api/v1/label/__name__/values" \
    | python3 -c "import json,sys;[print('  '+m) for m in json.load(sys.stdin)['data'] if 'fivegs' in m or 'session' in m.lower()]" 2>/dev/null | head -30

echo
echo "== Grafana =="
curl -sf -o /dev/null -w '  Grafana HTTP %{http_code} at %{url_effective}\n' "$GRAF/login" \
    || { echo "  Grafana not reachable at $GRAF"; exit 1; }

echo "  datasources (login ${GRAFANA_USERNAME}/${GRAFANA_PASSWORD}):"
curl -sf -u "${GRAFANA_USERNAME}:${GRAFANA_PASSWORD}" "$GRAF/api/datasources" \
  | python3 -c "import json,sys;[print(f\"    {d['name']:<10} {d['type']:<10} uid={d['uid']} url={d.get('url')}\") for d in json.load(sys.stdin)]" 2>/dev/null \
  || echo "    (could not query; check GF_SECURITY_ADMIN creds)"

echo "  dashboards (search):"
curl -sf -u "${GRAFANA_USERNAME}:${GRAFANA_PASSWORD}" "$GRAF/api/search?type=dash-db" \
  | python3 -c "import json,sys;d=json.load(sys.stdin);[print(f\"    {x['title']:<12} folder={x.get('folderTitle')} uid={x['uid']}\") for x in d] or print('    (none provisioned)')" 2>/dev/null \
  || echo "    (could not query)"

echo
echo "  If the dashboard is missing, provision a provider error is logged in:"
echo "    docker logs grafana | grep -iE 'provision|dashboard|datasource|error'"
echo "  If the panels show 'datasource not found', the dashboard expects datasource"
echo "  uid PA240B69645956401; see docs/observability.md (UID note)."
