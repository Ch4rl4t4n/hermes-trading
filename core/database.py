"""SQLAlchemy engine and session factory for LETAGENTSCOOK multi-tenant DB."""

from __future__ import annotations

import os
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, scoped_session, sessionmaker


class Base(DeclarativeBase):
    pass


engine = None
SessionLocal: scoped_session | None = None


def init_engine() -> None:
    """Create engine + scoped session factory when DATABASE_URL is set."""
    global engine, SessionLocal
    url = (os.getenv("DATABASE_URL") or "").strip()
    if not url:
        engine = None
        SessionLocal = None
        return
    engine = create_engine(url, pool_pre_ping=True, future=True)
    SessionLocal = scoped_session(sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True))


def get_engine():
    return engine


def db_session() -> scoped_session:
    if SessionLocal is None:
        raise RuntimeError("Database not configured (missing DATABASE_URL)")
    return SessionLocal()


def session_scope() -> Generator:
    """Yield a session and commit/rollback; caller should use as context manager via get_db()."""
    sess = db_session()
    try:
        yield sess
        sess.commit()
    except Exception:
        sess.rollback()
        raise
    finally:
        sess.close()


def init_db() -> None:
    """Create tables (tests / dev). Prefer Alembic migrations in production."""
    if engine is None:
        return
    from core import models  # noqa: F401

    Base.metadata.create_all(bind=engine)


def remove_scoped_session() -> None:
    if SessionLocal is not None:
        SessionLocal.remove()
