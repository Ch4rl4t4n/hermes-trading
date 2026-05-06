# Hermes — Swing agent roster

Eight active **swing** agents. **LLM** is off in YAML until enabled deliberately. All orders respect **`HERMES_DRY_RUN`** (default `true`).

## Summary table

| # | Symbol | Class | Category | Rola / výber | TF | RSI | SL | TP | Trailing* |
|---|--------|-------|----------|----------------|-----|-----|----|----|-----------|
| 1 | **BTC/USD** | `StableStrategy` | 1 Stable | Krypto, konzervatívny trend-following | 4h | 30/70 | 3% | 8% | +4% |
| 2 | **ETH/USD** | `TrendingStrategy` | 2 Trending | Krypto, vyvážený MR + breakouts | 1h | 35/65 | 4% | 10% | +5% |
| 3 | **SOL/USD** | `VolatileStrategy` | 3 Volatile | Krypto, agresívny momentum + breakouts | 15m | 25/75 | 5% | 12% | +6% |
| 4 | **NVDA** | `TrendingStrategy` | 2 Trending | AI leader, trend pullbacks | 1h | 35/65 | 4% | 10% | +5% |
| 5 | **TSLA** | `VolatileStrategy` | 3 Volatile | Volatilné, breakouts + earnings | 15m | 25/75 | 5% | 12% | +6% |
| 6 | **AMD** | `TrendingStrategy` | 2 Trending | High-beta semis, trend follow | 1h | 35/65 | 4% | 10% | +5% |
| 7 | **GLD** | `StableStrategy` | 1 Stable | Zlato ETF, macro hedge, Fed | 4h | 30/70 | 3% | 8% | +4% |
| 8 | **USO** | `VolatileStrategy` | 3 Volatile | Ropa ETF, geopolitika, news | 15m | 25/75 | 5% | 12% | +6% |

\* **Trailing** = trailing stop sa aktivuje až po tomto zisku od entry (high-water mark), potom platí `trailing_stop_pct` z YAML.

**Kategórie:**  
- **1** — dlhšie držanie (5–15 d)  
- **2** — stredné (3–10 d), MACD crossover ako potvrdenie (ETH, NVDA, AMD)  
- **3** — kratšie (1–7 d), širšie RSI pásma, u SOL/TSLA/USO voliteľné **ATR position sizing**

## Archív (neaktívne)

| Symbol | Dôvod odstránenia z aktívnej sady |
|--------|-----------------------------------|
| AVAX, LINK | Menej likvidné, vysoká korelácia so SOL — duplicita |
| SPY | HODL profil, nie swing — bude samostatná fáza |
| SLV | Satelit GLD; GLD zostáva primárny zlato exposure |

## Konfigurácia

- YAML: `config/agents/<symbol_lowercase>.yaml` (názov súboru, nie ticker v názve)
- Registrácia: `agents/factory.py` podľa `symbol` (presne `BTC/USD`, `ETH/USD`, …)
- Stretégie: `agents/strategies/{stable,trending,volatile}.py` — `get_signal()` → `get_rule_signal()`
