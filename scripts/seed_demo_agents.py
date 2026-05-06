#!/usr/bin/env python3
"""
Priradí demo agentov všetkým existujúcim userom bez aktívnych odberov.
Spusti: cd /root/hermes && python scripts/seed_demo_agents.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BASE))

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv(_BASE / ".env")

from core.agent_marketplace import assign_demo_agents


def main() -> None:
    url = (os.getenv("DATABASE_URL") or "").strip()
    if not url:
        print("DATABASE_URL not set", file=sys.stderr)
        sys.exit(1)
    engine = create_engine(url, future=True)

    dialect = engine.dialect.name
    if dialect == "sqlite":
        not_admin = "(u.is_admin = 0 OR u.is_admin IS NULL)"
        active_sub = "(us.is_active = 1 OR us.is_active = true)"
    else:
        not_admin = "COALESCE(u.is_admin, false) = false"
        active_sub = "us.is_active IS TRUE"

    with engine.begin() as conn:
        users = conn.execute(
            text(f"""
                SELECT u.id, u.email FROM users u
                WHERE {not_admin}
                AND NOT EXISTS (
                    SELECT 1 FROM user_subscriptions us
                    WHERE us.user_id = u.id AND {active_sub}
                )
            """),
        ).fetchall()

        print(f"Nájdených {len(users)} userov bez aktívnych agentov")

        for user in users:
            uid = int(user[0])
            email = user[1] or ""
            assigned = assign_demo_agents(uid, conn)
            print(f"  User {uid} ({email}): priradených {len(assigned)} agentov")

    print("Hotovo!")


if __name__ == "__main__":
    main()
