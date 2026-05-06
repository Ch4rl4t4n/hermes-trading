"""Subscription tier capabilities and enforcement helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from core.models import User

# Canonical tiers (database / API)
TIER_BASIC = "basic"
TIER_MEDIUM = "medium"
TIER_PRO = "pro"
TIER_ELITE = "elite"
TIER_ADMIN = "admin"

_LEGACY_MAP = {
    "free": TIER_BASIC,
    "starter": TIER_MEDIUM,
    "professional": TIER_PRO,
}

TIER_RANK = {
    TIER_BASIC: 0,
    TIER_MEDIUM: 1,
    TIER_PRO: 2,
    TIER_ELITE: 3,
    TIER_ADMIN: 4,
}

BASIC_AGENT_SYMBOLS = frozenset({"BTC/USD", "ETH/USD", "TSLA"})

# Display names and list pricing (informational; Stripe is source of truth for billing)
TIER_DISPLAY_NAME: dict[str, str] = {
    TIER_BASIC: "Basic",
    TIER_MEDIUM: "Medium",
    TIER_PRO: "Pro",
    TIER_ELITE: "Elite",
    TIER_ADMIN: "Admin",
}

TIER_PRICE_MONTHLY_USD: dict[str, int] = {
    TIER_BASIC: 0,
    TIER_MEDIUM: 29,
    TIER_PRO: 19,
    TIER_ELITE: 49,
    TIER_ADMIN: 0,
}


def normalize_tier(raw: str | None) -> str:
    if not raw:
        return TIER_BASIC
    t = str(raw).strip().lower()
    if t in _LEGACY_MAP:
        return _LEGACY_MAP[t]
    if t in TIER_RANK:
        return t
    return t


def effective_tier(user: User | None) -> str:
    if user is None:
        return TIER_BASIC
    if getattr(user, "is_admin", False):
        return TIER_ADMIN
    t = normalize_tier(getattr(user, "tier", None))
    if t not in TIER_RANK:
        t = TIER_BASIC
    promo = getattr(user, "trial_promo_tier", None)
    until = getattr(user, "trial_promo_until", None)
    if promo and until:
        now = datetime.now(timezone.utc)
        if until > now:
            pt = normalize_tier(promo)
            if pt in TIER_RANK and pt != TIER_ADMIN and TIER_RANK[pt] > TIER_RANK[t]:
                return pt
    return t


@dataclass(frozen=True)
class TierCaps:
    history_days: Optional[int]
    agent_allowlist: Optional[frozenset[str]]
    agents_limit: Optional[int]
    ai_insights: bool
    backtest: bool
    portfolio_full: bool
    portfolio_advanced: bool
    dca: bool
    grid: bool
    real_money: bool


def tier_caps(tier: str) -> TierCaps:
    t = normalize_tier(tier)
    if t == TIER_ADMIN:
        return TierCaps(
            history_days=None,
            agent_allowlist=None,
            agents_limit=None,
            ai_insights=True,
            backtest=True,
            portfolio_full=True,
            portfolio_advanced=True,
            dca=True,
            grid=True,
            real_money=True,
        )
    if t == TIER_BASIC:
        return TierCaps(
            history_days=30,
            agent_allowlist=BASIC_AGENT_SYMBOLS,
            agents_limit=3,
            ai_insights=False,
            backtest=False,
            portfolio_full=False,
            portfolio_advanced=False,
            dca=False,
            grid=False,
            real_money=False,
        )
    if t == TIER_MEDIUM:
        return TierCaps(
            history_days=30,
            agent_allowlist=None,
            agents_limit=8,
            ai_insights=True,
            backtest=True,
            portfolio_full=False,
            portfolio_advanced=True,
            dca=True,
            grid=False,
            real_money=False,
        )
    if t == TIER_PRO:
        return TierCaps(
            history_days=365,
            agent_allowlist=None,
            agents_limit=10,
            ai_insights=True,
            backtest=True,
            portfolio_full=True,
            portfolio_advanced=True,
            dca=True,
            grid=True,
            real_money=True,
        )
    if t == TIER_ELITE:
        return TierCaps(
            history_days=None,
            agent_allowlist=None,
            agents_limit=None,
            ai_insights=True,
            backtest=True,
            portfolio_full=True,
            portfolio_advanced=True,
            dca=True,
            grid=True,
            real_money=True,
        )
    return tier_caps(TIER_BASIC)


def tier_display_name(tier_key: str) -> str:
    t = normalize_tier(tier_key)
    return TIER_DISPLAY_NAME.get(t, t.title())


# Plan caps for enforcement (marketplace slots + alert rules); keys used by API / UI.
TIER_LIMITS: dict[str, dict[str, Any]] = {
    TIER_BASIC: {
        "max_agents": 3,
        "max_alerts": 3,
        "leaderboard": "view",
        "telegram": False,
        "history_days": 30,
        "export": False,
        "api_access": False,
    },
    TIER_MEDIUM: {
        "max_agents": 8,
        "max_alerts": 8,
        "leaderboard": "full",
        "telegram": False,
        "history_days": 30,
        "export": True,
        "api_access": False,
    },
    TIER_PRO: {
        "max_agents": 10,
        "max_alerts": 15,
        "leaderboard": "full",
        "telegram": True,
        "history_days": 365,
        "export": True,
        "api_access": False,
    },
    TIER_ELITE: {
        "max_agents": 9999,
        "max_alerts": 9999,
        "leaderboard": "full",
        "telegram": True,
        "history_days": 9999,
        "export": True,
        "api_access": True,
    },
    TIER_ADMIN: {
        "max_agents": 9999,
        "max_alerts": 9999,
        "leaderboard": "full",
        "telegram": True,
        "history_days": 9999,
        "export": True,
        "api_access": True,
    },
}


def get_tier_limits(tier: str) -> dict[str, Any]:
    t = normalize_tier(tier)
    if t not in TIER_LIMITS:
        t = TIER_BASIC
    return dict(TIER_LIMITS[t])


def referral_extra_agent_slots(user: "User | None") -> int:
    """Extra marketplace / builder slots from an active referral bonus window."""
    if user is None:
        return 0
    now = datetime.now(timezone.utc)
    slots = int(getattr(user, "referral_bonus_slots", 0) or 0)
    exp = getattr(user, "referral_bonus_expires_at", None)
    if slots <= 0 or exp is None:
        return 0
    if getattr(exp, "tzinfo", None) is None:
        exp = exp.replace(tzinfo=timezone.utc)
    if exp <= now:
        return 0
    return slots


def effective_max_marketplace_agents(user: "User | None") -> Optional[int]:
    """Cap on active marketplace subscriptions including referral bonus (None = unlimited)."""
    if user is None:
        return 3
    lim = get_tier_limits(effective_tier(user)).get("max_agents")
    if lim is None or not isinstance(lim, int):
        return None
    if lim >= 9000:
        return None
    return lim + referral_extra_agent_slots(user)


def check_tier_limit(user: "User | None", limit_key: str, current_count: int = 0) -> bool:
    """Return True if user is under the cap for ``limit_key`` (e.g. max_agents)."""
    if user is None:
        return False
    limits = get_tier_limits(effective_tier(user))
    limit = limits.get(limit_key)
    if isinstance(limit, bool):
        return bool(limit)
    if isinstance(limit, int):
        return current_count < limit
    return True


def features_payload(user: User | None) -> dict[str, Any]:
    et = effective_tier(user)
    caps = tier_caps(et)
    stored = normalize_tier(getattr(user, "tier", None)) if user else TIER_BASIC
    if stored not in TIER_RANK:
        stored = TIER_BASIC
    now = datetime.now(timezone.utc)
    ttl = getattr(user, "trial_promo_until", None) if user else None
    ttt = getattr(user, "trial_promo_tier", None) if user else None
    trial_active = bool(
        user and ttl and ttt and ttl > now and normalize_tier(ttt) in TIER_RANK
    )
    trial_tier_norm = normalize_tier(ttt) if ttt else None
    tdisp = tier_display_name(et)
    if et == TIER_ADMIN:
        tdisp = "Admin"
    lim = dict(get_tier_limits(et))
    ex = referral_extra_agent_slots(user)
    ma = lim.get("max_agents")
    if isinstance(ma, int) and ma < 9000:
        lim["max_agents"] = ma + ex
    stripe_sub = getattr(user, "stripe_subscription_status", None) if user else None
    billing_cy = (getattr(user, "billing_cycle", None) or "monthly") if user else "monthly"
    tier_exp = getattr(user, "tier_expires_at", None) if user else None
    alim = caps.agents_limit
    if alim is not None:
        alim = alim + ex
    return {
        "tier": et,
        "tier_stored": stored,
        "tier_display": tdisp,
        "tier_limits": lim,
        "agents_limit": alim,
        "agents_limited": caps.agent_allowlist is not None,
        "allowed_agent_symbols": list(caps.agent_allowlist) if caps.agent_allowlist else None,
        "ai_insights": caps.ai_insights,
        "backtest": caps.backtest,
        "portfolio_full": caps.portfolio_full,
        "portfolio_advanced": caps.portfolio_advanced,
        "dca": caps.dca,
        "grid": caps.grid,
        "real_money": caps.real_money,
        "history_days": caps.history_days,
        "stripe_subscription_status": stripe_sub,
        "billing_cycle": billing_cy,
        "tier_expires_at": tier_exp.isoformat() if tier_exp else None,
        "onboarding_complete": bool(getattr(user, "onboarding_completed_at", None))
        if user
        else False,
        "price_monthly": TIER_PRICE_MONTHLY_USD.get(normalize_tier(et), 0),
        "trial": {
            "active": trial_active,
            "promo_tier": trial_tier_norm if trial_active else None,
            "ends_at": ttl.isoformat() if trial_active and ttl else None,
        },
    }


def tier_at_least(user: User | None, minimum: str) -> bool:
    et = effective_tier(user)
    need = normalize_tier(minimum)
    if need == TIER_ADMIN:
        return et == TIER_ADMIN
    return TIER_RANK.get(et, 0) >= TIER_RANK.get(need, 0)


def feature_allowed(user: User | None, feature_name: str) -> bool:
    """Map feature names (API / decorator) to tier capabilities."""
    if user is None:
        return False
    caps = tier_caps(effective_tier(user))
    if feature_name == "ai_insights":
        return caps.ai_insights
    if feature_name == "backtest":
        return caps.backtest
    if feature_name == "dca":
        return caps.dca
    if feature_name == "grid":
        return caps.grid
    if feature_name == "real_money":
        return caps.real_money
    if feature_name == "portfolio_full":
        return caps.portfolio_full
    if feature_name == "portfolio_advanced":
        return caps.portfolio_advanced
    if feature_name == "onboarding_complete":
        return bool(getattr(user, "onboarding_completed_at", None))
    return False


def agent_symbol_allowed(user: User | None, symbol: str) -> bool:
    caps = tier_caps(effective_tier(user))
    if caps.agent_allowlist is None:
        return True
    return symbol in caps.agent_allowlist


def clamp_trade_history_rows(
    rows: list[dict[str, Any]],
    user: User | None,
    ts_key: str = "exit_ts",
) -> list[dict[str, Any]]:
    caps = tier_caps(effective_tier(user))
    if caps.history_days is None:
        return rows
    cutoff = datetime.now(timezone.utc) - timedelta(days=caps.history_days)

    def _parse_ts(r: dict) -> Optional[datetime]:
        v = r.get(ts_key) or r.get("entry_ts")
        if not v:
            return None
        try:
            if isinstance(v, (int, float)):
                return datetime.fromtimestamp(float(v), tz=timezone.utc)
            s = str(v).replace("Z", "+00:00")
            return datetime.fromisoformat(s)
        except (ValueError, TypeError, OSError):
            return None

    out: list[dict[str, Any]] = []
    for r in rows:
        dt = _parse_ts(r)
        if dt is None or dt >= cutoff:
            out.append(r)
    return out


def user_real_account_forbidden(user: User | None, account_type: str | None) -> bool:
    if account_type != "real":
        return False
    return not tier_caps(effective_tier(user)).real_money


def unrestricted_features_payload() -> dict[str, Any]:
    """File / env legacy login — treat as full access for backwards compatibility."""
    return {
        "tier": "legacy",
        "tier_stored": "legacy",
        "tier_display": "Legacy",
        "agents_limit": None,
        "agents_limited": False,
        "allowed_agent_symbols": None,
        "ai_insights": True,
        "backtest": True,
        "portfolio_full": True,
        "portfolio_advanced": True,
        "dca": True,
        "grid": True,
        "real_money": True,
        "history_days": None,
        "onboarding_complete": True,
        "price_monthly": 0,
        "trial": {"active": False, "promo_tier": None, "ends_at": None},
    }
