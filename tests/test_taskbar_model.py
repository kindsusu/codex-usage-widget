from datetime import UTC, datetime, timedelta

import pytest

from codex_usage_widget.models import UsageSnapshot, UsageWindow
from codex_usage_widget.service import FailureKind, RefreshStatus, WidgetState
from codex_usage_widget.taskbar_model import build_taskbar_model

NOW = datetime(2026, 9, 13, 12, tzinfo=UTC)


def _window(duration: int, used: float) -> UsageWindow:
    return UsageWindow("id", None, used, duration, NOW + timedelta(hours=2))


def test_orders_actual_windows_and_formats_remaining_values() -> None:
    snapshot = UsageSnapshot(
        (_window(10_080, 20.25), _window(300, 99.96), _window(60, 50)),
        None,
        None,
        NOW,
    )
    state = WidgetState(snapshot, RefreshStatus.FRESH, False, None)

    model = build_taskbar_model(state, NOW)

    assert tuple(row.label for row in model.rows) == ("1h", "5h")
    assert model.rows[0].percent_text == "50%"
    assert model.rows[1].remaining_percent == pytest.approx(0.04)
    assert model.rows[1].percent_text == "0%"


def test_unavailable_state_does_not_invent_zero_rows() -> None:
    state = WidgetState(None, RefreshStatus.ERROR, False, FailureKind.UNAVAILABLE)

    model = build_taskbar_model(state, NOW)

    assert model.rows == ()
    assert model.status_text == "사용 불가"
    assert model.error_text is not None


def test_stale_snapshot_preserves_rows_and_marks_status() -> None:
    snapshot = UsageSnapshot((_window(300, 25),), None, None, NOW)
    state = WidgetState(
        snapshot,
        RefreshStatus.STALE,
        False,
        FailureKind.LOGIN_REQUIRED,
    )

    model = build_taskbar_model(state, NOW)

    assert model.stale
    assert model.rows[0].percent_text == "75%"
    assert model.status_text == "이전 값"
