# pyright: reportAttributeAccessIssue=false, reportMissingTypeStubs=false, reportUnannotatedClassAttribute=false, reportUnknownArgumentType=false, reportUnknownLambdaType=false, reportUnknownMemberType=false, reportUnknownVariableType=false
"""Optional system-tray adapter that never calls Tk from its worker thread."""

from __future__ import annotations

import io
from dataclasses import dataclass
from threading import Thread
from typing import TYPE_CHECKING, Protocol

from PIL import Image

from codex_usage_widget.assets import load_tray_png

if TYPE_CHECKING:
    from collections.abc import Callable


class _TrayIcon(Protocol):
    def run(self) -> None: ...

    def stop(self) -> None: ...

    def update_menu(self) -> None: ...


class _TrayEvent(Protocol):
    pass


@dataclass(frozen=True, slots=True)
class TrayCallbacks:
    """Optional tray commands and live checked-state providers."""

    toggle_desktop: Callable[[], None]
    toggle_mini: Callable[[], None]
    toggle_taskbar: Callable[[], None]
    show_details: Callable[[], None]
    desktop_checked: Callable[[], bool]
    mini_checked: Callable[[], bool]
    taskbar_checked: Callable[[], bool]
    refresh: Callable[[], None]


class TrayController:
    """Own a pystray icon while emitting only thread-safe callbacks."""

    _show: Callable[[], None]
    _exit: Callable[[], None]
    _icon: _TrayIcon | None
    _available: bool

    def __init__(
        self,
        show: Callable[[], None],
        exit_app: Callable[[], None],
        *,
        callbacks: TrayCallbacks | None = None,
    ) -> None:
        """Store callbacks without importing the optional tray package."""
        self._show = show
        self._exit = exit_app
        resolved = callbacks or TrayCallbacks(
            toggle_desktop=show,
            toggle_mini=lambda: None,
            toggle_taskbar=lambda: None,
            show_details=show,
            desktop_checked=lambda: True,
            mini_checked=lambda: False,
            taskbar_checked=lambda: False,
            refresh=lambda: None,
        )
        self._toggle_desktop = resolved.toggle_desktop
        self._toggle_mini = resolved.toggle_mini
        self._toggle_taskbar = resolved.toggle_taskbar
        self._show_details = resolved.show_details
        self._desktop_checked = resolved.desktop_checked
        self._mini_checked = resolved.mini_checked
        self._taskbar_checked = resolved.taskbar_checked
        self._refresh = resolved.refresh
        self._icon = None
        self._available = False

    @property
    def available(self) -> bool:
        """Report whether a live tray restoration path exists."""
        return self._available

    def start(self) -> bool:
        """Start the optional tray loop and report whether it was available."""
        try:
            import pystray  # noqa: PLC0415 -- optional integration boundary
        except ImportError:
            return False
        image = Image.open(io.BytesIO(load_tray_png())).convert("RGBA")
        menu = pystray.Menu(
            pystray.MenuItem("사용량 상세", self._on_details, default=True),
            pystray.MenuItem(
                "데스크톱 표시",
                self._on_toggle_desktop,
                checked=lambda _item: self._desktop_checked(),
            ),
            pystray.MenuItem(
                "데스크톱 미니모드",
                self._on_toggle_mini,
                checked=lambda _item: self._mini_checked(),
            ),
            pystray.MenuItem(
                "작업표시줄 표시",
                self._on_toggle_taskbar,
                checked=lambda _item: self._taskbar_checked(),
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("새로고침", self._on_refresh),
            pystray.MenuItem("종료", self._on_exit),
        )
        icon = pystray.Icon("codex-usage-widget", image, "Codex 사용량", menu)
        self._icon = icon
        self._available = True
        _ = Thread(target=self._run_icon, daemon=True).start()
        return True

    def stop(self) -> None:
        """Stop the tray loop when one was created."""
        self._available = False
        if self._icon is not None:
            self._icon.stop()
            self._icon = None

    def set_status(self, status: str | None) -> None:
        """Expose an effective-surface fallback in the tray tooltip."""
        if self._icon is not None:
            self._icon.title = (
                "Codex 사용량" if status is None else f"Codex 사용량 · {status}"
            )

    def refresh_menu(self) -> None:
        """Rebuild checked states after queued settings have been persisted."""
        icon = self._icon
        if icon is None or not self._available:
            return
        try:
            icon.update_menu()
        except Exception:  # noqa: BLE001  # noqa: BROAD_EXCEPT_OK
            self._available = False

    def _run_icon(self) -> None:
        icon = self._icon
        if icon is None:
            return
        try:
            icon.run()
        except Exception:  # noqa: BLE001  # noqa: BROAD_EXCEPT_OK
            self._available = False
        finally:
            self._available = False

    def _on_show(self, _icon: _TrayEvent, _item: _TrayEvent) -> None:
        self._show()

    def _on_details(self, _icon: _TrayEvent, _item: _TrayEvent) -> None:
        self._show_details()

    def _on_toggle_desktop(self, _icon: _TrayEvent, _item: _TrayEvent) -> None:
        self._toggle_desktop()

    def _on_toggle_mini(self, _icon: _TrayEvent, _item: _TrayEvent) -> None:
        self._toggle_mini()

    def _on_toggle_taskbar(self, _icon: _TrayEvent, _item: _TrayEvent) -> None:
        self._toggle_taskbar()

    def _on_refresh(self, _icon: _TrayEvent, _item: _TrayEvent) -> None:
        self._refresh()

    def _on_exit(self, _icon: _TrayEvent, _item: _TrayEvent) -> None:
        self._exit()
