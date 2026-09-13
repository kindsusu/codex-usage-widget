"""Immutable presentation model for the embedded taskbar surface."""

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from codex_usage_widget.presentation import (
    ordered_windows,
    percent_text,
    reset_detail,
)
from codex_usage_widget.service import RefreshStatus, WidgetState, failure_message

_FIVE_HOURS = 300
_ONE_WEEK = 10_080

if TYPE_CHECKING:
    from codex_usage_widget.models import UsageWindow


@dataclass(frozen=True, slots=True)
class TaskbarRow:
    """One compact usage row."""

    label: str
    remaining_percent: float
    percent_text: str
    reset_text: str


@dataclass(frozen=True, slots=True)
class TaskbarModel:
    """All text and numeric data consumed by the native renderer."""

    rows: tuple[TaskbarRow, ...]
    title: str
    status_text: str
    error_text: str | None
    stale: bool


def build_taskbar_model(state: WidgetState, now: datetime) -> TaskbarModel:
    """Build a compact model without inventing unavailable limit values."""
    rows: tuple[TaskbarRow, ...] = ()
    title = "Codex"
    status_text = _status_text(state.status)
    if state.snapshot is not None:
        rows = tuple(
            _row(window, now)
            for window in ordered_windows(state.snapshot.windows)[:2]
        )
        plan_titles: dict[str | None, str] = {
            "plus": "Codex Plus",
            "pro": "Codex Pro",
        }
        title = plan_titles.get(state.snapshot.plan_type, "Codex")
    error_text = None if state.failure is None else failure_message(state.failure)
    return TaskbarModel(
        rows=rows,
        title=title,
        status_text=status_text,
        error_text=error_text,
        stale=state.status is RefreshStatus.STALE,
    )


def _row(window: "UsageWindow", now: datetime) -> TaskbarRow:
    remaining = max(0.0, min(100.0, 100.0 - window.used_percent))
    return TaskbarRow(
        label=_short_label(window.window_duration_mins),
        remaining_percent=remaining,
        percent_text=percent_text(remaining),
        reset_text=reset_detail(window, now),
    )


def _short_label(duration: int) -> str:
    if duration == _FIVE_HOURS:
        return "5h"
    if duration == _ONE_WEEK:
        return "주간"
    if duration % 1_440 == 0:
        return f"{duration // 1_440}d"
    if duration % 60 == 0:
        return f"{duration // 60}h"
    return f"{duration}m"


def _status_text(status: RefreshStatus) -> str:
    return {
        RefreshStatus.LOADING: "불러오는 중",
        RefreshStatus.REFRESHING: "업데이트 중",
        RefreshStatus.FRESH: "최신",
        RefreshStatus.STALE: "이전 값",
        RefreshStatus.ERROR: "사용 불가",
        RefreshStatus.SHUTDOWN: "종료됨",
    }[status]
