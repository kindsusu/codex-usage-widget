# pyright: reportAny=false, reportUnknownArgumentType=false, reportUnknownMemberType=false
"""Deterministic per-pixel-alpha renderer for the embedded taskbar surface."""

from __future__ import annotations

import io
from contextlib import suppress
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Final, Literal, TypeAlias

from PIL import Image, ImageChops, ImageDraw, ImageFont

from codex_usage_widget.assets import load_tray_png

if TYPE_CHECKING:
    from codex_usage_widget.taskbar_model import TaskbarModel, TaskbarRow

HoverRegion: TypeAlias = Literal["usage", "menu"]
_BASE_DPI: Final = 96
_SUPERSAMPLE: Final = 3
_MENU_WIDTH: Final = 38
_MENU_HEIGHT: Final = 44
_GAP: Final = 5
# Usage block columns: label | bar | right-aligned %. The bar ran 45..104
# (59px) until 2026-09-14, when the user asked for 80% of that length; it is
# now 47px and the severity colour carries the reading. The strip gave up the
# same 12px.
_BAR_LEFT: Final = 45
_BAR_WIDTH: Final = 47                  # 80% of the old 59
_PERCENT_WIDTH: Final = 42
_PAD_RIGHT: Final = 8
_USAGE_WIDTH: Final = _BAR_LEFT + _BAR_WIDTH + _PERCENT_WIDTH + _PAD_RIGHT
_HEIGHT: Final = 46
_MIN_FULL_WIDTH: Final = 113
_DANGER_REMAINING: Final = 20
_WARNING_REMAINING: Final = 50
_EMPTY_MESSAGES: Final = {
    "Codex 사용량을 불러올 수 없습니다.": "사용 불가",
    "Codex에 로그인한 뒤 다시 시도하세요.": "로그인 필요",
    "Codex 사용량 응답을 확인할 수 없습니다.": "응답 오류",
}
_RED_LIGHT: Final = "#c53532"
_RED_DARK: Final = "#ff716c"


@dataclass(frozen=True, slots=True)
class HitRegion:
    """One physical-pixel interaction rectangle."""

    left: int
    top: int
    right: int
    bottom: int


@dataclass(frozen=True, slots=True)
class TaskbarHitRegions:
    """Physical hit targets matching the rendered usage and menu buttons."""

    usage: HitRegion
    menu: HitRegion


def taskbar_hit_regions(width: int, height: int, dpi: int) -> TaskbarHitRegions:
    """Return DPI-scaled hit targets for native pointer routing.

    The Codex mark sits on the left and the usage block on its right
    (2026-09-14 user-approved layout change).
    """
    scale = max(_BASE_DPI, dpi) / _BASE_DPI
    menu_width = min(width, round(_MENU_WIDTH * scale))
    gap = min(max(0, width - menu_width), round(_GAP * scale))
    usage_left = menu_width + gap
    content_height = min(height, round(_HEIGHT * scale))
    top = max(0, (height - content_height) // 2)
    menu_height = min(content_height, round(_MENU_HEIGHT * scale))
    menu_top = top + (content_height - menu_height) // 2
    return TaskbarHitRegions(
        usage=HitRegion(usage_left, top, width, top + content_height),
        menu=HitRegion(0, menu_top, menu_width, menu_top + menu_height),
    )


def render_taskbar(  # noqa: PLR0913
    model: TaskbarModel,
    *,
    dpi: int,
    width: int,
    height: int,
    hover_region: HoverRegion | None = None,
    light_theme: bool = True,
    high_contrast: bool = False,
) -> Image.Image:
    """Render the approved taskbar design as straight-alpha RGBA pixels."""
    width = max(1, width)
    height = max(1, height)
    dpi = max(_BASE_DPI, dpi)
    factor = dpi / _BASE_DPI * _SUPERSAMPLE
    canvas = Image.new("RGBA", (width * _SUPERSAMPLE, height * _SUPERSAMPLE))
    draw = ImageDraw.Draw(canvas)
    regions = taskbar_hit_regions(width, height, dpi)
    palette = _palette(light_theme, high_contrast)
    if hover_region == "usage":
        _rounded(draw, regions.usage, factor, 7, palette.hover)
    if hover_region == "menu":
        _rounded(draw, regions.menu, factor, 7, palette.hover)
    _draw_usage(draw, model, regions.usage, factor, palette)
    _draw_menu(canvas, regions.menu, factor, palette, model)
    rendered = canvas.resize((width, height), Image.Resampling.LANCZOS)
    logical_width = (regions.usage.right - regions.usage.left) * _BASE_DPI / dpi
    if model.rows and logical_width >= _MIN_FULL_WIDTH:
        _redraw_tracks(rendered, model.rows[:2], regions.usage, dpi, palette)
    _ensure_hit_alpha(rendered, regions, dpi)
    return rendered


@dataclass(frozen=True, slots=True)
class _Palette:
    text: str
    muted: str
    track: str
    green: str
    amber: str
    red: str
    hover: tuple[int, int, int, int]


def _palette(light: bool, high_contrast: bool) -> _Palette:
    if high_contrast:
        color = "#000000" if light else "#ffffff"
        return _Palette(color, color, color, color, color, color, (127, 127, 127, 80))
    return _Palette(
        text="#172033" if light else "#f3f6fb",
        muted="#5e6b7d" if light else "#aeb8c7",
        track="#dfe6ef" if light else "#3a4558",
        green="#18864b" if light else "#47c77d",
        amber="#c27612" if light else "#e6a842",
        red=_RED_LIGHT if light else _RED_DARK,
        hover=(27, 43, 68, 20) if light else (255, 255, 255, 23),
    )


def _draw_usage(
    draw: ImageDraw.ImageDraw,
    model: TaskbarModel,
    region: HitRegion,
    factor: float,
    palette: _Palette,
) -> None:
    logical_width = (region.right - region.left) * _SUPERSAMPLE / factor
    rows = model.rows[:2]
    if not rows:
        message = model.error_text or model.status_text
        _center_text(
            draw,
            _EMPTY_MESSAGES.get(message, message[:12]),
            _point(8, 23, region, factor),
            _font(11, False, factor, hangul=True),
            palette.muted,
            anchor="lm",
        )
        return
    if logical_width < _MIN_FULL_WIDTH:
        _draw_numbers(draw, rows, region, factor, palette)
        return
    centers = (23.0,) if len(rows) == 1 else (13.5, 32.5)
    for row, center_y in zip(rows, centers, strict=False):
        _draw_full_row(draw, row, center_y, region, factor, palette)


def _draw_full_row(  # noqa: PLR0913, PLR0917
    draw: ImageDraw.ImageDraw,
    row: TaskbarRow,
    center_y: float,
    region: HitRegion,
    factor: float,
    palette: _Palette,
) -> None:
    left = region.left * _SUPERSAMPLE
    top = region.top * _SUPERSAMPLE
    def x(value: float) -> int:
        return left + round(value * factor)

    y = top + round(center_y * factor)
    _center_text(
        draw,
        row.label,
        (x(8), y),
        _font(11, False, factor, hangul=_contains_hangul(row.label)),
        palette.muted,
        "lm",
    )
    track_left = x(_BAR_LEFT)
    track_right = min(
        x(_BAR_LEFT + _BAR_WIDTH),
        round(region.right * _SUPERSAMPLE - _PERCENT_WIDTH * factor),
    )
    radius = max(1, round(2 * factor))
    if track_right > track_left:
        track_box = (track_left, y - radius, track_right, y + radius)
        draw.rounded_rectangle(track_box, radius=radius, fill=palette.track)
        fill_right = track_left + round(
            (track_right - track_left) * row.remaining_percent / 100
        )
        if fill_right > track_left:
            draw.rounded_rectangle(
                (track_left, y - radius, fill_right, y + radius),
                radius=radius,
                fill=_severity(row.remaining_percent, palette),
            )
    _center_text(
        draw,
        row.percent_text,
        (
            min(
                x(_USAGE_WIDTH - _PAD_RIGHT),
                region.right * _SUPERSAMPLE - round(_PAD_RIGHT * factor),
            ),
            y,
        ),
        _font(14, True, factor),
        palette.text,
        "rm",
    )


def _draw_numbers(
    draw: ImageDraw.ImageDraw,
    rows: tuple[TaskbarRow, ...],
    region: HitRegion,
    factor: float,
    palette: _Palette,
) -> None:
    left = region.left * _SUPERSAMPLE
    width = (region.right - region.left) * _SUPERSAMPLE
    column = width / len(rows)
    top = region.top * _SUPERSAMPLE
    for index, row in enumerate(rows):
        center = left + column * (index + 0.5)
        _center_text(
            draw,
            row.percent_text,
            (round(center), top + round(17 * factor)),
            _font(15, True, factor),
            palette.text,
            "mm",
        )
        _center_text(
            draw,
            row.label,
            (round(center), top + round(34 * factor)),
            _font(11, False, factor, hangul=_contains_hangul(row.label)),
            palette.muted,
            "mm",
        )


def _draw_menu(
    canvas: Image.Image,
    region: HitRegion,
    factor: float,
    palette: _Palette,
    model: TaskbarModel,
) -> None:
    icon_size = max(1, round(19 * factor))
    mask = _codex_mask(icon_size)
    icon = Image.new("RGBA", mask.size, palette.text)
    icon.putalpha(mask)
    center_x = (region.left + region.right) * _SUPERSAMPLE // 2
    center_y = (region.top + region.bottom) * _SUPERSAMPLE // 2
    canvas.alpha_composite(icon, (center_x - icon_size // 2, center_y - icon_size // 2))
    dot = max(1, round(5 * factor))
    right = region.right * _SUPERSAMPLE - round(7 * factor)
    bottom = region.bottom * _SUPERSAMPLE - round(7 * factor)
    color = palette.amber if model.stale or model.error_text else palette.green
    ImageDraw.Draw(canvas).ellipse(
        (right - dot, bottom - dot, right, bottom),
        fill=color,
    )


def _rounded(
    draw: ImageDraw.ImageDraw,
    region: HitRegion,
    factor: float,
    radius: int,
    fill: tuple[int, int, int, int],
) -> None:
    draw.rounded_rectangle(
        tuple(
            value * _SUPERSAMPLE
            for value in (region.left, region.top, region.right, region.bottom)
        ),
        radius=round(radius * factor),
        fill=fill,
    )


def _ensure_hit_alpha(
    image: Image.Image,
    regions: TaskbarHitRegions,
    dpi: int,
) -> None:
    """Keep transparent-looking button footprints native-hit-testable."""
    mask = Image.new("L", image.size)
    draw = ImageDraw.Draw(mask)
    radius = round(7 * max(_BASE_DPI, dpi) / _BASE_DPI)
    for region in (regions.usage, regions.menu):
        draw.rounded_rectangle(
            (region.left, region.top, region.right - 1, region.bottom - 1),
            radius=radius,
            fill=1,
        )
    alpha = image.getchannel("A")
    image.putalpha(ImageChops.lighter(alpha, mask))


def _redraw_tracks(
    image: Image.Image,
    rows: tuple[TaskbarRow, ...],
    region: HitRegion,
    dpi: int,
    palette: _Palette,
) -> None:
    """Replace color-resampled bars with solid-color alpha-mask capsules."""
    scale = max(_BASE_DPI, dpi) / _BASE_DPI
    left = region.left + _BAR_LEFT * scale
    right = region.left + (_BAR_LEFT + _BAR_WIDTH) * scale
    centers = (23.0,) if len(rows) == 1 else (13.5, 32.5)
    pixels = image.load()
    if pixels is None:
        return
    for row, center in zip(rows, centers, strict=False):
        center_y = region.top + center * scale
        top, bottom = center_y - 2 * scale, center_y + 2 * scale
        for y in range(max(0, int(top) - 2), min(image.height, round(bottom) + 3)):
            for x in range(max(0, int(left) - 2), min(image.width, round(right) + 3)):
                pixels[x, y] = (0, 0, 0, 0)
        _masked_capsule(image, (left, top, right, bottom), palette.track)
        fill_right = left + (right - left) * row.remaining_percent / 100
        if fill_right > left:
            _masked_capsule(
                image,
                (left, top, fill_right, bottom),
                _severity(row.remaining_percent, palette),
            )


def _masked_capsule(
    image: Image.Image,
    box: tuple[float, float, float, float],
    color: str,
) -> None:
    """Composite one exact-color capsule using only a resampled alpha mask."""
    mask = Image.new("L", (image.width * _SUPERSAMPLE, image.height * _SUPERSAMPLE))
    draw = ImageDraw.Draw(mask)
    scaled = tuple(round(value * _SUPERSAMPLE) for value in box)
    radius = max(1, round((box[3] - box[1]) * _SUPERSAMPLE / 2))
    draw.rounded_rectangle(scaled, radius=radius, fill=255)
    mask = mask.resize(image.size, Image.Resampling.LANCZOS)
    solid = Image.new("RGBA", image.size, color)
    solid.putalpha(mask)
    image.alpha_composite(solid)


def _point(x: float, y: float, region: HitRegion, factor: float) -> tuple[int, int]:
    return (
        region.left * _SUPERSAMPLE + round(x * factor),
        region.top * _SUPERSAMPLE + round(y * factor),
    )


def _center_text(  # noqa: PLR0913, PLR0917
    draw: ImageDraw.ImageDraw,
    text: str,
    point: tuple[int, int],
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    fill: str,
    anchor: str,
) -> None:
    draw.text(point, text, font=font, fill=fill, anchor=anchor)


def _severity(remaining: float, palette: _Palette) -> str:
    if remaining <= _DANGER_REMAINING:
        return palette.red
    if remaining <= _WARNING_REMAINING:
        return palette.amber
    return palette.green


@lru_cache(maxsize=16)
def _font(
    size: int,
    semibold: bool,
    factor: float,
    *,
    hangul: bool = False,
) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    pixels = max(1, round(size * factor))
    windows = Path("C:/Windows/Fonts")
    if hangul:
        names = ("malgunbd.ttf", "malgun.ttf") if semibold else ("malgun.ttf",)
    else:
        # The variable font's weight-selection support varies by Pillow build.
        # seguisb is a stable real 600-weight face and matches the HTML intent.
        names = ("seguisb.ttf", "SegUIVar.ttf") if semibold else (
            "SegUIVar.ttf",
            "segoeui.ttf",
        )
    for name in names:
        try:
            font = ImageFont.truetype(str(windows / name), pixels)
        except OSError:
            continue
        else:
            if name == "SegUIVar.ttf" and semibold:
                with suppress(OSError, ValueError):
                    font.set_variation_by_name("Semibold Text")
            return font
    return ImageFont.load_default(size=pixels)


def _contains_hangul(text: str) -> bool:
    return any("\uac00" <= character <= "\ud7a3" for character in text)


@lru_cache(maxsize=8)
def _codex_mask(size: int) -> Image.Image:
    with Image.open(io.BytesIO(load_tray_png())) as source:
        alpha = source.convert("RGBA").getchannel("A")
    return alpha.resize((size, size), Image.Resampling.LANCZOS)


__all__ = ["HitRegion", "TaskbarHitRegions", "render_taskbar", "taskbar_hit_regions"]
