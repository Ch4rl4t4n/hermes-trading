"""Shared dependencies and runtime resources for Hermes FastAPI v2."""

from __future__ import annotations

import os
from typing import Any, AsyncGenerator

from dotenv import load_dotenv
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

load_dotenv("/root/hermes/.env")

bearer_scheme = HTTPBearer(auto_error=False)

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None
_redis: Redis | None = None


def _database_url() -> str:
    direct = (os.getenv("DATABASE_URL") or "").strip()
    if direct:
        if direct.startswith("postgresql://"):
            return direct.replace("postgresql://", "postgresql+asyncpg://", 1)
        return direct

    host = (os.getenv("DB_HOST") or "127.0.0.1").strip()
    name = (os.getenv("DB_NAME") or "").strip()
    user = (os.getenv("DB_USER") or "").strip()
    password = (os.getenv("DB_PASS") or "").strip()
    port = (os.getenv("DB_PORT") or "5432").strip()
    if not all([host, name, user, password]):
        raise RuntimeError("Missing database configuration. Set DATABASE_URL or DB_* variables.")
    return f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{name}"


def _redis_url() -> str:
    primary = (os.getenv("REDIS_URL") or "").strip()
    if primary:
        return primary
    fallback = (os.getenv("HERMES_RATELIMIT_STORAGE_URI") or "").strip()
    if fallback.startswith("redis://") or fallback.startswith("rediss://"):
        return fallback
    return "redis://127.0.0.1:6379/0"


def _jwt_secret() -> str:
    secret = (os.getenv("FASTAPI_JWT_SECRET") or "").strip()
    if not secret:
        raise RuntimeError("Missing FASTAPI_JWT_SECRET")
    return secret


def _jwt_alg() -> str:
    return (os.getenv("FASTAPI_JWT_ALG") or "HS256").strip().upper()


async def startup_resources() -> None:
    global _engine, _session_factory, _redis
    if _engine is None:
        _engine = create_async_engine(_database_url(), pool_pre_ping=True)
        _session_factory = async_sessionmaker(_engine, expire_on_commit=False)
    if _redis is None:
        client = Redis.from_url(_redis_url(), decode_responses=True)
        try:
            await client.ping()
            _redis = client
        except Exception:  # noqa: BLE001
            await client.aclose()
            _redis = None


async def shutdown_resources() -> None:
    global _engine, _session_factory, _redis
    if _redis is not None:
        await _redis.aclose()
    _redis = None
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _session_factory = None


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    if _session_factory is None:
        raise RuntimeError("Database engine is not initialized")
    async with _session_factory() as session:
        yield session


async def get_redis_client() -> Redis | None:
    return _redis


def decode_fastapi_token(token: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(token, _jwt_secret(), algorithms=[_jwt_alg()])
    except JWTError as exc:
        raise ValueError("Invalid token") from exc
    if not payload.get("sub"):
        raise ValueError("Token missing sub claim")
    return payload


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    if credentials is None or not credentials.credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")

    try:
        payload = decode_fastapi_token(credentials.credentials)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc

    user_id = str(payload.get("sub") or "").strip()
    row = (
        await db.execute(
            text(
                """
                SELECT id, email, tier, is_admin
                FROM users
                WHERE CAST(id AS text) = :user_id
                LIMIT 1
                """
            ),
            {"user_id": user_id},
        )
    ).mappings().first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    return {
        "id": int(row["id"]),
        "email": row["email"],
        "tier": row["tier"],
        "is_admin": bool(row.get("is_admin")),
    }
