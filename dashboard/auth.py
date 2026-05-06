"""
dashboard/auth.py — user management, password hashing, TOTP 2FA.

Storage: ``/root/hermes/config/users.json``

    {
      "users": {
        "<username>": {
          "username": "<username>",
          "password_hash": "<bcrypt>",
          "totp_secret": "<base32>",
          "totp_enabled": false,
          "created_at": "<iso8601>",
          "role": "admin"
        }
      }
    }

The module is process-agnostic — every read re-loads the file so a manual
edit (or a second worker) sees the current state immediately.  Writes use a
``tempfile.replace`` swap so we never observe a half-written file.

Session tokens are *separate* from the user store: they're in-memory only,
keyed by a random UUID, so they expire on dashboard restart — that's a
feature, not a bug.  The Flask session cookie is the primary auth carrier;
the bearer token is a convenience for scripted clients.
"""
from __future__ import annotations

import base64
import io
import json
import logging
import os
import secrets
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import bcrypt
import pyotp
import qrcode

log = logging.getLogger("dashboard.auth")

_BASE = Path(os.getenv("HERMES_BASE", "/root/hermes"))
_USERS_PATH = Path(os.getenv("HERMES_USERS_FILE", str(_BASE / "config" / "users.json")))
_DEFAULT_ADMIN_PASSWORD = "HermesTrader2026!"

# TOTP issuer / account label (Google Authenticator entry title).
TOTP_ISSUER = os.getenv("HERMES_TOTP_ISSUER", "LETAGENTSCOOK")

# Backup codes: 8 one-time codes, each 8 chars (A–Z + 2–9, no 0/O/1/I).
_BACKUP_CODE_LEN = 8
_MAX_BACKUP_CODES = 8
_BACKUP_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"

# bcrypt cost (12 ≈ 250 ms on a modest CPU; tune via env if needed).
_BCRYPT_ROUNDS = int(os.getenv("HERMES_BCRYPT_ROUNDS", "12"))

# Lock for read/modify/write.  Flask serves Wsgi requests one-at-a-time with
# the default werkzeug runner anyway, but cron-style scripts may import this
# module and race; the lock keeps state consistent.
_FILE_LOCK = threading.RLock()


# ── Storage ──────────────────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _empty_store() -> dict:
    return {"users": {}}


def _load() -> dict:
    if not _USERS_PATH.exists():
        return _empty_store()
    try:
        with open(_USERS_PATH) as f:
            data = json.load(f)
        if not isinstance(data, dict) or "users" not in data:
            log.warning("users.json malformed; reinitializing")
            return _empty_store()
        return data
    except Exception as exc:  # noqa: BLE001
        log.error("users.json read failed: %s", exc)
        return _empty_store()


def _save(data: dict) -> None:
    _USERS_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = _USERS_PATH.with_suffix(".tmp")
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2, sort_keys=True)
    # 0600 — only root can read.
    try:
        os.chmod(tmp, 0o600)
    except PermissionError:
        pass
    tmp.replace(_USERS_PATH)


def _get_user(username: str) -> Optional[dict]:
    return _load().get("users", {}).get(username)


# ── Bootstrap: ensure an admin user exists on import ─────────────────────────

def _bootstrap_admin_username() -> str:
    """Primary dashboard login name (``DASHBOARD_USERNAME``, else ``admin``)."""
    return (os.getenv("DASHBOARD_USERNAME", "admin") or "admin").strip()


def ensure_default_admin() -> dict:
    """Create the default admin user on first run.  The password comes from:

      1. ``DASHBOARD_PASSWORD`` env var, or
      2. the hard-coded fallback ``HermesTrader2026!``.

    Username is ``DASHBOARD_USERNAME`` (default ``admin``).
    Legacy ``DASHBOARD_USER`` may seed an *additional* migrated account.
    """
    with _FILE_LOCK:
        data = _load()
        users = data.setdefault("users", {})
        changed = False
        primary = _bootstrap_admin_username()
        if primary not in users:
            password = os.getenv("DASHBOARD_PASSWORD") or _DEFAULT_ADMIN_PASSWORD
            users[primary] = _new_user_record(primary, password, role="admin")
            changed = True
            log.info("Bootstrap user %r created in %s", primary, _USERS_PATH)
        legacy = os.getenv("DASHBOARD_USER")
        if legacy and legacy != primary and legacy not in users:
            password = os.getenv("DASHBOARD_PASSWORD") or _DEFAULT_ADMIN_PASSWORD
            users[legacy] = _new_user_record(legacy, password, role="admin")
            changed = True
            log.info("Legacy user %r migrated into users.json", legacy)
        if changed:
            _save(data)
        return data


def _new_user_record(username: str, password: str, role: str = "admin") -> dict:
    return {
        "username":      username,
        "password_hash": _hash_password(password),
        "totp_secret":   pyotp.random_base32(),
        "totp_enabled":  False,
        "backup_codes":  [],   # sha256 hex of remaining (one-time) backup codes
        "created_at":    _now_iso(),
        "role":          role,
    }


# ── Password hashing ─────────────────────────────────────────────────────────

def _hash_password(password: str) -> str:
    if not isinstance(password, str) or not password:
        raise ValueError("password must be a non-empty string")
    salt = bcrypt.gensalt(rounds=_BCRYPT_ROUNDS)
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


# Pre-computed bcrypt hash of an unknown random secret — used purely as a
# timing-equalising decoy when an unknown username is queried.  Generated once
# at import; never matches a user-supplied password.
_DUMMY_HASH = bcrypt.hashpw(secrets.token_bytes(32), bcrypt.gensalt(rounds=_BCRYPT_ROUNDS))


def verify_password(username: str, password: str) -> bool:
    """Constant-time bcrypt compare; treats unknown users as rate-limited
    failures (returns ``False`` after a dummy hash check to avoid timing
    oracles)."""
    user = _get_user(username)
    if not user or not isinstance(password, str):
        # Run a real bcrypt compare against a sentinel hash to keep the
        # response time of "unknown user" indistinguishable from "wrong
        # password".  The secret is unknowable so the check always fails.
        try:
            bcrypt.checkpw(password.encode("utf-8") if isinstance(password, str) else b"x", _DUMMY_HASH)
        except Exception:  # noqa: BLE001
            pass
        return False
    try:
        return bcrypt.checkpw(password.encode("utf-8"), user["password_hash"].encode("utf-8"))
    except (KeyError, ValueError):
        return False


# ── TOTP ─────────────────────────────────────────────────────────────────────

def _user_totp(user: dict) -> pyotp.TOTP:
    return pyotp.TOTP(user["totp_secret"])


def verify_totp(username: str, code: str) -> bool:
    """Verify a 6-digit TOTP (30 s period, ``valid_window=1`` → ±30 s drift).

    Also accepts **backup codes** (8 alnum chars, or legacy hyphenated codes).
    """
    if not code:
        return False
    user = _get_user(username)
    if not user:
        return False
    raw = code.strip()
    norm = raw.upper().replace(" ", "").replace("-", "")
    # Backup code: new format = 8 chars; legacy = 16+ hex-like groups with hyphens.
    if len(norm) == _BACKUP_CODE_LEN and all(c in _BACKUP_ALPHABET for c in norm):
        return _consume_backup_code(username, raw)
    if "-" in raw or len(norm) >= 12:
        return _consume_backup_code(username, raw)
    # Standard 6-digit TOTP.
    if not (raw.isdigit() and len(raw) == 6):
        return False
    try:
        return _user_totp(user).verify(raw, valid_window=1)
    except Exception as exc:  # noqa: BLE001
        log.debug("TOTP verify error for %s: %s", username, exc)
        return False


def get_totp_secret(username: str) -> Optional[str]:
    user = _get_user(username)
    return user["totp_secret"] if user else None


def get_totp_qr_uri(username: str) -> Optional[str]:
    """Return an ``otpauth://`` provisioning URI for Google Authenticator."""
    user = _get_user(username)
    if not user:
        return None
    return _user_totp(user).provisioning_uri(name=username, issuer_name=TOTP_ISSUER)


def generate_qr_base64(username: str) -> Optional[str]:
    """PNG QR code rendered as base64 (no ``data:`` prefix).  Returns ``None``
    when the user is unknown."""
    uri = get_totp_qr_uri(username)
    if not uri:
        return None
    img = qrcode.make(uri, box_size=8, border=2)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def is_totp_enabled(username: str) -> bool:
    user = _get_user(username)
    return bool(user and user.get("totp_enabled"))


def enable_totp(username: str, code: str) -> tuple[bool, list[str]]:
    """Enable TOTP for ``username`` *only* if ``code`` validates against the
    stored secret.  Returns ``(success, backup_codes)``; on success a fresh
    set of backup codes is generated, stored hashed, and returned plaintext
    *exactly once* so the operator can record them.
    """
    with _FILE_LOCK:
        data = _load()
        user = data.get("users", {}).get(username)
        if not user:
            return False, []
        try:
            ok = pyotp.TOTP(user["totp_secret"]).verify(str(code or "").strip(), valid_window=1)
        except Exception:  # noqa: BLE001
            ok = False
        if not ok:
            return False, []
        plain_backup = _generate_backup_codes()
        user["totp_enabled"] = True
        user["backup_codes"] = [_hash_backup_code(c) for c in plain_backup]
        user["totp_enabled_at"] = _now_iso()
        _save(data)
        log.info("TOTP enabled for %s", username)
        return True, plain_backup


def disable_totp(username: str, code: str) -> bool:
    """Disable TOTP — requires a valid current code or a backup code.  Rotates
    the secret on success so an attacker who saw the QR can't re-enable."""
    if not verify_totp(username, code):
        return False
    with _FILE_LOCK:
        data = _load()
        user = data.get("users", {}).get(username)
        if not user:
            return False
        user["totp_enabled"] = False
        user["totp_secret"] = pyotp.random_base32()
        user["backup_codes"] = []
        _save(data)
        log.info("TOTP disabled for %s (secret rotated)", username)
        return True


# ── Backup codes ─────────────────────────────────────────────────────────────

def _hash_backup_code(plain: str) -> str:
    """SHA-256 of the normalised code (uppercase, no separators)."""
    import hashlib
    norm = plain.upper().replace("-", "").replace(" ", "")
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()


def _one_backup_code() -> str:
    return "".join(secrets.choice(_BACKUP_ALPHABET) for _ in range(_BACKUP_CODE_LEN))


def _generate_backup_codes(n: int = _MAX_BACKUP_CODES) -> list[str]:
    return [_one_backup_code() for _ in range(n)]


def _consume_backup_code(username: str, code: str) -> bool:
    with _FILE_LOCK:
        data = _load()
        user = data.get("users", {}).get(username)
        if not user:
            return False
        target = _hash_backup_code(code)
        codes = list(user.get("backup_codes") or [])
        if target in codes:
            codes.remove(target)
            user["backup_codes"] = codes
            _save(data)
            log.warning("Backup code consumed for %s (%d remaining)", username, len(codes))
            return True
        return False


# ── Public mutation API ──────────────────────────────────────────────────────

def create_user(username: str, password: str, role: str = "admin") -> dict:
    """Create a new user with bcrypt password + fresh TOTP secret (TOTP off).
    Idempotent overwrite when called for an existing username — useful for
    password rotation."""
    if not username:
        raise ValueError("username required")
    with _FILE_LOCK:
        data = _load()
        users = data.setdefault("users", {})
        users[username] = _new_user_record(username, password, role=role)
        _save(data)
        log.info("User %s created/reset (role=%s)", username, role)
        return users[username]


def change_password(username: str, current_password: str, new_password: str) -> bool:
    if not verify_password(username, current_password):
        return False
    with _FILE_LOCK:
        data = _load()
        user = data.get("users", {}).get(username)
        if not user:
            return False
        user["password_hash"] = _hash_password(new_password)
        user["password_changed_at"] = _now_iso()
        _save(data)
        log.info("Password rotated for %s", username)
        return True


def get_user_public(username: str) -> Optional[dict]:
    """Sanitised user view (no secrets)."""
    user = _get_user(username)
    if not user:
        return None
    return {
        "username":     user["username"],
        "role":         user.get("role", "admin"),
        "totp_enabled": bool(user.get("totp_enabled")),
        "created_at":   user.get("created_at"),
        "backup_codes_remaining": len(user.get("backup_codes") or []),
    }


# ── Session tokens (in-memory) ───────────────────────────────────────────────

@dataclass
class _Session:
    username: str
    issued_at: float
    expires_at: float


_TOKEN_TTL = int(os.getenv("HERMES_SESSION_TTL_SECONDS", str(24 * 3600)))  # 24 h
_TOKENS: dict[str, _Session] = {}
_TOKEN_LOCK = threading.RLock()


def issue_token(username: str) -> tuple[str, int]:
    """Mint a new bearer token; returns ``(token, expires_at_epoch)``."""
    token = secrets.token_urlsafe(32)
    now = time.time()
    with _TOKEN_LOCK:
        _TOKENS[token] = _Session(username=username, issued_at=now, expires_at=now + _TOKEN_TTL)
        _gc_expired_tokens()
    return token, int(now + _TOKEN_TTL)


def validate_token(token: str) -> Optional[str]:
    """Return the username associated with ``token`` if still valid."""
    if not token:
        return None
    with _TOKEN_LOCK:
        sess = _TOKENS.get(token)
        if not sess:
            return None
        if sess.expires_at < time.time():
            _TOKENS.pop(token, None)
            return None
        return sess.username


def revoke_token(token: str) -> None:
    if not token:
        return
    with _TOKEN_LOCK:
        _TOKENS.pop(token, None)


def _gc_expired_tokens() -> None:
    now = time.time()
    expired = [k for k, v in _TOKENS.items() if v.expires_at < now]
    for k in expired:
        _TOKENS.pop(k, None)


# ── Brute-force throttle ─────────────────────────────────────────────────────

# Per-(ip, username) fail counters with sliding window + temporary block.
_FAILS: dict[tuple[str, str], list[float]] = {}
_BLOCKS: dict[tuple[str, str], float] = {}
_FAILS_LOCK = threading.RLock()

_FAIL_WINDOW_SECONDS = 15 * 60
_FAIL_THRESHOLD = 5
_BLOCK_DURATION_SECONDS = 30 * 60


def is_blocked(ip: str, username: str = "") -> tuple[bool, int]:
    """Return ``(blocked, seconds_remaining)``.  Blocks are per (ip, user);
    omitting username gives a per-IP global block (used for protocol abuse)."""
    key = (ip or "?", username or "")
    with _FAILS_LOCK:
        until = _BLOCKS.get(key)
        if until and until > time.time():
            return True, int(until - time.time())
        if until:
            _BLOCKS.pop(key, None)
        return False, 0


def record_failure(ip: str, username: str = "") -> tuple[bool, int]:
    """Note a failed login.  Returns ``(now_blocked, seconds_left)``."""
    key = (ip or "?", username or "")
    now = time.time()
    cutoff = now - _FAIL_WINDOW_SECONDS
    with _FAILS_LOCK:
        bucket = [t for t in _FAILS.get(key, ()) if t >= cutoff]
        bucket.append(now)
        _FAILS[key] = bucket
        if len(bucket) >= _FAIL_THRESHOLD:
            _BLOCKS[key] = now + _BLOCK_DURATION_SECONDS
            _FAILS.pop(key, None)
            log.warning("Auth: blocking %s/%s for %ds (>= %d fails)",
                        key[0], key[1] or "?", _BLOCK_DURATION_SECONDS, _FAIL_THRESHOLD)
            return True, _BLOCK_DURATION_SECONDS
        return False, 0


def record_success(ip: str, username: str) -> None:
    """Clear counters on success."""
    with _FAILS_LOCK:
        _FAILS.pop((ip or "?", username or ""), None)
        _BLOCKS.pop((ip or "?", username or ""), None)


# ── Module load ──────────────────────────────────────────────────────────────

ensure_default_admin()
