#!/usr/bin/env bash
# =============================================================================
# Scenario B — page 6: import the datasource + dashboard into Grafana via API.
#
# Why not file provisioning: when the repository lives on a VirtualBox shared
# folder (vboxsf), the bind mount into /etc/grafana/provisioning is not readable
# by Grafana's user (472) -> "permission denied" -> nothing is provisioned.
# The API import stores the datasource and dashboard in Grafana's own database
# (the grafana_data volume), independent of the shared folder.
#
# Usage:  ./scripts/grafana-import.sh
# =============================================================================
set -uo pipefail
HERE=$(cd "$(dirname "$0")/.." && pwd)
set -a; . "$HERE/.env"; set +a

GRAF="http://127.0.0.1:${GRAFANA_PORT:-3000}"
AUTH="${GRAFANA_USERNAME:-open5gs}:${GRAFANA_PASSWORD:-open5gs}"
DS_UID="PA240B69645956401"          # must match the UID used in the dashboard JSON
DS_URL="http://${METRICS_IP}:${METRICS_BIND_PORT}"
DASH="$HERE/grafana/dashboards/open5gs_dashboard.json"

curl -sf -o /dev/null "$GRAF/api/health" || { echo "Grafana not reachable at $GRAF"; exit 1; }
[[ -f "$DASH" ]] || { echo "missing $DASH"; exit 1; }

echo "[import] Grafana OK at $GRAF"

# --- datasource -------------------------------------------------------------
code=$(curl -s -o /dev/null -w '%{http_code}' -u "$AUTH" "$GRAF/api/datasources/uid/$DS_UID")
if [[ "$code" == "200" ]]; then
    echo "[import] datasource $DS_UID already present"
else
    echo "[import] creating datasource 'Open5Gs' ($DS_UID) -> $DS_URL"
    curl -s -u "$AUTH" -X POST "$GRAF/api/datasources" -H 'Content-Type: application/json' \
        -d "{\"name\":\"Open5Gs\",\"type\":\"prometheus\",\"uid\":\"$DS_UID\",\"access\":\"proxy\",\"url\":\"$DS_URL\",\"isDefault\":true,\"jsonData\":{}}" \
        | python3 -c "import json,sys;d=json.load(sys.stdin);print('  ',d.get('message','ok'),d.get('uid',''))" 2>/dev/null || true
fi

# --- dashboard --------------------------------------------------------------
tmp=$(mktemp)
python3 - "$DASH" > "$tmp" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
print(json.dumps({"dashboard": d, "overwrite": True, "folderUid": "", "message": "scenario-b import"}))
PY
echo "[import] importing dashboard 'Open5GS'"
curl -s -u "$AUTH" -X POST "$GRAF/api/dashboards/db" -H 'Content-Type: application/json' -d @"$tmp" \
    | python3 -c "import json,sys;d=json.load(sys.stdin);print('  status:',d.get('status'),'| url:',d.get('url'),'|',d.get('message',''))" 2>/dev/null || true
rm -f "$tmp"

# --- verify -----------------------------------------------------------------
echo "[import] dashboards now:"
curl -s -u "$AUTH" "$GRAF/api/search?type=dash-db" \
    | python3 -c "import json,sys;d=json.load(sys.stdin);[print(f\"    {x['title']}  folder={x.get('folderTitle')}  uid={x['uid']}\") for x in d] or print('    (none)')" 2>/dev/null || true

echo
echo "[import] done. Open $GRAF/dashboards -> folder 'General' -> 'Open5GS'"
