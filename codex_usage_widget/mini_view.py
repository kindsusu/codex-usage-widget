# pyright: reportUnknownArgumentType=false, reportUnknownMemberType=false
"""Mini-mode surface with root-level restore interaction.

The compact strip renders one iPhone-style battery per usage window: a
rounded body stroked in the theme foreground, a terminal nub, and an inner
fill that shows REMAINING capacity (100 - used). The fill turns red once the
remaining charge drops to the low threshold. Floating S/W glyphs sit to the
left of each battery as hard-edged (alpha-thresholded) images so they never
show ClearType fringe against the transparent color key.
"""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, Protocol, TypeAlias, final

from PIL import Image, ImageDraw, ImageFont, ImageTk

from codex_usage_widget.presentation import percent_text

if TYPE_CHECKING:
    from codex_usage_widget.presentation import SnapshotViewModel, UsageRowViewModel
    from codex_usage_widget.service import WidgetState
    from codex_usage_widget.theme import ThemeTokens

BindingCallback: TypeAlias = Callable[[], str]
_BATTERY_TEXT_SWITCH_PERCENT: Final = 50.0
_LOW_REMAINING_PERCENT: Final = 20.0
_MIN_VISIBLE_FILL_PX: Final = 3
_OPAQUE_ALPHA_THRESHOLD: Final = 128
_LABEL_PAD: Final = 2
_WEEKLY_DURATION_MINS: Final = 10_080
_BOLD_FONT_FILE: Final = "segoeuib.ttf"


class BindingTarget(Protocol):
    """Minimal tree and binding seam used by mini-mode interactions."""

    def children(self) -> tuple[BindingTarget, ...]:
        """Return direct descendants."""
        ...

    def bind(self, sequence: str, callback: BindingCallback) -> str:
        """Register and identify one binding."""
        ...

    def unbind(self, sequence: str, binding_id: str) -> None:
        """Remove one identified binding."""
        ...


@final
class TkBindingTarget:
    """Adapt one Tk widget tree to the testable binding seam."""

    def __init__(self, widget: tk.Misc) -> None:
        """Wrap a concrete Tk widget."""
        self._widget = widget

    def children(self) -> tuple[BindingTarget, ...]:
        """Return wrapped direct descendants."""
        return tuple(TkBindingTarget(child) for child in self._widget.winfo_children())

    def bind(self, sequence: str, callback: BindingCallback) -> str:
        """Add a callback that can stop root drag propagation."""

        def handle(_event: tk.Event[tk.Misc]) -> str:
            return callback()

        return self._widget.bind(sequence, handle, add="+")

    def unbind(self, sequence: str, binding_id: str) -> None:
        """Remove one callback without disturbing unrelated bindings."""
        self._widget.unbind(sequence, binding_id)


@final
class RestoreBindingGroup:
    """Bind restore and release guards across one complete widget tree."""

    def __init__(self, root: BindingTarget, restore: Callable[[], None]) -> None:
        """Bind every current descendant and guard restore to one call."""
        self._restore = restore
        self._restored = False
        self._bindings: list[tuple[BindingTarget, str, str]] = []
        for target in _binding_targets(root):
            restore_id = target.bind("<Double-Button-1>", self._restore_once)
            release_id = target.bind("<ButtonRelease-1>", _stop_root_release)
            self._bindings.extend(
                (
                    (target, "<Double-Button-1>", restore_id),
                    (target, "<ButtonRelease-1>", release_id),
                )
            )

    def dispose(self) -> None:
        """Remove all exact function ids in reverse registration order."""
        for target, sequence, binding_id in reversed(self._bindings):
            target.unbind(sequence, binding_id)
        self._bindings.clear()

    def _restore_once(self) -> str:
        if not self._restored:
            self._restored = True
            self._restore()
        return "break"


def _binding_targets(root: BindingTarget) -> tuple[BindingTarget, ...]:
    descendants = tuple(
        nested for child in root.children() for nested in _binding_targets(child)
    )
    return (root, *descendants)


def _stop_root_release() -> str:
    return "break"


@final
@dataclass(frozen=True, slots=True)
class MiniBatteryStyle:
    """Codex-brand label glyph and fill for one usage window."""

    label: str
    base_fill: str
    label_color: str


@final
@dataclass(frozen=True, slots=True)
class FillBox:
    """Drawn coordinates of a battery's remaining-charge rectangle."""

    left: int
    top: int
    right: int
    bottom: int


@final
@dataclass(frozen=True, slots=True)
class RoundedRect:
    """Position, size, and corner radius for a smoothed rectangle."""

    x: int
    y: int
    width: int
    height: int
    radius: int


def mini_remaining_percent(used_percent: float) -> float:
    """Convert a used percentage into a clamped remaining percentage."""
    return 100.0 - max(0.0, min(100.0, used_percent))


def mini_battery_fill_pixels(remaining_percent: float, inner_width: int) -> int:
    """Return the remaining-charge width, floored so a sliver stays visible."""
    clamped = max(0.0, min(100.0, remaining_percent))
    if clamped <= 0.0:
        return 0
    return max(_MIN_VISIBLE_FILL_PX, round(inner_width * clamped / 100))


def mini_fill_box(
    body_x: int,
    body_y: int,
    body_height: int,
    inset: int,
    fill_pixels: int,
) -> FillBox:
    """Derive a symmetric fill rectangle from the body box.

    The top and bottom insets are both ``inset`` by construction. Tk paints an
    outline-less rectangle up to ``x2 - 1`` / ``y2 - 1`` (right/bottom
    exclusive), so ``+1`` on each far edge renders the full intended box.
    """
    left = body_x + inset
    top = body_y + inset
    fill_height = body_height - 2 * inset
    return FillBox(left, top, left + fill_pixels + 1, top + fill_height + 1)


def mini_battery_fill_color(
    remaining_percent: float,
    base_fill: str,
    low_fill: str,
) -> str:
    """Swap the brand fill for the low-charge red at or below the threshold."""
    return low_fill if remaining_percent <= _LOW_REMAINING_PERCENT else base_fill


def mini_battery_text_color(remaining_percent: float, tokens: ThemeTokens) -> str:
    """Keep centered percentage text legible across filled and empty halves."""
    return (
        tokens.meter_text_on_fill
        if remaining_percent >= _BATTERY_TEXT_SWITCH_PERCENT
        else tokens.text_primary
    )


def mini_battery_style(
    window_duration_mins: int, tokens: ThemeTokens
) -> MiniBatteryStyle:
    """Map a window duration to its S (5-hour) or W (weekly) battery style."""
    if window_duration_mins == _WEEKLY_DURATION_MINS:
        return MiniBatteryStyle("W", tokens.mini_weekly_fill, tokens.mini_weekly_label)
    return MiniBatteryStyle("S", tokens.mini_session_fill, tokens.mini_session_label)


def render_label_image(text: str, color_hex: str, px_size: int) -> Image.Image:
    """Render bold text as a hard-edged RGBA image (binary alpha, no fringe)."""
    font = _load_bold_font(px_size)
    bbox = font.getbbox(text)
    width = int(bbox[2] - bbox[0]) + _LABEL_PAD * 2
    height = int(bbox[3] - bbox[1]) + _LABEL_PAD * 2
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.text(
        (_LABEL_PAD - bbox[0], _LABEL_PAD - bbox[1]),
        text,
        font=font,
        fill=color_hex,
    )
    alpha = image.getchannel("A").point(_binary_alpha)
    image.putalpha(alpha)
    return image


@final
@dataclass(frozen=True, slots=True)
class MiniSurfaceSpec:
    """Immutable inputs required to render a mini surface."""

    view_model: SnapshotViewModel | None
    state: WidgetState
    tokens: ThemeTokens
    restore: Callable[[], None]


@final
class MiniSurface:
    """Own the floating battery strip and its restore bindings."""

    def __init__(
        self,
        root: tk.Tk,
        spec: MiniSurfaceSpec,
    ) -> None:
        """Build and bind one mini-mode surface."""
        self._root = root
        tokens = spec.tokens
        self._label_photos: list[ImageTk.PhotoImage] = []
        frame = tk.Frame(
            root,
            bg=tokens.mini_background_key,
            highlightthickness=0,
            padx=0,
            pady=0,
        )
        self._frame = frame
        _ = frame.pack(fill="both", expand=True)
        canvas = tk.Canvas(
            frame,
            width=tokens.mini_width,
            height=tokens.mini_height,
            bg=tokens.mini_background_key,
            borderwidth=0,
            highlightthickness=0,
        )
        _ = canvas.pack()
        rows = () if spec.view_model is None else spec.view_model.mini_rows
        if rows:
            for index, row in enumerate(rows):
                body_x = tokens.mini_first_body_x + index * tokens.mini_group_pitch
                self._draw_battery(canvas, body_x, row, tokens)
        else:
            _ = canvas.create_text(
                tokens.mini_first_body_x,
                tokens.mini_height / 2,
                anchor="w",
                text="확인 중…" if spec.state.failure is None else "연결 필요",
                fill=tokens.text_secondary,
                font=(tokens.font_family, 8),
            )
        self._bindings = RestoreBindingGroup(TkBindingTarget(frame), spec.restore)
        root.geometry(f"{tokens.mini_width}x{tokens.mini_height}")

    def dispose(self) -> None:
        """Release bindings and destroy mini widgets."""
        self._bindings.dispose()
        self._frame.destroy()
        self._label_photos.clear()

    def _draw_battery(
        self,
        canvas: tk.Canvas,
        body_x: int,
        row: UsageRowViewModel,
        tokens: ThemeTokens,
    ) -> None:
        body_y = tokens.mini_battery_top
        body_w = tokens.mini_battery_width
        body_h = tokens.mini_battery_height
        inset = tokens.mini_battery_inset
        remaining = mini_remaining_percent(row.window.used_percent)
        style = mini_battery_style(row.window.window_duration_mins, tokens)
        _ = _rounded_rect(
            canvas,
            RoundedRect(
                body_x,
                body_y,
                body_w,
                body_h,
                tokens.mini_battery_corner_radius,
            ),
            fill=tokens.bar_background,
            outline=tokens.control_default,
            width=1,
        )
        _ = _rounded_rect(
            canvas,
            RoundedRect(
                body_x + body_w + 1,
                body_y + (body_h - tokens.mini_nub_height) // 2,
                tokens.mini_nub_width,
                tokens.mini_nub_height,
                2,
            ),
            fill=tokens.control_default,
            outline="",
        )
        inner_width = body_w - 2 * inset
        fill_pixels = mini_battery_fill_pixels(remaining, inner_width)
        if fill_pixels > 0:
            box = mini_fill_box(body_x, body_y, body_h, inset, fill_pixels)
            _ = canvas.create_rectangle(
                box.left,
                box.top,
                box.right,
                box.bottom,
                fill=mini_battery_fill_color(
                    remaining, style.base_fill, tokens.mini_low_fill
                ),
                outline="",
            )
        photo = ImageTk.PhotoImage(
            render_label_image(style.label, style.label_color, tokens.mini_label_px)
        )
        self._label_photos.append(photo)
        _ = canvas.create_image(
            body_x - tokens.mini_label_gap + 2,
            body_y + body_h // 2,
            image=photo,
            anchor="e",
        )
        _ = canvas.create_text(
            body_x + body_w // 2,
            body_y + body_h // 2,
            text=percent_text(remaining),
            fill=mini_battery_text_color(remaining, tokens),
            font=(tokens.font_family, 8, "bold"),
        )


def _rounded_rect(
    canvas: tk.Canvas,
    rect: RoundedRect,
    *,
    fill: str,
    outline: str,
    width: float = 1.0,
) -> int:
    """Approximate an iOS-style rounded rectangle via a smoothed polygon."""
    x, y, w, h, r = rect.x, rect.y, rect.width, rect.height, rect.radius
    points = [
        x + r, y, x + w - r, y, x + w, y, x + w, y + r,
        x + w, y + h - r, x + w, y + h, x + w - r, y + h,
        x + r, y + h, x, y + h, x, y + h - r, x, y + r, x, y,
    ]
    return canvas.create_polygon(
        points, smooth=True, fill=fill, outline=outline, width=width
    )


def _load_bold_font(px_size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    try:
        return ImageFont.truetype(_BOLD_FONT_FILE, px_size)
    except OSError:
        return ImageFont.load_default()


def _binary_alpha(value: float) -> int:
    return 255 if value >= _OPAQUE_ALPHA_THRESHOLD else 0
