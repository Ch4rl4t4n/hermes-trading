"""Request-scoped helpers for multi-tenant dashboard (Alpaca clients, identity)."""

from __future__ import annotations

from typing import Any, Optional

from alpaca.data.historical import CryptoHistoricalDataClient, StockHistoricalDataClient
from alpaca.trading.client import TradingClient

from core.models import Account
from core.saas_helpers import decrypt_account_keys


def build_alpaca_clients(
    key: str | None,
    secret: str | None,
    *,
    paper: bool,
) -> tuple[TradingClient | None, CryptoHistoricalDataClient | None, StockHistoricalDataClient | None]:
    if not key or not secret:
        return None, None, None
    try:
        tc = TradingClient(key, secret, paper=paper)
        cc = CryptoHistoricalDataClient()
        sc = StockHistoricalDataClient(api_key=key, secret_key=secret)
        return tc, cc, sc
    except Exception:
        return None, None, None


def bundle_for_account(
    account: Account | None,
    fallback_key: str,
    fallback_secret: str,
    fallback_paper: bool,
) -> tuple[Any, Any, Any, str, str, bool]:
    """Return (trading, crypto, stock, key, secret, paper)."""
    if account is not None:
        k, s = decrypt_account_keys(account)
        paper = account.account_type == "paper"
        if k and s:
            tc, cc, sc = build_alpaca_clients(k, s, paper=paper)
            return tc, cc, sc, k, s, paper
        return None, None, None, "", "", paper
    tc, cc, sc = build_alpaca_clients(fallback_key, fallback_secret, paper=fallback_paper)
    return tc, cc, sc, fallback_key, fallback_secret, fallback_paper
