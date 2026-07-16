"""Immutable usage-domain models."""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class UsageWindow:
    """One rate-limit window returned by Codex."""

    limit_id: str
    limit_name: str | None
    used_percent: float
    window_duration_mins: int
    resets_at: datetime


@dataclass(frozen=True, slots=True)
class CreditStatus:
    """Account credit availability reported with the rate limits."""

    has_credits: bool
    unlimited: bool
    balance: str | None


@dataclass(frozen=True, slots=True)
class UsageSnapshot:
    """Normalized immutable result of one rate-limit fetch."""

    windows: tuple[UsageWindow, ...]
    credits: CreditStatus | None
    reset_credit_count: int | None
    fetched_at: datetime
    plan_type: str | None = None
