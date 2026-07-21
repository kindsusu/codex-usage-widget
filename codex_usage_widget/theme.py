"""Immutable color, spacing, and meter tokens for the native widget."""

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final, TypeAlias

from codex_usage_widget.config import ThemeName

Rgb: TypeAlias = tuple[int, int, int]
_METER_LOW: Final[Rgb] = (166, 227, 161)
_METER_MID: Final[Rgb] = (249, 226, 175)
_METER_HIGH: Final[Rgb] = (243, 139, 168)
_METER_MIDPOINT: Final = 50.0


@dataclass(frozen=True, slots=True)
class ThemeTokens:
    """One complete theme resolved from the design-system contract."""

    surface_primary: str
    surface_secondary: str
    text_primary: str
    text_secondary: str
    text_muted: str
    accent_primary: str
    bar_background: str
    control_default: str
    control_hover: str
    control_surface_hover: str
    control_surface_pressed: str
    focus_ring: str
    tooltip_surface: str
    tooltip_text: str
    status_error: str
    meter_low: str = "#a6e3a1"
    meter_mid: str = "#f9e2af"
    meter_high: str = "#f38ba8"
    meter_text_on_fill: str = "#111827"
    mini_secondary: str = "#89b4fa"
    mini_icon_asset: str = "codex-color.png"
    # Near-white transparent color key (LWA_COLORKEY) for the floating mini
    # strip in BOTH themes: anti-aliased battery/text fringe blends toward
    # white, staying invisible over light desktops instead of showing a halo.
    mini_background_key: str = "#fdfdfb"
    # Codex-brand battery palette. Fills are shared across themes; the floating
    # S/W label glyphs get theme-specific tones for legibility on each backdrop.
    mini_session_fill: str = "#7fd8bb"
    mini_weekly_fill: str = "#8ad3e6"
    mini_low_fill: str = "#f38ba8"
    mini_session_label: str = "#10a37f"
    mini_weekly_label: str = "#0e7490"
    font_family: str = "Segoe UI"
    space_1: int = 2
    space_2: int = 4
    space_3: int = 6
    space_5: int = 10
    row_gap: int = 6
    bar_width: int = 220
    bar_height: int = 8
    pet_size: int = 20
    pet_canvas_size: int = 24
    control_size: int = 20
    control_icon_size: int = 14
    # iPhone-style mini battery geometry (base pixels; two groups pitched apart).
    mini_first_body_x: int = 20
    mini_group_pitch: int = 74
    mini_battery_top: int = 10
    mini_battery_width: int = 48
    mini_battery_height: int = 20
    mini_battery_corner_radius: int = 6
    mini_battery_inset: int = 3
    mini_nub_width: int = 4
    mini_nub_height: int = 10
    mini_label_gap: int = 5
    mini_label_px: int = 12
    mini_width: int = 156
    mini_height: int = 40
    full_width: int = 276


_LIGHT: Final = ThemeTokens(
    surface_primary="#f4f3ee",
    surface_secondary="#e8e7e1",
    text_primary="#111827",
    text_secondary="#4b5563",
    text_muted="#5f6672",
    accent_primary="#1d4ed8",
    bar_background="#e5e3dc",
    control_default="#52606d",
    control_hover="#111827",
    control_surface_hover="#e8e7e1",
    control_surface_pressed="#d8d6cd",
    focus_ring="#1d4ed8",
    tooltip_surface="#111827",
    tooltip_text="#f9fafb",
    status_error="#b42318",
)
_DARK: Final = ThemeTokens(
    surface_primary="#1e1e2e",
    surface_secondary="#2a2b3d",
    text_primary="#cdd6f4",
    text_secondary="#b8bfd8",
    text_muted="#a3aac2",
    accent_primary="#89b4fa",
    bar_background="#313244",
    control_default="#aeb6cf",
    control_hover="#cdd6f4",
    control_surface_hover="#2a2b3d",
    control_surface_pressed="#383a52",
    focus_ring="#89b4fa",
    tooltip_surface="#e5e7eb",
    tooltip_text="#181825",
    status_error="#ff9aae",
    mini_icon_asset="codex-color-dark.png",
    mini_session_label="#7fd8bb",
    mini_weekly_label="#8ad3e6",
)
_THEMES: Final[Mapping[ThemeName, ThemeTokens]] = MappingProxyType(
    {ThemeName.LIGHT: _LIGHT, ThemeName.DARK: _DARK},
)


def theme_tokens(theme: ThemeName) -> ThemeTokens:
    """Return the immutable token set for a configured theme."""
    return _THEMES[theme]


def meter_color(used_percent: float) -> str:
    """Interpolate the semantic green-to-yellow-to-red usage color."""
    clamped = max(0.0, min(100.0, used_percent))
    if clamped <= _METER_MIDPOINT:
        color = _interpolate(
            _METER_LOW,
            _METER_MID,
            clamped / _METER_MIDPOINT,
        )
    else:
        color = _interpolate(
            _METER_MID,
            _METER_HIGH,
            (clamped - _METER_MIDPOINT) / _METER_MIDPOINT,
        )
    return f"#{color[0]:02x}{color[1]:02x}{color[2]:02x}"


def _interpolate(start: Rgb, end: Rgb, amount: float) -> Rgb:
    return (
        round(start[0] + (end[0] - start[0]) * amount),
        round(start[1] + (end[1] - start[1]) * amount),
        round(start[2] + (end[2] - start[2]) * amount),
    )
