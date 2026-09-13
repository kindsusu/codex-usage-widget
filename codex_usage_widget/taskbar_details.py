# pyright: reportAny=false, reportUnknownMemberType=false, reportUnannotatedClassAttribute=false
"""Tk-owned usage details popup opened from the native taskbar surface."""

from __future__ import annotations

import ctypes
import os
import tkinter as tk
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Final

from codex_usage_widget.presentation import present_snapshot
from codex_usage_widget.service import RefreshStatus, failure_message
from codex_usage_widget.theme import theme_tokens
from codex_usage_widget.window_runtime import format_window_position

if TYPE_CHECKING:
    from codex_usage_widget.config import ThemeName
    from codex_usage_widget.service import WidgetState

_WIDTH_LOGICAL: Final = 292
_MONITOR_DEFAULTTONEAREST: Final = 2
_DEFAULT_DPI: Final = 96


def bounded_popup_position(
    anchor_x: int,
    anchor_y: int,
    width: int,
    height: int,
    bounds: tuple[int, int, int, int],
) -> tuple[int, int]:
    """Place a popup above its anchor and clamp it to visible bounds."""
    left, top, right, bottom = bounds
    x = anchor_x - width // 2
    y = anchor_y - height - 8
    return (
        max(left, min(x, right - width)),
        max(top, min(y, bottom - height)),
    )


class TaskbarDetailsPopup:
    """Own at most one non-modal detail window on Tk's UI thread."""

    def __init__(self, root: tk.Tk) -> None:
        """Bind popup lifecycle to the application root."""
        self._root = root
        self._window: tk.Toplevel | None = None
        self._anchor = (0, 0)

    @property
    def open(self) -> bool:
        """Report whether a live detail window exists."""
        return self._window is not None and bool(self._window.winfo_exists())

    def toggle(self, x: int, y: int, state: WidgetState, theme: ThemeName) -> None:
        """Close an open popup or create one at the taskbar click point."""
        if self.open:
            self.close()
            return
        self._anchor = (x, y)
        self._window = tk.Toplevel(self._root)
        _ = self._window.overrideredirect(True)
        _ = self._window.attributes("-topmost", True)
        _ = self._window.resizable(False, False)
        _ = self._window.bind("<Escape>", lambda _event: self.close())
        _ = self._window.bind("<FocusOut>", lambda _event: self.close())
        self.update(state, theme)
        _ = self._window.focus_force()

    def update(self, state: WidgetState, theme: ThemeName) -> None:
        """Replace popup contents with the latest shared service state."""
        window = self._window
        if window is None or not window.winfo_exists():
            self._window = None
            return
        tokens = theme_tokens(theme)
        bounds, dpi = monitor_metrics(*self._anchor)
        scale = dpi / _DEFAULT_DPI
        width = round(_WIDTH_LOGICAL * scale)

        def pixels(logical: int) -> int:
            return max(1, round(logical * scale))

        for child in window.winfo_children():
            child.destroy()
        _ = window.configure(bg=tokens.surface_primary)
        shell = tk.Frame(
            window,
            bg=tokens.surface_primary,
            highlightbackground=tokens.bar_background,
            highlightthickness=1,
            padx=pixels(12),
            pady=pixels(10),
        )
        _ = shell.pack(fill="both", expand=True)
        model = (
            None
            if state.snapshot is None
            else present_snapshot(state.snapshot, datetime.now(tz=UTC))
        )
        title = "Codex 사용량" if model is None else model.title
        _add_label(shell, title, tokens.text_primary, pixels(14), bold=True)
        if model is None:
            message = (
                failure_message(state.failure)
                if state.failure is not None
                else "Codex 사용량을 확인하는 중…"
            )
            _add_label(
                shell,
                message,
                tokens.text_secondary,
                pixels(12),
                pady=(pixels(8), pixels(3)),
            )
        else:
            for row in model.rows:
                remaining = max(0.0, min(100.0, 100.0 - row.window.used_percent))
                text = f"{row.label}  {remaining:g}% 남음"
                _add_label(
                    shell,
                    text,
                    tokens.text_primary,
                    pixels(12),
                    pady=(pixels(8), 0),
                )
                _add_label(shell, row.reset_text, tokens.text_secondary, pixels(11))
        status = _status_text(state, model.status_text if model is not None else "")
        _add_label(
            shell,
            status,
            tokens.text_muted,
            pixels(11),
            pady=(pixels(9), 0),
        )
        window.update_idletasks()
        height = window.winfo_reqheight()
        if bounds is None:
            bounds = (
                self._root.winfo_vrootx(),
                self._root.winfo_vrooty(),
                self._root.winfo_vrootx() + self._root.winfo_vrootwidth(),
                self._root.winfo_vrooty() + self._root.winfo_vrootheight(),
            )
        x, y = bounded_popup_position(*self._anchor, width, height, bounds)
        position = format_window_position(x, y)
        _ = window.geometry(f"{width}x{height}{position}")

    def close(self) -> None:
        """Destroy the popup without changing either visibility preference."""
        window, self._window = self._window, None
        if window is not None and window.winfo_exists():
            window.destroy()



def _add_label(  # noqa: PLR0913
    parent: tk.Misc,
    text: str,
    color: str,
    size: int,
    *,
    bold: bool = False,
    pady: tuple[int, int] = (0, 0),
) -> None:
    """Add one consistently styled text row."""
    label = tk.Label(
        parent,
        text=text,
        bg=str(parent.cget("bg")),
        fg=color,
        anchor="w",
        justify="left",
        font=("Segoe UI", -size, "bold" if bold else "normal"),
    )
    _ = label.pack(fill="x", pady=pady)


def monitor_work_area(x: int, y: int) -> tuple[int, int, int, int] | None:
    """Return the nearest Windows monitor's usable rectangle."""
    return monitor_metrics(x, y)[0]


def monitor_metrics(
    x: int,
    y: int,
) -> tuple[tuple[int, int, int, int] | None, int]:
    """Return nearest work area and effective DPI in physical coordinates."""
    if os.name != "nt":
        return None, _DEFAULT_DPI

    class _Point(ctypes.Structure):
        _fields_ = (("x", ctypes.c_long), ("y", ctypes.c_long))

    class _Rect(ctypes.Structure):
        _fields_ = (
            ("left", ctypes.c_long),
            ("top", ctypes.c_long),
            ("right", ctypes.c_long),
            ("bottom", ctypes.c_long),
        )

    class _MonitorInfo(ctypes.Structure):
        _fields_ = (
            ("cbSize", ctypes.c_ulong),
            ("rcMonitor", _Rect),
            ("rcWork", _Rect),
            ("dwFlags", ctypes.c_ulong),
        )

    try:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.MonitorFromPoint.argtypes = [_Point, ctypes.c_ulong]
        user32.MonitorFromPoint.restype = ctypes.c_void_p
        monitor = user32.MonitorFromPoint(_Point(x, y), _MONITOR_DEFAULTTONEAREST)
        info = _MonitorInfo(cbSize=ctypes.sizeof(_MonitorInfo))
        user32.GetMonitorInfoW.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(_MonitorInfo),
        ]
        user32.GetMonitorInfoW.restype = ctypes.c_int
        if not monitor or not user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
            return None, _DEFAULT_DPI
        dpi = _monitor_dpi(monitor)
    except (AttributeError, OSError, TypeError, ValueError):
        return None, _DEFAULT_DPI
    bounds = (info.rcWork.left, info.rcWork.top, info.rcWork.right, info.rcWork.bottom)
    return bounds, dpi


def _monitor_dpi(monitor: int) -> int:
    try:
        shcore = ctypes.WinDLL("shcore")
        dpi_x = ctypes.c_uint(_DEFAULT_DPI)
        dpi_y = ctypes.c_uint(_DEFAULT_DPI)
        shcore.GetDpiForMonitor.argtypes = [
            ctypes.c_void_p,
            ctypes.c_int,
            ctypes.POINTER(ctypes.c_uint),
            ctypes.POINTER(ctypes.c_uint),
        ]
        shcore.GetDpiForMonitor.restype = ctypes.c_long
        result = shcore.GetDpiForMonitor(
            monitor,
            0,
            ctypes.byref(dpi_x),
            ctypes.byref(dpi_y),
        )
        if result == 0:
            return max(_DEFAULT_DPI, int(dpi_x.value))
    except (AttributeError, OSError, TypeError, ValueError):
        pass
    return _DEFAULT_DPI


def _status_text(state: WidgetState, fresh_text: str) -> str:
    if state.failure is not None:
        prefix = "이전 데이터 · " if state.snapshot is not None else ""
        return prefix + failure_message(state.failure)
    if state.status is RefreshStatus.REFRESHING:
        return f"{fresh_text} · 새로고침 중…" if fresh_text else "새로고침 중…"
    return fresh_text or "최신 데이터를 기다리는 중"
