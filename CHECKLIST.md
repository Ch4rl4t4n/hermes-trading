# Hermes — Master Checklist

## Phase 1 — Foundation (Day 1) ✅
- [x] Project skeleton (Python 3.12, venv, requirements.txt)
- [x] `.env` with Alpaca + Anthropic keys, permissions 600
- [x] `BaseAgent` with RSI, EMA, MACD, VWAP, `get_rule_signal()` + `get_signal()` entry
- [x] `AgentConfig` dataclass (all parameters)
- [x] `submit_order()` with DRY_RUN guard
- [x] `check_exit_conditions()` — trailing stop + take profit
- [x] `calculate_qty()` — USD-based with max_position_pct cap
- [x] `is_market_open()` — timezone-aware
- [x] `config_loader.py` — YAML → AgentConfig
- [x] 11 agent files (crypto/stocks/commodities) + factory
- [x] 15 unit tests green

## Phase 2 — Infrastructure (Day 2) ✅
- [x] `DataFeed` — shared price poller, ROLLING_WINDOW=200
- [x] `hermes.py` — asyncio orchestrator, kill switch, SIGTERM
- [x] Exponential backoff (10s/30s/60s, suspend after 4th fault)
- [x] Portfolio value cache (TTL=300s)
- [x] Daily limits: max_trades_per_day, max_daily_loss_pct
- [x] `reset_daily_counters_if_new_day()`
- [x] `bootstrap_price_history()` + `_sync_prices_from_feed()`
- [x] Telegram notifications (start / kill switch / suspension)
- [x] LLM placeholders in AgentConfig + stubs in BaseAgent
- [x] 25 unit tests green

## Phase 3 — Strategy Refactor (Day 3) ✅
- [x] Archive: AVAX, LINK, SPY, SLV → config/agents/_archived/
- [x] New agent roster: BTC, ETH, SOL (crypto) + NVDA, TSLA, AMD (stocks) + GLD, USO (commodities)
- [x] `StableStrategy` (BTC, GLD): RSI 30/70, 4h, SL 3%, TP 8%, trailing after +4%
- [x] `TrendingStrategy` (ETH, NVDA, AMD): RSI 35/65, 1h, SL 4%, TP 10%, MACD crossover
- [x] `VolatileStrategy` (SOL, TSLA, USO): RSI 25/75, 15m, SL 5%, TP 12%, ATR sizing
- [x] `trailing_activate_pct` + high water mark trailing stop in BaseAgent
- [x] `timeframe` + `atr_position_sizing` fields in AgentConfig
- [x] `agents/strategies/` package with 3 strategy classes
- [x] 8 updated YAML configs + AMD new
- [x] `factory.py` updated (removed 4, added AMD)
- [x] Strategy unit tests added
- [x] All tests green

## Phase 4 — LLM Layer (Day 4) ✅
- [x] `LLMAdvisor` class — `core/llm_advisor.py` (Haiku / Sonnet via `HERMES_LLM_*_MODEL`)
- [x] Rate limiter — per-agent hourly cap (`llm_max_calls_per_hour`, UTC hour reset)
- [x] `get_llm_context()` — extended for all 8 agents (strategy, timeframe, drivers)
- [x] `BaseAgent._apply_llm_if_enabled` + `custom_signal_override()` after LLM
- [x] Prompt caching — `cache_control: ephemeral` on static system block
- [x] LLM when `llm_enabled` and `confidence >= llm_trigger_threshold` (after rule threshold)
- [x] Sonnet when `confidence >= llm_use_sonnet_above`, else Haiku
- [x] Logging + `logs/llm_audit.log` (JSONL, gitignored)
- [x] Tests: `tests/test_llm_advisor.py` (parse JSON, rate limit, mocked API)

## Phase 5 — Dashboard (Day 5) ✅
- [x] FastAPI: `/api/status`, `/api/agents`, `/api/positions`, `/api/risk`, `POST /api/kill` (`core/dashboard_app.py`)
- [x] WebSocket `/ws/prices?key=…` (1 Hz JSON feed; optional `HERMES_DASHBOARD_ENABLE`, `DASHBOARD_API_KEY`)
- [x] `GET /` — minimal HTML (agents table, kill, localStorage API key)
- [x] Auth: header `X-API-Key` (or `Authorization: Bearer`) + tests `tests/test_dashboard.py`
- [x] Uvicorn task in `Hermes._run_dashboard()` (same process as trading loop)

## Phase 6 — Live Trading Readiness (code) ✅  *(operational: paper ≥2 weeks — manual)*
- [ ] Paper trading validation in production (min 2 weeks) — run manually
- [x] Idempotent kill switch — only first `activate_kill_switch` runs SELL + Telegram; SIGTERM / concurrent calls are safe
- [x] MACD signal line: EMA(9) of MACD history + per-tick cache to avoid double-append in `TrendingStrategy`
- [x] Risk: very low RSI (knife) tames BUY confidence; `GET /api/risk` exposure vs portfolio
- [x] `ALPACA_PAPER=false` + not dry → requires `HERMES_LIVE_CONFIRM=I_UNDERSTAND`
- [x] `HERMES_DAILY_LOSS_ALERT_PCT` (default 1.5) — one Telegram per agent per day
- [x] `reconcile_agent_positions()` on startup + Telegram on mismatch

## Strategic refactor — 8 swing agents (Q2 2026) ✅
- [x] Finálne zloženie: 3 crypto + 3 stock + 2 komodity-ETF, dokumentované v `docs/AGENTS.md`
- [x] YAML parametre zladené s kategóriami 1/2/3 (RSI, TF, SL/TP, trailing, ATR kde treba)
- [x] `get_signal()` explicitne v `StableStrategy` / `TrendingStrategy` / `VolatileStrategy`
- [x] `ARCHITECTURE.md` + sekcia Agent Strategies; žiadne zmeny LLM logiky (v YAML `llm.enabled: false`)
- [x] Testy: `get_signal` vs `get_rule_signal`, `eth.yaml` load, existujúce strategy testy

## Phase 7 — Supplemental data (doplnkové API) ✅ *(optional vendors later)*
- [x] Dohodnutý počet a symboly pre swing sadu (8) — HODL/SPY samostatne
- [x] `MarketDataProvider` + `get_yfinance_last()` v `core/market_data/provider.py` (yfinance in `requirements.txt`)
- [x] `docs/DATA_PROVIDERS.md` — limity, žiadne kľúče v gite, Alpaca zostáva primary
- [ ] (Voliteľné) Finnhub, Polygon, CMC, … + samostatné kľúče a rate limity
- [x] `DataFeed` — robustnejší stock bootstrap, ak Alpaca nevráti očakávaný kľúč
