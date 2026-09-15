"""Public, platform-safe facade for the embedded taskbar widget."""

from collections.abc import Callable
from typing import final

from codex_usage_widget.taskbar_model import TaskbarModel
from codex_usage_widget.taskbar_native import (
    NativeTaskbarHost,
    StripPlacement,
)
from codex_usage_widget.taskbar_placement import DropDecision


@final
class TaskbarController:
    """Thread-safe controller that never calls Tk from native callbacks."""

    def __init__(
        self,
        on_details: Callable[[int, int], None],
        on_visibility: Callable[[int, int], None],
        on_menu: Callable[[int, int], None],
        on_move: Callable[[DropDecision], None] | None = None,
        on_priority: Callable[[bool], None] | None = None,
    ) -> None:
        """Bind screen-coordinate callbacks without starting native work."""
        self._host = NativeTaskbarHost(
            on_details, on_visibility, on_menu, on_move, on_priority
        )

    @property
    def available(self) -> bool:
        """Whether the private native worker is alive."""
        return self._host.available

    @property
    def attached(self) -> bool:
        """Whether the owned HWND is currently embedded and placeable."""
        return self._host.attached

    @property
    def hwnd(self) -> int:
        """Return the owned native handle for diagnostics."""
        return self._host.hwnd

    def start(self) -> bool:
        """Start the bounded native worker; repeated calls are safe."""
        return self._host.start()

    @property
    def host_fallback(self) -> bool:
        """Whether the strip currently sits on a fallback taskbar."""
        return self._host.host_fallback

    def set_visible(self, visible: bool) -> None:
        """Request visibility without blocking the caller."""
        self._host.set_visible(visible)

    def set_placement(self, placement: StripPlacement) -> None:
        """Publish new saved placement settings to the native worker."""
        self._host.set_placement(placement)

    def update(self, model: TaskbarModel) -> None:
        """Publish the latest immutable render model."""
        self._host.update(model)

    def suppress_held_menu_release(self) -> bool:
        """Consume the release that follows a held popup-dismissal press."""
        return self._host.suppress_held_menu_release()

    def menu_button_contains_screen(self, x: int, y: int) -> bool:
        """Return whether a screen point is over the current Codex button."""
        return self._host.menu_button_contains_screen(x, y)

    def stop(self) -> None:
        """Stop the worker and destroy only its owned HWND."""
        self._host.stop()


__all__ = ["StripPlacement", "TaskbarController", "TaskbarModel"]
