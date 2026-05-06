"""Hermes Telegram bot — alerts and /start, /status, /pnl commands."""

from __future__ import annotations

import html
import os
from datetime import datetime, timezone
from typing import Any, Optional

import requests
from sqlalchemy import text as sql_text

TELEGRAM_TOKEN = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
APP_URL = (
    os.getenv("HERMES_APP_URL")
    or os.getenv("DASHBOARD_PUBLIC_BASE_URL")
    or "https://app.letagentscook.lol"
).rstrip("/")


def send_message(chat_id: int, text: str, *, parse_mode: str = "HTML") -> bool:
    if not TELEGRAM_TOKEN:
        print(f"TELEGRAM (no token): {text[:100]}")
        return False
    try:
        r = requests.post(
            f"{TELEGRAM_API}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": parse_mode,
                "disable_web_page_preview": True,
            },
            timeout=10,
        )
        return r.status_code == 200
    except Exception as e:  # noqa: BLE001
        print(f"Telegram send failed: {e}")
        return False


def send_alert(chat_id: int, title: str, message: str, alert_type: str = "info") -> bool:
    icons = {
        "pnl_drop": "🔴",
        "agent_inactive": "⚠️",
        "weekly_summary": "📊",
        "info": "ℹ️",
        "success": "✅",
        "demo_agent": "🤖",
    }
    icon = icons.get(alert_type, "ℹ️")
    safe_title = html.escape(str(title))
    safe_msg = html.escape(str(message))
    text_body = (
        f"{icon} <b>{safe_title}</b>\n\n"
        f"{safe_msg}\n\n"
        f"<a href=\"{html.escape(APP_URL)}\">Otvoriť Hermes →</a>"
    )
    return send_message(chat_id, text_body)


def get_updates(offset: Optional[int] = None) -> list[dict[str, Any]]:
    if not TELEGRAM_TOKEN:
        return []
    try:
        params: dict[str, Any] = {"timeout": 0, "limit": 100}
        if offset is not None:
            params["offset"] = offset
        r = requests.get(
            f"{TELEGRAM_API}/getUpdates",
            params=params,
            timeout=15,
        )
        if r.status_code == 200:
            return list(r.json().get("result") or [])
    except Exception as e:  # noqa: BLE001
        print(f"Telegram getUpdates failed: {e}")
    return []


def set_webhook(webhook_url: str) -> bool:
    if not TELEGRAM_TOKEN:
        return False
    try:
        payload: dict[str, Any] = {"url": webhook_url}
        secret = (os.getenv("TELEGRAM_WEBHOOK_SECRET") or "").strip()
        if secret:
            payload["secret_token"] = secret
        r = requests.post(
            f"{TELEGRAM_API}/setWebhook",
            json=payload,
            timeout=10,
        )
        return r.status_code == 200
    except Exception as e:  # noqa: BLE001
        print(f"Telegram setWebhook failed: {e}")
        return False


def delete_webhook() -> bool:
    if not TELEGRAM_TOKEN:
        return False
    try:
        r = requests.post(f"{TELEGRAM_API}/deleteWebhook", timeout=10)
        return r.status_code == 200
    except Exception as e:  # noqa: BLE001
        print(f"Telegram deleteWebhook failed: {e}")
        return False


def process_update(update: dict, db_conn) -> None:
    message = update.get("message") or {}
    if not message:
        return
    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    text_raw = (message.get("text") or "").strip()
    if chat_id is None or not text_raw:
        return
    chat_id = int(chat_id)

    command = None
    if text_raw.startswith("/"):
        command = text_raw.split()[0].lower()
        if "@" in command:
            command = command.split("@", 1)[0]
    if command == "/start":
        _handle_start(chat_id, text_raw, db_conn)
    elif command == "/status":
        _handle_status(chat_id, db_conn)
    elif command == "/pnl":
        _handle_pnl(chat_id, db_conn)
    elif command == "/help":
        _handle_help(chat_id)
    elif command == "/stop":
        _handle_stop(chat_id, db_conn)
    else:
        send_message(
            chat_id,
            "Nerozumiem príkazu. Pošli /help pre zoznam príkazov.",
            parse_mode="HTML",
        )


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _handle_start(chat_id: int, text: str, db_conn) -> None:
    parts = text.split()
    if len(parts) < 2:
        send_message(
            chat_id,
            "👋 <b>Vitaj v Hermes Trading Bot!</b>\n\n"
            "Pre prepojenie s tvojím Hermes účtom:\n"
            "1. Otvor <a href=\""
            + html.escape(APP_URL)
            + "\">Hermes dashboard</a>\n"
            "2. V menu Settings otvor sekciu Telegram\n"
            "3. Klikni „Prepojiť Telegram“\n\n"
            "Dostaneš odkaz s tokenom.",
            parse_mode="HTML",
        )
        return

    connect_token = parts[1].strip()
    row = db_conn.execute(
        sql_text("""
            SELECT id, email, telegram_connect_token_exp
            FROM users
            WHERE telegram_connect_token = :token
            LIMIT 1
        """),
        {"token": connect_token},
    ).mappings().first()
    if not row:
        send_message(
            chat_id,
            "❌ Token je neplatný alebo expiroval.\n"
            "Vygeneruj nový v Hermes nastaveniach.",
        )
        return

    exp = row["telegram_connect_token_exp"]
    now = _now_utc()
    if exp is not None:
        exp_d = exp if exp.tzinfo else exp.replace(tzinfo=timezone.utc)
        if exp_d <= now:
            send_message(
                chat_id,
                "❌ Token je neplatný alebo expiroval.\n"
                "Vygeneruj nový v Hermes nastaveniach.",
            )
            return

    uid = int(row["id"])
    email = str(row["email"] or "")

    db_conn.execute(
        sql_text("""
            UPDATE users
            SET telegram_chat_id = :chat_id,
                telegram_connected_at = CURRENT_TIMESTAMP,
                telegram_connect_token = NULL,
                telegram_connect_token_exp = NULL
            WHERE id = :uid
        """),
        {"chat_id": chat_id, "uid": uid},
    )

    send_message(
        chat_id,
        "✅ <b>Úspešne prepojené!</b>\n\n"
        f"Tvoj Hermes účet ({html.escape(email)}) je teraz prepojený.\n\n"
        "Budeš dostávať:\n"
        "• 🔴 Alerty keď P&amp;L klesne\n"
        "• ⚠️ Upozornenia pri neaktívnom agentovi\n"
        "• 📊 Týždenné reporty\n\n"
        "Príkazy: /pnl /status /help /stop",
        parse_mode="HTML",
    )


def _handle_status(chat_id: int, db_conn) -> None:
    user = db_conn.execute(
        sql_text("SELECT id FROM users WHERE telegram_chat_id = :cid"),
        {"cid": chat_id},
    ).mappings().first()
    if not user:
        send_message(chat_id, "Najprv prepoj účet cez /start.")
        return

    uid = int(user["id"])
    agents = db_conn.execute(
        sql_text("""
            SELECT ta.name, ta.symbol, us.mode, us.is_active
            FROM user_subscriptions us
            JOIN trading_agents ta ON ta.id = us.agent_id
            WHERE us.user_id = :uid AND us.is_active IS TRUE
            ORDER BY ta.name
        """),
        {"uid": uid},
    ).mappings().all()

    if not agents:
        send_message(
            chat_id,
            "Nemáš žiadnych aktívnych agentov.\n"
            f"Pridaj si ich na {html.escape(APP_URL)}",
        )
        return

    lines = ["📊 <b>Tvoji aktívni agenti:</b>\n"]
    for a in agents:
        status = "✅" if a["is_active"] else "⏸"
        lines.append(
            f"{status} {html.escape(str(a['name']))} "
            f"({html.escape(str(a['symbol']))}) — {html.escape(str(a['mode']))}"
        )
    send_message(chat_id, "\n".join(lines), parse_mode="HTML")


def _handle_pnl(chat_id: int, db_conn) -> None:
    user = db_conn.execute(
        sql_text("SELECT id FROM users WHERE telegram_chat_id = :cid"),
        {"cid": chat_id},
    ).mappings().first()
    if not user:
        send_message(chat_id, "Najprv prepoj účet cez /start.")
        return

    uid = int(user["id"])
    snaps = db_conn.execute(
        sql_text("""
            SELECT ta.name, ta.symbol,
                   aps.pnl_usd, aps.pnl_pct, aps.snapshot_date
            FROM agent_pnl_snapshots aps
            JOIN trading_agents ta ON ta.id = aps.agent_id
            WHERE aps.user_id = :uid
              AND aps.snapshot_date = CURRENT_DATE
            ORDER BY aps.pnl_pct DESC
        """),
        {"uid": uid},
    ).mappings().all()

    if not snaps:
        send_message(
            chat_id,
            "Žiadne P&amp;L dáta pre dnešok.\n"
            "Watcher ich aktualizuje priebežne.",
            parse_mode="HTML",
        )
        return

    total = sum(float(s["pnl_usd"] or 0) for s in snaps)
    sign = "+" if total >= 0 else ""
    emoji = "📈" if total >= 0 else "📉"

    lines = [f"{emoji} <b>Dnešný P&amp;L:</b> {sign}{total:.2f} USD\n"]
    for s in snaps:
        pnl_pct = float(s["pnl_pct"] or 0)
        pnl_usd = float(s["pnl_usd"] or 0)
        pct_sign = "+" if pnl_pct >= 0 else ""
        usd_sign = "+" if pnl_usd >= 0 else ""
        e = "🟢" if pnl_pct >= 0 else "🔴"
        lines.append(
            f"{e} {html.escape(str(s['name']))}: "
            f"{pct_sign}{pnl_pct:.2f}% "
            f"({usd_sign}{pnl_usd:.2f}$)"
        )
    send_message(chat_id, "\n".join(lines), parse_mode="HTML")


def _handle_help(chat_id: int) -> None:
    send_message(
        chat_id,
        "🤖 <b>Hermes Bot — príkazy:</b>\n\n"
        "/pnl — Aktuálny P&amp;L tvojich agentov\n"
        "/status — Stav aktívnych agentov\n"
        "/help — Tento zoznam\n"
        "/stop — Odpoj Telegram notifikácie\n\n"
        f"<a href=\"{html.escape(APP_URL)}\">Otvoriť dashboard</a>",
        parse_mode="HTML",
    )


def _handle_stop(chat_id: int, db_conn) -> None:
    db_conn.execute(
        sql_text("""
            UPDATE users
            SET telegram_chat_id = NULL,
                telegram_connected_at = NULL
            WHERE telegram_chat_id = :cid
        """),
        {"cid": chat_id},
    )
    send_message(
        chat_id,
        "✅ Telegram notifikácie boli vypnuté.\n"
        "Môžeš ich znova zapnúť v Hermes nastaveniach.",
    )
