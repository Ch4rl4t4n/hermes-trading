#!/usr/bin/env bash
# Run a command with PATH prefixed so `node` / npm's child processes use the same
# Hermes-resolved Node as check_frontend_node_version.sh (see scripts/_node_pick.sh).
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NODE_EXEC="$("$SCRIPT_DIR/_node_pick.sh")"
export PATH="$(dirname "$NODE_EXEC"):$PATH"
exec "$@"
