#!/usr/bin/env bash
# =============================================================================
# Scenario B — page 6: (re)install the Grafana provisioning and verify it.
#
# The upstream dashboard expects a fixed datasource UID that its own datasource
# file does not set, so provisioning can end up with no working dashboard. This
# installs scenario-b/grafana/* over the upstream clone and restarts Grafana.
#
# Usage:  ./scripts/grafana-fix.sh
# =============================================================================
set -uo pipefail
HERE=$(cd "$(dirname "$0")/.." && pwd)          # scenario-b
UP="$HERE/upstream"
set -a; . "$HERE/.env" 2>/dev/null || true; set +a

[[ -d "$UP" ]] || { echo "run scripts/fetch-upstream.sh first"; exit 1; }

echo "[grafana] installing provisioning files into $UP/grafana"
mkdir -p "$UP/grafana/datasources" "$UP/grafana/dashboards"
cp "$HERE"/grafana/datasources/* "$UP/grafana/datasources/"
cp "$HERE"/grafana/dashboards/*  "$UP/grafana/dashboards/"

echo "[grafana] restarting grafana"
docker restart grafana >/dev/null

printf '[grafana] waiting to come up'
for _ in $(seq 1 30); do
    curl -sf -o /dev/null http://127.0.0.1:3000/api/health && { echo " ...ok"; break; }
    printf '.'; sleep 2
done

AUTH="${GRAFANA_USERNAME:-open5gs}:${GRAFANA_PASSWORD:-open5gs}"
echo
echo "[grafana] datasources:"
curl -s -u "$AUTH" http://127.0.0.1:3000/api/datasources \
  | python3 -c "import json,sys;[print(f\"  {d['name']:<10} {d['type']:<10} uid={d['uid']} url={d.get('url')}\") for d in json.load(sys.stdin)]" 2>/dev/null \
  || echo "  (could not query)"

echo "[grafana] dashboards:"
curl -s -u "$AUTH" 'http://127.0.0.1:3000/api/search?type=dash-db' \
  | python3 -c "import json,sys;d=json.load(sys.stdin);[print(f\"  {x['title']:<12} folder={x.get('folderTitle')} uid={x['uid']}\") for x in d] or print('  (none)')" 2>/dev/null \
  || echo "  (could not query)"

echo
echo "[grafana] provisioning log (last lines):"
docker logs grafana 2>&1 | grep -iE 'provision|dashboard|datasource|error' | tail -15 || true

echo
echo "[grafana] open http://127.0.0.1:3000 -> Dashboards -> folder 'Services' -> 'Open5GS'"
