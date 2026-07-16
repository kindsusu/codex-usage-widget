"""Korean display copy for the native widget surface."""

from __future__ import annotations

from datetime import UTC
from typing import TYPE_CHECKING

from codex_usage_widget.service import RefreshStatus, WidgetState, failure_message

if TYPE_CHECKING:
    from codex_usage_widget.presentation import SnapshotViewModel


def empty_text(state: WidgetState) -> str:
    """Return one actionable loading or failure message for the body."""
    if state.failure is not None:
        return failure_message(state.failure)
    return "Codex 사용량을 확인하는 중…"


def footer_text(view_model: SnapshotViewModel | None, state: WidgetState) -> str:
    """Return status metadata without repeating the body failure message."""
    if state.status is RefreshStatus.LOADING:
        return "잠시만 기다려 주세요"
    last_success = _last_success(state)
    if state.failure is not None:
        retry = "Ctrl+R로 다시 시도"
        return f"{last_success} · {retry}" if last_success else retry
    credit_text = "" if view_model is None else view_model.credits_text
    if state.status is RefreshStatus.REFRESHING:
        status = "새로고침 중…"
    else:
        status = "최신 상태" if view_model is None else view_model.status_text
    return f"{status} · {credit_text}" if credit_text else status


def short_label(label: str) -> str:
    """Condense a limit label for the mini strip."""
    return label.removesuffix(" 한도").replace("시간", "h").replace("주간", "W")


def _last_success(state: WidgetState) -> str:
    if state.snapshot is None:
        return ""
    local_time = state.snapshot.fetched_at.astimezone(UTC).astimezone()
    return f"마지막 확인 {local_time:%H:%M}"
