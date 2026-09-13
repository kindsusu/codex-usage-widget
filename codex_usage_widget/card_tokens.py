"""Isolated design tokens for the approved desktop usage cards."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal, TypeAlias

from codex_usage_widget.config import ThemeName

Severity: TypeAlias = Literal["green", "amber", "red"]
_DANGER_REMAINING: Final = 20.0
_WARNING_REMAINING: Final = 50.0


@dataclass(frozen=True, slots=True)
class CardPalette:
    """Colors shared by the full and mini desktop card renderers."""

    surface: tuple[int, int, int, int]
    mini_surface: tuple[int, int, int, int]
    surface_solid: str
    text: str
    muted: str
    line: tuple[int, int, int, int]
    track: str
    green: str
    amber: str
    red: str
    hover: tuple[int, int, int, int]
    shadow: tuple[int, int, int, int]
    background_key: str = "#fdfdfb"


@dataclass(frozen=True, slots=True)
class CardMetrics:
    """CSS-pixel geometry from the approved desktop proposal."""

    full_width: int = 280
    full_height: int = 156
    mini_width: int = 244
    mini_height: int = 46
    full_padding: int = 16
    full_radius: int = 14
    mini_radius: int = 10
    brand_size: int = 26
    brand_radius: int = 8
    brand_glyph_size: int = 16
    mini_glyph_size: int = 14
    full_track_height: int = 6
    mini_track_height: int = 4
    restore_size: int = 28
    status_extra_height: int = 22


CARD_METRICS: Final = CardMetrics()

_LIGHT: Final = CardPalette(
    surface=(255, 255, 255, 240),
    mini_surface=(255, 255, 255, 148),
    surface_solid="#ffffff",
    text="#172033",
    muted="#5e6b7d",
    line=(36, 49, 70, 36),
    track="#dfe6ef",
    green="#18864b",
    amber="#c27612",
    red="#c53532",
    hover=(27, 43, 68, 20),
    shadow=(29, 43, 65, 41),
)
_DARK: Final = CardPalette(
    surface=(29, 37, 51, 245),
    mini_surface=(20, 27, 39, 148),
    surface_solid="#1d2533",
    text="#f3f6fb",
    muted="#aeb8c7",
    line=(231, 237, 247, 38),
    track="#3a4558",
    green="#47c77d",
    amber="#e6a842",
    red="#ff716c",
    hover=(255, 255, 255, 23),
    shadow=(0, 0, 0, 97),
)


def card_palette(theme: ThemeName | bool) -> CardPalette:
    """Resolve card colors from a theme name or a light-theme flag."""
    light = theme if isinstance(theme, bool) else theme is ThemeName.LIGHT
    return _LIGHT if light else _DARK


def remaining_severity(remaining_percent: float) -> Severity:
    """Map remaining capacity to the approved semantic thresholds."""
    if remaining_percent <= _DANGER_REMAINING:
        return "red"
    if remaining_percent <= _WARNING_REMAINING:
        return "amber"
    return "green"


def severity_color(palette: CardPalette, remaining_percent: float) -> str:
    """Return the theme-aware color for remaining capacity."""
    severity = remaining_severity(remaining_percent)
    if severity == "red":
        return palette.red
    if severity == "amber":
        return palette.amber
    return palette.green
