# Hermes FastAPI v2 Rollout Checklist

Tento checklist je pre final integration + produkčný rollout hybrid Flask + FastAPI.

## 1) Predpoklady

- `FASTAPI_JWT_SECRET` je nastavený v produkčnom `.env` (silný random secret).
- `DATABASE_URL` a `REDIS_URL` sú dostupné pre `hermes-api` service.
- `python-jose`, `fastapi`, `uvicorn`, `asyncpg`, `redis`, `websockets`, `structlog` sú nainštalované vo `venv`.

## 2) Deploy súbory

- Nginx config template: `deploy/hermes-api.nginx.conf`
- Systemd unit template: `deploy/hermes-api.service`

Skopíruj ich na server:

```bash
cp /root/hermes/deploy/hermes-api.nginx.conf /etc/nginx/sites-enabled/hermes
cp /root/hermes/deploy/hermes-api.service /etc/systemd/system/hermes-api.service
```

## 3) Service reload/restart (spusti na serveri)

```bash
systemctl daemon-reload
systemctl enable --now hermes-api
systemctl restart hermes-api
systemctl restart hermes-dashboard
nginx -t && systemctl reload nginx
```

## 4) Smoke tests

### 4.1 Získaj FastAPI token (odporúčané cez mint script)

```bash
cd /root/hermes
TOKEN="$(venv/bin/python scripts/mint_fastapi_token.py)"
echo "$TOKEN"
```

Očakávané:

```json
eyJhbGciOi...
```

### 4.2 FastAPI agents endpoint

```bash
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost/api/v2/agents
```

### 4.3 FastAPI leaderboard endpoint

```bash
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost/api/v2/leaderboard?period=7d"
```

### 4.4 WebSocket P&L

```bash
wscat -c ws://localhost/api/v2/ws/pnl \
  -H "Authorization: Bearer $TOKEN"
```

### 4.5 Swarm health + policy status

```bash
curl -s "http://127.0.0.1:8001/api/v2/swarm/status" \
  -H "Authorization: Bearer $TOKEN"
```

### 4.5b OpenAPI route presence check (bez pipe/heredoc problémov)

```bash
cd /root/hermes
python3 scripts/check_swarm_openapi_route.py
```

Očakávané:

- `HAS_ROUTE=true` pre `/api/v2/swarm/capabilities`

### 4.6 Admin Swarm smoke flow (status + capabilities + route + dispatch)

```bash
cd /root/hermes
scripts/smoke_swarm_admin_flow.sh
```

Voliteľne s custom API base:

```bash
API_BASE="http://127.0.0.1:8001/api/v2" scripts/smoke_swarm_admin_flow.sh
```

Poznámka: ak aktuálne nasadenie ešte nemá `/api/v2/swarm/capabilities`, skript vypíše `WARN` a pokračuje (status/route/dispatch ostávajú povinné).

Strict mód (capabilities endpoint musí byť dostupný):

```bash
STRICT_CAPABILITIES=1 scripts/smoke_swarm_admin_flow.sh
```

### 4.7 Frontend Node.js runtime check

Pred frontend buildom over minimálnu verziu Node:

```bash
cd /root/hermes
scripts/check_frontend_node_version.sh
```

Ak skript vráti warning pre `20.18.x`, aktualizuj Node na `20.19+` (alebo `22.12+`) pred release buildom.

### 4.8 One-shot pre-release checks (build + smoke)

```bash
cd /root/hermes
scripts/pre_release_checks.sh
```

Strict mód pre capabilities endpoint:

```bash
STRICT_CAPABILITIES=1 scripts/pre_release_checks.sh
```

Strict mód aj pre Node runtime:

```bash
STRICT_NODE=1 STRICT_CAPABILITIES=1 scripts/pre_release_checks.sh
```

Shortcut pre plne strict gate:

```bash
scripts/pre_release_checks_strict.sh
```

Node upgrade runbook:

- `deploy/NODE_RUNTIME_UPGRADE.md`

## 5) Self-check

- [ ] `/api/v2/*` odpovedá bez regresie Flask `/api/*`
- [ ] Invalid/missing token vracia `401`
- [ ] `period` mimo `7d|30d|all` vracia `400`
- [ ] Redis cache key `fastapi:v2:leaderboard:*` má TTL 60s
- [ ] Frontend po login uloží `v2_fastapi_token` (localStorage + cookie)
- [ ] Frontend pri sign-out vymaže `v2_fastapi_token`

