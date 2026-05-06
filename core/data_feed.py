import asyncio
import logging
import os
from collections import deque
from dataclasses import dataclass
from datetime import datetime, time as dtime
from zoneinfo import ZoneInfo

from alpaca.data.historical import StockHistoricalDataClient, CryptoHistoricalDataClient
from alpaca.data.requests import (
    StockBarsRequest, CryptoBarsRequest,
    StockLatestQuoteRequest, CryptoLatestQuoteRequest,
    StockLatestTradeRequest,
)
from alpaca.data.timeframe import TimeFrame

log = logging.getLogger("data_feed")

ROLLING_WINDOW = 200
BOOTSTRAP_BARS = 50


@dataclass
class SymbolMeta:
    symbol: str
    asset_type: str       # "crypto" | "stock" | "commodity_etf"
    timezone: str
    active_hours_start: dtime
    active_hours_end: dtime


class DataFeed:
    def __init__(self, symbols: list[SymbolMeta]):
        self._meta: dict[str, SymbolMeta] = {s.symbol: s for s in symbols}
        self._history: dict[str, deque] = {
            s.symbol: deque(maxlen=ROLLING_WINDOW) for s in symbols
        }
        self._latest: dict[str, float] = {}
        self._running = False

        self._stock = StockHistoricalDataClient(
            api_key=os.getenv("ALPACA_API_KEY"),
            secret_key=os.getenv("ALPACA_API_SECRET"),
        )
        self._crypto = CryptoHistoricalDataClient()

    # ── Public API ─────────────────────────────────────────────────────────────

    def get_price(self, symbol: str) -> float:
        return self._latest.get(symbol, 0.0)

    def get_history(self, symbol: str) -> list[float]:
        return list(self._history[symbol])

    def is_market_open_for(self, symbol: str) -> bool:
        meta = self._meta.get(symbol)
        if not meta:
            return False
        tz = ZoneInfo(meta.timezone)
        now = datetime.now(tz).time()
        return meta.active_hours_start <= now <= meta.active_hours_end

    # ── Bootstrap ──────────────────────────────────────────────────────────────

    def bootstrap(self) -> None:
        """Load historical bars for all symbols at startup so RSI/MACD are warm."""
        log.info("Bootstrapping %d symbols with %d bars each...", len(self._meta), BOOTSTRAP_BARS)

        crypto_syms = self._crypto_symbols()
        stock_syms = self._stock_symbols()

        if crypto_syms:
            self._bootstrap_crypto(crypto_syms)
        if stock_syms:
            self._bootstrap_stocks(stock_syms)

        log.info(
            "Bootstrap complete — %d symbols ready",
            sum(1 for s in self._meta if self._latest.get(s, 0) > 0),
        )

    def _bootstrap_crypto(self, symbols: list[str]) -> None:
        # Alpaca batch bars returns only the first symbol — request individually
        for sym in symbols:
            try:
                req = CryptoBarsRequest(
                    symbol_or_symbols=sym,
                    timeframe=TimeFrame.Minute,
                    limit=BOOTSTRAP_BARS,
                )
                bars = self._crypto.get_crypto_bars(req).data.get(sym, [])
                for bar in bars:
                    self._history[sym].append(float(bar.close))
                if self._history[sym]:
                    self._latest[sym] = self._history[sym][-1]
                    log.info("Bootstrapped %s: %d bars, last=$%.4f", sym, len(self._history[sym]), self._latest[sym])
            except Exception as exc:
                log.warning("Crypto bootstrap failed for %s: %s", sym, exc)

    def _bootstrap_stocks(self, symbols: list[str]) -> None:
        for sym in symbols:
            try:
                req = StockBarsRequest(
                    symbol_or_symbols=sym,
                    timeframe=TimeFrame.Minute,
                    limit=BOOTSTRAP_BARS,
                )
                barset = self._stock.get_stock_bars(req)
                bars_by_sym: dict = barset.data
                bars = bars_by_sym.get(sym) or (
                    list(bars_by_sym.values())[0] if bars_by_sym else []
                )
                for bar in bars:
                    self._history[sym].append(float(bar.close))
                if self._history[sym]:
                    self._latest[sym] = self._history[sym][-1]
                    log.info("Bootstrapped %s: %d bars, last=$%.2f", sym, len(self._history[sym]), self._latest[sym])
            except Exception as exc:
                log.warning("Stock bootstrap failed for %s: %s", sym, exc)

    # ── Refresh loop ───────────────────────────────────────────────────────────

    async def run(self, interval_seconds: int = 60) -> None:
        self._running = True
        log.info("DataFeed live — refresh every %ds", interval_seconds)
        while self._running:
            await self._fetch_all()
            await asyncio.sleep(interval_seconds)

    def stop(self) -> None:
        self._running = False

    async def _fetch_all(self) -> None:
        crypto_syms = self._crypto_symbols()
        open_stocks = [s for s in self._stock_symbols() if self.is_market_open_for(s)]
        closed_stocks = [s for s in self._stock_symbols() if not self.is_market_open_for(s)]

        if closed_stocks:
            log.debug("Market closed, skipping: %s", ", ".join(closed_stocks))

        if crypto_syms:
            await asyncio.get_event_loop().run_in_executor(None, self._fetch_crypto, crypto_syms)
        for sym in open_stocks:
            await asyncio.get_event_loop().run_in_executor(None, self._fetch_stock, sym)

    def _fetch_crypto(self, symbols: list[str]) -> None:
        try:
            req = CryptoLatestQuoteRequest(symbol_or_symbols=symbols)
            quotes = self._crypto.get_crypto_latest_quote(req)
            for sym in symbols:
                if sym not in quotes:
                    continue
                price = float(quotes[sym].ask_price)
                if price > 0:
                    self._record(sym, price)
        except Exception as exc:
            log.warning("Crypto batch fetch failed: %s", exc)

    def _fetch_stock(self, sym: str) -> None:
        try:
            req = StockLatestQuoteRequest(symbol_or_symbols=sym)
            quote = self._stock.get_stock_latest_quote(req)
            price = float(quote[sym].ask_price)
            if price == 0.0:
                trade_req = StockLatestTradeRequest(symbol_or_symbols=sym)
                trade = self._stock.get_stock_latest_trade(trade_req)
                price = float(trade[sym].price)
            if price > 0:
                self._record(sym, price)
        except Exception as exc:
            log.warning("Stock fetch failed for %s: %s", sym, exc)

    def _record(self, symbol: str, price: float) -> None:
        old = self._latest.get(symbol, 0.0)
        self._latest[symbol] = price
        self._history[symbol].append(price)
        if price != old:
            log.debug("%-12s $%.4f  (Δ %+.4f)", symbol, price, price - old)

    # ── Helpers ────────────────────────────────────────────────────────────────

    def _crypto_symbols(self) -> list[str]:
        return [s for s, m in self._meta.items() if m.asset_type == "crypto"]

    def _stock_symbols(self) -> list[str]:
        return [s for s, m in self._meta.items() if m.asset_type != "crypto"]
