#!/usr/bin/env bash
set -euo pipefail

ROOT="/root/hermes"

STRICT_NODE=1 STRICT_CAPABILITIES=1 "$ROOT/scripts/pre_release_checks.sh"
