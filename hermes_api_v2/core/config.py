"""Runtime settings for Hermes FastAPI v2."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv("DATABASE_URL", "").strip()
    fastapi_jwt_secret: str = os.getenv("FASTAPI_JWT_SECRET", "").strip()
    fastapi_jwt_alg: str = os.getenv("FASTAPI_JWT_ALG", "HS256").strip().upper()
    fastapi_jwt_exp_minutes: int = int(os.getenv("FASTAPI_JWT_EXP_MINUTES", "60"))
    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379/0").strip()
    cors_allow_origins_raw: str = os.getenv(
        "FASTAPI_CORS_ALLOW_ORIGINS",
        "https://app.letagentscook.lol",
    ).strip()


settings = Settings()


def cors_allow_origins() -> list[str]:
    return [
        origin.strip()
        for origin in settings.cors_allow_origins_raw.split(",")
        if origin.strip()
    ]


def require_fastapi_jwt_secret() -> str:
    secret = settings.fastapi_jwt_secret.strip()
    if not secret:
        raise RuntimeError("Missing FASTAPI_JWT_SECRET")
    return secret

