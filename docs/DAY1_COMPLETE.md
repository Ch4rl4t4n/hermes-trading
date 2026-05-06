# Day 1 — Complete

## Goal
Bootstrap the Hermes trading platform: project skeleton, BaseAgent with technical indicators, first agent configs, and Alpaca connectivity.

## What was built

### Project skeleton
- Python 3.12, virtualenv, `requirements.txt` (alpaca-py, pyyaml, python-telegram-bot, fastapi, uvicorn, pytest)
- `.env` with `ALPACA_API_KEY`, `ALPACA_API_SECRET`, `ANTHROPIC_API_KEY`, `HERMES_DRY_RUN=true`
- `.env` permissions set to 600

### `agents/base_agent.py`
- `AgentConfig` dataclass — all agent parameters in one place
- `SignalResult` dataclass — direction/confidence/reason
- `BaseAgent` abstract class with:
  - RSI calculation (period-configurable, flat-market fix: returns 50.0)
  - EMA calculation (proper history-seeded, not simplified)
  - MACD (ema12 - ema26, approximate signal line)
  - VWAP (simple mean of price history)
  - `get_rule_signal()` — RSI + MACD + VWAP fusion
  - `submit_order()` — DRY_RUN mode logs instead of sending
  - `check_exit_conditions()` — trailing stop + take profit
  - `calculate_qty()` — USD-based position sizing with max_position_pct cap
  - `is_market_open()` — timezone-aware

### `core/config_loader.py`
- `load_agent_config(path)` — parses YAML to AgentConfig
- `load_all_agents(dir)` — loads all enabled agents from directory

### `agents/` — first agent files
- `agents/crypto/`: BTC, ETH, SOL, AVAX, LINK (all thin subclasses)
- `agents/stocks/`: SPY, TSLA, NVDA
- `agents/commodities/`: GLD, SLV, USO
- `agents/factory.py` — symbol → class registry

### `config/agents/` — YAML configs
11 files: btc, eth, sol, avax, link, spy, tsla, nvda, gld, slv, uso

### Tests
- 15 unit tests covering RSI, MACD, signal fusion, market hours, daily limits, config loading

## Key decisions
- DRY_RUN=true is the default — no real trades unless explicitly disabled
- `asset_type: "commodity_etf"` for GLD/SLV/USO (treated as stocks for market hours)
- MACD signal line is an approximation (`macd_line * 0.2`); noted as known gap
