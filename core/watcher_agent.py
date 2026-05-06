#!/usr/bin/env python3
"""Hermes watcher: health checks, disk, SSL, optional auto-restart (systemd)."""

from __future__ import annotations

import os
import secrets
import socket
import ssl
import subprocess
import sys
import time
import html
from datetime import datetime, time as dtime, timezone
from email.message import EmailMessage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import requests
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

_BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BASE))
load_dotenv(_BASE / ".env")

from core.leaderboard import compute_leaderboard_cache
from core.telegram_bot import get_updates, process_update, send_alert

APP_URL = (os.getenv("DASHBOARD_PUBLIC_BASE_URL") or "http://127.0.0.1:5000").strip().rstrip("/")
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = (os.getenv("SMTP_USER") or "").strip()
SMTP_PASSWORD = (os.getenv("SMTP_PASSWORD") or "").strip()
ADMIN_EMAIL = (os.getenv("ADMIN_EMAIL") or SMTP_USER or "").strip()
WATCHER_SERVICE_NAME = os.getenv("HERMES_WATCHER_SERVICE", "hermes-dashboard")
_CYCLE_SEC = int(os.getenv("WATCHER_CYCLE_SEC", "300"))
_CANDLE_REFRESH_MARK = _BASE / ".watcher_historical_candles_date"


def _maybe_refresh_historical_candles() -> None:
    """At most once per UTC day: warm historical_candles (7d 1h) for major symbols."""
    today = datetime.now(timezone.utc).date().isoformat()
    try:
        last = _CANDLE_REFRESH_MARK.read_text().strip() if _CANDLE_REFRESH_MARK.exists() else ""
    except OSError:
        last = ""
    if last == today:
        return
    try:
        from core.backtester import refresh_historical_candles

        refresh_historical_candles()
        try:
            _CANDLE_REFRESH_MARK.write_text(today)
        except OSError:
            pass
        log_event("historical_candles", "info", "Daily Binance candle cache refresh completed")
    except Exception as exc:  # noqa: BLE001
        log_event("historical_candles", "warning", f"Candle cache refresh failed: {exc}")


def _engine():
    url = (os.getenv("DATABASE_URL") or "").strip()
    if not url:
        return None
    return create_engine(url, pool_pre_ping=True, future=True)


def log_event(event_type: str, severity: str, message: str, details: str | None = None) -> None:
    eng = _engine()
    line = f"[{severity.upper()}] {event_type}: {message}"
    print(line)
    if eng is None:
        return
    try:
        with eng.begin() as c:
            c.execute(
                text("""
                INSERT INTO system_events (event_type, severity, message, details)
                VALUES (:event_type, :severity, :message, :details)
                """),
                {
                    "event_type": event_type,
                    "severity": severity,
                    "message": message,
                    "details": details,
                },
            )
    except Exception as exc:  # noqa: BLE001
        print(f"log_event DB failed: {exc}")


def send_admin_alert(subject: str, body: str) -> None:
    if not SMTP_USER or not SMTP_PASSWORD or not ADMIN_EMAIL:
        print(f"ALERT (no email configured): {subject}\n{body}")
        return
    try:
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = SMTP_USER
        msg["To"] = ADMIN_EMAIL
        msg.set_content(body)
        import smtplib

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as smtp:
            smtp.starttls()
            smtp.login(SMTP_USER, SMTP_PASSWORD)
            smtp.send_message(msg)
        print(f"Alert sent: {subject}")
    except Exception as exc:  # noqa: BLE001
        print(f"Failed to send alert: {exc}")


def build_weekly_email_html(
    user_email: str,
    agents_data: list,
    total_pnl: float,
    total_pnl_pct: float,
    unsubscribe_url: str,
) -> str:
    """Build HTML body for weekly performance email (inline CSS).

    agents_data entries: name, symbol, weekly_pnl_usd, weekly_pnl_pct, win_rate (0–100), trade_count.
    """
    _ = user_email
    pnl_color = "#34d399" if total_pnl >= 0 else "#f87171"
    sign_usd = "+" if total_pnl >= 0 else ""
    sign_pct = "+" if total_pnl_pct >= 0 else ""
    total_usd_fmt = f"{sign_usd}{total_pnl:,.2f} USD"
    total_pct_fmt = f"{sign_pct}{total_pnl_pct:.2f}%"
    app_url = (
        (os.getenv("HERMES_APP_URL") or os.getenv("DASHBOARD_PUBLIC_BASE_URL") or APP_URL).strip().rstrip("/")
    )

    row_template = """
<tr style="border-bottom:1px solid rgba(255,255,255,.04)">
  <td style="padding:10px 0">
    <div style="font-size:13px;color:#e2e8f0;font-weight:500">{name}</div>
    <div style="font-size:11px;color:#475569">{symbol}</div>
  </td>
  <td style="padding:10px 0;text-align:right;font-size:13px;font-weight:600;color:{pnl_color}">{weekly_pnl}</td>
  <td style="padding:10px 0;text-align:right;font-size:12px;color:#64748b">{win_rate}</td>
</tr>
"""
    rows_parts: list[str] = []
    for a in agents_data:
        wpu = float(a.get("weekly_pnl_usd") or 0)
        wr = float(a.get("win_rate") or 0)
        pcol = "#34d399" if wpu >= 0 else "#f87171"
        ws = "+" if wpu >= 0 else ""
        wpf = f"{ws}{wpu:,.2f} USD"
        rows_parts.append(
            row_template.format(
                name=html.escape(str(a.get("name") or "")),
                symbol=html.escape(str(a.get("symbol") or "")),
                pnl_color=pcol,
                weekly_pnl=wpf,
                win_rate=f"{wr:.1f}%",
            )
        )
    agents_rows = "".join(rows_parts)

    template = """<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#0f172a;font-family:Arial,sans-serif">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#0f172a;padding:20px 0">
    <tr><td align="center">
      <table width="600" cellpadding="0" cellspacing="0"
             style="max-width:600px;width:100%;background:#1e293b;border-radius:16px;overflow:hidden">

        <tr><td style="background:linear-gradient(135deg,#6366f1,#8b5cf6);padding:24px 32px">
          <div style="font-size:22px;font-weight:700;color:#fff;letter-spacing:2px">HERMES</div>
          <div style="font-size:13px;color:rgba(255,255,255,.7);margin-top:4px">Týždenný report výkonnosti</div>
        </td></tr>

        <tr><td style="padding:28px 32px;text-align:center;border-bottom:1px solid rgba(255,255,255,.06)">
          <div style="font-size:12px;color:#64748b;text-transform:uppercase;letter-spacing:.1em;margin-bottom:8px">
            Celkový P&L tento týždeň
          </div>
          <div style="font-size:42px;font-weight:700;color:{PNL_COLOR}">{TOTAL_PNL_USD}</div>
          <div style="font-size:18px;color:{PNL_COLOR};margin-top:4px">{TOTAL_PNL_PCT}</div>
        </td></tr>

        <tr><td style="padding:24px 32px">
          <div style="font-size:12px;color:#64748b;text-transform:uppercase;letter-spacing:.1em;margin-bottom:16px">
            Výkonnosť agentov
          </div>
          <table width="100%" cellpadding="0" cellspacing="0">
            <tr style="border-bottom:1px solid rgba(255,255,255,.06)">
              <td style="font-size:11px;color:#475569;padding:0 0 8px">AGENT</td>
              <td style="font-size:11px;color:#475569;padding:0 0 8px;text-align:right">TÝŽD. P&L</td>
              <td style="font-size:11px;color:#475569;padding:0 0 8px;text-align:right">WIN RATE</td>
            </tr>
            {AGENTS_ROWS}
          </table>
        </td></tr>

        <tr><td style="padding:8px 32px 28px;text-align:center">
          <a href="{APP_URL}"
             style="display:inline-block;padding:14px 32px;background:linear-gradient(135deg,#6366f1,#8b5cf6);
                    color:#fff;text-decoration:none;border-radius:10px;font-size:15px;font-weight:600">
            Otvoriť dashboard →
          </a>
        </td></tr>

        <tr><td style="padding:16px 32px;border-top:1px solid rgba(255,255,255,.06);text-align:center">
          <div style="font-size:11px;color:#334155">
            Hermes Trading Platform ·
            <a href="{UNSUBSCRIBE_URL}" style="color:#475569">Vypnúť týždenné reporty</a>
          </div>
        </td></tr>

      </table>
    </td></tr>
  </table>
</body>
</html>"""
    return template.format(
        PNL_COLOR=pnl_color,
        TOTAL_PNL_USD=total_usd_fmt,
        TOTAL_PNL_PCT=total_pct_fmt,
        AGENTS_ROWS=agents_rows,
        APP_URL=app_url,
        UNSUBSCRIBE_URL=unsubscribe_url,
    )


def _send_html_email(to_email: str, subject: str, html_body: str) -> None:
    """Send HTML email via configured SMTP."""
    to = (to_email or "").strip()
    if not SMTP_USER or not SMTP_PASSWORD or not to:
        print(f"USER EMAIL (no SMTP): {subject} → {to}")
        return
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = SMTP_USER
        msg["To"] = to
        msg.attach(MIMEText(html_body, "html", "utf-8"))
        import smtplib

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as smtp:
            smtp.starttls()
            smtp.login(SMTP_USER, SMTP_PASSWORD)
            smtp.send_message(msg)
        print(f"Weekly report sent: {to}")
    except Exception as exc:  # noqa: BLE001
        print(f"Failed to send weekly report to {to}: {exc}")


def send_weekly_reports() -> None:
    """Send weekly reports to users with weekly_report_enabled."""
    eng = _engine()
    if eng is None:
        return

    base_url = (
        os.getenv("HERMES_APP_URL") or os.getenv("DASHBOARD_PUBLIC_BASE_URL") or "https://app.letagentscook.lol"
    ).strip().rstrip("/")

    try:
        with eng.connect() as conn:
            users = conn.execute(
                text("""
                SELECT id, email, unsubscribe_token, telegram_chat_id
                FROM users
                WHERE weekly_report_enabled IS TRUE
                  AND email IS NOT NULL
                  AND (weekly_report_sent_at IS NULL
                       OR weekly_report_sent_at < NOW() - INTERVAL '6 days')
                """),
            ).mappings().all()
    except Exception as exc:  # noqa: BLE001
        log_event("weekly_report", "warning", f"Weekly report user query failed: {exc}")
        return

    baseline = 10000.0
    for user in users:
        uid = int(user["id"])
        email = (user["email"] or "").strip()
        if not email:
            continue
        try:
            with eng.begin() as c:
                tok_row = c.execute(
                    text("SELECT unsubscribe_token FROM users WHERE id = :id"),
                    {"id": uid},
                ).mappings().first()
                token = ((tok_row or {}).get("unsubscribe_token") or "").strip()
                if not token:
                    token = secrets.token_hex(32)
                    c.execute(
                        text("UPDATE users SET unsubscribe_token = :t WHERE id = :id"),
                        {"t": token, "id": uid},
                    )
                agents = c.execute(
                    text("""
                    SELECT
                        ta.name AS name,
                        ta.symbol AS symbol,
                        COALESCE(SUM(pt.pnl), 0) AS weekly_pnl_usd,
                        COUNT(pt.id) AS trade_count,
                        COALESCE(
                            CASE WHEN COUNT(pt.id) > 0 THEN
                                SUM(CASE WHEN pt.pnl > 0 THEN 1 ELSE 0 END)::double precision
                                / NULLIF(COUNT(pt.id), 0)::double precision * 100
                            END,
                            ta.win_rate
                        ) AS win_rate_pct
                    FROM user_subscriptions us
                    JOIN trading_agents ta ON ta.id = us.agent_id
                    LEFT JOIN paper_trades pt
                        ON pt.user_id = us.user_id
                        AND pt.agent_id = us.agent_id
                        AND pt.timestamp >= NOW() - INTERVAL '7 days'
                    WHERE us.user_id = :uid AND us.is_active IS TRUE
                    GROUP BY ta.id, ta.name, ta.symbol, ta.win_rate
                    ORDER BY weekly_pnl_usd DESC
                    """),
                    {"uid": uid},
                ).mappings().all()
        except Exception as exc:  # noqa: BLE001
            log_event("weekly_report", "warning", f"Weekly report prep failed for user {uid}: {exc}")
            continue

        if not agents:
            continue

        agents_data = []
        for a in agents[:5]:
            wpu = float(a["weekly_pnl_usd"] or 0)
            wr = float(a["win_rate_pct"] or 0)
            tc = int(a["trade_count"] or 0)
            agents_data.append(
                {
                    "name": a["name"],
                    "symbol": a["symbol"],
                    "weekly_pnl_usd": wpu,
                    "weekly_pnl_pct": (wpu / baseline * 100.0) if baseline else 0.0,
                    "win_rate": wr,
                    "trade_count": tc,
                }
            )

        total_pnl = sum(float(a["weekly_pnl_usd"] or 0) for a in agents)
        pcts = [(float(a["weekly_pnl_usd"] or 0) / baseline * 100.0) for a in agents]
        total_pnl_pct = sum(pcts) / len(pcts) if pcts else 0.0

        unsubscribe_url = f"{base_url}/unsubscribe/{token}"
        html_body = build_weekly_email_html(email, agents_data, total_pnl, total_pnl_pct, unsubscribe_url)

        sign = "+" if total_pnl >= 0 else ""
        subject = f"[Hermes] Týždenný report: {sign}{total_pnl:.2f} USD"

        _send_html_email(email, subject, html_body)
        log_event("weekly_report", "info", f"Weekly report emailed user {uid}")
        tg_chat = user.get("telegram_chat_id")
        if tg_chat is not None:
            try:
                best_name = agents_data[0]["name"] if agents_data else "—"
                tg_msg = (
                    f"Tvoji agenti tento týždeň: {sign}{total_pnl:.2f} USD\n"
                    f"Najlepší: {best_name}"
                )
                send_alert(int(tg_chat), "Týždenný report", tg_msg, "weekly_summary")
            except Exception as texc:  # noqa: BLE001
                log_event("weekly_report", "warning", f"Weekly Telegram failed for user {uid}: {texc}")
        try:
            with eng.begin() as c:
                c.execute(
                    text("UPDATE users SET weekly_report_sent_at = NOW() WHERE id = :uid"),
                    {"uid": uid},
                )
        except Exception as exc:  # noqa: BLE001
            log_event("weekly_report", "warning", f"Weekly report sent_at update failed for {uid}: {exc}")


def send_user_alert(to_email: str, subject: str, body: str) -> None:
    to = (to_email or "").strip()
    if not SMTP_USER or not SMTP_PASSWORD or not to:
        print(f"USER ALERT (no SMTP or recipient): {subject}\n{body}")
        return
    try:
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = SMTP_USER
        msg["To"] = to
        msg.set_content(body)
        import smtplib

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as smtp:
            smtp.starttls()
            smtp.login(SMTP_USER, SMTP_PASSWORD)
            smtp.send_message(msg)
        print(f"User alert sent to {to}: {subject}")
    except Exception as exc:  # noqa: BLE001
        print(f"Failed to send user alert: {exc}")


def check_web_health() -> bool:
    try:
        r = requests.get(f"{APP_URL}/api/auth/status", timeout=10)
        if r.status_code == 200:
            log_event("health_check", "info", "Web app healthy")
            return True
        msg = f"Web app returned {r.status_code}"
        log_event("health_check", "warning", msg)
        send_admin_alert(f"[HERMES] Warning: {msg}", f"URL: {APP_URL}\nStatus: {r.status_code}")
        return False
    except Exception as e:  # noqa: BLE001
        msg = f"Web app unreachable: {e}"
        log_event("health_check", "critical", msg)
        send_admin_alert(
            "[HERMES] CRITICAL: App Down!",
            f"URL: {APP_URL}\nError: {e}\nAttempting restart...",
        )
        return False


def restart_dashboard() -> bool:
    try:
        result = subprocess.run(
            ["systemctl", "restart", WATCHER_SERVICE_NAME],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            log_event("auto_fix", "info", "Dashboard restarted successfully")
            send_admin_alert(
                "[HERMES] Auto-fix: Dashboard restarted",
                f"{WATCHER_SERVICE_NAME} was automatically restarted.",
            )
            return True
        log_event("auto_fix", "critical", f"Restart failed: {result.stderr}")
        send_admin_alert("[HERMES] CRITICAL: Restart failed!", result.stderr or result.stdout)
        return False
    except Exception as e:  # noqa: BLE001
        log_event("auto_fix", "critical", f"Restart exception: {e}")
        return False


def check_disk_space() -> None:
    try:
        result = subprocess.run(["df", "-h", "/"], capture_output=True, text=True, timeout=15)
        for line in result.stdout.split("\n")[1:]:
            parts = line.split()
            if len(parts) >= 5 and parts[4].endswith("%"):
                usage = int(parts[4].replace("%", ""))
                if usage > 85:
                    msg = f"Disk usage critical: {usage}%"
                    log_event("disk_space", "critical", msg)
                    send_admin_alert(f"[HERMES] Disk Space: {usage}%", msg)
                elif usage > 70:
                    log_event("disk_space", "warning", f"Disk usage high: {usage}%")
    except Exception as e:  # noqa: BLE001
        log_event("disk_space", "warning", f"df failed: {e}")


def check_ssl_cert() -> None:
    if not APP_URL.lower().startswith("https://"):
        return
    try:
        host = APP_URL.replace("https://", "").split("/")[0].split(":")[0]
        ctx = ssl.create_default_context()
        with ctx.wrap_socket(socket.socket(), server_hostname=host) as s:
            s.settimeout(10)
            s.connect((host, 443))
            cert = s.getpeercert()
        exp_s = cert.get("notAfter")
        if not exp_s:
            return
        exp = datetime.strptime(exp_s, "%b %d %H:%M:%S %Y %Z").replace(tzinfo=timezone.utc)
        days_left = (exp - datetime.now(timezone.utc)).days
        if days_left < 14:
            msg = f"SSL cert expires in {days_left} days"
            log_event("ssl_check", "warning", msg)
            send_admin_alert(f"[HERMES] SSL Expiry: {days_left} days", msg)
        else:
            log_event("ssl_check", "info", f"SSL cert valid ~{days_left} days")
    except Exception as e:  # noqa: BLE001
        log_event("ssl_check", "warning", f"SSL check failed: {e}")


def compute_and_store_pnl_snapshots() -> None:
    """Upsert cumulative paper P&L metrics into agent_pnl_snapshots (PostgreSQL)."""
    eng = _engine()
    if eng is None:
        return
    snap_date = datetime.now(timezone.utc).date()
    baseline = 10000.0
    try:
        with eng.begin() as conn:
            pairs = conn.execute(
                text("""
                SELECT DISTINCT user_id, agent_id FROM user_subscriptions
                WHERE is_active IS TRUE
                """),
            ).mappings().all()
            for row in pairs:
                uid = int(row["user_id"])
                aid = str(row["agent_id"])
                agg = conn.execute(
                    text("""
                    SELECT COALESCE(SUM(pnl), 0) AS total,
                           COUNT(*)::int AS ntr,
                           COALESCE(SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END), 0)::int AS nw
                    FROM paper_trades
                    WHERE user_id = :u AND agent_id = :a
                    """),
                    {"u": uid, "a": aid},
                ).mappings().first()
                total = float(agg["total"] or 0) if agg else 0.0
                ntr = int(agg["ntr"] or 0) if agg else 0
                nw = int(agg["nw"] or 0) if agg else 0
                equity = baseline + total
                pnl_pct = (total / baseline * 100.0) if baseline else 0.0
                conn.execute(
                    text("""
                    INSERT INTO agent_pnl_snapshots (
                        agent_id, user_id, snapshot_date, pnl_usd, pnl_pct, equity,
                        trade_count, win_count, is_active
                    ) VALUES (
                        :aid, :uid, :sd, :pu, :pp, :eq, :tc, :wc, TRUE
                    )
                    ON CONFLICT (agent_id, user_id, snapshot_date)
                    DO UPDATE SET
                        pnl_usd = EXCLUDED.pnl_usd,
                        pnl_pct = EXCLUDED.pnl_pct,
                        equity = EXCLUDED.equity,
                        trade_count = EXCLUDED.trade_count,
                        win_count = EXCLUDED.win_count,
                        is_active = EXCLUDED.is_active,
                        created_at = CURRENT_TIMESTAMP
                    """),
                    {
                        "aid": aid,
                        "uid": uid,
                        "sd": snap_date,
                        "pu": total,
                        "pp": pnl_pct,
                        "eq": equity,
                        "tc": ntr,
                        "wc": nw,
                    },
                )
    except Exception as exc:  # noqa: BLE001
        print(f"compute_and_store_pnl_snapshots failed: {exc}")


def check_and_fire_alerts() -> None:
    """Evaluate alert_rules and insert notifications + email subscribers."""
    eng = _engine()
    if eng is None:
        return
    base_url = (os.getenv("HERMES_APP_URL") or APP_URL or "https://app.letagentscook.lol").strip().rstrip("/")

    try:
        with eng.begin() as c:
            rules = c.execute(
                text("""
                SELECT ar.id, ar.user_id, ar.agent_id, ar.threshold,
                       u.email AS user_email, u.telegram_chat_id AS telegram_chat_id,
                       ta.name AS agent_name, ta.symbol AS symbol
                FROM alert_rules ar
                JOIN users u ON u.id = ar.user_id
                JOIN trading_agents ta ON ta.id = ar.agent_id
                WHERE ar.alert_type = 'pnl_drop'
                  AND ar.is_enabled IS TRUE
                  AND (ar.last_triggered_at IS NULL
                       OR ar.last_triggered_at < NOW() - INTERVAL '24 hours')
                """),
            ).mappings().all()

            for rule in rules:
                snap = c.execute(
                    text("""
                    SELECT pnl_pct FROM agent_pnl_snapshots
                    WHERE agent_id = :aid AND user_id = :uid
                    ORDER BY snapshot_date DESC, created_at DESC
                    LIMIT 1
                    """),
                    {"aid": rule["agent_id"], "uid": rule["user_id"]},
                ).mappings().first()
                if not snap:
                    continue
                pnl_pct = float(snap["pnl_pct"] or 0)
                thr = float(rule["threshold"] or 5)
                if pnl_pct > -abs(thr):
                    continue

                agent_name = str(rule["agent_name"] or "")
                symbol = str(rule["symbol"] or "")
                title = f"Agent {agent_name} stratil {abs(pnl_pct):.1f}%"
                message = (
                    f"Tvoj agent {agent_name} ({symbol}) zaznamenal pokles P&L o {abs(pnl_pct):.1f}%. "
                    f"Aktuálny P&L: {pnl_pct:.2f}%."
                )
                c.execute(
                    text("""
                    INSERT INTO notifications (user_id, type, title, message)
                    VALUES (:uid, 'pnl_drop', :title, :msg)
                    """),
                    {"uid": rule["user_id"], "title": title, "msg": message},
                )
                c.execute(
                    text("UPDATE alert_rules SET last_triggered_at = NOW() WHERE id = :rid"),
                    {"rid": rule["id"]},
                )
                to_email = str(rule["user_email"] or "")
                send_user_alert(
                    to_email,
                    f"[Hermes Alert] {title}",
                    f"{message}\n\nPozri sa na: {base_url}",
                )
                tgid = rule.get("telegram_chat_id")
                if tgid is not None:
                    try:
                        send_alert(int(tgid), title, message, "pnl_drop")
                    except Exception as tgx:  # noqa: BLE001
                        print(f"Telegram pnl_drop alert failed: {tgx}")
                log_event("alert_fired", "info", title)

            inactive_rules = c.execute(
                text("""
                SELECT ar.id, ar.user_id, ar.agent_id, ar.threshold,
                       u.email AS user_email, u.telegram_chat_id AS telegram_chat_id,
                       ta.name AS agent_name
                FROM alert_rules ar
                JOIN users u ON u.id = ar.user_id
                JOIN trading_agents ta ON ta.id = ar.agent_id
                WHERE ar.alert_type = 'agent_inactive'
                  AND ar.is_enabled IS TRUE
                  AND (ar.last_triggered_at IS NULL
                       OR ar.last_triggered_at < NOW() - INTERVAL '24 hours')
                """),
            ).mappings().all()

            hours = 24
            for rule in inactive_rules:
                thr_h = rule["threshold"]
                try:
                    hours = int(float(thr_h)) if thr_h is not None else 24
                except (TypeError, ValueError):
                    hours = 24
                hours = max(1, min(hours, 168))

                recent = c.execute(
                    text("""
                    SELECT 1 AS ok FROM paper_trades
                    WHERE user_id = :uid AND agent_id = :aid
                      AND timestamp >= NOW() - CAST(:win AS interval)
                    LIMIT 1
                    """),
                    {
                        "uid": rule["user_id"],
                        "aid": rule["agent_id"],
                        "win": f"{hours} hours",
                    },
                ).first()
                if recent:
                    continue

                agent_name = str(rule["agent_name"] or "")
                title = f"Agent {agent_name} je neaktívny"
                message = (
                    f"Tvoj agent {agent_name} neobchodoval posledných {hours} hodín. Skontroluj jeho stav."
                )
                c.execute(
                    text("""
                    INSERT INTO notifications (user_id, type, title, message)
                    VALUES (:uid, 'agent_inactive', :title, :msg)
                    """),
                    {"uid": rule["user_id"], "title": title, "msg": message},
                )
                c.execute(
                    text("UPDATE alert_rules SET last_triggered_at = NOW() WHERE id = :rid"),
                    {"rid": rule["id"]},
                )
                to_email = str(rule["user_email"] or "")
                send_user_alert(
                    to_email,
                    f"[Hermes Alert] {title}",
                    f"{message}\n\n{base_url}",
                )
                tgid = rule.get("telegram_chat_id")
                if tgid is not None:
                    try:
                        send_alert(int(tgid), title, message, "agent_inactive")
                    except Exception as tgx:  # noqa: BLE001
                        print(f"Telegram agent_inactive alert failed: {tgx}")
                log_event("alert_fired", "info", title)

    except Exception as exc:  # noqa: BLE001
        log_event("alert_check", "warning", f"Alert check failed: {exc}")


_USER_AGENT_BASE_USD = {
    "BTC": 97500.0,
    "ETH": 3400.0,
    "SOL": 180.0,
    "BNB": 640.0,
    "XRP": 2.2,
    "ADA": 0.95,
    "AVAX": 38.0,
    "DOT": 7.2,
    "MATIC": 0.85,
    "LINK": 18.0,
}

_WATCHER_DEFAULTS = {
    "polling_interval_sec": 60,
    "max_position_size_pct": 10.0,
    "stop_loss_pct": 2.0,
    "take_profit_pct": 0.0,
    "trailing_stop": False,
    "trailing_stop_pct": 1.5,
    "max_daily_drawdown_pct": 5.0,
    "max_daily_trades": 10,
    "trading_hours_enabled": False,
    "trading_hours_start": "09:00",
    "trading_hours_end": "17:00",
    "trading_days": [1, 2, 3, 4, 5, 6, 7],
    "momentum_lookback": 20,
    "mean_reversion_threshold": 2.0,
    "alert_pnl_drop_pct": 3.0,
    "alert_price_target": 0.0,
    "priority": "normal",
}


def get_agent_watcher_config(agent: dict) -> dict:
    """Load watcher config with safe defaults + basic validation."""
    raw = agent.get("watcher_config")
    cfg = raw if isinstance(raw, dict) else {}
    merged = {**_WATCHER_DEFAULTS, **cfg}
    try:
        merged["polling_interval_sec"] = int(max(10, min(300, int(merged.get("polling_interval_sec", 60)))))
    except Exception:  # noqa: BLE001
        merged["polling_interval_sec"] = _WATCHER_DEFAULTS["polling_interval_sec"]
    for k, lo, hi in (
        ("max_position_size_pct", 1.0, 50.0),
        ("stop_loss_pct", 0.1, 15.0),
        ("take_profit_pct", 0.0, 50.0),
        ("trailing_stop_pct", 0.1, 20.0),
        ("max_daily_drawdown_pct", 0.5, 30.0),
        ("mean_reversion_threshold", 0.5, 5.0),
    ):
        try:
            merged[k] = float(max(lo, min(hi, float(merged.get(k, _WATCHER_DEFAULTS[k])))))
        except Exception:  # noqa: BLE001
            merged[k] = _WATCHER_DEFAULTS[k]
    try:
        merged["max_daily_trades"] = int(max(1, min(200, int(merged.get("max_daily_trades", 10)))))
    except Exception:  # noqa: BLE001
        merged["max_daily_trades"] = _WATCHER_DEFAULTS["max_daily_trades"]
    try:
        merged["momentum_lookback"] = int(max(5, min(50, int(merged.get("momentum_lookback", 20)))))
    except Exception:  # noqa: BLE001
        merged["momentum_lookback"] = _WATCHER_DEFAULTS["momentum_lookback"]
    merged["trailing_stop"] = bool(merged.get("trailing_stop"))
    merged["trading_hours_enabled"] = bool(merged.get("trading_hours_enabled"))
    days = merged.get("trading_days")
    if not isinstance(days, list):
        days = [1, 2, 3, 4, 5, 6, 7]
    clean_days = []
    for d in days:
        try:
            di = int(d)
            if 1 <= di <= 7:
                clean_days.append(di)
        except Exception:  # noqa: BLE001
            continue
    merged["trading_days"] = clean_days or [1, 2, 3, 4, 5, 6, 7]
    pr = str(merged.get("priority") or "normal").lower()
    merged["priority"] = "high" if pr == "high" else "normal"
    return merged


def should_trade_now(watcher_config: dict) -> bool:
    """Check trading schedule in UTC."""
    if not watcher_config.get("trading_hours_enabled"):
        return True
    now_utc = datetime.now(timezone.utc)
    current_day = now_utc.isoweekday()
    if current_day not in watcher_config.get("trading_days", [1, 2, 3, 4, 5, 6, 7]):
        return False
    start_s = str(watcher_config.get("trading_hours_start", "00:00"))
    end_s = str(watcher_config.get("trading_hours_end", "23:59"))
    try:
        sh, sm = [int(x) for x in start_s.split(":")]
        eh, em = [int(x) for x in end_s.split(":")]
        start_t = dtime(sh, sm)
        end_t = dtime(eh, em)
    except Exception:  # noqa: BLE001
        return True
    ct = now_utc.time()
    if start_t <= end_t:
        return start_t <= ct <= end_t
    return ct >= start_t or ct <= end_t


def check_daily_drawdown(agent_id: int, user_id: int, max_drawdown_pct: float) -> bool:
    """Pause agent if daily drawdown threshold is reached. Returns paused bool."""
    eng = _engine()
    if eng is None:
        return False
    baseline = 10000.0
    try:
        with eng.begin() as conn:
            pnl_row = conn.execute(
                text(
                    """
                    SELECT COALESCE(SUM(pnl), 0)::double precision AS pnl
                    FROM paper_trades
                    WHERE user_agent_id = :aid
                      AND user_id = :uid
                      AND (timestamp AT TIME ZONE 'UTC')::date
                          = (CURRENT_TIMESTAMP AT TIME ZONE 'UTC')::date
                    """
                ),
                {"aid": int(agent_id), "uid": int(user_id)},
            ).mappings().first()
            today_pnl = float((pnl_row or {}).get("pnl") or 0.0)
            dd_pct = abs((today_pnl / baseline) * 100.0) if today_pnl < 0 else 0.0
            if dd_pct < float(max_drawdown_pct):
                return False
            ag = conn.execute(
                text("SELECT name, status FROM user_agents WHERE id = :aid AND user_id = :uid"),
                {"aid": int(agent_id), "uid": int(user_id)},
            ).mappings().first()
            if not ag or str(ag.get("status") or "") == "paused":
                return False
            conn.execute(
                text("UPDATE user_agents SET status = 'paused', updated_at = NOW() WHERE id = :aid AND user_id = :uid"),
                {"aid": int(agent_id), "uid": int(user_id)},
            )
            msg = (
                f"Agent {ag.get('name') or agent_id} bol automaticky pauzovaný "
                f"(denný drawdown limit -{float(max_drawdown_pct):.2f}% dosiahnutý)."
            )
            conn.execute(
                text(
                    """
                    INSERT INTO notifications (user_id, type, title, message)
                    VALUES (:uid, 'risk_guard', 'Auto-pause agenta', :msg)
                    """
                ),
                {"uid": int(user_id), "msg": msg},
            )
            log_event("user_agents", "warning", msg)
            return True
    except Exception as exc:  # noqa: BLE001
        log_event("user_agents", "warning", f"daily drawdown check failed for {agent_id}: {exc}")
        return False


def process_user_agents() -> None:
    """Generate occasional paper trades for user-created (no-code) agents."""
    import random

    from sqlalchemy.exc import ProgrammingError

    from core.agent_marketplace import record_paper_trade

    eng = _engine()
    if eng is None:
        return
    try:
        with eng.connect() as conn:
            rows = conn.execute(
                text("""
                SELECT ua.id, ua.user_id, ua.name, ua.symbol, ua.strategy_type, ua.config_json,
                       COALESCE(u.tier, 'basic') AS user_tier
                FROM user_agents ua
                JOIN users u ON u.id = ua.user_id
                WHERE ua.status = 'active'
                """),
            ).mappings().all()
    except ProgrammingError as exc:
        log_event("user_agents", "info", f"user_agents skip: {exc}")
        return
    except Exception as exc:  # noqa: BLE001
        log_event("user_agents", "warning", f"user_agents load failed: {exc}")
        return

    buy_bias = {
        "momentum": 0.55,
        "mean_reversion": 0.45,
        "breakout": 0.52,
        "trend_following": 0.58,
        "scalping": 0.5,
        "grid": 0.5,
        "dca": 0.62,
    }

    rows_sorted = sorted(
        rows,
        key=lambda r: 0
        if (
            str(r.get("user_tier") or "").lower() in ("elite", "admin")
            and get_agent_watcher_config(dict(r)).get("priority") == "high"
        )
        else 1,
    )

    for row in rows_sorted:
        watcher_cfg = get_agent_watcher_config(dict(row))
        if not should_trade_now(watcher_cfg):
            continue
        cfg = row["config_json"] if isinstance(row["config_json"], dict) else {}
        max_daily = watcher_cfg.get("max_daily_trades", cfg.get("max_daily_trades", 10))
        if max_daily == "unlimited" or str(max_daily).lower() == "unlimited":
            max_daily = 999
        try:
            max_daily = int(max_daily)
        except (TypeError, ValueError):
            max_daily = 10

        try:
            with eng.begin() as cnt_conn:
                cnt_row = cnt_conn.execute(
                    text("""
                    SELECT COUNT(*)::int AS c FROM paper_trades
                    WHERE user_agent_id = :uaid
                      AND (timestamp AT TIME ZONE 'UTC')::date
                          = (CURRENT_TIMESTAMP AT TIME ZONE 'UTC')::date
                    """),
                    {"uaid": row["id"]},
                ).mappings().first()
                n_today = int(cnt_row["c"]) if cnt_row else 0
        except Exception:  # noqa: BLE001
            continue

        if n_today >= max_daily:
            continue
        if random.random() > 0.35:
            continue

        sym_raw = str(row["symbol"] or "BTC")
        if "/" in sym_raw:
            sym_pair = sym_raw.upper()
            base_sym = sym_raw.split("/")[0].strip().upper()
        else:
            base_sym = sym_raw.strip().upper()
            sym_pair = f"{base_sym}/USD"

        base_price = float(_USER_AGENT_BASE_USD.get(base_sym, 100.0))
        price = base_price * random.uniform(0.997, 1.003)

        st = str(row["strategy_type"] or "momentum").lower()
        bias = buy_bias.get(st, 0.5)
        action = "buy" if random.random() < bias else "sell"

        pos_pct = float(watcher_cfg.get("max_position_size_pct", cfg.get("position_size_pct", 10.0)) or 10.0)
        qty = max(0.0001, (10000.0 * (pos_pct / 100.0)) / price)
        slip_pct = float(watcher_cfg.get("stop_loss_pct", cfg.get("stop_loss_pct", 2.0)) or 2.0) / 100.0
        if st == "momentum":
            lookback = int(watcher_cfg.get("momentum_lookback", 20))
            bias = min(0.7, max(0.45, 0.5 + (lookback - 20) * 0.003))
            action = "buy" if random.random() < bias else "sell"
        elif st == "mean_reversion":
            thr = float(watcher_cfg.get("mean_reversion_threshold", 2.0))
            bias = min(0.65, max(0.35, 0.5 - (thr - 2.0) * 0.03))
            action = "buy" if random.random() < bias else "sell"
        pnl = random.uniform(-slip_pct, slip_pct * 1.15) * qty * price * (1.0 if action == "buy" else -0.85)
        pnl = round(pnl, 4)

        agent_row = {
            "strategy": st,
            "name": row["name"],
            "symbol": sym_pair,
            "category": "crypto",
        }
        try:
            record_paper_trade(
                int(row["user_id"]),
                None,
                sym_pair,
                action,
                float(price),
                float(qty),
                float(pnl),
                user_agent_id=int(row["id"]),
                agent_row=agent_row,
                write_explanation=True,
            )
        except Exception as exc:  # noqa: BLE001
            log_event("user_agents", "warning", f"user_agent {row['id']} trade: {exc}")
            continue

        check_daily_drawdown(int(row["id"]), int(row["user_id"]), float(watcher_cfg.get("max_daily_drawdown_pct", 5.0)))


def run_watcher_cycle() -> None:
    print(f"\n[{datetime.now(timezone.utc).isoformat()}] Watcher cycle…")
    healthy = check_web_health()
    if not healthy:
        time.sleep(30)
        healthy = check_web_health()
        if not healthy:
            print("App still down, attempting restart…")
            restarted = restart_dashboard()
            time.sleep(15)
            if restarted and check_web_health():
                send_admin_alert(
                    "[HERMES] Auto-fix SUCCESS",
                    "App was down but restarted and now answers /api/auth/status.",
                )
    compute_and_store_pnl_snapshots()
    process_user_agents()
    _maybe_refresh_historical_candles()
    check_and_fire_alerts()
    now = datetime.now(timezone.utc)
    if now.weekday() == 0 and now.hour == 8 and now.minute < 10:
        send_weekly_reports()
    if now.hour % 6 == 0 and now.minute < 5:
        try:
            eng_lb = _engine()
            if eng_lb is not None:
                with eng_lb.begin() as c_lb:
                    compute_leaderboard_cache(c_lb)
                log_event("leaderboard", "info", "Leaderboard cache refreshed")
        except Exception as exc:  # noqa: BLE001
            log_event("leaderboard", "warning", f"Leaderboard refresh failed: {exc}")
    if (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip():
        try:
            offset_file = _BASE / ".telegram_offset"
            offset_val: int | None = None
            if offset_file.exists():
                try:
                    offset_val = int(offset_file.read_text().strip())
                except (ValueError, OSError):
                    offset_val = None
            updates = get_updates(offset_val)
            if updates:
                eng_tg = _engine()
                if eng_tg is not None:
                    with eng_tg.begin() as conn_tg:
                        for upd in updates:
                            process_update(upd, conn_tg)
                    new_off = int(updates[-1]["update_id"]) + 1
                    try:
                        offset_file.write_text(str(new_off))
                    except OSError:
                        pass
        except Exception as exc:  # noqa: BLE001
            log_event("telegram_poll", "warning", f"Telegram polling error: {exc}")
    check_disk_space()
    check_ssl_cert()


if __name__ == "__main__":
    print("Hermes Watcher Agent started")
    send_admin_alert("[HERMES] Watcher Started", "System monitoring is now active.")
    while True:
        run_watcher_cycle()
        time.sleep(max(60, _CYCLE_SEC))
