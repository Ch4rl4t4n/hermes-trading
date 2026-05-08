"""Stripe Checkout, Customer Portal, and webhooks for subscription billing."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Optional

import stripe
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from core import saas_helpers
from core.models import PlatformSetting, User
from core.tier_access import (
    TIER_ELITE,
    TIER_MEDIUM,
    TIER_PRO,
    TIER_RANK,
    effective_tier,
    normalize_tier,
)

log = logging.getLogger("stripe_billing")

STRIPE_TIER_MEDIUM = TIER_MEDIUM
STRIPE_TIER_PRO = TIER_PRO
STRIPE_TIER_ELITE = TIER_ELITE
_VALID_CHECKOUT_TIERS = frozenset({STRIPE_TIER_MEDIUM, STRIPE_TIER_PRO})
_VALID_EUR_CHECKOUT_TIERS = frozenset({STRIPE_TIER_PRO, STRIPE_TIER_ELITE})


def _public_base_url() -> str:
    return (os.getenv("DASHBOARD_PUBLIC_BASE_URL") or "https://app.letagentscook.lol").strip().rstrip("/")


def _webhook_secret() -> str:
    return (os.getenv("STRIPE_WEBHOOK_SECRET") or "").strip()


def _secret_key() -> str:
    return (os.getenv("STRIPE_SECRET_KEY") or "").strip()


def configure_stripe() -> None:
    key = _secret_key()
    if key:
        stripe.api_key = key


def _get_catalog_from_db(sess: Session) -> dict[str, Any]:
    plat = saas_helpers.get_platform_settings_dict(sess)
    raw = plat.get("stripe") or {}
    return raw if isinstance(raw, dict) else {}


def _save_catalog(sess: Session, catalog: dict[str, Any]) -> None:
    row = sess.get(PlatformSetting, "stripe")
    if row:
        base = dict(row.value) if isinstance(row.value, dict) else {}
        base.update(catalog)
        row.value = base
    else:
        sess.add(PlatformSetting(key="stripe", value=dict(catalog)))
    sess.flush()


def ensure_stripe_catalog(sess: Session) -> dict[str, str]:
    """Create Stripe products/prices if missing; persist IDs in platform_settings.stripe."""
    configure_stripe()
    if not _secret_key():
        raise RuntimeError("STRIPE_SECRET_KEY is not set.")

    catalog = _get_catalog_from_db(sess)
    pm = catalog.get("price_medium_id")
    pp = catalog.get("price_pro_id")
    if isinstance(pm, str) and pm.startswith("price_") and isinstance(pp, str) and pp.startswith("price_"):
        return {"price_medium_id": pm, "price_pro_id": pp, **{k: v for k, v in catalog.items() if "product" in k}}

    out: dict[str, str] = {}

    prod_m = stripe.Product.create(
        name="LETAGENTSCOOK Medium",
        description="LATC Medium — monthly subscription",
        metadata={"latc_tier": STRIPE_TIER_MEDIUM},
        idempotency_key="latc_product_medium_v1",
    )
    price_m = stripe.Price.create(
        product=prod_m.id,
        unit_amount=2900,
        currency="usd",
        recurring={"interval": "month"},
        metadata={"latc_tier": STRIPE_TIER_MEDIUM},
        idempotency_key="latc_price_medium_monthly_v1",
    )
    out["product_medium_id"] = prod_m.id
    out["price_medium_id"] = price_m.id

    prod_p = stripe.Product.create(
        name="LETAGENTSCOOK Pro",
        description="LATC Pro — monthly subscription",
        metadata={"latc_tier": STRIPE_TIER_PRO},
        idempotency_key="latc_product_pro_v1",
    )
    price_p = stripe.Price.create(
        product=prod_p.id,
        unit_amount=9900,
        currency="usd",
        recurring={"interval": "month"},
        metadata={"latc_tier": STRIPE_TIER_PRO},
        idempotency_key="latc_price_pro_monthly_v1",
    )
    out["product_pro_id"] = prod_p.id
    out["price_pro_id"] = price_p.id

    _save_catalog(sess, out)
    return out


def _env_price_to_tier() -> dict[str, str]:
    out: dict[str, str] = {}
    pairs = [
        ("STRIPE_PRICE_PRO_MONTHLY", STRIPE_TIER_PRO),
        ("STRIPE_PRICE_PRO_YEARLY", STRIPE_TIER_PRO),
        ("STRIPE_PRICE_ELITE_MONTHLY", STRIPE_TIER_ELITE),
        ("STRIPE_PRICE_ELITE_YEARLY", STRIPE_TIER_ELITE),
    ]
    for env_k, tier_v in pairs:
        v = (os.getenv(env_k) or "").strip()
        if v.startswith("price_"):
            out[v] = tier_v
    return out


def _resolve_eur_price_id(tier: str, billing: str) -> Optional[str]:
    t = normalize_tier(tier)
    b = (billing or "monthly").strip().lower()
    if b not in ("monthly", "yearly"):
        b = "monthly"
    key_map = {
        (STRIPE_TIER_PRO, "monthly"): "STRIPE_PRICE_PRO_MONTHLY",
        (STRIPE_TIER_PRO, "yearly"): "STRIPE_PRICE_PRO_YEARLY",
        (STRIPE_TIER_ELITE, "monthly"): "STRIPE_PRICE_ELITE_MONTHLY",
        (STRIPE_TIER_ELITE, "yearly"): "STRIPE_PRICE_ELITE_YEARLY",
    }
    env_k = key_map.get((t, b))
    if not env_k:
        return None
    v = (os.getenv(env_k) or "").strip()
    return v if v.startswith("price_") else None


def _apply_subscription_stripe_fields(user: User, subscription: dict[str, Any]) -> None:
    user.stripe_subscription_status = subscription.get("status")
    items = (subscription.get("items") or {}).get("data") or []
    if items:
        iv = (items[0].get("price") or {}).get("recurring", {}) or {}
        interval = iv.get("interval") or "month"
        user.billing_cycle = "yearly" if interval == "year" else "monthly"
    cpe = subscription.get("current_period_end")
    if cpe:
        user.tier_expires_at = datetime.fromtimestamp(int(cpe), tz=timezone.utc)
    else:
        user.tier_expires_at = None


def price_id_for_tier(catalog: dict[str, Any], tier: str) -> str:
    tier = normalize_tier(tier)
    if tier == STRIPE_TIER_MEDIUM:
        pid = catalog.get("price_medium_id")
    elif tier == STRIPE_TIER_PRO:
        pid = catalog.get("price_pro_id")
    else:
        raise ValueError("Invalid tier for checkout.")
    if not isinstance(pid, str) or not pid.startswith("price_"):
        raise RuntimeError("Stripe catalog missing price id; retry after catalog sync.")
    return pid


def tier_for_price_id(catalog: dict[str, Any], price_id: str | None) -> Optional[str]:
    if not price_id:
        return None
    env_t = _env_price_to_tier().get(price_id)
    if env_t:
        return normalize_tier(env_t)
    if price_id == catalog.get("price_medium_id"):
        return STRIPE_TIER_MEDIUM
    if price_id == catalog.get("price_pro_id"):
        return STRIPE_TIER_PRO
    return None


def _ensure_customer(sess: Session, user: User) -> str:
    configure_stripe()
    if user.stripe_customer_id:
        return user.stripe_customer_id
    cust = stripe.Customer.create(
        email=user.email,
        metadata={"user_id": str(user.id), "username": user.username},
        idempotency_key=f"latc_customer_{user.id}_v1",
    )
    user.stripe_customer_id = cust.id
    sess.flush()
    return cust.id


def create_checkout_session(sess: Session, user: User, tier: str) -> str:
    tier = normalize_tier(tier)
    if tier not in _VALID_CHECKOUT_TIERS:
        raise ValueError("Tier must be medium or pro.")
    if user.is_admin:
        raise ValueError("Admin accounts do not use paid checkout.")
    cur = normalize_tier(user.tier)
    paid_tiers = (STRIPE_TIER_MEDIUM, STRIPE_TIER_PRO, STRIPE_TIER_ELITE)
    if TIER_RANK.get(cur, 0) >= TIER_RANK.get(tier, 0) and cur in paid_tiers:
        raise ValueError("Already on this plan or higher — use the billing portal to change plans.")

    ensure_stripe_catalog(sess)
    catalog = _get_catalog_from_db(sess)
    price_id = price_id_for_tier(catalog, tier)
    cust_id = _ensure_customer(sess, user)

    base = _public_base_url()
    sess_obj = stripe.checkout.Session.create(
        customer=cust_id,
        mode="subscription",
        line_items=[{"price": price_id, "quantity": 1}],
        success_url=f"{base}/?payment=success",
        cancel_url=f"{base}/?payment=cancelled",
        client_reference_id=str(user.id),
        metadata={"user_id": str(user.id), "tier": tier},
        subscription_data={"metadata": {"user_id": str(user.id), "tier": tier}},
        allow_promotion_codes=True,
        idempotency_key=f"latc_checkout_{user.id}_{tier}_{int(datetime.now(timezone.utc).timestamp())}"[:255],
    )
    url = sess_obj.url
    if not url:
        raise RuntimeError("Checkout session missing URL.")
    saas_helpers.record_audit(
        sess,
        user_id=user.id,
        account_id=None,
        action="billing.checkout_started",
        details={"tier": tier, "session_id": sess_obj.id},
        ip=None,
    )
    sess.flush()
    return url


def create_eur_checkout_session(
    sess: Session,
    user: User,
    *,
    tier: str,
    billing: str = "monthly",
    price_id: str | None = None,
) -> str:
    """Checkout for Pro / Elite using EUR prices from env (``STRIPE_PRICE_*``)."""
    tier = normalize_tier(tier)
    if tier not in _VALID_EUR_CHECKOUT_TIERS:
        raise ValueError("Tier must be pro or elite.")
    if user.is_admin:
        raise ValueError("Admin accounts do not use paid checkout.")
    cur = normalize_tier(user.tier)
    paid_tiers = (STRIPE_TIER_MEDIUM, STRIPE_TIER_PRO, STRIPE_TIER_ELITE)
    if TIER_RANK.get(cur, 0) >= TIER_RANK.get(tier, 0) and cur in paid_tiers:
        raise ValueError("Already on this plan or higher — use the billing portal to change plans.")
    configure_stripe()
    pid = (price_id or "").strip() if price_id else ""
    if not pid.startswith("price_"):
        pid = _resolve_eur_price_id(tier, billing) or ""
    if not pid.startswith("price_"):
        raise RuntimeError(
            "Stripe EUR price not configured. Set STRIPE_PRICE_PRO_* / STRIPE_PRICE_ELITE_* in .env "
            "or run scripts/create_stripe_products.py."
        )
    cust_id = _ensure_customer(sess, user)
    base = _public_base_url()
    sess_obj = stripe.checkout.Session.create(
        customer=cust_id,
        mode="subscription",
        line_items=[{"price": pid, "quantity": 1}],
        success_url=f"{base}/?checkout=success&payment=success&session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{base}/?checkout=cancelled&payment=cancelled",
        client_reference_id=str(user.id),
        metadata={"user_id": str(user.id), "tier": tier, "billing": billing},
        subscription_data={"metadata": {"user_id": str(user.id), "tier": tier}},
        allow_promotion_codes=True,
        idempotency_key=(
            f"hermes_eur_checkout_{user.id}_{tier}_{billing}_{int(datetime.now(timezone.utc).timestamp())}"
        )[:255],
    )
    url = sess_obj.url
    if not url:
        raise RuntimeError("Checkout session missing URL.")
    saas_helpers.record_audit(
        sess,
        user_id=user.id,
        account_id=None,
        action="billing.checkout_started",
        details={"tier": tier, "billing": billing, "session_id": sess_obj.id, "price_id": pid},
        ip=None,
    )
    sess.flush()
    return url


def create_customer_portal_session(sess: Session, user: User, *, return_url: str | None = None) -> str:
    configure_stripe()
    if not user.stripe_customer_id:
        raise ValueError("No billing account yet — subscribe first.")
    base = _public_base_url()
    ret = return_url if return_url else f"{base}/"
    portal = stripe.billing_portal.Session.create(
        customer=user.stripe_customer_id,
        return_url=ret,
    )
    url = portal.url
    if not url:
        raise RuntimeError("Portal session missing URL.")
    saas_helpers.record_audit(
        sess,
        user_id=user.id,
        account_id=None,
        action="billing.portal_opened",
        details={},
        ip=None,
    )
    sess.flush()
    return url


def cancel_subscription_at_period_end(sess: Session, user: User) -> None:
    configure_stripe()
    if not user.stripe_subscription_id:
        raise ValueError("No active subscription.")
    stripe.Subscription.modify(user.stripe_subscription_id, cancel_at_period_end=True)
    saas_helpers.record_audit(
        sess,
        user_id=user.id,
        account_id=None,
        action="billing.cancel_scheduled",
        details={"subscription_id": user.stripe_subscription_id},
        ip=None,
    )
    sess.flush()


def _user_by_customer(sess: Session, customer_id: str | None) -> Optional[User]:
    if not customer_id:
        return None
    return sess.execute(select(User).where(User.stripe_customer_id == customer_id)).scalar_one_or_none()


def _sync_user_tier_from_subscription(
    sess: Session,
    user: User,
    subscription: stripe.Subscription,
    catalog: dict[str, Any],
) -> Optional[str]:
    """Apply recurring price → user.tier. Returns new tier or None."""
    sub_d: dict[str, Any] = subscription if isinstance(subscription, dict) else subscription.to_dict()  # type: ignore[assignment]
    items = (sub_d.get("items") or {}).get("data") or []
    price_id = None
    if items:
        price_id = (items[0].get("price") or {}).get("id")
    tier = tier_for_price_id(catalog, price_id)
    if tier:
        user.tier = tier
        sid = sub_d.get("id")
        if sid:
            user.stripe_subscription_id = str(sid)
    _apply_subscription_stripe_fields(user, sub_d)
    return tier


def _apply_subscription_items_to_user(
    sess: Session,
    user: User,
    subscription: stripe.Subscription | dict[str, Any],
    catalog: dict[str, Any],
) -> None:
    old = normalize_tier(user.tier)
    tier = _sync_user_tier_from_subscription(sess, user, subscription, catalog)  # type: ignore[arg-type]
    if tier:
        sub_d = subscription if isinstance(subscription, dict) else subscription.to_dict()  # type: ignore[union-attr]
        items = (sub_d.get("items") or {}).get("data") or []
        price_id = (items[0].get("price") or {}).get("id") if items else None
        saas_helpers.record_audit(
            sess,
            user_id=user.id,
            account_id=None,
            action="billing.subscription_updated",
            details={"tier": tier, "from": old, "subscription_id": sub_d.get("id"), "price_id": price_id},
            ip=None,
        )


def handle_webhook(sess: Session, payload: bytes, sig_header: str | None) -> tuple[dict[str, Any], int]:
    """Verify signature and apply event. Returns (json body for Stripe, http code)."""
    secret = _webhook_secret()
    if not secret or secret.lower() in ("placeholder", "changeme", "your-secret"):
        log.warning("STRIPE_WEBHOOK_SECRET not set or placeholder — refusing webhook.")
        return {"error": "Webhook not configured"}, 503

    try:
        event = stripe.Webhook.construct_event(payload, sig_header or "", secret)
    except ValueError:
        return {"error": "Invalid payload"}, 400
    except stripe.SignatureVerificationError:
        return {"error": "Invalid signature"}, 400

    configure_stripe()
    catalog = _get_catalog_from_db(sess)
    etype = event.get("type")
    event_id = str(event.get("id") or "").strip()
    data_object = (event.get("data") or {}).get("object") or {}

    try:
        sess.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS stripe_webhook_events (
                    event_id TEXT PRIMARY KEY,
                    event_type TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
        )
        if event_id:
            inserted = sess.execute(
                text(
                    """
                    INSERT INTO stripe_webhook_events (event_id, event_type)
                    VALUES (:eid, :etype)
                    ON CONFLICT (event_id) DO NOTHING
                    RETURNING event_id
                    """
                ),
                {"eid": event_id, "etype": str(etype or "")[:120]},
            ).first()
            if inserted is None:
                sess.rollback()
                return {"received": True, "duplicate": True, "type": etype}, 200
        sess.commit()
    except Exception:
        sess.rollback()
        log.exception("Stripe webhook idempotency guard failed for %s", etype)
        return {"error": "Webhook persistence unavailable"}, 503

    try:
        if etype == "checkout.session.completed":
            session = data_object
            uid = session.get("client_reference_id") or (session.get("metadata") or {}).get("user_id")
            cust = session.get("customer")
            sub_id = session.get("subscription")
            if uid:
                user = sess.get(User, int(uid))
                if user:
                    if cust and not user.stripe_customer_id:
                        user.stripe_customer_id = str(cust)
                    if sub_id:
                        old_tier = normalize_tier(user.tier)
                        user.stripe_subscription_id = str(sub_id)
                        if not catalog.get("price_medium_id") and not _env_price_to_tier():
                            ensure_stripe_catalog(sess)
                            catalog = _get_catalog_from_db(sess)
                        sub = stripe.Subscription.retrieve(str(sub_id))
                        _sync_user_tier_from_subscription(sess, user, sub, catalog)
                        new_tier = normalize_tier(user.tier)
                        if new_tier != old_tier:
                            sess.execute(
                                text("""
                                    INSERT INTO notifications (user_id, type, title, message)
                                    VALUES (:uid, 'upgrade', :title, :msg)
                                """),
                                {
                                    "uid": user.id,
                                    "title": f"Vitaj v Hermes {new_tier.title()}!",
                                    "msg": (
                                        f"Tvoj účet bol upgradovaný na {new_tier.title()} plán. "
                                        "Všetky nové limity sú aktívne."
                                    ),
                                },
                            )
                    saas_helpers.record_audit(
                        sess,
                        user_id=user.id,
                        account_id=None,
                        action="billing.checkout_completed",
                        details={"session_id": session.get("id"), "subscription_id": sub_id},
                        ip=None,
                    )
        elif etype == "customer.subscription.updated":
            sub = data_object
            cust = sub.get("customer")
            user = _user_by_customer(sess, str(cust) if cust else None)
            if not user:
                md = (sub.get("metadata") or {}).get("user_id")
                if md:
                    user = sess.get(User, int(md))
            if user:
                if not catalog.get("price_medium_id") and not _env_price_to_tier():
                    ensure_stripe_catalog(sess)
                    catalog = _get_catalog_from_db(sess)
                user.stripe_subscription_id = sub.get("id") or user.stripe_subscription_id
                _apply_subscription_stripe_fields(user, sub)
                st = str(sub.get("status") or "")
                if st in ("active", "trialing"):
                    _apply_subscription_items_to_user(sess, user, sub, catalog)
                elif st in ("canceled", "unpaid", "incomplete_expired"):
                    if not user.is_admin:
                        user.tier = "basic"
        elif etype == "customer.subscription.deleted":
            sub = data_object
            cust = sub.get("customer")
            user = _user_by_customer(sess, str(cust) if cust else None)
            if user:
                user.stripe_subscription_id = None
                user.stripe_subscription_status = "canceled"
                user.tier_expires_at = None
                user.billing_cycle = "monthly"
                if not user.is_admin:
                    user.tier = "basic"
                saas_helpers.record_audit(
                    sess,
                    user_id=user.id,
                    account_id=None,
                    action="billing.subscription_ended",
                    details={"subscription_id": sub.get("id")},
                    ip=None,
                )
        elif etype == "invoice.payment_failed":
            inv = data_object
            cust = inv.get("customer")
            user = _user_by_customer(sess, str(cust) if cust else None)
            if user:
                user.stripe_subscription_status = "past_due"
            saas_helpers.record_audit(
                sess,
                user_id=user.id if user else None,
                account_id=None,
                action="billing.payment_failed",
                details={"invoice_id": inv.get("id"), "customer": cust},
                ip=None,
            )
        sess.commit()
    except Exception:
        sess.rollback()
        log.exception("Stripe webhook handler failed for %s", etype)
        return {"error": "Webhook processing failed", "type": etype}, 500
    return {"received": True, "type": etype}, 200


def get_subscription_status(sess: Session, user: User) -> dict[str, Any]:
    configure_stripe()
    et = effective_tier(user)
    nt = normalize_tier(user.tier)
    out: dict[str, Any] = {
        "tier": nt,
        "effective_tier": et,
        "status": "none",
        "next_billing_date": None,
        "cancel_at": None,
        "cancel_at_period_end": False,
        "stripe_customer_id": user.stripe_customer_id,
    }
    if not user.stripe_subscription_id or not _secret_key():
        return out
    try:
        sub = stripe.Subscription.retrieve(user.stripe_subscription_id)
        out["status"] = sub.get("status") or "unknown"
        cpe = sub.get("current_period_end")
        if cpe:
            out["next_billing_date"] = datetime.fromtimestamp(int(cpe), tz=timezone.utc).isoformat()
        ca = sub.get("cancel_at")
        if ca:
            out["cancel_at"] = datetime.fromtimestamp(int(ca), tz=timezone.utc).isoformat()
        out["cancel_at_period_end"] = bool(sub.get("cancel_at_period_end"))
    except Exception as exc:  # noqa: BLE001
        log.warning("Could not load subscription %s: %s", user.stripe_subscription_id, exc)
        out["status"] = "unknown"
    return out
