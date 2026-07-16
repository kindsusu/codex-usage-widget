from typing import final

from codex_usage_widget.tray import TrayController


@final
class _FailingIcon:
    stopped = False

    def run(self) -> None:
        raise RuntimeError

    def stop(self) -> None:
        self.stopped = True


@final
class _TestableTrayController(TrayController):
    def run_failing_icon(self, icon: _FailingIcon) -> None:
        self._icon = icon
        self._available = True
        self._run_icon()


def test_tray_availability_clears_when_backend_thread_fails() -> None:
    # Given
    controller = _TestableTrayController(lambda: None, lambda: None)

    # When
    controller.run_failing_icon(_FailingIcon())

    # Then
    assert controller.available is False
