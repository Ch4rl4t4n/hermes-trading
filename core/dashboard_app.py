"""FastAPI dashboard: REST + WebSocket + minimal HTML (Phase 5)."""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import os
import secrets
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from fastapi import Depends, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse

from agents.base_agent import DRY_RUN

if TYPE_CHECKING:
    from core.hermes import Hermes

log = logging.getLogger("hermes.dashboard")

DASH_COOKIE = "hermes_dash"
COOKIE_MAX_AGE = 60 * 60 * 24 * 7  # 7 days


def _session_secret() -> bytes:
    for k in ("DASHBOARD_SESSION_SECRET", "DASHBOARD_API_KEY"):
        v = os.getenv(k, "").strip()
        if v:
            return v.encode("utf-8")
    return b"hermes-dashboard-insecure-fallback"  # recommended: set DASHBOARD_API_KEY / DASHBOARD_SESSION_SECRET


def _create_session() -> str:
    exp = int(time.time()) + COOKIE_MAX_AGE
    sec = _session_secret()
    sig = hmac.new(sec, str(exp).encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{exp}|{sig}"


def _verify_session_value(value: str) -> bool:
    if not value or "|" not in value:
        return False
    try:
        exp_s, sig = value.rsplit("|", 1)
        exp = int(exp_s)
    except ValueError:
        return False
    if int(time.time()) > exp:
        return False
    want = hmac.new(_session_secret(), str(exp).encode("utf-8"), hashlib.sha256).hexdigest()
    return hmac.compare_digest(want, sig)


def _dashboard_user() -> str:
    return os.getenv("DASHBOARD_USER", "shako").strip()


def _dashboard_password() -> str:
    return os.getenv("DASHBOARD_PASSWORD", "shako").strip()


def _api_key_ok(request: Request) -> bool:
    expected = os.getenv("DASHBOARD_API_KEY", "").strip()
    if not expected:
        return False
    got = request.headers.get("X-API-Key", "").strip()
    if not got:
        auth = request.headers.get("Authorization", "")
        if auth.lower().startswith("bearer "):
            got = auth[7:].strip()
    return secrets.compare_digest(got, expected)


def _session_ok(request: Request) -> bool:
    val = request.cookies.get(DASH_COOKIE) or ""
    return _verify_session_value(val)


def _auth_ok(request: Request) -> bool:
    return _api_key_ok(request) or _session_ok(request)


def create_dashboard_app(hermes: "Hermes") -> FastAPI:
    app = FastAPI(title="LETAGENTSCOOK Dashboard", version="1.0.0", docs_url=None, redoc_url=None)
    app.state.hermes = hermes

    def require_auth(request: Request) -> None:
        if not _auth_ok(request):
            raise HTTPException(
                status_code=401, detail="Authentication required: login, or set X-API-Key to DASHBOARD_API_KEY"
            )

    @app.post("/api/auth/login")
    async def auth_login(request: Request) -> JSONResponse:
        try:
            data = await request.json()
        except (json.JSONDecodeError, TypeError, ValueError):
            data = {}
        u = (data or {}).get("username", "") or ""
        p = (data or {}).get("password", "") or ""
        u_ok = secrets.compare_digest(str(u), _dashboard_user())
        p_ok = secrets.compare_digest(str(p), _dashboard_password())
        if not (u_ok and p_ok):
            raise HTTPException(status_code=401, detail="Invalid username or password")
        r = JSONResponse({"ok": True})
        r.set_cookie(
            DASH_COOKIE,
            _create_session(),
            max_age=COOKIE_MAX_AGE,
            httponly=True,
            samesite="lax",
            path="/",
        )
        return r

    @app.post("/api/auth/logout")
    async def auth_logout() -> JSONResponse:
        r = JSONResponse({"ok": True})
        r.delete_cookie(DASH_COOKIE, path="/")
        return r

    @app.get("/api/status", dependencies=[Depends(require_auth)])
    async def status() -> dict[str, Any]:
        h: Hermes = app.state.hermes
        return {
            "dry_run": DRY_RUN,
            "kill_switch": h.kill_event.is_set(),
            "agents": len(h.agents),
        }

    @app.get("/api/agents", dependencies=[Depends(require_auth)])
    async def agents() -> list[dict[str, Any]]:
        h: Hermes = app.state.hermes
        out: list[dict[str, Any]] = []
        for a in h.agents:
            price = a.prices[-1] if a.prices else 0.0
            out.append(
                {
                    "name": a.name,
                    "symbol": a.symbol,
                    "paused": a.paused_manually or a.paused_by_limit,
                    "trades_today": a.trades_today,
                    "position_qty": a.position_qty,
                    "entry_price": a.entry_price,
                    "last_price": price,
                }
            )
        return out

    @app.get("/api/positions", dependencies=[Depends(require_auth)])
    async def positions() -> list[dict[str, Any]]:
        h: Hermes = app.state.hermes
        rows: list[dict[str, Any]] = []
        for a in h.agents:
            if a.position_qty <= 0:
                continue
            px = a.prices[-1] if a.prices else 0.0
            ep = a.entry_price or 0.0
            pnl = (px - ep) * a.position_qty if ep else 0.0
            rows.append(
                {
                    "name": a.name,
                    "symbol": a.symbol,
                    "qty": a.position_qty,
                    "entry": ep,
                    "last": px,
                    "unrealized_pnl_usd": round(pnl, 2),
                }
            )
        return rows

    @app.get("/api/risk", dependencies=[Depends(require_auth)])
    async def risk() -> dict[str, Any]:
        h: Hermes = app.state.hermes
        total = 0.0
        parts: list[dict[str, Any]] = []
        for a in h.agents:
            if a.position_qty <= 0:
                continue
            px = a.prices[-1] if a.prices else 0.0
            n = abs(a.position_qty * px)
            total += n
            parts.append({"symbol": a.symbol, "notional_usd": round(n, 2)})
        portfolio = 0.0
        if h.agents:
            try:
                portfolio = h.agents[0]._get_portfolio_value()  # noqa: SLF001
            except Exception:
                portfolio = 0.0
        pct = (total / portfolio * 100.0) if portfolio > 0 else 0.0
        return {
            "open_notional_usd": round(total, 2),
            "portfolio_value_usd": round(portfolio, 2) if portfolio else None,
            "gross_exposure_pct": round(pct, 2) if portfolio else None,
            "by_symbol": parts,
        }

    @app.post("/api/kill", dependencies=[Depends(require_auth)])
    async def kill() -> JSONResponse:
        h: Hermes = app.state.hermes
        await h.activate_kill_switch()
        return JSONResponse({"ok": True, "kill_switch": True})

    @app.get("/", response_class=HTMLResponse)
    async def page() -> str:
        return _load_dashboard_html()

    @app.websocket("/ws/prices")
    async def ws_prices(websocket: WebSocket) -> None:
        exp = os.getenv("DASHBOARD_API_KEY", "").strip()
        key = websocket.query_params.get("key", "")
        ck = websocket.cookies.get(DASH_COOKIE) or ""
        allow = False
        if exp and key and secrets.compare_digest(key, exp):
            allow = True
        elif _verify_session_value(ck):
            allow = True
        if not allow:
            await websocket.close(code=4001, reason="auth")
            return
        h: Hermes = app.state.hermes
        await websocket.accept()
        try:
            while not h.kill_event.is_set():
                if h.feed is None:
                    await asyncio.sleep(1.0)
                    continue
                payload: dict[str, float] = {}
                for a in h.agents:
                    p = h.feed.get_price(a.symbol)
                    if p and p > 0:
                        payload[a.symbol] = p
                await websocket.send_text(json.dumps({"type": "prices", "data": payload}))
                await asyncio.sleep(1.0)
        except (WebSocketDisconnect, asyncio.CancelledError):
            pass
        except Exception as exc:
            log.debug("ws: %s", exc)

    return app


def _load_dashboard_html() -> str:
    return Path(__file__).with_name("dashboard.html").read_text(encoding="utf-8")
