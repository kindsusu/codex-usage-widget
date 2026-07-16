# pyright: reportUnknownArgumentType=false, reportUnknownMemberType=false
"""Theme-aware rendering for user-provided compact icon assets."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final, Literal, TypeAlias

from PIL import Image, ImageTk

from codex_usage_widget.assets import ASSET_ROOT

IconName: TypeAlias = Literal["theme", "opacity", "mini", "close"]


@dataclass(frozen=True, slots=True)
class IconAppearance:
    """Theme color, state variant, and title-matched icon dimensions."""

    color: str
    filled: bool
    canvas_size: int
    glyph_size: int


@dataclass(frozen=True, slots=True)
class _IconAssetPair:
    line: str
    fill: str


IconFallback: TypeAlias = Callable[[tk.Canvas, IconAppearance], None]
_ICON_ASSETS: Final[Mapping[IconName, _IconAssetPair]] = MappingProxyType(
    {
        "theme": _IconAssetPair("moon_stars_line.png", "moon_stars_fill.png"),
        "opacity": _IconAssetPair("drop_line.png", "drop_fill.png"),
        "mini": _IconAssetPair("scale_line.png", "scale_fill.png"),
    }
)


def icon_asset_name(icon: IconName, *, filled: bool) -> str | None:
    """Return the user-provided raster asset selected for an icon state."""
    pair = _ICON_ASSETS.get(icon)
    if pair is None:
        return None
    return pair.fill if filled else pair.line


def draw_icon(
    canvas: tk.Canvas,
    icon: IconName,
    appearance: IconAppearance,
) -> ImageTk.PhotoImage | None:
    """Draw a title-sized provided asset or a standard vector fallback."""
    name = icon_asset_name(icon, filled=appearance.filled)
    if name is not None:
        photo = _asset_photo(canvas, name, appearance)
        if photo is not None:
            center = appearance.canvas_size / 2
            _ = canvas.create_image(center, center, image=photo)
            return photo
    fallback = _FALLBACKS.get(icon)
    if fallback is not None:
        fallback(canvas, appearance)
    return None


def _asset_photo(
    canvas: tk.Canvas,
    name: str,
    appearance: IconAppearance,
) -> ImageTk.PhotoImage | None:
    try:
        with Image.open(ASSET_ROOT / "icon" / name, formats=("PNG",)) as source:
            if source.size != (24, 24):
                return None
            alpha = (
                source.convert("RGBA")
                .getchannel("A")
                .resize(
                    (appearance.glyph_size, appearance.glyph_size),
                    Image.Resampling.LANCZOS,
                )
            )
    except (OSError, SyntaxError, Image.DecompressionBombError):
        return None
    color = appearance.color
    rgb = tuple(int(color[index : index + 2], 16) for index in (1, 3, 5))
    tinted = Image.new(
        "RGBA",
        (appearance.glyph_size, appearance.glyph_size),
        (*rgb, 0),
    )
    tinted.putalpha(alpha)
    return ImageTk.PhotoImage(tinted, master=canvas)


def _draw_close(canvas: tk.Canvas, appearance: IconAppearance) -> None:
    center = appearance.canvas_size / 2
    half = appearance.glyph_size * 0.36
    width = max(1.5, appearance.glyph_size / 8)
    _ = canvas.create_line(
        center - half,
        center - half,
        center + half,
        center + half,
        fill=appearance.color,
        width=width,
        capstyle=tk.ROUND,
    )
    _ = canvas.create_line(
        center + half,
        center - half,
        center - half,
        center + half,
        fill=appearance.color,
        width=width,
        capstyle=tk.ROUND,
    )


_FALLBACKS: Final[Mapping[IconName, IconFallback]] = MappingProxyType(
    {"close": _draw_close}
)
