# pyright: reportPrivateUsage=false
from typing import final

from codex_usage_widget.actions import DesktopMode
from codex_usage_widget.tray import TrayCallbacks, TrayController


@final
class _FailingIcon:
    stopped = False

    def run(self) -> None:
        raise RuntimeError

    def stop(self) -> None:
        self.stopped = True

    def update_menu(self) -> None:
        return None


@final
class _MenuIcon:
    title = "Codex 사용량"

    def __init__(self, *, fail: bool = False) -> None:
        self.updated = 0
        self._fail = fail

    def run(self) -> None:
        return None

    def stop(self) -> None:
        return None

    def update_menu(self) -> None:
        self.updated += 1
        if self._fail:
            raise RuntimeError


@final
class _TestableTrayController(TrayController):
    def run_failing_icon(self, icon: _FailingIcon) -> None:
        self._icon = icon
        self._available = True
        self._run_icon()

    def install_menu_icon(self, icon: _MenuIcon) -> None:
        self._icon = icon
        self._available = True


def test_tray_availability_clears_when_backend_thread_fails() -> None:
    # Given
    controller = _TestableTrayController(lambda: None, lambda: None)

    # When
    controller.run_failing_icon(_FailingIcon())

    # Then
    assert controller.available is False


def test_tray_commands_forward_without_calling_tk() -> None:
    events: list[str] = []
    callbacks = TrayCallbacks(
        desktop_normal=lambda: events.append("normal"),
        desktop_mini=lambda: events.append("mini"),
        desktop_hidden=lambda: events.append("hidden"),
        toggle_taskbar=lambda: events.append("taskbar"),
        show_details=lambda: events.append("details"),
        desktop_mode=lambda: DesktopMode.MINI,
        taskbar_checked=lambda: True,
        refresh=lambda: events.append("refresh"),
    )
    controller = TrayController(
        lambda: events.append("show"),
        lambda: events.append("exit"),
        callbacks=callbacks,
    )

    controller._on_details(None, None)
    controller._on_desktop_normal(None, None)
    controller._on_desktop_mini(None, None)
    controller._on_desktop_hidden(None, None)
    controller._on_toggle_taskbar(None, None)
    controller._on_refresh(None, None)

    assert events == ["details", "normal", "mini", "hidden", "taskbar", "refresh"]


def test_refresh_menu_rebuilds_checked_state_and_contains_backend_failure() -> None:
    controller = _TestableTrayController(lambda: None, lambda: None)
    working = _MenuIcon()
    controller.install_menu_icon(working)

    controller.refresh_menu()

    assert working.updated == 1
    assert controller.available is True

    failing = _MenuIcon(fail=True)
    controller.install_menu_icon(failing)
    controller.refresh_menu()

    assert failing.updated == 1
    assert controller.available is False
