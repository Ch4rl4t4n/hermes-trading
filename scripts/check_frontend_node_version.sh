#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
required_major=20
required_minor=19
STRICT_NODE="${STRICT_NODE:-0}"

if ! NODE_EXEC="$("$SCRIPT_DIR/_node_pick.sh")"; then
  echo "ERROR: node is not installed"
  exit 1
fi

version="$("$NODE_EXEC" -v | sed 's/^v//')"
major="${version%%.*}"
rest="${version#*.}"
minor="${rest%%.*}"

if [[ "$major" -gt "$required_major" ]] || [[ "$major" -eq "$required_major" && "$minor" -ge "$required_minor" ]]; then
  echo "OK: Node.js $version via $NODE_EXEC (requirement >= ${required_major}.${required_minor}.0)"
  exit 0
fi

if [[ "$STRICT_NODE" == "1" ]]; then
  echo "ERROR: Node.js $version via $NODE_EXEC; strict mode requires >= ${required_major}.${required_minor}.0"
  exit 3
fi

echo "WARN: Node.js $version via $NODE_EXEC; Vite requires >= ${required_major}.${required_minor}.0"
exit 2
