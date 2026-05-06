"""Helpers for SaaS registration, trading-config blobs, and DB-backed telemetry."""

from __future__ import annotations

import math
import os
import re
import secrets
import string
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

import bcrypt
import hashlib
import pyotp
import yaml
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core.models import Account, AuditLog, PlatformSetting, Trade, TradingConfiguration, User
from core.security import decrypt_field, encrypt_field
from core.tier_access import TIER_BASIC, TIER_PRO, normalize_tier

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_BCRYPT_ROUNDS = 12

_VALID_TIERS = frozenset({"basic", "medium", "pro", "free", "starter", "professional"})
_VALID_ADMIN_CREATE_TIERS = frozenset({"basic", "medium", "pro", "admin"})
_USERNAME_RE = re.compile(r"^[a-zA-Z0-9_]{3,20}$")

DEFAULT_PLATFORM_SETTINGS: dict[str, Any] = {
    "trading_defaults": {
        "default_paper_balance": 100_000,
        "max_single_trade_pct": 5,
        "max_daily_loss_pct": 3,
        "max_drawdown_pct": 10,
    },
    "agents_available": {},
    "registration": {
        "open": True,
        "require_email_verification": False,
        "default_tier": "basic",
        "trial_pro_days": 14,
    },
    "stripe": {},
}


def _deep_merge(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = dict(base)
    for k, v in patch.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def get_platform_settings_dict(db: Session) -> dict[str, Any]:
    merged: dict[str, Any] = {k: dict(v) if isinstance(v, dict) else v for k, v in DEFAULT_PLATFORM_SETTINGS.items()}
    rows = db.execute(select(PlatformSetting)).scalars().all()
    for row in rows:
        key = row.key
        val = row.value if isinstance(row.value, dict) else {}
        if key in merged and isinstance(merged[key], dict) and isinstance(val, dict):
            merged[key] = _deep_merge(merged[key], val)
        else:
            merged[key] = row.value
    return merged


def apply_pro_trial_for_new_basic_user(user: User, plat: dict[str, Any]) -> None:
    """Grant time-limited Pro feature access to new users whose stored tier is Basic."""
    reg = plat.get("registration") or {}
    raw = reg.get("trial_pro_days")
    if raw is None or raw == "":
        raw_e = (os.getenv("HERMES_TRIAL_PRO_DAYS") or "14").strip()
        try:
            days = int(raw_e)
        except (TypeError, ValueError):
            days = 14
    else:
        try:
            days = int(raw)
        except (TypeError, ValueError):
            days = 0
    if days <= 0:
        return
    if normalize_tier(user.tier) != TIER_BASIC:
        return
    user.trial_promo_tier = TIER_PRO
    user.trial_promo_until = datetime.now(timezone.utc) + timedelta(days=days)


def upsert_platform_settings(
    db: Session,
    patch: dict[str, Any],
) -> dict[str, Any]:
    allowed = {"trading_defaults", "registration", "agents_available"}
    for key, value in patch.items():
        if key not in allowed or not isinstance(value, dict):
            continue
        row = db.get(PlatformSetting, key)
        if row:
            base = dict(row.value) if isinstance(row.value, dict) else {}
            row.value = _deep_merge(base, value)
        else:
            db.add(PlatformSetting(key=key, value=value))
    db.flush()
    return get_platform_settings_dict(db)


def normalise_email(email: str) -> str:
    return (email or "").strip().lower()


def validate_email(email: str) -> bool:
    return bool(_EMAIL_RE.match(normalise_email(email)))


def validate_username(username: str) -> bool:
    return bool(_USERNAME_RE.match((username or "").strip()))


def generate_strong_password(length: int = 16) -> str:
    """Return a random password that passes :func:`validate_password_strength`."""
    alphabet = string.ascii_letters + string.digits
    for _ in range(500):
        pw = "".join(secrets.choice(alphabet) for _ in range(max(12, length)))
        ok, _ = validate_password_strength(pw)
        if ok:
            return pw
    return "Aa9" + secrets.token_urlsafe(16)[:20]


def validate_password_strength(password: str) -> tuple[bool, str]:
    if len(password) < 8:
        return False, "Password must be at least 8 characters."
    if not re.search(r"[A-Z]", password):
        return False, "Password must contain an uppercase letter."
    if not re.search(r"\d", password):
        return False, "Password must contain a number."
    return True, ""


def registration_requires_email_verification(plat: dict[str, Any]) -> bool:
    reg = plat.get("registration") or {}
    return bool(reg.get("require_email_verification"))


def hash_email_verification_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def user_by_verification_token(db: Session, raw_token: str) -> User | None:
    if not raw_token or len(raw_token) < 16:
        return None
    digest = hash_email_verification_token(raw_token)
    return db.execute(select(User).where(User.email_verification_token_hash == digest)).scalar_one_or_none()


def assign_email_verification_token(user: User) -> str:
    """Set a fresh token on user; return raw token for email (caller commits)."""
    raw = secrets.token_urlsafe(32)
    user.email_verification_token_hash = hash_email_verification_token(raw)
    user.email_verification_expires_at = datetime.now(timezone.utc) + timedelta(hours=48)
    user.email_verification_sent_at = datetime.now(timezone.utc)
    return raw


def clear_email_verification_token(user: User) -> None:
    user.email_verification_token_hash = None
    user.email_verification_expires_at = None
    user.email_verification_sent_at = None


def hash_password(password: str) -> str:
    salt = bcrypt.gensalt(rounds=_BCRYPT_ROUNDS)
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password_hash(password_hash: str, password: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def build_default_agents_blob(
    config_dir: Path,
    agents_available: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Load stock YAML agent specs into JSON-compatible dicts for new accounts."""
    docs: list[dict[str, Any]] = []
    for yaml_file in sorted(config_dir.glob("*.yaml")):
        try:
            with open(yaml_file) as f:
                doc = yaml.safe_load(f) or {}
            if isinstance(doc, dict) and doc.get("symbol"):
                sym = str(doc.get("symbol"))
                if agents_available and agents_available.get(sym) is False:
                    continue
                docs.append(doc)
        except OSError:
            continue
    return {"agents": docs, "paused_symbols": []}


def agents_list_from_blob(blob: dict[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(blob, dict):
        return []
    inner = blob.get("agents")
    if isinstance(inner, list):
        return [x for x in inner if isinstance(x, dict)]
    return []


def paused_from_blob(blob: dict[str, Any]) -> set[str]:
    if not isinstance(blob, dict):
        return set()
    ps = blob.get("paused_symbols") or []
    if isinstance(ps, list):
        return {str(x) for x in ps}
    return set()


def merge_paused_into_blob(blob: dict[str, Any], paused: set[str]) -> dict[str, Any]:
    out = dict(blob) if isinstance(blob, dict) else {}
    inner = list(agents_list_from_blob(out))
    out["agents"] = inner
    out["paused_symbols"] = sorted(paused)
    return out


def verify_db_totp(user: User, code: str) -> bool:
    if not user.totp_enabled:
        return True
    if not code:
        return False
    raw = str(code).strip()
    if not (raw.isdigit() and len(raw) == 6):
        return False
    try:
        return pyotp.TOTP(user.totp_secret).verify(raw, valid_window=2)
    except Exception:
        return False


def register_user(
    db: Session,
    *,
    email: str,
    username: str,
    password: str,
    config_dir: Path,
    ip: str | None,
    oauth_registration: bool = False,
) -> tuple[User, Optional[str]]:
    email_n = normalise_email(email)
    uname = (username or "").strip()
    if not validate_email(email_n):
        raise ValueError("Invalid email address")
    if not validate_username(uname):
        raise ValueError("Username must be 3–20 characters (letters, numbers, underscore only).")
    ok_pw, pw_msg = validate_password_strength(password)
    if not oauth_registration:
        if not ok_pw:
            raise ValueError(pw_msg)
    elif not ok_pw:
        raise ValueError("Invalid password")
    if db.execute(select(User.id).where(User.email == email_n)).scalar_one_or_none():
        raise ValueError("Email already registered")
    if db.execute(select(User.id).where(User.username == uname)).scalar_one_or_none():
        raise ValueError("Username already taken")

    plat = get_platform_settings_dict(db)
    reg = plat.get("registration") or {}
    if reg.get("open") is False:
        raise ValueError("Registration is currently closed")
    tier = str(reg.get("default_tier") or "basic").strip().lower()
    if tier not in _VALID_TIERS:
        tier = "basic"
    if tier == "free":
        tier = "basic"
    elif tier == "starter":
        tier = "medium"
    elif tier == "professional":
        tier = "pro"
    td = plat.get("trading_defaults") or {}
    paper_bal = float(td.get("default_paper_balance", 100_000))
    mst = float(td.get("max_single_trade_pct", 5))
    mdl = float(td.get("max_daily_loss_pct", 3))
    mdd = float(td.get("max_drawdown_pct", 10))
    agents_avail = plat.get("agents_available")
    if not isinstance(agents_avail, dict):
        agents_avail = {}

    need_verify = registration_requires_email_verification(plat) and not oauth_registration

    user = User(
        email=email_n,
        username=uname,
        password_hash=hash_password(password),
        totp_secret=pyotp.random_base32(),
        totp_enabled=False,
        tier=tier,
        email_verified=not need_verify,
        unsubscribe_token=secrets.token_hex(32),
    )
    db.add(user)
    db.flush()

    account = Account(
        user_id=user.id,
        account_type="paper",
        account_status="active",
        alpaca_api_key=None,
        alpaca_api_secret=None,
        paper_balance=paper_bal,
        max_single_trade_pct=mst,
        max_daily_loss_pct=mdl,
        max_drawdown_pct=mdd,
    )
    db.add(account)
    db.flush()

    blob = build_default_agents_blob(config_dir, agents_avail)
    tconf = TradingConfiguration(
        account_id=account.id,
        agents=blob,
        llm_enabled=True,
        trading_mode="day_trading",
    )
    db.add(tconf)

    db.add(
        AuditLog(
            user_id=user.id,
            account_id=account.id,
            action="user.register",
            details={"email": email_n, "username": uname, "email_verification_pending": need_verify},
            ip_address=ip,
        )
    )
    apply_pro_trial_for_new_basic_user(user, plat)
    raw_token_out: Optional[str] = None
    if need_verify:
        raw_token_out = assign_email_verification_token(user)
    else:
        clear_email_verification_token(user)
    db.flush()
    return user, raw_token_out


def admin_create_user(
    db: Session,
    *,
    email: str,
    username: str,
    password: str | None,
    tier_choice: str,
    config_dir: Path,
    ip: str | None,
) -> tuple[User, str]:
    """Create user + $100k paper account; bypass registration closed / ToS.

    ``tier_choice`` may include ``admin`` (sets ``is_admin=True``, stored tier ``pro``).

    Returns ``(user, plaintext_password)``.
    """
    email_n = normalise_email(email)
    uname = (username or "").strip()
    tc = (tier_choice or "").strip().lower()
    if tc not in _VALID_ADMIN_CREATE_TIERS:
        raise ValueError("Invalid tier. Use: basic, medium, pro, admin")
    if not validate_email(email_n):
        raise ValueError("Invalid email address")
    if not validate_username(uname):
        raise ValueError("Username must be 3–20 characters (letters, numbers, underscore only).")

    plain = (password or "").strip()
    if not plain:
        plain = generate_strong_password()
    else:
        ok_pw, pw_msg = validate_password_strength(plain)
        if not ok_pw:
            raise ValueError(pw_msg)

    if db.execute(select(User.id).where(User.email == email_n)).scalar_one_or_none():
        raise ValueError("Email already registered")
    if db.execute(select(User.id).where(User.username == uname)).scalar_one_or_none():
        raise ValueError("Username already taken")

    is_admin_user = tc == "admin"
    sub_tier = "pro" if is_admin_user else tc

    plat = get_platform_settings_dict(db)
    td = plat.get("trading_defaults") or {}
    mst = float(td.get("max_single_trade_pct", 5))
    mdl = float(td.get("max_daily_loss_pct", 3))
    mdd = float(td.get("max_drawdown_pct", 10))
    agents_avail = plat.get("agents_available")
    if not isinstance(agents_avail, dict):
        agents_avail = {}

    paper_bal = 100_000.0

    user = User(
        email=email_n,
        username=uname,
        password_hash=hash_password(plain),
        totp_secret=pyotp.random_base32(),
        totp_enabled=False,
        tier=sub_tier,
        is_admin=is_admin_user,
        email_verified=True,
        unsubscribe_token=secrets.token_hex(32),
    )
    db.add(user)
    db.flush()
    clear_email_verification_token(user)

    account = Account(
        user_id=user.id,
        account_type="paper",
        account_status="active",
        alpaca_api_key=None,
        alpaca_api_secret=None,
        paper_balance=paper_bal,
        max_single_trade_pct=mst,
        max_daily_loss_pct=mdl,
        max_drawdown_pct=mdd,
    )
    db.add(account)
    db.flush()

    blob = build_default_agents_blob(config_dir, agents_avail)
    db.add(
        TradingConfiguration(
            account_id=account.id,
            agents=blob,
            llm_enabled=True,
            trading_mode="day_trading",
        )
    )
    db.flush()
    return user, plain


def register_or_get_google_user(
    db: Session,
    *,
    email: str,
    full_name: str | None,
    google_sub: str | None,
    config_dir: Path,
    ip: str | None,
) -> tuple[User, bool]:
    email_n = normalise_email(email)
    if not validate_email(email_n):
        raise ValueError("Invalid email from Google")
    existing = db.execute(select(User).where(User.email == email_n)).scalar_one_or_none()
    if existing:
        if google_sub and not (existing.google_id or "").strip():
            existing.google_id = google_sub
        return existing, False
    if google_sub:
        clash = db.execute(select(User.id).where(User.google_id == google_sub)).scalar_one_or_none()
        if clash:
            raise ValueError("This Google account is already linked to another user.")
    raw_base = (full_name or email_n.split("@")[0]).strip()
    raw_base = re.sub(r"[^a-zA-Z0-9_]", "_", raw_base) or "user"
    if len(raw_base) < 3:
        raw_base = raw_base + "_user"
    raw_base = raw_base[:20]
    cand = raw_base
    suffix = 0
    while db.execute(select(User.id).where(User.username == cand)).scalar_one_or_none():
        suffix += 1
        cand = (raw_base[:14] + "_" + str(suffix))[:20]
    pw = secrets.token_urlsafe(32)
    user, _verify_raw = register_user(
        db,
        email=email_n,
        username=cand,
        password=pw,
        config_dir=config_dir,
        ip=ip,
        oauth_registration=True,
    )
    user.auth_kind = "google"
    if google_sub:
        user.google_id = google_sub
    db.flush()
    return user, True


def record_audit(
    db: Session,
    *,
    user_id: int | None,
    account_id: int | None,
    action: str,
    details: dict[str, Any] | None,
    ip: str | None,
) -> None:
    db.add(
        AuditLog(
            user_id=user_id,
            account_id=account_id,
            action=action,
            details=details or {},
            ip_address=ip,
        )
    )


def default_paper_account_for_user(db: Session, user_id: int) -> Optional[Account]:
    return db.execute(
        select(Account).where(Account.user_id == user_id, Account.account_type == "paper")
    ).scalar_one_or_none()


def trade_performance_payload(db: Session, account_id: int) -> dict[str, Any]:
    """Mirror PerformanceTracker.summary / by_symbol / recent for dashboard."""
    rows = db.execute(select(Trade).where(Trade.account_id == account_id)).scalars().all()
    closed = [t for t in rows if t.exit_time is not None and t.pnl is not None]

    def _summary() -> dict[str, Any]:
        n = len(closed)
        if n == 0:
            return {
                "trades": 0,
                "win_rate": 0.0,
                "avg_profit_usd": 0.0,
                "avg_loss_usd": 0.0,
                "avg_profit_pct": 0.0,
                "avg_loss_pct": 0.0,
                "profit_factor": 0.0,
                "expectancy_usd": 0.0,
                "sharpe_daily": 0.0,
                "max_drawdown_usd": 0.0,
                "total_pnl_usd": 0.0,
                "open_trades": sum(1 for t in rows if t.exit_time is None),
            }
        wins = [t for t in closed if float(t.pnl or 0) > 0]
        losses = [t for t in closed if float(t.pnl or 0) <= 0]
        gross_profit = sum(float(t.pnl or 0) for t in wins)
        gross_loss = sum(float(t.pnl or 0) for t in losses)
        total_pnl = gross_profit + gross_loss
        profit_factor = (gross_profit / abs(gross_loss)) if gross_loss < 0 else (float("inf") if gross_profit > 0 else 0.0)
        by_day: dict[str, float] = {}
        for t in closed:
            if not t.exit_time:
                continue
            dkey = t.exit_time.date().isoformat()
            by_day[dkey] = by_day.get(dkey, 0.0) + float(t.pnl or 0)
        daily = list(by_day.values())
        sharpe = 0.0
        if len(daily) > 1:
            mean = sum(daily) / len(daily)
            sd = _stdev(daily)
            if sd > 0:
                sharpe = (mean / sd) * math.sqrt(252)
        equity = 0.0
        peak = 0.0
        max_dd = 0.0
        for t in sorted(closed, key=lambda x: x.exit_time or datetime.min.replace(tzinfo=timezone.utc)):
            equity += float(t.pnl or 0)
            if equity > peak:
                peak = equity
            dd = peak - equity
            if dd > max_dd:
                max_dd = dd
        return {
            "trades": n,
            "win_rate": len(wins) / n if n else 0.0,
            "avg_profit_usd": gross_profit / len(wins) if wins else 0.0,
            "avg_loss_usd": gross_loss / len(losses) if losses else 0.0,
            "avg_profit_pct": sum(float(t.pnl_pct or 0) for t in wins) / len(wins) if wins else 0.0,
            "avg_loss_pct": sum(float(t.pnl_pct or 0) for t in losses) / len(losses) if losses else 0.0,
            "profit_factor": profit_factor,
            "expectancy_usd": total_pnl / n,
            "sharpe_daily": sharpe,
            "max_drawdown_usd": max_dd,
            "total_pnl_usd": total_pnl,
            "open_trades": sum(1 for t in rows if t.exit_time is None),
        }

    def _by_symbol() -> dict[str, Any]:
        out: dict[str, dict[str, float]] = {}
        for t in closed:
            sym = t.symbol
            bucket = out.setdefault(sym, {"trades": 0, "pnl": 0.0})
            bucket["trades"] += 1
            bucket["pnl"] += float(t.pnl or 0)
        return out

    def _recent(n: int = 20) -> list[dict[str, Any]]:
        def sort_key(t: Trade) -> datetime:
            return t.exit_time or t.entry_time or datetime.min.replace(tzinfo=timezone.utc)

        out = []
        for t in sorted(rows, key=sort_key, reverse=True)[:n]:
            out.append(
                {
                    "symbol": t.symbol,
                    "side": "LONG" if t.trade_type == "BUY" else "SHORT",
                    "entry_ts": t.entry_time.isoformat() if t.entry_time else None,
                    "entry_price": float(t.entry_price) if t.entry_price is not None else None,
                    "qty": float(t.entry_qty) if t.entry_qty is not None else None,
                    "exit_ts": t.exit_time.isoformat() if t.exit_time else None,
                    "exit_price": float(t.exit_price) if t.exit_price is not None else None,
                    "pnl_usd": float(t.pnl) if t.pnl is not None else None,
                    "pnl_pct": float(t.pnl_pct) if t.pnl_pct is not None else None,
                    "mode": t.trading_mode,
                    "regime": t.regime,
                    "exit_reason": None,
                }
            )
        return out

    return {"summary": _summary(), "by_symbol": _by_symbol(), "recent": _recent(20)}


def _stdev(xs: list[float]) -> float:
    n = len(xs)
    if n < 2:
        return 0.0
    m = sum(xs) / n
    var = sum((x - m) ** 2 for x in xs) / (n - 1)
    return math.sqrt(var)


def read_perf_dict_for_account(db: Session, account_id: int) -> dict[str, Any]:
    """Shape compatible with _read_perf() file structure."""
    rows = db.execute(select(Trade).where(Trade.account_id == account_id)).scalars().all()
    trades_out: list[dict[str, Any]] = []
    for t in rows:
        trades_out.append(
            {
                "symbol": t.symbol,
                "side": "LONG",
                "entry_ts": t.entry_time.isoformat() if t.entry_time else None,
                "exit_ts": t.exit_time.isoformat() if t.exit_time else None,
                "entry_price": float(t.entry_price) if t.entry_price is not None else None,
                "qty": float(t.entry_qty) if t.entry_qty is not None else None,
                "exit_price": float(t.exit_price) if t.exit_price is not None else None,
                "pnl_usd": float(t.pnl) if t.pnl is not None else None,
                "pnl_pct": float(t.pnl_pct) if t.pnl_pct is not None else None,
                "mode": t.trading_mode,
                "regime": t.regime,
            }
        )
    pl = trade_performance_payload(db, account_id)
    return {"trades": trades_out, "summary": pl["summary"]}


def realised_pnl_today_db(db: Session, account_id: int, symbol: str | None = None) -> float:
    start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    q = select(func.coalesce(func.sum(Trade.pnl), 0)).where(
        Trade.account_id == account_id,
        Trade.exit_time.isnot(None),
        Trade.exit_time >= start,
        Trade.exit_time < end,
    )
    if symbol:
        q = q.where(Trade.symbol == symbol)
    val = db.execute(q).scalar()
    return round(float(val or 0.0), 4)


def decrypt_account_keys(account: Account) -> tuple[str | None, str | None]:
    k = decrypt_field(account.alpaca_api_key) if account.alpaca_api_key else None
    s = decrypt_field(account.alpaca_api_secret) if account.alpaca_api_secret else None
    return k, s


def seed_admin_user(
    db: Session,
    *,
    email: str,
    username: str,
    password: str,
    config_dir: Path,
    alpaca_key: str | None,
    alpaca_secret: str | None,
) -> User:
    """Idempotent bootstrap of the primary admin (paper account + Alpaca secrets)."""
    email_n = normalise_email(email)
    existing = db.execute(select(User).where(User.email == email_n)).scalar_one_or_none()
    if existing:
        return existing
    user = User(
        email=email_n,
        username=username,
        password_hash=hash_password(password),
        totp_secret=pyotp.random_base32(),
        tier="pro",
        totp_enabled=False,
        is_admin=True,
        unsubscribe_token=secrets.token_hex(32),
    )
    db.add(user)
    db.flush()
    account = Account(
        user_id=user.id,
        account_type="paper",
        account_status="active",
        alpaca_api_key=encrypt_field(alpaca_key) if alpaca_key else None,
        alpaca_api_secret=encrypt_field(alpaca_secret) if alpaca_secret else None,
    )
    db.add(account)
    db.flush()
    plat = get_platform_settings_dict(db)
    agents_avail = plat.get("agents_available")
    if not isinstance(agents_avail, dict):
        agents_avail = {}
    blob = build_default_agents_blob(config_dir, agents_avail)
    db.add(
        TradingConfiguration(
            account_id=account.id,
            agents=blob,
            llm_enabled=True,
            trading_mode="day_trading",
        )
    )
    db.flush()
    return user


def reset_db_user_password(
    db: Session,
    *,
    password: str,
    email: str | None = None,
    username: str | None = None,
) -> User:
    """Set a new password, clear lockout/TOTP requirement, ensure is_admin.

    Match by normalised ``email`` first, then by ``username`` (for ``login_id``
    without ``@``).
    """
    user: User | None = None
    if email:
        email_n = normalise_email(email)
        user = db.execute(select(User).where(User.email == email_n)).scalar_one_or_none()
    if user is None and username:
        un = username.strip()
        user = db.execute(select(User).where(User.username == un)).scalar_one_or_none()
    if user is None:
        raise ValueError(
            "User not found in database. Create one with scripts/seed_admin.py first."
        )
    user.password_hash = hash_password(password)
    user.totp_enabled = False
    user.failed_login_count = 0
    user.locked_until = None
    user.is_admin = True
    return user
