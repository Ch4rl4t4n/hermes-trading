"""SQLAlchemy models for multi-tenant SaaS data."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.database import Base

if TYPE_CHECKING:
    pass


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False, index=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    tier: Mapped[str] = mapped_column(String(32), nullable=False, default="basic")
    failed_login_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    locked_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    totp_secret: Mapped[str] = mapped_column(String(64), nullable=False)
    totp_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    last_login: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    stripe_customer_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    stripe_subscription_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    stripe_subscription_status: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    tier_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    billing_cycle: Mapped[str] = mapped_column(String(8), nullable=False, default="monthly")
    trial_promo_tier: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    trial_promo_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    onboarding_completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    google_id: Mapped[Optional[str]] = mapped_column(String(255), unique=True, nullable=True, index=True)
    auth_kind: Mapped[str] = mapped_column(String(20), nullable=False, default="db")
    email_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    email_verification_token_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    email_verification_expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    email_verification_sent_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    weekly_report_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    weekly_report_sent_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    unsubscribe_token: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, unique=True)
    telegram_chat_id: Mapped[Optional[int]] = mapped_column(BigInteger(), nullable=True)
    telegram_connected_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    telegram_connect_token: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    telegram_connect_token_exp: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    referral_code: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, unique=True, index=True)
    referred_by: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    referral_bonus_expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    referral_bonus_slots: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    audit_logs: Mapped[list["AuditLog"]] = relationship(back_populates="user")
    accounts: Mapped[list["Account"]] = relationship(
        "Account",
        back_populates="user",
        cascade="all, delete-orphan",
    )


class Referral(Base):
    __tablename__ = "referrals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    referrer_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    referred_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    bonus_granted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class Account(Base):
    __tablename__ = "accounts"
    __table_args__ = (UniqueConstraint("user_id", "account_type", name="uq_user_account_type"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    account_type: Mapped[str] = mapped_column(String(16), nullable=False)  # paper|real
    account_status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")  # active|suspended|closed
    alpaca_api_key: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    alpaca_api_secret: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    paper_balance: Mapped[Any] = mapped_column(Numeric(18, 2), nullable=False, default=100_000)
    real_balance: Mapped[Optional[Any]] = mapped_column(Numeric(18, 2), nullable=True)
    max_single_trade_pct: Mapped[Any] = mapped_column(Numeric(6, 2), nullable=False, default=5)
    max_daily_loss_pct: Mapped[Any] = mapped_column(Numeric(6, 2), nullable=False, default=3)
    max_drawdown_pct: Mapped[Any] = mapped_column(Numeric(6, 2), nullable=False, default=10)

    user: Mapped["User"] = relationship("User", back_populates="accounts")
    trading_configuration: Mapped[Optional["TradingConfiguration"]] = relationship(
        back_populates="account",
        uselist=False,
        cascade="all, delete-orphan",
    )
    trades: Mapped[list["Trade"]] = relationship(back_populates="account", cascade="all, delete-orphan")


class TradingConfiguration(Base):
    __tablename__ = "trading_configurations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), unique=True, nullable=False)
    agents: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    llm_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    trading_mode: Mapped[str] = mapped_column(String(32), nullable=False, default="day_trading")

    account: Mapped["Account"] = relationship(back_populates="trading_configuration")


class Trade(Base):
    __tablename__ = "trades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False, index=True)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    trade_type: Mapped[str] = mapped_column(String(8), nullable=False)  # BUY|SELL

    entry_price: Mapped[Optional[Any]] = mapped_column(Numeric(24, 8), nullable=True)
    entry_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    entry_qty: Mapped[Optional[Any]] = mapped_column(Numeric(24, 12), nullable=True)

    exit_price: Mapped[Optional[Any]] = mapped_column(Numeric(24, 8), nullable=True)
    exit_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    pnl: Mapped[Optional[Any]] = mapped_column(Numeric(18, 4), nullable=True)
    pnl_pct: Mapped[Optional[Any]] = mapped_column(Numeric(12, 4), nullable=True)

    trading_mode: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    regime: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    llm_decision: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    alpaca_order_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    account: Mapped["Account"] = relationship(back_populates="trades")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    account_id: Mapped[Optional[int]] = mapped_column(ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True)
    action: Mapped[str] = mapped_column(String(128), nullable=False)
    details: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)

    user: Mapped[Optional["User"]] = relationship(back_populates="audit_logs")


class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    key_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    key_prefix: Mapped[str] = mapped_column(String(8), nullable=False)
    name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    scopes: Mapped[str] = mapped_column(String(200), nullable=False, default="read:all,write:agents")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)


class ApiRequest(Base):
    __tablename__ = "api_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    api_key_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("api_keys.id", ondelete="SET NULL"), nullable=True, index=True
    )
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    endpoint: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    method: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    status_code: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    response_time_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)


class PlatformSetting(Base):
    __tablename__ = "platform_settings"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )


class Announcement(Base):
    __tablename__ = "announcements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    dismissals: Mapped[list["AnnouncementDismissal"]] = relationship(
        back_populates="announcement",
        cascade="all, delete-orphan",
    )


class AnnouncementDismissal(Base):
    """Per-user dismiss state for an announcement (table name: user_announcements)."""

    __tablename__ = "user_announcements"
    __table_args__ = (UniqueConstraint("user_id", "announcement_id", name="uq_user_announcement_dismissal"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    announcement_id: Mapped[int] = mapped_column(
        ForeignKey("announcements.id", ondelete="CASCADE"), nullable=False, index=True
    )
    dismissed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)

    announcement: Mapped["Announcement"] = relationship(back_populates="dismissals")
