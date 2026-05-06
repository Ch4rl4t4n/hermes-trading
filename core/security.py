"""Fernet field-level encryption for broker API secrets stored in PostgreSQL."""

from __future__ import annotations

import os
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken


@lru_cache(maxsize=1)
def _fernet() -> Fernet:
    raw = (os.getenv("ENCRYPTION_KEY") or "").strip()
    if not raw:
        raise RuntimeError("ENCRYPTION_KEY is not set in the environment")
    return Fernet(raw.encode() if isinstance(raw, str) else raw)


def encrypt_field(value: str | None) -> str | None:
    if value is None or value == "":
        return None
    return _fernet().encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_field(value: str | None) -> str | None:
    if value is None or value == "":
        return None
    try:
        return _fernet().decrypt(value.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError, TypeError):
        return None
