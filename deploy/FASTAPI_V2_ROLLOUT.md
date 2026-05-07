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

### 4.1 Získaj FastAPI token cez Flask bridge

```bash
curl -X POST \
  -H "X-Internal-Token: <INTERNAL_API_TOKEN>" \
  -H "X-User-Email: <USER_EMAIL>" \
  http://localhost/api/v1/auth/fastapi-token
```

Očakávané:

```json
{"fastapi_token":"...","expires_in":3600}
```

### 4.2 FastAPI agents endpoint

```bash
curl -H "Authorization: Bearer <FASTAPI_TOKEN>" \
  http://localhost/api/v2/agents
```

### 4.3 FastAPI leaderboard endpoint

```bash
curl -H "Authorization: Bearer <FASTAPI_TOKEN>" \
  "http://localhost/api/v2/leaderboard?period=7d"
```

### 4.4 WebSocket P&L

```bash
wscat -c ws://localhost/api/v2/ws/pnl \
  -H "Authorization: Bearer <FASTAPI_TOKEN>"
```

## 5) Self-check

- [ ] `/api/v2/*` odpovedá bez regresie Flask `/api/*`
- [ ] Invalid/missing token vracia `401`
- [ ] `period` mimo `7d|30d|all` vracia `400`
- [ ] Redis cache key `fastapi:v2:leaderboard:*` má TTL 60s
- [ ] Frontend po login uloží `v2_fastapi_token` (localStorage + cookie)
- [ ] Frontend pri sign-out vymaže `v2_fastapi_token`

