#!/usr/bin/env bash
set -euo pipefail

ROOT="/root/hermes"
STRICT_CAPABILITIES="${STRICT_CAPABILITIES:-0}"
STRICT_NODE="${STRICT_NODE:-0}"

echo "[1/3] Node runtime check"
if STRICT_NODE="$STRICT_NODE" "$ROOT/scripts/check_frontend_node_version.sh"; then
  :
else
  rc=$?
  if [[ "$rc" -eq 2 ]]; then
    echo "WARN: pokračujem ďalej, ale odporúčaný je Node >= 20.19.0"
  else
    echo "ERROR: Node runtime check zlyhal"
    exit "$rc"
  fi
fi

echo "[2/3] Frontend build"
(cd "$ROOT/frontend" && "$ROOT/scripts/with_hermes_node.sh" npm run build)

echo "[3/3] Swarm admin smoke"
STRICT_CAPABILITIES="$STRICT_CAPABILITIES" "$ROOT/scripts/smoke_swarm_admin_flow.sh"

echo "OK: pre-release checks passed"
