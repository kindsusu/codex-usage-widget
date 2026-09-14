# pyright: reportUnknownMemberType=false
# ruff: noqa: PLR0913, PLR0917
"""Deterministic Pillow renderer for the desktop full and mini cards."""

from __future__ import annotations

import io
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Final, Literal, TypeAlias

from PIL import Image, ImageDraw, ImageFont

from codex_usage_widget.assets import load_tray_png
from codex_usage_widget.card_tokens import (
    CARD_METRICS,
    CardPalette,
    card_palette,
    severity_color,
)
from codex_usage_widget.presentation import percent_text
from codex_usage_widget.service import RefreshStatus, failure_message

if TYPE_CHECKING:
    from codex_usage_widget.presentation import SnapshotViewModel
    from codex_usage_widget.service import WidgetState

CardMode: TypeAlias = Literal["full", "mini"]
HoverRegion: TypeAlias = Literal["brand", "mode"]
_SUPERSAMPLE: Final = 3
_FULL_BASE_SCALE: Final = 0.70
_FONT_ROOT: Final = Path("C:/Windows/Fonts")
_MAX_STATUS_CHARS: Final = 24
_BASE_ROW_COUNT: Final = 2
_EXTRA_ROW_HEIGHT: Final = 46


@dataclass(frozen=True, slots=True)
class CardMetric:
    """One actual usage window expressed as remaining capacity."""

    label: str
    mini_label: str
    remaining_percent: float
    percent_text: str


@dataclass(frozen=True, slots=True)
class DesktopCardModel:
    """Privacy-safe data needed by both desktop card modes."""

    plan: str
    rows: tuple[CardMetric, ...]
    status_text: str | None


@dataclass(frozen=True, slots=True)
class HitRegion:
    """Physical-pixel interaction rectangle."""

    left: int
    top: int
    right: int
    bottom: int

    def contains(self, x: int, y: int) -> bool:
        """Return whether a physical point is inside the half-open box."""
        return self.left <= x < self.right and self.top <= y < self.bottom


@dataclass(frozen=True, slots=True)
class DesktopHitRegions:
    """Clickable regions for the rendered card."""

    brand: HitRegion | None
    mode: HitRegion


@dataclass(frozen=True, slots=True)
class RenderedDesktopCard:
    """Straight-alpha image and matching physical hit targets."""

    image: Image.Image
    hit_regions: DesktopHitRegions
    logical_width: int
    logical_height: int


def build_desktop_card_model(
    view_model: SnapshotViewModel | None,
    state: WidgetState,
) -> DesktopCardModel:
    """Adapt the existing snapshot presentation without changing shared models."""
    rows = () if view_model is None else view_model.rows
    metrics = tuple(
        CardMetric(
            label=row.label,
            mini_label=_mini_label(row.label),
            remaining_percent=_remaining(row.window.used_percent),
            percent_text=percent_text(_remaining(row.window.used_percent)),
        )
        for row in rows
    )
    plan = "" if view_model is None else view_model.title.removeprefix("Codex").strip()
    status: str | None = None
    if state.failure is not None:
        status = failure_message(state.failure)
    elif view_model is None:
        status = "Codex 사용량을 확인하는 중…"
    elif state.status is RefreshStatus.REFRESHING:
        status = "새로고침 중…"
    return DesktopCardModel(plan=plan, rows=metrics, status_text=status)


def render_desktop_card(
    model: DesktopCardModel,
    *,
    mode: CardMode,
    light_theme: bool,
    scale: float = 1.0,
    hover_region: HoverRegion | None = None,
) -> RenderedDesktopCard:
    """Render one card at its mode-specific base size multiplied by ``scale``."""
    scale = max(0.5, min(4.0, scale))
    render_scale = scale * (_FULL_BASE_SCALE if mode == "full" else 1.0)
    logical_width = (
        CARD_METRICS.full_width if mode == "full" else CARD_METRICS.mini_width
    )
    logical_height = (
        CARD_METRICS.full_height if mode == "full" else CARD_METRICS.mini_height
    )
    if mode == "full" and len(model.rows) > _BASE_ROW_COUNT:
        logical_height += (len(model.rows) - _BASE_ROW_COUNT) * _EXTRA_ROW_HEIGHT
    if mode == "full" and model.status_text is not None:
        logical_height += CARD_METRICS.status_extra_height
    width = max(1, round(logical_width * render_scale))
    height = max(1, round(logical_height * render_scale))
    ss_scale = render_scale * _SUPERSAMPLE
    canvas = Image.new("RGBA", (width * _SUPERSAMPLE, height * _SUPERSAMPLE))
    palette = card_palette(light_theme)
    draw = ImageDraw.Draw(canvas)
    _draw_card_background(
        canvas, draw, mode, logical_width, logical_height, ss_scale, palette
    )
    regions = _hit_regions(mode, render_scale)
    if mode == "full":
        _draw_full(canvas, draw, model, ss_scale, palette, hover_region)
    else:
        _draw_mini(canvas, draw, model, ss_scale, palette, hover_region)
    image = canvas.resize((width, height), Image.Resampling.LANCZOS)
    _redraw_tracks(image, model, mode, render_scale, palette)
    _clip_opaque_silhouette(image, mode, render_scale)
    base_width = round(logical_width * (_FULL_BASE_SCALE if mode == "full" else 1.0))
    base_height = round(
        logical_height * (_FULL_BASE_SCALE if mode == "full" else 1.0)
    )
    return RenderedDesktopCard(image, regions, base_width, base_height)


def _draw_card_background(
    canvas: Image.Image,
    draw: ImageDraw.ImageDraw,
    mode: CardMode,
    width: int,
    height: int,
    scale: float,
    palette: CardPalette,
) -> None:
    radius = CARD_METRICS.full_radius if mode == "full" else CARD_METRICS.mini_radius
    _ = canvas
    box = (0, 0, round(width * scale) - 1, round(height * scale) - 1)
    surface = (
        palette.surface_solid if mode == "full" else _rgb_hex(palette.mini_surface[:3])
    )
    draw.rounded_rectangle(
        box,
        radius=round(radius * scale),
        fill=surface,
        outline=_blend(surface, palette.line) if mode == "full" else None,
        width=max(1, round(scale)),
    )


def _draw_full(
    canvas: Image.Image,
    draw: ImageDraw.ImageDraw,
    model: DesktopCardModel,
    scale: float,
    palette: CardPalette,
    hover: HoverRegion | None,
) -> None:
    _rounded(draw, (16, 18, 42, 44), 8, scale, palette.text)
    _draw_codex(canvas, (21, 23), 16, scale, palette.surface_solid)
    _text(draw, (51, 31), "Codex", 14, True, scale, palette.text, "lm")
    button = (200, 17, 262, 45)
    if hover == "mode":
        _rounded(
            draw,
            button,
            6,
            scale,
            _blend(palette.surface_solid, palette.hover),
        )
    _rounded(
        draw,
        button,
        6,
        scale,
        None,
        _blend(palette.surface_solid, palette.line),
        1,
    )
    _text(draw, (231, 31), "미니 모드", 11, False, scale, palette.muted, "mm", True)
    if model.plan:
        _text(draw, (191, 31), model.plan, 12, False, scale, palette.muted, "rm")
    centers = (
        tuple(71 + index * 46 for index in range(len(model.rows)))
        if len(model.rows) > 1
        else (94,)
    )
    for row, center in zip(model.rows, centers, strict=False):
        _text(draw, (16, center), row.label, 12, False, scale, palette.text, "lm", True)
        _text(
            draw,
            (264, center),
            f"{row.percent_text} 남음",
            12,
            True,
            scale,
            palette.text,
            "rm",
            True,
        )
        _track(draw, 17, center + 16, 246, 6, row.remaining_percent, scale, palette)
    if not model.rows and model.status_text is None:
        _text(
            draw,
            (16, 96),
            "사용량 정보 없음",
            12,
            False,
            scale,
            palette.muted,
            "lm",
            True,
        )
    if model.status_text is not None:
        y = (
            159 + max(0, len(model.rows) - _BASE_ROW_COUNT) * _EXTRA_ROW_HEIGHT
            if model.rows
            else 113
        )
        _text(
            draw,
            (16, y),
            _bounded_status(model.status_text),
            11,
            False,
            scale,
            palette.muted,
            "la",
            True,
        )


def _draw_mini(
    canvas: Image.Image,
    draw: ImageDraw.ImageDraw,
    model: DesktopCardModel,
    scale: float,
    palette: CardPalette,
    hover: HoverRegion | None,
) -> None:
    _draw_codex(canvas, (8, 16), 14, scale, palette.text)
    for row, left in zip(model.rows[:2], (30, 116), strict=False):
        _text(
            draw,
            (left, 23),
            row.mini_label,
            11,
            False,
            scale,
            palette.muted,
            "lm",
            True,
        )
        _track(draw, left + 25, 21, 25, 4, row.remaining_percent, scale, palette)
        _text(
            draw, (left + 78, 23), row.percent_text, 11, True, scale, palette.text, "rm"
        )
    if not model.rows:
        message = "연결 필요" if model.status_text else "확인 중…"
        _text(draw, (30, 23), message, 11, False, scale, palette.muted, "lm", True)
    button = (208, 9, 236, 37)
    if hover == "mode":
        surface = _rgb_hex(palette.mini_surface[:3])
        _rounded(draw, button, 6, scale, _blend(surface, palette.hover))
    color = palette.text if hover == "mode" else palette.muted
    _maximize(draw, button, scale, color)


def _hit_regions(mode: CardMode, scale: float) -> DesktopHitRegions:
    def region(box: tuple[int, int, int, int]) -> HitRegion:
        return HitRegion(*(round(value * scale) for value in box))

    if mode == "full":
        return DesktopHitRegions(region((16, 18, 42, 44)), region((200, 17, 262, 45)))
    return DesktopHitRegions(None, region((208, 9, 236, 37)))


def _track(
    draw: ImageDraw.ImageDraw,
    left: int,
    top: int,
    width: int,
    height: int,
    remaining: float,
    scale: float,
    palette: CardPalette,
) -> None:
    box = tuple(
        round(value * scale) for value in (left, top, left + width, top + height)
    )
    radius = max(1, round(height * scale / 2))
    draw.rounded_rectangle(box, radius=radius, fill=palette.track)
    fill_right = box[0] + round((box[2] - box[0]) * remaining / 100)
    if fill_right > box[0]:
        draw.rounded_rectangle(
            (box[0], box[1], fill_right, box[3]),
            radius=radius,
            fill=severity_color(palette, remaining),
        )


def _redraw_tracks(
    image: Image.Image,
    model: DesktopCardModel,
    mode: CardMode,
    scale: float,
    palette: CardPalette,
) -> None:
    """Repaint bars at output size so LANCZOS cannot create pale color tails."""
    draw = ImageDraw.Draw(image)
    if mode == "full":
        centers = (
            tuple(71 + index * 46 for index in range(len(model.rows)))
            if len(model.rows) > 1
            else (94,)
        )
        specs = ((17, center + 16, 246, 6) for center in centers)
    else:
        specs = ((left + 25, 21, 25, 4) for left in (30, 116))
    rows = model.rows if mode == "full" else model.rows[:2]
    for row, (left, top, width, height) in zip(rows, specs, strict=False):
        _track(draw, left, top, width, height, row.remaining_percent, scale, palette)


def _clip_opaque_silhouette(
    image: Image.Image,
    mode: CardMode,
    scale: float,
) -> None:
    """Keep Tk's color-key surface opaque inside and transparent outside."""
    radius = CARD_METRICS.full_radius if mode == "full" else CARD_METRICS.mini_radius
    mask = Image.new("L", image.size)
    ImageDraw.Draw(mask).rounded_rectangle(
        (0, 0, image.width - 1, image.height - 1),
        radius=max(1, round(radius * scale)),
        fill=255,
    )
    image.putalpha(mask)


def _draw_codex(
    canvas: Image.Image, origin: tuple[int, int], size: int, scale: float, color: str
) -> None:
    px = max(1, round(size * scale))
    mask = _codex_mask(px)
    glyph = Image.new("RGBA", (px, px), color)
    glyph.putalpha(mask)
    canvas.alpha_composite(glyph, (round(origin[0] * scale), round(origin[1] * scale)))


@lru_cache(maxsize=16)
def _codex_mask(size: int) -> Image.Image:
    with Image.open(io.BytesIO(load_tray_png()), formats=("PNG",)) as source:
        return (
            source.convert("RGBA")
            .getchannel("A")
            .resize((size, size), Image.Resampling.LANCZOS)
        )


def _rounded(
    draw: ImageDraw.ImageDraw,
    box: tuple[float, float, float, float],
    radius: float,
    scale: float,
    fill: str | tuple[int, int, int, int] | None,
    outline: str | tuple[int, int, int, int] | None = None,
    width: int = 1,
) -> None:
    draw.rounded_rectangle(
        tuple(round(value * scale) for value in box),
        radius=round(radius * scale),
        fill=fill,
        outline=outline,
        width=max(1, round(width * scale)),
    )


def _text(
    draw: ImageDraw.ImageDraw,
    point: tuple[float, float],
    value: str,
    size: int,
    bold: bool,
    scale: float,
    color: str,
    anchor: str,
    hangul: bool = False,
) -> None:
    draw.text(
        (round(point[0] * scale), round(point[1] * scale)),
        value,
        font=_font(size, bold, scale, hangul),
        fill=color,
        anchor=anchor,
    )


@lru_cache(maxsize=64)
def _font(
    logical_size: int, bold: bool, scale: float, hangul: bool
) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    px = max(1, round(logical_size * scale))
    if hangul:
        candidates = ("malgunbd.ttf", "malgun.ttf") if bold else ("malgun.ttf",)
    else:
        candidates = (
            ("seguisb.ttf", "SegUIVar.ttf") if bold else ("SegUIVar.ttf", "segoeui.ttf")
        )
    for name in candidates:
        try:
            font = ImageFont.truetype(_FONT_ROOT / name, px)
        except OSError:
            continue
        return font
    return ImageFont.load_default(size=px)


def _maximize(
    draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], scale: float, color: str
) -> None:
    left, top, right, bottom = box
    inset = 8
    x1, y1 = round((left + inset) * scale), round((top + inset) * scale)
    x2, y2 = round((right - inset) * scale), round((bottom - inset) * scale)
    line = max(1, round(1.5 * scale))
    length = max(2, round(4 * scale))
    draw.line((x1, y1 + length, x1, y1, x1 + length, y1), fill=color, width=line)
    draw.line((x2 - length, y2, x2, y2, x2, y2 - length), fill=color, width=line)


def _remaining(used_percent: float) -> float:
    return 100.0 - max(0.0, min(100.0, used_percent))


def _mini_label(label: str) -> str:
    if label.startswith("5시간"):
        return "5h"
    if label.startswith("주간"):
        return "주간"
    return label.removesuffix(" 한도")[:3]


def _bounded_status(value: str) -> str:
    return (
        value
        if len(value) <= _MAX_STATUS_CHARS
        else value[: _MAX_STATUS_CHARS - 1] + "…"
    )


def _blend(background: str, foreground: tuple[int, int, int, int]) -> str:
    base = tuple(int(background[index : index + 2], 16) for index in (1, 3, 5))
    alpha = foreground[3] / 255
    channels = (
        round(foreground[0] * alpha + base[0] * (1 - alpha)),
        round(foreground[1] * alpha + base[1] * (1 - alpha)),
        round(foreground[2] * alpha + base[2] * (1 - alpha)),
    )
    return _rgb_hex(channels)


def _rgb_hex(channels: tuple[int, int, int]) -> str:
    return "#" + "".join(f"{channel:02x}" for channel in channels)
