"""Database and Redis lifecycle for Hermes FastAPI v2."""

from __future__ import annotations

import logging
from typing import AsyncGenerator

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from hermes_api_v2.core.config import settings

log = logging.getLogger("hermes_api_v2.database")

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None
_redis_client: Redis | None = None


def init_engine() -> None:
    global _engine, _session_factory
    if not settings.database_url:
        return
    async_url = settings.database_url
    if async_url.startswith("postgresql://"):
        async_url = async_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    _engine = create_async_engine(async_url, pool_pre_ping=True)
    _session_factory = async_sessionmaker(_engine, expire_on_commit=False)


async def close_engine() -> None:
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _session_factory = None


async def init_redis() -> None:
    global _redis_client
    try:
        client = Redis.from_url(settings.redis_url, decode_responses=True)
        await client.ping()
        _redis_client = client
    except Exception as exc:  # noqa: BLE001
        _redis_client = None
        log.warning("redis unavailable, continuing without cache: %s", exc)


async def close_redis() -> None:
    global _redis_client
    if _redis_client is not None:
        await _redis_client.aclose()
    _redis_client = None


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    if _session_factory is None:
        raise RuntimeError("Database engine is not initialized")
    async with _session_factory() as session:
        yield session


async def get_redis() -> Redis | None:
    return _redis_client


async def startup_resources() -> None:
    init_engine()
    await init_redis()


async def shutdown_resources() -> None:
    await close_redis()
    await close_engine()

