# pyright: reportMissingTypeStubs=false, reportUnknownArgumentType=false, reportUnknownMemberType=false, reportUnknownVariableType=false
"""Optional system-tray adapter that never calls Tk from its worker thread."""

from __future__ import annotations

import io
from threading import Thread
from typing import TYPE_CHECKING, Protocol

from PIL import Image

from codex_usage_widget.assets import load_tray_png

if TYPE_CHECKING:
    from collections.abc import Callable


class _TrayIcon(Protocol):
    def run(self) -> None: ...

    def stop(self) -> None: ...


class _TrayEvent(Protocol):
    pass


class TrayController:
    """Own a pystray icon while emitting only thread-safe callbacks."""

    _show: Callable[[], None]
    _exit: Callable[[], None]
    _icon: _TrayIcon | None
    _available: bool

    def __init__(self, show: Callable[[], None], exit_app: Callable[[], None]) -> None:
        """Store callbacks without importing the optional tray package."""
        self._show = show
        self._exit = exit_app
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
            pystray.MenuItem("위젯 열기", self._on_show, default=True),
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

    def _on_exit(self, _icon: _TrayEvent, _item: _TrayEvent) -> None:
        self._exit()
