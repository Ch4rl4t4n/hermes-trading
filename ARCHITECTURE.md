# Hermes — Architecture

Trading orchestration service: shared **DataFeed**, one **asyncio** task per agent, **Alpaca** for market data and orders (paper/live), optional **Telegram** notifications, optional **LLM** layer (disabled in config by default).

## High-level flow

```
core/hermes.py (Hermes.run)
  ├── DataFeed — poll prices, rolling history per symbol
  ├── load_all_agents → create_agent() per YAML
  └── Per agent: asyncio task → BaseAgent.tick()
         ├── get_signal() → strategy-specific logic
         ├── optional LLM review (if enabled in YAML)
         └── submit_order() (DRY_RUN or live)
```

## Agent Strategies

Eight **swing** agents (no HODL basket in this release). Each maps to a **strategy class** in `agents/strategies/`:

| Class | Category | Symbols | Timeframe | Core idea |
|-------|----------|-----------|-----------|-----------|
| `StableStrategy` | 1 — stable (≈5–15d) | BTC/USD, GLD | 4h | RSI 30/70, SL 3%, TP 8%, trailing after +4% |
| `TrendingStrategy` | 2 — trending (≈3–10d) | ETH/USD, NVDA, AMD | 1h | RSI 35/65, MACD crossover boost, SL 4%, TP 10%, trailing after +5% |
| `VolatileStrategy` | 3 — volatile (≈1–7d) | SOL/USD, TSLA, USO | 15m | RSI 25/75, ATR sizing when enabled, SL 5%, TP 12%, trailing after +6% |

**Signal path:** `BaseAgent.tick()` calls `get_signal()`, which each strategy implements (typically delegating to `get_rule_signal()` where extra logic such as MACD crossover or ATR sizing applies). The composite `get_rule_signal()` in `BaseAgent` combines RSI, MACD histogram, and VWAP into a `SignalResult`.

**Session hours:** crypto agents use `UTC` 24/7. Stocks and commodity ETFs use `America/New_York` **09:30–16:00** RTH (regular trading hours) per project decision.

**Archived symbols** (not loaded): `config/agents/_archived/` — AVAX, LINK, SPY, SLV (kept for reference only).

## Key directories

- `config/agents/*.yaml` — one file per live agent
- `agents/crypto|stocks|commodities/` — thin subclasses wiring strategy + optional `get_llm_context`
- `core/` — `hermes`, `data_feed`, `config_loader`, `dashboard_app` (FastAPI), `reconciliation`, optional `llm_advisor`, `market_data/`
- `docs/` — `AGENTS.md`, `DATA_PROVIDERS.md`

## Dashboard (Day 5)

When `HERMES_DASHBOARD_ENABLE=true` and `DASHBOARD_API_KEY` is set, Hermes starts **uvicorn** alongside agents: REST `GET /api/status|agents|positions|risk`, `POST /api/kill` (header `X-API-Key`), `GET /` static UI, WebSocket `/ws/prices?key=…` for price JSON. Without an API key the API returns 401.

## Reconciliation & live safety

On startup, `reconcile_agent_positions()` compares Alpaca open positions to each agent’s `position_qty`. Mismatches are logged and optionally sent to Telegram.

If `ALPACA_PAPER=false` and not in `HERMES_DRY_RUN`, Hermes refuses to start unless `HERMES_LIVE_CONFIRM=I_UNDERSTAND`.

## Runtime

- `HERMES_DRY_RUN=true` (default): log orders, no Alpaca submission
- `ALPACA_*` + `ANTHROPIC_API_KEY` (if LLM enabled) via `.env`
