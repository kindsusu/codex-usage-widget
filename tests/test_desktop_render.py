from datetime import UTC, datetime, timedelta
from typing import cast

from codex_usage_widget.card_tokens import card_palette, remaining_severity
from codex_usage_widget.desktop_render import (
    build_desktop_card_model,
    render_desktop_card,
)
from codex_usage_widget.models import UsageSnapshot, UsageWindow
from codex_usage_widget.presentation import present_snapshot
from codex_usage_widget.desktop_render import DesktopCardModel
from codex_usage_widget.service import FailureKind, RefreshStatus, WidgetState

NOW = datetime(2026, 9, 14, tzinfo=UTC)


def _state(*, failure: FailureKind | None = None) -> WidgetState:
    snapshot = UsageSnapshot(
        windows=(
            UsageWindow("session", None, 28, 300, NOW + timedelta(hours=2)),
            UsageWindow("weekly", None, 62, 10_080, NOW + timedelta(days=3)),
        ),
        credits=None,
        reset_credit_count=None,
        fetched_at=NOW,
        plan_type="plus",
    )
    return WidgetState(
        snapshot,
        RefreshStatus.STALE if failure else RefreshStatus.FRESH,
        False,
        failure,
    )


def _model(state: WidgetState) -> DesktopCardModel:
    assert state.snapshot is not None
    return build_desktop_card_model(present_snapshot(state.snapshot, NOW), state)


def test_desktop_model_uses_actual_windows_and_remaining_capacity() -> None:
    model = _model(_state())
    assert model.plan == "Plus"
    assert tuple(row.label for row in model.rows) == ("5시간 한도", "주간 한도")
    assert tuple(row.percent_text for row in model.rows) == ("72%", "38%")


def test_remaining_severity_matches_approved_thresholds() -> None:
    assert remaining_severity(20.0) == "red"
    assert remaining_severity(20.1) == "amber"
    assert remaining_severity(50.0) == "amber"
    assert remaining_severity(50.1) == "green"


def test_full_and_mini_render_exact_css_sizes_at_100_and_150_percent() -> None:
    model = _model(_state())
    full = render_desktop_card(model, mode="full", light_theme=True)
    full_150 = render_desktop_card(model, mode="full", light_theme=False, scale=1.5)
    mini = render_desktop_card(model, mode="mini", light_theme=True)
    mini_150 = render_desktop_card(model, mode="mini", light_theme=False, scale=1.5)
    assert full.image.size == (280, 156)
    assert full_150.image.size == (420, 234)
    assert mini.image.size == (244, 46)
    assert mini_150.image.size == (366, 69)
    assert full.image.mode == mini.image.mode == "RGBA"


def test_track_centers_are_solid_approved_colors_without_resampling_tails() -> None:
    rendered = render_desktop_card(_model(_state()), mode="full", light_theme=True)
    palette = card_palette(True)
    assert cast("tuple[int, int, int, int]", rendered.image.getpixel((20, 89)))[:3] == (
        24,
        134,
        75,
    )
    assert cast("tuple[int, int, int, int]", rendered.image.getpixel((250, 89)))[
        :3
    ] == (223, 230, 239)
    assert cast("tuple[int, int, int, int]", rendered.image.getpixel((20, 135)))[
        :3
    ] == (194, 118, 18)
    assert palette.green == "#18864b"


def test_status_state_grows_only_full_card_and_remains_privacy_safe() -> None:
    state = _state(failure=FailureKind.UNAVAILABLE)
    model = _model(state)
    full = render_desktop_card(model, mode="full", light_theme=True)
    mini = render_desktop_card(model, mode="mini", light_theme=True)
    assert model.status_text == "Codex 사용량을 불러올 수 없습니다."
    assert full.image.size == (280, 178)
    assert mini.image.size == (244, 46)


def test_hit_regions_scale_with_the_rendered_pixels() -> None:
    model = _model(_state())
    full = render_desktop_card(model, mode="full", light_theme=True, scale=1.5)
    mini = render_desktop_card(model, mode="mini", light_theme=True, scale=1.5)
    assert full.hit_regions.brand is not None
    assert full.hit_regions.brand.contains(30, 30)
    assert full.hit_regions.mode.contains(320, 35)
    assert mini.hit_regions.brand is None
    assert mini.hit_regions.mode.contains(330, 30)


def test_full_card_keeps_additional_actual_windows_and_grows_per_row() -> None:
    state = _state()
    assert state.snapshot is not None
    third = UsageWindow("daily", None, 10, 1_440, NOW + timedelta(days=1))
    snapshot = UsageSnapshot(
        (*state.snapshot.windows, third),
        None,
        None,
        NOW,
        "plus",
    )
    expanded = WidgetState(snapshot, RefreshStatus.FRESH, False, None)
    model = build_desktop_card_model(present_snapshot(snapshot, NOW), expanded)

    full = render_desktop_card(model, mode="full", light_theme=True)
    mini = render_desktop_card(model, mode="mini", light_theme=True)

    assert len(model.rows) == 3
    assert full.image.size == (280, 202)
    assert mini.image.size == (244, 46)


def test_rounded_card_corners_remain_fully_transparent() -> None:
    rendered = render_desktop_card(_model(_state()), mode="full", light_theme=False)

    assert rendered.image.getpixel((0, 0)) == (0, 0, 0, 0)
