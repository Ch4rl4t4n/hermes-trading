# CLAUDE.md — Hermes Trading Platform
> Tento súbor je primárny kontext pre Claude Code, Cursor a všetky AI nástroje.
> Aktualizuj ho po každej väčšej zmene. Posledná aktualizácia: Máj 2026

---

## 🗺️ Architektúra projektu

### Server
- **IP:** 46.224.120.151 (Ubuntu 8GB, Hetzner)
- **URLs:** https://letagentscook.lol (marketing) | https://app.letagentscook.lol (app)
- **Systemd services:** hermes-dashboard | hermes-watcher | hermes-agents | hermes-api

### Stack
- **Backend:** Flask (Python) + FastAPI v2 (hybrid) + PostgreSQL + Redis
- **Frontend:** Single-file SPA — `index.html` (~9225 riadkov, vanilla JS)
- **Auth:** bcrypt + Google OAuth (Flask-Dance)
- **Email:** Gmail SMTP
- **Payments:** Stripe (test mode)
- **Telegram:** @Let_Agents_Cook_bot

---

## 📁 Kľúčové súbory a ich veľkosť

| Súbor | Riadky | Popis |
|-------|--------|-------|
| `/root/hermes/dashboard/app.py` | ~4735 | Hlavná Flask app, všetky API endpointy |
| `/root/hermes/api/main.py` | ~40 | FastAPI v2 app assembly + lifespan (DB/Redis) |
| `/root/hermes/api/dependencies.py` | ~140 | JWT auth dependency + DB/Redis lifecycle |
| `/root/hermes/api/routers/agents.py` | ~220 | `/api/v2/agents*` endpointy |
| `/root/hermes/api/routers/leaderboard.py` | ~130 | `/api/v2/leaderboard` + Redis cache TTL 60s |
| `/root/hermes/api/routers/swarm.py` | ~320 | `/api/v2/swarm/*` status, queue, routing, dispatch |
| `/root/hermes/dashboard/templates/index.html` | ~9225 | Celý frontend (HTML + CSS + JS v jednom) |
| `/root/hermes/core/watcher_agent.py` | ~865 | Monitoring, alerts, weekly report, paper trades |
| `/root/hermes/core/agent_marketplace.py` | — | Marketplace + record_paper_trade() |
| `/root/hermes/core/telegram_bot.py` | — | Telegram bot logika |
| `/root/hermes/core/trade_reasons.py` | — | generate_trade_reason() |
| `/root/hermes/core/leaderboard.py` | — | compute_leaderboard_cache() |
| `/root/hermes/core/queue_manager.py` | ~320 | Pg+Redis dual-write queue manager (durable + hot cache) |
| `/root/hermes/core/swarm_definitions.py` | ~125 | Default swarm definitions + seed helper |
| `/root/hermes/core/swarm_registry.py` | ~380 | Agent Registry (Postgres canonical + Redis hot cache) |
| `/root/hermes/core/task_router.py` | ~230 | Orchestra task routing engine with scoring + DB audit |
| `/root/hermes/core/orchestra_agent.py` | ~40 | Orchestra compatibility facade (`orchestra.start()`) |
| `/root/hermes/core/swarm_bootstrap.py` | ~200 | Registry hydration + seed + auto-registration + scheduler |
| `/root/hermes/core/swarm_actors.py` | ~170 | Dramatiq actors (`route_task`, `execute_task`, `orchestra_tick`) |
| `/root/hermes/core/swarm_handlers.py` | ~240 | Domain handlers (market/report/alert/snapshot) |
| `/root/hermes/core/intelligence_stalker.py` | ~NEW | Intelligence swarm worker (news/trends/summary reports) |
| `/root/hermes/frontend/src/utils/appRoutes.js` | ~NEW | Mapovanie URL ↔ interný `page` kľúč (SPA história, PWA shortcuts) |
| `/root/hermes/frontend/src/pages/AdminSwarm.jsx` | ~NEW | Admin War Room control center (swarm ops, queue, health, directory) |
| `/root/hermes/frontend/src/components/adminswarm/*.jsx` | ~NEW | War Room modular panels (routing, sidebar, swarm grid, directory, drawer) |
| `/root/hermes/frontend/src/hooks/useAdminSwarmRoutingInsights.js` | ~NEW | Routing insight computations (capability signals, confidence, checklist) |
| `/root/hermes/scripts/pre_release_checks.sh` | ~NEW | One-shot pre-release checks (node check + frontend build + swarm smoke) |
| `/root/hermes/scripts/pre_release_checks_strict.sh` | ~NEW | Strict release gate wrapper (`STRICT_NODE=1`, `STRICT_CAPABILITIES=1`) |
| `/root/hermes/scripts/check_frontend_node_version.sh` | ~NEW | Frontend Node.js runtime validator (`>=20.19.0`), výber cez `_node_pick.sh` |
| `/root/hermes/scripts/_node_pick.sh` | ~NEW | Vyberie správny `node` keď PATH tiene IDE/Cursor binárku pred `/usr/bin/node` |
| `/root/hermes/scripts/with_hermes_node.sh` | ~NEW | Spustí príkaz s PATH nastaveným na Hermes Node (pre `npm run build`) |
| `/root/hermes/scripts/smoke_swarm_admin_flow.sh` | ~NEW | Admin swarm smoke (`status`, `route`, `dispatch`, optional `capabilities`) |
| `/root/hermes/frontend/src/components/SwarmBuilderModal.jsx` | ~NEW | Prompt-based AI swarm generator modal + prompt library |
| `/root/hermes/core/agent_builder.py` | ~NEW | Agent Builder backend (ALLOWED_SYMBOLS, ALLOWED_STRATEGIES, AI summary) |
| `/root/hermes/.env` | — | Všetky secrets |

---

## 🗃️ Databázové tabuľky

```
users               — id, email, tier, stripe_customer_id, telegram_chat_id, weekly_report_enabled, referral_code, referred_by, referral_bonus_slots, referral_bonus_expires_at
trading_agents      — id, name, symbol, category, strategy, win_rate, total_trades, show_in_leaderboard
user_agents         — id, user_id, name, symbol, strategy_type, config_json, status, is_public, public_id, marketplace_status, created_at
user_subscriptions  — user_id, agent_id, mode, is_active
paper_trades        — id, user_id, agent_id (nullable), user_agent_id (nullable), symbol, action, price, quantity, pnl, reason, signals (jsonb), confidence, timestamp
trade_explanations  — trade_id, explanation, signals, generated_at
agent_pnl_snapshots — agent_id, user_id, snapshot_date, pnl_usd, pnl_pct, equity, trade_count, win_count
agent_leaderboard_cache — agent_id, period, rank, pnl_pct, pnl_usd, win_rate, trade_count, subscriber_count
alert_rules         — user_id, agent_id, alert_type, threshold, is_enabled, last_triggered_at
notifications       — user_id, type, title, message, is_read
referrals           — id, referrer_id, referred_id, created_at, bonus_granted
community_agents    — id, user_id, name, symbol, category, strategy, risk_level, description, status, win_rate, total_return, subscribers, price_monthly, is_featured, reject_reason, created_at, approved_at
backtest_results    — id, user_id, agent_id, symbol, strategy, timeframe, start_date, end_date, initial_capital, final_capital, total_return, max_drawdown, win_rate, total_trades, winning_trades, sharpe_ratio, equity_curve, trades_log, created_at
agent_registry      — id, agent_id, name, swarm_name, agent_type, status, capabilities, priority, config, memory_enabled, human_approval_required, cost_limit_daily, tasks_completed, tasks_failed, last_heartbeat, created_by, created_at, updated_at
task_queue          — id, task_id, task_type, payload, status, priority, assigned_to, required_capabilities, result, error_message, created_at, started_at, completed_at, retry_count, max_retries
intelligence_reports — id, report_type, symbol, title, content, sentiment, sentiment_score, source, tags, agent_id, created_at
```

---

## 🔌 API Endpointy (kompletný zoznam)

```
AUTH
  GET/POST  /api/auth/status|login|register
  POST      /api/v1/auth/fastapi-token

MARKETPLACE
  GET       /api/marketplace/agents|slots
  POST      /api/marketplace/subscribe|unsubscribe
  GET       /api/marketplace/my-agents

AGENT BUILDER (nové)
  POST      /api/agent-builder/create
  GET       /api/agent-builder/my-agents
  PATCH     /api/agent-builder/:id/status
  DELETE    /api/agent-builder/:id
  POST      /api/agent-builder/ai-summary

AGENTS & TRADES
  GET       /api/agents/pnl
  GET       /api/agents/badges
  GET       /api/trades/history
  GET       /api/intelligence/feed
  GET       /api/intelligence/sentiment

BACKTEST
  POST      /api/backtest/run
  GET       /api/backtest/history

EXPORT
  GET       /api/export/trades.csv
  GET       /api/export/report.pdf

LEADERBOARD
  GET       /api/leaderboard?period=weekly|monthly|alltime

ALERTS & NOTIFICATIONS
  GET/POST  /api/alerts/rules
  GET       /api/notifications
  POST      /api/notifications/read

STRIPE
  POST      /api/stripe/create-checkout-session|create-portal-session|webhook

TELEGRAM
  POST      /api/telegram/connect-token|disconnect|webhook

SETTINGS
  GET/POST  /api/settings/weekly-report
  GET       /unsubscribe/<token>

SHARING
  GET       /api/sharing/referral-info
  POST      /api/sharing/track-referral
  POST      /api/sharing/grant-referral-bonus
  GET       /api/sharing/performance-card/:agent_id?type=trading_agent|user_agent|leaderboard

COMMUNITY MARKETPLACE (nové)
  GET       /api/community/agents
  POST      /api/community/agents
  GET       /api/community/my-agents
  POST      /api/community/my-agents
  GET       /api/admin/community/agents/pending
  POST      /api/admin/community/agents/:agent_id/review

ADMIN
  POST      /api/admin/assign-demo-agents
  GET       /api/admin/registry/agents
  POST      /api/admin/registry/agents
  POST      /api/admin/registry/agents/:agent_id/status
  GET       /api/admin/queue/stats
  POST      /api/admin/queue/push
  GET       /api/admin/queue/tasks
  POST      /api/admin/router/route
  POST      /api/admin/router/simulate
  GET       /api/admin/router/log
  GET       /api/admin/system/health
  POST      /api/admin/swarm-builder/generate
  POST      /api/admin/swarm-builder/create

FASTAPI V2 (nové)
  GET       /api/v2/agents
  GET       /api/v2/agents/:agent_id/pnl
  GET       /api/v2/agents/:agent_id/trades
  POST      /api/v2/agents/:agent_id/pause
  GET       /api/v2/leaderboard?period=7d|30d|all
  GET       /api/v2/swarm/status
  GET       /api/v2/swarm/swarms
  GET       /api/v2/swarm/agents
  GET       /api/v2/swarm/agents/:agent_id
  GET       /api/v2/swarm/queue
  GET       /api/v2/swarm/routing-log
  POST      /api/v2/swarm/route
  POST      /api/v2/swarm/dispatch
  POST      /api/v2/swarm/seed
```

---

## 👤 Tier systém

| Tier | Agenti (marketplace) | User Agents (builder) | Alerty | Telegram | Cena |
|------|---------------------|----------------------|--------|----------|------|
| basic | 3 | 1 | 3 | ❌ | free |
| pro | 10 | 5 | 15 | ✅ | 19€/mes |
| elite | unlimited | unlimited | unlimited | ✅ | 49€/mes |
| admin | unlimited | unlimited | unlimited | ✅ | — |

---

## ✅ Hotové features (Fáza 1 + 2 + 3-start)

- [x] Login/registrácia (manual + Google OAuth)
- [x] Tier systém (basic/pro/elite/admin)
- [x] 50 trading agentov v DB
- [x] Marketplace API
- [x] Onboarding (empty states, checklist, contextual tooltips)
- [x] Demo agenti pre nových userov
- [x] Live P&L dashboard (agent_pnl_snapshots, auto-refresh 30s)
- [x] Performance badges (top_gainer, hot_streak, steady, reliable)
- [x] Alert systém (pnl_drop + agent_inactive) + modal UI + email + telegram
- [x] Weekly email report (HTML, opt-out, pondelok 8:00 UTC)
- [x] Leaderboard agentov (weekly/monthly/alltime, cache 6h)
- [x] "Why?" vysvetlenia pre trades (reason, signals jsonb, confidence)
- [x] Telegram bot (príkazy: /start /pnl /status /help /stop)
- [x] Stripe integrácia (checkout, portal, webhooky, tier enforcement)
- [x] **No-code Agent Builder** (4-krokový wizard, AI summary, watcher integrácia)
- [x] **Social Sharing** (Performance Card share, Referral Program +3 sloty/30 dní, Leaderboard Brag Share)
- [x] **User-created Community Marketplace** (submit flow, admin approve/reject, community tab)
- [x] **Redis Queue + Agent Registry + Capability System** (registry DB + Redis queue manager + admin swarms overview)
- [x] **War Room UI (Admin Swarm Control Center)** (`/admin-swarm` page-state route, live queue, system health, agent directory/drawer)
- [x] **Prompt-Based Swarm Builder** (Claude-generated swarm config, create swarm endpoint, modal with saved prompts)
- [x] **War Room hardening audit (BOD 26-28)** (admin checks alignment, Redis-safe queue manager, modal/polling cleanup, rate-limited swarm generation)
- [x] **Orchestra Swarm + Dynamic Task Router** (task_router engine, orchestra background worker, router API, War Room routing section)
- [x] **Intelligence Stalker Swarm** (automated market intelligence reports + dashboard intelligence feed)
- [x] **Swarm v2 Production Backbone** (Dramatiq workers, Pg+Redis registry, durable queue, routing decisions audit, `/api/v2/swarm/*`)

---

## 🗺️ Roadmapa — zostatok

### Fáza 3 (Biznis model) — HOTOVÁ ✅
- [x] No-code Agent Builder
- [x] Social Sharing

### Fáza 4 (UX/UI & Mobile) — ĎALŠIA
- [x] Mobile responsiveness (safe-area, bottom nav, swarm KPI grid, narrow agents grid)
- [x] PWA / mobile app (manifest PNG ikony, scope, apple-touch-icon, SW cache bump)
- [x] Dark/light mode toggle
- [x] Accessibility (základ: skip link, focus-visible, modal Tab trap, reduced motion, ARIA hlavičiek/navigácie)

### Fáza 5 (Pokročilé funkcie)
- [ ] Agent marketplace (user-created agents, publikovanie)
- [x] Backtesting engine (real calculations + equity curve + history)
- [ ] API prístup pre Elite tier
- [ ] Custom watcher nastavenia
- [x] CSV/PDF export (trades CSV + P&L PDF + backtest CSV)

---

## ⚙️ Pracovné pravidlá pre AI

### Štýl kódu
- Všetky DB queries cez `SQLAlchemy text()`
- Migrácie cez Alembic: `cd /root/hermes && venv/bin/alembic upgrade head`
- Frontend: vanilla JS, žiadne externé JS knižnice (len Bootstrap + existujúce)
- Všetky texty UI v **slovenčine**
- Dark theme, konzistentné s existujúcim dizajnom

### Pred každou implementáciou — PLAN MODE
```
1. Vymenuj všetky súbory ktoré budeš meniť
2. Pre každý súbor uveď čo konkrétne pridáš/zmeniš
3. Identifikuj potenciálne konflikty s existujúcim kódom
4. Až potom začni kódovať
```

### Po každej implementácii — SELF-CHECK
```
□ Všetky nové endpointy vracajú správne HTTP kódy (200/400/403/404/500)
□ Tier limity sú enforced na backende (nie len frontende)
□ Žiadne hardcoded values (secrets, URLs, limity sú v konštantách)
□ Existujúca funkcionalita nie je rozbita
□ Nové DB stĺpce majú správne indexy
□ Error handling pre všetky async operácie
□ Loading states v UI pre každé API volanie
```

### Časté chyby — VYHNI SA
- ❌ Nikdy neupravuj `paper_trades.agent_id` na NOT NULL (je nullable kvôli user_agents)
- ❌ Nikdy nepridávaj `<form>` tagy do index.html (použiť onClick handlers)
- ❌ Nikdy neinštaluj nové npm/pip balíčky bez explicitného súhlasu
- ❌ Nikdy nemazať existujúce API endpointy (môžu ich používať iné časti)
- ❌ `gen_random_uuid()` vyžaduje `pgcrypto` rozšírenie — over pred použitím
- ❌ Nikdy nepoužívaj hardcoded URL — existuje konštanta `dash_config.APP_URL` (rovnaká ako `DASHBOARD_PUBLIC_BASE_URL`)
- ❌ Google OAuth referral: track-referral sa volá v `init()` po `handleOAuthWelcomeParams` (nie v redirect URL)

### Deploy príkazy
```bash
cd /root/hermes && venv/bin/alembic upgrade head
systemctl restart hermes-dashboard hermes-watcher
```

---

## 🔑 ENV premenné (kľúčové)

```
DATABASE_URL
SECRET_KEY
GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET
GMAIL_USER / GMAIL_PASSWORD
STRIPE_SECRET_KEY / STRIPE_WEBHOOK_SECRET
STRIPE_PRICE_PRO_MONTHLY / STRIPE_PRICE_PRO_YEARLY
STRIPE_PRICE_ELITE_MONTHLY / STRIPE_PRICE_ELITE_YEARLY
TELEGRAM_BOT_TOKEN
ANTHROPIC_API_KEY
HERMES_AGENT_BUILDER_MODEL  (optional, default: claude-sonnet-4-20250514)
```

---

## 🧩 Frontend sekcie (index.html navigácia)

Sekcie sa zobrazujú/skrývajú cez `showSection(id)`:

```
#dashboard          — hlavný prehľad, P&L
#marketplace        — výber agentov
#agentBuilderPage   — No-code Agent Builder (nové)
#leaderboard        — rebríček agentov
#trades             — história obchodov
#alerts             — nastavenie alertov
#settings           — profil, Telegram, weekly report
```

---

## 📋 Sub-task rozdelenie (pre paralelné Cursor sessiony)

Pri väčších features rozdeľ na:
- **Session A:** DB migrácia + backend API (`app.py` + nové core súbory)
- **Session B:** Frontend UI (`index.html` — nová sekcia + modal)
- **Session C:** Background worker integrácia (`watcher_agent.py`)

Každá session môže bežať paralelne v samostatnom Git worktree.

---

## 🤖 Smart Model Routing (minmax náklady + rýchlosť)

**Nikdy nepoužívaj drahý model na to, čo zvládne lacný. Tokeny -60%, rýchlosť +3-4x.**

| Úloha | Model | Dôvod |
|-------|-------|-------|
| High-level architektúra, plán featury, contrarian audit | **Grok** | Rýchly, lacný, skvelý big-picture |
| Komplexná logika, veľké refaktory, agent koordinácia | **Claude Opus** | Najsilnejší reasoning |
| Štandardný vývoj, nové endpointy, frontend sekcie | **Claude Sonnet** | Najlepší pomer cena/výkon |
| Inline edity, bugfixy, boilerplate, UI tweaks | **Claude Haiku / Cursor fast** | Lacná exekúcia |
| Security audit, PR review, "find every way this can break" | **Grok (red team mode)** | Contrarian thinking |

### Routing pravidlá pre Hermes
```
Nová feature (plán)     → Grok: "Navrhnime architektúru pre X, čo môže zlyhať?"
Nová feature (kód)      → Sonnet v Cursor: štandardný Cursor prompt
Veľký refaktor          → Opus: "Refaktoruj app.py sekciu X bez rozbíjania Y"
Rýchly bugfix           → Haiku: "Oprav tento konkrétny bug na riadku X"
Pred každým commitom    → Grok: "Act as senior engineer, find every way this PR can break"
```

---

## 🏆 Agent Teams workflow (pre veľké features)

Pre feature ktorá trvá 2+ hodiny — rozdeľ na Agent Team:

```
Leader (Opus/Sonnet):   Koordinuje, drží celkový kontext, robí finálny review
Backend Dev (Sonnet):   app.py endpointy, DB migrácie, core logika
Frontend Dev (Sonnet):  index.html sekcia, modal, JS funkcie  
Watcher Dev (Haiku):    watcher_agent.py integrácia, background tasks
Tester (Haiku):         generuje testy, overuje edge cases
Reviewer (Grok):        finálny security + UX + logic audit
```

**Spustenie v Claude Code:**
```
"Create Agent Team for [feature name]:
- Backend agent: focus on app.py and core/ files only
- Frontend agent: focus on index.html only  
- Tester agent: generate edge case tests
- Work in parallel, coordinate through CLAUDE.md"
```

---

## 📅 Daily Development Workflow

### Začiatok každého dňa
```bash
# 1. Fresh context - nikdy nepokračuj v starej session
/clear  (alebo nová Cursor session)

# 2. Skontroluj stav servera
systemctl status hermes-dashboard hermes-watcher

# 3. Načítaj CLAUDE.md ako prvý kontext
# V Cursor: @CLAUDE.md na začiatok každého promptu
```

### Štruktúra každého tasku
```
1. PLAN (Grok alebo /plan mode):
   "Chcem implementovať X. Aké sú riziká? Čo môže zlyhať?"

2. SPLIT (ak task > 2 hodiny):
   Rozdeľ na Session A / B / C (pozri sub-task sekciu)

3. CODE (Cursor + Sonnet):
   Cursor prompt podľa šablóny (pozri nižšie)

4. SELF-CHECK (automaticky v prompte):
   Cursor overí 7 bodov pred dokončením

5. RED TEAM (Grok):
   "Act as senior engineer. Find every way this implementation can break."

6. DEPLOY:
   alembic upgrade head && systemctl restart hermes-dashboard hermes-watcher

7. UPDATE CLAUDE.md:
   Aktualizuj riadky súborov a hotové features
```

### Koniec každého dňa
```
- Commitni všetky zmeny s popisom
- Aktualizuj CLAUDE.md (nové riadky súborov, hotové featury)
- Nastav /compact ak context > 60%
```

---

## 📝 Cursor Prompt Šablóna (pre každý task)

```
Kontext: @CLAUDE.md

[PLAN MODE - pred kódovaním]
Najprv vymenuj:
1. Ktoré súbory budeš meniť a prečo
2. Potenciálne konflikty s existujúcim kódom
3. Poradie krokov implementácie

[TASK]
[sem ide konkrétny popis featury]

[CONSTRAINTS]
- Vanilla JS, žiadne nové knižnice
- Všetky texty v slovenčine
- Dark theme, konzistentné s existujúcim dizajnom
- SQLAlchemy text() pre všetky queries
- Tier limity enforced na backende

[SELF-CHECK po implementácii]
□ HTTP kódy správne (200/400/403/404/500)
□ Tier limity enforced na backende
□ Žiadne hardcoded values
□ Existujúca funkcionalita nie je rozbita
□ DB stĺpce majú indexy
□ Error handling pre async operácie
□ Loading states v UI
```

---

## 💰 Cost Optimization

**Cieľ: udržať AI náklady pod 30$/mesiac pri intenzívnom vývoji**

- Haiku na všetky rutinné tasky (10x lacnejší ako Sonnet)
- Sonnet na štandardný vývoj
- Opus len na architektonické rozhodnutia a veľké refaktory
- Grok (xAI) zadarmo / veľmi lacný na planning a review
- `/compact` pri 60% contexte — ušetrí 40-60% tokenov
- Jeden Cursor prompt = jeden dobre definovaný task (nie vague requesty)
- Nikdy nedávaj celý index.html (9225 riadkov) do contextu — použi `@specific-section`

- Používaj TypeScript strict mode
- Všetky komponenty musia mať error handling
- Kód musí byť mobile-first a prístupný
- Žiadne console.log v produkcii
- Komponenty max 300 riadkov