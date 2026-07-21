from __future__ import annotations

from typing import TYPE_CHECKING, Literal, final

if TYPE_CHECKING:
    from collections.abc import Callable

    import pytest

from codex_usage_widget.topmost import SmartTopmostController
from codex_usage_widget.window_runtime import ForegroundProcess


def _codex_foreground() -> ForegroundProcess:
    return ForegroundProcess(name="codex.exe", related_process_names=())


def _other_foreground() -> ForegroundProcess:
    return ForegroundProcess(name="explorer.exe", related_process_names=())


@final
class _TopmostRoot:
    def __init__(self) -> None:
        self.topmost_values: list[bool] = []
        self.cancelled: list[str] = []
        self.grabbed: _TopmostRoot | None = None
        self.focused: _TopmostRoot | None = None

    def after(self, ms: int, func: Callable[[], None]) -> str:
        del ms, func
        return "timer-1"

    def after_cancel(self, id: str) -> None:  # noqa: A002
        self.cancelled.append(id)

    def focus_get(self) -> _TopmostRoot | None:
        return self.focused

    def grab_current(self) -> _TopmostRoot | None:
        return self.grabbed

    def set_topmost(self, value: bool) -> str:
        self.topmost_values.append(value)
        return ""

    def winfo_id(self) -> int:
        return 42


def test_smart_topmost_tracks_foreground_codex_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given
    root = _TopmostRoot()
    foregrounds = iter((_codex_foreground(), _other_foreground()))
    layers: list[str] = []
    monkeypatch.setattr(
        "codex_usage_widget.topmost.read_foreground_process",
        lambda: next(foregrounds),
    )

    def record_layer(_hwnd: int, layer: Literal["top", "bottom"]) -> bool:
        layers.append(layer)
        return True

    monkeypatch.setattr(
        "codex_usage_widget.topmost.set_window_zorder",
        record_layer,
    )
    controller = SmartTopmostController(root, lambda: True, root.set_topmost)

    # When
    controller.apply()
    controller.apply()

    # Then
    assert root.topmost_values == [True, False]
    assert layers == ["top", "bottom"]


def test_smart_topmost_stays_topmost_while_widget_owns_focus(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given
    root = _TopmostRoot()
    root.focused = root
    monkeypatch.setattr(
        "codex_usage_widget.topmost.read_foreground_process",
        _other_foreground,
    )
    controller = SmartTopmostController(root, lambda: True, root.set_topmost)

    # When
    controller.apply()

    # Then
    assert root.topmost_values == [True]


def test_smart_topmost_controller_cancels_its_timer_on_stop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given
    root = _TopmostRoot()
    monkeypatch.setattr(
        "codex_usage_widget.topmost.read_foreground_process",
        _codex_foreground,
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
        _codex_foreground,
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
        _codex_foreground,
    )
    controller = SmartTopmostController(root, lambda: True, root.set_topmost)
    controller.apply()
    root.grabbed = root

    # When
    controller.suspend()
    controller.apply()
    root.grabbed = None
    controller.resume()

    # Then
    assert root.topmost_values == [True, False, True]


def test_smart_topmost_recovers_when_menu_close_callback_is_missed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given
    root = _TopmostRoot()
    monkeypatch.setattr(
        "codex_usage_widget.topmost.read_foreground_process",
        _codex_foreground,
    )
    controller = SmartTopmostController(root, lambda: True, root.set_topmost)
    controller.apply()
    root.grabbed = root
    controller.suspend()
    controller.apply()

    # When
    root.grabbed = None
    controller.apply()

    # Then
    assert root.topmost_values == [True, False, True]
