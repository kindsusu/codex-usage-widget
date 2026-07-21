# pyright: reportUnknownArgumentType=false, reportUnknownMemberType=false
"""Foreground-sensitive topmost lifecycle."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal, Protocol, final

from codex_usage_widget.window_runtime import (
    read_foreground_process,
    should_keep_topmost,
)
from codex_usage_widget.windows import set_window_zorder

if TYPE_CHECKING:
    from collections.abc import Callable

    class _GrabOwner(Protocol): ...

    class _TopmostRoot(Protocol):
        def after(self, ms: int, func: Callable[[], None]) -> str: ...

        def after_cancel(self, id: str) -> None: ...  # noqa: A002

        def focus_get(self) -> object | None: ...

        def grab_current(self) -> _GrabOwner | None: ...

        def winfo_id(self) -> int: ...


@final
class SmartTopmostController:
    """Own foreground-sensitive z-order polling and popup suspension."""

    def __init__(
        self,
        root: _TopmostRoot,
        smart_enabled: Callable[[], bool],
        set_topmost: Callable[[bool], str],
    ) -> None:
        """Bind a window and a live setting reader without starting polling."""
        self._root = root
        self._smart_enabled = smart_enabled
        self._set_topmost = set_topmost
        self._timer: str | None = None
        self._suspended = False
        # Last layer actually pushed to Win32. None means "unknown", forcing the
        # next apply() to reassert. SetWindowPos/-topmost only fire on a real
        # transition, so a steady poll never re-asserts TOPMOST -- re-asserting
        # is exactly what used to shove the widget above (then over) a menu.
        self._current_layer: Literal["top", "bottom"] | None = None

    def apply(self) -> None:
        """Apply the current foreground-sensitive topmost decision once."""
        # While a popup menu is open the widget must be FROZEN: not re-raised
        # (that flickered it over the menu) and not lowered (that hid it behind
        # other windows). A native Windows menu registers no Tk grab and the
        # 750 ms poll still fires inside tk_popup's modal loop, so the suspend
        # flag -- not grab_current() -- is the reliable freeze; grab_current()
        # still covers real Tk grabs.
        if self._suspended or self._root.grab_current() is not None:
            return
        keep = should_keep_topmost(
            self._smart_enabled(),
            widget_focused=self._root.focus_get() is not None,
            foreground=read_foreground_process(),
        )
        self._set_zorder("top" if keep else "bottom")

    def suspend(self) -> None:
        """Freeze z-order while a popup menu is open, leaving the widget put.

        The widget is NOT lowered: a native menu already renders above it, and
        lowering would hide the widget behind other windows. Freezing apply()
        stops the poll from re-asserting TOPMOST over the menu.
        """
        self._suspended = True

    def resume(self) -> None:
        """Unfreeze and force one reassert to correct any drift while frozen."""
        self._suspended = False
        self._current_layer = None
        self.apply()

    def start(self) -> None:
        """Start one polling timer when it is not already running."""
        if self._timer is None:
            self._timer = self._root.after(750, self._tick)

    def stop(self) -> None:
        """Cancel the polling timer before its Tk root is destroyed."""
        if self._timer is not None:
            self._root.after_cancel(self._timer)
            self._timer = None

    def _set_zorder(self, layer: Literal["top", "bottom"]) -> None:
        # Only touch Win32 on a real layer transition (Claude-widget parity):
        # a no-op poll must never call SetWindowPos, or it re-raises the widget.
        if layer == self._current_layer:
            return
        _ = self._set_topmost(layer == "top")
        _ = set_window_zorder(self._root.winfo_id(), layer)
        self._current_layer = layer

    def _tick(self) -> None:
        self.apply()
        self._timer = self._root.after(750, self._tick)
