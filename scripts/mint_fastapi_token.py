#!/usr/bin/env python3
"""Mint a FastAPI v2 JWT for local smoke tests.

Usage:
  /root/hermes/venv/bin/python /root/hermes/scripts/mint_fastapi_token.py
  /root/hermes/venv/bin/python /root/hermes/scripts/mint_fastapi_token.py --email admin@example.com
  /root/hermes/venv/bin/python /root/hermes/scripts/mint_fastapi_token.py --user-id 1
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv
from jose import jwt
from sqlalchemy import create_engine, text


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Mint FastAPI JWT for Hermes v2.")
    p.add_argument("--email", help="User email to mint token for")
    p.add_argument("--user-id", type=int, help="User ID to mint token for")
    p.add_argument("--minutes", type=int, default=60, help="Token expiry in minutes")
    return p


def main() -> int:
    base = Path("/root/hermes")
    load_dotenv(base / ".env")

    db_url = (os.getenv("DATABASE_URL") or "").strip()
    secret = (os.getenv("FASTAPI_JWT_SECRET") or "").strip()
    alg = (os.getenv("FASTAPI_JWT_ALG") or "HS256").strip().upper()
    default_exp = int(os.getenv("FASTAPI_JWT_EXP_MINUTES") or "60")

    if not db_url:
        print("ERROR: DATABASE_URL missing in .env", file=sys.stderr)
        return 1
    if not secret:
        print("ERROR: FASTAPI_JWT_SECRET missing in .env", file=sys.stderr)
        return 1

    args = build_parser().parse_args()
    minutes = max(1, int(args.minutes or default_exp))

    eng = create_engine(db_url, pool_pre_ping=True)
    query = (
        "SELECT id, email, tier "
        "FROM users "
        "WHERE (:uid IS NULL OR id = :uid) "
        "  AND (:email IS NULL OR LOWER(email) = LOWER(:email)) "
        "ORDER BY CASE WHEN tier='admin' THEN 0 ELSE 1 END, id ASC "
        "LIMIT 1"
    )
    with eng.connect() as conn:
        row = conn.execute(
            text(query),
            {"uid": args.user_id, "email": args.email},
        ).mappings().first()

    if row is None:
        print("ERROR: No matching user found", file=sys.stderr)
        return 2

    payload = {
        "sub": str(row["id"]),
        "tier": str(row.get("tier") or "basic"),
        "scopes": ["agent:read", "pnl:read", "pnl:stream"],
        "exp": datetime.now(timezone.utc) + timedelta(minutes=minutes),
    }
    token = jwt.encode(payload, secret, algorithm=alg)
    print(token)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

