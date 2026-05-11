"""
Hermes Dashboard — Flask app serving live trading data.

Pulls live data from:
  - Alpaca Trading API (positions, account, orders) via TradingClient
  - Alpaca Market Data API (latest quotes for crypto + stocks)
  - core.external_data (Crypto/Stocks Fear & Greed, CoinGecko, CMC, Alpaca News, Yahoo)
  - core.performance_tracker (closed-trade ledger + aggregated stats)
  - core.risk_manager (daily P&L cap + total drawdown kill switch)

Reads agent configs from /root/hermes/config/agents/*.yaml. Mode/pause changes
write back to those YAML files (preserving comments via surgical line edits).
"""
import asyncio
import base64
import concurrent.futures
import csv
import hashlib
import io
import json
import logging
import os
import re
import secrets
import shutil
import subprocess
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from functools import wraps
from pathlib import Path
from typing import Any, Optional

import pyotp
import qrcode
import yaml
from dotenv import load_dotenv
from flask import (  # noqa: E402
    Flask,
    Response,
    g,
    has_request_context,
    jsonify,
    make_response,
    redirect,
    render_template,
    render_template_string,
    request,
    send_file,
    send_from_directory,
    session,
)
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.middleware.proxy_fix import ProxyFix

# Make project root importable BEFORE we touch any project module.
_BASE = Path(__file__).resolve().parent.parent
if str(_BASE) not in sys.path:
    sys.path.insert(0, str(_BASE))
load_dotenv(_BASE / ".env")

from dashboard import config as dash_config  # noqa: E402

# Project imports (after .env so the modules see the keys).
from agents.base_agent import AgentConfig  # noqa: E402
from core.config_loader import load_all_agents  # noqa: E402
from core.external_data import (  # noqa: E402
    get_cmc_altcoin_season_latest,
    get_crypto_fear_greed,
    get_market_context,
    get_stocks_fear_greed,
)
from core.performance_tracker import get_performance_tracker  # noqa: E402
from core.portfolio_analytics import PortfolioAnalytics  # noqa: E402
from core.regime_detector import detect_regime  # noqa: E402
from core.risk_manager import get_risk_manager  # noqa: E402
from dashboard import auth  # noqa: E402
from dashboard import mailer  # noqa: E402
from dashboard import utils as dash_utils  # noqa: E402
import core.database as db
from core import saas_helpers
from core import stripe_billing  # noqa: E402
from core.leaderboard import compute_leaderboard_cache
from core.agent_builder import (
    ALLOWED_STRATEGIES,
    ALLOWED_SYMBOLS,
    STRATEGY_LABELS,
    generate_ai_summary_sync,
    symbol_to_pair,
    user_agent_cap_for_user,
)
from core.backtester import (
    BinanceFetchError,
    agent_config_from_row_system,
    agent_config_from_row_user,
    backtest_allowed_timeframes,
    backtest_limits_payload,
    backtest_max_days_for_tier,
    fetch_candles,
    run_backtest,
)
from core.api_auth import (
    API_RATE_LIMIT_PER_MIN,
    generate_api_key,
    hash_api_key,
    log_api_request,
    require_api_key,
)
from core.exporter import (
    export_agent_performance_csv,
    export_agent_trades_csv,
    export_portfolio_csv,
    generate_agent_pdf_report,
    generate_portfolio_pdf_report,
)
from core.agent_marketplace import (
    PNL_BASELINE_USD,
    assign_demo_agents,
    get_all_agents,
    get_live_pnl_payload,
    get_marketplace_slots,
    get_user_pnl,
    get_user_subscriptions,
    subscribe_agent,
    unsubscribe_agent,
)
from core.community_marketplace import (
    can_publish_tier,
    compute_top_gainer_user_agent_ids,
    enrich_listing_for_api,
    fetch_approved_agent_by_public_id,
    fetch_approved_listing_candidates,
    recent_trades_for_listing,
    sort_listing_rows,
    validate_publish_requirements,
)
from core.queue_manager import queue_manager, r as queue_redis
from core.task_router import task_router
from core.orchestra_agent import orchestra
from core.intelligence_stalker import stalker
from core.swarm_definitions import DEFAULT_SWARMS, seed_default_swarms
from core.referral_helpers import (
    apply_referral_tracking,
    referral_info_for_user,
    try_grant_referral_first_login,
)
from core.badges import (
    BADGE_DEFINITIONS,
    compute_badges_for_agent,
    compute_top_gainers_24h,
    compute_user_badges_map,
    grouped_performance_from_table,
    merge_badge_ids,
)
from core.owner_access import user_is_owner
from core.tier_access import (
    TIER_ADMIN,
    TIER_BASIC,
    TIER_ELITE,
    TIER_MEDIUM,
    TIER_PRO,
    TIER_RANK,
    agent_symbol_allowed,
    clamp_trade_history_rows,
    effective_tier,
    features_payload,
    get_tier_limits,
    normalize_tier,
    tier_at_least,
    tier_caps,
    unrestricted_features_payload,
    user_real_account_forbidden,
)
from hermes_api_v2.core.config import settings as fastapi_v2_settings
from hermes_api_v2.core.security import create_fastapi_token
from core.models import (
    Account,
    Announcement,
    AnnouncementDismissal,
    AuditLog,
    PlatformSetting,
    Trade,
    TradingConfiguration,
    User,
)

try:
    import psutil
except ImportError:  # pragma: no cover - optional dependency in some environments
    psutil = None

try:
    import anthropic

    ANTHROPIC_AVAILABLE = True
except ImportError:  # pragma: no cover - optional dependency in some environments
    anthropic = None
    ANTHROPIC_AVAILABLE = False
from dashboard.multitenant import bundle_for_account
from sqlalchemy import asc, desc, func, or_, select, text
from sqlalchemy.exc import IntegrityError

# Alpaca SDK clients.
from alpaca.data.historical import (  # noqa: E402
    CryptoHistoricalDataClient,
    StockHistoricalDataClient,
)
from alpaca.data.requests import (  # noqa: E402
    CryptoBarsRequest,
    CryptoLatestQuoteRequest,
    StockBarsRequest,
    StockLatestQuoteRequest,
    StockLatestTradeRequest,
)
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit  # noqa: E402
from alpaca.trading.client import TradingClient  # noqa: E402
from alpaca.trading.enums import QueryOrderStatus  # noqa: E402
from alpaca.trading.requests import GetOrdersRequest  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)-18s | %(levelname)-7s | %(message)s",
)
log = logging.getLogger("dashboard")

# ── Config ───────────────────────────────────────────────────────────────────
CONFIG_DIR = _BASE / "config" / "agents"
PORTFOLIO_YAML = _BASE / "config" / "portfolio.yaml"
ALPACA_PAPER = os.getenv("ALPACA_PAPER", "true").lower() == "true"
DRY_RUN = os.getenv("HERMES_DRY_RUN", "true").lower() == "true"
# Legacy env vars are still consulted by dashboard/auth.py to seed the bootstrap
# admin user — see auth.ensure_default_admin().  Once users.json exists they
# stop having any effect, so password rotation must happen via the API.
# Use a dashboard-specific port var so we don't collide with the Hermes
# orchestrator's internal dashboard (which reads DASHBOARD_PORT). Default
# matches the nginx proxy_pass target.
PORT = int(os.getenv("HERMES_FLASK_PORT", "5000"))
# Bind localhost when behind nginx; set HERMES_FLASK_HOST=0.0.0.0 for direct LAN access.
_FLASK_BIND_HOST = os.getenv("HERMES_FLASK_HOST", "127.0.0.1")
INTERNAL_API_TOKEN = (os.getenv("INTERNAL_API_TOKEN") or "").strip()
_INTERNAL_API_TOKEN_WEAK_VALUES = frozenset({"", "hermes-internal-2026", "changeme", "placeholder"})
_INTERNAL_API_ALLOWED_PATHS = frozenset(
    {
        "/api/agents/pnl",
        "/api/marketplace/agents",
        "/api/marketplace/slots",
        "/api/marketplace/subscribe",
        "/api/marketplace/unsubscribe",
        "/api/marketplace/my-agents",
        "/api/leaderboard",
        "/api/backtest/run",
        "/api/agent-builder/my-agents",
        "/api/agent-builder/create",
        "/api/agent-builder/ai-summary",
        "/api/ai/builder",
        "/api/system-events",
        "/api/trades/history",
        "/api/auth/status",
        "/api/v1/auth/fastapi-token",
        "/api/settings/weekly-report",
        "/api/telegram/connect-token",
        "/api/telegram/disconnect",
        "/api/stripe/create-checkout-session",
        "/api/stripe/create-portal-session",
        "/api/notifications",
        "/api/notifications/read",
        "/api/alerts/rules",
        "/api/agents/badges",
        "/api/support/ticket",
        "/api/community/posts",
        "/api/community/sentiment",
        "/api/heatmap",
        "/api/news/intelligence",
    }
)

_INTERNAL_API_PARAMETERIZED_PATTERNS = (
    re.compile(r"^/api/alerts/rules/\d+$"),
    re.compile(r"^/api/alerts/rules/\d+/toggle$"),
    re.compile(r"^/api/community/posts/\d+/like$"),
    re.compile(r"^/api/community/posts/\d+$"),
    re.compile(r"^/api/news/intelligence/\d+$"),
)


def _internal_api_path_allowed(path: str) -> bool:
    if path in _INTERNAL_API_ALLOWED_PATHS:
        return True
    return any(p.match(path) for p in _INTERNAL_API_PARAMETERIZED_PATTERNS)


# ── Flask app ────────────────────────────────────────────────────────────────
# Pin template/static roots to this package directory so `python dashboard/app.py`
# (import name __main__) always resolves `dashboard/templates`, not the repo cwd.
_DASHBOARD_PKG_DIR = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__, root_path=_DASHBOARD_PKG_DIR, template_folder="templates")
app.secret_key = os.getenv("DASHBOARD_SECRET_KEY", secrets.token_hex(32))
# Stricter cookies in production: HttpOnly is on by default, set Secure when
# served behind HTTPS, and SameSite=Lax keeps the dashboard usable from
# bookmarks while blocking CSRF from third-party origins.
_SESSION_TTL = int(os.getenv("HERMES_SESSION_TTL_SECONDS", str(24 * 3600)))
# TLS defaults: production is HTTPS behind nginx. For plain http:// local dev set
# HERMES_USE_HTTPS=false or DASHBOARD_COOKIE_SECURE=false (explicit cookie flag
# still wins when set).
_cookie_explicit = os.getenv("DASHBOARD_COOKIE_SECURE")
if _cookie_explicit is not None and str(_cookie_explicit).strip() != "":
    _COOKIE_SECURE = str(_cookie_explicit).lower() == "true"
else:
    _COOKIE_SECURE = os.getenv("HERMES_USE_HTTPS", "true").lower() == "true"
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SECURE=_COOKIE_SECURE,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_NAME=os.getenv("DASHBOARD_SESSION_COOKIE", "hermes_session"),
    PERMANENT_SESSION_LIFETIME=_SESSION_TTL,
    # So url_for(..., _external=True) and OAuth redirects use https when cookies are Secure.
    PREFERRED_URL_SCHEME="https" if _COOKIE_SECURE else "http",
)
# Trust X-Forwarded-* from nginx (app.letagentscook.lol terminates TLS) so OAuth
# builds the correct external redirect URI (must match dash_config.GOOGLE_REDIRECT_URI).
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
CORS(
    app,
    supports_credentials=True,
    origins=["http://localhost:3000", "https://trading.letagentscook.lol"],
    allow_headers=["Content-Type", "X-CSRFToken"],
    methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
)
db.init_engine()


def _ensure_support_tables() -> None:
    """Best-effort fallback for support tables when migration is unavailable."""
    eng = db.get_engine()
    if eng is None:
        return
    with eng.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS support_tickets (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                    email VARCHAR(255) NOT NULL,
                    subject VARCHAR(255) NOT NULL,
                    message TEXT NOT NULL,
                    status VARCHAR(20) DEFAULT 'open',
                    priority VARCHAR(20) DEFAULT 'normal',
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW()
                );
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS support_replies (
                    id SERIAL PRIMARY KEY,
                    ticket_id INTEGER NOT NULL REFERENCES support_tickets(id) ON DELETE CASCADE,
                    author_email VARCHAR(255) NOT NULL,
                    author_type VARCHAR(20) DEFAULT 'user',
                    message TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT NOW()
                );
                """
            )
        )


try:
    _ensure_support_tables()
except Exception:
    log.exception("support tables ensure failed")

try:
    with app.app_context():
        seed_default_swarms(queue_manager)
        orchestra.start()
        stalker.start()
except Exception:
    log.warning("default swarm seeding skipped", exc_info=True)

_GOOGLE_CID = dash_config.GOOGLE_CLIENT_ID
_GOOGLE_CS = dash_config.GOOGLE_CLIENT_SECRET
_GOOGLE_PLACEHOLDER = (
    not _GOOGLE_CID
    or not _GOOGLE_CS
    or _GOOGLE_CID.lower() in ("placeholder", "changeme", "your-client-id")
    or _GOOGLE_CS.lower() in ("placeholder", "changeme", "your-client-secret")
)
# Absolute URL after Google redirects back (avoids broken url_for behind some proxies).
_DASHBOARD_PUBLIC = dash_config.DASHBOARD_PUBLIC_BASE_URL
_GOOGLE_OAUTH_DONE_URL = (
    f"{_DASHBOARD_PUBLIC}/oauth/google/done" if _DASHBOARD_PUBLIC else None
)


def _public_app_base_url() -> str:
    u = (os.getenv("HERMES_APP_URL") or os.getenv("DASHBOARD_PUBLIC_BASE_URL") or "").strip().rstrip("/")
    if u:
        return u
    if has_request_context():
        return (request.url_root or "").rstrip("/")
    return "https://app.letagentscook.lol"


def _api_rate_limit_key() -> str:
    uid = session.get("user_id")
    if uid is not None and session.get("auth_kind") == "db":
        try:
            return f"uid:{int(uid)}"
        except (TypeError, ValueError):
            pass
    return f"ip:{get_remote_address()}"


limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    storage_uri=os.getenv("HERMES_RATELIMIT_STORAGE_URI", "memory://"),
    default_limits=(
        [
            x.strip()
            for x in os.getenv(
                "HERMES_DEFAULT_RATELIMITS",
                "200 per day,50 per hour",
            ).split(",")
            if x.strip()
        ]
        or None
    ),
)


def _user_summary_for_api(user: User) -> dict[str, Any]:
    return {
        "id": user.id,
        "email": user.email,
        "username": user.username,
        "tier": user.tier,
        "email_verified": bool(getattr(user, "email_verified", True)),
    }


def _auth_fail(message: str, status: int = 401, **extra: Any):
    payload: dict[str, Any] = {"success": False, "message": message, "error": message, **extra}
    return jsonify(payload), status


def _sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _try_assign_demo_agents(user_id: int) -> None:
    """Best-effort preset marketplace subscriptions; never raises."""
    try:
        eng = db.get_engine()
        if eng is None:
            return
        with eng.begin() as conn:
            assigned = assign_demo_agents(user_id, conn)
        if assigned:
            log.info("demo_agents: assigned %s to user %s", assigned, user_id)
    except Exception as exc:  # noqa: BLE001
        log.warning("demo agent assignment failed for user %s: %s", user_id, exc)


@app.errorhandler(429)
def _ratelimit_exceeded(_e):
    return jsonify({"error": "Too many attempts. Please try again in a few minutes."}), 429


if not _GOOGLE_PLACEHOLDER:
    try:
        # Google Sign-In via Flask-Dance. Authlib is installed for optional future OAuth use.
        from flask_dance.contrib.google import make_google_blueprint

        google_bp = make_google_blueprint(
            client_id=_GOOGLE_CID,
            client_secret=_GOOGLE_CS,
            scope=[
                "openid",
                "https://www.googleapis.com/auth/userinfo.email",
                "https://www.googleapis.com/auth/userinfo.profile",
            ],
            redirect_url=_GOOGLE_OAUTH_DONE_URL,
            redirect_to=None if _GOOGLE_OAUTH_DONE_URL else "google_auth_finish",
        )
        app.register_blueprint(google_bp, url_prefix="/oauth")
        log.info(
            "Google OAuth blueprint registered (post-login redirect: %s)",
            _GOOGLE_OAUTH_DONE_URL or "url_for(google_auth_finish)",
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("Google OAuth blueprint not registered: %s", exc)

_CSP = os.getenv(
    "DASHBOARD_CSP",
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline' 'unsafe-eval' blob: "
    "https://cdn.jsdelivr.net https://cdn.tailwindcss.com https://unpkg.com "
    "https://cdnjs.cloudflare.com https://s3.tradingview.com https://*.tradingview.com; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
    "img-src 'self' data: blob: https:; "
    "font-src 'self' data: blob: https://fonts.gstatic.com https://fonts.googleapis.com; "
    "connect-src 'self' blob: https://cdn.jsdelivr.net https://unpkg.com "
    "https://s3.tradingview.com https://*.tradingview.com https://data.tradingview.com "
    "wss://*.tradingview.com; "
    "frame-src https://s3.tradingview.com https://*.tradingview.com "
    "https://www.tradingview.com https://widget.tradingview.com; "
    "child-src https://s3.tradingview.com https://*.tradingview.com "
    "https://www.tradingview.com https://widget.tradingview.com; "
    "worker-src 'self' blob:; "
    "base-uri 'self'; "
    "form-action 'self'",
)
if "script-src" in _CSP and "'unsafe-eval'" not in _CSP:
    _CSP = _CSP.replace("script-src", "script-src 'unsafe-eval'", 1)


def _issue_csrf_token() -> str:
    tok = secrets.token_hex(32)
    session.permanent = True
    session["csrf_token"] = tok
    session.modified = True
    return tok


@app.teardown_appcontext
def _teardown_db_session(_exc):
    db.remove_scoped_session()


@app.before_request
def _force_https_redirect():
    """Optional strict http→https when not terminating TLS in the proxy layer."""
    if os.getenv("HERMES_FORCE_HTTPS_REDIRECT", "false").lower() != "true":
        return None
    if request.is_secure:
        return None
    host = (request.host or "").split(":")[0].lower()
    if host in ("127.0.0.1", "localhost", "::1"):
        return None
    path = request.path or ""
    if path.startswith("/.well-known/acme-challenge"):
        return None
    url = request.url.replace("http://", "https://", 1)
    return redirect(url, code=301)


@app.after_request
def _security_headers(resp: Response):
    resp.headers["X-Frame-Options"] = "SAMEORIGIN"
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-XSS-Protection"] = "1; mode=block"
    resp.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    resp.headers["Content-Security-Policy"] = _CSP
    if getattr(request, "is_secure", False):
        resp.headers.setdefault(
            "Strict-Transport-Security",
            (os.getenv("HERMES_HSTS") or "max-age=31536000; includeSubDomains").strip(),
        )
    path = request.path or ""
    if path.startswith("/v1/") or path.startswith("/api/v1/"):
        resp.headers["Access-Control-Allow-Origin"] = "*"
        resp.headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type, X-API-Key"
        lim = int(getattr(g, "api_rate_limit", API_RATE_LIMIT_PER_MIN))
        rem = int(getattr(g, "api_rate_remaining", lim))
        rst = int(getattr(g, "api_rate_reset", int(time.time()) + 60))
        resp.headers["X-RateLimit-Limit"] = str(lim)
        resp.headers["X-RateLimit-Remaining"] = str(max(0, rem))
        resp.headers["X-RateLimit-Reset"] = str(rst)
        try:
            started = float(getattr(g, "_v1_started_at", 0.0))
            elapsed = int(max(0.0, (time.time() - started) * 1000.0)) if started > 0 else 0
            log_api_request(
                endpoint=path,
                method=request.method,
                status_code=getattr(resp, "status_code", 0),
                response_time_ms=elapsed,
                ip_address=(request.headers.get("X-Forwarded-For") or request.remote_addr or "").split(",")[0].strip(),
                api_key_id=getattr(g, "api_key_id", None),
                user_id=getattr(g, "api_user_id", None),
            )
        except Exception:  # noqa: BLE001
            pass
    return resp


@app.before_request
def _v1_request_start():
    if (request.path or "").startswith("/v1/") or (request.path or "").startswith("/api/v1/"):
        g._v1_started_at = time.time()
    return None


@app.before_request
def _csrf_protect():
    """Double-submit CSRF for cookie-based POSTs.  Exempt when a valid bearer
    token is present (automation / scripts).  Flask-CORS preflight is OPTIONS."""
    if request.method == "OPTIONS":
        return None
    if request.method != "POST":
        return None
    path = request.path or ""
    if not path.startswith("/api/"):
        return None
    # Unauthenticated auth endpoints: no session/CSRF yet (or cookie rejected e.g.
    # Secure flag on HTTP). Exempt to avoid login/register deadlock; automation
    # can POST without a prior GET /api/auth/csrf.
    if path in (
        "/api/auth/login",
        "/api/auth/register",
        "/api/auth/resend-verification",
        "/api/v1/auth/fastapi-token",
        "/api/telegram/webhook",
        "/api/stripe/webhook",
    ):
        return None
    bt = _bearer_token()
    if bt and auth.validate_token(bt):
        return None
    expected = session.get("csrf_token")
    if not expected:
        return jsonify({
            "error": "Missing valid CSRF token. Reload the page and try again.",
            "csrf_required": True,
        }), 403
    body = request.get_json(silent=True) or {}
    got = (
        request.headers.get("X-CSRF-Token")
        or request.headers.get("X-Csrf-Token")
        or body.get("csrf_token")
    )
    if not got or not secrets.compare_digest(str(expected), str(got)):
        return jsonify({"error": "Invalid CSRF token.", "csrf_required": True}), 403
    return None

# ── Alpaca clients (constructed once at startup) ─────────────────────────────
_ALPACA_KEY = os.getenv("ALPACA_API_KEY", "")
_ALPACA_SECRET = os.getenv("ALPACA_API_SECRET", "")
_trading_client: Optional[TradingClient] = None
_crypto_client: Optional[CryptoHistoricalDataClient] = None
_stock_client: Optional[StockHistoricalDataClient] = None
try:
    _trading_client = TradingClient(_ALPACA_KEY, _ALPACA_SECRET, paper=ALPACA_PAPER)
    _crypto_client = CryptoHistoricalDataClient()
    _stock_client = StockHistoricalDataClient(api_key=_ALPACA_KEY, secret_key=_ALPACA_SECRET)
    log.info("Alpaca clients initialised (paper=%s)", ALPACA_PAPER)
except Exception as exc:  # noqa: BLE001
    log.error("Alpaca client init failed: %s", exc)


def _portfolio_analytics() -> PortfolioAnalytics:
    """Shared analytics helper using request-scoped Alpaca clients."""
    tc, cc, sc, key, secret, paper = _alpaca_clients()
    return PortfolioAnalytics(
        tc or _trading_client,
        stock_client=sc or _stock_client,
        crypto_client=cc or _crypto_client,
        api_key=key or _ALPACA_KEY,
        api_secret=secret or _ALPACA_SECRET,
        paper=paper,
    )

# ── Runtime state (process-local) ────────────────────────────────────────────
_state: dict[str, Any] = {
    "kill_switch": False,
    "started_at": time.time(),
    "paused_symbols": set(),   # symbols paused via dashboard
}

# ── Caches ───────────────────────────────────────────────────────────────────
_PRICE_TTL = 30
_ACCOUNT_TTL = 60
_ORDERS_TTL = 60
_AGENT_CFG_TTL = 30
_BARS_TTL = 300
_REGIME_TTL = 300
_price_cache: dict[str, tuple[float, float]] = {}
_account_cache: dict[str, dict[str, Any]] = {}
_orders_cache: dict[str, tuple[list[dict], float]] = {}
_cfg_cache_store: dict[str, dict[str, Any]] = {}
_bars_cache: dict[str, tuple[list[float], float]] = {}
_regime_cache: dict[str, tuple[dict, float]] = {}

# Where the trading-engine writes its tracker state.  Defined lazily so we
# can read it even if the engine isn't running yet.
_LOG_DIR = _BASE / "logs"
_PERF_PATH = _LOG_DIR / "performance.json"
_RISK_EVENTS_PATH = _LOG_DIR / "risk_events.log"
_LLM_AUDIT_PATH = _LOG_DIR / "llm_audit.log"
_DS_OVERRIDE_PATH = _LOG_DIR / "datasource_overrides.json"

# Sources users can toggle.  `alpaca` is intentionally absent — broker access
# is non-negotiable.  `anthropic_llm` is special-cased to write llm.enabled
# in YAML so the engine respects it on next reload.
DATASOURCES = ("coingecko", "cmc", "crypto_fg", "yahoo", "news", "anthropic_llm")


def _now() -> float:
    return time.time()


def _tenant_tag() -> str:
    if not has_request_context():
        return "legacy"
    _resolve_identity()
    try:
        acc = getattr(g, "db_account", None)
        if acc is not None:
            return f"a{acc.id}"
    except RuntimeError:
        pass
    return "legacy"


def _resolve_identity() -> None:
    if not has_request_context():
        return
    if getattr(g, "_identity_done", False):
        return
    g._identity_done = True
    g.auth_kind = None
    g.db_user = None
    g.db_account = None
    g.legacy_username = None
    g._alpaca_cached = None
    if db.SessionLocal is None:
        if session.get("logged_in") and session.get("username") and session.get("auth_kind") != "db":
            g.auth_kind = "legacy"
            g.legacy_username = session.get("username")
        return

    sess = db.db_session()
    tok = _bearer_token()

    # Allow server-to-server calls from Next.js proxy for selected API routes.
    # This keeps browser CORS/cookie concerns out of the client.
    if _internal_api_path_allowed(request.path):
        itok = (request.headers.get("X-Internal-Token") or "").strip()
        iemail = (request.headers.get("X-User-Email") or "").strip().lower()
        if (
            itok
            and iemail
            and INTERNAL_API_TOKEN not in _INTERNAL_API_TOKEN_WEAK_VALUES
            and secrets.compare_digest(itok, INTERNAL_API_TOKEN)
        ):
            iuser = sess.execute(select(User).where(func.lower(User.email) == iemail)).scalar_one_or_none()
            if iuser and iuser.is_active:
                g.db_user = iuser
                g.auth_kind = "db"
                iacc = saas_helpers.default_paper_account_for_user(sess, iuser.id)
                if iacc and iacc.account_status == "active":
                    g.db_account = iacc
                return
        elif itok and INTERNAL_API_TOKEN in _INTERNAL_API_TOKEN_WEAK_VALUES:
            log.warning("Rejected internal API auth on %s due to weak INTERNAL_API_TOKEN", request.path)

    if session.get("logged_in") and session.get("auth_kind") == "db":
        uid = session.get("user_id")
        aid = session.get("account_id")
        u: User | None = sess.get(User, int(uid)) if uid is not None else None
        a: Account | None = sess.get(Account, int(aid)) if aid is not None else None
        if u and u.is_active and a and a.account_status == "active":
            if user_real_account_forbidden(u, a.account_type):
                paper = saas_helpers.default_paper_account_for_user(sess, u.id)
                if paper and paper.account_status == "active":
                    g.db_user = u
                    g.db_account = paper
                    g.auth_kind = "db"
                    try:
                        session["account_id"] = paper.id
                        session.modified = True
                    except RuntimeError:
                        pass
                return
            g.db_user = u
            g.db_account = a
            g.auth_kind = "db"
        return

    if session.get("logged_in") and session.get("username"):
        g.auth_kind = "legacy"
        g.legacy_username = session.get("username")
        return

    if tok:
        token_name: str | None = auth.validate_token(tok)
    else:
        token_name = None
    if token_name:
        u2 = sess.execute(select(User).where(User.username == token_name)).scalar_one_or_none()
        if u2 and u2.is_active:
            g.db_user = u2
            a2 = saas_helpers.default_paper_account_for_user(sess, u2.id)
            if a2 and a2.account_status == "active":
                g.db_account = a2
                g.auth_kind = "db"
            return
        g.auth_kind = "legacy"
        g.legacy_username = token_name


def _alpaca_clients() -> tuple[Any, Any, Any, str, str, bool]:
    if not has_request_context():
        return bundle_for_account(None, _ALPACA_KEY, _ALPACA_SECRET, ALPACA_PAPER)
    _resolve_identity()
    if getattr(g, "_alpaca_cached", None) is not None:
        return g._alpaca_cached
    acc = getattr(g, "db_account", None)
    bundle = bundle_for_account(acc, _ALPACA_KEY, _ALPACA_SECRET, ALPACA_PAPER)
    g._alpaca_cached = bundle
    return bundle


# ── Config loading + URL→symbol decoding ─────────────────────────────────────

def _load_configs(force: bool = False) -> list[AgentConfig]:
    if has_request_context():
        _resolve_identity()
        key = _tenant_tag()
    else:
        key = "legacy"
    bucket = _cfg_cache_store.setdefault(key, {"cfgs": [], "ts": 0.0})
    if not force and bucket["cfgs"] and (_now() - bucket["ts"]) < _AGENT_CFG_TTL:
        return bucket["cfgs"]
    cfgs: list[AgentConfig] = []
    acc = getattr(g, "db_account", None) if has_request_context() else None
    if acc is not None and db.SessionLocal is not None:
        sess = db.db_session()
        tconf = sess.execute(
            select(TradingConfiguration).where(TradingConfiguration.account_id == acc.id)
        ).scalar_one_or_none()
        if tconf and isinstance(tconf.agents, dict):
            for doc in saas_helpers.agents_list_from_blob(tconf.agents):
                try:
                    cfg = agent_config_from_dict(doc)
                    if cfg.enabled:
                        cfgs.append(cfg)
                except Exception as exc:  # noqa: BLE001
                    log.debug("agent from db failed: %s", exc)
    if not cfgs:
        try:
            cfgs = load_all_agents(CONFIG_DIR)
        except Exception as exc:  # noqa: BLE001
            log.error("load_all_agents failed: %s", exc)
            cfgs = bucket["cfgs"] or []
    bucket["cfgs"] = cfgs
    bucket["ts"] = _now()
    return cfgs


def _bump_cfg_cache() -> None:
    _resolve_identity()
    key = _tenant_tag()
    if key in _cfg_cache_store:
        _cfg_cache_store[key]["ts"] = 0.0


def _db_update_agent_root_fields(canonical: str, updates: dict[str, Any]) -> bool:
    if getattr(g, "db_account", None) is None:
        return False
    blob = _trading_blob_for_account()
    if not blob:
        return False
    docs = saas_helpers.agents_list_from_blob(blob)
    found = False
    for i, doc in enumerate(docs):
        if doc.get("symbol") == canonical:
            d2 = dict(doc)
            for k, v in updates.items():
                d2[k] = v
            docs[i] = d2
            found = True
            break
    if not found:
        return False
    nb = saas_helpers.merge_paused_into_blob({**blob, "agents": docs}, saas_helpers.paused_from_blob(blob))
    _save_trading_blob(nb)
    _bump_cfg_cache()
    return True


def _db_merge_agent_yaml_fields(canonical: str, updates: dict[str, Any]) -> bool:
    if getattr(g, "db_account", None) is None:
        return False
    blob = _trading_blob_for_account()
    if not blob:
        blob = saas_helpers.build_default_agents_blob(CONFIG_DIR)
    docs = list(saas_helpers.agents_list_from_blob(blob))
    ok = False
    for i, doc in enumerate(docs):
        if doc.get("symbol") != canonical:
            continue
        d2 = dict(doc)
        for k, v in updates.items():
            if isinstance(v, dict) and isinstance(d2.get(k), dict):
                inner = dict(d2[k])
                inner.update(v)
                d2[k] = inner
            else:
                d2[k] = v
        docs[i] = d2
        ok = True
        break
    if not ok:
        return False
    nb = saas_helpers.merge_paused_into_blob({**blob, "agents": docs}, saas_helpers.paused_from_blob(blob))
    _save_trading_blob(nb)
    _bump_cfg_cache()
    return True


def _trading_blob_for_account() -> dict[str, Any] | None:
    acc = getattr(g, "db_account", None)
    if acc is None or db.SessionLocal is None:
        return None
    sess = db.db_session()
    row = sess.execute(
        select(TradingConfiguration).where(TradingConfiguration.account_id == acc.id)
    ).scalar_one_or_none()
    if row and isinstance(row.agents, dict):
        return dict(row.agents)
    return None


def _save_trading_blob(blob: dict[str, Any]) -> None:
    acc = getattr(g, "db_account", None)
    if acc is None or db.SessionLocal is None:
        return
    sess = db.db_session()
    row = sess.execute(
        select(TradingConfiguration).where(TradingConfiguration.account_id == acc.id)
    ).scalar_one_or_none()
    if row:
        row.agents = blob
        sess.commit()
    tkey = _tenant_tag()
    if tkey in _cfg_cache_store:
        _cfg_cache_store[tkey]["ts"] = 0.0


def _paused_symbols() -> set[str]:
    if getattr(g, "db_account", None) is not None:
        blob = _trading_blob_for_account() or {}
        return saas_helpers.paused_from_blob(blob)
    return _state["paused_symbols"]


def _set_paused(canonical: str, paused: bool) -> None:
    if getattr(g, "db_account", None) is not None:
        blob = _trading_blob_for_account()
        if not blob:
            blob = saas_helpers.build_default_agents_blob(CONFIG_DIR)
        paused_set = saas_helpers.paused_from_blob(blob)
        if paused:
            paused_set.add(canonical)
        else:
            paused_set.discard(canonical)
        _save_trading_blob(saas_helpers.merge_paused_into_blob(blob, paused_set))
        return
    if paused:
        _state["paused_symbols"].add(canonical)
    else:
        _state["paused_symbols"].discard(canonical)


def _config_path_for_symbol(symbol: str) -> Optional[Path]:
    """Return the YAML file whose `symbol:` key matches the agent's symbol."""
    _resolve_identity()
    if getattr(g, "db_account", None) is not None:
        return None
    for path in CONFIG_DIR.glob("*.yaml"):
        try:
            with open(path) as f:
                d = yaml.safe_load(f) or {}
            if d.get("symbol") == symbol:
                return path
        except Exception:  # noqa: BLE001
            continue
    return None


def _url_to_symbol(url_sym: str) -> Optional[str]:
    """Map the URL form back to the canonical agent symbol.

    `BTC-USD`  → `BTC/USD`
    `BTC%2FUSD`→ `BTC/USD`  (Flask already URL-decodes `%2F`, so we just match)
    `TSLA`     → `TSLA`
    Returns None if no agent matches.
    """
    cfgs = _load_configs()
    candidates = {
        url_sym,
        url_sym.replace("-", "/"),
        url_sym.replace("/", "-"),
    }
    for c in cfgs:
        if c.symbol in candidates or c.symbol.replace("/", "-") in candidates:
            return c.symbol
    return None


def _alpaca_clean(symbol: str) -> str:
    """Alpaca uses dashless symbols for orders/positions: BTC/USD → BTCUSD."""
    return symbol.replace("/", "")


# ── Auth ─────────────────────────────────────────────────────────────────────

def _bearer_token() -> Optional[str]:
    """Pull a bearer token from the Authorization header (or X-API-Key for
    legacy scripts)."""
    h = request.headers.get("Authorization", "")
    if h.lower().startswith("bearer "):
        return h.split(" ", 1)[1].strip() or None
    return request.headers.get("X-API-Key") or None


def _current_username() -> Optional[str]:
    """Primary username for logging and legacy auth helpers (file-based TOTP)."""
    _resolve_identity()
    if getattr(g, "db_user", None):
        return g.db_user.username
    if getattr(g, "legacy_username", None):
        return g.legacy_username
    return None


def _is_authenticated() -> bool:
    _resolve_identity()
    return bool(getattr(g, "db_user", None) or getattr(g, "legacy_username", None))


def _admin_ok() -> bool:
    _resolve_identity()
    if getattr(g, "db_user", None) and g.db_user.is_admin:
        return True
    u = _current_username()
    if u:
        info = auth.get_user_public(u) or {}
        if info.get("role") == "admin":
            return True
    return False


def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not _is_authenticated():
            return jsonify({"error": "unauthorized"}), 401
        return f(*args, **kwargs)

    return limiter.limit("60 per minute", key_func=_api_rate_limit_key)(wrapper)


def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not _is_authenticated() or not _admin_ok():
            return jsonify({"error": "forbidden"}), 403
        return f(*args, **kwargs)

    return limiter.limit("60 per minute", key_func=_api_rate_limit_key)(wrapper)


def require_tier(minimum: str):
    def deco(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            _resolve_identity()
            if getattr(g, "auth_kind", None) == "legacy":
                return f(*args, **kwargs)
            u = getattr(g, "db_user", None)
            if u is None:
                return jsonify({"error": "Upgrade required.", "upgrade_required": True, "min_tier": minimum}), 403
            if not tier_at_least(u, minimum):
                return jsonify(
                    {
                        "error": "Upgrade required.",
                        "upgrade_required": True,
                        "min_tier": minimum,
                        "current_tier": effective_tier(u),
                    }
                ), 403
            return f(*args, **kwargs)

        return wrapper

    return deco


def require_portfolio_full(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        _resolve_identity()
        if getattr(g, "auth_kind", None) == "legacy":
            return f(*args, **kwargs)
        u = getattr(g, "db_user", None)
        if u is None:
            return jsonify({"error": "unauthorized"}), 401
        if not tier_caps(effective_tier(u)).portfolio_full:
            return jsonify(
                {
                    "error": "This feature requires Pro plan or higher.",
                    "feature": "portfolio_full",
                    "upgrade_required": True,
                    "min_tier": TIER_PRO,
                    "current_tier": effective_tier(u),
                }
            ), 403
        return f(*args, **kwargs)

    return wrapper


def require_portfolio_advanced(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        _resolve_identity()
        if getattr(g, "auth_kind", None) == "legacy":
            return f(*args, **kwargs)
        u = getattr(g, "db_user", None)
        if u is None:
            return jsonify({"error": "unauthorized"}), 401
        if not tier_caps(effective_tier(u)).portfolio_advanced:
            return jsonify(
                {
                    "error": "This feature requires Medium plan or higher.",
                    "feature": "portfolio_advanced",
                    "upgrade_required": True,
                    "min_tier": TIER_MEDIUM,
                    "current_tier": effective_tier(u),
                }
            ), 403
        return f(*args, **kwargs)

    return wrapper


def require_dca_tier(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        _resolve_identity()
        if getattr(g, "auth_kind", None) == "legacy":
            return f(*args, **kwargs)
        u = getattr(g, "db_user", None)
        if u is None or not tier_caps(effective_tier(u)).dca:
            return jsonify(
                {
                    "error": "DCA requires Medium plan or higher.",
                    "upgrade_required": True,
                    "min_tier": TIER_MEDIUM,
                    "current_tier": effective_tier(u) if u else "basic",
                }
            ), 403
        return f(*args, **kwargs)

    return wrapper


def require_grid_tier(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        _resolve_identity()
        if getattr(g, "auth_kind", None) == "legacy":
            return f(*args, **kwargs)
        u = getattr(g, "db_user", None)
        if u is None or not tier_caps(effective_tier(u)).grid:
            return jsonify(
                {
                    "error": "Grid trading requires Pro plan.",
                    "upgrade_required": True,
                    "min_tier": TIER_PRO,
                    "current_tier": effective_tier(u) if u else "basic",
                }
            ), 403
        return f(*args, **kwargs)

    return wrapper


def require_feature(feature_name: str):
    """403 when the current user's effective tier lacks a named capability."""

    def deco(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            _resolve_identity()
            if getattr(g, "auth_kind", None) == "legacy":
                return f(*args, **kwargs)
            u = getattr(g, "db_user", None)
            if u is None:
                return jsonify({"error": "Not authenticated.", "feature": feature_name}), 401
            if dash_utils.check_feature_access(u, feature_name):
                return f(*args, **kwargs)
            feat = features_payload(u)
            return jsonify(
                {
                    "error": "Feature not available for your plan.",
                    "feature": feature_name,
                    "upgrade_required": True,
                    "current_tier": feat.get("tier_display"),
                    "tier": feat.get("tier"),
                }
            ), 403

        return wrapper

    return deco


def _agent_tier_gate(symbol: str):
    _resolve_identity()
    if getattr(g, "auth_kind", None) == "legacy":
        return None
    u = getattr(g, "db_user", None)
    if u and not agent_symbol_allowed(u, symbol):
        return jsonify(
            {
                "error": "This agent is not included in your plan.",
                "upgrade_required": True,
                "min_tier": TIER_MEDIUM,
                "current_tier": effective_tier(u),
            }
        ), 403
    return None


# ── Async runner ─────────────────────────────────────────────────────────────

def _run_async(coro):
    """Run an async coroutine from sync Flask handler context."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ── Alpaca data helpers ──────────────────────────────────────────────────────

def _fetch_price_yfinance(symbol: str, asset_type: str) -> Optional[float]:
    try:
        import yfinance as yf

        ysym = symbol.replace("/", "-") if asset_type == "crypto" else symbol
        t = yf.Ticker(ysym)
        h = t.history(period="5d")
        if h is not None and not h.empty:
            return float(h["Close"].iloc[-1])
    except Exception as exc:  # noqa: BLE001
        log.debug("yfinance price %s: %s", symbol, exc)
    return None


def _fetch_price(symbol: str, asset_type: str) -> Optional[float]:
    ck = f"{_tenant_tag()}:{symbol}"
    cached = _price_cache.get(ck)
    if cached and (_now() - cached[1]) < _PRICE_TTL:
        return cached[0]
    _tc, _cc, _sc, _, _, _ = _alpaca_clients()
    cc = _cc or _crypto_client
    sc = _sc or _stock_client
    if cc is None or sc is None:
        yp = _fetch_price_yfinance(symbol, asset_type)
        if yp and yp > 0:
            _price_cache[ck] = (yp, _now())
            return yp
        return cached[0] if cached else None
    try:
        if asset_type == "crypto":
            req = CryptoLatestQuoteRequest(symbol_or_symbols=symbol)
            quote = cc.get_crypto_latest_quote(req)
            price = float(quote[symbol].ask_price)
        else:
            req = StockLatestQuoteRequest(symbol_or_symbols=symbol)
            quote = sc.get_stock_latest_quote(req)
            price = float(quote[symbol].ask_price)
            if price <= 0:
                tr = StockLatestTradeRequest(symbol_or_symbols=symbol)
                trade = sc.get_stock_latest_trade(tr)
                price = float(trade[symbol].price)
        if price > 0:
            _price_cache[ck] = (price, _now())
            return price
    except Exception as exc:  # noqa: BLE001
        log.warning("Price fetch failed for %s: %s", symbol, exc)
    yp = _fetch_price_yfinance(symbol, asset_type)
    if yp and yp > 0:
        _price_cache[ck] = (yp, _now())
        return yp
    return cached[0] if cached else None


def _fetch_account() -> dict:
    tag = _tenant_tag()
    bucket = _account_cache.setdefault(tag, {"d": None, "ts": 0.0})
    if bucket["d"] is not None and (_now() - bucket["ts"]) < _ACCOUNT_TTL:
        return bucket["d"]
    tc, _, _, _, _, _ = _alpaca_clients()
    tclient = tc or _trading_client
    if tclient is None:
        return bucket["d"] or {}
    try:
        a = tclient.get_account()
        d = {
            "buying_power": float(a.buying_power or 0),
            "portfolio_value": float(a.portfolio_value or 0),
            "cash": float(a.cash or 0),
            "equity": float(a.equity or 0),
            "currency": getattr(a, "currency", "USD") or "USD",
        }
        bucket["d"] = d
        bucket["ts"] = _now()
        return d
    except Exception as exc:  # noqa: BLE001
        log.warning("Account fetch failed: %s", exc)
        return bucket["d"] or {}


def _fetch_positions() -> list[dict]:
    tc, _, _, _, _, _ = _alpaca_clients()
    tclient = tc or _trading_client
    if tclient is None:
        return []
    try:
        positions = tclient.get_all_positions()
        out: list[dict] = []
        for p in positions:
            try:
                out.append({
                    "symbol": p.symbol,
                    "qty": float(p.qty or 0),
                    "avg_entry_price": float(p.avg_entry_price or 0),
                    "current_price": float(p.current_price) if p.current_price else None,
                    "unrealized_pnl_usd": float(p.unrealized_pl or 0),
                    "unrealized_pnl_pct": float(p.unrealized_plpc or 0) * 100,
                    "market_value": float(p.market_value or 0),
                })
            except Exception:  # noqa: BLE001
                continue
        return out
    except Exception as exc:  # noqa: BLE001
        log.warning("Positions fetch failed: %s", exc)
        return []


def _find_position(positions: list[dict], symbol: str) -> Optional[dict]:
    """Match a position against an agent symbol; Alpaca strips slashes."""
    target_clean = _alpaca_clean(symbol)
    for p in positions:
        if p["symbol"] in (symbol, target_clean):
            return p
    return None


def _fetch_recent_orders(symbol: str, limit: int = 10) -> list[dict]:
    ock = f"{_tenant_tag()}:{symbol}"
    cached = _orders_cache.get(ock)
    if cached and (_now() - cached[1]) < _ORDERS_TTL:
        return cached[0]
    tc, _, _, _, _, _ = _alpaca_clients()
    tclient = tc or _trading_client
    if tclient is None:
        return cached[0] if cached else []
    try:
        clean = _alpaca_clean(symbol)
        req = GetOrdersRequest(
            status=QueryOrderStatus.CLOSED,
            limit=limit,
            symbols=[clean],
        )
        raw = tclient.get_orders(filter=req)
        out: list[dict] = []
        for o in raw:
            try:
                side = o.side.value if hasattr(o.side, "value") else str(o.side)
                status = o.status.value if hasattr(o.status, "value") else str(o.status)
                out.append({
                    "id": str(o.id),
                    "symbol": o.symbol,
                    "side": side,
                    "qty": float(o.qty or 0),
                    "filled_qty": float(o.filled_qty or 0),
                    "filled_avg_price": float(o.filled_avg_price) if o.filled_avg_price else None,
                    "status": status,
                    "submitted_at": str(o.submitted_at) if o.submitted_at else "",
                    "filled_at": str(o.filled_at) if o.filled_at else "",
                })
            except Exception:  # noqa: BLE001
                continue
        _orders_cache[ock] = (out, _now())
        return out
    except Exception as exc:  # noqa: BLE001
        log.warning("Orders fetch failed for %s: %s", symbol, exc)
        return cached[0] if cached else []


def _trades_today_count(symbol: str) -> int:
    db_stats = _paper_trade_stats_today(symbol)
    if db_stats is not None:
        return int(db_stats["trade_count"])

    orders = _fetch_recent_orders(symbol, limit=50)
    today = datetime.now(timezone.utc).date()
    n = 0
    for o in orders:
        ts = (o.get("filled_at") or o.get("submitted_at") or "").strip()
        if not ts:
            continue
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            if dt.date() == today:
                n += 1
        except Exception:  # noqa: BLE001
            continue
    return n


def _paper_trade_stats_today(symbol: str) -> dict[str, float | int] | None:
    _resolve_identity()
    if db.SessionLocal is None:
        return None
    u = getattr(g, "db_user", None)
    if u is None:
        return None

    sym = (symbol or "").strip()
    if not sym:
        return {"pnl_usd": 0.0, "trade_count": 0}
    sym_alt = sym.replace("/", "-")
    sess = db.db_session()
    try:
        row = sess.execute(
            text(
                """
                SELECT
                    COALESCE(SUM(pt.pnl), 0)::double precision AS pnl_usd,
                    COUNT(*)::int AS trade_count
                FROM paper_trades pt
                WHERE pt.user_id = :uid
                  AND DATE(pt.timestamp AT TIME ZONE 'UTC') = (CURRENT_TIMESTAMP AT TIME ZONE 'UTC')::date
                  AND (pt.symbol = :sym OR pt.symbol = :sym_alt)
                """
            ),
            {"uid": int(u.id), "sym": sym, "sym_alt": sym_alt},
        ).mappings().first()
    except Exception as exc:  # noqa: BLE001
        log.debug("paper trade stats today failed for %s: %s", sym, exc)
        return {"pnl_usd": 0.0, "trade_count": 0}

    return {
        "pnl_usd": float((row or {}).get("pnl_usd") or 0.0),
        "trade_count": int((row or {}).get("trade_count") or 0),
    }


# ── Bar history (for regime detection) ──────────────────────────────────────

def _fetch_bars(symbol: str, asset_type: str, limit: int = 80) -> list[float]:
    """Fetch a short close-price history for `symbol`.  Cached ~5 min."""
    bck = f"{_tenant_tag()}:{symbol}"
    cached = _bars_cache.get(bck)
    if cached and (_now() - cached[1]) < _BARS_TTL:
        return cached[0]
    _tc, _cc, _sc, _, _, _ = _alpaca_clients()
    cc = _cc or _crypto_client
    sc = _sc or _stock_client
    if cc is None or sc is None:
        return cached[0] if cached else []
    try:
        if asset_type == "crypto":
            req = CryptoBarsRequest(
                symbol_or_symbols=symbol,
                timeframe=TimeFrame(15, TimeFrameUnit.Minute),
                limit=limit,
            )
            bars = cc.get_crypto_bars(req).data.get(symbol, [])
        else:
            req = StockBarsRequest(
                symbol_or_symbols=symbol,
                timeframe=TimeFrame.Hour,
                limit=limit,
            )
            barset = sc.get_stock_bars(req)
            bars_dict = barset.data
            bars = bars_dict.get(symbol) or (
                list(bars_dict.values())[0] if bars_dict else []
            )
        closes = [float(b.close) for b in bars]
        if closes:
            _bars_cache[bck] = (closes, _now())
        return closes
    except Exception as exc:  # noqa: BLE001
        log.warning("bar fetch failed for %s: %s", symbol, exc)
        return cached[0] if cached else []


# ── Performance tracker / log readers ────────────────────────────────────────

def _read_perf() -> dict:
    _resolve_identity()
    if getattr(g, "db_account", None) is not None and db.SessionLocal is not None:
        try:
            return saas_helpers.read_perf_dict_for_account(db.db_session(), g.db_account.id)
        except Exception as exc:  # noqa: BLE001
            log.debug("db perf read failed: %s", exc)
            return {}
    try:
        if _PERF_PATH.exists():
            with open(_PERF_PATH) as f:
                return json.load(f) or {}
    except Exception as exc:  # noqa: BLE001
        log.debug("perf read failed: %s", exc)
    return {}


def _read_risk_events(n: int = 20) -> list[dict]:
    """Read the last N JSON-line risk events (newest first)."""
    if not _RISK_EVENTS_PATH.exists():
        return []
    try:
        # File is small (one line per event) — read whole thing then tail.
        with open(_RISK_EVENTS_PATH) as f:
            raw = f.readlines()
    except Exception as exc:  # noqa: BLE001
        log.debug("risk events read failed: %s", exc)
        return []
    out: list[dict] = []
    for line in raw[-n:]:
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return list(reversed(out))


def _read_llm_decisions(symbol: Optional[str] = None, n: int = 20) -> list[dict]:
    """Tail the LLM audit log; optional symbol filter."""
    if not _LLM_AUDIT_PATH.exists():
        return []
    try:
        with open(_LLM_AUDIT_PATH) as f:
            raw = f.readlines()
    except Exception as exc:  # noqa: BLE001
        log.debug("llm audit read failed: %s", exc)
        return []
    out: list[dict] = []
    for line in reversed(raw):
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        if symbol and d.get("symbol") != symbol:
            continue
        out.append(d)
        if len(out) >= n:
            break
    return out


def _realized_pnl_today(symbol: str) -> float:
    db_stats = _paper_trade_stats_today(symbol)
    if db_stats is not None:
        return round(float(db_stats["pnl_usd"]), 4)

    _resolve_identity()
    if getattr(g, "db_account", None) is not None and db.SessionLocal is not None:
        try:
            return saas_helpers.realised_pnl_today_db(db.db_session(), g.db_account.id, symbol=symbol)
        except Exception as exc:  # noqa: BLE001
            log.debug("db pnl today: %s", exc)
            return 0.0
    perf = _read_perf()
    today = datetime.now(timezone.utc).date().isoformat()
    pnl = 0.0
    for t in (perf.get("trades") or []):
        if t.get("symbol") != symbol:
            continue
        exit_ts = (t.get("exit_ts") or "")[:10]
        if exit_ts != today:
            continue
        try:
            pnl += float(t.get("pnl_usd") or 0.0)
        except (TypeError, ValueError):
            continue
    return round(pnl, 4)


def _realized_pnl_today_total() -> float:
    _resolve_identity()
    if getattr(g, "db_account", None) is not None and db.SessionLocal is not None:
        try:
            return saas_helpers.realised_pnl_today_db(db.db_session(), g.db_account.id, symbol=None)
        except Exception as exc:  # noqa: BLE001
            log.debug("db pnl today total: %s", exc)
            return 0.0
    perf = _read_perf()
    today = datetime.now(timezone.utc).date().isoformat()
    pnl = 0.0
    for t in (perf.get("trades") or []):
        exit_ts = (t.get("exit_ts") or "")[:10]
        if exit_ts != today:
            continue
        try:
            pnl += float(t.get("pnl_usd") or 0.0)
        except (TypeError, ValueError):
            continue
    return round(pnl, 4)


# ── YAML config writer (preserves comments via line-level regex) ─────────────

def _write_yaml_field(path: Path, key: str, value: str) -> None:
    """Update a top-level scalar field in a YAML file in-place, preserving
    formatting and comments.  Inserts the field after `trade_usd:` if missing.
    """
    text = path.read_text()
    pattern = rf"^{re.escape(key)}:.*$"
    if re.search(pattern, text, flags=re.M):
        new_text = re.sub(pattern, f"{key}: {value}", text, count=1, flags=re.M)
    else:
        new_text = re.sub(
            r"^(trade_usd:.*)$",
            rf"\1\n{key}: {value}",
            text,
            count=1,
            flags=re.M,
        )
    path.write_text(new_text)


def _write_yaml_nested_field(path: Path, parent: str, child: str, value: str) -> None:
    """Update `parent.child: value` inside an indented YAML block, preserving
    comments and formatting.  If the child key is missing it's inserted at the
    top of the parent block; if the parent block is missing both are appended.

    Uses a line-level scan rather than regex multiline back-references because
    the latter are brittle across PyYAML-style and hand-written configs.
    """
    raw = path.read_text()
    lines = raw.splitlines()
    in_parent = False
    parent_indent = 0
    insert_at: Optional[int] = None
    for i, line in enumerate(lines):
        stripped = line.lstrip(" ")
        indent = len(line) - len(stripped)
        if not in_parent:
            if stripped.startswith(f"{parent}:") and not stripped.startswith(f"{parent}: "):
                # Flow scalar like `parent: foo` — overwrite as a block.
                lines[i] = f"{parent}:"
                in_parent = True
                parent_indent = indent
            elif stripped.startswith(f"{parent}:"):
                in_parent = True
                parent_indent = indent
            continue
        # We're inside the parent block.
        if stripped == "" or stripped.lstrip().startswith("#"):
            continue
        if indent <= parent_indent:
            insert_at = i
            break
        if stripped.startswith(f"{child}:"):
            lines[i] = " " * indent + f"{child}: {value}"
            path.write_text("\n".join(lines) + ("\n" if raw.endswith("\n") else ""))
            return
    if in_parent:
        new_line = " " * (parent_indent + 2) + f"{child}: {value}"
        if insert_at is None:
            lines.append(new_line)
        else:
            lines.insert(insert_at, new_line)
    else:
        lines.append(f"{parent}:")
        lines.append(f"  {child}: {value}")
    path.write_text("\n".join(lines) + ("\n" if raw.endswith("\n") else ""))


def _merge_root_yaml_fields(path: Path, updates: dict[str, Any]) -> None:
    """Round-trip merge for top-level blocks (DCA / grid / take_profit / schedules)."""
    with open(path, encoding="utf-8") as f:
        root = yaml.safe_load(f) or {}
    for key, val in updates.items():
        if val is None:
            continue
        root[key] = val
    tmp = path.with_suffix(".merge_tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        yaml.safe_dump(root, f, sort_keys=False, default_flow_style=False, allow_unicode=True)
    tmp.replace(path)


def _merge_portfolio_rebalancing(updates: dict[str, Any]) -> None:
    p = PORTFOLIO_YAML
    p.parent.mkdir(parents=True, exist_ok=True)
    if p.exists():
        with open(p, encoding="utf-8") as f:
            root = yaml.safe_load(f) or {}
    else:
        root = {}
    reb = dict(root.get("rebalancing") or {})
    for k, v in updates.items():
        if v is None:
            continue
        reb[k] = v
    root["rebalancing"] = reb
    tmp = p.with_suffix(".merge_tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        yaml.safe_dump(root, f, sort_keys=False, default_flow_style=False, allow_unicode=True)
    tmp.replace(p)


def _load_ds_overrides() -> dict:
    """Per-symbol runtime data-source enable/disable overrides."""
    if not _DS_OVERRIDE_PATH.exists():
        return {}
    try:
        with open(_DS_OVERRIDE_PATH) as f:
            return json.load(f) or {}
    except Exception as exc:  # noqa: BLE001
        log.debug("ds overrides read failed: %s", exc)
        return {}


def _save_ds_overrides(d: dict) -> None:
    _DS_OVERRIDE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = _DS_OVERRIDE_PATH.with_suffix(".tmp")
    with open(tmp, "w") as f:
        json.dump(d, f, indent=2, sort_keys=True)
    tmp.replace(_DS_OVERRIDE_PATH)


def _ds_enabled(symbol: str, source: str, default: bool = True) -> bool:
    return bool(_load_ds_overrides().get(symbol, {}).get(source, default))


def _datasource_state(canonical: str, cfg) -> dict:
    """Return enabled/disabled state for every toggleable source for `cfg`.

    `alpaca` is always on; `anthropic_llm` reads from YAML; others read
    the runtime overrides JSON.
    """
    return {
        "alpaca":        True,
        "coingecko":     _ds_enabled(canonical, "coingecko"),
        "cmc":           _ds_enabled(canonical, "cmc"),
        "crypto_fg":     _ds_enabled(canonical, "crypto_fg"),
        "yahoo":         _ds_enabled(canonical, "yahoo"),
        "news":          _ds_enabled(canonical, "news"),
        "anthropic_llm": bool(cfg.llm_enabled),
    }


# ── PWA: root-scoped service worker + Digital Asset Links ────────────────────
_STATIC_ROOT = Path(__file__).resolve().parent / "static"


@app.route("/sw.js")
def service_worker():
    """Serve SW from site root so default scope is '/' (install / updates)."""
    resp = make_response(send_from_directory(_STATIC_ROOT, "sw.js", mimetype="application/javascript"))
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    resp.headers["Service-Worker-Allowed"] = "/"
    return resp


@app.route("/.well-known/assetlinks.json")
def well_known_assetlinks():
    path = _STATIC_ROOT / ".well-known" / "assetlinks.json"
    if not path.is_file():
        return jsonify({"error": "assetlinks not found"}), 404
    return send_file(path, mimetype="application/json", max_age=3600)


@app.after_request
def _pwa_static_cache_headers(response: Response):
    try:
        p = request.path or ""
        if p.startswith("/static/") and "sw.js" not in p and response.status_code == 200:
            if "Cache-Control" not in response.headers:
                response.headers["Cache-Control"] = "public, max-age=604800, immutable"
    except Exception:  # noqa: BLE001
        pass
    return response


# ── Routes ───────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return send_file(Path(app.template_folder) / "dashboard.html")


@app.route("/old")
def dashboard_old():
    return render_template("index.html")


@app.route("/pricing")
def pricing():
    """Public pricing page (same SPA shell as dashboard)."""
    return render_template("index.html")


@app.route("/docs/api")
def api_docs_page():
    """Public API documentation page."""
    return render_template("api_docs.html")


@app.route("/v2")
def dashboard_v2():
    return redirect("/")


@app.route("/login/google")
def login_google_start():
    """Friendly URL for Google OAuth (Flask-Dance entry is ``/oauth/google``).

    Pozor: ak nginx/static host vracia SPA ``index.html`` pre všetky cesty okrem ``/api/*``,
    tento endpoint sa nikdy nedostane do Flasku — použite ``/api/auth/google/start``.
    """
    return redirect("/oauth/google")


@app.route("/api/auth/google/start", methods=["GET"])
def auth_google_oauth_start():
    """Vstup do Google OAuth cez ``/api/*`` — spoľahlivé za nginx SPA fallbackom.

    Celostránkový redirect na Flask-Dance (``/oauth/google``). Vyžaduje, aby ``/oauth/``
    tiež smerovalo na Flask (pozri ``docs/nginx-hermes-pwa-snippet.conf``).
    """
    if _GOOGLE_PLACEHOLDER or db.SessionLocal is None:
        return redirect("/?google=unavailable")
    return redirect("/oauth/google")


# Auth ----------------------------------------------------------------------

@app.route("/api/auth/csrf", methods=["GET"])
def auth_csrf():
    """Mint / refresh the CSRF double-submit token stored in the session.

    Call once on page load (before any POST) so the browser has a session
    cookie + matching header token.
    """
    tok = _issue_csrf_token()
    return jsonify({"csrf_token": tok})


@app.route("/api/auth/register", methods=["POST"])
@limiter.limit("3 per hour", key_func=get_remote_address)
def auth_register():
    if db.SessionLocal is None:
        return jsonify({
            "success": False,
            "error": "User registration is not available on this server.",
            "message": "User registration is not available on this server.",
        }), 503
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip()
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    confirm = data.get("confirm_password") or data.get("password_confirm") or ""
    ip = request.remote_addr or "?"
    if confirm and confirm != password:
        return jsonify({
            "success": False,
            "error": "Passwords do not match.",
            "message": "Passwords do not match.",
        }), 400
    sess = db.db_session()
    try:
        user, verify_raw = saas_helpers.register_user(
            sess,
            email=email,
            username=username,
            password=password,
            config_dir=CONFIG_DIR,
            ip=ip,
        )
        ref_in = (
            (request.args.get("ref") or "").strip()
            or (data.get("ref_code") or "").strip()
            or (data.get("referral_code") or "").strip()
        )
        apply_referral_tracking(sess, user, ref_in)
        if verify_raw:
            if not mailer.is_mail_configured():
                sess.rollback()
                return jsonify({
                    "success": False,
                    "error": (
                        "Email verification is required but outgoing mail is not configured. "
                        "Set MAIL_TRANSPORT=smtp, SMTP_HOST, SMTP_USER, SMTP_PASSWORD, and MAIL_FROM in .env."
                    ),
                    "message": (
                        "Email verification is required but outgoing mail is not configured on the server."
                    ),
                }), 503
            try:
                mailer.send_verification_email(
                    user.email,
                    verify_raw,
                    public_base_url=dash_config.DASHBOARD_PUBLIC_BASE_URL,
                )
            except Exception as send_exc:
                sess.rollback()
                log.exception("verification email send failed: %s", send_exc)
                return jsonify({
                    "success": False,
                    "error": "Could not send verification email. Try again later.",
                    "message": "Could not send verification email. Try again later.",
                }), 500
            sess.commit()
            log.info("register pending email verification: %s", user.email)
            return jsonify({
                "success": True,
                "requires_email_verification": True,
                "message": "Check your email to verify your account, then sign in.",
                "email": user.email,
            })
        try_grant_referral_first_login(sess, user)
        sess.commit()
        acc = saas_helpers.default_paper_account_for_user(sess, user.id)
        sess.refresh(user)
        auth.record_success(ip, email)
        session.clear()
        session.permanent = True
        csrf_new = secrets.token_hex(32)
        session["csrf_token"] = csrf_new
        session["logged_in"] = True
        session["auth_kind"] = "db"
        session["user_id"] = user.id
        session["account_id"] = acc.id if acc else None
        session["username"] = user.username
        session["email"] = user.email
        token, expires_at = auth.issue_token(user.username)
        log.info("register + auto-login: %s", user.email)
        _try_assign_demo_agents(user.id)
        return jsonify(
            {
                "success": True,
                "user": _user_summary_for_api(user),
                "welcome": True,
                "email": user.email,
                "username": user.username,
                "auth_kind": "db",
                "token": token,
                "expires_at": expires_at,
                "csrf_token": csrf_new,
                "is_admin": bool(user.is_admin),
                "features": features_payload(user),
            }
        )
    except ValueError as exc:
        sess.rollback()
        msg = str(exc)
        code = 409 if ("Email already registered" in msg or "Username already taken" in msg) else 400
        return jsonify({"success": False, "error": msg, "message": msg}), code
    except Exception as exc:  # noqa: BLE001
        sess.rollback()
        log.exception(
            "auth.register failed (email=%r username=%r): %s",
            email,
            username,
            exc,
        )
        msg_user = "Registration could not complete due to a server error."
        payload: dict[str, Any] = {
            "success": False,
            "error": msg_user,
            "message": msg_user,
        }
        exc_msg = str(exc)
        if "has no property 'accounts'" in exc_msg or (
            type(exc).__name__ == "InvalidRequestError" and "accounts" in exc_msg
        ):
            payload["hint"] = (
                "Application ORM is out of date: `User` must define `accounts` and "
                "`Account` must define `user` with matching back_populates. Deploy the "
                "latest `core/models.py` and restart the service."
            )
        if os.getenv("HERMES_EXPOSE_API_ERRORS", "").lower() in ("1", "true", "yes"):
            payload["detail"] = exc_msg
        return jsonify(payload), 500


@app.route("/api/auth/verify-email", methods=["GET"])
def auth_verify_email():
    """Consume one-time email verification token (link from outbound mail)."""
    raw = (request.args.get("token") or "").strip()
    accept = (request.headers.get("Accept") or "").lower()

    def _respond(ok: bool, *, expired: bool = False, missing: bool = False) -> Any:
        if "application/json" in accept and "text/html" not in accept:
            if ok:
                return jsonify({"success": True, "message": "Email verified."})
            if missing:
                return jsonify({"success": False, "error": "Missing token"}), 400
            if expired:
                return jsonify({"success": False, "error": "Link expired."}), 400
            return jsonify({"success": False, "error": "Invalid token."}), 400
        if ok:
            return redirect("/?verified=1")
        if missing:
            return redirect("/?verify=invalid")
        if expired:
            return redirect("/?verify=expired")
        return redirect("/?verify=invalid")

    if not raw:
        return _respond(False, missing=True)
    if db.SessionLocal is None:
        return jsonify({"success": False, "error": "Database unavailable"}), 503
    sess = db.db_session()
    try:
        user = saas_helpers.user_by_verification_token(sess, raw)
        if not user:
            return _respond(False)
        now = datetime.now(timezone.utc)
        exp = user.email_verification_expires_at
        if exp is not None and exp < now:
            return _respond(False, expired=True)
        user.email_verified = True
        saas_helpers.clear_email_verification_token(user)
        saas_helpers.record_audit(
            sess,
            user_id=user.id,
            account_id=None,
            action="user.email_verified",
            details={"email": user.email},
            ip=request.remote_addr or "?",
        )
        sess.commit()
        _try_assign_demo_agents(user.id)
        return _respond(True)
    except Exception as exc:  # noqa: BLE001
        sess.rollback()
        log.exception("verify-email: %s", exc)
        return _respond(False)
    finally:
        sess.close()
        db.remove_scoped_session()


@app.route("/api/auth/forgot-password", methods=["POST"])
@limiter.limit("5 per hour", key_func=get_remote_address)
def auth_forgot_password():
    msg = "If an account exists, reset instructions were sent."
    if db.SessionLocal is None:
        return jsonify({"success": True, "message": msg})
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    if not email:
        return jsonify({"success": True, "message": msg})
    sess = db.db_session()
    try:
        user = sess.execute(select(User).where(func.lower(User.email) == email)).scalar_one_or_none()
        if user and user.is_active and mailer.is_mail_configured():
            raw = secrets.token_urlsafe(32)
            exp = datetime.now(timezone.utc) + timedelta(hours=1)
            sess.execute(
                text(
                    """
                    INSERT INTO password_reset_tokens (user_id, token_hash, expires_at, created_at)
                    VALUES (:uid, :th, :exp, NOW())
                    """
                ),
                {"uid": int(user.id), "th": _sha256_hex(raw), "exp": exp},
            )
            sess.commit()
            try:
                mailer.send_password_reset_email(
                    user.email,
                    raw,
                    public_base_url=dash_config.DASHBOARD_PUBLIC_BASE_URL,
                )
            except Exception:
                log.exception("password reset email send failed")
        return jsonify({"success": True, "message": msg})
    except Exception:
        sess.rollback()
        log.exception("forgot-password failed")
        return jsonify({"success": True, "message": msg})


@app.route("/api/auth/reset-password", methods=["POST"])
@limiter.limit("10 per hour", key_func=get_remote_address)
def auth_reset_password():
    if db.SessionLocal is None:
        return jsonify({"success": False, "error": "Password reset unavailable."}), 503
    data = request.get_json(silent=True) or {}
    raw = (data.get("token") or "").strip()
    new_password = data.get("new_password") or ""
    if not raw:
        return jsonify({"success": False, "error": "Missing token."}), 400
    if not new_password or len(new_password) < 8:
        return jsonify({"success": False, "error": "Password must be at least 8 characters."}), 400
    sess = db.db_session()
    try:
        row = sess.execute(
            text(
                """
                SELECT id, user_id, expires_at, used_at
                FROM password_reset_tokens
                WHERE token_hash = :th
                LIMIT 1
                """
            ),
            {"th": _sha256_hex(raw)},
        ).mappings().first()
        if not row:
            return jsonify({"success": False, "error": "Invalid or expired token."}), 400
        if row.get("used_at") is not None:
            return jsonify({"success": False, "error": "Token already used."}), 400
        exp = row.get("expires_at")
        if not exp or exp < datetime.now(timezone.utc):
            return jsonify({"success": False, "error": "Invalid or expired token."}), 400
        user = sess.get(User, int(row["user_id"]))
        if user is None or not user.is_active:
            return jsonify({"success": False, "error": "Invalid token."}), 400
        user.password_hash = saas_helpers.hash_password(new_password)
        sess.execute(
            text("UPDATE password_reset_tokens SET used_at = NOW() WHERE id = :id"),
            {"id": int(row["id"])},
        )
        sess.commit()
        return jsonify({"success": True, "message": "Password updated. You can sign in now."})
    except Exception:
        sess.rollback()
        log.exception("reset-password failed")
        return jsonify({"success": False, "error": "Could not reset password."}), 500


@app.route("/api/auth/resend-verification", methods=["POST"])
@limiter.limit("5 per hour", key_func=get_remote_address)
def auth_resend_verification():
    """Resend verification email for db-registered users (enumeration-safe)."""
    data = request.get_json(silent=True) or {}
    email_raw = (data.get("email") or "").strip()
    ack = {
        "success": True,
        "message": "If an account exists and needs verification, we sent an email.",
    }
    if not email_raw or "@" not in email_raw:
        return jsonify(ack)
    if db.SessionLocal is None:
        return jsonify({"success": False, "error": "Database unavailable"}), 503
    if not mailer.is_mail_configured():
        log.warning("resend-verification: mail not configured")
        return jsonify(ack)
    sess = db.db_session()
    try:
        email_n = saas_helpers.normalise_email(email_raw)
        user = sess.execute(select(User).where(User.email == email_n)).scalar_one_or_none()
        if (
            not user
            or user.email_verified
            or (getattr(user, "auth_kind", None) or "db") == "google"
        ):
            return jsonify(ack)
        plat = saas_helpers.get_platform_settings_dict(sess)
        if not saas_helpers.registration_requires_email_verification(plat):
            return jsonify(ack)
        sent_at = user.email_verification_sent_at
        if sent_at is not None and (datetime.now(timezone.utc) - sent_at).total_seconds() < 60:
            return jsonify({
                "success": False,
                "error": "Please wait a minute before requesting another email.",
                "message": "Please wait a minute before requesting another email.",
            }), 429
        raw = saas_helpers.assign_email_verification_token(user)
        sess.commit()
        try:
            mailer.send_verification_email(
                user.email,
                raw,
                public_base_url=dash_config.DASHBOARD_PUBLIC_BASE_URL,
            )
        except Exception as send_exc:
            log.exception("resend-verification send failed: %s", send_exc)
        return jsonify(ack)
    finally:
        sess.close()
        db.remove_scoped_session()


@app.route("/api/auth/google/status", methods=["GET"])
def auth_google_status():
    reasons: list[str] = []
    if _GOOGLE_PLACEHOLDER:
        reasons.append("missing_or_placeholder_google_credentials")
    if db.SessionLocal is None:
        reasons.append("database_not_configured")
    base = dash_config.DASHBOARD_PUBLIC_BASE_URL
    callback = dash_config.GOOGLE_REDIRECT_URI or None
    return jsonify({
        "enabled": bool(not _GOOGLE_PLACEHOLDER and db.SessionLocal is not None),
        "reasons": reasons,
        "client_id_is_placeholder": _GOOGLE_CID.lower() == "placeholder",
        "public_base_url_configured": bool(base),
        "oauth_callback_url_hint": callback,
    })


@app.route("/api/platform/tier-features", methods=["GET"])
def api_platform_tier_features():
    """Static tier matrix from ``dashboard.config`` (see also per-user ``features`` in auth/status)."""
    return jsonify(dash_config.TIER_FEATURES)


@app.route("/api/exchange-rates", methods=["GET"])
def api_exchange_rates():
    """Approximate FX vs USD for SPA CurrencyContext (falls back match frontend FALLBACK_RATES_VS_USD)."""
    return jsonify({
        "rates": {
            "EUR": 0.93,
            "GBP": 0.79,
            "CZK": 23.4,
        },
        "source": "static",
    })


@app.route("/oauth/google/done")
def google_auth_finish():
    if _GOOGLE_PLACEHOLDER or db.SessionLocal is None:
        return redirect("/?google=unavailable")
    from flask_dance.contrib.google import google

    if not google.authorized:
        return redirect("/?google=denied")
    r = google.get("/oauth2/v2/userinfo")
    if not r.ok:
        return redirect("/?google=userinfo_error")
    info = r.json() or {}
    email = (info.get("email") or "").strip()
    name = (info.get("name") or "").strip()
    google_sub = (info.get("sub") or info.get("id") or "").strip() or None
    if not email:
        return redirect("/?google=noemail")
    ip = request.remote_addr or "?"
    sess = db.db_session()
    try:
        user, _created = saas_helpers.register_or_get_google_user(
            sess,
            email=email,
            full_name=name or None,
            google_sub=google_sub,
            config_dir=CONFIG_DIR,
            ip=ip,
        )
        if not user.is_active:
            return redirect("/?google=suspended")
        acc = saas_helpers.default_paper_account_for_user(sess, user.id)
        if acc and acc.account_status != "active":
            return redirect("/?google=account_inactive")
        user.failed_login_count = 0
        user.locked_until = None
        user.last_login = datetime.now(timezone.utc)
        saas_helpers.record_audit(
            sess,
            user_id=user.id,
            account_id=acc.id if acc else None,
            action="auth.login",
            details={"email": user.email, "via": "google"},
            ip=ip,
        )
        try_grant_referral_first_login(sess, user)
        sess.commit()
        if _created:
            _try_assign_demo_agents(user.id)
        auth.record_success(ip, email)
        session.clear()
        session.permanent = True
        csrf_new = secrets.token_hex(32)
        session["csrf_token"] = csrf_new
        session["logged_in"] = True
        session["auth_kind"] = "db"
        session["user_id"] = user.id
        session["account_id"] = acc.id if acc else None
        session["username"] = user.username
        session["email"] = user.email
        redir_q = "google=ok"
        if _created:
            redir_q += "&welcome=1"
        return redirect(f"/?{redir_q}")
    except Exception as exc:  # noqa: BLE001
        sess.rollback()
        log.warning("google oauth finish: %s", exc)
        return redirect("/?google=error")


@app.route("/api/auth/login", methods=["POST"])
@limiter.limit("5 per minute", key_func=get_remote_address)
def auth_login():
    """Login with email (or legacy username). Tries PostgreSQL users first, then users.json."""
    data = request.get_json(silent=True) or {}
    login_id = (data.get("email") or data.get("username") or "").strip()
    password = data.get("password") or ""
    code = (data.get("totp_code") or "").strip()
    ip = request.remote_addr or "?"

    blocked, secs = auth.is_blocked(ip, login_id)
    if blocked:
        log.warning("login blocked: %s/%s for %ds more", ip, login_id, secs)
        return jsonify({
            "success": False,
            "error": "Too many failed attempts. Please try again later.",
            "message": "Too many failed attempts. Please try again later.",
            "blocked_seconds_remaining": secs,
        }), 429

    if not login_id or not password:
        return jsonify({
            "success": False,
            "error": "Enter email and password.",
            "message": "Enter email and password.",
        }), 400

    if db.SessionLocal is not None:
        sess = db.db_session()
        try:
            email_n = saas_helpers.normalise_email(login_id)
            user = sess.execute(select(User).where(User.email == email_n)).scalar_one_or_none()
            if not user and "@" not in login_id:
                user = sess.execute(select(User).where(User.username == login_id)).scalar_one_or_none()
            if user:
                if not user.is_active:
                    return _auth_fail("Account is suspended. Contact support.", status=403)
                if (getattr(user, "auth_kind", None) or "db") == "google":
                    return jsonify({
                        "success": False,
                        "error": "This account uses Google sign-in. Use “Sign in with Google”.",
                        "message": "This account uses Google sign-in. Use “Sign in with Google”.",
                    }), 403
                now = datetime.now(timezone.utc)
                lu = user.locked_until
                if lu is not None:
                    if lu > now:
                        msg = f"Account locked. Try again at {lu.strftime('%H:%M')} UTC."
                        return jsonify({
                            "success": False,
                            "error": msg,
                            "message": msg,
                            "locked_until": lu.isoformat(),
                        }), 403
                    user.locked_until = None
                    user.failed_login_count = 0

                def _bump_lockout() -> None:
                    fc = int(getattr(user, "failed_login_count", 0) or 0) + 1
                    user.failed_login_count = fc
                    if fc >= 5:
                        user.locked_until = now + timedelta(minutes=15)
                        user.failed_login_count = 0

                if not saas_helpers.verify_password_hash(user.password_hash, password):
                    _bump_lockout()
                    sess.commit()
                    now_blocked, block_secs = auth.record_failure(ip, login_id)
                    extra: dict[str, Any] = {}
                    if now_blocked:
                        extra["blocked_seconds_remaining"] = block_secs
                    if user.locked_until and user.locked_until > now:
                        extra["locked_until"] = user.locked_until.isoformat()
                        return jsonify({
                            "success": False,
                            "error": f"Account locked. Try again at {user.locked_until.strftime('%H:%M')} UTC.",
                            "message": f"Account locked. Try again at {user.locked_until.strftime('%H:%M')} UTC.",
                            **extra,
                        }), 401
                    return _auth_fail("Invalid email or password.", **extra)
                plat_login = saas_helpers.get_platform_settings_dict(sess)
                if saas_helpers.registration_requires_email_verification(plat_login) and not user.email_verified:
                    return jsonify({
                        "success": False,
                        "error": (
                            "Please verify your email before signing in. "
                            "Check your inbox or click “Resend verification email”."
                        ),
                        "message": (
                            "Please verify your email before signing in. "
                            "Check your inbox or click “Resend verification email”."
                        ),
                        "email_not_verified": True,
                    }), 403
                if user.totp_enabled:
                    if not code:
                        return _auth_fail(
                            "Please enter your authenticator code.",
                            requires_2fa=True,
                            totp_required=True,
                        )
                    if not saas_helpers.verify_db_totp(user, code):
                        _bump_lockout()
                        sess.commit()
                        now_blocked, block_secs = auth.record_failure(ip, login_id)
                        extra_t: dict[str, Any] = {"requires_2fa": True, "totp_required": True}
                        if now_blocked:
                            extra_t["blocked_seconds_remaining"] = block_secs
                        if user.locked_until and user.locked_until > now:
                            extra_t["locked_until"] = user.locked_until.isoformat()
                            return jsonify({
                                "success": False,
                                "error": f"Account locked. Try again at {user.locked_until.strftime('%H:%M')} UTC.",
                                "message": f"Account locked. Try again at {user.locked_until.strftime('%H:%M')} UTC.",
                                **extra_t,
                            }), 401
                        return _auth_fail("Invalid authenticator code.", **extra_t)
                acc = saas_helpers.default_paper_account_for_user(sess, user.id)
                user.failed_login_count = 0
                user.locked_until = None
                user.last_login = datetime.now(timezone.utc)
                if acc and acc.account_status != "active":
                    return _auth_fail("Trading account is not active.", status=403)
                saas_helpers.record_audit(
                    sess,
                    user_id=user.id,
                    account_id=acc.id if acc else None,
                    action="auth.login",
                    details={"email": user.email},
                    ip=ip,
                )
                try_grant_referral_first_login(sess, user)
                sess.commit()
                auth.record_success(ip, login_id)
                session.clear()
                session.permanent = True
                csrf_new = secrets.token_hex(32)
                session["csrf_token"] = csrf_new
                session["logged_in"] = True
                session["auth_kind"] = "db"
                session["user_id"] = user.id
                session["account_id"] = acc.id if acc else None
                session["username"] = user.username
                session["email"] = user.email
                token, expires_at = auth.issue_token(user.username)
                log.info("login OK (db): %s from %s", user.email, ip)
                return jsonify({
                    "success": True,
                    "user": _user_summary_for_api(user),
                    "username": user.username,
                    "email": user.email,
                    "auth_kind": "db",
                    "token": token,
                    "expires_at": expires_at,
                    "totp_enabled": bool(user.totp_enabled),
                    "totp_required_setup": not user.totp_enabled,
                    "csrf_token": csrf_new,
                    "is_admin": bool(user.is_admin),
                    "features": features_payload(user),
                })

            sess.rollback()
            if "@" in login_id:
                hint_u = (os.getenv("DASHBOARD_USERNAME") or "admin").strip() or "admin"
                return _auth_fail(
                    f"No database account matches this email. Sign in with username «{hint_u}» if you use "
                    "file-based auth, or run scripts/seed_admin.py / reset the password for this email."
                )
        finally:
            sess.close()
            db.remove_scoped_session()

    legacy_user = login_id
    if "@" in login_id:
        fb = (os.getenv("DASHBOARD_USERNAME") or "admin").strip() or "admin"
        if auth.verify_password(fb, password):
            legacy_user = fb
    if not auth.verify_password(legacy_user, password):
        now_blocked, block_secs = auth.record_failure(ip, login_id)
        log.warning("login FAIL (bad password): %s/%s", ip, login_id)
        extra_l: dict[str, Any] = {}
        if now_blocked:
            extra_l["blocked_seconds_remaining"] = block_secs
        return _auth_fail("Invalid email or password.", **extra_l)

    totp_enabled = auth.is_totp_enabled(legacy_user)
    if totp_enabled:
        if not code:
            return _auth_fail(
                "Please enter your authenticator code.",
                requires_2fa=True,
                totp_required=True,
            )
        if not auth.verify_totp(legacy_user, code):
            now_blocked, block_secs = auth.record_failure(ip, login_id)
            log.warning("login FAIL (bad TOTP): %s/%s", ip, login_id)
            extra_t2: dict[str, Any] = {"requires_2fa": True, "totp_required": True}
            if now_blocked:
                extra_t2["blocked_seconds_remaining"] = block_secs
            return _auth_fail("Invalid authenticator code.", **extra_t2)

    auth.record_success(ip, login_id)
    session.clear()
    session.permanent = True
    csrf_new = secrets.token_hex(32)
    session["csrf_token"] = csrf_new
    session["logged_in"] = True
    session["auth_kind"] = "legacy"
    session["username"] = legacy_user
    token, expires_at = auth.issue_token(legacy_user)
    log.info("login OK (legacy): %s from %s (totp=%s)", legacy_user, ip, totp_enabled)
    return jsonify({
        "success": True,
        "user": {"id": None, "email": None, "username": legacy_user, "tier": None},
        "username": legacy_user,
        "email": None,
        "auth_kind": "legacy",
        "token": token,
        "expires_at": expires_at,
        "totp_enabled": totp_enabled,
        "totp_required_setup": not totp_enabled,
        "csrf_token": csrf_new,
        "is_admin": (auth.get_user_public(legacy_user) or {}).get("role") == "admin",
    })


@app.route("/api/auth/logout", methods=["POST"])
def auth_logout():
    token = _bearer_token()
    if token:
        auth.revoke_token(token)
    session.clear()
    return jsonify({"success": True})


@app.route("/unsubscribe/<token>")
def unsubscribe_weekly(token: str):
    """One-click unsubscribe from weekly email reports (no login)."""
    t = (token or "").strip()
    dash = _public_app_base_url()
    ok_page = """<!DOCTYPE html>
<html lang="sk"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Hermes — Odhlásený</title></head>
<body style="margin:0;background:#0f172a;color:#e2e8f0;font-family:system-ui,sans-serif;display:flex;min-height:100vh;align-items:center;justify-content:center;padding:24px">
  <div style="max-width:420px;text-align:center">
    <p style="font-size:18px;margin:0 0 12px">Odhlásený z týždenných reportov</p>
    <p style="font-size:14px;color:#94a3b8;margin:0 0 20px">Už nebudeme posielať týždenný súhrn na tento účet.</p>
    <a href="{{ dash }}/" style="color:#818cf8">Späť na dashboard →</a>
  </div>
</body></html>"""
    err_page = """<!DOCTYPE html>
<html lang="sk"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Hermes — Odkaz</title></head>
<body style="margin:0;background:#0f172a;color:#e2e8f0;font-family:system-ui,sans-serif;display:flex;min-height:100vh;align-items:center;justify-content:center;padding:24px">
  <div style="max-width:420px;text-align:center">
    <p style="font-size:18px;margin:0 0 12px">Neplatný odkaz</p>
    <a href="{{ dash }}/" style="color:#818cf8">Späť na dashboard →</a>
  </div>
</body></html>"""
    if not t or len(t) > 64 or db.SessionLocal is None:
        return render_template_string(err_page, dash=dash), 404
    sess = db.db_session()
    try:
        u = sess.scalar(select(User).where(User.unsubscribe_token == t))
        if u is None:
            return render_template_string(err_page, dash=dash), 404
        u.weekly_report_enabled = False
        sess.commit()
    finally:
        sess.close()
    return render_template_string(ok_page, dash=dash)


@app.route("/api/auth/status")
def auth_status():
    _resolve_identity()
    if not _is_authenticated():
        return jsonify({"authenticated": False, "logged_in": False})
    if g.auth_kind == "db" and g.db_user:
        u = g.db_user
        wre = bool(getattr(u, "weekly_report_enabled", True))
        tg_chat = getattr(u, "telegram_chat_id", None)
        tg_at = getattr(u, "telegram_connected_at", None)
        tg_connected = tg_chat is not None
        tg_iso = tg_at.isoformat() if tg_at else None
        return jsonify({
            "authenticated": True,
            "logged_in": True,
            "username": u.username,
            "email": u.email,
            "auth_kind": "db",
            "account_auth_kind": (getattr(u, "auth_kind", None) or "db"),
            "totp_enabled": bool(u.totp_enabled),
            "role": "admin" if u.is_admin else "user",
            "is_admin": bool(u.is_admin),
            "is_owner": bool(user_is_owner(u)),
            "tier": u.tier,
            "backup_codes_remaining": 0,
            "features": features_payload(u),
            "weekly_report_enabled": wre,
            "telegram_connected": tg_connected,
            "telegram_connected_at": tg_iso,
            "user": {
                "weekly_report_enabled": wre,
                "telegram_connected": tg_connected,
                "telegram_connected_at": tg_iso,
                "tier_limits": get_tier_limits(effective_tier(u)),
                "stripe_status": getattr(u, "stripe_subscription_status", None),
                "billing_cycle": (getattr(u, "billing_cycle", None) or "monthly"),
                "stripe_customer_id": getattr(u, "stripe_customer_id", None),
            },
        })
    user = _current_username()
    info = auth.get_user_public(user or "") or {}
    return jsonify({
        "authenticated": True,
        "logged_in": True,
        "username": user,
        "email": None,
        "auth_kind": "legacy",
        "totp_enabled": bool(info.get("totp_enabled")),
        "role": info.get("role"),
        "is_admin": info.get("role") == "admin",
        "backup_codes_remaining": info.get("backup_codes_remaining", 0),
        "features": unrestricted_features_payload(),
    })


@app.route("/api/v1/auth/fastapi-token", methods=["POST"])
@login_required
def issue_fastapi_token():
    """Bridge endpoint: issue a FastAPI v2 JWT for currently authenticated DB user."""
    _resolve_identity()
    if getattr(g, "auth_kind", None) != "db" or not getattr(g, "db_user", None):
        return jsonify({"error": "A registered account is required."}), 400

    u = g.db_user
    try:
        token = create_fastapi_token(str(u.id), str(u.tier or "basic"))
    except Exception as exc:  # noqa: BLE001
        log.warning("fastapi token issue failed: %s", exc)
        return jsonify({"error": "Unable to issue FastAPI token"}), 500

    expires_in = int(getattr(fastapi_v2_settings, "fastapi_jwt_exp_minutes", 60) * 60)
    return jsonify({"fastapi_token": token, "expires_in": expires_in})


@app.route("/api/settings/weekly-report", methods=["POST"])
@login_required
def toggle_weekly_report():
    _resolve_identity()
    if getattr(g, "auth_kind", None) != "db" or not getattr(g, "db_user", None):
        return jsonify({"error": "A registered account is required."}), 400
    if db.SessionLocal is None:
        return jsonify({"error": "database unavailable"}), 503
    body = request.get_json(silent=True) or {}
    enabled = bool(body.get("enabled", True))
    sess = db.db_session()
    try:
        u = sess.get(User, g.db_user.id)
        if u is None:
            return jsonify({"error": "user not found"}), 404
        u.weekly_report_enabled = enabled
        sess.commit()
    finally:
        sess.close()
    return jsonify({"ok": True})


@app.route("/api/telegram/connect-token", methods=["POST"])
@login_required
def telegram_connect_token():
    _resolve_identity()
    if getattr(g, "auth_kind", None) != "db" or not getattr(g, "db_user", None):
        return jsonify({"ok": False, "error": "A registered account is required."}), 400
    if db.SessionLocal is None:
        return jsonify({"ok": False, "error": "database unavailable"}), 503
    token = secrets.token_urlsafe(32)
    if len(token) > 64:
        token = token[:64]
    exp = datetime.now(timezone.utc) + timedelta(minutes=10)
    sess = db.db_session()
    try:
        u = sess.get(User, g.db_user.id)
        if u is None:
            return jsonify({"ok": False, "error": "user not found"}), 404
        u.telegram_connect_token = token
        u.telegram_connect_token_exp = exp
        sess.commit()
    finally:
        sess.close()
    bot_username = (os.getenv("TELEGRAM_BOT_USERNAME") or "Let_Agents_Cook_bot").strip().lstrip("@")
    deep_link = f"https://t.me/{bot_username}?start={token}"
    return jsonify({"ok": True, "deep_link": deep_link, "expires_in": 600})


@app.route("/api/telegram/disconnect", methods=["POST"])
@login_required
def telegram_disconnect():
    _resolve_identity()
    if getattr(g, "auth_kind", None) != "db" or not getattr(g, "db_user", None):
        return jsonify({"ok": False, "error": "A registered account is required."}), 400
    if db.SessionLocal is None:
        return jsonify({"ok": False, "error": "database unavailable"}), 503
    sess = db.db_session()
    try:
        u = sess.get(User, g.db_user.id)
        if u is None:
            return jsonify({"ok": False, "error": "user not found"}), 404
        u.telegram_chat_id = None
        u.telegram_connected_at = None
        u.telegram_connect_token = None
        u.telegram_connect_token_exp = None
        sess.commit()
    finally:
        sess.close()
    return jsonify({"ok": True})


@app.route("/api/telegram/webhook", methods=["POST"])
@limiter.exempt
def telegram_webhook():
    secret = (os.getenv("TELEGRAM_WEBHOOK_SECRET") or "").strip()
    if secret:
        got = (request.headers.get("X-Telegram-Bot-Api-Secret-Token") or "").strip()
        if len(got) != len(secret) or not secrets.compare_digest(got, secret):
            return "", 403
    payload = request.get_json(silent=True)
    if not payload:
        return "", 200
    eng = db.get_engine()
    if eng is None:
        return "", 200
    try:
        from core.telegram_bot import process_update

        with eng.begin() as conn:
            process_update(payload, conn)
    except Exception as exc:  # noqa: BLE001
        log.warning("telegram webhook: %s", exc)
    return "", 200


@app.route("/api/user/onboarding/complete", methods=["POST"])
@login_required
def user_onboarding_complete():
    if db.SessionLocal is None:
        return jsonify({"error": "database unavailable"}), 503
    _resolve_identity()
    if getattr(g, "auth_kind", None) != "db" or not getattr(g, "db_user", None):
        return jsonify({"error": "A registered account is required."}), 400
    sess = db.db_session()
    u = g.db_user
    u.onboarding_completed_at = datetime.now(timezone.utc)
    sess.commit()
    sess.refresh(u)
    return jsonify({"success": True, "features": features_payload(u)})


@app.route("/api/auth/me")
@login_required
def auth_me():
    _resolve_identity()
    if g.auth_kind == "db" and g.db_user:
        u, a = g.db_user, g.db_account
        acct_payload = None
        if a:
            acct_payload = {
                "id": a.id,
                "type": a.account_type,
                "status": a.account_status,
                "paper_balance": float(a.paper_balance),
            }
        return jsonify({
            "id": u.id,
            "email": u.email,
            "username": u.username,
            "tier": u.tier,
            "is_admin": u.is_admin,
            "is_owner": bool(user_is_owner(u)),
            "totp_enabled": u.totp_enabled,
            "account_auth_kind": (getattr(u, "auth_kind", None) or "db"),
            "account": acct_payload,
            "features": features_payload(u),
        })
    un = _current_username()
    return jsonify({
        "username": un,
        "auth_kind": "legacy",
        "is_admin": (auth.get_user_public(un or "") or {}).get("role") == "admin",
        "features": unrestricted_features_payload(),
    })


# 2FA ------------------------------------------------------------------------

@app.route("/api/auth/2fa/status")
@login_required
def auth_2fa_status():
    _resolve_identity()
    if g.auth_kind == "db" and g.db_user:
        u = g.db_user
        return jsonify({
            "username": u.username,
            "totp_enabled": bool(u.totp_enabled),
            "backup_codes_remaining": 0,
        })
    user = _current_username() or ""
    info = auth.get_user_public(user) or {}
    return jsonify({
        "username": user,
        "totp_enabled": bool(info.get("totp_enabled")),
        "backup_codes_remaining": info.get("backup_codes_remaining", 0),
    })


@app.route("/api/auth/2fa/setup")
@login_required
def auth_2fa_setup():
    _resolve_identity()
    if g.auth_kind == "db" and g.db_user:
        u = g.db_user
        if u.totp_enabled:
            return jsonify({"error": "TOTP already enabled — disable it first to re-setup"}), 409
        uri = pyotp.TOTP(u.totp_secret).provisioning_uri(name=u.email, issuer_name=auth.TOTP_ISSUER)
        img = qrcode.make(uri, box_size=8, border=2)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        qr_b64 = base64.b64encode(buf.getvalue()).decode("ascii")
        return jsonify({
            "username": u.username,
            "secret": u.totp_secret,
            "issuer": auth.TOTP_ISSUER,
            "uri": uri,
            "qr_png_b64": qr_b64,
        })
    user = _current_username() or ""
    if auth.is_totp_enabled(user):
        return jsonify({
            "error": "TOTP already enabled — disable it first to re-setup",
        }), 409
    secret = auth.get_totp_secret(user)
    qr = auth.generate_qr_base64(user)
    if not secret or not qr:
        return jsonify({"error": "user not found"}), 404
    return jsonify({
        "username": user,
        "secret": secret,
        "issuer": auth.TOTP_ISSUER,
        "uri": auth.get_totp_qr_uri(user),
        "qr_png_b64": qr,
    })


@app.route("/api/auth/2fa/verify", methods=["POST"])
@login_required
def auth_2fa_verify():
    _resolve_identity()
    data = request.get_json(silent=True) or {}
    code = (data.get("code") or data.get("totp_code") or "").strip()
    if not code:
        return jsonify({"error": "code required"}), 400
    if g.auth_kind == "db" and g.db_user:
        u = g.db_user
        if not pyotp.TOTP(u.totp_secret).verify(code, valid_window=1):
            return jsonify({"error": "Invalid code — try again"}), 401
        u.totp_enabled = True
        db.db_session().commit()
        log.info("2FA enabled (db) for %s", u.email)
        return jsonify({"success": True, "totp_enabled": True, "backup_codes": []})
    user = _current_username() or ""
    ok, backup = auth.enable_totp(user, code)
    if not ok:
        return jsonify({"error": "Invalid code — try again"}), 401
    log.info("2FA enabled for %s", user)
    return jsonify({
        "success": True,
        "totp_enabled": True,
        "backup_codes": backup,
    })


@app.route("/api/auth/2fa/disable", methods=["POST"])
@login_required
def auth_2fa_disable():
    _resolve_identity()
    data = request.get_json(silent=True) or {}
    code = (data.get("code") or data.get("totp_code") or "").strip()
    if not code:
        return jsonify({"error": "code required"}), 400
    if g.auth_kind == "db" and g.db_user:
        u = g.db_user
        if not pyotp.TOTP(u.totp_secret).verify(code, valid_window=1):
            return jsonify({"error": "Invalid code"}), 401
        u.totp_enabled = False
        u.totp_secret = pyotp.random_base32()
        db.db_session().commit()
        log.warning("2FA disabled (db) for %s", u.email)
        return jsonify({"success": True, "totp_enabled": False})
    user = _current_username() or ""
    ok = auth.disable_totp(user, code)
    if not ok:
        return jsonify({"error": "Invalid code"}), 401
    log.warning("2FA disabled for %s", user)
    return jsonify({"success": True, "totp_enabled": False})


@app.route("/api/auth/password", methods=["POST"])
@login_required
def auth_change_password():
    _resolve_identity()
    data = request.get_json(silent=True) or {}
    cur = data.get("current_password") or ""
    new = data.get("new_password") or ""
    if not new or len(new) < 8:
        return jsonify({"error": "new password must be at least 8 characters"}), 400
    if g.auth_kind == "db" and g.db_user:
        u = g.db_user
        if not saas_helpers.verify_password_hash(u.password_hash, cur):
            return jsonify({"error": "current password incorrect"}), 401
        u.password_hash = saas_helpers.hash_password(new)
        db.db_session().commit()
        return jsonify({"success": True})
    user = _current_username() or ""
    if not auth.change_password(user, cur, new):
        return jsonify({"error": "current password incorrect"}), 401
    return jsonify({"success": True})


# Agents --------------------------------------------------------------------

@app.route("/api/agents")
@login_required
def api_agents():
    cfgs = _load_configs()
    _resolve_identity()
    u = getattr(g, "db_user", None)
    if getattr(g, "auth_kind", None) != "legacy" and u is not None:
        allow = tier_caps(effective_tier(u)).agent_allowlist
        if allow is not None:
            cfgs = [c for c in cfgs if c.symbol in allow]
    positions = _fetch_positions()
    out: list[dict] = []
    for c in cfgs:
        price = _fetch_price(c.symbol, c.asset_type) or 0.0
        pos = _find_position(positions, c.symbol)
        entry = pos["avg_entry_price"] if pos else None
        qty = pos["qty"] if pos else 0.0
        llm_row = _read_llm_decisions(symbol=c.symbol, n=1)
        decision = ((llm_row[0].get("out") or "HOLD") if llm_row else "HOLD").upper()
        if decision not in ("BUY", "SELL", "HOLD"):
            decision = "HOLD"
        reg = _detect_regime_for(c.symbol, c.asset_type)
        out.append({
            "symbol": c.symbol,
            "name": c.name,
            "status": "active",
            "paused": (c.symbol in _paused_symbols()) or (not c.enabled),
            "signal": decision,
            "confidence": float(reg.get("confidence") or 0.0),
            "regime": reg.get("regime") or "unknown",
            "last_price": price,
            "entry_price": entry,
            "position_qty": qty,
            "realized_pnl_today_usd": _realized_pnl_today(c.symbol),
            "rsi": None,
            "trades_today": _trades_today_count(c.symbol),
            "trading_mode": c.trading_mode,
            "asset_type": c.asset_type,
            "llm_enabled": c.llm_enabled,
            "llm_model": c.llm_model,
            "timeframe": c.timeframe,
            "dca": getattr(c, "dca", {}) or {},
            "grid": getattr(c, "grid", {}) or {},
            "take_profit": getattr(c, "take_profit_scaled", {}) or {},
            "scheduled_orders": getattr(c, "scheduled_orders", []) or [],
        })
    return jsonify(out)


def _ensure_memory_agent_access(sess, user_id: int, agent_id: str) -> bool:
    row = sess.execute(
        text(
            """
            SELECT 1
            FROM user_subscriptions
            WHERE user_id = :uid AND agent_id = :aid
            LIMIT 1
            """
        ),
        {"uid": int(user_id), "aid": str(agent_id)},
    ).first()
    return row is not None


@app.route("/api/agents/<agent_id>/memory", methods=["GET"])
@login_required
def get_agent_memory(agent_id: str):
    _resolve_identity()
    if getattr(g, "auth_kind", None) != "db" or not getattr(g, "db_user", None):
        return jsonify({"error": "A registered account is required."}), 400
    if db.SessionLocal is None:
        return jsonify({"error": "database unavailable"}), 503
    clean_agent_id = str(agent_id or "").strip()
    if not clean_agent_id or len(clean_agent_id) > 64:
        return jsonify({"error": "invalid agent id"}), 400

    uid = int(g.db_user.id)
    sess = db.db_session()
    try:
        if not _ensure_memory_agent_access(sess, uid, clean_agent_id):
            return jsonify({"error": "Agent not found for user."}), 404
        rows = sess.execute(
            text(
                """
                SELECT memory_key, memory_value, updated_at
                FROM agent_memory
                WHERE agent_id = :aid AND user_id = :uid
                ORDER BY updated_at DESC
                """
            ),
            {"aid": clean_agent_id, "uid": uid},
        ).mappings().all()
        out = [
            {
                "key": row["memory_key"],
                "value": row["memory_value"],
                "updated_at": row["updated_at"].isoformat() if row.get("updated_at") is not None else None,
            }
            for row in rows
        ]
        return jsonify(out)
    except Exception:  # noqa: BLE001
        log.exception("get agent memory")
        return jsonify({"error": "Could not load memory."}), 500
    finally:
        sess.close()


@app.route("/api/agents/<agent_id>/memory", methods=["POST"])
@login_required
def set_agent_memory(agent_id: str):
    _resolve_identity()
    if getattr(g, "auth_kind", None) != "db" or not getattr(g, "db_user", None):
        return jsonify({"error": "A registered account is required."}), 400
    if db.SessionLocal is None:
        return jsonify({"error": "database unavailable"}), 503
    clean_agent_id = str(agent_id or "").strip()
    if not clean_agent_id or len(clean_agent_id) > 64:
        return jsonify({"error": "invalid agent id"}), 400

    data = request.get_json(silent=True) or {}
    raw_key = str(data.get("key") or "").strip()
    raw_value = str(data.get("value") or "")
    if len(raw_key) > 100:
        return jsonify({"error": "key too long"}), 400
    if len(raw_value) > 2000:
        return jsonify({"error": "value too long"}), 400
    key = raw_key
    value = raw_value
    if not key:
        return jsonify({"error": "key required"}), 400

    uid = int(g.db_user.id)
    sess = db.db_session()
    try:
        if not _ensure_memory_agent_access(sess, uid, clean_agent_id):
            return jsonify({"error": "Agent not found for user."}), 404
        sess.execute(
            text(
                """
                INSERT INTO agent_memory (agent_id, user_id, memory_key, memory_value, updated_at)
                VALUES (:aid, :uid, :mkey, :mval, NOW())
                ON CONFLICT (agent_id, user_id, memory_key)
                DO UPDATE SET memory_value = EXCLUDED.memory_value, updated_at = NOW()
                """
            ),
            {"aid": clean_agent_id, "uid": uid, "mkey": key, "mval": value},
        )
        sess.commit()
        return jsonify({"status": "ok"})
    except Exception:  # noqa: BLE001
        sess.rollback()
        log.exception("set agent memory")
        return jsonify({"error": "Could not store memory."}), 500
    finally:
        sess.close()


@app.route("/api/agents/<agent_id>/memory/<key>", methods=["DELETE"])
@login_required
def delete_agent_memory(agent_id: str, key: str):
    _resolve_identity()
    if getattr(g, "auth_kind", None) != "db" or not getattr(g, "db_user", None):
        return jsonify({"error": "A registered account is required."}), 400
    if db.SessionLocal is None:
        return jsonify({"error": "database unavailable"}), 503
    clean_agent_id = str(agent_id or "").strip()
    if not clean_agent_id or len(clean_agent_id) > 64:
        return jsonify({"error": "invalid agent id"}), 400

    clean_key = str(key or "").strip()
    if len(clean_key) > 100:
        return jsonify({"error": "key too long"}), 400
    if not clean_key:
        return jsonify({"error": "key required"}), 400

    uid = int(g.db_user.id)
    sess = db.db_session()
    try:
        if not _ensure_memory_agent_access(sess, uid, clean_agent_id):
            return jsonify({"error": "Agent not found for user."}), 404
        sess.execute(
            text(
                """
                DELETE FROM agent_memory
                WHERE agent_id = :aid AND user_id = :uid AND memory_key = :mkey
                """
            ),
            {"aid": clean_agent_id, "uid": uid, "mkey": clean_key},
        )
        sess.commit()
        return jsonify({"status": "deleted"})
    except Exception:  # noqa: BLE001
        sess.rollback()
        log.exception("delete agent memory")
        return jsonify({"error": "Could not delete memory."}), 500
    finally:
        sess.close()


def _detect_regime_for(symbol: str, asset_type: str) -> dict:
    """Cached regime detection used by /api/agent and /api/regime."""
    cached = _regime_cache.get(symbol)
    if cached and (_now() - cached[1]) < _REGIME_TTL:
        return cached[0]
    closes = _fetch_bars(symbol, asset_type, limit=80)
    if len(closes) < 21:
        out = {"regime": "unknown", "confidence": 0.0,
               "details": {"reason": f"need >= 21 bars, got {len(closes)}"}}
        _regime_cache[symbol] = (out, _now())
        return out
    try:
        ext_type = "crypto" if asset_type == "crypto" else "stock"
        ctx = _run_async(get_market_context(symbol, ext_type))
    except Exception:  # noqa: BLE001
        ctx = {}
    try:
        result = _run_async(detect_regime(symbol, asset_type, closes, ctx))
        out = {"regime": result.regime, "confidence": result.confidence,
               "details": result.details}
    except Exception as exc:  # noqa: BLE001
        log.debug("regime detect failed for %s: %s", symbol, exc)
        out = {"regime": "unknown", "confidence": 0.0, "details": {"error": str(exc)}}
    _regime_cache[symbol] = (out, _now())
    return out


_VALID_TRADING_MODES = frozenset({"scalping", "day_trading", "long_term", "full_ai"})


def _mode_recommendation_for_symbol(symbol: str, regime: dict) -> dict:
    """Suggest trading mode from historical P&L by mode, else regime heuristic."""
    modes = ("scalping", "day_trading", "long_term", "full_ai")
    pt = get_performance_tracker()
    closed = [
        t for t in pt.trades
        if t.symbol == symbol and t.closed and t.pnl_usd is not None and t.mode in _VALID_TRADING_MODES
    ]
    by_mode: dict[str, dict] = {}
    for m in modes:
        sub = [t for t in closed if t.mode == m]
        if not sub:
            by_mode[m] = {"trades": 0, "total_pnl_usd": 0.0}
        else:
            wins = sum(1 for t in sub if (t.pnl_usd or 0) > 0)
            by_mode[m] = {
                "trades": len(sub),
                "total_pnl_usd": round(sum(t.pnl_usd or 0.0 for t in sub), 4),
                "win_rate": round(wins / len(sub), 4),
            }
    candidates = [(m, v["total_pnl_usd"]) for m, v in by_mode.items() if v["trades"] >= 2]
    if candidates:
        best_mode, best_pnl = max(candidates, key=lambda x: x[1])
        return {
            "recommended": best_mode,
            "source": "history",
            "reason": (
                f"Among modes with ≥2 closed trades on {symbol}, {best_mode} has the highest "
                f"recorded total P&L ({best_pnl:+.2f} USD) in the performance log."
            ),
            "by_mode": by_mode,
        }
    reg = (regime or {}).get("regime") or "unknown"
    reg_map = {
        "trending_up": "long_term",
        "trending_down": "day_trading",
        "ranging": "scalping",
        "volatile": "day_trading",
        "crash": "day_trading",
        "unknown": "day_trading",
    }
    rec = reg_map.get(reg, "day_trading")
    return {
        "recommended": rec,
        "source": "regime",
        "reason": (
            f"Not enough closed trades per mode for {symbol} yet — heuristic from regime "
            f"'{reg}' suggests starting with {rec} (validate with backtests and LLM decisions)."
        ),
        "by_mode": by_mode,
        "regime": reg,
    }


@app.route("/api/agent/<symbol>")
@login_required
def api_agent(symbol):
    canonical = _url_to_symbol(symbol)
    if not canonical:
        return jsonify({"error": f"agent not found: {symbol}"}), 404
    gate = _agent_tier_gate(canonical)
    if gate is not None:
        return gate
    cfgs = _load_configs()
    cfg = next((c for c in cfgs if c.symbol == canonical), None)
    if not cfg:
        return jsonify({"error": f"agent not found: {canonical}"}), 404
    positions = _fetch_positions()
    pos = _find_position(positions, canonical)
    price = _fetch_price(canonical, cfg.asset_type)
    orders = _fetch_recent_orders(canonical, limit=10)
    regime = _detect_regime_for(canonical, cfg.asset_type)
    realized_today = _realized_pnl_today(canonical)
    last_llm = _read_llm_decisions(symbol=canonical, n=1)
    return jsonify({
        "symbol": canonical,
        "name": cfg.name,
        "asset_type": cfg.asset_type,
        "trading_mode": cfg.trading_mode,
        "timeframe": cfg.timeframe,
        "enabled": cfg.enabled,
        "paused": (canonical in _paused_symbols()) or (not cfg.enabled),
        "last_price": price,
        "position": pos,
        "trades_today": _trades_today_count(canonical),
        "realized_pnl_today_usd": realized_today,
        "recent_orders": orders,
        "regime": regime,
        "last_llm_decision": last_llm[0] if last_llm else None,
        "llm_enabled": cfg.llm_enabled,
        "llm_model": cfg.llm_model,
        "rsi_buy_threshold": cfg.rsi_buy_threshold,
        "rsi_sell_threshold": cfg.rsi_sell_threshold,
        "trade_usd": cfg.trade_usd,
        "datasource_enabled": _datasource_state(canonical, cfg),
        "dca": getattr(cfg, "dca", {}) or {},
        "grid": getattr(cfg, "grid", {}) or {},
        "take_profit": getattr(cfg, "take_profit_scaled", {}) or {},
        "scheduled_orders": getattr(cfg, "scheduled_orders", []) or [],
        "mode_recommendation": _mode_recommendation_for_symbol(canonical, regime),
    })


@app.route("/api/regime/<symbol>")
@login_required
def api_regime(symbol):
    canonical = _url_to_symbol(symbol)
    if not canonical:
        return jsonify({"error": f"agent not found: {symbol}"}), 404
    gate = _agent_tier_gate(canonical)
    if gate is not None:
        return gate
    cfgs = _load_configs()
    cfg = next((c for c in cfgs if c.symbol == canonical), None)
    if not cfg:
        return jsonify({"error": f"agent not found: {canonical}"}), 404
    return jsonify(_detect_regime_for(canonical, cfg.asset_type))


@app.route("/api/llm-decisions/<symbol>")
@login_required
@require_tier(TIER_MEDIUM)
def api_llm_decisions(symbol):
    canonical = _url_to_symbol(symbol)
    if not canonical:
        return jsonify({"error": f"agent not found: {symbol}"}), 404
    gate = _agent_tier_gate(canonical)
    if gate is not None:
        return gate
    n = int(request.args.get("limit", "20"))
    return jsonify(_read_llm_decisions(symbol=canonical, n=max(1, min(n, 100))))


@app.route("/api/llm-decisions")
@login_required
@require_tier(TIER_MEDIUM)
def api_llm_decisions_all():
    n = int(request.args.get("limit", "20"))
    return jsonify(_read_llm_decisions(symbol=None, n=max(1, min(n, 100))))


@app.route("/api/risk-events")
@login_required
def api_risk_events():
    n = int(request.args.get("limit", "20"))
    return jsonify(_read_risk_events(n=max(1, min(n, 100))))


@app.route("/api/positions")
@login_required
def api_positions():
    return jsonify(_fetch_positions())


@app.route("/api/trades/<symbol>")
@login_required
def api_trades(symbol):
    canonical = _url_to_symbol(symbol)
    if not canonical:
        return jsonify({"error": f"agent not found: {symbol}"}), 404
    return jsonify(_fetch_recent_orders(canonical, limit=10))


@app.route("/api/market-context/<symbol>")
@login_required
def api_market_context(symbol):
    canonical = _url_to_symbol(symbol)
    if not canonical:
        return jsonify({"error": f"agent not found: {symbol}"}), 404
    cfgs = _load_configs()
    cfg = next((c for c in cfgs if c.symbol == canonical), None)
    if not cfg:
        return jsonify({"error": f"agent not found: {canonical}"}), 404
    asset_type = "crypto" if cfg.asset_type == "crypto" else "stock"
    try:
        ctx = _run_async(get_market_context(canonical, asset_type))
        return jsonify(ctx)
    except Exception as exc:  # noqa: BLE001
        log.warning("market-context fetch failed for %s: %s", canonical, exc)
        return jsonify({"error": str(exc)}), 500


# Status / kill -------------------------------------------------------------

def _uptime_str() -> str:
    sec = int(_now() - _state["started_at"])
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h {m}m"
    if m:
        return f"{m}m"
    return f"{s}s"


def _risk_status_summary() -> dict:
    """Compose a small dict the header pill consumes."""
    rm = get_risk_manager(
        max_daily_loss_pct=float(os.getenv("HERMES_MAX_DAILY_LOSS_PCT", "3.0")),
        max_total_drawdown_pct=float(os.getenv("HERMES_MAX_DRAWDOWN_PCT", "10.0")),
    )
    s = rm.status()
    pv = (_fetch_account() or {}).get("portfolio_value") or 0
    daily_pnl = float(s.get("daily_pnl") or 0)
    daily_start = float(s.get("daily_start_portfolio") or 0) or pv
    peak = float(s.get("peak_portfolio") or 0) or pv
    max_daily_loss_usd = daily_start * float(s.get("max_daily_loss_pct") or 3.0) / 100.0 if daily_start else 0.0
    daily_used_pct = (-daily_pnl / max_daily_loss_usd * 100.0) if max_daily_loss_usd > 0 and daily_pnl < 0 else 0.0
    drawdown_pct = ((peak - pv) / peak * 100.0) if peak > 0 and pv > 0 else 0.0
    if s.get("kill_switch_active"):
        level = "stopped"
    elif daily_used_pct >= 100 or drawdown_pct >= float(s.get("max_total_drawdown_pct") or 10.0):
        level = "stopped"
    elif daily_used_pct >= 60 or drawdown_pct >= 5:
        level = "caution"
    else:
        level = "safe"
    return {
        "level": level,
        "daily_pnl": round(daily_pnl, 2),
        "daily_used_pct": round(min(daily_used_pct, 999), 2),
        "daily_max_pct": float(s.get("max_daily_loss_pct") or 3.0),
        "drawdown_pct": round(drawdown_pct, 2),
        "drawdown_max_pct": float(s.get("max_total_drawdown_pct") or 10.0),
        "peak_portfolio": peak,
        "kill_switch_active": bool(s.get("kill_switch_active")),
    }


@app.route("/api/status")
@login_required
def api_status():
    account = _fetch_account()
    try:
        crypto_fg = _run_async(get_crypto_fear_greed())
    except Exception:  # noqa: BLE001
        crypto_fg = {"value": 50, "label": "Neutral"}
    try:
        stocks_fg = _run_async(get_stocks_fear_greed())
    except Exception:  # noqa: BLE001
        stocks_fg = {"value": 50, "label": "Neutral"}
    try:
        altcoin_season = _run_async(get_cmc_altcoin_season_latest())
    except Exception:  # noqa: BLE001
        altcoin_season = None
    cfgs = _load_configs()
    total_trades = sum(_trades_today_count(c.symbol) for c in cfgs)
    open_positions = len(_fetch_positions())
    realized_today = _realized_pnl_today_total()
    btc_regime = _detect_regime_for("BTC/USD", "crypto") if any(c.symbol == "BTC/USD" for c in cfgs) else {"regime": "unknown"}
    risk_summary = _risk_status_summary()
    return jsonify({
        "kill_switch": _state["kill_switch"] or risk_summary.get("kill_switch_active", False),
        "dry_run": DRY_RUN,
        "alpaca_paper": ALPACA_PAPER,
        "uptime": _uptime_str(),
        "total_trades": total_trades,
        "agent_count": len(cfgs),
        "open_positions": open_positions,
        "realized_pnl_today_usd": realized_today,
        "account": account,
        "market_sentiment": {
            "crypto_fear_greed": crypto_fg,
            "stocks_fear_greed": stocks_fg,
        },
        "altcoin_season": altcoin_season,
        "btc_regime": btc_regime,
        "risk": risk_summary,
    })


# Export ------------------------------------------------------------------

EXPORT_LIMITS = {
    TIER_BASIC: {"csv_per_month": 10, "pdf_per_week": 0, "max_period_days": 7},
    TIER_MEDIUM: {"csv_per_month": 100, "pdf_per_week": 3, "max_period_days": 30},
    TIER_PRO: {"csv_per_month": 500, "pdf_per_week": 20, "max_period_days": 90},
    TIER_ELITE: {"csv_per_month": 5000, "pdf_per_week": 200, "max_period_days": 365},
    TIER_ADMIN: {"csv_per_month": 999999, "pdf_per_week": 999999, "max_period_days": 3650},
}


def _export_limits_for_user(u: Any) -> dict[str, int]:
    tier = effective_tier(u) if u is not None else TIER_BASIC
    return dict(EXPORT_LIMITS.get(tier, EXPORT_LIMITS[TIER_BASIC]))


def _reset_export_windows_if_needed(session, user_id: int) -> dict[str, Any]:
    row = session.execute(
        text(
            """
            SELECT export_csv_count_month, export_pdf_count_week, export_reset_month, export_reset_week
            FROM users WHERE id = :uid
            """
        ),
        {"uid": int(user_id)},
    ).mappings().first()
    if not row:
        return {"csv_count": 0, "pdf_count": 0}
    today = datetime.now(timezone.utc).date()
    month_anchor = today.replace(day=1)
    week_anchor = today - timedelta(days=today.weekday())
    csv_count = int(row.get("export_csv_count_month") or 0)
    pdf_count = int(row.get("export_pdf_count_week") or 0)
    reset_month = row.get("export_reset_month")
    reset_week = row.get("export_reset_week")
    if reset_month is None or reset_month < month_anchor:
        csv_count = 0
        session.execute(
            text("UPDATE users SET export_csv_count_month = 0, export_reset_month = :d WHERE id = :uid"),
            {"d": month_anchor, "uid": int(user_id)},
        )
    if reset_week is None or reset_week < week_anchor:
        pdf_count = 0
        session.execute(
            text("UPDATE users SET export_pdf_count_week = 0, export_reset_week = :d WHERE id = :uid"),
            {"d": week_anchor, "uid": int(user_id)},
        )
    return {"csv_count": csv_count, "pdf_count": pdf_count}


def _consume_export_quota(user_id: int, export_kind: str) -> tuple[bool, str | None]:
    _resolve_identity()
    u = getattr(g, "db_user", None)
    if not u or int(u.id) != int(user_id):
        return False, "unauthorized"
    limits = _export_limits_for_user(u)
    session = db.db_session()
    counters = _reset_export_windows_if_needed(session, user_id)
    if export_kind == "pdf":
        if limits["pdf_per_week"] <= 0:
            return False, "PDF export je dostupný od Medium tieru."
        if counters["pdf_count"] >= limits["pdf_per_week"]:
            return False, "Dosiahol si týždenný limit PDF exportov."
        session.execute(
            text("UPDATE users SET export_pdf_count_week = COALESCE(export_pdf_count_week, 0) + 1 WHERE id = :uid"),
            {"uid": int(user_id)},
        )
    else:
        if counters["csv_count"] >= limits["csv_per_month"]:
            return False, "Dosiahol si mesačný limit CSV exportov."
        session.execute(
            text("UPDATE users SET export_csv_count_month = COALESCE(export_csv_count_month, 0) + 1 WHERE id = :uid"),
            {"uid": int(user_id)},
        )
    session.commit()
    return True, None


def _parse_export_period_days(default_days: int = 30) -> int:
    raw = request.args.get("period_days")
    try:
        val = int(raw) if raw is not None else int(default_days)
    except Exception:  # noqa: BLE001
        val = int(default_days)
    return max(1, min(val, 3650))


@app.route("/api/export/limits")
@login_required
def api_export_limits():
    _resolve_identity()
    u = getattr(g, "db_user", None)
    if not u:
        return jsonify({"error": "unauthorized"}), 401
    session = db.db_session()
    counters = _reset_export_windows_if_needed(session, int(u.id))
    session.commit()
    limits = _export_limits_for_user(u)
    return jsonify(
        {
            "tier": effective_tier(u),
            "limits": limits,
            "usage": counters,
            "remaining": {
                "csv_per_month": max(0, int(limits["csv_per_month"]) - int(counters["csv_count"])),
                "pdf_per_week": max(0, int(limits["pdf_per_week"]) - int(counters["pdf_count"])),
            },
        }
    )


@app.route("/api/export/agent/<agent_id>")
@login_required
def api_export_agent(agent_id: str):
    _resolve_identity()
    u = getattr(g, "db_user", None)
    if not u:
        return jsonify({"error": "unauthorized"}), 401
    fmt = (request.args.get("format") or "csv").lower()
    export_type = (request.args.get("type") or "trades").lower()
    agent_type = (request.args.get("agent_type") or "user").lower()
    if agent_type not in {"user", "system"}:
        return jsonify({"error": "invalid agent_type"}), 400
    if fmt not in {"csv", "pdf"}:
        return jsonify({"error": "invalid format"}), 400
    period_days = _parse_export_period_days(30)
    limits = _export_limits_for_user(u)
    if period_days > int(limits["max_period_days"]):
        return jsonify({"error": f"maximum period_days for your tier is {limits['max_period_days']}"}), 403
    ok, err = _consume_export_quota(int(u.id), "pdf" if fmt == "pdf" else "csv")
    if not ok:
        code = 401 if err == "unauthorized" else 403
        return jsonify({"error": err}), code
    try:
        if fmt == "pdf":
            data = generate_agent_pdf_report(int(u.id), agent_id, agent_type, period_days=period_days)
            mem = io.BytesIO(data)
            filename = f"hermes-agent-{agent_id}-{period_days}d.pdf"
            return send_file(mem, mimetype="application/pdf", as_attachment=True, download_name=filename)
        if export_type == "performance":
            buf = export_agent_performance_csv(int(u.id), agent_id, agent_type, period_days=period_days)
            filename = f"hermes-agent-{agent_id}-performance-{period_days}d.csv"
        else:
            buf = export_agent_trades_csv(int(u.id), agent_id, agent_type, period_days=period_days)
            filename = f"hermes-agent-{agent_id}-trades-{period_days}d.csv"
        return send_file(
            io.BytesIO(buf.getvalue().encode("utf-8")),
            mimetype="text/csv; charset=utf-8",
            as_attachment=True,
            download_name=filename,
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 404
    except Exception as exc:  # noqa: BLE001
        log.warning("agent export failed: %s", exc)
        return jsonify({"error": "Export zlyhal"}), 500


@app.route("/api/export/portfolio")
@login_required
def api_export_portfolio():
    _resolve_identity()
    u = getattr(g, "db_user", None)
    if not u:
        return jsonify({"error": "unauthorized"}), 401
    fmt = (request.args.get("format") or "csv").lower()
    if fmt not in {"csv", "pdf"}:
        return jsonify({"error": "invalid format"}), 400
    period_days = _parse_export_period_days(30)
    limits = _export_limits_for_user(u)
    if period_days > int(limits["max_period_days"]):
        return jsonify({"error": f"maximum period_days for your tier is {limits['max_period_days']}"}), 403
    ok, err = _consume_export_quota(int(u.id), "pdf" if fmt == "pdf" else "csv")
    if not ok:
        code = 401 if err == "unauthorized" else 403
        return jsonify({"error": err}), code
    try:
        if fmt == "pdf":
            data = generate_portfolio_pdf_report(int(u.id), period_days=period_days)
            return send_file(
                io.BytesIO(data),
                mimetype="application/pdf",
                as_attachment=True,
                download_name=f"hermes-portfolio-{period_days}d.pdf",
            )
        buf = export_portfolio_csv(int(u.id), period_days=period_days)
        return send_file(
            io.BytesIO(buf.getvalue().encode("utf-8")),
            mimetype="text/csv; charset=utf-8",
            as_attachment=True,
            download_name=f"hermes-portfolio-{period_days}d.csv",
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("portfolio export failed: %s", exc)
        return jsonify({"error": "Export zlyhal"}), 500

@app.route("/api/export/trades")
@login_required
def api_export_trades():
    """Export performance-tracker closed trades.

    ?format=csv (default) or ?format=json
    Includes a `live_orders` fallback when the engine hasn't run yet:
    we union the performance file (which is empty pre-run) with recent
    Alpaca closed orders for each agent so users see something useful.
    """
    fmt = (request.args.get("format") or "csv").lower()
    perf = _read_perf()
    rows: list[dict] = list(perf.get("trades") or [])
    # Fallback: if no tracker rows, expose Alpaca closed orders so the user
    # always gets a downloadable history.
    if not rows:
        cfgs = _load_configs()
        for c in cfgs:
            for o in _fetch_recent_orders(c.symbol, limit=50):
                rows.append({
                    "symbol": c.symbol,
                    "side": (o.get("side") or "").upper(),
                    "entry_ts": o.get("submitted_at"),
                    "exit_ts": o.get("filled_at"),
                    "entry_price": o.get("filled_avg_price"),
                    "qty": o.get("filled_qty"),
                    "pnl_usd": None,
                    "pnl_pct": None,
                    "mode": c.trading_mode,
                    "regime": None,
                    "exit_reason": o.get("status"),
                })

    _resolve_identity()
    u = getattr(g, "db_user", None)
    if u is not None:
        rows = clamp_trade_history_rows(rows, u, ts_key="exit_ts")

    if fmt == "json":
        payload = {
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "count": len(rows),
            "trades": rows,
        }
        resp = Response(json.dumps(payload, indent=2, default=str), mimetype="application/json")
        resp.headers["Content-Disposition"] = "attachment; filename=hermes-trades.json"
        return resp

    # CSV — keep a stable column order.
    columns = [
        "symbol", "side", "entry_ts", "entry_price", "qty",
        "exit_ts", "exit_price", "pnl_usd", "pnl_pct",
        "hold_seconds", "mode", "regime", "exit_reason",
    ]
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(columns)
    for r in rows:
        w.writerow([r.get(c, "") if r.get(c) is not None else "" for c in columns])
    resp = Response(buf.getvalue(), mimetype="text/csv")
    resp.headers["Content-Disposition"] = "attachment; filename=hermes-trades.csv"
    return resp


@app.route("/api/export/trades.csv", methods=["GET"])
@login_required
def export_trades_csv():
    _resolve_identity()
    user = getattr(g, "db_user", None)
    if user is None:
        return jsonify({"error": "unauthorized"}), 401
    agent_id = (request.args.get("agent_id") or "").strip()
    try:
        limit = min(max(int(request.args.get("limit", 1000)), 1), 5000)
    except (TypeError, ValueError):
        limit = 1000

    where = "WHERE pt.user_id = :uid"
    params: dict[str, Any] = {"uid": int(user.id), "lim": int(limit)}
    if agent_id:
        where += " AND CAST(pt.agent_id AS TEXT) = :aid"
        params["aid"] = agent_id

    eng = db.get_engine()
    if eng is None:
        return jsonify({"error": "database unavailable"}), 503
    with eng.connect() as conn:
        rows = conn.execute(
            text(
                f"""
                SELECT pt.timestamp AS created_at,
                       ta.name AS agent_name,
                       pt.symbol,
                       pt.action AS side,
                       pt.price,
                       pt.quantity,
                       pt.pnl
                FROM paper_trades pt
                LEFT JOIN trading_agents ta ON ta.id = pt.agent_id
                {where}
                ORDER BY pt.timestamp DESC
                LIMIT :lim
                """
            ),
            params,
        ).mappings().all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Date", "Agent", "Symbol", "Side", "Price", "Quantity", "P&L", "Status"])
    for r in rows:
        created_at = r.get("created_at")
        created_at_s = created_at.strftime("%Y-%m-%d %H:%M:%S") if hasattr(created_at, "strftime") else str(created_at or "")[:19]
        writer.writerow(
            [
                created_at_s,
                r.get("agent_name") or "N/A",
                r.get("symbol") or "",
                r.get("side") or "",
                float(r.get("price") or 0.0),
                float(r.get("quantity") or 0.0),
                float(r.get("pnl")) if r.get("pnl") is not None else "",
                "closed",
            ]
        )

    response = make_response(output.getvalue())
    response.headers["Content-Type"] = "text/csv"
    response.headers["Content-Disposition"] = (
        f'attachment; filename=hermes_trades_{datetime.now(timezone.utc).strftime("%Y%m%d")}.csv'
    )
    return response


@app.route("/api/export/report.pdf", methods=["GET"])
@login_required
def export_report_pdf():
    _resolve_identity()
    user = getattr(g, "db_user", None)
    if user is None:
        return jsonify({"error": "unauthorized"}), 401
    try:
        from reportlab.lib import colors  # noqa: PLC0415
        from reportlab.lib.pagesizes import A4  # noqa: PLC0415
        from reportlab.lib.styles import getSampleStyleSheet  # noqa: PLC0415
        from reportlab.lib.units import mm  # noqa: PLC0415
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle  # noqa: PLC0415
    except Exception:
        return jsonify({"error": "PDF dependency missing: install reportlab"}), 503

    eng = db.get_engine()
    if eng is None:
        return jsonify({"error": "database unavailable"}), 503
    with eng.connect() as conn:
        stats = conn.execute(
            text(
                """
                SELECT
                    COALESCE(SUM(pnl), 0) AS total_pnl,
                    COUNT(*)::int AS total_trades,
                    COUNT(CASE WHEN pnl > 0 THEN 1 END)::int AS winning_trades,
                    COUNT(CASE WHEN pnl < 0 THEN 1 END)::int AS losing_trades,
                    COALESCE(MAX(pnl), 0) AS best_trade,
                    COALESCE(MIN(pnl), 0) AS worst_trade,
                    COALESCE(AVG(pnl), 0) AS avg_pnl
                FROM paper_trades
                WHERE user_id = :uid
                """
            ),
            {"uid": int(user.id)},
        ).mappings().first() or {}
        recent_trades = conn.execute(
            text(
                """
                SELECT pt.timestamp AS created_at,
                       ta.name AS agent,
                       pt.symbol,
                       pt.action AS side,
                       pt.price,
                       pt.pnl
                FROM paper_trades pt
                LEFT JOIN trading_agents ta ON ta.id = pt.agent_id
                WHERE pt.user_id = :uid
                ORDER BY pt.timestamp DESC
                LIMIT 20
                """
            ),
            {"uid": int(user.id)},
        ).mappings().all()

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=20 * mm,
        leftMargin=20 * mm,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
    )
    styles = getSampleStyleSheet()
    story = []

    story.append(Paragraph("HERMES TRADING PLATFORM", styles["Title"]))
    story.append(Paragraph(f"Performance Report - {datetime.now(timezone.utc).strftime('%B %d, %Y')}", styles["Normal"]))
    story.append(
        Paragraph(
            f"Account: {getattr(user, 'email', 'N/A')} | Tier: {str(getattr(user, 'tier', 'basic')).upper()}",
            styles["Normal"],
        )
    )
    story.append(Spacer(1, 10 * mm))

    total_trades = int(stats.get("total_trades") or 0)
    winning_trades = int(stats.get("winning_trades") or 0)
    win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0.0
    summary_data = [
        ["Metric", "Value"],
        ["Total P&L", f"${float(stats.get('total_pnl') or 0):+.2f}"],
        ["Total Trades", str(total_trades)],
        ["Win Rate", f"{win_rate:.1f}%"],
        ["Winning Trades", str(winning_trades)],
        ["Losing Trades", str(int(stats.get("losing_trades") or 0))],
        ["Best Trade", f"${float(stats.get('best_trade') or 0):+.2f}"],
        ["Worst Trade", f"${float(stats.get('worst_trade') or 0):+.2f}"],
        ["Avg P&L / Trade", f"${float(stats.get('avg_pnl') or 0):+.2f}"],
    ]
    t = Table(summary_data, colWidths=[80 * mm, 80 * mm])
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a1f4e")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#f8f9ff"), colors.white]),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e0e4f0")),
                ("FONTSIZE", (0, 0), (-1, -1), 10),
                ("PADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(Paragraph("SUMMARY", styles["Heading2"]))
    story.append(t)
    story.append(Spacer(1, 8 * mm))

    trades_data = [["Date", "Agent", "Symbol", "Side", "Price", "P&L"]]
    for r in recent_trades:
        created_at = r.get("created_at")
        d_s = created_at.strftime("%Y-%m-%d") if hasattr(created_at, "strftime") else str(created_at or "")[:10]
        trades_data.append(
            [
                d_s,
                str(r.get("agent") or "N/A")[:20],
                r.get("symbol") or "",
                r.get("side") or "",
                f"${float(r.get('price') or 0.0):.2f}",
                f"${float(r.get('pnl') or 0.0):+.2f}" if r.get("pnl") is not None else "-",
            ]
        )
    t2 = Table(trades_data, colWidths=[25 * mm, 45 * mm, 25 * mm, 15 * mm, 25 * mm, 25 * mm])
    t2.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a1f4e")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#f8f9ff"), colors.white]),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e0e4f0")),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("PADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.append(Paragraph("RECENT TRADES (Last 20)", styles["Heading2"]))
    story.append(t2)
    story.append(Spacer(1, 10 * mm))
    story.append(Paragraph("Generated by Hermes Trading Platform - letagentscook.lol", styles["Normal"]))
    doc.build(story)
    buffer.seek(0)

    response = make_response(buffer.getvalue())
    response.headers["Content-Type"] = "application/pdf"
    response.headers["Content-Disposition"] = (
        f'attachment; filename=hermes_report_{datetime.now(timezone.utc).strftime("%Y%m%d")}.pdf'
    )
    return response


@app.route("/api/export/performance")
@login_required
def api_export_performance():
    """Download a JSON summary of overall performance + risk + sentiment."""
    perf = _read_perf()
    risk = _risk_status_summary()
    _resolve_identity()
    u = getattr(g, "db_user", None)
    trades = list(perf.get("trades") or [])
    if u is not None:
        trades = clamp_trade_history_rows(trades, u, ts_key="exit_ts")
    try:
        crypto_fg = _run_async(get_crypto_fear_greed())
    except Exception:  # noqa: BLE001
        crypto_fg = None
    payload = {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "summary": perf.get("summary") or {},
        "by_symbol": (perf.get("summary") and {}) or {},
        "risk": risk,
        "market_sentiment": {"crypto_fear_greed": crypto_fg},
        "trades": trades,
    }
    resp = Response(json.dumps(payload, indent=2, default=str), mimetype="application/json")
    resp.headers["Content-Disposition"] = "attachment; filename=hermes-performance.json"
    return resp


@app.route("/api/kill", methods=["POST"])
@login_required
def api_kill():
    _state["kill_switch"] = True
    log.warning("Kill switch activated via dashboard")
    return jsonify({
        "kill_switch": True,
        "message": "Kill switch activated (dashboard scope; the live trading "
                   "engine reads its own kill_event).",
    })


# Performance / Risk -------------------------------------------------------

@app.route("/api/performance")
@login_required
def api_performance():
    """Aggregated trade performance — win rate, Sharpe, drawdown, P&L."""
    _resolve_identity()
    try:
        if getattr(g, "db_account", None) is not None and db.SessionLocal is not None:
            pl = saas_helpers.trade_performance_payload(db.db_session(), g.db_account.id)
            u2 = getattr(g, "db_user", None)
            pl["recent"] = clamp_trade_history_rows(pl.get("recent") or [], u2)
            return jsonify(pl)
        tracker = get_performance_tracker()
        return jsonify({
            "summary": tracker.summary(),
            "by_symbol": tracker.by_symbol(),
            "recent": tracker.recent(20),
        })
    except Exception as exc:  # noqa: BLE001
        log.warning("performance fetch failed: %s", exc)
        return jsonify({"error": str(exc)}), 500


@app.route("/api/risk")
@login_required
def api_risk():
    """Portfolio-level risk manager state (daily P&L, peak, drawdown)."""
    try:
        rm = get_risk_manager(
            max_daily_loss_pct=float(os.getenv("HERMES_MAX_DAILY_LOSS_PCT", "3.0")),
            max_total_drawdown_pct=float(os.getenv("HERMES_MAX_DRAWDOWN_PCT", "10.0")),
        )
        return jsonify(rm.status())
    except Exception as exc:  # noqa: BLE001
        log.warning("risk fetch failed: %s", exc)
        return jsonify({"error": str(exc)}), 500


# Health monitoring -------------------------------------------------------

# Per-agent log files written by core.hermes._setup_agent_logger.  The naming
# is "<agent_name_lowercase_with_underscores>.log".  Most users see them at
# /var/log/hermes/<sym>_agent.log; we also fall back to /root/hermes/logs.
_AGENT_LOG_DIRS = (Path("/var/log/hermes"), _BASE / "logs")
_HERMES_LOG_CANDIDATES = (Path("/var/log/hermes/hermes.log"), _BASE / "logs" / "hermes.log")
_HERMES_AGENTS_LOG = Path("/var/log/hermes-agents.log")

# Regex to parse a per-agent log line:  "YYYY-MM-DD HH:MM:SS,mmm | LEVEL | MSG"
_LOG_LINE_RE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d+\s*\|\s*(?P<level>\w+)\s*\|\s*(?P<msg>.*)$"
)
# Regex to extract a STATUS line's payload.  The format matches what
# BaseAgent.tick logs:
#   STATUS  price=$78765.6920  RSI=60.4   signal=HOLD conf=0.00  pos=0.000000  regime=ranging  session=0.50
_STATUS_RE = re.compile(
    r"STATUS\s+price=\$?(?P<price>[-\d.]+)\s+RSI=(?P<rsi>[\d.]+)\s+"
    r"signal=(?P<signal>\w+)\s+conf=(?P<conf>[\d.]+)\s+"
    r"pos=(?P<pos>[-\d.]+)(?:\s+regime=(?P<regime>\w+))?(?:\s+session=(?P<session>[-\d.]+))?"
)


def _candidate_log_paths(agent_name: str) -> list[Path]:
    """Map an agent's `name` to the on-disk log path, trying both common dirs.

    Example:  "BTC Agent" → ["/var/log/hermes/btc_agent.log", "/root/hermes/logs/btc_agent.log"]
    """
    safe = agent_name.lower().replace(" ", "_")
    return [d / f"{safe}.log" for d in _AGENT_LOG_DIRS]


def _tail_lines(path: Path, n: int = 200) -> list[str]:
    """Cheap reverse tail: read last 32 KB then split.  Good enough for ≤200 lines
    of structured log output.
    """
    if not path.exists():
        return []
    try:
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(max(0, size - 32 * 1024))
            data = f.read().decode("utf-8", errors="replace")
        lines = data.splitlines()
        return lines[-n:]
    except Exception as exc:  # noqa: BLE001
        log.debug("tail %s failed: %s", path, exc)
        return []


def _parse_ts(ts: str) -> Optional[float]:
    """Parse "YYYY-MM-DD HH:MM:SS" (UTC) → epoch float."""
    try:
        return datetime.strptime(ts, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).timestamp()
    except (TypeError, ValueError):
        return None


def _agent_log_health(agent_name: str) -> dict:
    """Walk back through an agent's log to extract the most recent STATUS,
    plus counts of recent ERROR/WARNING events."""
    out: dict[str, Any] = {
        "log_path": None,
        "last_status_at": None,
        "last_status_age_seconds": None,
        "last_status": None,        # parsed STATUS payload
        "last_error_at": None,
        "last_error_msg": None,
        "errors_recent": 0,
        "warnings_recent": 0,
    }
    path = next((p for p in _candidate_log_paths(agent_name) if p.exists()), None)
    if not path:
        return out
    out["log_path"] = str(path)
    lines = _tail_lines(path, n=200)
    now = time.time()
    found_status = False
    for line in reversed(lines):
        m = _LOG_LINE_RE.match(line)
        if not m:
            continue
        level = m.group("level")
        msg = m.group("msg")
        ts_epoch = _parse_ts(m.group("ts"))
        if not found_status and msg.startswith("STATUS"):
            sm = _STATUS_RE.search(msg)
            if sm:
                out["last_status_at"] = m.group("ts")
                out["last_status_age_seconds"] = round(now - ts_epoch, 1) if ts_epoch else None
                out["last_status"] = {
                    "price":      float(sm.group("price")),
                    "rsi":        float(sm.group("rsi")),
                    "signal":     sm.group("signal"),
                    "confidence": float(sm.group("conf")),
                    "position":   float(sm.group("pos")),
                    "regime":     sm.group("regime") or "unknown",
                    "session":    float(sm.group("session")) if sm.group("session") else None,
                }
                found_status = True
        if level == "ERROR":
            out["errors_recent"] += 1
            if out["last_error_at"] is None:
                out["last_error_at"] = m.group("ts")
                out["last_error_msg"] = msg[:240]
        elif level == "WARNING":
            out["warnings_recent"] += 1
    return out


def _systemd_service_status(unit: str) -> dict:
    """Parse `systemctl show` output for a unit; safe in sandboxes that block
    systemctl entirely (returns `available=False` instead of raising)."""
    if not shutil.which("systemctl"):
        return {"available": False}
    try:
        proc = subprocess.run(
            ["systemctl", "show", unit,
             "--property=ActiveState,SubState,MainPID,ActiveEnterTimestamp,ExecMainStartTimestamp,Result,NRestarts"],
            capture_output=True, text=True, timeout=3,
        )
    except Exception as exc:  # noqa: BLE001
        return {"available": False, "error": str(exc)}
    if proc.returncode != 0:
        return {"available": False, "error": proc.stderr.strip() or f"rc={proc.returncode}"}
    fields: dict[str, str] = {}
    for line in proc.stdout.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            fields[k] = v
    active = fields.get("ActiveState") == "active"
    sub = fields.get("SubState")
    started = fields.get("ActiveEnterTimestamp") or fields.get("ExecMainStartTimestamp") or ""
    started_epoch: Optional[float] = None
    if started:
        # systemd format: "Sun 2026-05-03 18:55:30 UTC"
        try:
            started_epoch = datetime.strptime(started.split(" ", 1)[1], "%Y-%m-%d %H:%M:%S %Z").replace(tzinfo=timezone.utc).timestamp()
        except (ValueError, IndexError):
            try:
                started_epoch = datetime.strptime(started, "%a %Y-%m-%d %H:%M:%S %Z").replace(tzinfo=timezone.utc).timestamp()
            except ValueError:
                started_epoch = None
    uptime = round(time.time() - started_epoch, 1) if started_epoch else None
    return {
        "available": True,
        "unit": unit,
        "active": active,
        "sub_state": sub,
        "main_pid": int(fields.get("MainPID") or 0) or None,
        "started_at": started or None,
        "uptime_seconds": uptime,
        "result": fields.get("Result"),
        "restart_count": int(fields.get("NRestarts") or 0),
    }


@app.route("/api/agents/health")
@login_required
def api_agents_health():
    """Health snapshot for the trading engine + every loaded agent.

    Combines three signals:
      - systemd state (active / sub-state / uptime / restart count)
      - per-agent log tail (last STATUS line, recent error counts)
      - dashboard-side derived state (paused, mode)
    """
    cfgs = _load_configs()
    service = _systemd_service_status("hermes-agents.service")

    # Engine summary: most-recent line in /var/log/hermes-agents.log so we can
    # tell at a glance whether something broke loose since service start.
    engine_log_path = _HERMES_AGENTS_LOG if _HERMES_AGENTS_LOG.exists() else next(
        (p for p in _HERMES_LOG_CANDIDATES if p.exists()), None
    )
    engine_last_line = ""
    engine_recent_errors = 0
    if engine_log_path:
        for line in _tail_lines(engine_log_path, n=100):
            m = _LOG_LINE_RE.match(line)
            if not m:
                continue
            engine_last_line = line
            if m.group("level") == "ERROR":
                engine_recent_errors += 1

    agents_out: list[dict] = []
    overall_ok = True
    overall_stale = 0
    for c in cfgs:
        h = _agent_log_health(c.name)
        # Heuristic: an agent is "stale" if its last STATUS is older than 4×
        # its check_interval, with a 60s floor (prevents fast-cadence agents
        # from being marked stale during normal sleeps).
        check_int = max(getattr(c, "check_interval_seconds", None) or 300, 60)
        stale = (
            h["last_status_age_seconds"] is None
            or h["last_status_age_seconds"] > 4 * check_int
        )
        if stale:
            overall_stale += 1
        # Status verdict: ok | stale | error
        if h["errors_recent"] > 0:
            verdict = "error"
            overall_ok = False
        elif stale:
            verdict = "stale"
        else:
            verdict = "ok"
        agents_out.append({
            "symbol": c.symbol,
            "name": c.name,
            "asset_type": c.asset_type,
            "trading_mode": c.trading_mode,
            "enabled": c.enabled,
            "paused": (c.symbol in _paused_symbols()) or (not c.enabled),
            "check_interval_seconds": check_int,
            "verdict": verdict,
            **h,
        })

    return jsonify({
        "service": service,
        "engine": {
            "log_path": str(engine_log_path) if engine_log_path else None,
            "last_log_line": engine_last_line,
            "recent_errors": engine_recent_errors,
            "agent_count": len(cfgs),
            "stale_agents": overall_stale,
            "all_ok": overall_ok and overall_stale == 0,
        },
        "agents": agents_out,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    })


@app.route("/api/agent/<symbol>/mode", methods=["POST"])
@login_required
def api_set_mode(symbol):
    canonical = _url_to_symbol(symbol)
    if not canonical:
        return jsonify({"error": f"agent not found: {symbol}"}), 404
    gate = _agent_tier_gate(canonical)
    if gate is not None:
        return gate
    data = request.get_json(silent=True) or {}
    mode = (data.get("mode") or "").strip()
    if mode not in _VALID_TRADING_MODES:
        return jsonify({
            "error": "invalid mode (use scalping|day_trading|long_term|full_ai)",
        }), 400
    path = _config_path_for_symbol(canonical)
    if path:
        try:
            _write_yaml_field(path, "trading_mode", mode)
            _bump_cfg_cache()
            log.info("trading_mode for %s set to %s", canonical, mode)
            return jsonify({"success": True, "symbol": canonical, "trading_mode": mode})
        except Exception as exc:  # noqa: BLE001
            return jsonify({"error": str(exc)}), 500
    if _db_update_agent_root_fields(canonical, {"trading_mode": mode}):
        log.info("trading_mode for %s set to %s (db)", canonical, mode)
        return jsonify({"success": True, "symbol": canonical, "trading_mode": mode})
    return jsonify({"error": f"config not found for {canonical}"}), 404


@app.route("/api/agent/<symbol>/datasource", methods=["POST"])
@login_required
def api_set_datasource(symbol):
    """Toggle a data source on/off for `symbol`.

    Body: {"source": "<name>", "enabled": <bool>}

    `anthropic_llm` writes `llm.enabled` into the agent's YAML config so the
    engine respects it on next reload.  All other sources are stored in the
    runtime overrides JSON; the engine can opt into reading these later.
    """
    canonical = _url_to_symbol(symbol)
    if not canonical:
        return jsonify({"error": f"agent not found: {symbol}"}), 404
    gate = _agent_tier_gate(canonical)
    if gate is not None:
        return gate
    cfgs = _load_configs()
    cfg = next((c for c in cfgs if c.symbol == canonical), None)
    if not cfg:
        return jsonify({"error": f"agent not found: {canonical}"}), 404
    data = request.get_json(silent=True) or {}
    source = str(data.get("source") or "").strip()
    enabled = bool(data.get("enabled"))
    if source not in DATASOURCES:
        return jsonify({
            "error": f"invalid source (allowed: {', '.join(DATASOURCES)})",
        }), 400
    try:
        if source == "anthropic_llm":
            path = _config_path_for_symbol(canonical)
            if path:
                _write_yaml_nested_field(path, "llm", "enabled", "true" if enabled else "false")
                _bump_cfg_cache()
                log.info("llm.enabled for %s set to %s", canonical, enabled)
            elif _db_merge_agent_yaml_fields(canonical, {"llm": {"enabled": enabled}}):
                _bump_cfg_cache()
                log.info("llm.enabled for %s set to %s (db)", canonical, enabled)
            else:
                return jsonify({"error": f"config not found for {canonical}"}), 404
        else:
            d = _load_ds_overrides()
            d.setdefault(canonical, {})[source] = enabled
            _save_ds_overrides(d)
            log.info("datasource %s for %s set to %s", source, canonical, enabled)
        # Re-fetch cfg after potential YAML write to surface new state.
        cfgs2 = _load_configs()
        cfg2 = next((c for c in cfgs2 if c.symbol == canonical), cfg)
        return jsonify({
            "success": True,
            "symbol": canonical,
            "source": source,
            "enabled": enabled,
            "datasource_enabled": _datasource_state(canonical, cfg2),
        })
    except Exception as exc:  # noqa: BLE001
        log.warning("datasource toggle failed for %s/%s: %s", canonical, source, exc)
        return jsonify({"error": str(exc)}), 500


@app.route("/api/agent/<symbol>/toggle", methods=["POST"])
@login_required
def api_toggle(symbol):
    canonical = _url_to_symbol(symbol)
    if not canonical:
        return jsonify({"error": f"agent not found: {symbol}"}), 404
    gate = _agent_tier_gate(canonical)
    if gate is not None:
        return gate
    ps = _paused_symbols()
    if canonical in ps:
        _set_paused(canonical, False)
        return jsonify({"symbol": canonical, "paused": False})
    _set_paused(canonical, True)
    return jsonify({"symbol": canonical, "paused": True})


# ── AI Insights & Backtesting (Block 7) ───────────────────────────────────────

@app.route("/api/insights/explain/<path:sym>")
@login_required
@require_tier(TIER_MEDIUM)
def api_insights_explain(sym):
    canonical = _url_to_symbol(sym) or sym.replace("-", "/")
    cfg = next((c for c in _load_configs() if c.symbol == canonical), None)
    if not cfg:
        return jsonify({"error": f"agent not found: {sym}"}), 404
    try:
        from core.market_explainer import explain_price_move

        out = _run_async(explain_price_move(cfg.symbol, cfg.asset_type))
        return jsonify(out)
    except Exception as exc:  # noqa: BLE001
        log.warning("insights explain failed: %s", exc)
        return jsonify({"error": str(exc)}), 500


@app.route("/api/insights/daily")
@login_required
@require_tier(TIER_MEDIUM)
def api_insights_daily():
    force = request.args.get("force", "").lower() in ("1", "true", "yes")
    try:
        from core.daily_summary import generate_daily_summary

        out = _run_async(generate_daily_summary(force_refresh=force))
        if out.get("error"):
            return jsonify(out), 503
        return jsonify(out)
    except Exception as exc:  # noqa: BLE001
        log.warning("daily summary endpoint: %s", exc)
        return jsonify({"error": str(exc)}), 500


@app.route("/api/insights/earnings/<symbol>")
@login_required
@require_tier(TIER_MEDIUM)
def api_insights_earnings(symbol):
    sym = symbol.strip().upper().replace("-USD", "").replace("/", "")
    try:
        from core.earnings_analyzer import analyze_earnings

        out = _run_async(analyze_earnings(sym))
        if out.get("error") == "unsupported":
            return jsonify(out), 400
        return jsonify(out)
    except Exception as exc:  # noqa: BLE001
        log.warning("earnings: %s", exc)
        return jsonify({"error": str(exc)}), 500


@app.route("/api/strategy/from-prompt", methods=["POST"])
@login_required
@require_tier(TIER_PRO)
def api_strategy_from_prompt():
    data = request.get_json(silent=True) or {}
    prompt = str(data.get("prompt") or "").strip()
    try:
        from core.strategy_builder import apply_params_to_agent_yaml, build_strategy_from_prompt

        out = _run_async(build_strategy_from_prompt(prompt))
        if out.get("error") and not out.get("ok"):
            code = 429 if out.get("error") == "rate_limit" else 400
            return jsonify(out), code
        if data.get("apply") and data.get("symbol"):
            sym = str(data["symbol"]).strip()
            apply_res = apply_params_to_agent_yaml(sym, out["params"])
            out["apply_result"] = apply_res
        return jsonify(out)
    except Exception as exc:  # noqa: BLE001
        log.warning("strategy from prompt: %s", exc)
        return jsonify({"error": str(exc)}), 500


# ── Portfolio & calendar (Block 8) ──────────────────────────────────────────


@app.route("/api/calendar")
@login_required
def api_calendar():
    from core.economic_calendar import get_trading_constraints, get_upcoming_events

    days = int(request.args.get("days", "14"))
    days = max(1, min(days, 60))
    events = _run_async(get_upcoming_events(days_ahead=days))
    return jsonify({"events": events, "constraints": get_trading_constraints()})


@app.route("/api/portfolio/snapshot")
@login_required
def api_portfolio_snapshot():
    return jsonify(_portfolio_analytics().get_snapshot_sync())


@app.route("/api/portfolio/equity")
@login_required
def api_portfolio_equity():
    days = int(request.args.get("days", "30"))
    days = max(1, min(days, 720))
    pa = _portfolio_analytics()
    return jsonify({
        "portfolio": pa.get_equity_curve_sync(days),
        "benchmark": pa.get_benchmark_curve_sync(days, "SPY"),
        "benchmark_symbol": "SPY",
    })


@app.route("/api/portfolio/metrics")
@login_required
@require_portfolio_full
def api_portfolio_metrics():
    pa = _portfolio_analytics()
    snap = pa.get_snapshot_sync()
    trades_all = get_performance_tracker().all_trades()
    closed = [t for t in trades_all if t.get("exit_ts")]
    metrics = PortfolioAnalytics.calculate_metrics(closed)
    eq = pa.get_equity_curve_sync(120)

    def _pct_change(steps: int) -> Optional[float]:
        if len(eq) < 2:
            return None
        span = min(len(eq) - 1, max(1, steps))
        tail = eq[-(span + 1):]
        if len(tail) < 2:
            return None
        v0, v1 = tail[0]["value"], tail[-1]["value"]
        if v0 and v1:
            return round((v1 / v0 - 1) * 100.0, 3)
        return None

    returns_block = {
        "daily_pct": snap.get("daily_pnl_pct"),
        "weekly_pct": _pct_change(7),
        "monthly_pct": _pct_change(30),
        "all_time_pct": _pct_change(len(eq) - 1) if len(eq) > 2 else None,
    }
    return jsonify({"returns": returns_block, "risk": metrics, "snapshot": snap})


@app.route("/api/portfolio/correlation")
@login_required
@require_portfolio_advanced
def api_portfolio_correlation():
    pa = _portfolio_analytics()
    closes = pa.fetch_daily_closes_sync(32)
    matrix = pa.get_correlation_matrix(closes)
    first_len = len(next(iter(closes.values()), [])) if closes else 0
    return jsonify({"symbols": matrix, "closes_days": first_len})


@app.route("/api/portfolio/allocation")
@login_required
@require_portfolio_full
def api_portfolio_allocation():
    from core.rebalancer import PortfolioRebalancer, load_rebalancing_config

    tc, *_ = _alpaca_clients()
    rb = PortfolioRebalancer.from_yaml(tc or _trading_client, PORTFOLIO_YAML)
    drift = rb.check_drift_sync()
    pa = _portfolio_analytics()
    snap = pa.get_snapshot_sync()
    return jsonify({
        "drift": drift,
        "snapshot_allocation": snap.get("allocation"),
        "rebalancing_config": load_rebalancing_config(PORTFOLIO_YAML),
    })


@app.route("/api/portfolio/rebalance", methods=["POST"])
@login_required
@require_portfolio_advanced
def api_portfolio_rebalance():
    from core.rebalancer import PortfolioRebalancer

    tc, *_ = _alpaca_clients()
    data = request.get_json(silent=True) or {}
    dry = data.get("dry_run") if "dry_run" in data else True
    rb = PortfolioRebalancer.from_yaml(tc or _trading_client, PORTFOLIO_YAML)
    orders = rb.rebalance_sync(dry_run=bool(dry))
    return jsonify({"dry_run": bool(dry), "orders": orders})


@app.route("/api/portfolio/rebalancing", methods=["POST"])
@login_required
@require_portfolio_advanced
def api_portfolio_rebalancing_config():
    from core.rebalancer import load_rebalancing_config

    data = request.get_json(silent=True) or {}
    allowed: dict[str, Any] = {}
    for k in ("enabled", "auto_rebalance", "check_time", "max_drift_pct"):
        if k in data:
            allowed[k] = data[k]
    if "target_allocation" in data:
        allowed["target_allocation"] = {
            str(k): float(v) for k, v in (data["target_allocation"] or {}).items()
        }
    _merge_portfolio_rebalancing(allowed)
    return jsonify({
        "success": True,
        "rebalancing": load_rebalancing_config(PORTFOLIO_YAML),
    })


@app.route("/api/portfolio/trades")
@login_required
@require_portfolio_full
def api_portfolio_trades():
    page = int(request.args.get("page", "1"))
    per_page = int(request.args.get("per_page", "20"))
    per_page = max(5, min(per_page, 100))
    page = max(1, page)
    trades = get_performance_tracker().all_trades()
    closed = [t for t in trades if t.get("exit_ts")]
    total = len(closed)
    start = (page - 1) * per_page
    page_rows = closed[start:start + per_page]
    return jsonify({
        "total": total,
        "page": page,
        "per_page": per_page,
        "trades": page_rows,
    })


@app.route("/api/agent/<symbol>/dca", methods=["POST"])
@login_required
@require_dca_tier
def api_agent_dca(symbol):
    canonical = _url_to_symbol(symbol)
    if not canonical:
        return jsonify({"error": f"agent not found: {symbol}"}), 404
    gate = _agent_tier_gate(canonical)
    if gate is not None:
        return gate
    path = _config_path_for_symbol(canonical)
    data = request.get_json(silent=True) or {}
    if path:
        with open(path, encoding="utf-8") as f:
            doc = yaml.safe_load(f) or {}
        dca = dict(doc.get("dca") or {})
        for k in ("enabled", "interval", "amount", "max_position"):
            if k in data:
                dca[k] = data[k]
        _merge_root_yaml_fields(path, {"dca": dca})
        _bump_cfg_cache()
        return jsonify({"success": True, "symbol": canonical, "dca": dca})
    blob = _trading_blob_for_account()
    doc = None
    if blob:
        for d in saas_helpers.agents_list_from_blob(blob):
            if d.get("symbol") == canonical:
                doc = d
                break
    dca = dict((doc or {}).get("dca") or {})
    for k in ("enabled", "interval", "amount", "max_position"):
        if k in data:
            dca[k] = data[k]
    if _db_merge_agent_yaml_fields(canonical, {"dca": dca}):
        _bump_cfg_cache()
        return jsonify({"success": True, "symbol": canonical, "dca": dca})
    return jsonify({"error": "config not found"}), 404


@app.route("/api/agent/<symbol>/grid", methods=["POST"])
@login_required
@require_grid_tier
def api_agent_grid(symbol):
    canonical = _url_to_symbol(symbol)
    if not canonical:
        return jsonify({"error": f"agent not found: {symbol}"}), 404
    gate = _agent_tier_gate(canonical)
    if gate is not None:
        return gate
    path = _config_path_for_symbol(canonical)
    data = request.get_json(silent=True) or {}
    if path:
        with open(path, encoding="utf-8") as f:
            doc = yaml.safe_load(f) or {}
        grid = dict(doc.get("grid") or {})
        for k in ("enabled", "upper_price", "lower_price", "grid_lines", "amount_per_grid", "trailing_exit"):
            if k in data:
                grid[k] = data[k]
        _merge_root_yaml_fields(path, {"grid": grid})
        _bump_cfg_cache()
        return jsonify({"success": True, "symbol": canonical, "grid": grid})
    blob = _trading_blob_for_account()
    doc = None
    if blob:
        for d in saas_helpers.agents_list_from_blob(blob):
            if d.get("symbol") == canonical:
                doc = d
                break
    grid = dict((doc or {}).get("grid") or {})
    for k in ("enabled", "upper_price", "lower_price", "grid_lines", "amount_per_grid", "trailing_exit"):
        if k in data:
            grid[k] = data[k]
    if _db_merge_agent_yaml_fields(canonical, {"grid": grid}):
        _bump_cfg_cache()
        return jsonify({"success": True, "symbol": canonical, "grid": grid})
    return jsonify({"error": "config not found"}), 404


@app.route("/api/agent/<symbol>/advanced", methods=["POST"])
@login_required
@require_tier(TIER_PRO)
def api_agent_advanced(symbol):
    canonical = _url_to_symbol(symbol)
    if not canonical:
        return jsonify({"error": f"agent not found: {symbol}"}), 404
    gate = _agent_tier_gate(canonical)
    if gate is not None:
        return gate
    data = request.get_json(silent=True) or {}
    updates: dict[str, Any] = {}
    if "take_profit" in data:
        updates["take_profit"] = data["take_profit"]
    if "scheduled_orders" in data:
        updates["scheduled_orders"] = data["scheduled_orders"]
    if not updates:
        return jsonify({"error": "no updates"}), 400
    path = _config_path_for_symbol(canonical)
    if path:
        _merge_root_yaml_fields(path, updates)
        _bump_cfg_cache()
        return jsonify({"success": True, "symbol": canonical, **updates})
    if _db_merge_agent_yaml_fields(canonical, updates):
        _bump_cfg_cache()
        return jsonify({"success": True, "symbol": canonical, **updates})
    return jsonify({"error": "config not found"}), 404


# ── Stripe billing ───────────────────────────────────────────────────────────


def _stripe_webhook_request():
    if db.SessionLocal is None:
        return jsonify({"error": "database unavailable"}), 503
    payload = request.get_data(cache=False, as_text=False)
    sig = request.headers.get("Stripe-Signature")
    sess = db.db_session()
    body, code = stripe_billing.handle_webhook(sess, payload, sig)
    return jsonify(body), code


@app.route("/webhook/stripe", methods=["POST"])
@limiter.exempt
def stripe_webhook():
    return _stripe_webhook_request()


@app.route("/api/stripe/webhook", methods=["POST"])
@limiter.exempt
def stripe_webhook_api_path():
    return _stripe_webhook_request()


@app.route("/api/stripe/create-checkout-session", methods=["POST"])
@login_required
def api_stripe_create_checkout_session():
    if db.SessionLocal is None:
        return jsonify({"error": "database unavailable"}), 503
    _resolve_identity()
    u = getattr(g, "db_user", None)
    if u is None or getattr(g, "auth_kind", None) != "db":
        return jsonify({"error": "Subscription billing requires a registered account."}), 400
    data = request.get_json(silent=True) or {}
    tier = str(data.get("tier") or "pro").strip().lower()
    billing = str(data.get("billing") or "monthly").strip().lower()
    price_id = (data.get("price_id") or "").strip() or None
    sess = db.db_session()
    try:
        stripe_billing.configure_stripe()
        url = stripe_billing.create_eur_checkout_session(
            sess, u, tier=tier, billing=billing, price_id=price_id,
        )
        sess.commit()
        return jsonify({"checkout_url": url})
    except ValueError as exc:
        sess.rollback()
        return jsonify({"error": str(exc)}), 400
    except RuntimeError as exc:
        sess.rollback()
        return jsonify({"error": str(exc)}), 503
    except Exception:  # noqa: BLE001
        sess.rollback()
        log.exception("stripe create checkout session")
        return jsonify({"error": "Checkout failed."}), 500


@app.route("/api/stripe/create-portal-session", methods=["POST"])
@login_required
def api_stripe_create_portal_session():
    if db.SessionLocal is None:
        return jsonify({"error": "database unavailable"}), 503
    _resolve_identity()
    u = getattr(g, "db_user", None)
    if u is None or getattr(g, "auth_kind", None) != "db":
        return jsonify({"error": "Subscription billing requires a registered account."}), 400
    sess = db.db_session()
    base = (os.getenv("DASHBOARD_PUBLIC_BASE_URL") or "https://app.letagentscook.lol").strip().rstrip("/")
    return_url = f"{base}/?page=settings"
    try:
        stripe_billing.configure_stripe()
        url = stripe_billing.create_customer_portal_session(sess, u, return_url=return_url)
        sess.commit()
        return jsonify({"portal_url": url})
    except ValueError as exc:
        sess.rollback()
        return jsonify({"error": str(exc)}), 400
    except Exception:  # noqa: BLE001
        sess.rollback()
        log.exception("stripe portal session")
        return jsonify({"error": "Could not open billing portal."}), 500


@app.route("/api/billing/checkout", methods=["POST"])
@login_required
def api_billing_checkout():
    if db.SessionLocal is None:
        return jsonify({"error": "database unavailable"}), 503
    _resolve_identity()
    u = getattr(g, "db_user", None)
    if u is None or getattr(g, "auth_kind", None) != "db":
        return jsonify({"error": "Subscription billing requires a registered account."}), 400
    data = request.get_json(silent=True) or {}
    tier = str(data.get("tier") or "").strip().lower()
    sess = db.db_session()
    try:
        stripe_billing.configure_stripe()
        url = stripe_billing.create_checkout_session(sess, u, tier)
        sess.commit()
        return jsonify({"url": url})
    except ValueError as exc:
        sess.rollback()
        return jsonify({"error": str(exc)}), 400
    except RuntimeError as exc:
        sess.rollback()
        return jsonify({"error": str(exc)}), 503
    except Exception:  # noqa: BLE001
        sess.rollback()
        log.exception("billing checkout")
        return jsonify({"error": "Checkout failed."}), 500


@app.route("/api/billing/portal", methods=["GET"])
@login_required
def api_billing_portal():
    if db.SessionLocal is None:
        return jsonify({"error": "database unavailable"}), 503
    _resolve_identity()
    u = getattr(g, "db_user", None)
    if u is None or getattr(g, "auth_kind", None) != "db":
        return jsonify({"error": "Subscription billing requires a registered account."}), 400
    sess = db.db_session()
    try:
        stripe_billing.configure_stripe()
        url = stripe_billing.create_customer_portal_session(sess, u)
        sess.commit()
        return jsonify({"url": url})
    except ValueError as exc:
        sess.rollback()
        return jsonify({"error": str(exc)}), 400
    except Exception:  # noqa: BLE001
        sess.rollback()
        log.exception("billing portal")
        return jsonify({"error": "Could not open billing portal."}), 500


@app.route("/api/billing/cancel", methods=["POST"])
@login_required
def api_billing_cancel():
    if db.SessionLocal is None:
        return jsonify({"error": "database unavailable"}), 503
    _resolve_identity()
    u = getattr(g, "db_user", None)
    if u is None or getattr(g, "auth_kind", None) != "db":
        return jsonify({"error": "Subscription billing requires a registered account."}), 400
    sess = db.db_session()
    try:
        stripe_billing.configure_stripe()
        stripe_billing.cancel_subscription_at_period_end(sess, u)
        sess.commit()
        return jsonify({"success": True})
    except ValueError as exc:
        sess.rollback()
        return jsonify({"error": str(exc)}), 400
    except Exception:  # noqa: BLE001
        sess.rollback()
        log.exception("billing cancel")
        return jsonify({"error": "Could not cancel subscription."}), 500


@app.route("/api/billing/status", methods=["GET"])
@login_required
def api_billing_status():
    if db.SessionLocal is None:
        return jsonify({"error": "database unavailable"}), 503
    _resolve_identity()
    u = getattr(g, "db_user", None)
    if u is None or getattr(g, "auth_kind", None) != "db":
        return jsonify({"error": "Subscription billing requires a registered account."}), 400
    sess = db.db_session()
    try:
        stripe_billing.configure_stripe()
        return jsonify(stripe_billing.get_subscription_status(sess, u))
    except Exception:  # noqa: BLE001
        log.exception("billing status")
        return jsonify({"error": "Could not load billing status."}), 500


def _marketplace_db_user():
    _resolve_identity()
    u = getattr(g, "db_user", None)
    if u is None or getattr(g, "auth_kind", None) != "db":
        return None
    return u


def _serialize_row_dt(d: dict) -> dict:
    out = {}
    for k, v in d.items():
        if hasattr(v, "isoformat"):
            out[k] = v.isoformat()
        elif isinstance(v, Decimal):
            out[k] = float(v)
        else:
            out[k] = v
    return out


def _leaderboard_cache_stale(max_updated: object) -> bool:
    if max_updated is None:
        return True
    mx = max_updated
    if getattr(mx, "tzinfo", None) is None:
        mx = mx.replace(tzinfo=timezone.utc)
    return mx < datetime.now(timezone.utc) - timedelta(hours=6)


@app.route("/api/leaderboard", methods=["GET"])
def get_leaderboard():
    period = (request.args.get("period") or "weekly").strip()
    if period not in ("weekly", "monthly", "alltime"):
        period = "weekly"
    eng = db.get_engine()
    if eng is None:
        return jsonify({"error": "database unavailable"}), 503

    _resolve_identity()
    user_id: int | None = None
    if getattr(g, "auth_kind", None) == "db" and getattr(g, "db_user", None):
        user_id = int(g.db_user.id)

    subscribed_ids: set[str] = set()
    if user_id is not None:
        with eng.connect() as conn:
            for row in conn.execute(
                text(
                    "SELECT agent_id FROM user_subscriptions WHERE user_id = :u AND is_active IS TRUE"
                ),
                {"u": user_id},
            ).fetchall():
                subscribed_ids.add(str(row[0]))

    with eng.begin() as conn:
        last = conn.execute(
            text("SELECT refreshed_at FROM leaderboard_cache_meta WHERE id = 1")
        ).scalar()
        if _leaderboard_cache_stale(last):
            compute_leaderboard_cache(conn)

    lb_rows: list[dict] = []
    updated_at_iso: str | None = None
    with eng.connect() as conn:
        mx2 = conn.execute(
            text("SELECT MAX(updated_at) FROM agent_leaderboard_cache WHERE period = :p"),
            {"p": period},
        ).scalar()
        if mx2 is not None:
            u_at = mx2
            if getattr(u_at, "tzinfo", None) is None:
                u_at = u_at.replace(tzinfo=timezone.utc)
            updated_at_iso = u_at.isoformat()
        else:
            mr = conn.execute(
                text("SELECT refreshed_at FROM leaderboard_cache_meta WHERE id = 1")
            ).scalar()
            if mr is not None:
                u_at = mr
                if getattr(u_at, "tzinfo", None) is None:
                    u_at = u_at.replace(tzinfo=timezone.utc)
                updated_at_iso = u_at.isoformat()
        for r in conn.execute(
            text("""
                SELECT c.rank, c.agent_id, ta.name, ta.symbol, ta.category,
                       c.pnl_pct, c.pnl_usd, c.win_rate, c.trade_count, c.subscriber_count
                FROM agent_leaderboard_cache c
                JOIN trading_agents ta ON ta.id = c.agent_id
                WHERE c.period = :p
                ORDER BY c.rank
                LIMIT 20
            """),
            {"p": period},
        ).mappings():
            aid = str(r["agent_id"])
            lb_rows.append(
                {
                    "rank": int(r["rank"]),
                    "agent_id": aid,
                    "name": r["name"],
                    "symbol": r["symbol"],
                    "category": r["category"],
                    "pnl_pct": float(r["pnl_pct"] or 0),
                    "pnl_usd": float(r["pnl_usd"] or 0),
                    "win_rate": float(r["win_rate"] or 0),
                    "trade_count": int(r["trade_count"] or 0),
                    "subscriber_count": int(r["subscriber_count"] or 0),
                    "is_subscribed": aid in subscribed_ids,
                }
            )

    return jsonify({"period": period, "updated_at": updated_at_iso, "leaderboard": lb_rows})


@app.route("/api/leaderboard/refresh", methods=["POST"])
@login_required
def refresh_leaderboard():
    _resolve_identity()
    u = getattr(g, "db_user", None)
    if u is None or not bool(u.is_admin):
        return jsonify({"error": "forbidden"}), 403
    eng = db.get_engine()
    if eng is None:
        return jsonify({"error": "database unavailable"}), 503
    try:
        with eng.begin() as conn:
            n = compute_leaderboard_cache(conn)
    except Exception as exc:  # noqa: BLE001
        log.exception("leaderboard refresh")
        return jsonify({"error": str(exc)}), 500
    return jsonify({"ok": True, "updated": n})


def _paper_agg_for_share(
    sess,
    user_id: int,
    *,
    agent_id: str | None,
    user_agent_id: int | None,
    days: int,
) -> dict[str, float]:
    if agent_id:
        clause = "pt.agent_id = :aid AND (pt.user_agent_id IS NULL)"
        params: dict[str, Any] = {"uid": user_id, "aid": str(agent_id), "days": int(days)}
    elif user_agent_id is not None:
        clause = "pt.user_agent_id = :uaid"
        params = {"uid": user_id, "uaid": int(user_agent_id), "days": int(days)}
    else:
        return {"sum_pnl": 0.0, "n": 0.0, "wins": 0.0}
    row = sess.execute(
        text(f"""
        SELECT
          COALESCE(SUM(pt.pnl), 0)::double precision AS sum_pnl,
          COUNT(*)::int AS n,
          COALESCE(SUM(CASE WHEN pt.pnl > 0 THEN 1 ELSE 0 END), 0)::int AS wins
        FROM paper_trades pt
        WHERE pt.user_id = :uid AND {clause}
          AND pt.timestamp >= (CURRENT_TIMESTAMP AT TIME ZONE 'UTC')
              - (CAST(:days AS text) || ' days')::interval
        """),
        params,
    ).mappings().first()
    if not row:
        return {"sum_pnl": 0.0, "n": 0.0, "wins": 0.0}
    return {
        "sum_pnl": float(row["sum_pnl"] or 0),
        "n": float(row["n"] or 0),
        "wins": float(row["wins"] or 0),
    }


@app.route("/api/sharing/referral-info", methods=["GET"])
@login_required
def api_sharing_referral_info():
    if db.SessionLocal is None:
        return jsonify({"error": "database unavailable"}), 503
    u = _marketplace_db_user()
    if u is None:
        return jsonify({"error": "Vyžaduje sa účet."}), 403
    sess = db.db_session()
    try:
        dbu = sess.get(User, u.id)
        if dbu is None:
            return jsonify({"error": "Účet nenájdený."}), 403
        payload = referral_info_for_user(sess, dbu, dash_config.APP_URL)
        sess.commit()
    except Exception:  # noqa: BLE001
        sess.rollback()
        log.exception("referral-info")
        return jsonify({"error": "Nepodarilo sa načítať referral."}), 500
    finally:
        sess.close()
        db.remove_scoped_session()
    return jsonify(payload)


@app.route("/api/sharing/track-referral", methods=["POST"])
@login_required
def api_sharing_track_referral():
    if db.SessionLocal is None:
        return jsonify({"error": "database unavailable"}), 503
    u = _marketplace_db_user()
    if u is None:
        return jsonify({"error": "Vyžaduje sa účet."}), 403
    data = request.get_json(silent=True) or {}
    code = (data.get("referral_code") or "").strip()
    sess = db.db_session()
    try:
        dbu = sess.get(User, u.id)
        if dbu is None:
            return jsonify({"success": False, "error": "Účet nenájdený."}), 403
        out = apply_referral_tracking(sess, dbu, code)
        try_grant_referral_first_login(sess, dbu)
        sess.commit()
    except Exception:  # noqa: BLE001
        sess.rollback()
        log.exception("track-referral")
        return jsonify({"success": False, "error": "Server error"}), 500
    finally:
        sess.close()
        db.remove_scoped_session()
    return jsonify({"success": True, "referrer_name": out.get("referrer_name")})


@app.route("/api/sharing/grant-referral-bonus", methods=["POST"])
@login_required
def api_sharing_grant_referral_bonus():
    if db.SessionLocal is None:
        return jsonify({"error": "database unavailable"}), 503
    u = _marketplace_db_user()
    if u is None:
        return jsonify({"error": "Vyžaduje sa účet."}), 403
    sess = db.db_session()
    try:
        u2 = sess.get(User, u.id)
        if u2:
            try_grant_referral_first_login(sess, u2)
        sess.commit()
    except Exception:  # noqa: BLE001
        sess.rollback()
        log.exception("grant-referral-bonus")
        return jsonify({"success": False, "error": "Server error"}), 500
    finally:
        sess.close()
        db.remove_scoped_session()
    return jsonify({"success": True})


@app.route("/api/sharing/performance-card/<path:agent_id>", methods=["GET"])
@login_required
def api_sharing_performance_card(agent_id: str):
    if db.SessionLocal is None:
        return jsonify({"error": "database unavailable"}), 503
    u = _marketplace_db_user()
    if u is None:
        return jsonify({"error": "Vyžaduje sa účet."}), 403
    sess = db.db_session()
    try:
        uid = int(u.id)
        dbu = sess.get(User, uid)
        if dbu is None:
            return jsonify({"error": "Účet nenájdený."}), 403
        share_type = (request.args.get("type") or "trading_agent").strip().lower()
        if share_type == "leaderboard":
            share_type = "trading_agent"
        base = dash_config.APP_URL.rstrip("/")
        show_wm = normalize_tier(effective_tier(dbu)) == TIER_BASIC

        if share_type == "user_agent":
            try:
                uaid = int(str(agent_id).strip())
            except (TypeError, ValueError):
                return jsonify({"error": "Neplatný agent."}), 400
            row = sess.execute(
                text("""
                SELECT id, name, symbol, strategy_type, status
                FROM user_agents
                WHERE id = :id AND user_id = :uid AND status != 'deleted'
                LIMIT 1
                """),
                {"id": uaid, "uid": uid},
            ).mappings().first()
            if not row:
                return jsonify({"error": "Agent neexistuje."}), 404
            name = str(row["name"] or "")
            symbol = str(row["symbol"] or "—")
            st_key = str(row["strategy_type"] or "")
            strategy = STRATEGY_LABELS.get(st_key, st_key or "—")
            wk = _paper_agg_for_share(sess, uid, agent_id=None, user_agent_id=uaid, days=7)
            mo = _paper_agg_for_share(sess, uid, agent_id=None, user_agent_id=uaid, days=30)
            lb_rank = None
            badge_el = None
        else:
            aid = str(agent_id).strip()[:64]
            sub = sess.execute(
                text("""
                SELECT 1 FROM user_subscriptions
                WHERE user_id = :u AND agent_id = :a AND is_active IS TRUE
                LIMIT 1
                """),
                {"u": uid, "a": aid},
            ).first()
            if not sub:
                return jsonify({"error": "Nie si prihlásený k tomuto agentovi."}), 403
            ta = sess.execute(
                text("SELECT id, name, symbol, strategy FROM trading_agents WHERE id = :a LIMIT 1"),
                {"a": aid},
            ).mappings().first()
            if not ta:
                return jsonify({"error": "Agent neexistuje."}), 404
            name = str(ta["name"] or "")
            symbol = str(ta["symbol"] or "—")
            strategy = str(ta["strategy"] or "—")
            wk = _paper_agg_for_share(sess, uid, agent_id=aid, user_agent_id=None, days=7)
            mo = _paper_agg_for_share(sess, uid, agent_id=aid, user_agent_id=None, days=30)
            rk = sess.execute(
                text("""
                SELECT rank FROM agent_leaderboard_cache
                WHERE period = 'weekly' AND agent_id = :a AND rank <= 20
                LIMIT 1
                """),
                {"a": aid},
            ).scalar()
            lb_rank = int(rk) if rk is not None else None
            bmap = compute_user_badges_map(sess, uid)
            bids = bmap.get(aid, [])
            badge_el = None
            if bids:
                b0 = bids[0]
                meta = BADGE_DEFINITIONS.get(b0)
                if meta:
                    badge_el = {"key": b0, "label": meta.get("label", b0), "icon": meta.get("icon", "")}

        nw = int(wk["n"])
        wins = int(wk["wins"])
        win_rate = round((wins / nw * 100.0), 1) if nw > 0 else 0.0
        pnl_usd_w = round(float(wk["sum_pnl"]), 2)
        pnl_pct_w = round((pnl_usd_w / PNL_BASELINE_USD) * 100.0, 2) if PNL_BASELINE_USD else 0.0
        pnl_usd_m = round(float(mo["sum_pnl"]), 2)
        pnl_pct_m = round((pnl_usd_m / PNL_BASELINE_USD) * 100.0, 2) if PNL_BASELINE_USD else 0.0

        out = {
            "agent_name": name,
            "symbol": symbol,
            "strategy": strategy,
            "pnl_pct_week": pnl_pct_w,
            "pnl_pct_month": pnl_pct_m,
            "pnl_usd_week": pnl_usd_w,
            "win_rate": win_rate,
            "trade_count": nw,
            "badge": badge_el,
            "leaderboard_rank": lb_rank,
            "show_watermark": show_wm,
            "app_url": base,
        }
    except Exception:  # noqa: BLE001
        log.exception("performance-card")
        return jsonify({"error": "Nepodarilo sa načítať kartu."}), 500
    finally:
        sess.close()
        db.remove_scoped_session()
    return jsonify(out)


@app.route("/api/trades/history", methods=["GET"])
@login_required
def get_trade_history():
    _resolve_identity()
    if getattr(g, "auth_kind", None) != "db" or not getattr(g, "db_user", None):
        return jsonify({"error": "A registered account is required."}), 400
    if db.SessionLocal is None:
        return jsonify({"error": "database unavailable"}), 503
    agent_id = (request.args.get("agent_id") or "").strip() or None
    try:
        limit = min(max(1, int(request.args.get("limit", 20))), 100)
    except (TypeError, ValueError):
        limit = 20
    uid = int(g.db_user.id)
    sess = db.db_session()

    def _norm_signals(val: object) -> dict:
        if val is None:
            return {}
        if isinstance(val, dict):
            return val
        if isinstance(val, str):
            try:
                return json.loads(val)
            except json.JSONDecodeError:
                return {}
        return {}

    try:
        rows = sess.execute(
            text("""
                SELECT
                    pt.id, pt.agent_id, ta.name AS agent_name, pt.symbol, pt.action,
                    pt.price, pt.quantity, pt.pnl, pt.timestamp,
                    pt.reason, pt.signals AS pt_signals, pt.confidence,
                    te.explanation AS te_explanation, te.signals AS te_signals
                FROM paper_trades pt
                JOIN trading_agents ta ON ta.id = pt.agent_id
                LEFT JOIN LATERAL (
                    SELECT explanation, signals
                    FROM trade_explanations
                    WHERE trade_id = pt.id
                    ORDER BY generated_at DESC
                    LIMIT 1
                ) te ON true
                WHERE pt.user_id = :uid
                  AND (:aid IS NULL OR pt.agent_id = :aid)
                ORDER BY pt.timestamp DESC NULLS LAST, pt.id DESC
                LIMIT :lim
            """),
            {"uid": uid, "aid": agent_id, "lim": limit},
        ).mappings().all()
    except Exception:  # noqa: BLE001
        log.exception("trade history")
        return jsonify({"error": "Could not load trade history."}), 500

    trades_out: list[dict] = []
    for r in rows:
        ts = r.get("timestamp")
        if ts is not None and hasattr(ts, "isoformat"):
            ts_s = ts.isoformat()
            if str(ts_s).endswith("+00:00"):
                ts_s = str(ts_s).replace("+00:00", "Z")
        else:
            ts_s = None
        sig = _norm_signals(r.get("pt_signals"))
        if not sig:
            sig = _norm_signals(r.get("te_signals"))
        reason = r.get("reason")
        if not reason:
            reason = r.get("te_explanation")
        conf_raw = r.get("confidence")
        conf_f = float(conf_raw) if conf_raw is not None else 0.0
        trades_out.append(
            {
                "id": int(r["id"]),
                "agent_id": str(r["agent_id"]),
                "agent_name": r["agent_name"],
                "symbol": r["symbol"],
                "action": str(r["action"] or "").lower(),
                "price": float(r["price"] or 0),
                "quantity": float(r["quantity"] or 0),
                "pnl": float(r["pnl"] or 0),
                "timestamp": ts_s,
                "reason": reason,
                "signals": sig,
                "confidence": round(conf_f, 4),
            }
        )

    return jsonify({"trades": trades_out})


@app.route("/api/marketplace/agents", methods=["GET"])
@login_required
def api_marketplace_agents():
    if db.SessionLocal is None:
        return jsonify({"error": "database unavailable"}), 503
    u = _marketplace_db_user()
    if u is None:
        return jsonify({"error": "Marketplace requires a registered account."}), 403
    category = request.args.get("category", "all")
    feats = features_payload(u)
    tier_key = normalize_tier(feats.get("tier", "basic"))
    agents_raw = get_all_agents(category=category, tier_filter=tier_key)
    subscribed_ids = [s["agent_id"] for s in get_user_subscriptions(u.id)]
    subscribed_set = set(subscribed_ids)
    ut = normalize_tier(feats.get("tier", "basic"))
    agents = []
    for raw in agents_raw:
        a = dict(raw)
        a["subscribed"] = a["id"] in subscribed_set
        a["locked"] = TIER_RANK.get(normalize_tier(a.get("min_tier")), 0) > TIER_RANK.get(ut, 0)
        agents.append(_serialize_row_dt(a))
    return jsonify(
        {
            "agents": agents,
            "subscribed_count": len(subscribed_ids),
            "limit": feats.get("agents_limit"),
        }
    )


@app.route("/api/marketplace/subscribe", methods=["POST"])
@login_required
def api_marketplace_subscribe():
    if db.SessionLocal is None:
        return jsonify({"error": "database unavailable"}), 503
    u = _marketplace_db_user()
    if u is None:
        return jsonify({"error": "Marketplace requires a registered account."}), 403
    data = request.get_json(silent=True) or {}
    result = subscribe_agent(u.id, data.get("agent_id"), data.get("mode", "paper"))
    if result.get("upgrade_required"):
        return jsonify(result), 403
    return jsonify(result), (200 if result.get("success") else 400)


@app.route("/api/marketplace/unsubscribe", methods=["POST"])
@login_required
def api_marketplace_unsubscribe():
    if db.SessionLocal is None:
        return jsonify({"error": "database unavailable"}), 503
    u = _marketplace_db_user()
    if u is None:
        return jsonify({"error": "Marketplace requires a registered account."}), 403
    data = request.get_json(silent=True) or {}
    result = unsubscribe_agent(u.id, data.get("agent_id"))
    return jsonify(result)


@app.route("/api/marketplace/my-agents", methods=["GET"])
@login_required
def api_marketplace_my_agents():
    if db.SessionLocal is None:
        return jsonify({"error": "database unavailable"}), 503
    u = _marketplace_db_user()
    if u is None:
        return jsonify({"error": "Marketplace requires a registered account."}), 403
    subs = get_user_subscriptions(u.id)
    pnl = get_user_pnl(u.id)
    return jsonify(
        {
            "subscriptions": [_serialize_row_dt(dict(s)) for s in subs],
            "pnl": [_serialize_row_dt(dict(p)) for p in pnl],
        }
    )


@app.route("/api/marketplace/slots", methods=["GET"])
@login_required
def api_marketplace_slots():
    if db.SessionLocal is None:
        return jsonify({"error": "database unavailable"}), 503
    u = _marketplace_db_user()
    if u is None:
        return jsonify({"error": "Marketplace requires a registered account."}), 403
    return jsonify(get_marketplace_slots(u))


def _community_marketplace_user():
    _resolve_identity()
    if getattr(g, "auth_kind", None) != "db":
        return None
    return getattr(g, "db_user", None)


def _community_tier(user: Any) -> str:
    return normalize_tier(effective_tier(user)) if user is not None else TIER_BASIC


@app.route("/api/community/agents", methods=["GET"])
@login_required
def get_community_agents():
    if db.SessionLocal is None:
        return jsonify({"error": "database unavailable"}), 503
    user = _community_marketplace_user()
    if user is None:
        return jsonify({"error": "registered account required"}), 403

    category = (request.args.get("category", "all") or "all").strip().lower()
    sort = (request.args.get("sort", "newest") or "newest").strip().lower()
    allowed_categories = {"all", "crypto", "stocks", "commodities"}
    if category not in allowed_categories:
        category = "all"
    order = {
        "newest": "ca.created_at DESC",
        "top": "ca.win_rate DESC",
        "popular": "ca.subscribers DESC",
    }.get(sort, "ca.created_at DESC")
    params: dict[str, Any] = {}
    where_parts = ["ca.status = 'approved'"]
    if category != "all":
        where_parts.append("LOWER(ca.category) = :cat")
        params["cat"] = category
    where_sql = " AND ".join(where_parts)

    sess = db.db_session()
    try:
        rows = sess.execute(
            text(
                f"""
                SELECT ca.*,
                       u.username AS author_handle,
                       u.tier AS author_tier
                FROM community_agents ca
                JOIN users u ON u.id = ca.user_id
                WHERE {where_sql}
                ORDER BY {order}
                LIMIT 50
                """
            ),
            params,
        ).mappings().all()
        return jsonify([_serialize_row_dt(dict(r)) for r in rows])
    except Exception:  # noqa: BLE001
        log.exception("community agents list")
        return jsonify({"error": "failed to load community agents"}), 500
    finally:
        sess.close()


def _submit_community_agent_impl():
    if db.SessionLocal is None:
        return jsonify({"error": "database unavailable"}), 503
    user = _community_marketplace_user()
    if user is None:
        return jsonify({"error": "registered account required"}), 403
    if _community_tier(user) not in (TIER_PRO, TIER_ELITE, TIER_ADMIN):
        return jsonify({"error": "Pro or Elite tier required"}), 403

    data = request.get_json(silent=True) or {}
    name = str(data.get("name") or "").strip()[:100]
    symbol = str(data.get("symbol") or "").strip()[:20]
    category = str(data.get("category") or "crypto").strip().lower()[:20] or "crypto"
    strategy = str(data.get("strategy") or "").strip()[:50]
    risk_level = str(data.get("risk_level") or "medium").strip().lower()[:20] or "medium"
    description = str(data.get("description") or "").strip()[:1000]
    try:
        price = float(data.get("price_monthly", 0) or 0)
    except (TypeError, ValueError):
        return jsonify({"error": "invalid price_monthly"}), 400
    if not name or not symbol or not strategy:
        return jsonify({"error": "name, symbol and strategy required"}), 400
    if category not in ("crypto", "stocks", "commodities"):
        return jsonify({"error": "invalid category"}), 400
    if risk_level not in ("low", "medium", "high"):
        return jsonify({"error": "invalid risk_level"}), 400
    if price < 0 or price > 99:
        return jsonify({"error": "price_monthly must be between 0 and 99"}), 400

    sess = db.db_session()
    try:
        sess.execute(
            text(
                """
                INSERT INTO community_agents
                  (user_id, name, symbol, category, strategy, risk_level, description, price_monthly)
                VALUES
                  (:uid, :name, :sym, :cat, :strat, :risk, :desc, :price)
                """
            ),
            {
                "uid": int(user.id),
                "name": name,
                "sym": symbol,
                "cat": category,
                "strat": strategy,
                "risk": risk_level,
                "desc": description,
                "price": price,
            },
        )
        sess.commit()
        return jsonify({"status": "submitted", "message": "Agent submitted for review"})
    except Exception:  # noqa: BLE001
        sess.rollback()
        log.exception("community submit agent")
        return jsonify({"error": "submission failed"}), 500
    finally:
        sess.close()


@app.route("/api/community/agents", methods=["POST"])
@login_required
def submit_community_agent():
    return _submit_community_agent_impl()


@app.route("/api/community/my-agents", methods=["POST"])
@login_required
def submit_community_agent_alias():
    return _submit_community_agent_impl()


@app.route("/api/community/my-agents", methods=["GET"])
@login_required
def my_community_agents():
    if db.SessionLocal is None:
        return jsonify({"error": "database unavailable"}), 503
    user = _community_marketplace_user()
    if user is None:
        return jsonify({"error": "registered account required"}), 403
    sess = db.db_session()
    try:
        rows = sess.execute(
            text(
                """
                SELECT *
                FROM community_agents
                WHERE user_id = :uid
                ORDER BY created_at DESC
                """
            ),
            {"uid": int(user.id)},
        ).mappings().all()
        return jsonify([_serialize_row_dt(dict(r)) for r in rows])
    except Exception:  # noqa: BLE001
        log.exception("my community agents")
        return jsonify({"error": "failed to load submissions"}), 500
    finally:
        sess.close()


@app.route("/api/admin/community/agents/<int:agent_id>/review", methods=["POST"])
@login_required
def review_community_agent(agent_id: int):
    if db.SessionLocal is None:
        return jsonify({"error": "database unavailable"}), 503
    user = _community_marketplace_user()
    if user is None or _community_tier(user) != TIER_ADMIN:
        return jsonify({"error": "Admin only"}), 403
    body = request.get_json(silent=True) or {}
    action = str(body.get("action") or "").strip().lower()
    reason = str(body.get("reason") or "").strip()[:1000]
    if action not in ("approve", "reject"):
        return jsonify({"error": "action must be approve or reject"}), 400
    if action == "reject" and not reason:
        return jsonify({"error": "reason is required for reject"}), 400

    sess = db.db_session()
    try:
        if action == "approve":
            row = sess.execute(
                text(
                    """
                    UPDATE community_agents
                    SET status = 'approved',
                        reject_reason = NULL,
                        approved_at = NOW()
                    WHERE id = :id AND status = 'pending'
                    RETURNING id
                    """
                ),
                {"id": int(agent_id)},
            ).first()
        else:
            row = sess.execute(
                text(
                    """
                    UPDATE community_agents
                    SET status = 'rejected',
                        reject_reason = :reason
                    WHERE id = :id AND status = 'pending'
                    RETURNING id
                    """
                ),
                {"id": int(agent_id), "reason": reason},
            ).first()
        if row is None:
            sess.rollback()
            return jsonify({"error": "pending community agent not found"}), 404
        sess.commit()
        return jsonify({"status": "ok"})
    except Exception:  # noqa: BLE001
        sess.rollback()
        log.exception("review community agent")
        return jsonify({"error": "review failed"}), 500
    finally:
        sess.close()


@app.route("/api/admin/community/agents/pending", methods=["GET"])
@login_required
def pending_community_agents():
    if db.SessionLocal is None:
        return jsonify({"error": "database unavailable"}), 503
    user = _community_marketplace_user()
    if user is None or _community_tier(user) != TIER_ADMIN:
        return jsonify({"error": "Admin only"}), 403
    sess = db.db_session()
    try:
        rows = sess.execute(
            text(
                """
                SELECT ca.*, u.username AS handle, u.email
                FROM community_agents ca
                JOIN users u ON u.id = ca.user_id
                WHERE ca.status = 'pending'
                ORDER BY ca.created_at ASC
                """
            )
        ).mappings().all()
        return jsonify([_serialize_row_dt(dict(r)) for r in rows])
    except Exception:  # noqa: BLE001
        log.exception("pending community agents")
        return jsonify({"error": "failed to load pending list"}), 500
    finally:
        sess.close()


def _coerce_jsonb_mapping(val: Any) -> dict[str, Any]:
    if isinstance(val, dict):
        return val
    if isinstance(val, str) and val.strip():
        try:
            return json.loads(val)
        except json.JSONDecodeError:
            return {}
    return {}


def _backtest_load_agent_and_symbol(
    conn: Any, user_id: int, agent_type: str, agent_id: Any
) -> tuple[str, dict[str, Any]]:
    at = (agent_type or "").strip().lower()
    if at == "user":
        try:
            uaid = int(agent_id)
        except (TypeError, ValueError) as exc:
            raise ValueError("Neplatné user agent ID.") from exc
        row = conn.execute(
            text("""
                SELECT symbol, strategy_type, config_json
                FROM user_agents
                WHERE id = :id AND user_id = :uid
            """),
            {"id": uaid, "uid": int(user_id)},
        ).mappings().first()
        if not row:
            raise ValueError("Vlastný agent neexistuje.")
        cfg = agent_config_from_row_user(
            row["strategy_type"], _coerce_jsonb_mapping(row["config_json"])
        )
        return str(row["symbol"]), cfg
    if at == "system":
        tid = str(agent_id).strip()
        row = conn.execute(
            text("SELECT symbol, strategy FROM trading_agents WHERE id = :id"),
            {"id": tid},
        ).mappings().first()
        if not row:
            raise ValueError("Marketplace agent neexistuje.")
        return str(row["symbol"]), agent_config_from_row_system(row.get("strategy"))
    raise ValueError("agent_type musí byť user alebo system.")


@app.route("/api/backtest/limits", methods=["GET"])
@login_required
def api_backtest_limits():
    if db.SessionLocal is None:
        return jsonify({"error": "database unavailable"}), 503
    u = _marketplace_db_user()
    if u is None:
        return jsonify({"error": "Vyžaduje sa registrovaný účet."}), 400
    return jsonify(backtest_limits_payload(effective_tier(u)))


@app.route("/api/backtest/history", methods=["GET"])
@login_required
def api_backtest_history():
    if db.SessionLocal is None:
        return jsonify({"error": "database unavailable"}), 503
    u = _marketplace_db_user()
    if u is None:
        return jsonify({"error": "Vyžaduje sa registrovaný účet."}), 400
    eng = db.get_engine()
    if eng is None:
        return jsonify({"error": "database unavailable"}), 503
    result_id_raw = request.args.get("id")
    with eng.connect() as conn:
        if result_id_raw not in (None, ""):
            try:
                result_id = int(result_id_raw)
            except (TypeError, ValueError):
                return jsonify({"error": "invalid id"}), 400
            row = conn.execute(
                text(
                    """
                    SELECT id, symbol, strategy, timeframe, start_date, end_date,
                           initial_capital, final_capital, total_return, max_drawdown,
                           win_rate, total_trades, winning_trades, sharpe_ratio,
                           equity_curve, trades_log, created_at
                    FROM backtest_results
                    WHERE id = :id AND user_id = :uid
                    LIMIT 1
                    """
                ),
                {"id": result_id, "uid": int(u.id)},
            ).mappings().first()
            if row is None:
                return jsonify({"error": "not found"}), 404
            return jsonify(_serialize_row_dt(dict(row)))

        rows = conn.execute(
            text(
                """
                SELECT id, symbol, strategy, timeframe, start_date, end_date,
                       initial_capital, final_capital, total_return, max_drawdown,
                       win_rate, total_trades, sharpe_ratio, created_at
                FROM backtest_results
                WHERE user_id = :uid
                ORDER BY created_at DESC
                LIMIT 20
                """
            ),
            {"uid": int(u.id)},
        ).mappings().all()
    return jsonify([_serialize_row_dt(dict(r)) for r in rows])


@app.route("/api/backtest/run", methods=["POST"])
@login_required
def api_backtest_run():
    if db.SessionLocal is None:
        return jsonify({"error": "database unavailable"}), 503
    u = _marketplace_db_user()
    if u is None:
        return jsonify({"error": "Vyžaduje sa registrovaný účet."}), 400
    from core.backtest_engine import run_backtest as run_real_backtest

    body = request.get_json(silent=True) or {}
    symbol = str(body.get("symbol") or "BTC/USD").strip()[:20] or "BTC/USD"
    strategy = str(body.get("strategy") or "momentum").strip().lower()[:50] or "momentum"
    start_str = str(body.get("start_date") or "2024-01-01").strip()
    end_str = str(body.get("end_date") or "2024-12-31").strip()
    timeframe = str(body.get("timeframe") or "1d").strip().lower()
    risk_level = str(body.get("risk_level") or "medium").strip().lower()
    try:
        capital = float(body.get("initial_capital", 10000) or 10000)
    except (TypeError, ValueError):
        return jsonify({"error": "Capital must be between $100 and $1,000,000"}), 400

    if timeframe not in {"1d", "4h", "1h"}:
        return jsonify({"error": "Invalid timeframe"}), 400
    if strategy not in {"momentum", "dca", "mean_reversion", "breakout", "grid"}:
        return jsonify({"error": "Invalid strategy"}), 400
    if risk_level not in {"low", "medium", "high"}:
        return jsonify({"error": "Invalid risk level"}), 400
    if capital < 100 or capital > 1_000_000:
        return jsonify({"error": "Capital must be between $100 and $1,000,000"}), 400

    try:
        start = datetime.strptime(start_str[:10], "%Y-%m-%d").date()
        end = datetime.strptime(end_str[:10], "%Y-%m-%d").date()
    except ValueError:
        return jsonify({"error": "Invalid date format"}), 400

    delta_days = (end - start).days
    if delta_days < 30:
        return jsonify({"error": "Minimum 30 days required"}), 400
    if delta_days > 730:
        return jsonify({"error": "Maximum 2 years"}), 400

    try:
        result = run_real_backtest(symbol, strategy, start, end, capital, timeframe, risk_level)
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": str(exc)}), 500

    eng = db.get_engine()
    if eng is None:
        return jsonify(result)

    try:
        with eng.begin() as conn:
            trading_agent_id = conn.execute(
                text("SELECT id FROM trading_agents WHERE symbol = :sym ORDER BY id ASC LIMIT 1"),
                {"sym": symbol},
            ).scalar()
            if trading_agent_id is None:
                trading_agent_id = conn.execute(text("SELECT id FROM trading_agents ORDER BY id ASC LIMIT 1")).scalar()
            conn.execute(
                text(
                    """
                    INSERT INTO backtest_results
                        (user_id, agent_id, symbol, strategy, timeframe, start_date, end_date,
                         initial_capital, final_capital, total_return, max_drawdown, win_rate,
                         total_trades, winning_trades, sharpe_ratio, equity_curve, trades_log,
                         agent_type, trading_agent_id, period_days, result_json)
                    VALUES
                        (:uid, :aid, :sym, :strat, :tf, :sd, :ed,
                         :ic, :fc, :tr, :md, :wr,
                         :tt, :wt, :sr, CAST(:ec AS JSONB), CAST(:tl AS JSONB),
                         'system', :taid, :pd, CAST(:rj AS JSONB))
                    """
                ),
                {
                    "uid": int(u.id),
                    "aid": int(trading_agent_id) if trading_agent_id is not None else None,
                    "sym": symbol,
                    "strat": strategy,
                    "tf": timeframe,
                    "sd": start.isoformat(),
                    "ed": end.isoformat(),
                    "ic": capital,
                    "fc": result["final_capital"],
                    "tr": result["total_return"],
                    "md": result["max_drawdown"],
                    "wr": result["win_rate"],
                    "tt": result["total_trades"],
                    "wt": result["winning_trades"],
                    "sr": result["sharpe_ratio"],
                    "ec": json.dumps(result["equity_curve"]),
                    "tl": json.dumps(result["trades_log"]),
                    "taid": str(trading_agent_id) if trading_agent_id is not None else None,
                    "pd": int(delta_days),
                    "rj": json.dumps(result),
                },
            )
    except Exception:  # noqa: BLE001
        log.exception("backtest_results insert")

    return jsonify(result)


@app.route("/api/backtest/quick", methods=["POST"])
@login_required
def api_backtest_quick():
    """Ad-hoc symbol + strategy backtest for legacy Backtest page (no agent_id)."""
    if db.SessionLocal is None:
        return jsonify({"error": "database unavailable"}), 503
    u = _marketplace_db_user()
    if u is None:
        return jsonify({"error": "Vyžaduje sa registrovaný účet."}), 400
    body = request.get_json(silent=True) or {}
    symbol = str(body.get("symbol") or "").strip()
    if not symbol:
        return jsonify({"error": "Chýba symbol."}), 400
    strategy_raw = body.get("strategy") or "momentum"
    start_s = str(body.get("start_date") or "").strip()
    end_s = str(body.get("end_date") or "").strip()
    if not start_s or not end_s:
        end_d0 = datetime.now(timezone.utc).date()
        start_d0 = end_d0 - timedelta(days=30)
        start_s = start_d0.isoformat()
        end_s = end_d0.isoformat()
    try:
        start_d = datetime.strptime(start_s[:10], "%Y-%m-%d").date()
        end_d = datetime.strptime(end_s[:10], "%Y-%m-%d").date()
    except ValueError:
        return jsonify({"error": "Neplatný dátum."}), 400
    period_days = max(1, (end_d - start_d).days + 1)
    tf_raw = str(body.get("timeframe") or "1Day").strip()
    tf_norm = tf_raw.lower().replace(" ", "").replace("_", "")
    tf_map = {"1hour": "1h", "1h": "1h", "4hour": "4h", "4h": "4h", "1day": "1d", "1d": "1d"}
    timeframe = tf_map.get(tf_norm, "1d")

    et = effective_tier(u)
    if period_days > backtest_max_days_for_tier(et):
        return (
            jsonify(
                {"error": "Obdobie presahuje limit tarifu.", "limits": backtest_limits_payload(et)},
            ),
            403,
        )
    if timeframe not in backtest_allowed_timeframes(et):
        return (
            jsonify(
                {"error": "Timeframe nie je v tvojom tarife.", "limits": backtest_limits_payload(et)},
            ),
            403,
        )

    cfg = agent_config_from_row_system(str(strategy_raw))
    if body.get("stop_loss_pct") is not None:
        try:
            cfg["stop_loss_pct"] = float(body["stop_loss_pct"])
        except (TypeError, ValueError):
            pass

    def _job_quick() -> dict[str, Any]:
        candles = fetch_candles(symbol, timeframe, period_days)
        if not candles:
            raise ValueError("Žiadne sviečky (skontroluj symbol alebo Binance).")
        return run_backtest(cfg, candles, timeframe)

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            fut = pool.submit(_job_quick)
            try:
                raw_res = fut.result(timeout=30)
            except concurrent.futures.TimeoutError:
                return jsonify({"error": "Backtest trvá príliš dlho.", "timeout": True}), 408
    except BinanceFetchError as exc:
        log.warning("backtest quick binance: %s", exc)
        return jsonify({"error": "Binance API dočasne nedostupné.", "detail": str(exc)}), 502
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    return jsonify(_backtest_compat_payload(raw_res))


def _backtest_compat_payload(sim: dict[str, Any]) -> dict[str, Any]:
    """Shape expected by legacy backtest UI (equity_curve.t / .v, metrics keys, trades)."""
    trades_out: list[dict[str, Any]] = []
    for t in sim.get("trades") or []:
        if t.get("action") != "SELL":
            continue
        ts = int(t.get("timestamp") or 0)
        trades_out.append(
            {
                "exit_t": datetime.fromtimestamp(ts / 1000.0, tz=timezone.utc).isoformat(),
                "exit_px": t.get("price"),
                "pnl_usd": t.get("pnl"),
                "exit_reason": t.get("reason") or "",
            }
        )
    curve: list[dict[str, Any]] = []
    for p in sim.get("equity_curve") or []:
        ts2 = int(p.get("timestamp") or 0)
        curve.append(
            {
                "t": datetime.fromtimestamp(ts2 / 1000.0, tz=timezone.utc).isoformat(),
                "v": p.get("equity"),
            }
        )
    return {
        "total_return_pct": sim.get("total_pnl_pct"),
        "final_equity": curve[-1]["v"] if curve else None,
        "metrics": {
            "num_trades": sim.get("total_trades"),
            "win_rate_pct": sim.get("win_rate"),
            "max_drawdown_pct": sim.get("max_drawdown_pct"),
            "sharpe_annualized": sim.get("sharpe_ratio"),
            "profit_factor": sim.get("profit_factor"),
            "avg_hold_seconds": None,
        },
        "trades": trades_out,
        "equity_curve": curve,
        "compare": None,
    }


def _api_key_owner_db_user():
    _resolve_identity()
    u = getattr(g, "db_user", None)
    if u is None or getattr(g, "auth_kind", None) != "db":
        return None
    t = normalize_tier(effective_tier(u))
    if t not in (TIER_ELITE, TIER_ADMIN):
        return None
    return u


def hash_key(raw_key: str) -> str:
    return hashlib.sha256((raw_key or "").encode("utf-8")).hexdigest()


def _serialize_api_key_row(row: dict[str, Any]) -> dict[str, Any]:
    out = dict(row)
    for k in ("last_used_at", "created_at"):
        v = out.get(k)
        if hasattr(v, "isoformat"):
            out[k] = v.isoformat()
    return out


def api_key_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        raw_key = (request.headers.get("X-API-Key") or request.args.get("api_key") or "").strip()
        if not raw_key:
            return jsonify({"error": "API key required"}), 401

        eng = db.get_engine()
        if eng is None:
            return jsonify({"error": "database unavailable"}), 503

        key_hash = hash_key(raw_key)
        with eng.begin() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT
                        ak.id,
                        ak.user_id,
                        ak.requests_today,
                        ak.requests_total,
                        ak.rate_limit,
                        u.tier
                    FROM api_keys ak
                    JOIN users u ON u.id = ak.user_id
                    WHERE ak.key_hash = :hash AND ak.is_active = TRUE
                    LIMIT 1
                    """
                ),
                {"hash": key_hash},
            ).mappings().first()

            if row is None:
                return jsonify({"error": "Invalid or inactive API key"}), 401

            tier = normalize_tier(str(row.get("tier") or TIER_BASIC))
            if tier not in (TIER_ELITE, TIER_ADMIN):
                return jsonify({"error": "Elite tier required"}), 403

            requests_today = int(row.get("requests_today") or 0)
            key_rate_limit = int(row.get("rate_limit") or 1000)
            if requests_today >= key_rate_limit:
                return jsonify({"error": "Daily rate limit exceeded"}), 429

            conn.execute(
                text(
                    """
                    UPDATE api_keys
                    SET requests_today = COALESCE(requests_today, 0) + 1,
                        requests_total = COALESCE(requests_total, 0) + 1,
                        last_used_at = NOW()
                    WHERE id = :kid
                    """
                ),
                {"kid": int(row["id"])},
            )

        g.api_user_id = int(row["user_id"])
        g.api_key_id = int(row["id"])
        g.api_rate_limit = key_rate_limit
        g.api_rate_remaining = max(0, key_rate_limit - requests_today - 1)
        g.api_rate_reset = int(time.time()) + 86400
        g.api_auth_ok = True
        return f(*args, **kwargs)

    return decorated


def _v1_success(data: Any, extra: dict[str, Any] | None = None, status: int = 200):
    payload: dict[str, Any] = {"data": data, "timestamp": datetime.now(timezone.utc).isoformat()}
    if extra:
        payload.update(extra)
    return jsonify(payload), status


def _v1_error(error: str, message: str, code: int):
    return jsonify({"error": error, "message": message, "code": int(code)}), int(code)


def _v1_period_to_since(period: str) -> datetime | None:
    p = (period or "all").strip().lower()
    now = datetime.now(timezone.utc)
    if p == "today":
        return now - timedelta(days=1)
    if p == "week":
        return now - timedelta(days=7)
    if p == "month":
        return now - timedelta(days=30)
    return None


def _serialize_v1_user_agent(row: dict[str, Any]) -> dict[str, Any]:
    cfg = row.get("config_json")
    if isinstance(cfg, str):
        try:
            cfg = json.loads(cfg)
        except json.JSONDecodeError:
            cfg = {}
    if not isinstance(cfg, dict):
        cfg = {}
    ca = row.get("created_at")
    return {
        "id": int(row["id"]),
        "type": "user_agent",
        "name": row.get("name") or "",
        "symbol": row.get("symbol") or "",
        "strategy": row.get("strategy_type") or "",
        "status": row.get("status") or "",
        "config": cfg,
        "created_at": ca.isoformat() if hasattr(ca, "isoformat") else str(ca or ""),
    }


@app.route("/api/developer/keys", methods=["GET"])
@login_required
def list_api_keys():
    if db.SessionLocal is None:
        return jsonify({"error": "database unavailable"}), 503
    u = _api_key_owner_db_user()
    if u is None:
        return jsonify({"error": "Elite tier required"}), 403

    eng = db.get_engine()
    if eng is None:
        return jsonify({"error": "database unavailable"}), 503

    with eng.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT id, key_prefix, name, is_active, requests_today,
                       requests_total, rate_limit, last_used_at, created_at
                FROM api_keys
                WHERE user_id = :uid
                ORDER BY created_at DESC
                """
            ),
            {"uid": int(u.id)},
        ).mappings().all()
    return jsonify([_serialize_api_key_row(dict(r)) for r in rows])


@app.route("/api/developer/keys", methods=["POST"])
@login_required
def create_api_key():
    if db.SessionLocal is None:
        return jsonify({"error": "database unavailable"}), 503
    u = _api_key_owner_db_user()
    if u is None:
        return jsonify({"error": "Elite tier required"}), 403

    body = request.get_json(silent=True) or {}
    name = str(body.get("name") or "Default").strip()[:100] or "Default"
    eng = db.get_engine()
    if eng is None:
        return jsonify({"error": "database unavailable"}), 503

    raw_key = f"hms_{secrets.token_urlsafe(32)}"
    prefix = raw_key[:8]
    key_hash = hash_key(raw_key)
    with eng.begin() as conn:
        count = conn.execute(
            text(
                """
                SELECT COUNT(*)::int AS c
                FROM api_keys
                WHERE user_id = :uid AND is_active = TRUE
                """
            ),
            {"uid": int(u.id)},
        ).scalar()
        if int(count or 0) >= 3:
            return jsonify({"error": "Maximum 3 API keys allowed"}), 400

        conn.execute(
            text(
                """
                INSERT INTO api_keys (user_id, key_hash, key_prefix, name)
                VALUES (:uid, :hash, :prefix, :name)
                """
            ),
            {"uid": int(u.id), "hash": key_hash, "prefix": prefix, "name": name},
        )

    return jsonify({"key": raw_key, "prefix": prefix, "name": name})


@app.route("/api/developer/keys/<int:key_id>", methods=["DELETE"])
@login_required
def revoke_api_key(key_id: int):
    if db.SessionLocal is None:
        return jsonify({"error": "database unavailable"}), 503
    u = _api_key_owner_db_user()
    if u is None:
        return jsonify({"error": "Elite tier required"}), 403
    eng = db.get_engine()
    if eng is None:
        return jsonify({"error": "database unavailable"}), 503

    with eng.begin() as conn:
        conn.execute(
            text(
                """
                UPDATE api_keys
                SET is_active = FALSE
                WHERE id = :kid AND user_id = :uid
                """
            ),
            {"kid": int(key_id), "uid": int(u.id)},
        )
    return jsonify({"status": "revoked"})


@app.route("/api/keys", methods=["GET"])
@login_required
def api_keys_list():
    if db.SessionLocal is None:
        return jsonify({"error": "database unavailable"}), 503
    u = _api_key_owner_db_user()
    if u is None:
        return jsonify({"error": "Elite/API prístup vyžaduje Elite alebo Admin tier."}), 403
    eng = db.get_engine()
    if eng is None:
        return jsonify({"error": "database unavailable"}), 503
    with eng.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT id, key_prefix, name, scopes, is_active, last_used_at, expires_at, created_at
                FROM api_keys
                WHERE user_id = :uid
                ORDER BY created_at DESC
                """
            ),
            {"uid": int(u.id)},
        ).mappings().all()
    out = []
    for r in rows:
        d = dict(r)
        for k in ("last_used_at", "expires_at", "created_at"):
            v = d.get(k)
            if hasattr(v, "isoformat"):
                d[k] = v.isoformat()
        out.append(d)
    return jsonify({"keys": out, "max_active": 5, "rate_limit_per_min": API_RATE_LIMIT_PER_MIN})


@app.route("/api/keys/generate", methods=["POST"])
@login_required
def api_keys_generate():
    if db.SessionLocal is None:
        return jsonify({"error": "database unavailable"}), 503
    u = _api_key_owner_db_user()
    if u is None:
        return jsonify({"error": "Elite/API prístup vyžaduje Elite alebo Admin tier."}), 403
    body = request.get_json(silent=True) or {}
    name = str(body.get("name") or "").strip()[:100] or None
    expires_days_raw = body.get("expires_in_days")
    expires_at = None
    if expires_days_raw not in (None, "", "null"):
        try:
            d = int(expires_days_raw)
            if d <= 0 or d > 3650:
                return jsonify({"error": "expires_in_days musí byť 1..3650 alebo null."}), 400
            expires_at = datetime.now(timezone.utc) + timedelta(days=d)
        except (TypeError, ValueError):
            return jsonify({"error": "Neplatný expires_in_days."}), 400

    eng = db.get_engine()
    if eng is None:
        return jsonify({"error": "database unavailable"}), 503
    plain = generate_api_key()
    kh = hash_api_key(plain)
    prefix = plain[:8]
    with eng.begin() as conn:
        active_count = conn.execute(
            text(
                """
                SELECT COUNT(*)::int
                FROM api_keys
                WHERE user_id = :uid AND is_active IS TRUE
                """
            ),
            {"uid": int(u.id)},
        ).scalar()
        if int(active_count or 0) >= 5:
            return jsonify({"error": "Max 5 aktívnych API kľúčov na účet."}), 400
        conn.execute(
            text(
                """
                INSERT INTO api_keys (user_id, key_hash, key_prefix, name, expires_at)
                VALUES (:uid, :kh, :kp, :nm, :exp)
                """
            ),
            {"uid": int(u.id), "kh": kh, "kp": prefix, "nm": name, "exp": expires_at},
        )
    return jsonify(
        {
            "api_key": plain,
            "prefix": prefix,
            "warning": "Tento kľúč uvidíš len raz. Ulož si ho bezpečne.",
        }
    )


@app.route("/api/keys/<int:key_id>", methods=["DELETE"])
@login_required
def api_keys_revoke(key_id: int):
    if db.SessionLocal is None:
        return jsonify({"error": "database unavailable"}), 503
    u = _api_key_owner_db_user()
    if u is None:
        return jsonify({"error": "Elite/API prístup vyžaduje Elite alebo Admin tier."}), 403
    eng = db.get_engine()
    if eng is None:
        return jsonify({"error": "database unavailable"}), 503
    with eng.begin() as conn:
        row = conn.execute(
            text(
                """
                UPDATE api_keys
                SET is_active = FALSE
                WHERE id = :kid AND user_id = :uid
                RETURNING id
                """
            ),
            {"kid": int(key_id), "uid": int(u.id)},
        ).first()
    if not row:
        return jsonify({"error": "API kľúč neexistuje alebo nepatrí používateľovi."}), 404
    return jsonify({"success": True, "id": int(key_id), "is_active": False})


@app.route("/api/keys/<int:key_id>/usage", methods=["GET"])
@login_required
def api_keys_usage(key_id: int):
    if db.SessionLocal is None:
        return jsonify({"error": "database unavailable"}), 503
    u = _api_key_owner_db_user()
    if u is None:
        return jsonify({"error": "Elite/API prístup vyžaduje Elite alebo Admin tier."}), 403
    eng = db.get_engine()
    if eng is None:
        return jsonify({"error": "database unavailable"}), 503
    with eng.connect() as conn:
        key_owner = conn.execute(
            text("SELECT id FROM api_keys WHERE id = :kid AND user_id = :uid"),
            {"kid": int(key_id), "uid": int(u.id)},
        ).first()
        if not key_owner:
            return jsonify({"error": "API kľúč neexistuje alebo nepatrí používateľovi."}), 404
        rows = conn.execute(
            text(
                """
                SELECT endpoint, method, status_code, response_time_ms, ip_address, created_at
                FROM api_requests
                WHERE api_key_id = :kid
                ORDER BY created_at DESC
                LIMIT 100
                """
            ),
            {"kid": int(key_id)},
        ).mappings().all()
        stats = conn.execute(
            text(
                """
                SELECT
                    COUNT(*)::int AS total_calls,
                    COALESCE(AVG(response_time_ms), 0)::double precision AS avg_response_time,
                    COALESCE(
                        100.0 * SUM(CASE WHEN status_code BETWEEN 200 AND 299 THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0),
                        0
                    )::double precision AS success_rate
                FROM api_requests
                WHERE api_key_id = :kid
                """
            ),
            {"kid": int(key_id)},
        ).mappings().first()
    out_rows = []
    for r in rows:
        d = dict(r)
        ca = d.get("created_at")
        if hasattr(ca, "isoformat"):
            d["created_at"] = ca.isoformat()
        out_rows.append(d)
    return jsonify(
        {
            "requests": out_rows,
            "stats": {
                "total_calls": int((stats or {}).get("total_calls") or 0),
                "success_rate": float((stats or {}).get("success_rate") or 0.0),
                "avg_response_time_ms": float((stats or {}).get("avg_response_time") or 0.0),
            },
        }
    )


@app.route("/api/v1/agents", methods=["GET"])
@api_key_required
def public_api_agents():
    eng = db.get_engine()
    if eng is None:
        return jsonify({"error": "database unavailable"}), 503
    uid = int(getattr(g, "api_user_id", 0))
    with eng.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT id, name, symbol, strategy_type AS strategy, status, created_at
                FROM user_agents
                WHERE user_id = :uid AND status != 'deleted'
                ORDER BY created_at DESC
                """
            ),
            {"uid": uid},
        ).mappings().all()
    out = []
    for row in rows:
        item = dict(row)
        created_at = item.get("created_at")
        if hasattr(created_at, "isoformat"):
            item["created_at"] = created_at.isoformat()
        out.append(item)
    return jsonify({"agents": out})


@app.route("/api/v1/agents/<int:agent_id>/trades", methods=["GET"])
@api_key_required
def public_api_trades(agent_id: int):
    eng = db.get_engine()
    if eng is None:
        return jsonify({"error": "database unavailable"}), 503
    uid = int(getattr(g, "api_user_id", 0))
    try:
        limit = min(max(int(request.args.get("limit", 50)), 1), 200)
    except (TypeError, ValueError):
        limit = 50

    with eng.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT symbol, action AS side, price, quantity, pnl, timestamp AS created_at
                FROM paper_trades
                WHERE user_id = :uid AND user_agent_id = :aid
                ORDER BY timestamp DESC
                LIMIT :lim
                """
            ),
            {"uid": uid, "aid": int(agent_id), "lim": int(limit)},
        ).mappings().all()
    out = []
    for row in rows:
        item = dict(row)
        created_at = item.get("created_at")
        if hasattr(created_at, "isoformat"):
            item["created_at"] = created_at.isoformat()
        out.append(item)
    return jsonify({"trades": out})


@app.route("/api/v1/pnl", methods=["GET"])
@api_key_required
def public_api_pnl():
    eng = db.get_engine()
    if eng is None:
        return jsonify({"error": "database unavailable"}), 503
    uid = int(getattr(g, "api_user_id", 0))
    with eng.connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT COALESCE(SUM(pnl), 0)::double precision AS total_pnl,
                       COUNT(*)::int AS total_trades,
                       COUNT(CASE WHEN pnl > 0 THEN 1 END)::int AS winning_trades
                FROM paper_trades
                WHERE user_id = :uid
                """
            ),
            {"uid": uid},
        ).mappings().first()
    return jsonify(
        {
            "total_pnl": float((row or {}).get("total_pnl") or 0.0),
            "total_trades": int((row or {}).get("total_trades") or 0),
            "winning_trades": int((row or {}).get("winning_trades") or 0),
        }
    )


@app.route("/v1/agents", methods=["GET"])
@require_api_key
def v1_agents_list():
    eng = db.get_engine()
    if eng is None:
        return _v1_error("Service Unavailable", "Database unavailable", 503)
    uid = int(getattr(g, "api_user_id", 0))
    with eng.connect() as conn:
        uas = conn.execute(
            text(
                """
                SELECT id, name, symbol, strategy_type, status, config_json, created_at
                FROM user_agents
                WHERE user_id = :uid AND status != 'deleted'
                ORDER BY created_at DESC
                """
            ),
            {"uid": uid},
        ).mappings().all()
        syss = conn.execute(
            text(
                """
                SELECT ta.id, ta.name, ta.symbol, ta.strategy, us.mode
                FROM user_subscriptions us
                JOIN trading_agents ta ON ta.id = us.agent_id
                WHERE us.user_id = :uid AND us.is_active IS TRUE
                ORDER BY ta.name ASC
                """
            ),
            {"uid": uid},
        ).mappings().all()
    data = [_serialize_v1_user_agent(dict(r)) for r in uas]
    for s in syss:
        data.append(
            {
                "id": str(s["id"]),
                "type": "system_agent",
                "name": s.get("name") or "",
                "symbol": s.get("symbol") or "",
                "strategy": s.get("strategy") or "",
                "status": "active",
                "config": {},
                "created_at": None,
            }
        )
    return _v1_success(data, extra={"total": len(data)})


@app.route("/v1/agents/<agent_id>", methods=["GET"])
@require_api_key
def v1_agent_detail(agent_id: str):
    eng = db.get_engine()
    if eng is None:
        return _v1_error("Service Unavailable", "Database unavailable", 503)
    uid = int(getattr(g, "api_user_id", 0))
    with eng.connect() as conn:
        ua = None
        try:
            aid_int = int(agent_id)
            ua = conn.execute(
                text(
                    """
                    SELECT id, name, symbol, strategy_type, status, config_json, created_at
                    FROM user_agents
                    WHERE id = :id AND user_id = :uid AND status != 'deleted'
                    """
                ),
                {"id": aid_int, "uid": uid},
            ).mappings().first()
        except (TypeError, ValueError):
            aid_int = None
        if ua:
            trades = conn.execute(
                text(
                    """
                    SELECT id, symbol, action, price, quantity, pnl, reason, timestamp
                    FROM paper_trades
                    WHERE user_id = :uid AND user_agent_id = :uaid
                    ORDER BY timestamp DESC
                    LIMIT 10
                    """
                ),
                {"uid": uid, "uaid": int(ua["id"])},
            ).mappings().all()
            out = _serialize_v1_user_agent(dict(ua))
            out["trades"] = [_serialize_row_dt(dict(t)) for t in trades]
            return _v1_success(out)

        sa = conn.execute(
            text(
                """
                SELECT ta.id, ta.name, ta.symbol, ta.strategy, us.mode
                FROM user_subscriptions us
                JOIN trading_agents ta ON ta.id = us.agent_id
                WHERE us.user_id = :uid AND us.is_active IS TRUE AND ta.id = :aid
                LIMIT 1
                """
            ),
            {"uid": uid, "aid": str(agent_id)},
        ).mappings().first()
        if not sa:
            return _v1_error("Not Found", "Agent not found", 404)
        trades = conn.execute(
            text(
                """
                SELECT id, symbol, action, price, quantity, pnl, reason, timestamp
                FROM paper_trades
                WHERE user_id = :uid AND agent_id = :aid
                ORDER BY timestamp DESC
                LIMIT 10
                """
            ),
            {"uid": uid, "aid": str(agent_id)},
        ).mappings().all()
    out = {
        "id": str(sa["id"]),
        "type": "system_agent",
        "name": sa.get("name") or "",
        "symbol": sa.get("symbol") or "",
        "strategy": sa.get("strategy") or "",
        "status": "active",
        "config": {},
        "created_at": None,
        "trades": [_serialize_row_dt(dict(t)) for t in trades],
    }
    return _v1_success(out)


@app.route("/v1/agents/<agent_id>/pnl", methods=["GET"])
@require_api_key
def v1_agent_pnl(agent_id: str):
    eng = db.get_engine()
    if eng is None:
        return _v1_error("Service Unavailable", "Database unavailable", 503)
    uid = int(getattr(g, "api_user_id", 0))
    period = (request.args.get("period") or "all").strip().lower()
    if period not in ("today", "week", "month", "all"):
        return _v1_error("Bad Request", "period musí byť today|week|month|all", 400)
    since = _v1_period_to_since(period)
    where_ts = " AND timestamp >= :since " if since is not None else " "
    with eng.connect() as conn:
        is_user_agent = False
        try:
            aid_int = int(agent_id)
            ua = conn.execute(
                text("SELECT id FROM user_agents WHERE id = :id AND user_id = :uid AND status != 'deleted'"),
                {"id": aid_int, "uid": uid},
            ).first()
            is_user_agent = ua is not None
        except (TypeError, ValueError):
            is_user_agent = False
        if is_user_agent:
            cond = "user_agent_id = :aid"
            aid_val = int(agent_id)
        else:
            cond = "agent_id = :aid"
            aid_val = str(agent_id)
        params = {"uid": uid, "aid": aid_val}
        if since is not None:
            params["since"] = since
        agg = conn.execute(
            text(
                f"""
                SELECT
                    COALESCE(SUM(pnl), 0)::double precision AS pnl_usd,
                    COUNT(*)::int AS trade_count,
                    COALESCE(
                        100.0 * SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0),
                        0
                    )::double precision AS win_rate
                FROM paper_trades
                WHERE user_id = :uid AND {cond}
                {where_ts}
                """
            ),
            params,
        ).mappings().first()
        snaps = conn.execute(
            text(
                f"""
                SELECT DATE(timestamp) AS d, COALESCE(SUM(pnl), 0)::double precision AS pnl
                FROM paper_trades
                WHERE user_id = :uid AND {cond}
                {where_ts}
                GROUP BY DATE(timestamp)
                ORDER BY d ASC
                LIMIT 120
                """
            ),
            params,
        ).mappings().all()
    pnl_usd = float((agg or {}).get("pnl_usd") or 0.0)
    pnl_pct = (pnl_usd / PNL_BASELINE_USD) * 100.0 if PNL_BASELINE_USD else 0.0
    equity = PNL_BASELINE_USD + pnl_usd
    snapshots = []
    running = PNL_BASELINE_USD
    for s in snaps:
        p = float(s.get("pnl") or 0.0)
        running += p
        snapshots.append({"date": str(s.get("d")), "pnl_pct": round((p / PNL_BASELINE_USD) * 100.0, 4), "equity": running})
    return _v1_success(
        {
            "agent_id": agent_id,
            "period": period,
            "pnl_usd": round(pnl_usd, 4),
            "pnl_pct": round(pnl_pct, 4),
            "win_rate": round(float((agg or {}).get("win_rate") or 0.0), 4),
            "trade_count": int((agg or {}).get("trade_count") or 0),
            "equity": round(equity, 4),
            "snapshots": snapshots,
        }
    )


@app.route("/v1/agents/<agent_id>/backtest", methods=["GET"])
@require_api_key
def v1_agent_backtest(agent_id: str):
    eng = db.get_engine()
    if eng is None:
        return _v1_error("Service Unavailable", "Database unavailable", 503)
    uid = int(getattr(g, "api_user_id", 0))
    try:
        aid_int = int(agent_id)
        use_user = True
    except (TypeError, ValueError):
        aid_int = None
        use_user = False
    with eng.connect() as conn:
        if use_user:
            row = conn.execute(
                text(
                    """
                    SELECT result_json, created_at
                    FROM backtest_results
                    WHERE user_id = :uid AND user_agent_id = :aid
                    ORDER BY created_at DESC
                    LIMIT 1
                    """
                ),
                {"uid": uid, "aid": aid_int},
            ).mappings().first()
        else:
            row = conn.execute(
                text(
                    """
                    SELECT result_json, created_at
                    FROM backtest_results
                    WHERE user_id = :uid AND trading_agent_id = :aid
                    ORDER BY created_at DESC
                    LIMIT 1
                    """
                ),
                {"uid": uid, "aid": str(agent_id)},
            ).mappings().first()
    if not row:
        return _v1_error("Not Found", "Backtest result not found", 404)
    res = row.get("result_json")
    if isinstance(res, str):
        try:
            res = json.loads(res)
        except json.JSONDecodeError:
            res = {}
    data = {"agent_id": agent_id, "created_at": row["created_at"].isoformat() if hasattr(row["created_at"], "isoformat") else None, "result": res or {}}
    return _v1_success(data)


@app.route("/v1/agents/<int:agent_id>/pause", methods=["POST"])
@require_api_key
def v1_agent_pause(agent_id: int):
    eng = db.get_engine()
    if eng is None:
        return _v1_error("Service Unavailable", "Database unavailable", 503)
    uid = int(getattr(g, "api_user_id", 0))
    with eng.begin() as conn:
        row = conn.execute(
            text(
                """
                UPDATE user_agents SET status = 'paused', updated_at = NOW()
                WHERE id = :id AND user_id = :uid AND status != 'deleted'
                RETURNING id, status
                """
            ),
            {"id": int(agent_id), "uid": uid},
        ).mappings().first()
    if not row:
        return _v1_error("Not Found", "User agent not found", 404)
    return _v1_success({"success": True, "agent_id": int(row["id"]), "status": row["status"]})


@app.route("/v1/agents/<int:agent_id>/resume", methods=["POST"])
@require_api_key
def v1_agent_resume(agent_id: int):
    eng = db.get_engine()
    if eng is None:
        return _v1_error("Service Unavailable", "Database unavailable", 503)
    uid = int(getattr(g, "api_user_id", 0))
    with eng.begin() as conn:
        row = conn.execute(
            text(
                """
                UPDATE user_agents SET status = 'active', updated_at = NOW()
                WHERE id = :id AND user_id = :uid AND status != 'deleted'
                RETURNING id, status
                """
            ),
            {"id": int(agent_id), "uid": uid},
        ).mappings().first()
    if not row:
        return _v1_error("Not Found", "User agent not found", 404)
    return _v1_success({"success": True, "agent_id": int(row["id"]), "status": row["status"]})


@app.route("/v1/agents/<int:agent_id>/config", methods=["POST"])
@require_api_key
def v1_agent_config_update(agent_id: int):
    eng = db.get_engine()
    if eng is None:
        return _v1_error("Service Unavailable", "Database unavailable", 503)
    uid = int(getattr(g, "api_user_id", 0))
    body = request.get_json(silent=True) or {}
    patch_cfg: dict[str, Any] = {}
    if "stop_loss_pct" in body:
        try:
            v = float(body.get("stop_loss_pct"))
            if v <= 0 or v > 50:
                return _v1_error("Bad Request", "stop_loss_pct musí byť v rozsahu 0-50.", 400)
            patch_cfg["stop_loss_pct"] = v
        except (TypeError, ValueError):
            return _v1_error("Bad Request", "Neplatný stop_loss_pct.", 400)
    if "position_size_pct" in body:
        try:
            v = float(body.get("position_size_pct"))
            if v <= 0 or v > 100:
                return _v1_error("Bad Request", "position_size_pct musí byť v rozsahu 0-100.", 400)
            patch_cfg["position_size_pct"] = v
        except (TypeError, ValueError):
            return _v1_error("Bad Request", "Neplatný position_size_pct.", 400)
    if "max_daily_trades" in body:
        try:
            v = int(body.get("max_daily_trades"))
            if v < 1 or v > 200:
                return _v1_error("Bad Request", "max_daily_trades musí byť v rozsahu 1-200.", 400)
            patch_cfg["max_daily_trades"] = v
        except (TypeError, ValueError):
            return _v1_error("Bad Request", "Neplatný max_daily_trades.", 400)
    if not patch_cfg:
        return _v1_error("Bad Request", "Neprišli žiadne validné config polia.", 400)

    with eng.begin() as conn:
        row = conn.execute(
            text(
                """
                SELECT config_json
                FROM user_agents
                WHERE id = :id AND user_id = :uid AND status != 'deleted'
                FOR UPDATE
                """
            ),
            {"id": int(agent_id), "uid": uid},
        ).mappings().first()
        if not row:
            return _v1_error("Not Found", "User agent not found", 404)
        cfg = row.get("config_json")
        if isinstance(cfg, str):
            try:
                cfg = json.loads(cfg)
            except json.JSONDecodeError:
                cfg = {}
        if not isinstance(cfg, dict):
            cfg = {}
        cfg.update(patch_cfg)
        conn.execute(
            text(
                """
                UPDATE user_agents
                SET config_json = CAST(:cfg AS JSONB), updated_at = NOW()
                WHERE id = :id AND user_id = :uid
                """
            ),
            {"cfg": json.dumps(cfg), "id": int(agent_id), "uid": uid},
        )
    return _v1_success({"success": True, "agent_id": int(agent_id), "config": cfg})


@app.route("/v1/marketplace", methods=["GET"])
def v1_marketplace_public():
    if db.SessionLocal is None:
        return _v1_error("Service Unavailable", "Database unavailable", 503)
    symbol = (request.args.get("symbol") or "").strip() or None
    strategy = (request.args.get("strategy") or "").strip() or None
    sort = (request.args.get("sort") or "pnl_week").strip()
    try:
        limit = min(max(int(request.args.get("limit") or 20), 1), 100)
    except (TypeError, ValueError):
        limit = 20
    sess = db.db_session()
    try:
        candidates = fetch_approved_listing_candidates(sess, symbol_filter=symbol, strategy_filter=strategy)
        ranked = sort_listing_rows(candidates, sort)
        all_ids = [int(r["id"]) for r in ranked]
        top = compute_top_gainer_user_agent_ids(sess, all_ids)
        out = [enrich_listing_for_api(sess, r, viewer_user_id=None, top_gainers=top) for r in ranked[:limit]]
        return _v1_success(out, extra={"total": len(out)})
    except Exception:
        log.exception("v1 marketplace")
        return _v1_error("Internal Error", "Nepodarilo sa načítať marketplace.", 500)


def _notify_user_in_session(sess, user_id: int, ntype: str, title: str, message: str) -> None:
    sess.execute(
        text("""
        INSERT INTO notifications (user_id, type, title, message)
        VALUES (:uid, :nt, :title, :msg)
        """),
        {
            "uid": int(user_id),
            "nt": (ntype or "system")[:64],
            "title": (title or "")[:255],
            "msg": message or "",
        },
    )


@app.route("/api/marketplace/listings", methods=["GET"])
def api_marketplace_community_listings():
    if db.SessionLocal is None:
        return jsonify({"error": "database unavailable"}), 503
    _resolve_identity()
    viewer_id: int | None = None
    u = _marketplace_db_user()
    if u is not None:
        viewer_id = int(u.id)
    symbol = (request.args.get("symbol") or "").strip() or None
    strategy = (request.args.get("strategy") or "").strip() or None
    sort = (request.args.get("sort") or "pnl_week").strip()
    try:
        limit = min(max(int(request.args.get("limit") or 20), 1), 100)
    except (TypeError, ValueError):
        limit = 20
    sess = db.db_session()
    try:
        candidates = fetch_approved_listing_candidates(sess, symbol_filter=symbol, strategy_filter=strategy)
        ranked = sort_listing_rows(candidates, sort)
        all_ids = [int(r["id"]) for r in ranked]
        top = compute_top_gainer_user_agent_ids(sess, all_ids)
        slice_rows = ranked[:limit]
        out = [
            enrich_listing_for_api(sess, r, viewer_user_id=viewer_id, top_gainers=top) for r in slice_rows
        ]
        return jsonify({"listings": out})
    except Exception:  # noqa: BLE001
        log.exception("community marketplace listings")
        return jsonify({"error": "Nepodarilo sa načítať marketplace."}), 500


@app.route("/api/marketplace/listings/<public_id>", methods=["GET"])
def api_marketplace_community_listing_detail(public_id: str):
    if db.SessionLocal is None:
        return jsonify({"error": "database unavailable"}), 503
    _resolve_identity()
    viewer_id: int | None = None
    u = _marketplace_db_user()
    if u is not None:
        viewer_id = int(u.id)
    try:
        uuid.UUID(str(public_id).strip())
    except ValueError:
        return jsonify({"error": "Neplatný identifikátor."}), 400
    sess = db.db_session()
    try:
        row = fetch_approved_agent_by_public_id(sess, public_id)
        if not row:
            return jsonify({"error": "Listing neexistuje."}), 404
        top = compute_top_gainer_user_agent_ids(sess, [int(row["id"])])
        listing = enrich_listing_for_api(sess, row, viewer_user_id=viewer_id, top_gainers=top)
        trades = recent_trades_for_listing(sess, int(row["id"]), int(row["user_id"]), limit=10)
        listing["recent_trades"] = trades
        return jsonify(listing)
    except Exception:  # noqa: BLE001
        log.exception("community listing detail")
        return jsonify({"error": "Chyba pri načítaní detailu."}), 500


@app.route("/api/marketplace/listings/<public_id>/clone", methods=["POST"])
@login_required
def api_marketplace_community_clone(public_id: str):
    if db.SessionLocal is None:
        return jsonify({"error": "database unavailable"}), 503
    u = _marketplace_db_user()
    if u is None:
        return jsonify({"error": "Vyžaduje sa registrovaný účet."}), 403
    try:
        uuid.UUID(str(public_id).strip())
    except ValueError:
        return jsonify({"error": "Neplatný identifikátor.", "success": False}), 400

    sess = db.db_session()
    try:
        src = fetch_approved_agent_by_public_id(sess, public_id)
        if not src:
            return jsonify({"success": False, "message": "Agent nie je dostupný na klonovanie."}), 404

        sid = int(src["id"])
        if int(src["user_id"]) == int(u.id):
            return jsonify({"success": False, "message": "Toto je tvoj vlastný agent."}), 400

        dup = sess.execute(
            text("""
            SELECT 1 FROM marketplace_clones
            WHERE source_agent_id = :sid AND cloned_by_user_id = :uid
            LIMIT 1
            """),
            {"sid": sid, "uid": int(u.id)},
        ).first()
        if dup is not None:
            return jsonify({"success": False, "message": "Tento agent už máš naklonovaný."}), 400

        cap = user_agent_cap_for_user(u)
        cur = _user_agent_counts(sess, int(u.id))
        if cap is not None and cur >= cap:
            return jsonify(
                {
                    "success": False,
                    "upgrade_required": True,
                    "message": "Dosiahol si limit agentov pre svoj plán. Upgraduj pre viac slotov.",
                    "limit": cap,
                    "count": cur,
                }
            ), 403

        cfg = src.get("config_json") or {}
        if isinstance(cfg, str):
            try:
                cfg = json.loads(cfg)
            except (json.JSONDecodeError, TypeError):
                cfg = {}
        cfg_js = json.dumps(cfg)
        base_name = str(src.get("name") or "Agent")[:80]
        new_name = (base_name + " (kópia)")[:100]

        new_row = sess.execute(
            text("""
            INSERT INTO user_agents (
              user_id, name, symbol, strategy_type, config_json, status, is_public, marketplace_status
            ) VALUES (
              :uid, :name, :symbol, :stype, CAST(:cfg AS jsonb), 'active', FALSE, NULL
            )
            RETURNING id
            """),
            {
                "uid": int(u.id),
                "name": new_name,
                "symbol": src.get("symbol") or "BTC/USD",
                "stype": str(src.get("strategy_type") or "momentum").lower(),
                "cfg": cfg_js,
            },
        ).mappings().first()
        new_id = int(new_row["id"]) if new_row else None
        if new_id is None:
            sess.rollback()
            return jsonify({"success": False, "message": "Klonovanie zlyhalo."}), 500

        sess.execute(
            text("""
            INSERT INTO marketplace_clones (source_agent_id, cloned_by_user_id)
            VALUES (:sid, :uid)
            """),
            {"sid": sid, "uid": int(u.id)},
        )
        sess.execute(
            text("""
            UPDATE user_agents
            SET clone_count = clone_count + 1,
                popularity_score = COALESCE(popularity_score, 0) + 1,
                updated_at = NOW()
            WHERE id = :sid
            """),
            {"sid": sid},
        )
        aname = str(src.get("name") or "Agent")
        _notify_user_in_session(
            sess,
            int(u.id),
            "marketplace",
            "Nový agent",
            f'Agent "{aname}" bol pridaný do tvojho portfólia! 🤖',
        )
        sess.commit()
        return jsonify({"success": True, "new_agent_id": new_id, "message": "Agent bol naklonovaný."})
    except IntegrityError:
        sess.rollback()
        return jsonify({"success": False, "message": "Tento agent už máš naklonovaný."}), 409
    except Exception:  # noqa: BLE001
        sess.rollback()
        log.exception("community clone")
        return jsonify({"success": False, "message": "Klonovanie zlyhalo."}), 500


@app.route("/api/marketplace/user-agents/publish", methods=["POST"])
@login_required
def api_marketplace_publish_user_agent():
    if db.SessionLocal is None:
        return jsonify({"error": "database unavailable"}), 503
    u = _marketplace_db_user()
    if u is None:
        return jsonify({"success": False, "message": "Vyžaduje sa registrovaný účet."}), 403
    if not can_publish_tier(u):
        return jsonify(
            {"success": False, "message": "Publikovať do community marketplace môžu len Pro, Elite alebo Admin."}
        ), 403

    data = request.get_json(silent=True) or {}
    try:
        agent_id = int(data.get("agent_id"))
    except (TypeError, ValueError):
        return jsonify({"success": False, "message": "Chýba platné agent_id."}), 400
    desc = (data.get("description") or "").strip()
    if len(desc) < 50:
        return jsonify({"success": False, "message": "Popis musí mať aspoň 50 znakov."}), 400
    if len(desc) > 500:
        return jsonify({"success": False, "message": "Popis môže mať najviac 500 znakov."}), 400

    sess = db.db_session()
    try:
        row = sess.execute(
            text("""
            SELECT * FROM user_agents
            WHERE id = :id AND user_id = :uid AND status != 'deleted'
            """),
            {"id": agent_id, "uid": int(u.id)},
        ).mappings().first()
        if not row:
            return jsonify({"success": False, "message": "Agent neexistuje alebo k nemu nemáš prístup."}), 404
        rowd = dict(row)
        if str(rowd.get("status") or "") != "active":
            return jsonify({"success": False, "message": "Agent musí byť v stave active."}), 400
        ms = (rowd.get("marketplace_status") or "").strip().lower()
        if ms == "pending":
            return jsonify({"success": False, "message": "Agent už čaká na schválenie."}), 400
        if ms == "approved":
            return jsonify({"success": False, "message": "Agent je už schválený v marketplace."}), 400

        chk = validate_publish_requirements(
            sess, int(u.id), agent_id, rowd.get("created_at")
        )
        if not chk.ok:
            return jsonify({"success": False, "message": " · ".join(chk.errors)}), 400

        sess.execute(
            text("""
            UPDATE user_agents SET
              description = :desc,
              is_public = TRUE,
              marketplace_status = 'pending',
              published_at = NOW(),
              marketplace_reject_reason = NULL,
              updated_at = NOW()
            WHERE id = :id AND user_id = :uid AND status != 'deleted'
            """),
            {"desc": desc, "id": agent_id, "uid": int(u.id)},
        )
        aname = str(rowd.get("name") or "Agent")
        _notify_user_in_session(
            sess,
            int(u.id),
            "marketplace",
            "Marketplace",
            f"Agent {aname} bol odoslaný na schválenie do marketplace 🚀",
        )
        sess.commit()
        return jsonify(
            {
                "success": True,
                "message": "Agent bol odoslaný na schválenie.",
            }
        )
    except Exception:  # noqa: BLE001
        sess.rollback()
        log.exception("publish user agent")
        return jsonify({"success": False, "message": "Publikovanie zlyhalo."}), 500


@app.route("/api/marketplace/user-agents/unpublish", methods=["POST"])
@login_required
def api_marketplace_unpublish_user_agent():
    if db.SessionLocal is None:
        return jsonify({"error": "database unavailable"}), 503
    u = _marketplace_db_user()
    if u is None:
        return jsonify({"success": False, "message": "Vyžaduje sa registrovaný účet."}), 403
    data = request.get_json(silent=True) or {}
    try:
        agent_id = int(data.get("agent_id"))
    except (TypeError, ValueError):
        return jsonify({"success": False, "message": "Chýba platné agent_id."}), 400
    sess = db.db_session()
    try:
        r = sess.execute(
            text("""
            UPDATE user_agents SET
              is_public = FALSE,
              marketplace_status = NULL,
              updated_at = NOW()
            WHERE id = :id AND user_id = :uid AND status != 'deleted'
            RETURNING id
            """),
            {"id": agent_id, "uid": int(u.id)},
        ).first()
        if r is None:
            sess.rollback()
            return jsonify({"success": False, "message": "Agent neexistuje."}), 404
        sess.commit()
        return jsonify({"success": True, "message": "Agent bol stiahnutý z verejného marketplace."})
    except Exception:  # noqa: BLE001
        sess.rollback()
        log.exception("unpublish user agent")
        return jsonify({"success": False, "message": "Operácia zlyhala."}), 500


@app.route("/api/admin/marketplace/pending", methods=["GET"])
@admin_required
def api_admin_marketplace_pending():
    if db.SessionLocal is None:
        return jsonify({"error": "database unavailable"}), 503
    sess = db.db_session()
    try:
        rows = sess.execute(
            text("""
            SELECT ua.id, ua.name, ua.symbol, ua.strategy_type, ua.description, ua.published_at,
                   ua.user_id, ua.public_id, u.username, u.tier,
                   (SELECT COUNT(*)::int FROM paper_trades pt
                    WHERE pt.user_agent_id = ua.id AND pt.user_id = ua.user_id) AS trade_count
            FROM user_agents ua
            JOIN users u ON u.id = ua.user_id
            WHERE ua.marketplace_status = 'pending' AND ua.status != 'deleted'
            ORDER BY ua.published_at NULLS LAST, ua.id DESC
            """)
        ).mappings().all()
        out = []
        for r in rows:
            d = dict(r)
            pid = d.get("public_id")
            if pid is not None and hasattr(pid, "hex"):
                d["public_id"] = str(pid)
            if d.get("published_at") is not None and hasattr(d["published_at"], "isoformat"):
                d["published_at"] = d["published_at"].isoformat()
            out.append(d)
        return jsonify({"pending": out})
    except Exception:  # noqa: BLE001
        log.exception("admin marketplace pending")
        return jsonify({"error": "Nepodarilo sa načítať zoznam."}), 500


@app.route("/api/admin/marketplace/approve", methods=["POST"])
@admin_required
def api_admin_marketplace_approve():
    if db.SessionLocal is None:
        return jsonify({"error": "database unavailable"}), 503
    data = request.get_json(silent=True) or {}
    try:
        aid = int(data.get("agent_id"))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "message": "agent_id required"}), 400
    sess = db.db_session()
    try:
        row = sess.execute(
            text("""
            UPDATE user_agents SET marketplace_status = 'approved', is_public = TRUE, updated_at = NOW()
            WHERE id = :id AND marketplace_status = 'pending' AND status != 'deleted'
            RETURNING user_id, name
            """),
            {"id": aid},
        ).mappings().first()
        if not row:
            sess.rollback()
            return jsonify({"ok": False, "message": "Agent sa nenašiel alebo nie je v stave pending."}), 404
        rd = dict(row)
        uname = str(rd.get("name") or "Agent")
        _notify_user_in_session(
            sess,
            int(rd["user_id"]),
            "marketplace",
            "Schválené",
            f'Tvoj agent "{uname}" bol schválený! 🎉',
        )
        sess.commit()
        return jsonify({"ok": True})
    except Exception:  # noqa: BLE001
        sess.rollback()
        log.exception("admin approve marketplace")
        return jsonify({"ok": False, "message": "Chyba."}), 500


@app.route("/api/admin/marketplace/reject", methods=["POST"])
@admin_required
def api_admin_marketplace_reject():
    if db.SessionLocal is None:
        return jsonify({"error": "database unavailable"}), 503
    data = request.get_json(silent=True) or {}
    try:
        aid = int(data.get("agent_id"))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "message": "agent_id required"}), 400
    reason = (data.get("reason") or "").strip()
    if len(reason) < 3:
        return jsonify({"ok": False, "message": "Uveď dôvod zamietnutia (min. 3 znaky)."}), 400
    sess = db.db_session()
    try:
        row = sess.execute(
            text("""
            UPDATE user_agents SET
              marketplace_status = 'rejected',
              is_public = FALSE,
              marketplace_reject_reason = :reason,
              updated_at = NOW()
            WHERE id = :id AND marketplace_status = 'pending' AND status != 'deleted'
            RETURNING user_id, name
            """),
            {"id": aid, "reason": reason[:2000]},
        ).mappings().first()
        if not row:
            sess.rollback()
            return jsonify({"ok": False, "message": "Agent sa nenašiel alebo nie je v stave pending."}), 404
        rd = dict(row)
        uname = str(rd.get("name") or "Agent")
        _notify_user_in_session(
            sess,
            int(rd["user_id"]),
            "marketplace",
            "Marketplace",
            f'Agent "{uname}" bol zamietnutý. Dôvod: {reason[:500]}',
        )
        sess.commit()
        return jsonify({"ok": True})
    except Exception:  # noqa: BLE001
        sess.rollback()
        log.exception("admin reject marketplace")
        return jsonify({"ok": False, "message": "Chyba."}), 500


def _admin_tier_user():
    if not _admin_ok():
        return None
    user = getattr(g, "db_user", None)
    if user is None:
        return None
    return user


@app.route("/api/admin/registry/agents", methods=["GET"])
@admin_required
def get_registry_agents():
    eng = db.get_engine()
    if eng is None:
        return jsonify({"error": "database unavailable"}), 503
    redis_agents = queue_manager.get_all_agents()
    with eng.connect() as conn:
        db_agents = conn.execute(
            text(
                """
                SELECT ar.*, u.username AS created_by_handle
                FROM agent_registry ar
                LEFT JOIN users u ON u.id = ar.created_by
                ORDER BY ar.created_at DESC
                """
            )
        ).mappings().all()
    return jsonify(
        {
            "redis_agents": redis_agents,
            "db_agents": [_serialize_row_dt(dict(row)) for row in db_agents],
            "queue_stats": queue_manager.get_queue_stats(),
            "swarms": DEFAULT_SWARMS,
        }
    )


@app.route("/api/admin/registry/agents", methods=["POST"])
@admin_required
def create_registry_agent():
    user = _admin_tier_user()
    if user is None:
        return jsonify({"error": "Registered admin account required"}), 403
    data = request.get_json(silent=True) or {}
    agent_id = str(data.get("agent_id") or f"agent-{str(uuid.uuid4())[:8]}").strip()[:50]
    if not agent_id:
        return jsonify({"error": "agent_id is required"}), 400
    name = str(data.get("name") or "New Agent").strip()[:100] or "New Agent"
    swarm_name = str(data.get("swarm_name") or "default").strip()[:50] or "default"
    capabilities = data.get("capabilities")
    if not isinstance(capabilities, list):
        capabilities = []
    config = data.get("config")
    if not isinstance(config, dict):
        config = {}
    try:
        priority = int(data.get("priority", 5))
    except (TypeError, ValueError):
        priority = 5
    priority = max(1, min(priority, 10))
    eng = db.get_engine()
    if eng is None:
        return jsonify({"error": "database unavailable"}), 503
    with eng.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO agent_registry (agent_id, name, swarm_name, capabilities, config, priority, created_by)
                VALUES (:aid, :name, :swarm, CAST(:caps AS JSONB), CAST(:cfg AS JSONB), :pri, :uid)
                ON CONFLICT (agent_id) DO UPDATE SET
                    name = EXCLUDED.name,
                    swarm_name = EXCLUDED.swarm_name,
                    capabilities = EXCLUDED.capabilities,
                    config = EXCLUDED.config,
                    priority = EXCLUDED.priority,
                    updated_at = NOW()
                """
            ),
            {
                "aid": agent_id,
                "name": name,
                "swarm": swarm_name,
                "caps": json.dumps(capabilities),
                "cfg": json.dumps(config),
                "pri": priority,
                "uid": int(user.id),
            },
        )
    queue_manager.register_agent(agent_id, name, swarm_name, capabilities, config)
    return jsonify({"status": "created", "agent_id": agent_id})


@app.route("/api/admin/registry/agents/<agent_id>/status", methods=["POST"])
@admin_required
def update_registry_agent_status(agent_id: str):
    status = str((request.get_json(silent=True) or {}).get("status") or "").strip().lower()
    if status not in ("idle", "running", "paused", "error", "stopped"):
        return jsonify({"error": "Invalid status"}), 400
    queue_manager.update_agent_status(agent_id, status)
    eng = db.get_engine()
    if eng is None:
        return jsonify({"error": "database unavailable"}), 503
    with eng.begin() as conn:
        conn.execute(
            text("UPDATE agent_registry SET status = :s, updated_at = NOW() WHERE agent_id = :aid"),
            {"s": status, "aid": str(agent_id)},
        )
    return jsonify({"status": "updated"})


@app.route("/api/admin/queue/stats", methods=["GET"])
@admin_required
def get_admin_queue_stats():
    stats = queue_manager.get_queue_stats()
    eng = db.get_engine()
    if eng is None:
        return jsonify({"error": "database unavailable"}), 503
    with eng.connect() as conn:
        db_stats = conn.execute(
            text(
                """
                SELECT status, COUNT(*)::int AS count
                FROM task_queue
                GROUP BY status
                """
            )
        ).mappings().all()
    stats["db_queue"] = {row["status"]: int(row["count"]) for row in db_stats}
    return jsonify(stats)


@app.route("/api/admin/queue/push", methods=["POST"])
@admin_required
def push_queue_task():
    data = request.get_json(silent=True) or {}
    task_type = str(data.get("task_type") or "generic").strip()[:50] or "generic"
    payload = data.get("payload")
    if not isinstance(payload, dict):
        payload = {}
    required = data.get("required_capabilities")
    if not isinstance(required, list):
        required = []
    try:
        priority = int(data.get("priority", 5))
    except (TypeError, ValueError):
        priority = 5
    priority = max(1, min(priority, 10))
    task_id = str(uuid.uuid4())
    queue_manager.push_task(
        task_type=task_type,
        payload=payload,
        priority=priority,
        required_capabilities=required,
        task_id=task_id,
    )
    return jsonify({"task_id": task_id, "status": "queued"})


@app.route("/api/admin/queue/tasks", methods=["GET"])
@admin_required
def get_queue_tasks():
    eng = db.get_engine()
    if eng is None:
        return jsonify({"error": "database unavailable"}), 503
    with eng.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT *
                FROM task_queue
                ORDER BY priority DESC, created_at DESC
                LIMIT 50
                """
            )
        ).mappings().all()
    return jsonify([_serialize_row_dt(dict(row)) for row in rows])


@app.route("/api/admin/router/route", methods=["POST"])
@admin_required
def manual_route_task():
    user = _admin_tier_user()
    if user is None:
        return jsonify({"error": "Registered admin account required"}), 403
    data = request.get_json(silent=True) or {}
    required = data.get("required_capabilities")
    if not isinstance(required, list):
        required = []
    payload = data.get("payload")
    if not isinstance(payload, dict):
        payload = {}
    try:
        priority = int(data.get("priority", 5))
    except (TypeError, ValueError):
        priority = 5
    decision = task_router.route_task(
        task_type=str(data.get("task_type") or "manual"),
        payload=payload,
        priority=max(1, min(priority, 10)),
        required_capabilities=required,
        preferred_swarm=str(data.get("preferred_swarm") or "").strip() or None,
    )
    return jsonify(decision)


@app.route("/api/admin/router/simulate", methods=["POST"])
@admin_required
def simulate_routing():
    user = _admin_tier_user()
    if user is None:
        return jsonify({"error": "Registered admin account required"}), 403
    data = request.get_json(silent=True) or {}
    required = data.get("required_capabilities")
    if not isinstance(required, list):
        required = []
    result = task_router.simulate_route(
        task_type=str(data.get("task_type") or "generic"),
        required_capabilities=required,
    )
    return jsonify(result)


@app.route("/api/admin/router/log", methods=["GET"])
@admin_required
def get_routing_log():
    user = _admin_tier_user()
    if user is None:
        return jsonify({"error": "Registered admin account required"}), 403
    try:
        limit = int(request.args.get("limit", 20))
    except (TypeError, ValueError):
        limit = 20
    return jsonify(task_router.get_routing_log(limit=max(1, min(limit, 50))))


@app.route("/api/admin/system/health", methods=["GET"])
@admin_required
def get_admin_system_health():
    eng = db.get_engine()
    db_ok = False
    if eng is not None:
        try:
            with eng.connect() as conn:
                conn.execute(text("SELECT 1"))
            db_ok = True
        except Exception:
            db_ok = False
    redis_ok = queue_manager.health_check()
    queue_stats = queue_manager.get_queue_stats() if redis_ok else {"pending": 0}
    if psutil is not None:
        mem = psutil.virtual_memory()
        cpu_percent = float(psutil.cpu_percent(interval=0.1))
        memory_percent = float(mem.percent)
        memory_used_gb = round(float(mem.used) / 1e9, 1)
        memory_total_gb = round(float(mem.total) / 1e9, 1)
    else:
        cpu_percent = 0.0
        memory_percent = 0.0
        memory_used_gb = 0.0
        memory_total_gb = 0.0
    return jsonify(
        {
            "cpu_percent": cpu_percent,
            "memory_percent": memory_percent,
            "memory_used_gb": memory_used_gb,
            "memory_total_gb": memory_total_gb,
            "psutil_available": bool(psutil is not None),
            "redis": redis_ok,
            "db": db_ok,
            "queue_pending": int(queue_stats.get("pending", 0)),
        }
    )


def check_rate_limit(user_id: int, action: str, max_per_minute: int = 10) -> bool:
    key = f"hermes:ratelimit:{action}:{int(user_id)}:{int(time.time() // 60)}"
    try:
        count = int(queue_redis.incr(key))
        queue_redis.expire(key, 120)
        return count <= int(max_per_minute)
    except Exception:
        return True


@app.route("/api/admin/swarm-builder/generate", methods=["POST"])
@admin_required
def generate_swarm_from_prompt():
    user = _admin_tier_user()
    if user is None:
        return jsonify({"error": "Registered admin account required"}), 403
    data = request.get_json(silent=True) or {}
    prompt = str(data.get("prompt") or "").strip()[:2000]
    if not prompt:
        return jsonify({"error": "Prompt required"}), 400
    if not check_rate_limit(int(user.id), "swarm-generate", 5):
        return jsonify({"error": "Rate limit exceeded. Max 5 generates/minute."}), 429
    api_key = (os.getenv("ANTHROPIC_API_KEY") or "").strip()
    if not api_key:
        return jsonify({"error": "ANTHROPIC_API_KEY not configured"}), 503
    if not ANTHROPIC_AVAILABLE:
        return jsonify({"error": "Anthropic SDK not available"}), 503

    ai_client = anthropic.Anthropic(api_key=api_key)
    system = """You are a Swarm Architecture Designer for Hermes AI Trading Platform.

When given a description of what a swarm should do, respond ONLY with valid JSON.
No markdown, no explanation, just raw JSON.

Available capabilities: trading, momentum, crypto, stocks, commodities, risk, portfolio,
research, news, analysis, trends, social, marketing, content, seo, tiktok, reels,
maintenance, monitoring, security, audit, backup, voice, support, routing, orchestration,
planning, reporting, email, telegram, data, ml, backtest, sentiment

JSON structure:
{
  "swarm_name": "snake_case_name",
  "display_name": "Human Readable Name",
  "icon": "emoji",
  "description": "One sentence description",
  "color": "oklch(0.72 0.18 295)",
  "priority": 5,
  "agents": [
    {
      "agent_id": "swarm_name-001",
      "name": "Agent Display Name",
      "agent_type": "worker|lead|orchestrator",
      "capabilities": ["cap1", "cap2"],
      "config": {
        "temperature": 0.7,
        "risk_level": "medium",
        "description": "What this agent does"
      }
    }
  ],
  "task_queue_settings": {
    "max_concurrent": 3,
    "rate_limit_per_hour": 100
  },
  "memory_enabled": true,
  "human_approval_required": false,
  "cost_limit_daily": 10.0,
  "estimated_monthly_cost": 15.0,
  "reasoning": "Brief explanation of why these agents were chosen"
}

Generate 2-6 agents. First agent should be 'lead' type, rest 'worker'.
Choose appropriate oklch color based on swarm purpose."""
    message = ai_client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1500,
        system=system,
        messages=[{"role": "user", "content": f"Design a swarm for: {prompt}"}],
    )
    raw = ""
    try:
        parts: list[str] = []
        for block in getattr(message, "content", []) or []:
            if getattr(block, "type", None) == "text":
                parts.append(str(getattr(block, "text", "") or ""))
        raw = "".join(parts).strip()
        raw = raw.replace("```json", "").replace("```", "").strip()
        config = json.loads(raw)
        return jsonify({"status": "ok", "config": config})
    except Exception as e:  # noqa: BLE001
        return jsonify({"error": f"Parse error: {e}", "raw": raw}), 500


@app.route("/api/admin/swarm-builder/create", methods=["POST"])
@admin_required
def create_swarm_from_config():
    user = _admin_tier_user()
    if user is None:
        return jsonify({"error": "Registered admin account required"}), 403
    data = request.get_json(silent=True) or {}
    config = data.get("config")
    if not isinstance(config, dict):
        return jsonify({"error": "Config required"}), 400
    agents = config.get("agents")
    if not isinstance(agents, list) or not agents:
        return jsonify({"error": "Config must include agents"}), 400

    swarm_name = str(config.get("swarm_name") or "custom").strip()[:50] or "custom"
    try:
        priority = int(config.get("priority", 5))
    except (TypeError, ValueError):
        priority = 5
    priority = max(1, min(priority, 10))

    swarm_metadata = {
        "display_name": str(config.get("display_name") or swarm_name)[:100],
        "icon": str(config.get("icon") or "🤖")[:8],
        "color": str(config.get("color") or "oklch(0.72 0.18 295)")[:80],
        "description": str(config.get("description") or "")[:500],
        "memory_enabled": bool(config.get("memory_enabled", True)),
        "human_approval_required": bool(config.get("human_approval_required", False)),
        "estimated_monthly_cost": float(config.get("estimated_monthly_cost") or 0),
        "task_queue_settings": config.get("task_queue_settings") if isinstance(config.get("task_queue_settings"), dict) else {},
        "created_by": int(user.id),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source": "prompt_builder",
    }

    eng = db.get_engine()
    if eng is None:
        return jsonify({"error": "database unavailable"}), 503

    created_agents: list[str] = []
    failed_agents: list[dict] = []

    try:
        from core.swarm_registry import swarm_registry as _registry
    except Exception:  # noqa: BLE001
        _registry = None

    for agent in agents:
        if not isinstance(agent, dict):
            continue
        agent_id = str(agent.get("agent_id") or f"{swarm_name}-{str(uuid.uuid4())[:6]}").strip()[:50]
        if not agent_id:
            continue
        name = str(agent.get("name") or "Agent").strip()[:100] or "Agent"
        caps = agent.get("capabilities") if isinstance(agent.get("capabilities"), list) else []
        cfg = agent.get("config") if isinstance(agent.get("config"), dict) else {}
        agent_type = str(agent.get("agent_type") or "worker").strip().lower()
        if agent_type not in ("worker", "lead", "orchestrator"):
            agent_type = "worker"

        agent_priority = priority
        try:
            agent_priority = int(agent.get("priority") or priority)
        except (TypeError, ValueError):
            pass
        agent_priority = max(1, min(agent_priority, 10))

        agent_metadata = {
            **swarm_metadata,
            "swarm_display_name": swarm_metadata["display_name"],
            "agent_role": str(agent.get("role") or "")[:200] if agent.get("role") else None,
        }

        try:
            with eng.begin() as conn:
                conn.execute(
                    text(
                        """
                        INSERT INTO agent_registry
                            (agent_id, name, swarm_name, capabilities, config, agent_type,
                             priority, metadata, created_by)
                        VALUES (:aid, :name, :swarm, CAST(:caps AS JSONB), CAST(:cfg AS JSONB),
                                :atype, :pri, CAST(:meta AS JSONB), :uid)
                        ON CONFLICT (agent_id) DO UPDATE SET
                            name = EXCLUDED.name,
                            swarm_name = EXCLUDED.swarm_name,
                            capabilities = EXCLUDED.capabilities,
                            config = EXCLUDED.config,
                            agent_type = EXCLUDED.agent_type,
                            priority = EXCLUDED.priority,
                            metadata = EXCLUDED.metadata,
                            updated_at = NOW()
                        """
                    ),
                    {
                        "aid": agent_id,
                        "name": name,
                        "swarm": swarm_name,
                        "caps": json.dumps(caps),
                        "cfg": json.dumps(cfg),
                        "atype": agent_type,
                        "pri": agent_priority,
                        "meta": json.dumps(agent_metadata),
                        "uid": int(user.id),
                    },
                )
        except Exception as exc:  # noqa: BLE001
            log.warning("swarm-builder create failed for %s: %s", agent_id, exc)
            failed_agents.append({"agent_id": agent_id, "error": str(exc)[:200]})
            continue

        # Hot-cache via Swarm v2 registry (preferred), fall back to legacy queue_manager.
        if _registry is not None:
            try:
                _registry.register_agent(
                    agent_id=agent_id,
                    name=name,
                    swarm=swarm_name,
                    capabilities=caps,
                    agent_type=agent_type,
                    priority=agent_priority,
                    config=cfg,
                    metadata=agent_metadata,
                )
            except Exception:  # noqa: BLE001
                queue_manager.register_agent(agent_id, name, swarm_name, caps, cfg)
        else:
            queue_manager.register_agent(agent_id, name, swarm_name, caps, cfg)

        created_agents.append(agent_id)

    return jsonify(
        {
            "status": "created",
            "swarm_name": swarm_name,
            "swarm_metadata": swarm_metadata,
            "agents_created": len(created_agents),
            "agent_ids": created_agents,
            "failed": failed_agents,
        }
    )


@app.route("/api/admin/swarm-builder/swarms/<path:swarm_name>", methods=["DELETE"])
@admin_required
def delete_swarm(swarm_name: str):
    """Hard-delete a custom swarm (all its agents) — admin only."""
    user = _admin_tier_user()
    if user is None:
        return jsonify({"error": "Registered admin account required"}), 403
    safe_swarm = str(swarm_name or "").strip()[:50]
    if not safe_swarm:
        return jsonify({"error": "Invalid swarm name"}), 400
    # Protect built-in swarms from accidental delete.
    PROTECTED = {"orchestra", "trading", "intelligence", "marketing", "maintenance"}
    if safe_swarm in PROTECTED:
        return jsonify({"error": f"Cannot delete protected swarm '{safe_swarm}'"}), 400

    eng = db.get_engine()
    if eng is None:
        return jsonify({"error": "database unavailable"}), 503

    with eng.begin() as conn:
        rows = conn.execute(
            text("SELECT agent_id FROM agent_registry WHERE swarm_name = :s"),
            {"s": safe_swarm},
        ).all()
        agent_ids = [str(r[0]) for r in rows]
        conn.execute(
            text("DELETE FROM agent_registry WHERE swarm_name = :s"),
            {"s": safe_swarm},
        )

    # Best-effort Redis cleanup
    try:
        from core.swarm_registry import get_redis, REGISTRY_PREFIX, SWARM_PREFIX, HEARTBEAT_PREFIX
        r = get_redis()
        for aid in agent_ids:
            try:
                r.delete(f"{REGISTRY_PREFIX}{aid}")
                r.delete(f"{HEARTBEAT_PREFIX}{aid}")
            except Exception:  # noqa: BLE001
                pass
        try:
            r.delete(f"{SWARM_PREFIX}{safe_swarm}")
        except Exception:  # noqa: BLE001
            pass
    except Exception:  # noqa: BLE001
        pass

    return jsonify({
        "status": "deleted",
        "swarm_name": safe_swarm,
        "agents_removed": len(agent_ids),
    })


@app.route("/api/admin/users", methods=["GET"])
@admin_required
def admin_get_users():
    if db.SessionLocal is None:
        return jsonify({"error": "database unavailable"}), 503
    eng = db.get_engine()
    if eng is None:
        return jsonify({"error": "database unavailable"}), 503
    with eng.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT id, email, tier, created_at, stripe_subscription_id
                FROM users
                ORDER BY created_at DESC
                """
            )
        ).mappings().all()
    out = []
    for r in rows:
        d = dict(r)
        if d.get("created_at") is not None and hasattr(d["created_at"], "isoformat"):
            d["created_at"] = d["created_at"].isoformat()
        out.append(d)
    return jsonify({"users": out})


@app.route("/api/admin/users/<int:user_id>/tier", methods=["POST"])
@admin_required
def admin_set_tier(user_id: int):
    if db.SessionLocal is None:
        return jsonify({"error": "database unavailable"}), 503
    data = request.get_json(silent=True) or {}
    new_tier = str(data.get("tier") or "").strip().lower()
    if new_tier not in ("basic", "pro", "elite", "admin"):
        return jsonify({"error": "Invalid tier"}), 400
    eng = db.get_engine()
    if eng is None:
        return jsonify({"error": "database unavailable"}), 503
    with eng.begin() as conn:
        row = conn.execute(
            text("UPDATE users SET tier = :tier WHERE id = :id RETURNING id"),
            {"tier": new_tier, "id": int(user_id)},
        ).first()
        if row is None:
            return jsonify({"error": "User not found"}), 404
    return jsonify({"success": True})


@app.route("/api/system-events", methods=["GET"])
@admin_required
def api_system_events():
    if db.SessionLocal is None:
        return jsonify({"error": "database unavailable"}), 503
    eng = db.get_engine()
    if eng is None:
        return jsonify({"error": "database unavailable"}), 503
    with eng.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT event_type, severity, message, created_at
                FROM system_events
                ORDER BY created_at DESC
                LIMIT 200
                """
            )
        ).mappings().all()
    out: list[dict[str, Any]] = []
    for r in rows:
        d = dict(r)
        if d.get("created_at") is not None and hasattr(d["created_at"], "isoformat"):
            d["created_at"] = d["created_at"].isoformat()
        out.append(d)
    return jsonify({"events": out})


# ── Admin CMS: revenue, agents, user detail ──────────────────────────────────

# Pricing constants for MRR estimate (kept here so backend stays single source of truth).
_TIER_PRICE_PRO_EUR = int(os.getenv("HERMES_TIER_PRICE_PRO_EUR", "19"))
_TIER_PRICE_ELITE_EUR = int(os.getenv("HERMES_TIER_PRICE_ELITE_EUR", "49"))


@app.route("/api/admin/revenue", methods=["GET"])
@admin_required
def admin_revenue():
    """Aggregate user/tier counts and MRR estimate for the admin CMS."""
    if db.SessionLocal is None:
        return jsonify({"error": "database unavailable"}), 503
    eng = db.get_engine()
    if eng is None:
        return jsonify({"error": "database unavailable"}), 503
    with eng.connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT
                    COUNT(*) FILTER (WHERE tier = 'pro')   AS pro_count,
                    COUNT(*) FILTER (WHERE tier = 'elite') AS elite_count,
                    COUNT(*) FILTER (WHERE tier = 'basic') AS basic_count,
                    COUNT(*)                               AS total_users,
                    COUNT(*) FILTER (WHERE stripe_subscription_id IS NOT NULL) AS paying_users
                FROM users
                """
            )
        ).mappings().first()

    pro_count = int(row["pro_count"] or 0) if row else 0
    elite_count = int(row["elite_count"] or 0) if row else 0
    basic_count = int(row["basic_count"] or 0) if row else 0
    total_users = int(row["total_users"] or 0) if row else 0
    paying_users = int(row["paying_users"] or 0) if row else 0

    return jsonify(
        {
            "pro_count": pro_count,
            "elite_count": elite_count,
            "basic_count": basic_count,
            "total_users": total_users,
            "paying_users": paying_users,
            "mrr_estimate": pro_count * _TIER_PRICE_PRO_EUR + elite_count * _TIER_PRICE_ELITE_EUR,
        }
    )


@app.route("/api/admin/agents", methods=["GET"])
@admin_required
def admin_get_agents():
    """List all trading agents with leaderboard visibility flag."""
    if db.SessionLocal is None:
        return jsonify({"error": "database unavailable"}), 503
    eng = db.get_engine()
    if eng is None:
        return jsonify({"error": "database unavailable"}), 503
    with eng.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT id, name, symbol, category, strategy,
                       win_rate, total_trades, show_in_leaderboard
                FROM trading_agents
                ORDER BY id
                """
            )
        ).mappings().all()
    return jsonify({"agents": [dict(r) for r in rows]})


@app.route("/api/admin/agents/<int:agent_id>/toggle", methods=["POST"])
@admin_required
def admin_toggle_agent(agent_id: int):
    """Flip show_in_leaderboard for a single trading agent."""
    if db.SessionLocal is None:
        return jsonify({"error": "database unavailable"}), 503
    eng = db.get_engine()
    if eng is None:
        return jsonify({"error": "database unavailable"}), 503
    with eng.begin() as conn:
        row = conn.execute(
            text(
                """
                UPDATE trading_agents
                SET show_in_leaderboard = NOT COALESCE(show_in_leaderboard, FALSE)
                WHERE id = :id
                RETURNING id, show_in_leaderboard
                """
            ),
            {"id": int(agent_id)},
        ).mappings().first()
    if row is None:
        return jsonify({"error": "Agent not found"}), 404
    return jsonify(
        {
            "success": True,
            "agent_id": int(row["id"]),
            "show_in_leaderboard": bool(row["show_in_leaderboard"]),
        }
    )


@app.route("/api/admin/users/<int:user_id>/detail", methods=["GET"])
@admin_required
def admin_user_detail(user_id: int):
    """Return user profile + active subscriptions + recent paper trades."""
    if db.SessionLocal is None:
        return jsonify({"error": "database unavailable"}), 503
    eng = db.get_engine()
    if eng is None:
        return jsonify({"error": "database unavailable"}), 503

    with eng.connect() as conn:
        user_row = conn.execute(
            text(
                """
                SELECT id, email, tier, created_at,
                       stripe_subscription_id, telegram_chat_id
                FROM users
                WHERE id = :id
                """
            ),
            {"id": int(user_id)},
        ).mappings().first()

        if user_row is None:
            return jsonify({"error": "User not found"}), 404

        subs_rows = conn.execute(
            text(
                """
                SELECT a.name, a.symbol, s.mode, s.is_active
                FROM user_subscriptions s
                JOIN trading_agents a ON a.id = s.agent_id
                WHERE s.user_id = :id
                ORDER BY s.is_active DESC, a.name ASC
                """
            ),
            {"id": int(user_id)},
        ).mappings().all()

        trade_rows = conn.execute(
            text(
                """
                SELECT symbol, action, price, pnl, timestamp
                FROM paper_trades
                WHERE user_id = :id
                ORDER BY timestamp DESC
                LIMIT 10
                """
            ),
            {"id": int(user_id)},
        ).mappings().all()

    user = dict(user_row)
    if user.get("created_at") is not None and hasattr(user["created_at"], "isoformat"):
        user["created_at"] = user["created_at"].isoformat()

    trades: list[dict[str, Any]] = []
    for r in trade_rows:
        t = dict(r)
        ts = t.get("timestamp")
        if ts is not None and hasattr(ts, "isoformat"):
            t["timestamp"] = ts.isoformat()
        for k in ("price", "pnl"):
            if t.get(k) is not None:
                try:
                    t[k] = float(t[k])
                except (TypeError, ValueError):
                    pass
        trades.append(t)

    return jsonify(
        {
            "user": user,
            "subscriptions": [dict(r) for r in subs_rows],
            "recent_trades": trades,
        }
    )


# ── Support / Helpdesk ────────────────────────────────────────────────────────


@app.route("/api/support/ticket", methods=["POST"])
def create_support_ticket():
    if db.SessionLocal is None:
        return jsonify({"error": "database unavailable"}), 503
    data = request.get_json(silent=True) or {}
    subject = str(data.get("subject") or "").strip()
    message = str(data.get("message") or "").strip()
    email = str(data.get("email") or request.headers.get("X-User-Email") or "").strip().lower()

    if not subject or not message or not email:
        return jsonify({"error": "Missing fields"}), 400

    eng = db.get_engine()
    if eng is None:
        return jsonify({"error": "database unavailable"}), 503

    with eng.begin() as conn:
        user_row = conn.execute(
            text("SELECT id FROM users WHERE lower(email) = :email LIMIT 1"),
            {"email": email},
        ).mappings().first()
        ticket = conn.execute(
            text(
                """
                INSERT INTO support_tickets (user_id, email, subject, message, status, priority)
                VALUES (:user_id, :email, :subject, :message, 'open', 'normal')
                RETURNING id
                """
            ),
            {
                "user_id": int(user_row["id"]) if user_row else None,
                "email": email,
                "subject": subject,
                "message": message,
            },
        ).mappings().first()

    try:
        if mailer.is_mail_configured():
            mailer.send_smtp_email(
                to_addr="support@letagentscook.lol",
                subject=f"[Support] New ticket: {subject}",
                text_body=(
                    f"From: {email}\n"
                    f"Ticket ID: #{int(ticket['id']) if ticket else 'n/a'}\n\n"
                    f"Message:\n{message}\n\n"
                    "Manage in admin support tab."
                ),
            )
    except Exception:
        log.exception("support admin notification failed")

    try:
        if mailer.is_mail_configured():
            mailer.send_smtp_email(
                to_addr=email,
                subject="[Hermes] We received your support request",
                text_body=(
                    "Hi,\n\n"
                    "We received your support request:\n\n"
                    f"Subject: {subject}\n\n"
                    "We will get back to you within 24 hours.\n\n"
                    "— Hermes Team"
                ),
            )
    except Exception:
        log.exception("support confirmation email failed")

    return jsonify({"success": True, "message": "Ticket created"})


@app.route("/api/admin/support/tickets", methods=["GET"])
@admin_required
def admin_get_support_tickets():
    if db.SessionLocal is None:
        return jsonify({"error": "database unavailable"}), 503
    status_filter = str(request.args.get("status") or "all").strip().lower()
    allowed = {"all", "open", "in-progress", "resolved", "closed"}
    if status_filter not in allowed:
        return jsonify({"error": "Invalid status"}), 400
    eng = db.get_engine()
    if eng is None:
        return jsonify({"error": "database unavailable"}), 503

    base_query = """
        SELECT t.id, t.user_id, t.email, t.subject, t.message, t.status, t.priority,
               t.created_at, t.updated_at,
               u.tier as user_tier,
               (SELECT COUNT(*) FROM support_replies r WHERE r.ticket_id = t.id) as reply_count
        FROM support_tickets t
        LEFT JOIN users u ON u.id = t.user_id
    """
    params: dict[str, Any] = {}
    if status_filter != "all":
        base_query += " WHERE t.status = :status "
        params["status"] = status_filter
    base_query += " ORDER BY t.created_at DESC LIMIT 100"

    with eng.connect() as conn:
        rows = conn.execute(text(base_query), params).mappings().all()

    out: list[dict[str, Any]] = []
    for r in rows:
        d = dict(r)
        for k in ("created_at", "updated_at"):
            if d.get(k) is not None and hasattr(d[k], "isoformat"):
                d[k] = d[k].isoformat()
        out.append(d)
    return jsonify({"tickets": out})


@app.route("/api/admin/support/tickets/<int:ticket_id>", methods=["GET"])
@admin_required
def admin_get_support_ticket_detail(ticket_id: int):
    if db.SessionLocal is None:
        return jsonify({"error": "database unavailable"}), 503
    eng = db.get_engine()
    if eng is None:
        return jsonify({"error": "database unavailable"}), 503
    with eng.connect() as conn:
        ticket = conn.execute(
            text("SELECT * FROM support_tickets WHERE id = :id"),
            {"id": int(ticket_id)},
        ).mappings().first()
        if ticket is None:
            return jsonify({"error": "Not found"}), 404
        replies = conn.execute(
            text("SELECT * FROM support_replies WHERE ticket_id = :id ORDER BY created_at ASC"),
            {"id": int(ticket_id)},
        ).mappings().all()

    ticket_out = dict(ticket)
    for k in ("created_at", "updated_at"):
        if ticket_out.get(k) is not None and hasattr(ticket_out[k], "isoformat"):
            ticket_out[k] = ticket_out[k].isoformat()
    replies_out: list[dict[str, Any]] = []
    for r in replies:
        d = dict(r)
        if d.get("created_at") is not None and hasattr(d["created_at"], "isoformat"):
            d["created_at"] = d["created_at"].isoformat()
        replies_out.append(d)
    return jsonify({"ticket": ticket_out, "replies": replies_out})


@app.route("/api/admin/support/tickets/<int:ticket_id>/reply", methods=["POST"])
@admin_required
def admin_reply_support_ticket(ticket_id: int):
    if db.SessionLocal is None:
        return jsonify({"error": "database unavailable"}), 503
    data = request.get_json(silent=True) or {}
    message = str(data.get("message") or "").strip()
    if not message:
        return jsonify({"error": "Empty message"}), 400
    eng = db.get_engine()
    if eng is None:
        return jsonify({"error": "database unavailable"}), 503

    with eng.begin() as conn:
        ticket = conn.execute(
            text("SELECT id, email, subject FROM support_tickets WHERE id = :id"),
            {"id": int(ticket_id)},
        ).mappings().first()
        if ticket is None:
            return jsonify({"error": "Not found"}), 404
        conn.execute(
            text(
                """
                INSERT INTO support_replies (ticket_id, author_email, author_type, message)
                VALUES (:ticket_id, :author_email, 'admin', :message)
                """
            ),
            {
                "ticket_id": int(ticket_id),
                "author_email": "support@letagentscook.lol",
                "message": message,
            },
        )
        conn.execute(
            text("UPDATE support_tickets SET status = 'in-progress', updated_at = NOW() WHERE id = :id"),
            {"id": int(ticket_id)},
        )

    try:
        if mailer.is_mail_configured():
            mailer.send_smtp_email(
                to_addr=str(ticket["email"]),
                subject=f"[Hermes Support] Re: {str(ticket['subject'])}",
                text_body=f"{message}\n\n---\nHermes Support Team\nhttps://trading.letagentscook.lol",
            )
    except Exception:
        log.exception("support reply email failed")

    return jsonify({"success": True})


@app.route("/api/admin/support/tickets/<int:ticket_id>/status", methods=["POST"])
@admin_required
def admin_update_support_ticket_status(ticket_id: int):
    if db.SessionLocal is None:
        return jsonify({"error": "database unavailable"}), 503
    data = request.get_json(silent=True) or {}
    status = str(data.get("status") or "").strip().lower()
    if status not in {"open", "in-progress", "resolved", "closed"}:
        return jsonify({"error": "Invalid status"}), 400
    eng = db.get_engine()
    if eng is None:
        return jsonify({"error": "database unavailable"}), 503
    with eng.begin() as conn:
        row = conn.execute(
            text("UPDATE support_tickets SET status = :status, updated_at = NOW() WHERE id = :id RETURNING id"),
            {"status": status, "id": int(ticket_id)},
        ).first()
    if row is None:
        return jsonify({"error": "Not found"}), 404
    return jsonify({"success": True})


# ── No-code Agent Builder ────────────────────────────────────────────────────


def _user_agent_counts(sess, user_id: int) -> int:
    row = sess.execute(
        text("""
        SELECT COUNT(*)::int AS c FROM user_agents
        WHERE user_id = :uid AND status != 'deleted'
        """),
        {"uid": user_id},
    ).mappings().first()
    return int(row["c"]) if row else 0


def _serialize_user_agent_row(r: dict) -> dict:
    out = _serialize_row_dt(dict(r))
    pid = out.get("public_id")
    if pid is not None and hasattr(pid, "hex"):
        out["public_id"] = str(pid)
    if isinstance(out.get("config_json"), str):
        try:
            out["config_json"] = json.loads(out["config_json"])
        except (json.JSONDecodeError, TypeError):
            out["config_json"] = {}
    if isinstance(out.get("watcher_config"), str):
        try:
            out["watcher_config"] = json.loads(out["watcher_config"])
        except (json.JSONDecodeError, TypeError):
            out["watcher_config"] = {}
    if not isinstance(out.get("watcher_config"), dict):
        out["watcher_config"] = {}
    return out


WATCHER_DEFAULTS: dict[str, Any] = {
    "polling_interval_sec": 60,
    "max_position_size_pct": 10.0,
    "stop_loss_pct": 2.0,
    "take_profit_pct": 5.0,
    "trailing_stop": False,
    "trailing_stop_pct": 1.5,
    "max_daily_drawdown_pct": 5.0,
    "max_daily_trades": 10,
    "trading_hours_enabled": False,
    "trading_hours_start": "09:00",
    "trading_hours_end": "17:00",
    "trading_days": [1, 2, 3, 4, 5],
    "momentum_lookback": 20,
    "mean_reversion_threshold": 2.0,
    "alert_pnl_drop_pct": 3.0,
    "alert_price_target": 0,
    "priority": "normal",
}

WATCHER_LIMITS: dict[str, dict[str, Any]] = {
    "basic": {"allowed": False},
    "pro": {
        "polling_interval_sec": {"min": 30, "max": 300},
        "max_position_size_pct": {"min": 1, "max": 25},
        "stop_loss_pct": {"min": 0.5, "max": 10},
        "take_profit_pct": {"min": 0, "max": 20},
        "max_daily_drawdown_pct": {"min": 1, "max": 20},
        "max_daily_trades": {"min": 1, "max": 50},
        "trading_hours_enabled": True,
        "priority": "normal",
    },
    "elite": {
        "polling_interval_sec": {"min": 10, "max": 300},
        "max_position_size_pct": {"min": 1, "max": 50},
        "stop_loss_pct": {"min": 0.1, "max": 15},
        "take_profit_pct": {"min": 0, "max": 50},
        "trailing_stop": True,
        "max_daily_drawdown_pct": {"min": 0.5, "max": 30},
        "max_daily_trades": {"min": 1, "max": 200},
        "trading_hours_enabled": True,
        "priority": "high",
    },
    "admin": {
        "polling_interval_sec": {"min": 10, "max": 300},
        "max_position_size_pct": {"min": 1, "max": 50},
        "stop_loss_pct": {"min": 0.1, "max": 15},
        "take_profit_pct": {"min": 0, "max": 50},
        "trailing_stop": True,
        "max_daily_drawdown_pct": {"min": 0.5, "max": 30},
        "max_daily_trades": {"min": 1, "max": 200},
        "trading_hours_enabled": True,
        "priority": "high",
    },
}


def _watcher_limits_for_user(u: Any) -> dict[str, Any]:
    t = normalize_tier(effective_tier(u))
    if t not in WATCHER_LIMITS:
        t = "basic"
    return {"tier": t, **WATCHER_LIMITS[t]}


def _normalize_watcher_config(raw: Any) -> dict[str, Any]:
    src = raw if isinstance(raw, dict) else {}
    cfg = {**WATCHER_DEFAULTS, **src}
    # normalize trading_days
    td = cfg.get("trading_days")
    if not isinstance(td, list):
        td = WATCHER_DEFAULTS["trading_days"]
    clean = []
    for d in td:
        try:
            di = int(d)
            if 1 <= di <= 7:
                clean.append(di)
        except (TypeError, ValueError):
            pass
    cfg["trading_days"] = clean or WATCHER_DEFAULTS["trading_days"]
    cfg["priority"] = "high" if str(cfg.get("priority") or "normal").lower() == "high" else "normal"
    cfg["trailing_stop"] = bool(cfg.get("trailing_stop"))
    cfg["trading_hours_enabled"] = bool(cfg.get("trading_hours_enabled"))
    return cfg


def _validate_watcher_config_for_user(u: Any, incoming: Any) -> tuple[dict[str, Any] | None, str | None]:
    lim = _watcher_limits_for_user(u)
    if not lim.get("allowed", True):
        return None, "Custom watcher nastavenia sú dostupné od Pro tieru."
    data = incoming if isinstance(incoming, dict) else {}
    cfg = _normalize_watcher_config(data)

    def _clamp_num(key: str, cast_type=float):
        if key not in cfg or key not in lim or not isinstance(lim[key], dict):
            return
        lo = lim[key].get("min")
        hi = lim[key].get("max")
        try:
            val = cast_type(cfg[key])
        except (TypeError, ValueError):
            raise ValueError(f"Neplatná hodnota pre {key}.")
        if lo is not None and val < lo:
            raise ValueError(f"{key} musí byť >= {lo}.")
        if hi is not None and val > hi:
            raise ValueError(f"{key} musí byť <= {hi}.")
        cfg[key] = int(val) if cast_type is int else float(val)

    try:
        _clamp_num("polling_interval_sec", int)
        _clamp_num("max_position_size_pct", float)
        _clamp_num("stop_loss_pct", float)
        _clamp_num("take_profit_pct", float)
        _clamp_num("max_daily_drawdown_pct", float)
        _clamp_num("max_daily_trades", int)
    except ValueError as exc:
        return None, str(exc)

    if lim.get("priority") != "high" and cfg.get("priority") == "high":
        return None, "Priority 'high' je dostupná len pre Elite."
    if not lim.get("trailing_stop", False):
        cfg["trailing_stop"] = False
    if lim.get("trading_hours_enabled") is not True:
        cfg["trading_hours_enabled"] = False
    return cfg, None


def _owner_user_agent_row(sess, user_id: int, agent_id: int):
    return sess.execute(
        text(
            """
            SELECT id, user_id, name, strategy_type, watcher_config
            FROM user_agents
            WHERE id = :id AND user_id = :uid AND status != 'deleted'
            """
        ),
        {"id": int(agent_id), "uid": int(user_id)},
    ).mappings().first()


@app.route("/api/agents/user/<int:agent_id>/watcher-settings", methods=["GET"])
@login_required
def api_user_agent_watcher_settings_get(agent_id: int):
    if db.SessionLocal is None:
        return jsonify({"error": "database unavailable"}), 503
    u = _marketplace_db_user()
    if u is None:
        return jsonify({"error": "Vyžaduje sa registrovaný účet."}), 403
    sess = db.db_session()
    row = _owner_user_agent_row(sess, int(u.id), int(agent_id))
    if not row:
        return jsonify({"error": "Agent neexistuje alebo k nemu nemáš prístup."}), 404
    cfg = _normalize_watcher_config(row.get("watcher_config"))
    return jsonify(
        {
            "agent_id": int(agent_id),
            "agent_name": row.get("name") or "",
            "strategy_type": row.get("strategy_type") or "",
            "watcher_config": cfg,
            "tier_limits": _watcher_limits_for_user(u),
            "defaults": WATCHER_DEFAULTS,
        }
    )


@app.route("/api/agents/user/<int:agent_id>/watcher-settings", methods=["POST"])
@login_required
def api_user_agent_watcher_settings_post(agent_id: int):
    if db.SessionLocal is None:
        return jsonify({"error": "database unavailable"}), 503
    u = _marketplace_db_user()
    if u is None:
        return jsonify({"error": "Vyžaduje sa registrovaný účet."}), 403
    body = request.get_json(silent=True) or {}
    raw_cfg = body.get("watcher_config")
    cfg, err = _validate_watcher_config_for_user(u, raw_cfg)
    if err:
        code = 403 if "Pro tieru" in err or "Elite" in err else 400
        return jsonify({"error": err}), code
    sess = db.db_session()
    row = _owner_user_agent_row(sess, int(u.id), int(agent_id))
    if not row:
        return jsonify({"error": "Agent neexistuje alebo k nemu nemáš prístup."}), 404
    try:
        sess.execute(
            text(
                """
                UPDATE user_agents
                SET watcher_config = CAST(:cfg AS jsonb), updated_at = NOW()
                WHERE id = :id AND user_id = :uid
                """
            ),
            {"cfg": json.dumps(cfg), "id": int(agent_id), "uid": int(u.id)},
        )
        sess.commit()
    except Exception:  # noqa: BLE001
        sess.rollback()
        log.exception("save watcher settings")
        return jsonify({"error": "Nepodarilo sa uložiť watcher nastavenia."}), 500
    return jsonify({"success": True, "watcher_config": cfg})


@app.route("/api/agents/user/<int:agent_id>/reset-watcher-settings", methods=["POST"])
@login_required
def api_user_agent_watcher_settings_reset(agent_id: int):
    if db.SessionLocal is None:
        return jsonify({"error": "database unavailable"}), 503
    u = _marketplace_db_user()
    if u is None:
        return jsonify({"error": "Vyžaduje sa registrovaný účet."}), 403
    sess = db.db_session()
    row = _owner_user_agent_row(sess, int(u.id), int(agent_id))
    if not row:
        return jsonify({"error": "Agent neexistuje alebo k nemu nemáš prístup."}), 404
    try:
        sess.execute(
            text(
                """
                UPDATE user_agents
                SET watcher_config = '{}'::jsonb, updated_at = NOW()
                WHERE id = :id AND user_id = :uid
                """
            ),
            {"id": int(agent_id), "uid": int(u.id)},
        )
        sess.commit()
    except Exception:  # noqa: BLE001
        sess.rollback()
        log.exception("reset watcher settings")
        return jsonify({"error": "Reset watcher nastavení zlyhal."}), 500
    return jsonify({"success": True, "watcher_config": WATCHER_DEFAULTS})


@app.route("/api/agent-builder/create", methods=["POST"])
@login_required
def api_agent_builder_create():
    if db.SessionLocal is None:
        return jsonify({"error": "database unavailable"}), 503
    u = _marketplace_db_user()
    if u is None:
        return jsonify({"error": "Vyžaduje sa registrovaný účet."}), 403
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name or len(name) > 100:
        return jsonify({"error": "Meno agenta je povinné (max 100 znakov)."}), 400
    sym = (data.get("symbol") or "").strip().upper().replace("/USD", "").replace("-USD", "")
    if sym not in ALLOWED_SYMBOLS:
        return jsonify({"error": "Neplatný symbol."}), 400
    st = (data.get("strategy_type") or "").strip().lower()
    if st not in ALLOWED_STRATEGIES:
        return jsonify({"error": "Neplatná stratégia."}), 400
    cfg = data.get("config_json")
    if cfg is None or not isinstance(cfg, dict):
        return jsonify({"error": "config_json musí byť objekt."}), 400
    cfg = dict(cfg)
    pair = symbol_to_pair(sym)

    sess = db.db_session()
    try:
        cap = user_agent_cap_for_user(u)
        cur = _user_agent_counts(sess, u.id)
        if cap is not None and cur >= cap:
            return jsonify({
                "error": "Dosiahol si limit vlastných agentov pre svoj plán.",
                "upgrade_required": True,
                "limit": cap,
                "count": cur,
            }), 403
        row = sess.execute(
            text("""
            INSERT INTO user_agents (user_id, name, symbol, strategy_type, config_json, status)
            VALUES (:uid, :name, :symbol, :stype, CAST(:cfg AS jsonb), 'active')
            RETURNING id, user_id, name, symbol, strategy_type, config_json, status,
                      is_public, public_id, marketplace_status,
                      description, published_at, clone_count, popularity_score, marketplace_reject_reason,
                      created_at, updated_at
            """),
            {
                "uid": u.id,
                "name": name[:100],
                "symbol": pair,
                "stype": st,
                "cfg": json.dumps(cfg),
            },
        ).mappings().first()
        sess.commit()
        if not row:
            return jsonify({"error": "Nepodarilo sa vytvoriť agenta."}), 500
        agent = _serialize_user_agent_row(dict(row))
        return jsonify({
            "ok": True,
            "agent": agent,
            "limit": cap,
            "count": cur + 1,
        })
    except Exception:  # noqa: BLE001
        sess.rollback()
        log.exception("agent-builder create")
        return jsonify({"error": "Chyba pri vytváraní agenta."}), 500


@app.route("/api/agent-builder/my-agents", methods=["GET"])
@login_required
def api_agent_builder_my_agents():
    if db.SessionLocal is None:
        return jsonify({"error": "database unavailable"}), 503
    u = _marketplace_db_user()
    if u is None:
        return jsonify({"error": "Vyžaduje sa registrovaný účet."}), 403
    sess = db.db_session()
    try:
        rows = sess.execute(
            text("""
            SELECT ua.*,
                   COALESCE(s.cnt, 0)::int AS total_trades,
                   COALESCE(s.pnl_sum, 0.0)::double precision AS total_pnl,
                   COALESCE(s.win_rate, 0.0) AS win_rate
            FROM user_agents ua
            LEFT JOIN (
                SELECT user_agent_id,
                       COUNT(*)::int AS cnt,
                       COALESCE(SUM(pnl), 0)::double precision AS pnl_sum,
                       CASE WHEN COUNT(*) = 0 THEN 0.0
                            ELSE (100.0 * SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) / COUNT(*))
                       END AS win_rate
                FROM paper_trades
                WHERE user_agent_id IS NOT NULL
                GROUP BY user_agent_id
            ) s ON s.user_agent_id = ua.id
            WHERE ua.user_id = :uid AND ua.status != 'deleted'
            ORDER BY ua.created_at DESC
            """),
            {"uid": u.id},
        ).mappings().all()
    except Exception:  # noqa: BLE001
        log.exception("agent-builder my-agents")
        return jsonify({"error": "Nepodarilo sa načítať agentov."}), 500

    agents_out: list[dict] = []
    for r in rows:
        d = _serialize_user_agent_row(dict(r))
        ua_id = d.get("id")
        trades: list[dict] = []
        if ua_id is not None:
            tr = sess.execute(
                text("""
                SELECT id, symbol, action, price, quantity, pnl, timestamp
                FROM paper_trades
                WHERE user_agent_id = :uaid
                ORDER BY timestamp DESC
                LIMIT 5
                """),
                {"uaid": int(ua_id)},
            ).mappings().all()
            trades = [_serialize_row_dt(dict(x)) for x in tr]
        d["recent_trades"] = trades
        agents_out.append(d)

    cap = user_agent_cap_for_user(u)
    count = _user_agent_counts(sess, u.id)
    return jsonify({
        "agents": agents_out,
        "limit": cap,
        "count": count,
        "unlimited": cap is None,
        "strategy_labels": STRATEGY_LABELS,
    })


@app.route("/api/agent-builder/<int:agent_id>/status", methods=["PATCH"])
@login_required
def api_agent_builder_patch_status(agent_id: int):
    if db.SessionLocal is None:
        return jsonify({"error": "database unavailable"}), 503
    u = _marketplace_db_user()
    if u is None:
        return jsonify({"error": "Vyžaduje sa registrovaný účet."}), 403
    data = request.get_json(silent=True) or {}
    status = (data.get("status") or "").strip().lower()
    if status not in ("active", "paused"):
        return jsonify({"error": "status musí byť active alebo paused."}), 400
    sess = db.db_session()
    try:
        row = sess.execute(
            text("""
            UPDATE user_agents SET status = :st, updated_at = NOW()
            WHERE id = :id AND user_id = :uid AND status != 'deleted'
            RETURNING id, user_id, name, symbol, strategy_type, config_json, status,
                      is_public, public_id, marketplace_status,
                      description, published_at, clone_count, popularity_score, marketplace_reject_reason,
                      created_at, updated_at
            """),
            {"st": status, "id": agent_id, "uid": u.id},
        ).mappings().first()
        sess.commit()
        if not row:
            return jsonify({"error": "Agent neexistuje alebo k nemu nemáš prístup."}), 404
        return jsonify({"ok": True, "agent": _serialize_user_agent_row(dict(row))})
    except Exception:  # noqa: BLE001
        sess.rollback()
        log.exception("agent-builder patch")
        return jsonify({"error": "Chyba pri úprave stavu."}), 500


@app.route("/api/agent-builder/<int:agent_id>", methods=["DELETE"])
@login_required
def api_agent_builder_delete(agent_id: int):
    if db.SessionLocal is None:
        return jsonify({"error": "database unavailable"}), 503
    u = _marketplace_db_user()
    if u is None:
        return jsonify({"error": "Vyžaduje sa registrovaný účet."}), 403
    sess = db.db_session()
    try:
        row = sess.execute(
            text("""
            UPDATE user_agents SET status = 'deleted', updated_at = NOW()
            WHERE id = :id AND user_id = :uid AND status != 'deleted'
            RETURNING id
            """),
            {"id": agent_id, "uid": u.id},
        ).first()
        sess.commit()
        if row is None:
            return jsonify({"error": "Agent neexistuje alebo už bol zmazaný."}), 404
        return jsonify({"ok": True})
    except Exception:  # noqa: BLE001
        sess.rollback()
        log.exception("agent-builder delete")
        return jsonify({"error": "Chyba pri mazaní."}), 500


@app.route("/api/agent-builder/ai-summary", methods=["POST"])
@login_required
def api_agent_builder_ai_summary():
    if db.SessionLocal is None:
        return jsonify({"error": "database unavailable"}), 503
    u = _marketplace_db_user()
    if u is None:
        return jsonify({"error": "Vyžaduje sa registrovaný účet."}), 403
    _ = u  # auth side-effect
    data = request.get_json(silent=True) or {}
    sym = (data.get("symbol") or "").strip().upper().replace("/USD", "").replace("-USD", "")
    if sym not in ALLOWED_SYMBOLS:
        sym = "BTC"
    st = (data.get("strategy_type") or "momentum").strip().lower()
    if st not in ALLOWED_STRATEGIES:
        st = "momentum"
    cfg = data.get("config_json") if isinstance(data.get("config_json"), dict) else {}
    summary = generate_ai_summary_sync(symbol_to_pair(sym), st, cfg)
    return jsonify({"summary": summary})


@app.route("/api/ai/builder", methods=["POST"])
@login_required
def ai_builder():
    import re  # noqa: PLC0415
    import json as json_lib  # noqa: PLC0415

    if not ANTHROPIC_AVAILABLE:
        return jsonify({"error": "Anthropic SDK not available", "agentConfig": None}), 503
    api_key = (os.environ.get("ANTHROPIC_API_KEY") or "").strip()
    if not api_key:
        return jsonify({"error": "ANTHROPIC_API_KEY not configured", "agentConfig": None}), 503

    data = request.get_json(silent=True) or {}
    messages = data.get("messages", [])
    if not isinstance(messages, list):
        messages = []

    system_prompt = """You are an AI trading agent builder for Hermes Trading Platform.
Help users create trading agents through conversation.
When user describes an agent, extract parameters and respond in this EXACT format:

<message>Your friendly 1-2 sentence response here</message>
<config>{"name": "...", "symbol": "BTC/USD|ETH/USD|SOL/USD|GLD|AAPL|NVDA|EUR/USD", "category": "crypto|stocks|commodities|forex", "strategy": "Momentum|Swing|Scalping|DCA|Grid", "risk": "low|medium|high", "indicators": ["RSI", "MACD", "EMA", "BB"]}</config>

If you need more info, ask ONE clarifying question and omit <config>.
Keep responses short (1-2 sentences). Be friendly and trading-focused."""

    try:
        ai_client = anthropic.Anthropic(api_key=api_key)
        response = ai_client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=400,
            system=system_prompt,
            messages=[
                {"role": m.get("role"), "content": m.get("content")}
                for m in messages[-10:]
                if isinstance(m, dict) and m.get("role") in {"user", "assistant"} and m.get("content")
            ],
        )
        text_parts: list[str] = []
        for block in response.content:
            if getattr(block, "type", None) == "text":
                text_parts.append(getattr(block, "text", "") or "")
        full = "".join(text_parts).strip()
        msg_match = re.search(r"<message>(.*?)</message>", full, re.DOTALL)
        cfg_match = re.search(r"<config>(.*?)</config>", full, re.DOTALL)
        message = msg_match.group(1).strip() if msg_match else full.strip()
        agent_config = None
        if cfg_match:
            try:
                agent_config = json_lib.loads(cfg_match.group(1))
            except Exception:  # noqa: BLE001
                pass
        return jsonify({"message": message, "agentConfig": agent_config})
    except Exception as e:  # noqa: BLE001
        app.logger.error(f"AI builder error: {e}")
        return jsonify({"message": "I'm having trouble right now. Try describing your agent again!", "agentConfig": None})


@app.route("/api/intelligence/feed", methods=["GET"])
@login_required
def intelligence_feed():
    symbol = str(request.args.get("symbol") or "").strip()
    report_type = str(request.args.get("type", "all") or "all").strip().lower()
    try:
        limit = int(request.args.get("limit", 20))
    except (TypeError, ValueError):
        limit = 20
    limit = max(1, min(limit, 50))
    eng = db.get_engine()
    if eng is None:
        return jsonify({"error": "database unavailable"}), 503
    where = "WHERE 1=1"
    params: dict[str, Any] = {"lim": limit}
    if symbol:
        where += " AND symbol = :sym"
        params["sym"] = symbol
    if report_type != "all":
        where += " AND report_type = :rtype"
        params["rtype"] = report_type
    with eng.connect() as conn:
        rows = conn.execute(
            text(
                f"""
                SELECT id, report_type, symbol, title, sentiment, sentiment_score, source, tags, agent_id, created_at
                FROM intelligence_reports
                {where}
                ORDER BY created_at DESC
                LIMIT :lim
                """
            ),
            params,
        ).mappings().all()
    return jsonify([_serialize_row_dt(dict(row)) for row in rows])


@app.route("/api/intelligence/sentiment", methods=["GET"])
@login_required
def market_sentiment():
    eng = db.get_engine()
    if eng is None:
        return jsonify({"error": "database unavailable"}), 503
    with eng.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT
                    symbol,
                    COUNT(*)::int AS total,
                    ROUND(AVG(sentiment_score)::numeric, 3) AS avg_score,
                    COUNT(CASE WHEN sentiment='positive' THEN 1 END)::int AS positive,
                    COUNT(CASE WHEN sentiment='negative' THEN 1 END)::int AS negative,
                    MAX(created_at) AS last_update
                FROM intelligence_reports
                WHERE created_at > NOW() - INTERVAL '24 hours'
                    AND symbol IS NOT NULL
                GROUP BY symbol
                ORDER BY total DESC
                """
            )
        ).mappings().all()
    return jsonify([_serialize_row_dt(dict(row)) for row in rows])


@app.route("/api/agents/pnl", methods=["GET"])
@login_required
def api_agents_pnl():
    if db.SessionLocal is None:
        return jsonify({"error": "database unavailable"}), 503
    u = _marketplace_db_user()
    if u is None:
        return jsonify({"error": "Marketplace requires a registered account."}), 403
    return jsonify(get_live_pnl_payload(u.id))


@app.route("/api/agents/badges", methods=["GET"])
@login_required
def api_agents_badges():
    """Badge metadata per subscribed agent (from agent_performance when migrated, else paper_trades)."""
    if db.SessionLocal is None:
        return jsonify({"error": "database unavailable"}), 503
    u = _marketplace_db_user()
    if u is None:
        return jsonify({"error": "Marketplace requires a registered account."}), 403
    sess = db.db_session()
    perf_by_agent = grouped_performance_from_table(sess, u.id)
    top_ids = compute_top_gainers_24h(sess, u.id)
    subs = get_user_subscriptions(u.id)
    result: dict[str, list[dict[str, str]]] = {}

    def _serialize(ids: list[str]) -> list[dict[str, str]]:
        return [{**BADGE_DEFINITIONS[b], "key": b} for b in ids if b in BADGE_DEFINITIONS]

    if perf_by_agent is not None:
        for s in subs:
            aid = str(s["agent_id"])
            perf_rows = perf_by_agent.get(aid, [])
            bids = merge_badge_ids(compute_badges_for_agent(aid, perf_rows), top_ids, aid)
            result[aid] = _serialize(bids)
        return jsonify({"badges": result})

    id_to_badges = compute_user_badges_map(sess, u.id)
    for s in subs:
        aid = str(s["agent_id"])
        result[aid] = _serialize(id_to_badges.get(aid, []))
    return jsonify({"badges": result})


@app.route("/api/alerts/rules", methods=["GET"])
@login_required
def api_alerts_rules_list():
    if db.SessionLocal is None:
        return jsonify({"error": "database unavailable"}), 503
    u = _marketplace_db_user()
    if u is None:
        return jsonify({"error": "Marketplace requires a registered account."}), 403
    sess = db.db_session()
    try:
        rows = sess.execute(
            text("""
            SELECT ar.id, ar.user_id, ar.agent_id, ar.alert_type, ar.threshold, ar.is_enabled,
                   ar.last_triggered_at, ar.created_at,
                   ta.name AS agent_name, ta.symbol AS agent_symbol
            FROM alert_rules ar
            JOIN trading_agents ta ON ta.id = ar.agent_id
            WHERE ar.user_id = :uid
            ORDER BY ar.agent_id, ar.alert_type
            """),
            {"uid": u.id},
        ).mappings().all()
    except Exception:  # noqa: BLE001
        log.exception("alert rules list")
        return jsonify({"error": "Could not load alert rules."}), 500
    return jsonify({"rules": [_serialize_row_dt(dict(r)) for r in rows]})


@app.route("/api/alerts/rules", methods=["POST"])
@login_required
def api_alerts_rules_upsert():
    if db.SessionLocal is None:
        return jsonify({"error": "database unavailable"}), 503
    u = _marketplace_db_user()
    if u is None:
        return jsonify({"error": "Marketplace requires a registered account."}), 403
    data = request.get_json(silent=True) or {}
    agent_id = data.get("agent_id")
    alert_type = (data.get("alert_type") or "").strip()
    allowed = frozenset({"pnl_drop", "agent_inactive", "price_target", "weekly_summary"})
    if not agent_id or alert_type not in allowed:
        return jsonify({"ok": False, "error": "agent_id and valid alert_type required"}), 400
    agent_id = str(agent_id).strip()[:64]
    try:
        threshold = float(data.get("threshold", 5))
    except (TypeError, ValueError):
        threshold = 5.0
    is_enabled = bool(data.get("is_enabled", True))

    sess = db.db_session()
    sub = sess.execute(
        text("""
        SELECT 1 FROM user_subscriptions
        WHERE user_id = :uid AND agent_id = :aid AND is_active IS TRUE
        LIMIT 1
        """),
        {"uid": u.id, "aid": agent_id},
    ).first()
    if not sub:
        return jsonify({"ok": False, "error": "Not subscribed to this agent."}), 403

    limits = get_tier_limits(effective_tier(u))
    max_alerts = limits.get("max_alerts")
    existing_en = sess.execute(
        text("""
        SELECT is_enabled FROM alert_rules
        WHERE user_id = :uid AND agent_id = :aid AND alert_type = :atype
        """),
        {"uid": u.id, "aid": agent_id, "atype": alert_type},
    ).mappings().first()
    prev_on = bool(existing_en and existing_en["is_enabled"])
    if is_enabled and isinstance(max_alerts, int):
        enabled_total = int(
            sess.execute(
                text("""
                SELECT COUNT(*) FROM alert_rules
                WHERE user_id = :uid AND is_enabled IS TRUE
                """),
                {"uid": u.id},
            ).scalar() or 0,
        )
        if not prev_on and enabled_total >= max_alerts:
            return jsonify({
                "ok": False,
                "error": "alert_limit_reached",
                "message": f"Tvoj plán umožňuje max {max_alerts} aktívnych alertov.",
                "upgrade_required": True,
            }), 403

    try:
        sess.execute(
            text("""
            INSERT INTO alert_rules (user_id, agent_id, alert_type, threshold, is_enabled)
            VALUES (:uid, :aid, :atype, :thr, :en)
            ON CONFLICT (user_id, agent_id, alert_type)
            DO UPDATE SET
                threshold = EXCLUDED.threshold,
                is_enabled = EXCLUDED.is_enabled
            """),
            {
                "uid": u.id,
                "aid": agent_id,
                "atype": alert_type,
                "thr": threshold,
                "en": is_enabled,
            },
        )
        sess.commit()
        row = sess.execute(
            text("""
            SELECT ar.id, ar.user_id, ar.agent_id, ar.alert_type, ar.threshold, ar.is_enabled,
                   ar.last_triggered_at, ar.created_at,
                   ta.name AS agent_name, ta.symbol AS agent_symbol
            FROM alert_rules ar
            JOIN trading_agents ta ON ta.id = ar.agent_id
            WHERE ar.user_id = :uid AND ar.agent_id = :aid AND ar.alert_type = :atype
            """),
            {"uid": u.id, "aid": agent_id, "atype": alert_type},
        ).mappings().first()
    except Exception:  # noqa: BLE001
        log.exception("alert rules upsert")
        sess.rollback()
        return jsonify({"ok": False, "error": "Could not save alert rule."}), 500
    if not row:
        return jsonify({"ok": False, "error": "Rule not found after save."}), 500
    return jsonify({"ok": True, "rule": _serialize_row_dt(dict(row))})


@app.route("/api/alerts/rules/<int:rule_id>", methods=["DELETE"])
@login_required
def api_alerts_rules_delete(rule_id: int):
    if db.SessionLocal is None:
        return jsonify({"error": "database unavailable"}), 503
    u = _marketplace_db_user()
    if u is None:
        return jsonify({"error": "Marketplace requires a registered account."}), 403
    sess = db.db_session()
    try:
        row = sess.execute(
            text("DELETE FROM alert_rules WHERE id = :rid AND user_id = :uid RETURNING id"),
            {"rid": rule_id, "uid": u.id},
        ).fetchone()
        sess.commit()
        if row is None:
            return jsonify({"ok": False, "error": "Rule not found."}), 404
    except Exception:  # noqa: BLE001
        log.exception("alert rules delete")
        sess.rollback()
        return jsonify({"ok": False, "error": "Could not delete rule."}), 500
    return jsonify({"ok": True})


@app.route("/api/alerts/rules/<int:rule_id>/toggle", methods=["POST"])
@login_required
def api_alerts_rules_toggle(rule_id: int):
    if db.SessionLocal is None:
        return jsonify({"error": "database unavailable"}), 503
    u = _marketplace_db_user()
    if u is None:
        return jsonify({"error": "Marketplace requires a registered account."}), 403
    sess = db.db_session()
    try:
        existing = sess.execute(
            text(
                """
                SELECT id, is_enabled
                FROM alert_rules
                WHERE id = :rid AND user_id = :uid
                """
            ),
            {"rid": rule_id, "uid": u.id},
        ).mappings().first()
    except Exception:  # noqa: BLE001
        log.exception("alert rules toggle select")
        return jsonify({"ok": False, "error": "Could not load alert rule."}), 500
    if not existing:
        return jsonify({"ok": False, "error": "Rule not found."}), 404

    prev_on = bool(existing["is_enabled"])
    next_on = not prev_on

    if next_on:
        limits = get_tier_limits(effective_tier(u))
        max_alerts = limits.get("max_alerts")
        if isinstance(max_alerts, int):
            enabled_total = int(
                sess.execute(
                    text(
                        """
                        SELECT COUNT(*) FROM alert_rules
                        WHERE user_id = :uid AND is_enabled IS TRUE
                        """
                    ),
                    {"uid": u.id},
                ).scalar()
                or 0,
            )
            if not prev_on and enabled_total >= max_alerts:
                return jsonify(
                    {
                        "ok": False,
                        "error": "alert_limit_reached",
                        "message": f"Tvoj plán umožňuje max {max_alerts} aktívnych alertov.",
                        "upgrade_required": True,
                    }
                ), 403

    try:
        sess.execute(
            text(
                """
                UPDATE alert_rules
                SET is_enabled = :en
                WHERE id = :rid AND user_id = :uid
                """
            ),
            {"en": next_on, "rid": rule_id, "uid": u.id},
        )
        sess.commit()
        row = sess.execute(
            text(
                """
                SELECT ar.id, ar.user_id, ar.agent_id, ar.alert_type, ar.threshold, ar.is_enabled,
                       ar.last_triggered_at, ar.created_at,
                       ta.name AS agent_name, ta.symbol AS agent_symbol
                FROM alert_rules ar
                JOIN trading_agents ta ON ta.id = ar.agent_id
                WHERE ar.id = :rid AND ar.user_id = :uid
                """
            ),
            {"rid": rule_id, "uid": u.id},
        ).mappings().first()
    except Exception:  # noqa: BLE001
        log.exception("alert rules toggle update")
        sess.rollback()
        return jsonify({"ok": False, "error": "Could not toggle alert rule."}), 500
    if not row:
        return jsonify({"ok": False, "error": "Rule not found after toggle."}), 500
    return jsonify({"ok": True, "rule": _serialize_row_dt(dict(row))})


@app.route("/api/notifications", methods=["GET"])
@login_required
def api_notifications_list():
    if db.SessionLocal is None:
        return jsonify({"error": "database unavailable"}), 503
    u = _marketplace_db_user()
    if u is None:
        return jsonify({"error": "Notifications require a registered account."}), 403
    sess = db.db_session()
    rows = sess.execute(
        text("""
        SELECT * FROM notifications
        WHERE user_id = :uid OR user_id IS NULL
        ORDER BY created_at DESC
        LIMIT 50
        """),
        {"uid": u.id},
    ).mappings().all()
    notifs = [_serialize_row_dt(dict(r)) for r in rows]
    unread = sum(1 for n in notifs if not bool(n.get("is_read")))
    return jsonify({"notifications": notifs, "unread": unread})


@app.route("/api/notifications/read", methods=["POST"])
@login_required
def api_notifications_read():
    if db.SessionLocal is None:
        return jsonify({"error": "database unavailable"}), 503
    u = _marketplace_db_user()
    if u is None:
        return jsonify({"error": "Notifications require a registered account."}), 403
    sess = db.db_session()
    sess.execute(
        text("UPDATE notifications SET is_read = true WHERE user_id = :uid"),
        {"uid": u.id},
    )
    sess.commit()
    return jsonify({"success": True})


@app.route("/api/notifications/unread-count", methods=["GET"])
@login_required
def api_notifications_unread_count():
    """Cheap polling endpoint — single int back. Counts user-specific + broadcast (user_id IS NULL)."""
    if db.SessionLocal is None:
        return jsonify({"error": "database unavailable"}), 503
    u = _marketplace_db_user()
    if u is None:
        return jsonify({"unread": 0})
    sess = db.db_session()
    try:
        row = sess.execute(
            text(
                """
                SELECT COUNT(*)::int AS c
                FROM notifications
                WHERE is_read = FALSE
                  AND (user_id = :uid OR user_id IS NULL)
                """
            ),
            {"uid": u.id},
        ).mappings().first()
        return jsonify({"unread": int(row["c"]) if row else 0})
    finally:
        sess.close()


@app.route("/api/notifications/<int:notif_id>/read", methods=["POST"])
@login_required
def api_notifications_read_one(notif_id: int):
    """Mark a single notification as read (only the owner can flip it)."""
    if db.SessionLocal is None:
        return jsonify({"error": "database unavailable"}), 503
    u = _marketplace_db_user()
    if u is None:
        return jsonify({"error": "Notifications require a registered account."}), 403
    sess = db.db_session()
    try:
        sess.execute(
            text(
                """
                UPDATE notifications SET is_read = TRUE
                WHERE id = :id AND (user_id = :uid OR user_id IS NULL)
                """
            ),
            {"id": notif_id, "uid": u.id},
        )
        sess.commit()
        return jsonify({"success": True})
    except Exception:  # noqa: BLE001
        sess.rollback()
        log.exception("notifications mark single")
        return jsonify({"error": "Označenie zlyhalo."}), 500
    finally:
        sess.close()


# ─────────────────────────────────────────────────────────────────────────────
# Community Feed (CMC-style) — posts + likes + sentiment
# ─────────────────────────────────────────────────────────────────────────────

_COMMUNITY_MAX_LEN = 600
_COMMUNITY_MIN_LEN = 2
_COMMUNITY_VALID_SENTIMENT = {"bullish", "bearish"}


def _community_serialize_row(row: dict, viewer_id: int | None) -> dict:
    return {
        "id": int(row["id"]),
        "user_id": int(row["user_id"]),
        "username": row.get("username") or "agent",
        "symbol": row.get("symbol"),
        "content": row.get("content") or "",
        "sentiment": row.get("sentiment"),
        "likes_count": int(row.get("likes_count") or 0),
        "comments_count": int(row.get("comments_count") or 0),
        "views_count": int(row.get("views_count") or 0),
        "is_liked": bool(row.get("is_liked")) if viewer_id else False,
        "is_own": bool(viewer_id and int(row["user_id"]) == int(viewer_id)),
        "created_at": (row["created_at"].isoformat() if row.get("created_at") else None),
    }


@app.route("/api/community/posts", methods=["GET"])
def api_community_posts_list():
    """
    Public read-only feed.
    Query params:
      tab=top|latest (default latest)
      symbol=BTC (optional filter)
      limit=<int 1..50> (default 20)
    """
    if db.SessionLocal is None:
        return jsonify({"error": "database unavailable"}), 503

    tab = (request.args.get("tab") or "latest").lower()
    if tab not in ("top", "latest"):
        tab = "latest"
    symbol = (request.args.get("symbol") or "").strip().upper() or None
    try:
        limit = max(1, min(50, int(request.args.get("limit") or 20)))
    except (TypeError, ValueError):
        limit = 20

    viewer_id: int | None = None
    try:
        viewer_id = int(session.get("user_id")) if session.get("user_id") else None
    except (TypeError, ValueError):
        viewer_id = None

    order_clause = (
        "p.likes_count DESC, p.created_at DESC"
        if tab == "top"
        else "p.created_at DESC"
    )

    sess = db.db_session()
    try:
        sql = f"""
            SELECT
                p.id, p.user_id, p.symbol, p.content, p.sentiment,
                p.likes_count, p.comments_count, p.views_count, p.created_at,
                u.username,
                CASE WHEN :viewer_id IS NULL THEN FALSE
                     ELSE EXISTS (
                        SELECT 1 FROM community_post_likes l
                         WHERE l.post_id = p.id AND l.user_id = :viewer_id
                     ) END AS is_liked
            FROM community_posts p
            JOIN users u ON u.id = p.user_id
            WHERE (:symbol IS NULL OR UPPER(p.symbol) = :symbol)
            ORDER BY {order_clause}
            LIMIT :lim
        """
        rows = sess.execute(
            text(sql),
            {"viewer_id": viewer_id, "symbol": symbol, "lim": limit},
        ).mappings().all()
        posts = [_community_serialize_row(dict(r), viewer_id) for r in rows]
        return jsonify({"posts": posts, "tab": tab})
    except Exception:  # noqa: BLE001
        log.exception("community posts list")
        return jsonify({"error": "Failed to load community feed."}), 500
    finally:
        sess.close()


@app.route("/api/community/posts", methods=["POST"])
@login_required
def api_community_posts_create():
    if db.SessionLocal is None:
        return jsonify({"error": "database unavailable"}), 503
    u = _marketplace_db_user()
    if u is None:
        return jsonify({"error": "Posting requires a registered account."}), 403

    body = request.get_json(silent=True) or {}
    content = (body.get("content") or "").strip()
    sentiment = (body.get("sentiment") or "").strip().lower() or None
    symbol_raw = (body.get("symbol") or "").strip().upper() or None

    if len(content) < _COMMUNITY_MIN_LEN:
        return jsonify({"error": "Post is too short."}), 400
    if len(content) > _COMMUNITY_MAX_LEN:
        return jsonify({"error": f"Post exceeds {_COMMUNITY_MAX_LEN} characters."}), 400
    if sentiment is not None and sentiment not in _COMMUNITY_VALID_SENTIMENT:
        return jsonify({"error": "Invalid sentiment."}), 400
    symbol = symbol_raw[:24] if symbol_raw else None

    sess = db.db_session()
    try:
        row = sess.execute(
            text(
                """
                INSERT INTO community_posts (user_id, symbol, content, sentiment)
                VALUES (:uid, :sym, :content, :sent)
                RETURNING id, user_id, symbol, content, sentiment,
                          likes_count, comments_count, views_count, created_at
                """
            ),
            {"uid": u.id, "sym": symbol, "content": content, "sent": sentiment},
        ).mappings().first()
        sess.commit()
        if not row:
            return jsonify({"error": "Could not save post."}), 500
        post = dict(row)
        post["username"] = u.username
        post["is_liked"] = False
        return jsonify({"post": _community_serialize_row(post, u.id)}), 201
    except Exception:  # noqa: BLE001
        sess.rollback()
        log.exception("community post create")
        return jsonify({"error": "Could not save post."}), 500
    finally:
        sess.close()


@app.route("/api/community/posts/<int:post_id>", methods=["DELETE"])
@login_required
def api_community_posts_delete(post_id: int):
    if db.SessionLocal is None:
        return jsonify({"error": "database unavailable"}), 503
    u = _marketplace_db_user()
    if u is None:
        return jsonify({"error": "Auth required."}), 403
    sess = db.db_session()
    try:
        is_admin = bool(getattr(u, "is_admin", False))
        if is_admin:
            res = sess.execute(
                text("DELETE FROM community_posts WHERE id = :id"),
                {"id": post_id},
            )
        else:
            res = sess.execute(
                text("DELETE FROM community_posts WHERE id = :id AND user_id = :uid"),
                {"id": post_id, "uid": u.id},
            )
        sess.commit()
        if not res.rowcount:
            return jsonify({"error": "not found"}), 404
        return jsonify({"ok": True})
    except Exception:  # noqa: BLE001
        sess.rollback()
        log.exception("community post delete")
        return jsonify({"error": "Could not delete post."}), 500
    finally:
        sess.close()


@app.route("/api/community/posts/<int:post_id>/like", methods=["POST"])
@login_required
def api_community_posts_like(post_id: int):
    """Toggle like for the current user. Returns new likes_count + is_liked."""
    if db.SessionLocal is None:
        return jsonify({"error": "database unavailable"}), 503
    u = _marketplace_db_user()
    if u is None:
        return jsonify({"error": "Auth required."}), 403
    sess = db.db_session()
    try:
        exists_row = sess.execute(
            text("SELECT 1 FROM community_post_likes WHERE post_id = :pid AND user_id = :uid"),
            {"pid": post_id, "uid": u.id},
        ).first()
        if exists_row:
            sess.execute(
                text("DELETE FROM community_post_likes WHERE post_id = :pid AND user_id = :uid"),
                {"pid": post_id, "uid": u.id},
            )
            sess.execute(
                text(
                    "UPDATE community_posts SET likes_count = GREATEST(likes_count - 1, 0) WHERE id = :pid"
                ),
                {"pid": post_id},
            )
            is_liked = False
        else:
            sess.execute(
                text(
                    "INSERT INTO community_post_likes (post_id, user_id) VALUES (:pid, :uid) "
                    "ON CONFLICT DO NOTHING"
                ),
                {"pid": post_id, "uid": u.id},
            )
            sess.execute(
                text("UPDATE community_posts SET likes_count = likes_count + 1 WHERE id = :pid"),
                {"pid": post_id},
            )
            is_liked = True
        row = sess.execute(
            text("SELECT likes_count FROM community_posts WHERE id = :pid"),
            {"pid": post_id},
        ).mappings().first()
        if not row:
            sess.rollback()
            return jsonify({"error": "not found"}), 404
        sess.commit()
        return jsonify({"likes_count": int(row["likes_count"]), "is_liked": is_liked})
    except Exception:  # noqa: BLE001
        sess.rollback()
        log.exception("community post like")
        return jsonify({"error": "Could not toggle like."}), 500
    finally:
        sess.close()


@app.route("/api/community/sentiment", methods=["GET"])
def api_community_sentiment():
    """24h aggregated bullish/bearish counts. Used for the sentiment bar."""
    if db.SessionLocal is None:
        return jsonify({"error": "database unavailable"}), 503

    symbol = (request.args.get("symbol") or "").strip().upper() or None
    sess = db.db_session()
    try:
        rows = sess.execute(
            text(
                """
                SELECT sentiment, COUNT(*)::int AS c
                FROM community_posts
                WHERE created_at >= NOW() - INTERVAL '24 hours'
                  AND sentiment IN ('bullish','bearish')
                  AND (:symbol IS NULL OR UPPER(symbol) = :symbol)
                GROUP BY sentiment
                """
            ),
            {"symbol": symbol},
        ).mappings().all()
        counts = {r["sentiment"]: int(r["c"]) for r in rows}
        bullish = counts.get("bullish", 0)
        bearish = counts.get("bearish", 0)
        total = bullish + bearish
        bullish_pct = round((bullish / total) * 100) if total else 50
        bearish_pct = 100 - bullish_pct if total else 50
        return jsonify(
            {
                "bullish": bullish,
                "bearish": bearish,
                "total_votes": total,
                "bullish_pct": bullish_pct,
                "bearish_pct": bearish_pct,
            }
        )
    except Exception:  # noqa: BLE001
        log.exception("community sentiment")
        return jsonify({"error": "Could not load sentiment."}), 500
    finally:
        sess.close()


# ─────────────────────────────────────────────────────────────────────────────
# Heatmap (24h) — CoinGecko top 20 with metric routing
# ─────────────────────────────────────────────────────────────────────────────

_HEATMAP_CACHE: dict[str, dict] = {}
_HEATMAP_TTL_S = 60
_HEATMAP_VALID_METRICS = ("volume", "change", "market_cap")
_HEATMAP_PLACEHOLDER_METRICS = ("liquidation", "open_interest")


def _heatmap_fetch_coingecko(order_param: str, limit: int = 20) -> list[dict]:
    """Synchronous fetch from CoinGecko /coins/markets (cheap, used behind 60s cache)."""
    import requests  # local import: keeps cold-import path lean

    url = "https://api.coingecko.com/api/v3/coins/markets"
    params = {
        "vs_currency": "usd",
        "order": order_param,
        "per_page": limit,
        "page": 1,
        "price_change_percentage": "24h",
        "sparkline": "false",
    }
    try:
        r = requests.get(url, params=params, timeout=8)
        if r.status_code != 200:
            log.warning("heatmap coingecko %s -> %s", order_param, r.status_code)
            return []
        rows = r.json() or []
    except Exception as exc:  # noqa: BLE001
        log.warning("heatmap coingecko %s failed: %s", order_param, exc)
        return []

    out: list[dict] = []
    for it in rows:
        try:
            out.append(
                {
                    "symbol": (it.get("symbol") or "").upper(),
                    "name": it.get("name") or "",
                    "image": it.get("image"),
                    "price": float(it.get("current_price") or 0),
                    "volume_24h": float(it.get("total_volume") or 0),
                    "market_cap": float(it.get("market_cap") or 0),
                    "change_24h": float(it.get("price_change_percentage_24h") or 0),
                }
            )
        except (TypeError, ValueError):
            continue
    return out


@app.route("/api/heatmap", methods=["GET"])
def api_heatmap():
    """
    Top 20 crypto assets for the dashboard heatmap.

    Query params:
        metric=volume | change | market_cap (default volume)
                liquidation | open_interest -> 200 with empty list + meta.coming_soon=true
        limit=int 5..30 (default 20)
    Cache: 60s in-memory per (metric, limit) key.
    """
    metric = (request.args.get("metric") or "volume").lower()
    try:
        limit = max(5, min(30, int(request.args.get("limit") or 20)))
    except (TypeError, ValueError):
        limit = 20

    if metric in _HEATMAP_PLACEHOLDER_METRICS:
        return jsonify({"items": [], "metric": metric, "coming_soon": True})

    if metric not in _HEATMAP_VALID_METRICS:
        metric = "volume"

    cache_key = f"{metric}:{limit}"
    now = time.time()
    cached = _HEATMAP_CACHE.get(cache_key)
    if cached and (now - cached["t"]) < _HEATMAP_TTL_S:
        return jsonify({"items": cached["data"], "metric": metric, "cached": True})

    order_param = {
        "volume": "volume_desc",
        "market_cap": "market_cap_desc",
        # CoinGecko has no public "biggest movers" sort — pull top-cap window then re-sort.
        "change": "market_cap_desc",
    }[metric]

    items = _heatmap_fetch_coingecko(order_param, limit=limit if metric != "change" else max(limit, 50))

    if metric == "change" and items:
        items.sort(key=lambda x: abs(x.get("change_24h") or 0), reverse=True)
        items = items[:limit]

    if items:
        _HEATMAP_CACHE[cache_key] = {"t": now, "data": items}
    elif cached:
        # Stale-while-error: serve last known good payload
        return jsonify({"items": cached["data"], "metric": metric, "cached": True, "stale": True})

    return jsonify({"items": items, "metric": metric, "cached": False})


# ─────────────────────────────────────────────────────────────────────────────
# Intelligence News Bubbles — agent-fed scrolling ticker on dashboard
# ─────────────────────────────────────────────────────────────────────────────

_INTELLIGENCE_VALID_KINDS = {"news", "question", "alert", "insight"}
_INTELLIGENCE_VALID_ACCENTS = {"orange", "blue", "green", "red", "purple", "neutral"}
_INTELLIGENCE_TITLE_MAX = 200


def _intelligence_serialize(row: dict) -> dict:
    return {
        "id": int(row["id"]),
        "kind": row.get("kind") or "news",
        "title": row.get("title") or "",
        "icon": row.get("icon"),
        "accent": row.get("accent") or "neutral",
        "url": row.get("url"),
        "source": row.get("source"),
        "agent_id": row.get("agent_id"),
        "priority": int(row.get("priority") or 0),
        "created_at": (row["created_at"].isoformat() if row.get("created_at") else None),
        "expires_at": (row["expires_at"].isoformat() if row.get("expires_at") else None),
    }


@app.route("/api/news/intelligence", methods=["GET"])
def api_intelligence_list():
    """
    Public ticker feed. Returns active (non-expired) bubbles ordered by
    priority DESC, created_at DESC. Limit is capped at 25.
    """
    if db.SessionLocal is None:
        return jsonify({"items": []})
    try:
        limit = max(1, min(25, int(request.args.get("limit") or 12)))
    except (TypeError, ValueError):
        limit = 12
    sess = db.db_session()
    try:
        rows = sess.execute(
            text(
                """
                SELECT id, kind, title, icon, accent, url, source,
                       agent_id, priority, created_at, expires_at
                  FROM intelligence_news
                 WHERE expires_at IS NULL OR expires_at > NOW()
                 ORDER BY priority DESC, created_at DESC
                 LIMIT :lim
                """
            ),
            {"lim": limit},
        ).mappings().all()
        items = [_intelligence_serialize(dict(r)) for r in rows]
        return jsonify({"items": items})
    except Exception:  # noqa: BLE001
        log.exception("intelligence list")
        return jsonify({"items": []}), 200
    finally:
        sess.close()


@app.route("/api/news/intelligence", methods=["POST"])
@admin_required
def api_intelligence_create():
    """
    Admin/agent push endpoint. Body:
      {
        "title": str (required),
        "kind": "news"|"question"|"alert"|"insight",
        "icon": str (optional),
        "accent": "orange"|"blue"|"green"|"red"|"purple"|"neutral",
        "url": str (optional),
        "source": str (optional),
        "agent_id": str (optional),
        "priority": int (optional, default 0),
        "ttl_minutes": int (optional, sets expires_at = NOW() + N minutes)
      }
    """
    if db.SessionLocal is None:
        return jsonify({"error": "database unavailable"}), 503

    body = request.get_json(silent=True) or {}
    title = (body.get("title") or "").strip()
    if not title:
        return jsonify({"error": "title is required"}), 400
    if len(title) > _INTELLIGENCE_TITLE_MAX:
        return jsonify({"error": f"title exceeds {_INTELLIGENCE_TITLE_MAX} chars"}), 400

    kind = (body.get("kind") or "news").lower()
    if kind not in _INTELLIGENCE_VALID_KINDS:
        return jsonify({"error": "invalid kind"}), 400

    accent = (body.get("accent") or "neutral").lower()
    if accent not in _INTELLIGENCE_VALID_ACCENTS:
        return jsonify({"error": "invalid accent"}), 400

    icon = (body.get("icon") or "")[:16] or None
    url = (body.get("url") or "").strip() or None
    source = (body.get("source") or "")[:64] or None
    agent_id = (body.get("agent_id") or "")[:64] or None
    try:
        priority = max(0, min(99, int(body.get("priority") or 0)))
    except (TypeError, ValueError):
        priority = 0

    expires_clause = "NULL"
    params = {
        "kind": kind,
        "title": title,
        "icon": icon,
        "accent": accent,
        "url": url,
        "source": source,
        "agent_id": agent_id,
        "priority": priority,
    }
    ttl = body.get("ttl_minutes")
    if ttl is not None:
        try:
            mins = max(1, min(60 * 24 * 14, int(ttl)))
            expires_clause = "NOW() + (:ttl || ' minutes')::interval"
            params["ttl"] = str(mins)
        except (TypeError, ValueError):
            pass

    sess = db.db_session()
    try:
        row = sess.execute(
            text(
                f"""
                INSERT INTO intelligence_news
                  (kind, title, icon, accent, url, source, agent_id, priority, expires_at)
                VALUES
                  (:kind, :title, :icon, :accent, :url, :source, :agent_id, :priority, {expires_clause})
                RETURNING id, kind, title, icon, accent, url, source,
                          agent_id, priority, created_at, expires_at
                """
            ),
            params,
        ).mappings().first()
        sess.commit()
        if not row:
            return jsonify({"error": "insert failed"}), 500
        return jsonify({"item": _intelligence_serialize(dict(row))}), 201
    except Exception:  # noqa: BLE001
        sess.rollback()
        log.exception("intelligence create")
        return jsonify({"error": "could not save"}), 500
    finally:
        sess.close()


@app.route("/api/news/intelligence/<int:item_id>", methods=["DELETE"])
@admin_required
def api_intelligence_delete(item_id: int):
    if db.SessionLocal is None:
        return jsonify({"error": "database unavailable"}), 503
    sess = db.db_session()
    try:
        res = sess.execute(
            text("DELETE FROM intelligence_news WHERE id = :id"),
            {"id": item_id},
        )
        sess.commit()
        if not res.rowcount:
            return jsonify({"error": "not found"}), 404
        return jsonify({"ok": True})
    except Exception:  # noqa: BLE001
        sess.rollback()
        log.exception("intelligence delete")
        return jsonify({"error": "could not delete"}), 500
    finally:
        sess.close()


# ── Admin CMS (see dashboard/admin_api.py) ─────────────────────────────────

from dashboard.owner_design_api import register_owner_design_routes  # noqa: E402

register_owner_design_routes(
    app,
    db=db,
    login_required=login_required,
    _resolve_identity=_resolve_identity,
)

from dashboard.admin_api import register_admin_routes  # noqa: E402

register_admin_routes(
    app,
    db=db,
    admin_required=admin_required,
    login_required=login_required,
    _load_configs=_load_configs,
    _state=_state,
    _PERF_PATH=_PERF_PATH,
    _uptime_str=_uptime_str,
    DRY_RUN=DRY_RUN,
    ALPACA_PAPER=ALPACA_PAPER,
    resolve_identity=_resolve_identity,
    g=g,
    config_dir=CONFIG_DIR,
    google_oauth_configured=bool(not _GOOGLE_PLACEHOLDER),
)


# ── Entrypoint ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    log.info(
        "Hermes Dashboard starting on %s:%d (paper=%s, dry_run=%s, agents=%d)",
        _FLASK_BIND_HOST,
        PORT,
        ALPACA_PAPER,
        DRY_RUN,
        len(_load_configs()),
    )
    app.run(host=_FLASK_BIND_HOST, port=PORT, debug=False, use_reloader=False)
