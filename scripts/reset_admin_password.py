#!/usr/bin/env python3
"""Reset dashboard admin password (PostgreSQL + legacy users.json)."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

_BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BASE))

from dotenv import load_dotenv

load_dotenv(_BASE / ".env")

import core.database as db
from core import saas_helpers


def _atomic_write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2, sort_keys=True)
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        pass
    tmp.replace(path)


def reset_legacy_admins(users_path: Path, password: str) -> int:
    """Disable TOTP and set password for every users.json entry with role admin."""
    if not users_path.is_file():
        return 0
    with open(users_path) as f:
        data = json.load(f)
    users = data.get("users")
    if not isinstance(users, dict):
        return 0
    pw_hash = saas_helpers.hash_password(password)
    n = 0
    for _un, rec in list(users.items()):
        if not isinstance(rec, dict):
            continue
        if rec.get("role") != "admin":
            continue
        rec["password_hash"] = pw_hash
        rec["totp_enabled"] = False
        rec["backup_codes"] = []
        rec.pop("totp_enabled_at", None)
        n += 1
    if n:
        _atomic_write_json(users_path, data)
    return n


def main() -> None:
    db.init_engine()
    explicit = os.getenv("LATC_RESET_ADMIN_PASSWORD")
    if explicit:
        pw, ok = explicit, True
        msg = "(from LATC_RESET_ADMIN_PASSWORD)"
    else:
        pw = saas_helpers.generate_strong_password()
        ok, err = saas_helpers.validate_password_strength(pw)
        if not ok:
            raise SystemExit(f"generated password rejected: {err}")
        msg = "(newly generated)"
    email = os.getenv("LATC_SEED_ADMIN_EMAIL", "admin@letagentscook.com")
    username = os.getenv("LATC_SEED_ADMIN_USERNAME", "admin")

    users_file = Path(os.getenv("HERMES_USERS_FILE", str(_BASE / "config" / "users.json")))

    db_done = False
    if db.SessionLocal is not None:
        sess = db.db_session()
        try:
            saas_helpers.reset_db_user_password(
                sess, password=pw, email=email, username=username
            )
            sess.commit()
            db_done = True
        except ValueError as e:
            sess.rollback()
            print(f"database: skip ({e})")
        except Exception as exc:
            sess.rollback()
            raise SystemExit(f"database reset failed: {exc}") from exc
        finally:
            sess.close()
            db.remove_scoped_session()
    else:
        print("database: DATABASE_URL not set, skipped")

    legacy_n = reset_legacy_admins(users_file, pw)

    print("—" * 60)
    if db_done:
        print(f"PostgreSQL admin updated: email={email!r} username={username!r}")
    print(f"Legacy users.json admin entries updated: {legacy_n} ({users_file})")
    print(f"New password {msg}:")
    print(pw)
    print("—" * 60)
    print("Log in with the email or username above. Restart the dashboard if it was running.")


if __name__ == "__main__":
    main()
