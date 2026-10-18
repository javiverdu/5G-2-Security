#!/usr/bin/env bash
# =============================================================================
# Scenario B — fetch the pinned Open5GS + UERANSIM base and prepare our params
#
#  * clones the upstream project into scenario-b/upstream (git-ignored) at a
#    pinned commit, so the deployment is reproducible;
#  * pulls the prebuilt images and tags them with the names the Compose files
#    expect (no local build);
#  * copies scenario-b/.env over upstream/.env.
#
# Usage:  ./scripts/fetch-upstream.sh
# =============================================================================
set -euo pipefail

HERE=$(cd "$(dirname "$0")/.." && pwd)
UP="$HERE/upstream"
REPO="https://github.com/herlesupreeth/docker_open5gs.git"
PIN="1f3bcf73f926b5b7526ef3c41cd2b839c2b17ac3"

command -v docker >/dev/null || { echo "docker not found"; exit 1; }
command -v git    >/dev/null || { echo "git not found"; exit 1; }

echo "[fetch] upstream -> $UP @ $PIN"
if [[ -d "$UP/.git" ]]; then
    git -C "$UP" fetch --all --tags
else
    git clone "$REPO" "$UP"
fi
git -C "$UP" checkout "$PIN"

echo "[fetch] pulling prebuilt images (GHCR) and tagging locally"
pull_tag() { # <src> <dst>
    docker pull "$1"
    docker tag "$1" "$2"
}
pull_tag ghcr.io/herlesupreeth/docker_open5gs:master  docker_open5gs:latest
pull_tag ghcr.io/herlesupreeth/docker_ueransim:master docker_ueransim:latest
pull_tag ghcr.io/herlesupreeth/docker_metrics:master  docker_metrics:latest

echo "[fetch] applying scenario-b/.env"
cp "$HERE/.env" "$UP/.env"

echo "[fetch] patching upf_init.sh so the internet APN is NOT masqueraded (N6 stays un-NATed)"
UPF_INIT="$UP/upf/upf_init.sh"
if [[ -f "$UPF_INIT" ]] && ! grep -q 'UPF_INTERNET_APN_IF_NAME.*--nat_rule' "$UPF_INIT"; then
    sed -i 's|\(--tun_ifname \$UPF_INTERNET_APN_IF_NAME.*\)|& --nat_rule no|' "$UPF_INIT"
fi

echo "[fetch] installing Scenario B Grafana provisioning (datasource + dashboard)"
mkdir -p "$UP/grafana/datasources" "$UP/grafana/dashboards"
cp "$HERE"/grafana/datasources/* "$UP/grafana/datasources/"
cp "$HERE"/grafana/dashboards/*  "$UP/grafana/dashboards/"

echo "[fetch] done. Next: ./scripts/deploy.sh"
