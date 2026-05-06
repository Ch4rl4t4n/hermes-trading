import os
import logging
import requests

log = logging.getLogger("telegram")


def send(message: str) -> None:
    """Fire-and-forget Telegram message. Never raises."""
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": message, "parse_mode": "HTML"},
            timeout=10,
        )
    except Exception as exc:
        log.warning("Telegram send failed: %s", exc)
