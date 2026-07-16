from __future__ import annotations

from typing import TYPE_CHECKING, final

if TYPE_CHECKING:
    from collections.abc import Callable

    import pytest

from codex_usage_widget.topmost import SmartTopmostController
from codex_usage_widget.window_runtime import ForegroundProcess, should_keep_topmost


@final
class _TopmostRoot:
    def __init__(self) -> None:
        self.topmost_values: list[bool] = []
        self.cancelled: list[str] = []
        self.grabbed: _TopmostRoot | None = None

    def after(self, ms: int, func: Callable[[], None]) -> str:
        del ms, func
        return "timer-1"

    def after_cancel(self, id: str) -> None:  # noqa: A002
        self.cancelled.append(id)

    def focus_get(self) -> None:
        return None

    def grab_current(self) -> _TopmostRoot | None:
        return self.grabbed

    def set_topmost(self, value: bool) -> str:
        self.topmost_values.append(value)
        return ""

    def winfo_id(self) -> int:
        return 42


def test_smart_topmost_requires_focus_or_a_codex_foreground_context() -> None:
    # Given
    ordinary = ForegroundProcess(name="explorer.exe", related_process_names=())
    codex_terminal = ForegroundProcess(
        name="WindowsTerminal.exe",
        related_process_names=("pwsh.exe", "codex.exe"),
    )

    # When / Then
    assert should_keep_topmost(True, widget_focused=True, foreground=ordinary) is True
    assert should_keep_topmost(True, widget_focused=False, foreground=codex_terminal)
    assert not should_keep_topmost(True, widget_focused=False, foreground=ordinary)
    assert not should_keep_topmost(
        False,
        widget_focused=True,
        foreground=codex_terminal,
    )


def test_smart_topmost_controller_cancels_its_timer_on_stop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given
    root = _TopmostRoot()
    monkeypatch.setattr(
        "codex_usage_widget.topmost.read_foreground_process",
        lambda: ForegroundProcess(name="codex.exe", related_process_names=()),
    )
    controller = SmartTopmostController(root, lambda: True, root.set_topmost)

    # When
    controller.apply()
    controller.start()
    controller.stop()

    # Then
    assert root.topmost_values == [True]
    assert root.cancelled == ["timer-1"]


def test_smart_topmost_does_not_raise_parent_while_context_menu_is_open(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given
    root = _TopmostRoot()
    monkeypatch.setattr(
        "codex_usage_widget.topmost.read_foreground_process",
        lambda: ForegroundProcess(name="codex.exe", related_process_names=()),
    )
    controller = SmartTopmostController(root, lambda: True, root.set_topmost)
    controller.apply()

    # When
    root.grabbed = root
    controller.apply()
    root.grabbed = None
    controller.apply()

    # Then
    assert root.topmost_values == [True, True]


def test_smart_topmost_lowers_parent_until_context_menu_closes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given
    root = _TopmostRoot()
    monkeypatch.setattr(
        "codex_usage_widget.topmost.read_foreground_process",
        lambda: ForegroundProcess(name="codex.exe", related_process_names=()),
    )
    controller = SmartTopmostController(root, lambda: True, root.set_topmost)
    controller.apply()

    # When
    controller.suspend()
    controller.apply()
    controller.resume()

    # Then
    assert root.topmost_values == [True, False, True]
