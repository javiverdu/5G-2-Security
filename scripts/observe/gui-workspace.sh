#!/usr/bin/env bash
# =============================================================================
# Scenario A — visual workspace for screenshots
#
# Opens a tmux session with four labelled panes, one per node of the topology
# (host, ue, access, core), each with a coloured prompt showing the node name,
# so the topology is obvious in screenshots.
#
# Usage:  sudo ./scripts/observe/gui-workspace.sh [session-name]
#         (default session name: 5g-lab)
#
# Requires: tmux  (sudo apt install tmux)
# =============================================================================
set -uo pipefail

ROOT=$(cd "$(dirname "$0")/../.." && pwd)
SESSION="${1:-5g-lab}"

[[ $EUID -eq 0 ]] || { echo "Run as root (sudo)."; exit 1; }
command -v tmux >/dev/null 2>&1 || { echo "tmux not installed:  sudo apt install tmux"; exit 1; }

for ns in ue access core; do
    ip netns list | awk '{print $1}' | grep -qx "$ns" \
        || { echo "missing namespace '$ns' — run scripts/deploy/setup.sh first"; exit 1; }
done

# --- per-node bash init: labelled coloured prompt ---------------------------
RCDIR=$(mktemp -d /tmp/opencode/5g-rc.XXXXXX 2>/dev/null || mktemp -d)
mk_rc() { # <label> -> prints rc file path
    local label="$1" f="$RCDIR/rc-$1"
    cat > "$f" <<EOF
PS1='\[\e[1;32m\](${label})\[\e[0m\] \w# '
EOF
    printf '%s' "$f"
}

# --- build the 4-pane layout ------------------------------------------------
tmux kill-session -t "$SESSION" 2>/dev/null || true

p_host=$(tmux new-session -d -P -F '#{pane_id}' -s "$SESSION" -n nodes -c "$ROOT" \
    "bash --rcfile $(mk_rc host)")
p_ue=$(tmux split-window -h -P -F '#{pane_id}' -t "$p_host" -c "$ROOT" \
    "ip netns exec ue bash --rcfile $(mk_rc ue)")
p_access=$(tmux split-window -v -P -F '#{pane_id}' -t "$p_host" -c "$ROOT" \
    "ip netns exec access bash --rcfile $(mk_rc access)")
p_core=$(tmux split-window -v -P -F '#{pane_id}' -t "$p_ue" -c "$ROOT" \
    "ip netns exec core bash --rcfile $(mk_rc core)")

tmux select-layout -t "$SESSION":nodes tiled 2>/dev/null || true
tmux set -t "$SESSION" -g pane-border-status top 2>/dev/null || true
tmux set -t "$SESSION" -g pane-border-format ' #{pane_title} ' 2>/dev/null || true
# Mouse: click to focus a pane, drag borders to resize, scroll to page output.
tmux set -t "$SESSION" -g mouse on 2>/dev/null || true
tmux select-pane -t "$p_host"   -T "host (root ns / Data Network boundary)"
tmux select-pane -t "$p_ue"     -T "ue    (10.0.1.10)"
tmux select-pane -t "$p_access" -T "access(10.0.1.1 / 10.0.2.1)"
tmux select-pane -t "$p_core"   -T "core  (10.0.2.2 / 10.0.3.1)"
tmux select-pane -t "$p_host"

echo "[gui-workspace] tmux session '$SESSION' ready (host / ue / access / core)."
echo "  attach:  tmux attach -t $SESSION"
echo "  kill:    tmux kill-session -t $SESSION"

tmux attach -t "$SESSION"
