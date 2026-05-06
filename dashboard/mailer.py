"""Send transactional email (SMTP)."""

from __future__ import annotations

import logging
import os
import smtplib
import ssl
from email.message import EmailMessage

log = logging.getLogger(__name__)


def is_mail_configured() -> bool:
    t = (os.getenv("MAIL_TRANSPORT") or "smtp").strip().lower()
    if t != "smtp":
        return False
    return bool(
        (os.getenv("SMTP_HOST") or "").strip()
        and (os.getenv("MAIL_FROM") or "").strip()
        and (os.getenv("SMTP_USER") or "").strip()
        and (os.getenv("SMTP_PASSWORD") or "").strip()
    )


def send_smtp_email(*, to_addr: str, subject: str, text_body: str) -> None:
    host = (os.getenv("SMTP_HOST") or "").strip()
    port = int((os.getenv("SMTP_PORT") or "587").strip() or "587")
    user = (os.getenv("SMTP_USER") or "").strip()
    password = (os.getenv("SMTP_PASSWORD") or "").strip()
    mail_from = (os.getenv("MAIL_FROM") or "").strip()
    if not host or not mail_from or not user:
        raise RuntimeError("SMTP is not fully configured")
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = mail_from
    msg["To"] = to_addr
    msg.set_content(text_body)
    ctx = ssl.create_default_context()
    with smtplib.SMTP(host, port, timeout=30) as smtp:
        smtp.ehlo()
        smtp.starttls(context=ctx)
        smtp.ehlo()
        smtp.login(user, password)
        smtp.send_message(msg)


def send_verification_email(to_email: str, raw_token: str, *, public_base_url: str) -> None:
    base = (public_base_url or "").strip().rstrip("/")
    if not base:
        raise RuntimeError("DASHBOARD_PUBLIC_BASE_URL is not set")
    link = f"{base}/api/auth/verify-email?token={raw_token}"
    subject = "Verify your LETAGENTSCOOK account"
    body = (
        "Welcome to LETAGENTSCOOK.\n\n"
        "Please verify your email by opening this link (valid 48 hours):\n\n"
        f"{link}\n\n"
        "If you did not create an account, you can ignore this message.\n"
    )
    if not is_mail_configured():
        raise RuntimeError("Outgoing mail is not configured (set MAIL_TRANSPORT=smtp and SMTP_* / MAIL_FROM).")
    send_smtp_email(to_addr=to_email, subject=subject, text_body=body)
    log.info("verification email queued/sent to %s", to_email)


def send_password_reset_email(to_email: str, raw_token: str, *, public_base_url: str) -> None:
    base = (public_base_url or "").strip().rstrip("/")
    if not base:
        raise RuntimeError("DASHBOARD_PUBLIC_BASE_URL is not set")
    link = f"{base}/?reset_token={raw_token}"
    subject = "Reset your LETAGENTSCOOK password"
    body = (
        "We received a request to reset your LETAGENTSCOOK password.\n\n"
        "Open this link to continue (valid 60 minutes):\n\n"
        f"{link}\n\n"
        "If you did not request this, you can ignore this message.\n"
    )
    if not is_mail_configured():
        raise RuntimeError("Outgoing mail is not configured (set MAIL_TRANSPORT=smtp and SMTP_* / MAIL_FROM).")
    send_smtp_email(to_addr=to_email, subject=subject, text_body=body)
    log.info("password reset email queued/sent to %s", to_email)
