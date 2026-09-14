from __future__ import annotations

import io
from datetime import UTC, datetime, timedelta, timezone
from typing import cast, final

import codex_usage_widget.icons as icons
import codex_usage_widget.mini_view as mini_view
from PIL import Image

from codex_usage_widget.assets import ASSET_ROOT, load_mini_icon_png
from codex_usage_widget.config import ThemeName
from codex_usage_widget.models import UsageSnapshot
from codex_usage_widget.service import FailureKind, RefreshStatus, WidgetState
from codex_usage_widget.theme import theme_tokens
from codex_usage_widget.menus import opacity_from_position
from codex_usage_widget.mini_view import (
    BindingCallback,
    BindingTarget,
    RestoreBindingGroup,
)
from codex_usage_widget.view_text import empty_text, footer_text, short_label
from codex_usage_widget.widgets import action_control_background


def test_header_actions_use_provided_svg_icon_assets() -> None:
    assert icons.icon_asset_name("theme", filled=False) == "moon_stars_line.png"
    assert icons.icon_asset_name("theme", filled=True) == "moon_stars_fill.png"
    assert icons.icon_asset_name("opacity", filled=False) == "drop_line.png"
    assert icons.icon_asset_name("opacity", filled=True) == "drop_fill.png"
    assert icons.icon_asset_name("mini", filled=False) == "scale_line.png"
    assert icons.icon_asset_name("mini", filled=True) == "scale_fill.png"
    assert icons.icon_asset_name("close", filled=False) is None


def test_weekly_mini_label_uses_an_english_abbreviation() -> None:
    assert short_label("주간 한도") == "W"


def test_provided_icon_rasters_are_transparent_24px_masks() -> None:
    names = (
        "moon_stars_line.png",
        "moon_stars_fill.png",
        "drop_line.png",
        "drop_fill.png",
        "scale_line.png",
        "scale_fill.png",
    )
    for name in names:
        with Image.open(ASSET_ROOT / "icon" / name, formats=("PNG",)) as image:
            alpha = image.getchannel("A")
            assert image.size == (24, 24)
            assert alpha.getbbox() is not None
            assert alpha.getextrema() == (0, 255)


def _relative_luminance(color: str) -> float:
    channels = tuple(int(color[index : index + 2], 16) / 255 for index in (1, 3, 5))

    def linear(channel: float) -> float:
        return (
            channel / 12.92
            if channel <= 0.04045
            else ((channel + 0.055) / 1.055) ** 2.4
        )

    red, green, blue = (linear(channel) for channel in channels)
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def _contrast(first: str, second: str) -> float:
    high, low = sorted(
        (_relative_luminance(first), _relative_luminance(second)), reverse=True
    )
    return (high + 0.05) / (low + 0.05)


def test_secondary_muted_error_and_control_colors_are_legible() -> None:
    for name in (ThemeName.LIGHT, ThemeName.DARK):
        tokens = theme_tokens(name)
        for color in (tokens.text_secondary, tokens.text_muted, tokens.status_error):
            assert _contrast(color, tokens.surface_primary) >= 4.5
        assert _contrast(tokens.control_default, tokens.surface_primary) >= 3.0
        assert _contrast(tokens.focus_ring, tokens.surface_primary) >= 3.0


def test_action_controls_are_transparent_until_interaction() -> None:
    tokens = theme_tokens(ThemeName.LIGHT)

    assert action_control_background(tokens, "idle") == tokens.surface_primary
    assert action_control_background(tokens, "hover") == tokens.control_surface_hover
    assert (
        action_control_background(tokens, "pressed") == tokens.control_surface_pressed
    )


def test_failure_body_is_actionable_and_footer_is_not_a_duplicate() -> None:
    state = WidgetState(
        snapshot=None,
        status=RefreshStatus.ERROR,
        refresh_in_flight=False,
        failure=FailureKind.LOGIN_REQUIRED,
    )

    body = empty_text(state)
    footer = footer_text(None, state)

    assert body == "Codex에 로그인한 뒤 다시 시도하세요."
    assert footer == "우클릭하여 새로고침"
    assert body != footer


def _stale_state(fetched_at: datetime) -> WidgetState:
    return WidgetState(
        snapshot=UsageSnapshot((), None, None, fetched_at),
        status=RefreshStatus.STALE,
        refresh_in_flight=False,
        failure=FailureKind.UNAVAILABLE,
    )


def test_stale_footer_includes_last_success_time_and_retry_hint() -> None:
    # Given -- one instant, tagged two ways. The footer renders the reader's
    # local wall clock, so the expected time is derived the same way instead of
    # being pinned to whichever zone this machine happens to run in.
    fetched_at = datetime(2026, 7, 16, 5, 34, tzinfo=UTC)
    elsewhere = fetched_at.astimezone(timezone(timedelta(hours=-4)))
    expected = f"마지막 확인 {fetched_at.astimezone():%H:%M} · 우클릭하여 새로고침"

    # When
    footer = footer_text(None, _stale_state(fetched_at))
    same_instant = footer_text(None, _stale_state(elsewhere))

    # Then
    assert footer == expected
    # Normalizing to the instant, not to the naive wall clock, is the behavior
    # under test: the same moment must read identically whatever zone tags it.
    assert same_instant == footer
    assert elsewhere.hour != fetched_at.hour
    assert footer.startswith("마지막 확인 ")
    assert footer.endswith(" · 우클릭하여 새로고침")


def test_opacity_slider_maps_track_positions_to_supported_range() -> None:
    assert opacity_from_position(-10, 140) == 0.3
    assert opacity_from_position(70, 140) == 0.65
    assert opacity_from_position(160, 140) == 1.0


def test_mini_battery_remaining_and_percentage_text_stay_legible() -> None:
    tokens = theme_tokens(ThemeName.DARK)

    # Remaining is the clamped inverse of used capacity.
    assert mini_view.mini_remaining_percent(-8.0) == 100.0
    assert mini_view.mini_remaining_percent(25.0) == 75.0
    assert mini_view.mini_remaining_percent(120.0) == 0.0
    # Centered text flips to the on-fill color once the fill covers the middle.
    assert mini_view.mini_battery_text_color(49.0, tokens) == tokens.text_primary
    assert mini_view.mini_battery_text_color(50.0, tokens) == tokens.meter_text_on_fill


def test_mini_battery_fill_pixels_floors_a_visible_sliver() -> None:
    # inner_width = body_width(48) - 2 * inset(3) = 42
    assert mini_view.mini_battery_fill_pixels(0.0, 42) == 0
    assert mini_view.mini_battery_fill_pixels(-8.0, 42) == 0
    assert mini_view.mini_battery_fill_pixels(50.0, 42) == 21
    assert mini_view.mini_battery_fill_pixels(120.0, 42) == 42
    # A near-empty charge still renders the minimum-visible floor.
    assert mini_view.mini_battery_fill_pixels(1.0, 42) == 3


def test_mini_battery_fill_turns_red_at_low_remaining() -> None:
    tokens = theme_tokens(ThemeName.DARK)
    session = tokens.mini_session_fill
    low = tokens.mini_low_fill

    assert mini_view.mini_battery_fill_color(20.1, session, low) == session
    assert mini_view.mini_battery_fill_color(20.0, session, low) == low
    assert mini_view.mini_battery_fill_color(0.0, session, low) == low


def test_mini_battery_style_maps_session_and_weekly_windows() -> None:
    dark = theme_tokens(ThemeName.DARK)
    light = theme_tokens(ThemeName.LIGHT)

    session = mini_view.mini_battery_style(300, dark)
    weekly = mini_view.mini_battery_style(10_080, dark)

    assert session.label == "S"
    assert session.base_fill == dark.mini_session_fill
    assert session.label_color == dark.mini_session_label
    assert weekly.label == "W"
    assert weekly.base_fill == dark.mini_weekly_fill
    assert weekly.label_color == dark.mini_weekly_label
    # Label glyph tone is theme-specific for legibility on each backdrop.
    assert mini_view.mini_battery_style(300, light).label_color == "#10a37f"
    assert mini_view.mini_battery_style(10_080, light).label_color == "#0e7490"


def test_mini_fill_box_keeps_equal_top_and_bottom_insets() -> None:
    body_x, body_y, body_height, inset = 20, 10, 20, 3

    box = mini_view.mini_fill_box(body_x, body_y, body_height, inset, fill_pixels=24)

    top_inset = box.top - body_y
    bottom_inset = (body_y + body_height) - (box.bottom - 1)
    assert top_inset == inset
    assert bottom_inset == inset
    assert top_inset == bottom_inset
    assert box.right - box.left == 24 + 1


def test_mini_label_image_is_hard_edged_with_binary_alpha() -> None:
    image = mini_view.render_label_image("W", "#8ad3e6", 12)

    alpha_values = set(image.getchannel("A").tobytes())
    assert image.mode == "RGBA"
    assert alpha_values <= {0, 255}
    assert 255 in alpha_values


def test_mini_codex_icons_have_no_tile_background() -> None:
    tokens = (theme_tokens(ThemeName.LIGHT), theme_tokens(ThemeName.DARK))

    for token in tokens:
        with Image.open(io.BytesIO(load_mini_icon_png(token.mini_icon_asset))) as image:
            pixel = cast(
                "tuple[int, int, int, int]",
                image.convert("RGBA").getpixel((32, 2)),
            )
            assert pixel[3] == 0


@final
class _FakeBindingTarget:
    def __init__(self, children: tuple[BindingTarget, ...] = ()) -> None:
        self._children = children
        self._handlers: dict[str, tuple[str, BindingCallback]] = {}
        self._next_id = 0

    def children(self) -> tuple[BindingTarget, ...]:
        return self._children

    def bind(self, sequence: str, callback: BindingCallback) -> str:
        self._next_id += 1
        binding_id = f"binding-{self._next_id}"
        self._handlers[sequence] = (binding_id, callback)
        return binding_id

    def unbind(self, sequence: str, binding_id: str) -> None:
        existing = self._handlers.get(sequence)
        if existing is not None and existing[0] == binding_id:
            del self._handlers[sequence]

    @property
    def sequences(self) -> frozenset[str]:
        return frozenset(self._handlers)

    def invoke(self, sequence: str) -> str:
        return self._handlers[sequence][1]()


def test_mini_restore_binds_every_descendant_once_and_disposes_cleanly() -> None:
    leaf = _FakeBindingTarget()
    label = _FakeBindingTarget((leaf,))
    frame = _FakeBindingTarget((label,))
    restore_count = 0

    def restore() -> None:
        nonlocal restore_count
        restore_count += 1

    bindings = RestoreBindingGroup(frame, restore)

    for target in (frame, label, leaf):
        assert target.sequences == {"<Double-Button-1>", "<ButtonRelease-1>"}
    assert leaf.invoke("<ButtonRelease-1>") == "break"
    assert label.invoke("<Double-Button-1>") == "break"
    assert frame.invoke("<Double-Button-1>") == "break"
    assert restore_count == 1

    bindings.dispose()

    assert all(not target.sequences for target in (frame, label, leaf))
