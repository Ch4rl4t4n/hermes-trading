"""
Target allocation drift checks and optional rebalance order generation / execution.
Reads `config/portfolio.yaml` (`rebalancing` block).
"""
from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Any, Optional

import yaml
from alpaca.data.historical import CryptoHistoricalDataClient, StockHistoricalDataClient
from alpaca.data.requests import CryptoLatestQuoteRequest, StockLatestQuoteRequest, StockLatestTradeRequest
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, OrderType, TimeInForce
from alpaca.trading.requests import MarketOrderRequest

from core.portfolio_analytics import position_to_agent_symbol

log = logging.getLogger("rebalancer")

_BASE = Path(os.getenv("HERMES_BASE", "/root/hermes"))
_DEFAULT_YAML = _BASE / "config" / "portfolio.yaml"


def load_rebalancing_config(path: Optional[Path] = None) -> dict[str, Any]:
    p = path or _DEFAULT_YAML
    if not p.exists():
        return {}
    try:
        with open(p) as f:
            d = yaml.safe_load(f) or {}
        return d.get("rebalancing") or {}
    except OSError as exc:
        log.warning("portfolio.yaml read failed: %s", exc)
        return {}


class PortfolioRebalancer:
    def __init__(
        self,
        trading_client: Optional[TradingClient],
        target_allocation: dict[str, float],
        *,
        max_drift_pct: float = 5.0,
        portfolio_yaml: Optional[Path] = None,
    ):
        self._trading = trading_client
        self.target_allocation = dict(target_allocation)
        self.max_drift_pct = float(max_drift_pct)
        self._yaml_path = portfolio_yaml or _DEFAULT_YAML
        key = os.getenv("ALPACA_API_KEY", "")
        secret = os.getenv("ALPACA_API_SECRET", "")
        self._crypto = CryptoHistoricalDataClient()
        self._stock = StockHistoricalDataClient(api_key=key, secret_key=secret) if key else None

    @classmethod
    def from_yaml(cls, trading_client: Optional[TradingClient], path: Optional[Path] = None) -> PortfolioRebalancer:
        cfg = load_rebalancing_config(path)
        target = cfg.get("target_allocation") or {}
        # YAML may load ints; normalize to float
        tgt = {str(k): float(v) for k, v in target.items()}
        md = float(cfg.get("max_drift_pct") or 5)
        return cls(trading_client, tgt, max_drift_pct=md, portfolio_yaml=path or _DEFAULT_YAML)

    def _price_for(self, symbol: str) -> float:
        asset = "crypto" if "/" in symbol else "stock"
        try:
            if asset == "crypto":
                q = self._crypto.get_crypto_latest_quote(
                    CryptoLatestQuoteRequest(symbol_or_symbols=symbol)
                )[symbol]
                v = float(q.ask_price)
                return v
            if self._stock:
                q = self._stock.get_stock_latest_quote(StockLatestQuoteRequest(symbol_or_symbols=symbol))[
                    symbol
                ]
                v = float(q.ask_price)
                if v <= 0:
                    t = self._stock.get_stock_latest_trade(StockLatestTradeRequest(symbol_or_symbols=symbol))
                    v = float(t[symbol].price)
                return v
        except Exception as exc:  # noqa: BLE001
            log.debug("price %s: %s", symbol, exc)
        return 0.0

    def _equity(self) -> float:
        if self._trading is None:
            return 0.0
        try:
            return float(self._trading.get_account().equity or 0)
        except Exception:  # noqa: BLE001
            return 0.0

    def check_drift_sync(self) -> dict[str, Any]:
        equity = self._equity()
        current_usd: dict[str, float] = {sym: 0.0 for sym in self.target_allocation}
        positions_summary: list[dict] = []

        if self._trading:
            try:
                for p in self._trading.get_all_positions():
                    canonical = position_to_agent_symbol(p.symbol)
                    if canonical not in current_usd:
                        continue
                    mv = float(p.market_value or 0)
                    current_usd[canonical] = mv
                    positions_summary.append(
                        {
                            "symbol": canonical,
                            "market_value": mv,
                            "qty": float(p.qty or 0),
                        }
                    )
            except Exception as exc:  # noqa: BLE001
                log.warning("positions for drift: %s", exc)

        current_pct: dict[str, float] = {}
        drift: dict[str, float] = {}
        if equity > 0:
            for sym, usd in current_usd.items():
                current_pct[sym] = round(usd / equity * 100.0, 3)
        else:
            current_pct = {sym: 0.0 for sym in current_usd}

        tgt_sum = sum(self.target_allocation.values())
        needs = False
        for sym, tgt in self.target_allocation.items():
            cur = current_pct.get(sym, 0.0)
            d = cur - tgt
            drift[sym] = round(d, 3)
            if abs(d) > self.max_drift_pct:
                needs = True

        return {
            "equity": round(equity, 2),
            "target_allocation": self.target_allocation,
            "target_sum_pct": round(tgt_sum, 3),
            "current_usd": {k: round(v, 2) for k, v in current_usd.items()},
            "current_pct": current_pct,
            "drift_pct": drift,
            "max_drift_pct": self.max_drift_pct,
            "needs_rebalance": needs,
            "positions": positions_summary,
        }

    async def check_drift(self) -> dict[str, Any]:
        return await asyncio.to_thread(self.check_drift_sync)

    def rebalance_sync(self, dry_run: bool = True) -> list[dict[str, Any]]:
        drift_report = self.check_drift_sync()
        equity = drift_report["equity"]
        if equity <= 0:
            return []

        orders: list[dict[str, Any]] = []
        for sym, tgt_pct in self.target_allocation.items():
            cur_pct = drift_report["current_pct"].get(sym, 0.0)
            if abs(cur_pct - tgt_pct) <= self.max_drift_pct:
                continue
            tgt_usd = equity * tgt_pct / 100.0
            cur_usd = drift_report["current_usd"].get(sym, 0.0)
            delta_usd = tgt_usd - cur_usd
            if abs(delta_usd) < 10.0:   # ignore tiny notionals
                continue
            price = self._price_for(sym)
            if price <= 0:
                orders.append(
                    {
                        "symbol": sym,
                        "error": "no_price",
                        "side": "BUY" if delta_usd > 0 else "SELL",
                        "delta_usd": round(delta_usd, 2),
                    }
                )
                continue
            qty = abs(delta_usd) / price
            decimals = 6 if "/" in sym else 4
            qty = round(qty, decimals)
            side = "BUY" if delta_usd > 0 else "SELL"
            if qty <= 0:
                continue
            od = {
                "symbol": sym,
                "alpaca_symbol": sym,
                "side": side,
                "qty": qty,
                "limit_price": None,
                "estimated_usd": round(qty * price, 2),
                "reason": f"target {tgt_pct:.1f}% vs current {cur_pct:.1f}%",
                "dry_run": dry_run,
            }
            orders.append(od)

            if dry_run or self._trading is None:
                continue
            try:
                tif = TimeInForce.GTC if "/" in sym else TimeInForce.DAY
                mo = MarketOrderRequest(
                    symbol=sym,
                    qty=qty,
                    side=OrderSide.BUY if side == "BUY" else OrderSide.SELL,
                    type=OrderType.MARKET,
                    time_in_force=tif,
                )
                resp = self._trading.submit_order(mo)
                od["order_id"] = str(resp.id)
                log.info("Rebalance %s %s qty=%s id=%s dry_run=%s", sym, side, qty, resp.id, dry_run)
            except Exception as exc:  # noqa: BLE001
                od["error"] = str(exc)
                log.warning("Rebalance order failed %s: %s", sym, exc)

        return orders

    async def rebalance(self, dry_run: bool = True) -> list[dict[str, Any]]:
        return await asyncio.to_thread(self.rebalance_sync, dry_run)


def save_target_allocation(
    allocation: dict[str, float],
    *,
    path: Optional[Path] = None,
) -> None:
    """Merge new target_allocation into portfolio.yaml (preserves other keys)."""
    p = path or _DEFAULT_YAML
    p.parent.mkdir(parents=True, exist_ok=True)
    if p.exists():
        with open(p) as f:
            root = yaml.safe_load(f) or {}
    else:
        root = {}
    reb = root.get("rebalancing") or {}
    reb["target_allocation"] = {k: float(v) for k, v in allocation.items()}
    root["rebalancing"] = reb
    tmp = p.with_suffix(".yaml.tmp")
    with open(tmp, "w") as f:
        yaml.safe_dump(root, f, sort_keys=False, default_flow_style=False)
    tmp.replace(p)
