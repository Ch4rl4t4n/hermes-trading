# Hermes — Roadmap

## Status: Day 4 + Day 5–7 (code) complete; paper validation manual

| Day | Phase | Status |
|-----|-------|--------|
| 1 | Foundation — BaseAgent, config, first 11 agents | ✅ Done |
| 2 | Infrastructure — DataFeed, kill switch, daily limits, Telegram | ✅ Done |
| 3 | Strategy refactor — 3 strategies × 8 agents, ATR, MACD crossover | ✅ Done |
| 4 | LLM layer — Anthropic API, per-agent context, rate limiting | ✅ Done |
| 5 | Dashboard — FastAPI, WebSocket, web UI (HERMES), login (shako/shako + cookie), kill switch | ✅ Done |
| 6 | Live readiness — code guards, recon, MACD, alerts, risk API | ✅ Done* |
| 7 | Free data — `market_data` + yfinance optional | ✅ Done* |

*\* Day 6: **paper ≥2 weeks** and formal go/no-go is an operational process, not a code deliverable. Day 7: Finnhub/Polygon/… integrations are optional follow-ups; Alpaca + optional yfinance helper are in place.*

---

## Phase 4.5 — Planned queue (Owner-only Universal CMS)

**Štart až po dokončení aktuálne otvorených položiek** v produktovej roadmape (prehľad nižšie / **`CLAUDE.md` → Fáza 5 nezaškrtnuté úlohy**) alebo po výslovnom GO vlastníka.

| Položka | Popis |
|---------|--------|
| **Názov** | Universal CMS & Design System Regenerator (interné, bez dopadu na bežných userov) |
| **Owner** | Jedna rola `owner` (nie len „admin“ tier); výhradný prístup |
| **Ciele** | Universal import (ZIP/JSON/CSS/Tailwind/text), AI analyze/remap/generate, manuálny UI editor, história verzií, one-click apply na web + PWA |
| **Hermes stack** | Vite React + Flask/FastAPI + Postgres + Redis + Anthropic (nie povinný Next/shadcn z pôvodného PDF úvodníka) |
| **Detail špecifikácie** | `.cursor/rules/CLAUDE.md` — sekcia **Fáza 4.5** (Verzia špecu 1.6 \| 8. mája 2026 zadaná vlastníkom) |

---

## Wishlist — fázy produktu (prehľad)

Rozdelenie práce podľa predstavy „dashboard → dáta → logika → produkcia“. S `HERMES` webom už máš **sledovanie** agentov (ceny, stav, kill switch); **nastavovanie** agentov z UI (YAML / pause / parametre v prehliadači) je ďalší krok v kóde, nie je ešte kompletné API.

### Fáza 1: Dashboard (web UI)
- Dizajn (Claude / koncept) → implementácia (Cursor) → **hotové v repozitári** (`core/dashboard.html`, `core/dashboard_app.py`).
- Prihlásenie: predvolené **shako / shako** (`DASHBOARD_USER`, `DASHBOARD_PASSWORD`), relácia cez HTTP-only cookie + voliteľne `X-API-Key` pre skripty.
- **Hosting na serveri:** Nginx ako reverse proxy pred Uvicorn, TLS (Let’s Encrypt), firewall (iba 80/443 verejne).

### Fáza 2: Free API integrácia
- Napojiť kontext pre agentov: napr. CoinMarketCap, Fear & Greed, Yahoo Finance (cez existujúci yfinance / rozšírenie), FRED, Alpaca News alebo iné news zdroje podľa limitov.
- Jednotná vrstva kľúčov a rate limitov v `.env` — nič z kľúčov do gitu.

### Fáza 3: Lepšia logika obchodovania
- Anthropic: overiť náklady, modely, či LLM reálne beží podľa `AgentConfig`; prípadné ladenie promptov.
- Risk: veľkosť pozície, drawdown limity, doladenie SL/TP / trailing.

### Fáza 4: Production-ready
- Backtest na historických dátaich; monitoring a alerting; kill switch (už v jadre + v dashboarde); logovanie a audit trail pre rozhodnutia a príkazy.

---

## Čo musíš získať / pripraviť (aby sa to dalo nasadiť a rozširovať)

Nižšie je checklist **ty alebo tím** musíte mať k dispozícii — bez toho sa integrácia v Cursori nedá „dokončiť“ len z kódu (chýbajú kľúče, účty alebo infraštruktúra).

### Hermes už teraz (minimum na beh)
| Čo | Na čo to je | Kde to získať |
|----|-------------|---------------|
| **Alpaca API Key + Secret** | príkazy a účet (paper odporúčané na začiatok) | [alpaca.markets](https://alpaca.markets) → Paper Trading |
| **ANTHROPIC_API_KEY** | LLM vrstva (Haiku/Sonnet) | [console.anthropic.com](https://console.anthropic.com) |
| **DASHBOARD_API_KEY** | API a podpis session cookie; skripty s hlavičkou `X-API-Key` | vygeneruj si dlhý náhodný reťazec; vlož do `.env` |
| **DASHBOARD_USER / DASHBOARD_PASSWORD** | web login (predvolené shako/shako — v produkcii zmeň) | `.env` na serveri |
| **TELEGRAM_BOT_TOKEN + CHAT_ID** (voliteľné) | alerty | [@BotFather](https://t.me/BotFather), vlastný chat ID |
| **DISCORD_WEBHOOK_URL** (voliteľné) | notifikácie | Discord server → Integrations → Webhook |
| **Stroj s Pythonom 3.12+** | beh `hermes` + Uvicorn | VPS, PC, Raspberry Pi… |
| **`.env` súbor** | tajomstvá mimo gitu | kopíruj z `.env.example` a doplň hodnoty |

### Fáza 1 — verejný web dashboard (ak chceš z internetu)
| Čo | Na čo to je |
|----|-------------|
| **VPS alebo server** (Linux) | 24/7 alebo kedy potrebuješ mať UI vonku |
| **Doména** (voliteľná) | pekná URL namiesto IP |
| **Nginx** | reverse proxy → `127.0.0.1:DASHBOARD_PORT` |
| **TLS certifikát** | Let’s Encrypt (certbot) alebo Cloudflare proxy |
| **Firewall** | otvorené len 80/443; dashboard neexponuj na surovú IP:port bez TLS, ak ide z internetu |
| **SSH kľúče** | bezpečný prístup na server (ty spravuješ; agent len potrebuje prístup ak deployuješ odtiaľ) |

### Fáza 2 — externé dáta (podľa toho, čo zapojíme)
| Čo | Poznámka |
|----|----------|
| Účty a **API kľúče** u každého poskytovateľa (CMC, FRED, …) | väčšina má free tier s dennými limitmi — treba si prečítať aktuálne podmienky |
| **Overený e-mail** pri registrácii | často povinné pred vydaním kľúča |
| **Súhlas s ToS** | obzvlášť pri komerčnom alebo bot use-case |

### Fáza 3 — obchodná logika a LLM
| Čo | Poznámka |
|----|----------|
| **Anthropic billing / kredity** | na reálne volania mimo free trial |
| **Stratégia rizika** v číslach (max. % portfólia, max. denná strata) | musíš vedieť ty — kód to vie obmedziť, limity sú tvoje rozhodnutie |

### Fáza 4 — produkcia
| Čo | Poznámka |
|----|----------|
| **Historické dáta** na backtest | podľa symbolov (Alpaca, súbory, alebo platený data vendor) |
| **Monitoring** (voliteľné: Sentry, Uptime, logy) | odporúčané pred reálnymi peniazmi |
| **Proces** paper ≥2 weeks + go/no-go | operatívne; nie len technický checkbox |

### Čo **ne treba** na úvod
- Vlastná burza mimo Alpaca (Hermes je postavený na Alpaca API).
- Verejná IP, ak bežíš len lokálne (`localhost` alebo LAN).

---

## Day 4 plan — LLM Layer

### Goal
Wire the LLM placeholders that already exist in BaseAgent/AgentConfig into real Anthropic API calls.

### Scope
1. `core/llm_advisor.py` — `LLMAdvisor` class
   - Takes signal + market context → returns override decision
   - Haiku by default; switches to Sonnet when confidence ≥ `llm_use_sonnet_above`
   - Rate limiter: `llm_max_calls_per_hour` per agent
   - Prompt caching: system prompt cached (saves tokens on repeated calls)

2. `BaseAgent.tick()` — replace `# LLM layer will be added in Phase 4` comment
   - Call `get_llm_context()` (already populated per-agent)
   - Call `custom_signal_override(signal)` (returns modified SignalResult)
   - Only invoke when `llm_enabled=True` and confidence in trigger range

3. `agents/` — populate `get_llm_context()` for all 8 agents
   - Include asset-specific context (sector, key drivers, recent regime)

4. Tests
   - Mock Anthropic API
   - Test rate limiting logic
   - Test Haiku vs Sonnet routing

### API cost estimate (dry run, no live trades)
- 8 agents × 6 calls/hour × 16h/day ≈ 768 Haiku calls/day
- At $0.00025/1K input tokens, ~$0.10/day during development

## Architecture overview

```
hermes.py (asyncio loop)
  └─ DataFeed (shared price poller)
  └─ Agent × 8 (one asyncio task each)
       └─ StableStrategy / TrendingStrategy / VolatileStrategy
            └─ BaseAgent (RSI, MACD, VWAP, order submission)
                 └─ LLMAdvisor (optional, Anthropic API)
  └─ TelegramNotifier (fire-and-forget)
  └─ FastAPI Dashboard (uvicorn, optional)
```

## Agent roster (8 swing — strategic refactor 2026-Q2)

| Symbol | Category | Rola (skrátene) | TF | RSI | SL | TP |
|--------|----------|-----------------|-----|-----|----|----|
| BTC/USD | Stable | Konzervatívny trend | 4h | 30/70 | 3% | 8% |
| GLD | Stable | Macro hedge, zlato | 4h | 30/70 | 3% | 8% |
| ETH/USD | Trending | MR + breakouts | 1h | 35/65 | 4% | 10% |
| NVDA | Trending | AI, trend pullbacks | 1h | 35/65 | 4% | 10% |
| AMD | Trending | High-beta semis | 1h | 35/65 | 4% | 10% |
| SOL/USD | Volatile | Momentum + breakouts | 15m | 25/75 | 5% | 12% |
| TSLA | Volatile | Earnings, breakouts | 15m | 25/75 | 5% | 12% |
| USO | Volatile | Ropa, news | 15m | 25/75 | 5% | 12% |

## Planned (Phase 7) — Počet agentov + free / freemium API

**Stav:** Dohodnuté s tímom: upraví sa počet a zostava agentov; následne sa zapoja ďalšie free/freemium služby na dáta. **V kóde to ešte nie je** — až keď bude hotové jadro (Dashboard + aspoň základná stabilita z fázy 6).

**Počet agentov:** Cieľová tabuľka symbolov sa zmení po rozhodnutí (menej / viac agentov, iné tickery). Výsledok sa premietne do `config/agents/*.yaml`, `factory.py` a `get_llm_context()`.

**Doplnkové dáta (kandidáti — žiadne kľúče v repozitári):** integrovať až **po** dohodnutom rosteri, s vlastnými kľúčmi v `.env` (limity free tieru rešpektovať v jednotnom rate-limit vrstve).

| Priorita (orient.) | Služba | Poznámka |
|--------------------|--------|----------|
| 1 | **Finnhub** | Stock/forex/crypto, REST + WS, štedrý free tier; vhodné na ceny + news/sentiment. |
| 2 | **yfinance** | Bez kľúča, rýchle prototypy; nie na kritické HFT. |
| 3 | **Twelve Data** | Multi-asset, denné limity — dobré na indikátory. |
| 4 | **FCS API** | Veľa symbolov, jednoduché endpointy. |
| 5 | **Polygon.io** | Kvalitné dáta + WS; free plán s obmedzeniami. |
| 6 | **Alpha Vantage** | Klasika, nízke denné limity. |
| 7 | **CoinMarketCap / CoinGecko** | Hlavne crypto metadáta / ceny / história. |
| 8 | **Exchangerate.host / Fixer** | Forex kurzy, konverzie. |
| 9 | **Binance API** | Ak by obchod išiel priamo cez burzu (iný flow ako Alpaca). |

**Architektúrny smer:** Hermes dnes berie ceny a príkazy cez **Alpaca**. Nové zdroje nebudú „mágicky“ nahrádzať Alpaca dôveryhodnosť; rozumné je: **(A)** deduplikovanie / kontrola cien, **(B)** sentiment / news do LLM kontextu, **(C)** fallback pri výpadku, **(D)** oddelený modul s jednotným `MarketDataProvider` + kvótami. Konkrétne balíčky a limity dohodnúť pred implementáciou.

**Kde to v budúcnosti „napojiť“ (orientačné súbory):** `core/data_feed.py` (ceny + história), prípadne nový `core/market_data/` + volanie z `BaseAgent` alebo z LLM `get_llm_context()`; kľúče do `.env` a `.env.example` — **žiadne kľúče do gitu**.

---

*Poznámka: Túto sekciu sme pridali podľa plánu s Claude; dátum overenia free tierov v zdrojoch z 2024 sa môže zmeniť — pred nasadením overiť aktuálne limity u každého poskytovateľa.*
