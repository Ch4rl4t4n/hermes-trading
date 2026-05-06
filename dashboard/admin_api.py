"""Admin CMS API handlers (registered on the Flask app in app.py)."""

from __future__ import annotations

import os
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

from flask import jsonify, request
from sqlalchemy import asc, case, desc, func, or_, select, text

from core import saas_helpers
from core.agent_marketplace import assign_demo_agents
from core.tier_access import effective_tier, normalize_tier
from core.models import (
    Account,
    Announcement,
    AnnouncementDismissal,
    AuditLog,
    Trade,
    TradingConfiguration,
    User,
)

if TYPE_CHECKING:
    from flask import Flask

_VALID_ADMIN_TIERS = frozenset({"basic", "medium", "pro"})
_VALID_ADMIN_USER_CREATE_TIERS = frozenset({"basic", "medium", "pro", "admin"})


def _format_audit_message(action: str, details: dict[str, Any] | None) -> str:
    d = details or {}
    em = str(d.get("email") or "").strip()
    tid = d.get("target_user_id")
    em_or_id = em or (f"user #{tid}" if tid is not None else "")

    if action == "admin.create_user":
        tl = d.get("tier_label") or d.get("tier") or ""
        return f"Admin created user {em or d.get('email', '')} with tier {tl}"
    if action == "admin.delete_user":
        return f"Admin deleted user {em or em_or_id}"
    if action == "admin.user_suspend":
        if d.get("suspend"):
            return f"Admin suspended user {em_or_id}"
        return f"Admin unsuspended user {em_or_id}"
    if action == "admin.user_unsuspend":
        return f"Admin unsuspended user {em_or_id}"
    if action == "admin.change_tier":
        return (
            f"Admin changed user {em_or_id} tier from {d.get('from', '?')} to {d.get('to', '?')}"
        )
    if action == "admin.reset_password":
        return f"Admin reset password for {em_or_id}"
    if action == "admin.settings_update":
        keys = d.get("keys") or []
        if isinstance(keys, list) and keys:
            joined = ", ".join(str(k) for k in keys)
            return f"Admin changed platform settings ({joined})"
        return "Admin changed platform settings"
    if action == "admin.announcement_create":
        return f"Admin published announcement: {d.get('title', '')}"
    if action == "admin.assign_demo_agents":
        return (
            f"Assigned demo marketplace agents ({d.get('assignments', 0)} subs) "
            f"for {d.get('users', 0)} users without active subscriptions"
        )
    if action == "billing.checkout_started":
        return f"Stripe checkout started ({d.get('tier', '')})"
    if action == "billing.checkout_completed":
        return "Stripe checkout completed — subscription linked"
    if action == "billing.portal_opened":
        return "Opened Stripe Customer Portal"
    if action == "billing.subscription_updated":
        return f"Subscription updated → {d.get('tier', '?')} (was {d.get('from', '?')})"
    if action == "billing.subscription_ended":
        return "Subscription ended — tier reset to Basic"
    if action == "billing.payment_failed":
        inv = d.get("invoice_id") or ""
        return f"Invoice payment failed{f' ({inv})' if inv else ''}"
    if action == "billing.cancel_scheduled":
        return "Subscription set to cancel at period end"
    if action.startswith("billing."):
        return f"Billing: {action.replace('billing.', '')}"
    return f"Admin action: {action} — {d}"


def _admin_session_user_id(app_resolve, app_g):
    app_resolve()
    u = getattr(app_g, "db_user", None)
    return u.id if u else None


def _admin_audit(sess, app_resolve, app_g, action: str, details: dict[str, Any] | None) -> None:
    saas_helpers.record_audit(
        sess,
        user_id=_admin_session_user_id(app_resolve, app_g),
        account_id=None,
        action=action,
        details=details or {},
        ip=request.remote_addr or "?",
    )


def register_admin_routes(
    app,
    *,
    db,
    admin_required,
    login_required,
    _load_configs,
    _state,
    _PERF_PATH,
    _uptime_str,
    DRY_RUN,
    ALPACA_PAPER,
    resolve_identity,
    g,
    config_dir: Path,
    google_oauth_configured: bool = False,
) -> None:
    """Attach routes to Flask ``app``."""

    def _agents_unit() -> str:
        return (os.getenv("HERMES_AGENTS_SYSTEMD_UNIT") or "hermes-agents").strip()

    def _dashboard_unit() -> str:
        return (os.getenv("HERMES_DASHBOARD_SYSTEMD_UNIT") or "hermes-dashboard").strip()

    def _dashboard_systemd_active() -> Optional[bool]:
        try:
            r = subprocess.run(
                ["systemctl", "is-active", _dashboard_unit()],
                capture_output=True,
                text=True,
                timeout=3,
            )
            out = (r.stdout or "").strip()
            if out == "active":
                return True
            if out in ("inactive", "failed", "activating"):
                return False
            return None
        except (OSError, subprocess.TimeoutExpired):
            return None

    def _agents_systemd_active() -> Optional[bool]:
        try:
            r = subprocess.run(
                ["systemctl", "is-active", _agents_unit()],
                capture_output=True,
                text=True,
                timeout=3,
            )
            out = (r.stdout or "").strip()
            if out == "active":
                return True
            if out in ("inactive", "failed", "activating"):
                return False
            return None
        except (OSError, subprocess.TimeoutExpired):
            return None

    def _database_ok(sess) -> bool:
        try:
            sess.execute(text("SELECT 1"))
            return True
        except Exception:
            return False

    def _last_trade_activity_minutes(sess) -> Optional[float]:
        mx_exit = sess.scalar(select(func.max(Trade.exit_time)))
        mx_entry = sess.scalar(select(func.max(Trade.entry_time)))
        last: Optional[datetime] = None
        for x in (mx_exit, mx_entry):
            if x is not None and (last is None or x > last):
                last = x
        if last is None:
            return None
        now = datetime.now(timezone.utc)
        secs = (now - last).total_seconds()
        if secs < 0:
            return 0.0
        return round(secs / 60.0, 1)

    @app.route("/api/admin/summary")
    @admin_required
    def api_admin_summary():
        if db.SessionLocal is None:
            return jsonify({"error": "database unavailable"}), 503
        sess = db.db_session()
        start_day = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        week_ago = start_day - timedelta(days=7)
        total_users = int(sess.scalar(select(func.count()).select_from(User)) or 0)
        active_today = int(
            sess.scalar(select(func.count()).select_from(User).where(User.last_login >= start_day)) or 0
        )
        new_this_week = int(
            sess.scalar(select(func.count()).select_from(User).where(User.created_at >= week_ago)) or 0
        )
        total_trades = int(sess.scalar(select(func.count()).select_from(Trade)) or 0)
        total_paper_accounts = int(
            sess.scalar(select(func.count()).select_from(Account).where(Account.account_type == "paper")) or 0
        )
        total_real_accounts = int(
            sess.scalar(select(func.count()).select_from(Account).where(Account.account_type == "real")) or 0
        )
        trades_today = int(
            sess.scalar(select(func.count()).select_from(Trade).where(Trade.entry_time >= start_day)) or 0
        )

        plat = saas_helpers.get_platform_settings_dict(sess)
        reg = plat.get("registration") or {}
        registration_open = reg.get("open") is not False

        signups_by_day: list[dict[str, Any]] = []
        trades_by_day: list[dict[str, Any]] = []
        for i in range(6, -1, -1):
            d0 = start_day - timedelta(days=i)
            d1 = d0 + timedelta(days=1)
            day_key = d0.date().isoformat()
            su = int(
                sess.scalar(
                    select(func.count()).select_from(User).where(
                        User.created_at >= d0,
                        User.created_at < d1,
                    )
                )
                or 0
            )
            signups_by_day.append({"date": day_key, "count": su})
            ts = func.coalesce(Trade.entry_time, Trade.exit_time)
            tc = int(
                sess.scalar(
                    select(func.count()).select_from(Trade).where(ts >= d0, ts < d1, ts.isnot(None))
                )
                or 0
            )
            trades_by_day.append({"date": day_key, "count": tc})

        recent_logs = (
            sess.execute(select(AuditLog).order_by(desc(AuditLog.created_at)).limit(10)).scalars().all()
        )
        users_by_tier: dict[str, int] = {"basic": 0, "medium": 0, "pro": 0, "admin": 0}
        for tier_raw, is_adm in sess.execute(select(User.tier, User.is_admin)).all():
            if is_adm:
                users_by_tier["admin"] += 1
            else:
                nt = normalize_tier(tier_raw)
                if nt not in ("basic", "medium", "pro"):
                    nt = "basic"
                users_by_tier[nt] += 1

        billing_logs = (
            sess.execute(
                select(AuditLog)
                .where(AuditLog.action.like("billing.%"))
                .order_by(desc(AuditLog.created_at))
                .limit(25)
            )
            .scalars()
            .all()
        )
        recent_billing_events = []
        for al in billing_logs:
            d = al.details or {}
            msg = _format_audit_message(al.action, d if isinstance(d, dict) else {})
            recent_billing_events.append({
                "ts": al.created_at.isoformat() if al.created_at else None,
                "time_label": (al.created_at.strftime("%H:%M") if al.created_at else "?"),
                "message": msg,
                "action": al.action,
            })

        recent_activity = []
        for al in recent_logs:
            msg = al.action
            d = al.details or {}
            if al.action.startswith("admin."):
                msg = _format_audit_message(al.action, d if isinstance(d, dict) else {})
            elif al.action.startswith("billing."):
                msg = _format_audit_message(al.action, d if isinstance(d, dict) else {})
            elif al.action == "user.register":
                msg = f"New user registered: {d.get('email', '')}"
            elif al.action == "auth.login":
                msg = f"User login: {d.get('email', d.get('username', ''))}"
            else:
                msg = f"{al.action}: {d}" if d else al.action
            recent_activity.append({
                "ts": al.created_at.isoformat() if al.created_at else None,
                "time_label": (al.created_at.strftime("%H:%M") if al.created_at else "?"),
                "message": msg,
                "action": al.action,
            })

        recent_users = (
            sess.execute(select(User).order_by(desc(User.created_at)).limit(5)).scalars().all()
        )
        recent_registrations = [
            {
                "email": u.email,
                "username": u.username,
                "tier": u.tier,
                "is_admin": u.is_admin,
                "created_at": u.created_at.isoformat() if u.created_at else None,
            }
            for u in recent_users
        ]

        dash_svc = _dashboard_systemd_active()
        agents_svc = _agents_systemd_active()
        db_ok = _database_ok(sess)
        last_act = _last_trade_activity_minutes(sess)

        return jsonify({
            "total_users": total_users,
            "active_today": active_today,
            "new_this_week": new_this_week,
            "total_trades": total_trades,
            "total_paper_accounts": total_paper_accounts,
            "total_real_accounts": total_real_accounts,
            "active_users_today": active_today,
            "trades_today": trades_today,
            "new_signups_week": new_this_week,
            "revenue_usd": 0,
            "billing_revenue_placeholder_usd": 0,
            "users_by_tier": users_by_tier,
            "recent_billing_events": recent_billing_events,
            "registration_open": registration_open,
            "signups_by_day": signups_by_day,
            "trades_by_day": trades_by_day,
            "recent_activity": recent_activity,
            "recent_registrations": recent_registrations,
            "health": {
                "dashboard_running": True
                if dash_svc
                else (False if dash_svc is False else None),
                "agents_running": True
                if agents_svc
                else (False if agents_svc is False else None),
                "database": "connected" if db_ok else "error",
                "last_agent_activity_minutes_ago": last_act,
            },
        })

    @app.route("/api/admin/users")
    @admin_required
    def api_admin_users():
        if db.SessionLocal is None:
            return jsonify({"error": "database unavailable"}), 503
        page = max(1, request.args.get("page", 1, type=int) or 1)
        per_page = min(max(1, request.args.get("per_page", 20, type=int) or 20), 100)
        search = (request.args.get("search") or "").strip()
        tier_filter = (request.args.get("tier") or "").strip().lower()
        sort = (request.args.get("sort") or "created_at").lower()
        order = (request.args.get("order") or "desc").lower()
        sess = db.db_session()

        tc_sub = (
            select(
                Account.user_id.label("uid"),
                func.count(Trade.id).label("tc"),
            )
            .select_from(Account)
            .outerjoin(Trade, Trade.account_id == Account.id)
            .group_by(Account.user_id)
            .subquery()
        )
        bal_sub = (
            select(
                Account.user_id.label("uid"),
                func.sum(
                    case(
                        (Account.account_type == "paper", func.coalesce(Account.paper_balance, 0)),
                        else_=func.coalesce(Account.real_balance, 0),
                    )
                ).label("balance"),
            )
            .group_by(Account.user_id)
            .subquery()
        )

        stmt = (
            select(User, func.coalesce(tc_sub.c.tc, 0).label("tc"), func.coalesce(bal_sub.c.balance, 0).label("bal"))
            .select_from(User)
            .outerjoin(tc_sub, tc_sub.c.uid == User.id)
            .outerjoin(bal_sub, bal_sub.c.uid == User.id)
        )
        cq = select(func.count()).select_from(User)
        if search:
            like = f"%{search}%"
            flt = or_(User.email.ilike(like), User.username.ilike(like))
            stmt = stmt.where(flt)
            cq = cq.where(flt)
        if tier_filter:
            stmt = stmt.where(User.tier == tier_filter)
            cq = cq.where(User.tier == tier_filter)
        total = int(sess.scalar(cq) or 0)
        pages = max(1, (total + per_page - 1) // per_page)

        order_columns = {
            "email": User.email,
            "username": User.username,
            "tier": User.tier,
            "created_at": User.created_at,
            "last_login": User.last_login,
            "is_active": User.is_active,
            "status": User.is_active,
            "trades_count": func.coalesce(tc_sub.c.tc, 0),
            "balance": func.coalesce(bal_sub.c.balance, 0),
        }
        ocol = order_columns.get(sort, User.created_at)
        stmt = stmt.order_by(desc(ocol) if order == "desc" else asc(ocol))
        stmt = stmt.offset((page - 1) * per_page).limit(per_page)
        rows = sess.execute(stmt).all()
        uids = [r[0].id for r in rows]
        acct_by_uid: dict[int, list[Account]] = {}
        if uids:
            for a in sess.execute(select(Account).where(Account.user_id.in_(uids))).scalars().all():
                acct_by_uid.setdefault(a.user_id, []).append(a)

        out_users = []
        for u, ntr, bal in rows:
            accts = acct_by_uid.get(u.id, [])
            types = sorted({a.account_type for a in accts})
            acct_type_label = (
                "both" if "paper" in types and "real" in types else (types[0] if types else "—")
            )
            out_users.append({
                "id": u.id,
                "email": u.email,
                "username": u.username,
                "tier": u.tier,
                "tier_normalized": normalize_tier(u.tier),
                "effective_tier": effective_tier(u),
                "is_active": u.is_active,
                "is_admin": u.is_admin,
                "created_at": u.created_at.isoformat() if u.created_at else None,
                "last_login": u.last_login.isoformat() if u.last_login else None,
                "trades_count": int(ntr or 0),
                "balance": float(bal or 0),
                "account_type": acct_type_label,
            })
        return jsonify({
            "users": out_users,
            "total": total,
            "page": page,
            "pages": pages,
            "per_page": per_page,
        })

    @app.route("/api/admin/user/create", methods=["POST"])
    @admin_required
    def api_admin_user_create():
        if db.SessionLocal is None:
            return jsonify({"error": "database unavailable"}), 503
        data = request.get_json(silent=True) or {}
        email = str(data.get("email") or "").strip()
        username = str(data.get("username") or "").strip()
        tier = str(data.get("tier") or "").strip().lower()
        auto_pw = bool(data.get("auto_generate_password"))
        password = None if auto_pw else str(data.get("password") or "").strip()
        if tier not in _VALID_ADMIN_USER_CREATE_TIERS:
            return jsonify({"error": "Invalid tier. Use: basic, medium, pro, admin."}), 400
        if not email or not username:
            return jsonify({"error": "Email and username are required."}), 400
        if not auto_pw and not password:
            return jsonify({"error": "Password is required unless auto-generate is enabled."}), 400
        sess = db.db_session()
        try:
            user, plain = saas_helpers.admin_create_user(
                sess,
                email=email,
                username=username,
                password=password,
                tier_choice=tier,
                config_dir=config_dir,
                ip=request.remote_addr or "?",
            )
        except ValueError as exc:
            sess.rollback()
            return jsonify({"error": str(exc)}), 400
        _admin_audit(
            sess,
            resolve_identity,
            g,
            "admin.create_user",
            {
                "target_user_id": user.id,
                "email": user.email,
                "username": user.username,
                "tier_label": tier,
            },
        )
        sess.commit()
        payload: dict[str, Any] = {
            "success": True,
            "user_id": user.id,
            "message": "User created",
        }
        if auto_pw:
            payload["generated_password"] = plain
        return jsonify(payload)

    @app.route("/api/admin/user/<int:uid>", methods=["GET", "DELETE"])
    @admin_required
    def api_admin_user_detail_or_delete(uid):
        if request.method == "DELETE":
            if db.SessionLocal is None:
                return jsonify({"error": "database unavailable"}), 503
            actor = _admin_session_user_id(resolve_identity, g)
            if actor is not None and actor == uid:
                return jsonify({"error": "You cannot delete your own account."}), 400
            sess = db.db_session()
            u = sess.get(User, uid)
            if not u:
                return jsonify({"error": "not found"}), 404
            _admin_audit(
                sess,
                resolve_identity,
                g,
                "admin.delete_user",
                {"target_user_id": uid, "email": u.email},
            )
            sess.delete(u)
            sess.commit()
            return jsonify({"success": True, "deleted_id": uid})

        if db.SessionLocal is None:
            return jsonify({"error": "database unavailable"}), 503
        sess = db.db_session()
        u = sess.get(User, uid)
        if not u:
            return jsonify({"error": "not found"}), 404
        accounts = sess.execute(select(Account).where(Account.user_id == uid)).scalars().all()
        acct_out: list[dict[str, Any]] = []
        for a in accounts:
            n_trades = int(sess.scalar(select(func.count()).select_from(Trade).where(Trade.account_id == a.id)) or 0)
            perf = saas_helpers.trade_performance_payload(sess, a.id)
            tc_row = sess.execute(
                select(TradingConfiguration).where(TradingConfiguration.account_id == a.id)
            ).scalar_one_or_none()
            acct_out.append({
                "id": a.id,
                "account_type": a.account_type,
                "account_status": a.account_status,
                "trade_count": n_trades,
                "paper_balance": float(a.paper_balance) if a.paper_balance is not None else None,
                "real_balance": float(a.real_balance) if a.real_balance is not None else None,
                "max_single_trade_pct": float(a.max_single_trade_pct) if a.max_single_trade_pct is not None else None,
                "max_daily_loss_pct": float(a.max_daily_loss_pct) if a.max_daily_loss_pct is not None else None,
                "max_drawdown_pct": float(a.max_drawdown_pct) if a.max_drawdown_pct is not None else None,
                "performance": perf.get("summary"),
                "trading_configuration": (
                    {
                        "llm_enabled": tc_row.llm_enabled,
                        "trading_mode": tc_row.trading_mode,
                        "agents": tc_row.agents,
                    }
                    if tc_row
                    else None
                ),
            })
        recent_trades: list[dict[str, Any]] = []
        for a in accounts:
            for row in saas_helpers.trade_performance_payload(sess, a.id).get("recent") or []:
                row = dict(row)
                row["account_type"] = a.account_type
                recent_trades.append(row)
        recent_trades.sort(key=lambda r: (r.get("exit_ts") or r.get("entry_ts") or ""), reverse=True)
        recent_trades = recent_trades[:20]

        audits = (
            sess.execute(
                select(AuditLog)
                .where(AuditLog.user_id == uid)
                .order_by(desc(AuditLog.created_at))
                .limit(20)
            )
            .scalars()
            .all()
        )
        audit_out = [
            {
                "id": al.id,
                "action": al.action,
                "details": al.details,
                "ip_address": al.ip_address,
                "created_at": al.created_at.isoformat() if al.created_at else None,
            }
            for al in audits
        ]

        return jsonify({
            "user": {
                "id": u.id,
                "email": u.email,
                "username": u.username,
                "tier": u.tier,
                "is_active": u.is_active,
                "is_admin": u.is_admin,
                "created_at": u.created_at.isoformat() if u.created_at else None,
                "last_login": u.last_login.isoformat() if u.last_login else None,
                "totp_enabled": bool(u.totp_enabled),
            },
            "accounts": acct_out,
            "recent_trades": recent_trades,
            "audit_log": audit_out,
        })

    @app.route("/api/admin/user/<int:uid>/suspend", methods=["POST"])
    @admin_required
    def api_admin_user_suspend(uid):
        if db.SessionLocal is None:
            return jsonify({"error": "database unavailable"}), 503
        data = request.get_json(silent=True) or {}
        suspend = bool(data.get("suspend", True))
        sess = db.db_session()
        u = sess.get(User, uid)
        if not u:
            return jsonify({"error": "not found"}), 404
        u.is_active = not suspend
        _admin_audit(
            sess,
            resolve_identity,
            g,
            "admin.user_suspend",
            {"target_user_id": uid, "suspend": suspend, "email": u.email},
        )
        sess.commit()
        return jsonify({"success": True, "user_id": uid, "is_active": u.is_active})

    @app.route("/api/admin/user/<int:uid>/unsuspend", methods=["POST"])
    @admin_required
    def api_admin_user_unsuspend(uid):
        if db.SessionLocal is None:
            return jsonify({"error": "database unavailable"}), 503
        sess = db.db_session()
        u = sess.get(User, uid)
        if not u:
            return jsonify({"error": "not found"}), 404
        u.is_active = True
        _admin_audit(
            sess,
            resolve_identity,
            g,
            "admin.user_unsuspend",
            {"target_user_id": uid, "email": u.email},
        )
        sess.commit()
        return jsonify({"success": True, "user_id": uid, "is_active": u.is_active})

    @app.route("/api/admin/user/<int:uid>/change-tier", methods=["POST"])
    @admin_required
    def api_admin_user_change_tier(uid):
        if db.SessionLocal is None:
            return jsonify({"error": "database unavailable"}), 503
        data = request.get_json(silent=True) or {}
        tier = str(data.get("tier") or "").strip().lower()
        if tier not in _VALID_ADMIN_TIERS:
            return jsonify({"error": "Invalid tier. Use: basic, medium, pro"}), 400
        sess = db.db_session()
        u = sess.get(User, uid)
        if not u:
            return jsonify({"error": "not found"}), 404
        old = u.tier
        u.tier = tier
        _admin_audit(
            sess,
            resolve_identity,
            g,
            "admin.change_tier",
            {"target_user_id": uid, "email": u.email, "from": old, "to": tier},
        )
        sess.commit()
        return jsonify({"success": True, "user_id": uid, "tier": u.tier})

    @app.route("/api/admin/user/<int:uid>/reset-password", methods=["POST"])
    @admin_required
    def api_admin_user_reset_password(uid):
        if db.SessionLocal is None:
            return jsonify({"error": "database unavailable"}), 503
        data = request.get_json(silent=True) or {}
        pw = data.get("password") or ""
        ok, msg = saas_helpers.validate_password_strength(str(pw))
        if not ok:
            return jsonify({"error": msg}), 400
        sess = db.db_session()
        u = sess.get(User, uid)
        if not u:
            return jsonify({"error": "not found"}), 404
        u.password_hash = saas_helpers.hash_password(str(pw))
        _admin_audit(
            sess,
            resolve_identity,
            g,
            "admin.reset_password",
            {"target_user_id": uid, "email": u.email},
        )
        sess.commit()
        return jsonify({"success": True, "user_id": uid})

    @app.route("/api/admin/settings", methods=["GET"])
    @admin_required
    def api_admin_settings_get():
        if db.SessionLocal is None:
            return jsonify({"error": "database unavailable"}), 503
        sess = db.db_session()
        settings = saas_helpers.get_platform_settings_dict(sess)
        nbytes = None
        try:
            nbytes = sess.scalar(text("SELECT pg_database_size(current_database())"))
        except Exception:
            nbytes = None
        last_perf = None
        try:
            if _PERF_PATH.exists():
                last_perf = datetime.fromtimestamp(_PERF_PATH.stat().st_mtime, tz=timezone.utc).isoformat()
        except OSError:
            last_perf = None
        cfgs = _load_configs()
        agents_svc = _agents_systemd_active()
        system = {
            "uptime_human": _uptime_str(),
            "process_started_at": datetime.fromtimestamp(_state.get("started_at", 0), tz=timezone.utc).isoformat()
            if _state.get("started_at")
            else None,
            "database_size_bytes": int(nbytes) if nbytes is not None else None,
            "agents_configured": len(cfgs),
            "agents_service_active": agents_svc,
            "dry_run": DRY_RUN,
            "alpaca_paper": ALPACA_PAPER,
            "last_performance_file_at": last_perf,
        }
        return jsonify({
            "settings": settings,
            "system": system,
            "google_oauth": {
                "configured": google_oauth_configured,
                "status": "Active" if google_oauth_configured else "Not configured",
                "instructions": (
                    "To enable Google login, set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in .env"
                ),
            },
        })

    @app.route("/api/admin/settings", methods=["PUT"])
    @admin_required
    def api_admin_settings_put():
        if db.SessionLocal is None:
            return jsonify({"error": "database unavailable"}), 503
        data = request.get_json(silent=True) or {}
        sess = db.db_session()
        patch = {k: data[k] for k in ("trading_defaults", "registration", "agents_available") if k in data}
        merged = saas_helpers.upsert_platform_settings(sess, patch)
        _admin_audit(sess, resolve_identity, g, "admin.settings_update", {"keys": list(patch.keys())})
        sess.commit()
        return jsonify({"success": True, "settings": merged})

    @app.route("/api/admin/activity")
    @admin_required
    def api_admin_activity():
        if db.SessionLocal is None:
            return jsonify({"error": "database unavailable"}), 503
        limit = min(max(1, request.args.get("limit", 50, type=int) or 50), 200)
        sess = db.db_session()
        logs = (
            sess.execute(select(AuditLog).order_by(desc(AuditLog.created_at)).limit(limit * 2))
            .scalars()
            .all()
        )
        rows: list[dict[str, Any]] = []
        for al in logs:
            d = al.details or {}
            msg = al.action
            if al.action.startswith("admin."):
                msg = _format_audit_message(al.action, d if isinstance(d, dict) else {})
            elif al.action.startswith("billing."):
                msg = _format_audit_message(al.action, d if isinstance(d, dict) else {})
            elif al.action == "user.register":
                msg = f"New user registered: {d.get('email', '')}"
            elif al.action == "auth.login":
                msg = f"User login: {d.get('email', d.get('username', ''))}"
            else:
                msg = f"{al.action}: {d}" if d else al.action
            rows.append({
                "ts": al.created_at.isoformat() if al.created_at else None,
                "time_label": (al.created_at.strftime("%H:%M") if al.created_at else "?"),
                "message": msg,
                "action": al.action,
            })

        stmt = (
            select(Trade, Account, User)
            .join(Account, Trade.account_id == Account.id)
            .join(User, Account.user_id == User.id)
            .order_by(desc(Trade.entry_time))
            .limit(30)
        )
        for t, ac, usr in sess.execute(stmt).all():
            ts = t.entry_time or t.exit_time
            price = t.entry_price
            qty = t.entry_qty
            rows.append({
                "ts": ts.isoformat() if ts else None,
                "time_label": ts.strftime("%H:%M") if ts else "?",
                "message": (
                    f"Trade: {t.symbol} {t.trade_type} {float(qty) if qty is not None else '?'} "
                    f"@ ${float(price) if price is not None else '?'} (user: {usr.username})"
                ),
                "action": "trade.record",
            })

        rows.sort(key=lambda r: r.get("ts") or "", reverse=True)
        rows = rows[:limit]
        return jsonify({"items": rows})

    @app.route("/api/admin/announcement", methods=["POST"])
    @admin_required
    def api_admin_announcement_create():
        if db.SessionLocal is None:
            return jsonify({"error": "database unavailable"}), 503
        data = request.get_json(silent=True) or {}
        title = (data.get("title") or "").strip()
        message = (data.get("message") or "").strip()
        if not title or not message:
            return jsonify({"error": "title and message required"}), 400
        sess = db.db_session()
        ann = Announcement(title=title[:256], message=message, active=True)
        sess.add(ann)
        sess.flush()
        _admin_audit(
            sess,
            resolve_identity,
            g,
            "admin.announcement_create",
            {"announcement_id": ann.id, "title": title},
        )
        sess.commit()
        return jsonify({
            "success": True,
            "id": ann.id,
            "title": ann.title,
            "message": ann.message,
            "created_at": ann.created_at.isoformat() if ann.created_at else None,
        })

    @app.route("/api/announcements")
    @login_required
    def api_announcements_public():
        """Active announcements for current DB user (cookie session)."""
        if db.SessionLocal is None:
            return jsonify([])
        resolve_identity()
        u = getattr(g, "db_user", None)
        if not u:
            return jsonify([])
        sess = db.db_session()
        dismissed = sess.execute(
            select(AnnouncementDismissal.announcement_id).where(AnnouncementDismissal.user_id == u.id)
        ).scalars().all()
        q = select(Announcement).where(Announcement.active == True)  # noqa: E712
        if dismissed:
            q = q.where(~Announcement.id.in_(dismissed))
        anns = sess.execute(q.order_by(desc(Announcement.created_at))).scalars().all()
        out = [
            {
                "id": a.id,
                "title": a.title,
                "message": a.message,
                "created_at": a.created_at.isoformat() if a.created_at else None,
            }
            for a in anns
        ]
        return jsonify(out)

    @app.route("/api/announcement/<int:aid>/dismiss", methods=["POST"])
    @login_required
    def api_announcement_dismiss(aid):
        if db.SessionLocal is None:
            return jsonify({"error": "database unavailable"}), 503
        resolve_identity()
        u = getattr(g, "db_user", None)
        if not u:
            return jsonify({"error": "unauthorized"}), 401
        sess = db.db_session()
        ann = sess.get(Announcement, aid)
        if not ann or not ann.active:
            return jsonify({"error": "not found"}), 404
        exists = sess.execute(
            select(AnnouncementDismissal).where(
                AnnouncementDismissal.user_id == u.id,
                AnnouncementDismissal.announcement_id == aid,
            )
        ).scalar_one_or_none()
        if not exists:
            sess.add(
                AnnouncementDismissal(
                    user_id=u.id,
                    announcement_id=aid,
                )
            )
        sess.commit()
        return jsonify({"success": True})

    @app.route("/api/admin/assign-demo-agents", methods=["POST"])
    @admin_required
    def api_admin_assign_demo_agents():
        """Assign preset paper marketplace agents to users who have no active subscriptions."""
        if db.SessionLocal is None:
            return jsonify({"error": "database unavailable"}), 503
        eng = db.get_engine()
        if eng is None:
            return jsonify({"error": "database unavailable"}), 503

        dialect = eng.dialect.name
        if dialect == "sqlite":
            not_admin = "(u.is_admin = 0 OR u.is_admin IS NULL)"
            active_sub = "(us.is_active = 1 OR us.is_active = true)"
        else:
            not_admin = "COALESCE(u.is_admin, false) = false"
            active_sub = "us.is_active IS TRUE"

        with eng.connect() as c0:
            users_without_agents = c0.execute(
                text(f"""
                SELECT u.id FROM users u
                WHERE {not_admin}
                AND NOT EXISTS (
                    SELECT 1 FROM user_subscriptions us
                    WHERE us.user_id = u.id AND {active_sub}
                )
                """),
            ).fetchall()

        total_assigned = 0
        for row in users_without_agents:
            uid = int(row[0])
            with eng.begin() as conn:
                assigned = assign_demo_agents(uid, conn)
                total_assigned += len(assigned)

        sess = db.db_session()
        try:
            _admin_audit(
                sess,
                resolve_identity,
                g,
                "admin.assign_demo_agents",
                {"users": len(users_without_agents), "assignments": total_assigned},
            )
            sess.commit()
        finally:
            sess.close()

        return jsonify({
            "ok": True,
            "users_processed": len(users_without_agents),
            "agents_assigned": total_assigned,
        })
