#!/usr/bin/env bash
set -euo pipefail

echo "== Hermes Swarm v2 rollout =="
echo

if [[ ! -d "/root/hermes" ]]; then
  echo "ERROR: /root/hermes not found"
  exit 1
fi

cd /root/hermes

if [[ ! -x "venv/bin/python" ]]; then
  echo "ERROR: virtualenv missing at /root/hermes/venv"
  exit 1
fi

echo "[1/6] Installing Python dependencies"
venv/bin/pip install -r requirements.txt

echo "[2/6] Running Alembic migration"
venv/bin/alembic upgrade head

echo "[3/6] Building frontend"
if [[ -d "frontend" ]]; then
  (
    cd frontend
    npm run build
  )
else
  echo "WARN: frontend directory not found, skipping build"
fi

echo "[4/6] Checking Redis connectivity"
if command -v redis-cli >/dev/null 2>&1; then
  if redis-cli ping >/dev/null 2>&1; then
    echo "Redis OK"
  else
    echo "WARN: redis-cli exists but Redis is not responding on default socket/host"
  fi
else
  echo "WARN: redis-cli not found. Install redis-server first."
fi

echo "[5/6] Installing worker unit file (if permitted)"
if [[ -f "deploy/hermes-workers.service" ]]; then
  cp "deploy/hermes-workers.service" "/etc/systemd/system/hermes-workers.service" || true
  echo "Worker unit copied to /etc/systemd/system/hermes-workers.service (or copy failed due permissions)"
else
  echo "WARN: deploy/hermes-workers.service missing"
fi

echo "[6/6] Pre-restart verification"
python3 - <<'PY'
import json, pathlib
root = pathlib.Path("/root/hermes")
required = [
    root / "api/routers/swarm.py",
    root / "core/swarm_registry.py",
    root / "core/swarm_actors.py",
    root / "core/swarm_handlers.py",
]
missing = [str(p) for p in required if not p.exists()]
if missing:
    print("Missing files:")
    for m in missing:
        print(" -", m)
else:
    print("All critical Swarm v2 files present.")
PY

echo
echo "Rollout prep complete."
echo "Spusti na serveri: systemctl daemon-reload && systemctl enable hermes-workers && systemctl restart hermes-dashboard hermes-api hermes-watcher hermes-workers"
echo "Then verify:"
echo "  curl -s http://127.0.0.1:8001/openapi.json | python3 -c 'import sys,json; d=json.load(sys.stdin); print([p for p in d[\"paths\"] if \"/api/v2/swarm\" in p])'"
