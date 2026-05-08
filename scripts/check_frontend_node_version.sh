#!/usr/bin/env bash
set -euo pipefail

required_major=20
required_minor=19
STRICT_NODE="${STRICT_NODE:-0}"

if ! command -v node >/dev/null 2>&1; then
  echo "ERROR: node is not installed"
  exit 1
fi

version="$(node -v | sed 's/^v//')"
major="${version%%.*}"
rest="${version#*.}"
minor="${rest%%.*}"

if [[ "$major" -gt "$required_major" ]] || [[ "$major" -eq "$required_major" && "$minor" -ge "$required_minor" ]]; then
  echo "OK: Node.js $version (requirement >= ${required_major}.${required_minor}.0)"
  exit 0
fi

if [[ "$STRICT_NODE" == "1" ]]; then
  echo "ERROR: Node.js $version detected; strict mode requires >= ${required_major}.${required_minor}.0"
  exit 3
fi

echo "WARN: Node.js $version detected; Vite requires >= ${required_major}.${required_minor}.0"
exit 2
