# pyright: reportAny=false, reportUnknownMemberType=false
"""Owned, DPI-aware opacity slider popup."""

from __future__ import annotations

import tkinter as tk
from contextlib import suppress
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, final

from codex_usage_widget.taskbar_details import monitor_metrics
from codex_usage_widget.theme import theme_tokens
from codex_usage_widget.visibility_panel import place_avoiding_rect
from codex_usage_widget.window_runtime import format_window_position
from codex_usage_widget.windows import hide_from_taskbar

if TYPE_CHECKING:
    from collections.abc import Callable

    from codex_usage_widget.config import ThemeName

_WIDTH: Final = 240
_HEIGHT: Final = 112
_TRACK_LEFT: Final = 18
_TRACK_RIGHT: Final = 222
_TRACK_Y: Final = 72


@dataclass(frozen=True, slots=True)
class OpacityPopupCallbacks:
    """Lifecycle and value callbacks owned by Runtime."""

    changed: Callable[[float], None]
    opened: Callable[[], None]
    closed: Callable[[], None]
    context_requested: Callable[[int, int], None]


@final
class OpacityPopupController:
    """Own exactly one non-modal opacity popup."""

    def __init__(self, root: tk.Tk, callbacks: OpacityPopupCallbacks) -> None:
        """Bind callbacks without creating a native window yet."""
        self._root = root
        self._callbacks = callbacks
        self._window: tk.Toplevel | None = None
        self._canvas: tk.Canvas | None = None
        self._value = 1.0
        self._theme: ThemeName | None = None
        self._scale = 1.0
        self._dragging = False

    @property
    def open(self) -> bool:
        """Return whether the controller owns a live popup window."""
        window = self._window
        if window is None:
            return False
        try:
            return bool(window.winfo_exists())
        except tk.TclError:
            return False

    @property
    def window(self) -> tk.Toplevel | None:
        """Expose the owned window for native smoke inspection."""
        return self._window if self.open else None

    def toggle(
        self,
        opacity: float,
        theme: ThemeName,
        avoid: tuple[int, int, int, int],
    ) -> None:
        """Close the current popup or open a fresh slider beside the widget."""
        if self.open:
            self.close()
            return
        self._value = _clamp_opacity(opacity)
        self._theme = theme
        anchor_x, anchor_y = avoid[2], avoid[1]
        bounds, dpi = monitor_metrics(anchor_x, anchor_y)
        self._scale = dpi / 96
        width, height = round(_WIDTH * self._scale), round(_HEIGHT * self._scale)
        if bounds is None:
            bounds = (
                self._root.winfo_vrootx(),
                self._root.winfo_vrooty(),
                self._root.winfo_vrootx() + self._root.winfo_vrootwidth(),
                self._root.winfo_vrooty() + self._root.winfo_vrootheight(),
            )
        left, top = place_avoiding_rect(avoid, width, height, bounds)
        tokens = theme_tokens(theme)
        window = tk.Toplevel(self._root)
        self._window = window
        _ = window.overrideredirect(True)
        _ = window.attributes("-topmost", True)
        _ = window.resizable(False, False)
        _ = window.configure(bg=tokens.surface_primary)
        _ = window.geometry(f"{width}x{height}{format_window_position(left, top)}")
        canvas = tk.Canvas(
            window,
            width=width,
            height=height,
            bg=tokens.surface_primary,
            highlightbackground=tokens.bar_background,
            highlightthickness=max(1, round(self._scale)),
            bd=0,
            cursor="hand2",
        )
        self._canvas = canvas
        _ = canvas.pack(fill="both", expand=True)
        _ = canvas.bind("<Button-1>", self._press)
        _ = canvas.bind("<B1-Motion>", self._drag)
        _ = canvas.bind("<ButtonRelease-1>", self._release)
        _ = window.bind("<Escape>", lambda _event: self.close())
        _ = window.bind("<FocusOut>", self._focus_out)
        _ = window.bind("<Button-3>", self._context_requested)
        self._draw()
        window.update_idletasks()
        _ = hide_from_taskbar(window.winfo_id())
        _ = window.after(100, lambda: self._reassert_toolwindow(window))
        self._callbacks.opened()
        _ = window.focus_force()

    def update(self, opacity: float, theme: ThemeName) -> None:
        """Refresh an open slider from the saved application state."""
        self._value = _clamp_opacity(opacity)
        self._theme = theme
        if self.open:
            self._draw()

    def close(self) -> None:
        """Destroy the owned popup and resume parent z-order handling."""
        window, self._window = self._window, None
        self._canvas = None
        self._dragging = False
        if window is None:
            return
        with suppress(tk.TclError):
            if window.winfo_exists():
                window.destroy()
        self._callbacks.closed()

    def _draw(self) -> None:
        canvas, theme = self._canvas, self._theme
        if canvas is None or theme is None:
            return
        tokens = theme_tokens(theme)
        def px(value: float) -> int:
            return round(value * self._scale)

        title_font = ("Malgun Gothic", -max(1, px(14)), "bold")
        value_font = ("Malgun Gothic", -max(1, px(13)))
        _ = canvas.delete("all")
        _ = canvas.create_text(
            px(18), px(25), text="투명도", anchor="w", fill=tokens.text_primary,
            font=title_font,
        )
        _ = canvas.create_text(
            px(222), px(25), text=f"{round(self._value * 100)}%", anchor="e",
            fill=tokens.text_secondary, font=value_font,
        )
        _ = canvas.create_line(
            px(_TRACK_LEFT), px(_TRACK_Y), px(_TRACK_RIGHT), px(_TRACK_Y),
            fill=tokens.bar_background, width=max(4, px(4)), capstyle=tk.ROUND,
        )
        thumb = _TRACK_LEFT + self._fraction * (_TRACK_RIGHT - _TRACK_LEFT)
        _ = canvas.create_line(
            px(_TRACK_LEFT), px(_TRACK_Y), px(thumb), px(_TRACK_Y),
            fill=tokens.accent_primary, width=max(4, px(4)), capstyle=tk.ROUND,
        )
        radius = px(7)
        center = px(thumb), px(_TRACK_Y)
        _ = canvas.create_oval(
            center[0] - radius, center[1] - radius,
            center[0] + radius, center[1] + radius,
            fill=tokens.surface_primary, outline=tokens.focus_ring,
            width=max(2, px(2)),
        )

    @property
    def _fraction(self) -> float:
        return (self._value - 0.3) / 0.7

    def _press(self, event: tk.Event[tk.Misc]) -> None:
        logical_y = event.y / self._scale
        if not (_TRACK_Y - 14 <= logical_y <= _TRACK_Y + 14):
            return
        self._dragging = True
        self._change_at(event.x)

    def _drag(self, event: tk.Event[tk.Misc]) -> None:
        if self._dragging:
            self._change_at(event.x)

    def _release(self, _event: tk.Event[tk.Misc]) -> None:
        self._dragging = False

    def _change_at(self, physical_x: int) -> None:
        logical_x = physical_x / self._scale
        fraction = (logical_x - _TRACK_LEFT) / (_TRACK_RIGHT - _TRACK_LEFT)
        self._value = round(0.3 + max(0.0, min(1.0, fraction)) * 0.7, 3)
        self._draw()
        self._callbacks.changed(self._value)

    def _focus_out(self, _event: tk.Event[tk.Misc]) -> None:
        window = self._window
        if window is None:
            return

        def close_if_outside() -> None:
            if self._window is not window:
                return
            try:
                focused = window.focus_get()
                outside = focused is None or focused.winfo_toplevel() is not window
            except tk.TclError:
                outside = True
            if outside:
                self.close()

        # Let focus settle after slider redraws and native z-order changes.
        _ = window.after(30, close_if_outside)

    def _context_requested(self, event: tk.Event[tk.Misc]) -> None:
        x, y = event.x_root, event.y_root
        self.close()
        with suppress(tk.TclError):
            _ = self._root.after_idle(lambda: self._callbacks.context_requested(x, y))

    def _reassert_toolwindow(self, window: tk.Toplevel) -> None:
        with suppress(tk.TclError):
            if self._window is window and window.winfo_exists():
                _ = hide_from_taskbar(window.winfo_id())


def _clamp_opacity(value: float) -> float:
    return max(0.3, min(1.0, value))


__all__ = ["OpacityPopupCallbacks", "OpacityPopupController"]
