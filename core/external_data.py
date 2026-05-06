"""
External Data Service - free API data sources for Hermes Trading Platform
1. Crypto Fear & Greed (alternative.me)
2. Stocks Fear & Greed (CNN)
3. CoinGecko (market cap, volume)
4. Alpaca News
5. Yahoo Finance (earnings, fundamentals)
6. FRED (macro data)
7. CoinMarketCap (rankings, global metrics, quotes)
"""
import asyncio
import logging
import os
import time
from typing import Any, Dict
from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger("external_data")

# Cache
_cache: Dict[str, dict] = {}
CACHE_TTL = {
    "fg_crypto": 3600,
    "fg_stocks": 3600,
    "coingecko": 300,
    "news": 300,
    "yahoo": 3600,
    "fred": 86400,
    "cmc": 300,
    "cmc_global": 3600,
    "cmc_asi": 3600,
}


def _cached(k):
    return k in _cache and (time.time() - _cache[k]["ts"]) < CACHE_TTL.get(k.split(":")[0], 300)


def _put(k, d):
    _cache[k] = {"d": d, "ts": time.time()}


def _get(k):
    return _cache.get(k, {}).get("d")


# ── 1. CRYPTO FEAR & GREED ──
async def get_crypto_fear_greed():
    if _cached("fg_crypto"):
        return _get("fg_crypto")
    try:
        import aiohttp
        async with aiohttp.ClientSession() as s:
            async with s.get("https://api.alternative.me/fng/?limit=1") as r:
                data = await r.json()
                entry = data["data"][0]
                res = {"value": int(entry["value"]), "label": entry["value_classification"]}
                _put("fg_crypto", res)
                log.info("Crypto F&G: %d (%s)", res["value"], res["label"])
                return res
    except Exception as e:
        log.warning("Crypto F&G failed: %s", e)
        return _get("fg_crypto") or {"value": 50, "label": "Neutral"}


# ── 2. STOCKS FEAR & GREED ──
async def get_stocks_fear_greed():
    if _cached("fg_stocks"):
        return _get("fg_stocks")
    try:
        import aiohttp
        async with aiohttp.ClientSession() as s:
            url = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
            hdrs = {"User-Agent": "Mozilla/5.0"}
            async with s.get(url, headers=hdrs) as r:
                data = await r.json()
                fg = data.get("fear_and_greed", {})
                res = {"value": round(fg.get("score", 50)), "label": fg.get("rating", "Neutral")}
                _put("fg_stocks", res)
                log.info("Stocks F&G: %d (%s)", res["value"], res["label"])
                return res
    except Exception as e:
        log.warning("Stocks F&G failed: %s", e)
        return _get("fg_stocks") or {"value": 50, "label": "Neutral"}


# ── 3. COINGECKO ──
COINGECKO_IDS = {"BTC/USD": "bitcoin", "ETH/USD": "ethereum", "SOL/USD": "solana"}


async def get_coingecko_data(symbol):
    cid = COINGECKO_IDS.get(symbol)
    if not cid:
        return {}
    k = "coingecko:" + symbol
    if _cached(k):
        return _get(k)
    try:
        import aiohttp
        async with aiohttp.ClientSession() as s:
            url = (
                "https://api.coingecko.com/api/v3/coins/" + cid
                + "?localization=false&tickers=false&community_data=false&developer_data=false"
            )
            async with s.get(url) as r:
                data = await r.json()
                md = data.get("market_data", {})
                res = {
                    "market_cap": md.get("market_cap", {}).get("usd", 0),
                    "volume_24h": md.get("total_volume", {}).get("usd", 0),
                    "change_24h": md.get("price_change_percentage_24h", 0),
                    "change_7d": md.get("price_change_percentage_7d", 0),
                }
                _put(k, res)
                log.info("CoinGecko %s: vol=%s, 24h=%.1f%%", symbol, res["volume_24h"], res["change_24h"])
                return res
    except Exception as e:
        log.warning("CoinGecko %s failed: %s", symbol, e)
        return _get(k) or {}


# ── 4. ALPACA NEWS ──
async def get_alpaca_news(symbol, limit=5):
    clean = symbol.replace("/", "")
    k = "news:" + clean
    if _cached(k):
        return _get(k)
    try:
        from alpaca.data.historical.news import NewsClient
        from alpaca.data.requests import NewsRequest

        client = NewsClient(
            os.getenv("ALPACA_API_KEY", ""),
            os.getenv("ALPACA_API_SECRET", ""),
        )
        raw = client.get_news(NewsRequest(symbols=clean, limit=limit))
        news_dict = dict(raw)
        articles = news_dict.get("data", {}).get("news", [])
        res = [
            {
                "headline": getattr(a, "headline", ""),
                "source": getattr(a, "source", ""),
                "summary": (getattr(a, "summary", "") or "")[:200],
                "created_at": str(getattr(a, "created_at", "")),
            }
            for a in articles
        ]
        _put(k, res)
        log.info("Alpaca News %s: %d articles", symbol, len(res))
        return res
    except Exception as e:
        log.warning("Alpaca News %s failed: %s", symbol, e)
        return _get(k) or []


# ── 5. YAHOO FINANCE ──
async def get_yahoo_data(symbol):
    clean = symbol.replace("/USD", "").replace("/", "")
    k = "yahoo:" + clean
    if _cached(k):
        return _get(k)
    try:
        import yfinance as yf

        info = yf.Ticker(clean).info or {}
        res = {
            "pe_ratio": info.get("trailingPE"),
            "market_cap": info.get("marketCap"),
            "52w_high": info.get("fiftyTwoWeekHigh"),
            "52w_low": info.get("fiftyTwoWeekLow"),
            "recommendation": info.get("recommendationKey"),
        }
        _put(k, res)
        log.info("Yahoo %s: PE=%s, rec=%s", symbol, res["pe_ratio"], res["recommendation"])
        return res
    except Exception as e:
        log.warning("Yahoo %s failed: %s", symbol, e)
        return _get(k) or {}


# ── 6. FRED (macro) ──
FRED_SERIES = {
    "fed_rate": "FEDFUNDS",
    "cpi": "CPIAUCSL",
    "unemployment": "UNRATE",
    "treasury_10y": "DGS10",
}


async def get_fred_data():
    k = "fred"
    if _cached(k):
        return _get(k)
    fred_key = os.getenv("FRED_API_KEY", "")
    if not fred_key:
        return {"error": "FRED_API_KEY not set"}
    try:
        import aiohttp

        result = {}
        async with aiohttp.ClientSession() as s:
            for name, sid in FRED_SERIES.items():
                url = (
                    "https://api.stlouisfed.org/fred/series/observations"
                    + "?series_id=" + sid
                    + "&api_key=" + fred_key
                    + "&file_type=json&limit=1&sort_order=desc"
                )
                async with s.get(url) as r:
                    data = await r.json()
                    obs = data.get("observations", [])
                    if obs and obs[0]["value"] != ".":
                        result[name] = {"value": float(obs[0]["value"]), "date": obs[0]["date"]}
        _put(k, result)
        log.info("FRED: %s", list(result.keys()))
        return result
    except Exception as e:
        log.warning("FRED failed: %s", e)
        return _get(k) or {}


# ── 7. COINMARKETCAP ──
CMC_SLUGS = {"BTC/USD": "bitcoin", "ETH/USD": "ethereum", "SOL/USD": "solana"}
CMC_BASE = "https://pro-api.coinmarketcap.com"


async def get_cmc_quote(symbol):
    """Get latest quote from CoinMarketCap for a crypto symbol."""
    slug = CMC_SLUGS.get(symbol)
    if not slug:
        return {}
    k = "cmc:" + symbol
    if _cached(k):
        return _get(k)
    cmc_key = os.getenv("CMC_API_KEY", "")
    if not cmc_key:
        return {"error": "CMC_API_KEY not set"}
    try:
        import aiohttp
        async with aiohttp.ClientSession() as s:
            url = CMC_BASE + "/v1/cryptocurrency/quotes/latest"
            params = {"slug": slug, "convert": "USD"}
            headers = {"X-CMC_PRO_API_KEY": cmc_key, "Accept": "application/json"}
            async with s.get(url, params=params, headers=headers) as r:
                data = await r.json()
                if data.get("status", {}).get("error_code", 0) != 0:
                    raise Exception(data["status"].get("error_message", "Unknown error"))
                coins = data.get("data", {})
                coin = list(coins.values())[0] if coins else {}
                quote = coin.get("quote", {}).get("USD", {})
                res = {
                    "price": quote.get("price"),
                    "volume_24h": quote.get("volume_24h"),
                    "market_cap": quote.get("market_cap"),
                    "change_1h": quote.get("percent_change_1h"),
                    "change_24h": quote.get("percent_change_24h"),
                    "change_7d": quote.get("percent_change_7d"),
                    "change_30d": quote.get("percent_change_30d"),
                    "market_cap_dominance": quote.get("market_cap_dominance"),
                    "cmc_rank": coin.get("cmc_rank"),
                    "circulating_supply": coin.get("circulating_supply"),
                    "max_supply": coin.get("max_supply"),
                }
                _put(k, res)
                log.info("CMC %s: price=$%.2f, 24h=%.1f%%, rank=%s",
                         symbol, res["price"] or 0, res["change_24h"] or 0, res["cmc_rank"])
                return res
    except Exception as e:
        log.warning("CMC %s failed: %s", symbol, e)
        return _get(k) or {}


async def get_cmc_global_metrics():
    """Get global crypto market metrics from CoinMarketCap."""
    k = "cmc_global"
    if _cached(k):
        return _get(k)
    cmc_key = os.getenv("CMC_API_KEY", "")
    if not cmc_key:
        return {"error": "CMC_API_KEY not set"}
    try:
        import aiohttp
        async with aiohttp.ClientSession() as s:
            url = CMC_BASE + "/v1/global-metrics/quotes/latest"
            headers = {"X-CMC_PRO_API_KEY": cmc_key, "Accept": "application/json"}
            async with s.get(url, headers=headers) as r:
                data = await r.json()
                gd = data.get("data", {})
                quote = gd.get("quote", {}).get("USD", {})
                res = {
                    "total_market_cap": quote.get("total_market_cap"),
                    "total_volume_24h": quote.get("total_volume_24h"),
                    "btc_dominance": gd.get("btc_dominance"),
                    "eth_dominance": gd.get("eth_dominance"),
                    "active_cryptocurrencies": gd.get("active_cryptocurrencies"),
                    "total_cryptocurrencies": gd.get("total_cryptocurrencies"),
                    "active_exchanges": gd.get("active_exchanges"),
                    "defi_volume_24h": gd.get("defi_volume_24h"),
                    "stablecoin_volume_24h": gd.get("stablecoin_volume_24h"),
                }
                _put(k, res)
                log.info("CMC Global: total_cap=$%.0fB, btc_dom=%.1f%%",
                         (res["total_market_cap"] or 0) / 1e9, res["btc_dominance"] or 0)
                return res
    except Exception as e:
        log.warning("CMC Global failed: %s", e)
        return _get(k) or {}


def _parse_altcoin_season_payload(data: Any) -> dict:
    """Extract index 0–100 from CMC altcoin-season-index/latest `data` field."""
    if data is None:
        return {}
    if isinstance(data, (int, float, str)):
        try:
            v = int(round(float(data)))
            data = {"value": max(0, min(100, v))}
        except (TypeError, ValueError):
            return {}
    row = data
    if isinstance(data, list) and data:
        row = data[0]
    if not isinstance(row, dict):
        return {}
    val = (
        row.get("value")
        or row.get("altcoin_season_index")
        or row.get("index")
        or row.get("score")
    )
    if val is None:
        return {}
    try:
        v = int(round(float(val)))
    except (TypeError, ValueError):
        return {}
    v = max(0, min(100, v))

    def _opt_int(key):
        x = row.get(key)
        if x is None:
            return None
        try:
            return max(0, min(100, int(round(float(x)))))
        except (TypeError, ValueError):
            return None

    if v >= 75:
        season = "altcoin"
        label = "Altcoin season"
    elif v <= 25:
        season = "bitcoin"
        label = "Bitcoin season"
    else:
        season = "neutral"
        label = "Neutral"

    out = {
        "value": v,
        "season": season,
        "label": label,
        "yesterday": _opt_int("yesterday") or _opt_int("value_yesterday"),
        "last_week": _opt_int("last_week") or _opt_int("value_last_week"),
        "last_month": _opt_int("last_month") or _opt_int("value_last_month"),
    }
    return {k: x for k, x in out.items() if x is not None}


async def get_cmc_altcoin_season_latest():
    """Latest CMC Altcoin Season Index (0 = Bitcoin season … 100 = Altcoin season)."""
    k = "cmc_asi"
    if _cached(k):
        return _get(k)
    cmc_key = os.getenv("CMC_API_KEY", "")
    if not cmc_key:
        return {"error": "CMC_API_KEY not set"}
    try:
        import aiohttp
        async with aiohttp.ClientSession() as s:
            url = CMC_BASE + "/v1/altcoin-season-index/latest"
            headers = {"X-CMC_PRO_API_KEY": cmc_key, "Accept": "application/json"}
            async with s.get(url, headers=headers) as r:
                data = await r.json()
                st = data.get("status") or {}
                if st.get("error_code", 0) != 0:
                    raise Exception(st.get("error_message", "Unknown error"))
                parsed = _parse_altcoin_season_payload(data.get("data"))
                if not parsed:
                    raise Exception("empty altcoin season payload")
                _put(k, parsed)
                log.info("CMC Altcoin Season: %s (%s)", parsed.get("value"), parsed.get("label"))
                return parsed
    except Exception as e:
        log.warning("CMC Altcoin Season failed: %s", e)
        return _get(k) or {"error": str(e)}


# ── MASTER: Get all context for an agent ──
async def get_market_context(symbol, asset_type="crypto"):
    """Collect all external data relevant for a given symbol."""
    tasks = {
        "crypto_fg": get_crypto_fear_greed(),
        "stocks_fg": get_stocks_fear_greed(),
        "news": get_alpaca_news(symbol),
    }
    if asset_type == "crypto":
        tasks["coingecko"] = get_coingecko_data(symbol)
        tasks["cmc_quote"] = get_cmc_quote(symbol)
        tasks["cmc_global"] = get_cmc_global_metrics()
    else:
        tasks["yahoo"] = get_yahoo_data(symbol)
        tasks["fred"] = get_fred_data()

    results = {}
    for name, coro in tasks.items():
        try:
            results[name] = await coro
        except Exception as e:
            results[name] = {"error": str(e)}
    return results


# ── Quick test ──
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    async def test():
        print("=== Testing External Data Service ===\n")
        ctx = await get_market_context("BTC/USD", "crypto")
        for k, v in ctx.items():
            print(f"--- {k} ---")
            print(v)
            print()

        print("\n=== Testing Stock (TSLA) ===\n")
        ctx2 = await get_market_context("TSLA", "stock")
        for k, v in ctx2.items():
            print(f"--- {k} ---")
            print(v)
            print()

    asyncio.run(test())
