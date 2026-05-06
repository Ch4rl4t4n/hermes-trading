"""API key auth + rate limiting for /v1 endpoints."""

from __future__ import annotations

import hashlib
import os
import secrets
import time
from datetime import datetime, timezone
from functools import wraps
from typing import Any

from flask import g, jsonify, request
from sqlalchemy import text

import core.database as db
from core.tier_access import effective_tier

_redis_client: Any = None
_redis_init_done = False

API_RATE_LIMIT_PER_MIN = 60


def generate_api_key() -> str:
    """Generate API key in hk_live_<random> format."""
    return f"hk_live_{secrets.token_urlsafe(32)}"


def hash_api_key(key: str) -> str:
    """SHA256 API key hash."""
    return hashlib.sha256((key or "").encode("utf-8")).hexdigest()


def _redis():
    global _redis_client, _redis_init_done
    if _redis_init_done:
        return _redis_client
    _redis_init_done = True
    redis_url = (os.getenv("REDIS_URL") or "").strip()
    if not redis_url:
        storage = (os.getenv("HERMES_RATELIMIT_STORAGE_URI") or "").strip()
        if storage.startswith("redis://") or storage.startswith("rediss://"):
            redis_url = storage
    if not redis_url:
        return None
    try:
        import redis  # noqa: PLC0415

        _redis_client = redis.Redis.from_url(redis_url, decode_responses=True)
        _redis_client.ping()
        return _redis_client
    except Exception:
        _redis_client = None
        return None


def _db_rate_limit_check(api_key_id: int, limit: int) -> tuple[bool, int, int]:
    eng = db.get_engine()
    now = int(time.time())
    reset_ts = ((now // 60) + 1) * 60
    if eng is None:
        return True, max(0, limit - 1), reset_ts
    with eng.connect() as conn:
        used = conn.execute(
            text(
                """
                SELECT COUNT(*)::int
                FROM api_requests
                WHERE api_key_id = :kid
                  AND created_at >= (NOW() - INTERVAL '60 seconds')
                """
            ),
            {"kid": int(api_key_id)},
        ).scalar()
    count = int(used or 0)
    remaining = max(0, limit - count)
    allowed = count < limit
    return allowed, remaining, reset_ts


def rate_limit_check(api_key_id: int, limit: int = API_RATE_LIMIT_PER_MIN) -> tuple[bool, int, int]:
    """Return (allowed, remaining, reset_timestamp). Redis primary, DB fallback."""
    now = int(time.time())
    minute_bucket = now // 60
    reset_ts = (minute_bucket + 1) * 60
    rc = _redis()
    if rc is not None:
        try:
            key = f"api:rl:{int(api_key_id)}:{minute_bucket}"
            used = int(rc.incr(key))
            if used == 1:
                rc.expire(key, 70)
            remaining = max(0, limit - used)
            return used <= limit, remaining, reset_ts
        except Exception:
            pass
    return _db_rate_limit_check(api_key_id, limit)


def _error(message: str, code: int, error: str = "Unauthorized"):
    return jsonify({"error": error, "message": message, "code": code}), code


def require_api_key(f):
    """Decorator for /v1 endpoints requiring active elite/admin API key."""

    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer hk_live_"):
            return _error(
                "Provide API key in Authorization: Bearer hk_live_... header",
                401,
                "Unauthorized",
            )

        api_key = auth_header[7:]
        key_hash = hash_api_key(api_key)
        eng = db.get_engine()
        if eng is None:
            return _error("Database unavailable", 503, "Service Unavailable")

        with eng.begin() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT k.id AS api_key_id, k.user_id, k.is_active, k.expires_at,
                           u.tier, u.is_admin
                    FROM api_keys k
                    JOIN users u ON u.id = k.user_id
                    WHERE k.key_hash = :kh
                    LIMIT 1
                    """
                ),
                {"kh": key_hash},
            ).mappings().first()
            if not row:
                return _error("Invalid API key", 401, "Unauthorized")
            if not bool(row["is_active"]):
                return _error("API key is revoked", 401, "Unauthorized")
            exp = row.get("expires_at")
            if exp is not None:
                exp_dt = exp if getattr(exp, "tzinfo", None) else exp.replace(tzinfo=timezone.utc)
                if exp_dt < datetime.now(timezone.utc):
                    return _error("API key expired", 401, "Unauthorized")

            class _U:
                tier = row.get("tier")
                is_admin = bool(row.get("is_admin"))

            t = effective_tier(_U())
            if t not in ("elite", "admin"):
                return _error("Elite tier required for API access", 403, "Forbidden")

            allowed, remaining, reset_ts = rate_limit_check(int(row["api_key_id"]), API_RATE_LIMIT_PER_MIN)
            if not allowed:
                g.api_user_id = int(row["user_id"])
                g.api_key_id = int(row["api_key_id"])
                g.api_rate_limit = API_RATE_LIMIT_PER_MIN
                g.api_rate_remaining = 0
                g.api_rate_reset = reset_ts
                return _error("Rate limit exceeded (60 req/min)", 429, "Too Many Requests")

            conn.execute(
                text("UPDATE api_keys SET last_used_at = NOW() WHERE id = :kid"),
                {"kid": int(row["api_key_id"])},
            )

        g.api_user_id = int(row["user_id"])
        g.api_key_id = int(row["api_key_id"])
        g.api_rate_limit = API_RATE_LIMIT_PER_MIN
        g.api_rate_remaining = remaining
        g.api_rate_reset = reset_ts
        g.api_auth_ok = True
        return f(*args, **kwargs)

    return decorated


def log_api_request(
    endpoint: str,
    method: str,
    status_code: int,
    response_time_ms: int,
    ip_address: str | None,
    api_key_id: int | None,
    user_id: int | None,
) -> None:
    eng = db.get_engine()
    if eng is None:
        return
    try:
        with eng.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO api_requests
                        (api_key_id, user_id, endpoint, method, status_code, response_time_ms, ip_address)
                    VALUES
                        (:kid, :uid, :ep, :m, :sc, :rt, :ip)
                    """
                ),
                {
                    "kid": api_key_id,
                    "uid": user_id,
                    "ep": (endpoint or "")[:200],
                    "m": (method or "")[:10],
                    "sc": int(status_code or 0),
                    "rt": int(max(0, response_time_ms or 0)),
                    "ip": (ip_address or "")[:45],
                },
            )
    except Exception:
        return
