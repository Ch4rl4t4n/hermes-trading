#!/usr/bin/env python3
"""Seed initial admin user in PostgreSQL (idempotent)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

_BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BASE))

from dotenv import load_dotenv

load_dotenv(_BASE / ".env")

import core.database as db
from core.saas_helpers import seed_admin_user


def main() -> None:
    db.init_engine()
    if db.SessionLocal is None:
        print("DATABASE_URL not set; skip seed")
        return
    sess = db.db_session()
    try:
        seed_admin_user(
            sess,
            email=os.getenv("LATC_SEED_ADMIN_EMAIL", "admin@letagentscook.com"),
            username=os.getenv("LATC_SEED_ADMIN_USERNAME", "admin"),
            password=os.getenv("LATC_SEED_ADMIN_PASSWORD", "HermesTrader2026!"),
            config_dir=_BASE / "config" / "agents",
            alpaca_key=os.getenv("ALPACA_API_KEY") or None,
            alpaca_secret=os.getenv("ALPACA_API_SECRET") or None,
        )
        sess.commit()
        print("Admin seed OK")
    except Exception as exc:
        sess.rollback()
        raise SystemExit(f"seed failed: {exc}") from exc
    finally:
        sess.close()
        db.remove_scoped_session()


if __name__ == "__main__":
    main()
