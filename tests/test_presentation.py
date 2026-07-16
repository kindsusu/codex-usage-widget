from datetime import UTC, datetime, timedelta

from codex_usage_widget.models import CreditStatus, UsageSnapshot, UsageWindow
from codex_usage_widget.presentation import (
    credits_footer,
    fetched_status,
    mini_windows,
    ordered_windows,
    percent_text,
    present_snapshot,
    reset_detail,
    window_label,
)

NOW = datetime(2026, 7, 16, 12, 0, tzinfo=UTC)


def _window(
    duration: int,
    *,
    used: float = 20.0,
    reset_delta: timedelta | None = None,
    limit_id: str = "codex",
    limit_name: str | None = None,
) -> UsageWindow:
    effective_delta = timedelta(hours=1) if reset_delta is None else reset_delta
    return UsageWindow(
        limit_id=limit_id,
        limit_name=limit_name,
        used_percent=used,
        window_duration_mins=duration,
        resets_at=NOW + effective_delta,
    )


def test_window_label_is_derived_from_duration_not_position() -> None:
    # Given
    weekly = _window(10_080)
    five_hour = _window(300)

    # When / Then
    assert window_label(weekly) == "주간 한도"
    assert window_label(five_hour) == "5시간 한도"


def test_window_label_calculates_unknown_durations() -> None:
    # Given
    windows = (_window(45), _window(90), _window(2_880))

    # When
    labels = tuple(window_label(window) for window in windows)

    # Then
    assert labels == ("45분 한도", "1시간 30분 한도", "2일 한도")


def test_reset_detail_uses_the_injected_clock() -> None:
    # Given
    windows = (
        _window(300, reset_delta=timedelta(seconds=20)),
        _window(300, reset_delta=timedelta(hours=1, minutes=30)),
        _window(300, reset_delta=timedelta(days=2, hours=3)),
        _window(300, reset_delta=timedelta(seconds=-1)),
    )

    # When
    details = tuple(reset_detail(window, NOW) for window in windows)

    # Then
    assert details == (
        "1분 이내 초기화",
        "1시간 30분 후 초기화",
        "2일 3시간 후 초기화",
        "초기화 예정 시각 지남",
    )


def test_ordered_and_mini_windows_use_only_actual_windows() -> None:
    # Given
    weekly = _window(10_080, used=30.0)
    daily = _window(1_440, used=10.0)
    five_hour = _window(300, used=40.0)

    # When
    ordered = ordered_windows((weekly, daily, five_hour))
    mini = mini_windows((weekly, daily, five_hour))

    # Then
    assert ordered == (five_hour, daily, weekly)
    assert mini == (five_hour, daily)


def test_credits_footer_combines_only_available_credit_information() -> None:
    # Given
    credit_status = CreditStatus(
        has_credits=True,
        unlimited=False,
        balance="766.76",
    )

    # When
    footer = credits_footer(credit_status, reset_credit_count=3)

    # Then
    assert footer == "크레딧 766.76 · 초기화권 3개"
    assert credits_footer(None, reset_credit_count=None) == ""


def test_present_snapshot_produces_exact_text_and_dynamic_rows() -> None:
    # Given
    snapshot = UsageSnapshot(
        windows=(_window(10_080, used=19.0),),
        credits=None,
        reset_credit_count=None,
        fetched_at=NOW,
    )

    # When
    presented = present_snapshot(snapshot, NOW)

    # Then
    assert len(presented.rows) == 1
    assert presented.rows[0].label == "주간 한도"
    assert presented.rows[0].percent_text == "19%"
    assert presented.rows[0].reset_text == "1시간 후 초기화"
    assert presented.mini_rows == presented.rows
    assert presented.credits_text == ""


def test_percent_text_preserves_useful_precision() -> None:
    # Given / When / Then
    assert percent_text(19.0) == "19%"
    assert percent_text(19.25) == "19.2%"


def test_present_snapshot_titles_only_supported_paid_plans() -> None:
    # Given
    snapshots = tuple(
        UsageSnapshot(
            windows=(),
            credits=None,
            reset_credit_count=None,
            fetched_at=NOW,
            plan_type=plan_type,
        )
        for plan_type in ("plus", "pro", "business", None)
    )

    # When
    titles = tuple(present_snapshot(snapshot, NOW).title for snapshot in snapshots)

    # Then
    assert titles == ("Codex Plus", "Codex Pro", "Codex", "Codex")


def test_fetched_status_uses_injected_clock_without_exposing_timestamp() -> None:
    # Given
    fetched_at = NOW - timedelta(minutes=4, seconds=30)

    # When
    status = fetched_status(fetched_at, NOW)

    # Then
    assert status == "4분 전 업데이트"
