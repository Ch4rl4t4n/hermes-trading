"""Dashboard configuration: Google OAuth (env) and tier feature matrix.

Enforcement lives in ``core.tier_access``; ``TIER_FEATURES`` is the canonical
static description for docs, admin UI, and ``GET /api/platform/tier-features``.
"""

from __future__ import annotations

import os
from typing import Any

_GOOGLE_CID = (os.getenv("GOOGLE_CLIENT_ID") or os.getenv("GOOGLE_OAUTH_CLIENT_ID") or "").strip()
_GOOGLE_CS = (os.getenv("GOOGLE_CLIENT_SECRET") or os.getenv("GOOGLE_OAUTH_CLIENT_SECRET") or "").strip()
# Default public URL when DASHBOARD_PUBLIC_BASE_URL is unset (override in .env for production).
_PUBLIC = (
    os.getenv("DASHBOARD_PUBLIC_BASE_URL") or "https://app.letagentscook.lol"
).strip().rstrip("/")

GOOGLE_CLIENT_ID = _GOOGLE_CID
GOOGLE_CLIENT_SECRET = _GOOGLE_CS
# Must match Authorized redirect URI in Google Cloud Console (Flask-Dance callback).
GOOGLE_REDIRECT_URI = "https://app.letagentscook.lol/oauth/google/authorized"
DASHBOARD_PUBLIC_BASE_URL = _PUBLIC
APP_URL = DASHBOARD_PUBLIC_BASE_URL

TIER_FEATURES: dict[str, dict[str, Any]] = {
    "basic": {
        "display_name": "Basic",
        "agents_limit": 3,
        "ai_insights": False,
        "allowed_agent_symbols": ["BTC/USD", "ETH/USD", "TSLA"],
        "backtest": False,
        "dca": False,
        "grid": False,
        "history_days": 7,
        "onboarding_complete": False,
        "portfolio_advanced": False,
        "portfolio_full": False,
        "real_money": False,
        "price_monthly": 0,
    },
    "medium": {
        "display_name": "Medium",
        "agents_limit": 8,
        "ai_insights": True,
        "allowed_agent_symbols": None,
        "backtest": True,
        "dca": True,
        "grid": False,
        "history_days": 30,
        "onboarding_complete": False,
        "portfolio_advanced": True,
        "portfolio_full": False,
        "real_money": False,
        "price_monthly": 29,
    },
    "pro": {
        "display_name": "Pro",
        "agents_limit": None,
        "ai_insights": True,
        "allowed_agent_symbols": None,
        "backtest": True,
        "dca": True,
        "grid": True,
        "history_days": 365,
        "onboarding_complete": False,
        "portfolio_advanced": True,
        "portfolio_full": True,
        "real_money": True,
        "price_monthly": 99,
    },
    "admin": {
        "display_name": "Admin",
        "agents_limit": None,
        "ai_insights": True,
        "allowed_agent_symbols": None,
        "backtest": True,
        "dca": True,
        "grid": True,
        "history_days": None,
        "onboarding_complete": True,
        "portfolio_advanced": True,
        "portfolio_full": True,
        "real_money": True,
        "price_monthly": 0,
    },
}
