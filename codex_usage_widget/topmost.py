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
    import tkinter as tk
    from collections.abc import Callable

    class _GrabOwner(Protocol): ...

    class _TopmostRoot(Protocol):
        def after(self, ms: int, func: Callable[[], None]) -> str: ...

        def after_cancel(self, id: str) -> None: ...  # noqa: A002

        def focus_get(self) -> tk.Misc | None: ...

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

    def apply(self) -> None:
        """Apply the current foreground-sensitive topmost decision once."""
        if self._root.grab_current() is not None:
            return
        keep = should_keep_topmost(
            self._smart_enabled(),
            widget_focused=self._root.focus_get() is not None,
            foreground=read_foreground_process(),
        )
        self._set_zorder("top" if keep else "bottom")

    def suspend(self) -> None:
        """Lower the widget while a popup menu owns the foreground."""
        self._set_zorder("bottom")

    def resume(self) -> None:
        """Resume foreground-sensitive topmost behavior after a popup closes."""
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
        _ = self._set_topmost(layer == "top")
        _ = set_window_zorder(self._root.winfo_id(), layer)

    def _tick(self) -> None:
        self.apply()
        self._timer = self._root.after(750, self._tick)
