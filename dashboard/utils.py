"""Dashboard helpers: tier capabilities (wrappers around ``core.tier_access``)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.tier_access import effective_tier, feature_allowed, features_payload, tier_caps

if TYPE_CHECKING:
    from core.models import User


def get_user_features(user: User | None) -> dict[str, Any]:
    """Resolved features for API/session (includes active Pro trial)."""
    return features_payload(user)


def check_feature_access(user: User | None, feature_name: str) -> bool:
    """Whether ``feature_name`` is allowed for this user's effective tier."""
    return feature_allowed(user, feature_name)


def check_agent_limit(user: User | None, current_agent_count: int) -> bool:
    """True if tier allows another agent given ``current_agent_count`` already configured."""
    caps = tier_caps(effective_tier(user))
    limit = caps.agents_limit
    if limit is None:
        return True
    return current_agent_count < limit
