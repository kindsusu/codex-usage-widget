# pyright: reportAny=false, reportUnknownMemberType=false
"""Non-modal visibility controls opened from Codex brand surfaces."""

from __future__ import annotations

import ctypes
import io
import math
import sys
import tkinter as tk
from ctypes import wintypes
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Final, final

from PIL import Image, ImageDraw, ImageFont, ImageTk

from codex_usage_widget.actions import DesktopMode, desktop_mode
from codex_usage_widget.assets import load_tray_png
from codex_usage_widget.card_tokens import card_palette
from codex_usage_widget.taskbar_details import bounded_popup_position, monitor_metrics
from codex_usage_widget.window_runtime import format_window_position
from codex_usage_widget.windows import hide_from_taskbar

if TYPE_CHECKING:
    from collections.abc import Callable

    from codex_usage_widget.config import WidgetConfig

_WIDTH: Final = 292
_HEIGHT: Final = 258.25
_ROW_TOP: Final = 46
_ROW_HEIGHT: Final = 40
_ROW_COUNT: Final = 4
_FONT_ROOT: Final = Path("C:/Windows/Fonts")
_SUPERSAMPLE: Final = 3


@dataclass(frozen=True, slots=True)
class VisibilityCallbacks:
    """Commands emitted by the exclusive desktop and taskbar rows."""

    normal: Callable[[], None]
    mini: Callable[[], None]
    hidden: Callable[[], None]
    taskbar: Callable[[], None]
    trigger_contains: Callable[[int, int], bool]


@final
class VisibilityPanel:
    """Own a single focus-dismissed visibility card on Tk's UI thread."""

    def __init__(self, root: tk.Tk, callbacks: VisibilityCallbacks) -> None:
        """Bind callbacks without constructing a native window yet."""
        self._root = root
        self._callbacks = callbacks
        self._window: tk.Toplevel | None = None
        self._canvas: tk.Canvas | None = None
        self._config: WidgetConfig | None = None
        self._hover: int | None = None
        self._icon: ImageTk.PhotoImage | None = None
        self._anchor = (0, 0)

    @property
    def open(self) -> bool:
        """Return whether the panel currently owns a live Toplevel."""
        window = self._window
        return window is not None and bool(window.winfo_exists())

    def toggle(
        self,
        x: int,
        y: int,
        config: WidgetConfig,
        *,
        avoid: tuple[int, int, int, int] | None = None,
    ) -> None:
        """Close an existing card or open one above the screen anchor."""
        if self.open:
            self.close()
            return
        self._anchor = (x, y)
        self._config = config
        bounds, dpi = monitor_metrics(x, y)
        palette = card_palette(config.theme)
        width, height = visibility_panel_size(dpi)
        window = tk.Toplevel(self._root)
        self._window = window
        _ = window.overrideredirect(True)
        _ = window.attributes("-topmost", True)
        _ = window.attributes("-transparentcolor", palette.background_key)
        _ = window.configure(bg=palette.background_key)
        _ = window.resizable(False, False)
        canvas = tk.Canvas(
            window,
            width=width,
            height=height,
            bg=palette.background_key,
            highlightthickness=0,
            bd=0,
        )
        self._canvas = canvas
        _ = canvas.pack()
        _ = canvas.bind("<Motion>", self._motion)
        _ = canvas.bind("<Leave>", self._leave)
        _ = canvas.bind("<ButtonRelease-1>", self._click)
        _ = window.bind("<Escape>", lambda _event: self.close())
        _ = window.bind("<FocusOut>", self._focus_out)
        if bounds is None:
            bounds = (
                self._root.winfo_vrootx(),
                self._root.winfo_vrooty(),
                self._root.winfo_vrootx() + self._root.winfo_vrootwidth(),
                self._root.winfo_vrooty() + self._root.winfo_vrootheight(),
            )
        left, top = (
            place_avoiding_rect(avoid, width, height, bounds)
            if avoid is not None
            else bounded_popup_position(x, y, width, height, bounds)
        )
        _ = window.geometry(f"{width}x{height}{format_window_position(left, top)}")
        self._draw()
        window.update_idletasks()
        _ = hide_from_taskbar(window.winfo_id())
        _ = window.after(100, lambda: self._reassert_toolwindow(window))
        _ = window.focus_force()

    def update(self, config: WidgetConfig) -> None:
        """Redraw current checked states from the persisted configuration."""
        self._config = config
        if self.open:
            self._draw()

    def close(self) -> None:
        """Destroy the card without changing visibility preferences."""
        window, self._window = self._window, None
        self._canvas = None
        self._hover = None
        self._icon = None
        if window is not None:
            try:
                if window.winfo_exists():
                    window.destroy()
            except tk.TclError:
                pass

    def _draw(self) -> None:
        canvas, config = self._canvas, self._config
        if canvas is None or config is None:
            return
        width = int(canvas.cget("width"))
        height = int(canvas.cget("height"))
        scale = width / _WIDTH
        palette = card_palette(config.theme)
        line = _blend(palette.surface_solid, palette.line)
        hover = _blend(palette.surface_solid, palette.hover)
        render_scale = scale * _SUPERSAMPLE

        def px(value: int) -> int:
            return round(value * render_scale)

        render_width, render_height = width * _SUPERSAMPLE, height * _SUPERSAMPLE
        # Keep the supersampled source opaque through the edge; the final
        # binary mask cuts the outer shape without dark transparent-RGB halos.
        image = Image.new(
            "RGBA", (render_width, render_height), palette.surface_solid
        )
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle(
            (0, 0, render_width - 1, render_height - 1),
            radius=px(12),
            fill=palette.surface_solid,
            outline=line,
            width=max(1, px(1)),
        )
        icon = _codex_image(px(15), palette.muted)
        if icon is not None:
            image.alpha_composite(icon, (px(17), px(19)))
        _text(draw, (40, 27), "Codex 사용량", 12, True, render_scale, palette.muted)
        mode = desktop_mode(config)
        rows = (
            ("바탕화면 일반 모드", mode is DesktopMode.NORMAL, True),
            ("바탕화면 미니 모드", mode is DesktopMode.MINI, True),
            ("바탕화면 숨기기", mode is DesktopMode.HIDDEN, True),
            ("작업표시줄 위젯 표시", config.taskbar_visible, False),
        )
        for index, (label, checked, radio) in enumerate(rows):
            top = _ROW_TOP + index * _ROW_HEIGHT
            if self._hover == index:
                draw.rounded_rectangle(
                    (
                        px(8),
                        px(top),
                        render_width - px(8),
                        px(top + _ROW_HEIGHT),
                    ),
                    radius=px(7),
                    fill=hover,
                )
            x1, y1, size = px(17), px(top + 12), px(16)
            control_box = (x1, y1, x1 + size, y1 + size)
            if radio:
                draw.ellipse(
                    control_box,
                    fill=palette.track,
                    outline=palette.green if checked else palette.muted,
                    width=max(1, px(1)),
                )
                if checked:
                    inset = px(4)
                    draw.ellipse(
                        (
                            x1 + inset,
                            y1 + inset,
                            x1 + size - inset,
                            y1 + size - inset,
                        ),
                        fill=palette.green,
                    )
            else:
                draw.rounded_rectangle(
                    control_box,
                    radius=max(1, px(2)),
                    fill=palette.green if checked else palette.track,
                    outline=palette.green if checked else palette.muted,
                    width=max(1, px(1)),
                )
            if checked and not radio:
                draw.line(
                    (
                        x1 + px(3), y1 + px(8),
                        x1 + px(7), y1 + px(12),
                        x1 + px(13), y1 + px(4),
                    ),
                    fill=palette.surface_solid,
                    width=max(2, px(2)),
                    joint="curve",
                )
            _text(draw, (43, top + 20), label, 13, False, render_scale, palette.text)
        draw.line(
            (px(17), px(211), render_width - px(17), px(211)),
            fill=line,
            width=px(1),
        )
        note = _visibility_note(mode, config.taskbar_visible)
        _text(draw, (17, 234), note, 11, False, render_scale, palette.muted)
        image = image.resize((width, height), Image.Resampling.LANCZOS)
        image.putalpha(_panel_mask(width, height, round(12 * scale)))
        self._icon = ImageTk.PhotoImage(image, master=canvas)
        _ = canvas.delete("all")
        _ = canvas.create_image(0, 0, image=self._icon, anchor="nw")

    def _row_at(self, y: int) -> int | None:
        canvas = self._canvas
        if canvas is None:
            return None
        scale = int(canvas.cget("width")) / _WIDTH
        logical_y = y / scale
        row_bottom = _ROW_TOP + _ROW_HEIGHT * _ROW_COUNT
        if _ROW_TOP <= logical_y < row_bottom:
            return int((logical_y - _ROW_TOP) // _ROW_HEIGHT)
        return None

    def _motion(self, event: tk.Event[tk.Misc]) -> None:
        hover = self._row_at(event.y)
        if hover != self._hover:
            self._hover = hover
            self._draw()

    def _leave(self, _event: tk.Event[tk.Misc]) -> None:
        if self._hover is not None:
            self._hover = None
            self._draw()

    def _click(self, event: tk.Event[tk.Misc]) -> None:
        row = self._row_at(event.y)
        if row is not None:
            callbacks = (
                self._callbacks.normal,
                self._callbacks.mini,
                self._callbacks.hidden,
                self._callbacks.taskbar,
            )
            callbacks[row]()

    def _focus_out(self, _event: tk.Event[tk.Misc]) -> None:
        window = self._window
        if window is None:
            return

        def close_if_outside() -> None:
            if self._window is not window:
                return
            button_state = _left_button_state()
            point = _cursor_position()
            on_trigger = (
                point is not None and self._callbacks.trigger_contains(*point)
            )
            if on_trigger:
                if button_state & 0x8000:
                    _ = window.after(25, close_if_outside)
                    return

                def close_if_release_was_not_delivered() -> None:
                    # The native release toggle normally destroys this exact
                    # window through Runtime's queue. This fallback handles a
                    # lost release and keyboard focus changes without reopening.
                    if self._window is window:
                        self.close()

                _ = window.after(200, close_if_release_was_not_delivered)
                return
            if button_state & 0x8000:
                _ = window.after(25, close_if_outside)
                return
            focused = window.focus_get()
            if focused is None or focused.winfo_toplevel() is not window:
                self.close()

        _ = window.after_idle(close_if_outside)

    def _reassert_toolwindow(self, window: tk.Toplevel) -> None:
        if self._window is window and window.winfo_exists():
            _ = hide_from_taskbar(window.winfo_id())


def _visibility_note(mode: DesktopMode, taskbar: bool) -> str:
    surface = {
        DesktopMode.NORMAL: "일반 위젯",
        DesktopMode.MINI: "미니 위젯",
        DesktopMode.HIDDEN: "바탕화면 숨김",
    }[mode]
    taskbar_text = "작업표시줄 표시" if taskbar else "작업표시줄 숨김"
    return f"{surface} · {taskbar_text}"


def _left_button_state() -> int:
    if sys.platform != "win32":
        return 0
    try:
        user32 = ctypes.WinDLL("user32")
        user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
        user32.GetAsyncKeyState.restype = ctypes.c_short
        return int(user32.GetAsyncKeyState(1)) & 0xFFFF
    except (AttributeError, OSError):
        return 0


def visibility_panel_size(dpi: int) -> tuple[int, int]:
    """Return the approved CSS card dimensions in physical pixels."""
    scale = max(96, dpi) / 96
    return round(_WIDTH * scale), math.ceil(_HEIGHT * scale)


def place_avoiding_rect(
    avoid: tuple[int, int, int, int],
    width: int,
    height: int,
    bounds: tuple[int, int, int, int],
    *,
    gap: int = 8,
) -> tuple[int, int]:
    """Place beside a desktop card without covering its brand trigger."""
    left, top, right, bottom = bounds
    avoid_left, avoid_top, avoid_right, avoid_bottom = avoid
    candidates = (
        (avoid_right + gap, avoid_top),
        (avoid_left - width - gap, avoid_top),
        (avoid_left, avoid_bottom + gap),
        (avoid_left, avoid_top - height - gap),
    )
    for x, y in candidates:
        if left <= x and x + width <= right and top <= y and y + height <= bottom:
            return x, y
    # Extremely small work areas cannot fit both rectangles. Clamp the card and
    # prefer the side with more space, which minimizes overlap deterministically.
    right_space = right - avoid_right
    left_space = avoid_left - left
    x = avoid_right + gap if right_space >= left_space else avoid_left - width - gap
    return max(left, min(x, right - width)), max(top, min(avoid_top, bottom - height))


def _cursor_position() -> tuple[int, int] | None:
    if sys.platform != "win32":
        return None
    try:
        user32 = ctypes.WinDLL("user32")
        point = wintypes.POINT()
        user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
        user32.GetCursorPos.restype = ctypes.c_int
        if user32.GetCursorPos(ctypes.byref(point)):
            return point.x, point.y
    except (AttributeError, OSError):
        pass
    return None


def _codex_image(size: int, color: str) -> Image.Image | None:
    try:
        with Image.open(io.BytesIO(load_tray_png()), formats=("PNG",)) as source:
            alpha = source.convert("RGBA").getchannel("A").resize(
                (size, size), Image.Resampling.LANCZOS
            )
    except (OSError, SyntaxError):
        return None
    rgb = tuple(int(color[index : index + 2], 16) for index in (1, 3, 5))
    tinted = Image.new("RGBA", (size, size), (*rgb, 0))
    tinted.putalpha(alpha)
    return tinted


def _text(  # noqa: PLR0913, PLR0917
    draw: ImageDraw.ImageDraw,
    point: tuple[int, int],
    value: str,
    size: int,
    bold: bool,
    scale: float,
    color: str,
) -> None:
    _ = draw.text(
        (round(point[0] * scale), round(point[1] * scale)),
        value,
        font=_font(size, bold, scale),
        fill=color,
        anchor="lm",
    )


@lru_cache(maxsize=16)
def _font(
    logical_size: int, bold: bool, scale: float
) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    size = max(1, round(logical_size * scale))
    candidates = ("malgunbd.ttf", "malgun.ttf") if bold else ("malgun.ttf",)
    for name in candidates:
        try:
            return ImageFont.truetype(_FONT_ROOT / name, size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def _panel_mask(width: int, height: int, radius: int) -> Image.Image:
    """Return a binary rounded mask that prevents resampled edge halos."""
    mask = Image.new("L", (width, height))
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle(
        (0, 0, width - 1, height - 1),
        radius=radius,
        fill=255,
    )
    return mask


def _blend(background: str, foreground: tuple[int, int, int, int]) -> str:
    """Blend an RGBA design token onto the panel's solid surface."""
    base = tuple(int(background[index : index + 2], 16) for index in (1, 3, 5))
    alpha = foreground[3] / 255
    channels = tuple(
        round(front * alpha + back * (1 - alpha))
        for front, back in zip(foreground[:3], base, strict=True)
    )
    return "#" + "".join(f"{channel:02x}" for channel in channels)


__all__ = [
    "VisibilityCallbacks",
    "VisibilityPanel",
    "place_avoiding_rect",
    "visibility_panel_size",
]
