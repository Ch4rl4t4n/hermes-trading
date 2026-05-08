# HERMES Swarm v2 — Deploy Guide

**Verzia:** 2.0.0
**Cieľ:** spustiť kompletnú swarm vrstvu (Redis + Dramatiq + Registry + Router) na produkcii (`46.224.120.151`).

---

## 1. Prerekvizity

| Komponent | Verzia | Stav |
|-----------|--------|------|
| Python | 3.12+ | ✅ existuje (`/root/hermes/venv`) |
| PostgreSQL | 16+ | ✅ beží |
| Redis | **7+** | ❌ **chýba — treba doinštalovať** |
| systemd | — | ✅ |

---

## 2. Inštalácia Redis (jednorazovo)

Na serveri spusti:

```bash
apt update && apt install -y redis-server
sed -i 's/^# *maxmemory-policy.*/maxmemory-policy allkeys-lru/' /etc/redis/redis.conf
sed -i 's/^# *maxmemory .*/maxmemory 1gb/' /etc/redis/redis.conf
systemctl enable --now redis-server
redis-cli ping   # → PONG
```

---

## 3. Aktualizácia .env

Doplň do `/root/hermes/.env`:

```env
# --- Swarm v2 ---
REDIS_URL=redis://127.0.0.1:6379/0
HERMES_DRAMATIQ_NAMESPACE=hermes
HERMES_SWARM_HEARTBEAT_TTL=60
HERMES_ORCHESTRA_INTERVAL=30
HERMES_WORKER_PROCESSES=4
HERMES_WORKER_THREADS=8
HERMES_ENABLE_PROMETHEUS=0
```

---

## 4. Python závislosti

```bash
cd /root/hermes
venv/bin/pip install -r requirements.txt
```

Pridáva sa: `dramatiq[redis,watch]`, `prometheus-client`, `asyncpg`, `python-jose[cryptography]`.

---

## 5. Databázová migrácia

```bash
cd /root/hermes
venv/bin/alembic upgrade head
```

Migrácia `p1q2r3s4t5u6_swarm_v2_persistence.py` pridá:
- indexy v `agent_registry` (swarm/status, GIN capabilities, heartbeat DESC)
- stĺpce v `task_queue` (swarm_name, routing_reason, dead_lettered_at, execution_time_ms)
- nové tabuľky `routing_decisions`, `swarm_metrics`

---

## 6. Inštalácia Dramatiq systemd unitu

```bash
cp /root/hermes/deploy/hermes-workers.service /etc/systemd/system/hermes-workers.service
systemctl daemon-reload
systemctl enable hermes-workers
```

---

## 7. Reštart servisov (cez teba — ja systemctl nevolám)

> Spusti na serveri:
>
> ```bash
> systemctl restart hermes-dashboard hermes-api hermes-workers
> systemctl status hermes-workers --no-pager | head -15
> ```

---

## 8. Smoke testy (po reštarte)

```bash
# 1) Redis ping
redis-cli ping

# 2) Worker beží
systemctl is-active hermes-workers

# 3) Registry hydrated (z Postgresu do Redis)
redis-cli keys 'hermes:agent:*' | wc -l   # > 0

# 4) Orchestra heartbeat
redis-cli ttl 'hermes:heartbeat:orchestra-001'   # < 60

# 5) FastAPI v2 swarm status (admin token vyžadovaný)
curl -H "Authorization: Bearer $TOKEN" \
  https://app.letagentscook.lol/api/v2/swarm/status | jq .

# 6) Routing log
curl -H "Authorization: Bearer $TOKEN" \
  https://app.letagentscook.lol/api/v2/swarm/routing-log?limit=5

# 7) Dispatch test task (admin)
curl -X POST -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"task_type":"ping","payload":{"hello":"world"},"priority":7}' \
  https://app.letagentscook.lol/api/v2/swarm/dispatch
```

Očakávaný výstup `/api/v2/swarm/status`:

```json
{
  "version": "2.0.0",
  "redis_ok": true,
  "agents": {"total": 60+, "alive": 1+, "running": 0, "idle": 60+, "unhealthy": 0},
  "queue":  {"pending": 0, "assigned": 0, "running": 0, "completed": 0, "failed": 0, "dead": 0},
  "swarms": [
    {"name": "intelligence", "members": 2, "alive_members": 0},
    {"name": "maintenance", "members": 2, "alive_members": 0},
    {"name": "marketing", "members": 2, "alive_members": 0},
    {"name": "orchestra", "members": 1, "alive_members": 1},
    {"name": "trading", "members": 50+, "alive_members": 0}
  ]
}
```

---

## 9. Nginx konfig — žiadna zmena

Existujúca konfigurácia `deploy/hermes-api.nginx.conf` už route-uje `/api/v2/*` → `127.0.0.1:8001`. Nové endpointy `/api/v2/swarm/*` sú automaticky dostupné.

---

## 10. Škálovanie (pri raste)

| Záťaž | Konfigurácia |
|-------|--------------|
| < 50 agentov | `HERMES_WORKER_PROCESSES=2` `HERMES_WORKER_THREADS=4` |
| 50–150 agentov | `HERMES_WORKER_PROCESSES=4` `HERMES_WORKER_THREADS=8` (default) |
| 150–500 agentov | `HERMES_WORKER_PROCESSES=8` `HERMES_WORKER_THREADS=16` + Redis `maxmemory 2gb` |
| 500+ agentov | Vyhradiť ďalší box len pre workerov; Redis Sentinel/Cluster |

---

## 11. Rollback

```bash
# 1. Stop workers
systemctl stop hermes-workers
systemctl disable hermes-workers

# 2. DB downgrade (vráti sa pred swarm v2 migráciu)
cd /root/hermes
venv/bin/alembic downgrade -1
```

Existujúce v1 endpointy (Flask `/api/admin/registry/*`) ostávajú funkčné — `queue_manager.py` zachoval pôvodné API.

---

## 12. Monitoring & Observability

- **Routing audit:** `SELECT * FROM routing_decisions ORDER BY decided_at DESC LIMIT 50;`
- **Dead-letter queue:** `SELECT * FROM task_queue WHERE status = 'dead' ORDER BY dead_lettered_at DESC;`
- **Per-swarm metriky:** `SELECT * FROM swarm_metrics WHERE swarm_name = 'trading' ORDER BY recorded_at DESC LIMIT 100;`
- **Prometheus** (voliteľné): `HERMES_ENABLE_PROMETHEUS=1`, scrape `:9191/metrics`.
