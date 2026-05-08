#!/usr/bin/env bash
set -euo pipefail

ROOT="/root/hermes"
VENV_BIN="$ROOT/venv/bin"

PROCESSES="${HERMES_WORKER_PROCESSES:-4}"
THREADS="${HERMES_WORKER_THREADS:-8}"
MODULE="${HERMES_DRAMATIQ_MODULE:-core.swarm_actors}"
BROKER="${HERMES_DRAMATIQ_BROKER:-core.dramatiq_app:broker}"
QUEUES="${HERMES_DRAMATIQ_QUEUES:-hermes_priority hermes_default hermes_low}"

if [[ "${1:-}" == "--print-cmd" ]]; then
  echo "$VENV_BIN/dramatiq --path /root /root/hermes --processes $PROCESSES --threads $THREADS --queues $QUEUES -- $BROKER $MODULE"
  exit 0
fi

exec "$VENV_BIN/dramatiq" \
  --path /root /root/hermes \
  --processes "$PROCESSES" \
  --threads "$THREADS" \
  --queues $QUEUES \
  -- \
  "$BROKER" \
  "$MODULE"

