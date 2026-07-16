"""Convert rate-limit snapshots into privacy-safe Korean display text."""

from dataclasses import dataclass
from datetime import datetime
from typing import Final

from codex_usage_widget.models import CreditStatus, UsageSnapshot, UsageWindow
from codex_usage_widget.theme import meter_color

_SECONDS_PER_MINUTE: Final = 60
_MINUTES_PER_DAY: Final = 1_440
_FIVE_HOUR_MINUTES: Final = 300
_WEEKLY_MINUTES: Final = 10_080
_SECONDS_PER_HOUR: Final = 3_600
_SECONDS_PER_DAY: Final = 86_400
_PLAN_TITLES: Final[dict[str | None, str]] = {
    None: "Codex",
    "plus": "Codex Plus",
    "pro": "Codex Pro",
}


@dataclass(frozen=True, slots=True)
class UsageRowViewModel:
    """All display values required to render one usage row."""

    window: UsageWindow
    label: str
    percent_text: str
    reset_text: str
    meter_color: str


@dataclass(frozen=True, slots=True)
class SnapshotViewModel:
    """Ordered full and mini display values for one snapshot."""

    rows: tuple[UsageRowViewModel, ...]
    mini_rows: tuple[UsageRowViewModel, ...]
    credits_text: str
    title: str
    status_text: str


def window_label(window: UsageWindow) -> str:
    """Derive a Korean limit label exclusively from its duration."""
    duration = window.window_duration_mins
    if duration == _FIVE_HOUR_MINUTES:
        return "5시간 한도"
    if duration == _WEEKLY_MINUTES:
        return "주간 한도"
    return f"{_duration_text(duration)} 한도"


def reset_detail(window: UsageWindow, now: datetime) -> str:
    """Describe reset proximity relative to the injected current time."""
    remaining_seconds = int((window.resets_at - now).total_seconds())
    if remaining_seconds <= 0:
        return "초기화 예정 시각 지남"
    if remaining_seconds < _SECONDS_PER_MINUTE:
        return "1분 이내 초기화"
    total_minutes = remaining_seconds // _SECONDS_PER_MINUTE
    days, minutes_after_days = divmod(total_minutes, _MINUTES_PER_DAY)
    hours, minutes = divmod(minutes_after_days, _SECONDS_PER_MINUTE)
    if days > 0:
        detail = f"{days}일"
        if hours > 0:
            detail = f"{detail} {hours}시간"
        return f"{detail} 후 초기화"
    if hours > 0:
        detail = f"{hours}시간"
        if minutes > 0:
            detail = f"{detail} {minutes}분"
        return f"{detail} 후 초기화"
    return f"{minutes}분 후 초기화"


def ordered_windows(windows: tuple[UsageWindow, ...]) -> tuple[UsageWindow, ...]:
    """Order actual windows by duration while preserving equal-duration order."""
    return tuple(sorted(windows, key=lambda window: window.window_duration_mins))


def mini_windows(windows: tuple[UsageWindow, ...]) -> tuple[UsageWindow, ...]:
    """Select at most two actual windows for the compact strip."""
    return ordered_windows(windows)[:2]


def percent_text(used_percent: float) -> str:
    """Format a percentage without visually noisy trailing zeroes."""
    return f"{used_percent:.1f}".rstrip("0").rstrip(".") + "%"


def credits_footer(
    credit_status: CreditStatus | None,
    reset_credit_count: int | None,
) -> str:
    """Combine only available, non-identity credit information."""
    parts: list[str] = []
    if credit_status is not None:
        parts.append(_credit_text(credit_status))
    if reset_credit_count is not None:
        parts.append(f"초기화권 {reset_credit_count}개")
    return " · ".join(parts)


def fetched_status(fetched_at: datetime, now: datetime) -> str:
    """Format a privacy-safe relative refresh status for the widget footer."""
    elapsed_seconds = max(0, int((now - fetched_at).total_seconds()))
    if elapsed_seconds < _SECONDS_PER_MINUTE:
        return "방금 업데이트"
    if elapsed_seconds < _SECONDS_PER_HOUR:
        return f"{elapsed_seconds // _SECONDS_PER_MINUTE}분 전 업데이트"
    if elapsed_seconds < _SECONDS_PER_DAY:
        return f"{elapsed_seconds // _SECONDS_PER_HOUR}시간 전 업데이트"
    return f"{elapsed_seconds // _SECONDS_PER_DAY}일 전 업데이트"


def present_snapshot(snapshot: UsageSnapshot, now: datetime) -> SnapshotViewModel:
    """Build deterministic full and mini rows for an immutable snapshot."""
    rows = tuple(
        _present_window(window, now) for window in ordered_windows(snapshot.windows)
    )
    return SnapshotViewModel(
        rows=rows,
        mini_rows=rows[:2],
        credits_text=credits_footer(snapshot.credits, snapshot.reset_credit_count),
        title=_PLAN_TITLES.get(snapshot.plan_type, "Codex"),
        status_text=fetched_status(snapshot.fetched_at, now),
    )


def _present_window(window: UsageWindow, now: datetime) -> UsageRowViewModel:
    return UsageRowViewModel(
        window=window,
        label=window_label(window),
        percent_text=percent_text(window.used_percent),
        reset_text=reset_detail(window, now),
        meter_color=meter_color(window.used_percent),
    )


def _duration_text(duration_minutes: int) -> str:
    days, minutes_after_days = divmod(duration_minutes, _MINUTES_PER_DAY)
    hours, minutes = divmod(minutes_after_days, _SECONDS_PER_MINUTE)
    parts: list[str] = []
    if days > 0:
        parts.append(f"{days}일")
    if hours > 0:
        parts.append(f"{hours}시간")
    if minutes > 0:
        parts.append(f"{minutes}분")
    return " ".join(parts)


def _credit_text(credit_status: CreditStatus) -> str:
    if credit_status.unlimited:
        return "크레딧 무제한"
    if not credit_status.has_credits:
        return "크레딧 없음"
    if credit_status.balance is not None:
        return f"크레딧 {credit_status.balance}"
    return "크레딧 사용 가능"
