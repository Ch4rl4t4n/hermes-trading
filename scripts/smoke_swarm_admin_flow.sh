#!/usr/bin/env bash
set -euo pipefail

ROOT="/root/hermes"
PYTHON_BIN="${PYTHON_BIN:-$ROOT/venv/bin/python}"
API_BASE="${API_BASE:-}"
STRICT_CAPABILITIES="${STRICT_CAPABILITIES:-0}"

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "ERROR: Python bin not found: $PYTHON_BIN" >&2
  exit 1
fi

TOKEN="$("$PYTHON_BIN" "$ROOT/scripts/mint_fastapi_token.py")"
if [[ -z "$TOKEN" ]]; then
  echo "ERROR: Failed to mint FastAPI token" >&2
  exit 1
fi

auth_header=(-H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json")

choose_api_base() {
  local candidates=()
  if [[ -n "$API_BASE" ]]; then
    candidates+=("$API_BASE")
  fi
  candidates+=(
    "http://127.0.0.1/api/v2"
    "http://localhost/api/v2"
    "http://127.0.0.1:8001/api/v2"
    "http://localhost:8001/api/v2"
  )

  local base code
  for base in "${candidates[@]}"; do
    code="$(curl -sS -o /dev/null -w "%{http_code}" "${auth_header[@]}" "$base/swarm/status" || true)"
    if [[ "$code" == "200" ]]; then
      echo "$base"
      return 0
    fi
  done
  return 1
}

if ! API_BASE="$(choose_api_base)"; then
  echo "ERROR: Could not reach /swarm/status on known API_BASE variants" >&2
  exit 2
fi
echo "Using API_BASE: $API_BASE"

request_json() {
  local method="$1"
  local url="$2"
  local data="${3:-}"
  local raw http body
  if [[ -n "$data" ]]; then
    raw="$(curl -sS "${auth_header[@]}" -X "$method" "$url" -d "$data" -w $'\n%{http_code}')"
  else
    raw="$(curl -sS "${auth_header[@]}" -X "$method" "$url" -w $'\n%{http_code}')"
  fi
  http="${raw##*$'\n'}"
  body="${raw%$'\n'*}"
  if [[ "$http" != "200" ]]; then
    echo "ERROR: $method $url -> HTTP $http" >&2
    echo "$body" >&2
    exit 3
  fi
  echo "$body"
}

status_json="$(request_json GET "$API_BASE/swarm/status")"
python3 -c 'import json,sys; d=json.loads(sys.argv[1]); assert isinstance(d.get("agents"), dict); assert isinstance(d.get("queue"), dict)' "$status_json"

cap_raw="$(curl -sS "${auth_header[@]}" -X GET "$API_BASE/swarm/capabilities" -w $'\n%{http_code}')"
cap_http="${cap_raw##*$'\n'}"
cap_body="${cap_raw%$'\n'*}"
if [[ "$cap_http" == "200" ]]; then
  python3 -c 'import json,sys; d=json.loads(sys.argv[1]); assert "items" in d and isinstance(d["items"], list)' "$cap_body"
else
  if [[ "$STRICT_CAPABILITIES" == "1" ]]; then
    echo "ERROR: /swarm/capabilities unavailable (HTTP $cap_http) and STRICT_CAPABILITIES=1" >&2
    exit 4
  fi
  echo "WARN: /swarm/capabilities unavailable (HTTP $cap_http), skipping capability inventory check"
fi

route_payload='{"task_type":"analysis","required_capabilities":["routing"],"preferred_swarm":"orchestra","priority":5}'
route_json="$(request_json POST "$API_BASE/swarm/route" "$route_payload")"
python3 -c 'import json,sys; d=json.loads(sys.argv[1]); assert "reason" in d and ("would_assign_to" in d or "swarm" in d)' "$route_json"

dispatch_payload='{"task_type":"manual","payload":{"source":"smoke-admin-flow"},"required_capabilities":["routing"],"preferred_swarm":"orchestra","priority":5}'
dispatch_json="$(request_json POST "$API_BASE/swarm/dispatch" "$dispatch_payload")"
python3 -c 'import json,sys; d=json.loads(sys.argv[1]); assert "task_id" in d and len(str(d["task_id"]))>0' "$dispatch_json"

echo "OK: Swarm admin smoke passed (status + route + dispatch)"
