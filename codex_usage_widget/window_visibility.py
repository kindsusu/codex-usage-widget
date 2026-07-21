"""Native taskbar and z-order state application for a materialized Tk window."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from codex_usage_widget.windows import hide_from_taskbar

if TYPE_CHECKING:
    from collections.abc import Callable

    class _NativeRoot(Protocol):
        def winfo_id(self) -> int: ...


def apply_native_window_state(
    root: _NativeRoot,
    apply_layer: Callable[[], None],
) -> None:
    """Hide the materialized native wrapper before applying its live layer."""
    _ = hide_from_taskbar(root.winfo_id())
    apply_layer()
