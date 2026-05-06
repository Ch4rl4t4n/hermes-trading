"""Referral codes, tracking, and first-login bonus grants."""

from __future__ import annotations

import secrets
import string
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from core.models import User

REFERRAL_CODE_ALPHABET = string.ascii_uppercase + string.digits
REFERRAL_CODE_LEN = 8
REFERRAL_BONUS_SLOTS = 3
REFERRAL_BONUS_DAYS = 30


def generate_referral_code() -> str:
    return "".join(secrets.choice(REFERRAL_CODE_ALPHABET) for _ in range(REFERRAL_CODE_LEN))


def ensure_user_referral_code(sess: Session, user: User) -> str:
    existing = getattr(user, "referral_code", None)
    if existing:
        return str(existing).strip().upper()
    for _ in range(48):
        cand = generate_referral_code()
        taken = sess.execute(
            text("SELECT 1 FROM users WHERE referral_code = :c LIMIT 1"),
            {"c": cand},
        ).first()
        if taken is None:
            user.referral_code = cand
            sess.flush()
            return cand
    cand = secrets.token_hex(4).upper()[:8]
    user.referral_code = cand
    sess.flush()
    return cand


def apply_referral_tracking(sess: Session, user: User, ref_code: str | None) -> dict[str, Any]:
    """Attach referrer to a new account. Safe to call multiple times."""
    code = (ref_code or "").strip().upper()
    out: dict[str, Any] = {"success": True}
    if not code or len(code) > 20:
        return out
    if getattr(user, "referred_by", None):
        return out
    ref_row = sess.execute(
        text("SELECT id, username FROM users WHERE UPPER(TRIM(referral_code)) = :c LIMIT 1"),
        {"c": code},
    ).mappings().first()
    if not ref_row or int(ref_row["id"]) == int(user.id):
        return out
    rid = int(ref_row["id"])
    sess.execute(
        text("UPDATE users SET referred_by = :rb WHERE id = :uid AND referred_by IS NULL"),
        {"rb": rid, "uid": user.id},
    )
    sess.execute(
        text("""
        INSERT INTO referrals (referrer_id, referred_id, bonus_granted)
        VALUES (:rid, :uid, FALSE)
        ON CONFLICT (referred_id) DO NOTHING
        """),
        {"rid": rid, "uid": user.id},
    )
    out["referrer_name"] = str(ref_row["username"])
    return out


def _stack_referral_bonus(user: User) -> None:
    now = datetime.now(timezone.utc)
    cur = int(getattr(user, "referral_bonus_slots", 0) or 0)
    user.referral_bonus_slots = cur + REFERRAL_BONUS_SLOTS
    user.referral_bonus_expires_at = now + timedelta(days=REFERRAL_BONUS_DAYS)


def try_grant_referral_first_login(sess: Session, user: User) -> None:
    """When a referred user logs in for the first time after tracking, bonus both parties."""
    row = sess.execute(
        text("""
        SELECT id, referrer_id FROM referrals
        WHERE referred_id = :uid AND (bonus_granted = FALSE OR bonus_granted IS NULL)
        LIMIT 1
        FOR UPDATE
        """),
        {"uid": user.id},
    ).mappings().first()
    if not row:
        return
    ref_id = int(row["referrer_id"])
    ref_pk = int(row["id"])
    referrer = sess.get(User, ref_id)
    if referrer is None:
        return
    _stack_referral_bonus(referrer)
    _stack_referral_bonus(user)
    sess.execute(
        text("UPDATE referrals SET bonus_granted = TRUE WHERE id = :id"),
        {"id": ref_pk},
    )
    sess.execute(
        text("""
        INSERT INTO notifications (user_id, type, title, message)
        VALUES (:uid, 'referral', :title, :msg)
        """),
        {
            "uid": ref_id,
            "title": "Referral bonus",
            "msg": "Tvoj priateľ sa pripojil! Získal si +3 agent sloty na 30 dní 🎉",
        },
    )
    sess.execute(
        text("""
        INSERT INTO notifications (user_id, type, title, message)
        VALUES (:uid, 'referral', :title, :msg)
        """),
        {
            "uid": user.id,
            "title": "Bonus za pozvánku",
            "msg": "Prepojili sme tvoj účet s pozvánkou — +3 extra sloty na agentov na 30 dní! 🎉",
        },
    )


def referral_count_for_user(sess: Session, user_id: int) -> int:
    r = sess.execute(
        text("SELECT COUNT(*)::int AS c FROM referrals WHERE referrer_id = :uid"),
        {"uid": user_id},
    ).mappings().first()
    return int(r["c"]) if r else 0


def referral_info_for_user(sess: Session, user: User, app_public_url: str) -> dict[str, Any]:
    code = ensure_user_referral_code(sess, user)
    base = (app_public_url or "").strip().rstrip("/") or "https://app.letagentscook.lol"
    url = f"{base}/?ref={code}"
    now = datetime.now(timezone.utc)
    exp = getattr(user, "referral_bonus_expires_at", None)
    bonus_active = False
    if exp is not None:
        if getattr(exp, "tzinfo", None) is None:
            exp = exp.replace(tzinfo=timezone.utc)
        bonus_active = bool(exp > now and int(getattr(user, "referral_bonus_slots", 0) or 0) > 0)
    return {
        "referral_code": code,
        "referral_url": url,
        "referral_count": referral_count_for_user(sess, user.id),
        "bonus_active": bonus_active,
        "bonus_expires_at": exp.isoformat() if exp and bonus_active else None,
    }
