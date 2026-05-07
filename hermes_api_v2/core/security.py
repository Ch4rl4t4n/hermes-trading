"""JWT helpers for Hermes FastAPI v2."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt

from hermes_api_v2.core.config import require_fastapi_jwt_secret, settings


def create_fastapi_token(user_id: str, tier: str) -> str:
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.fastapi_jwt_exp_minutes)
    payload: dict[str, Any] = {
        "sub": user_id,
        "tier": tier,
        "scopes": ["agent:read", "pnl:read", "pnl:stream"],
        "exp": expires_at,
    }
    return jwt.encode(payload, require_fastapi_jwt_secret(), algorithm=settings.fastapi_jwt_alg)


def decode_fastapi_token(token: str) -> dict[str, Any]:
    try:
        decoded = jwt.decode(
            token,
            require_fastapi_jwt_secret(),
            algorithms=[settings.fastapi_jwt_alg],
        )
    except JWTError as exc:
        raise ValueError("Invalid token") from exc
    if not decoded.get("sub"):
        raise ValueError("Token missing sub claim")
    return decoded

