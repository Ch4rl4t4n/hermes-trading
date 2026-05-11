"""Platform owner allowlist (design CMS / internal tools). Separate from admin tier."""

from __future__ import annotations

import os
from typing import Any


def parse_owner_user_ids() -> set[int]:
    raw = (os.getenv("HERMES_OWNER_USER_IDS") or "").strip()
    if not raw:
        return set()
    out: set[int] = set()
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            out.add(int(part))
        except ValueError:
            continue
    return out


def user_is_owner(user: Any) -> bool:
    if user is None:
        return False
    uid = getattr(user, "id", None)
    if uid is None:
        return False
    try:
        return int(uid) in parse_owner_user_ids()
    except (TypeError, ValueError):
        return False
