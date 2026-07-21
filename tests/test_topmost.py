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


def _record_layers(
    monkeypatch: pytest.MonkeyPatch, layers: list[str]
) -> None:
    def record_layer(_hwnd: int, layer: Literal["top", "bottom"]) -> bool:
        layers.append(layer)
        return True

    monkeypatch.setattr(
        "codex_usage_widget.topmost.set_window_zorder",
        record_layer,
    )


def test_smart_topmost_only_touches_win32_on_a_layer_transition(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given the foreground never changes, so every poll wants the same layer.
    root = _TopmostRoot()
    layers: list[str] = []
    monkeypatch.setattr(
        "codex_usage_widget.topmost.read_foreground_process",
        _codex_foreground,
    )
    _record_layers(monkeypatch, layers)
    controller = SmartTopmostController(root, lambda: True, root.set_topmost)

    # When
    controller.apply()  # unknown -> top: one transition
    controller.apply()  # top -> top: no-op
    controller.apply()  # top -> top: no-op

    # Then a steady poll never re-asserts TOPMOST (the old over-the-menu bug).
    assert root.topmost_values == [True]
    assert layers == ["top"]


def test_smart_topmost_does_not_reassert_while_a_tk_grab_is_active(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given
    root = _TopmostRoot()
    layers: list[str] = []
    monkeypatch.setattr(
        "codex_usage_widget.topmost.read_foreground_process",
        _codex_foreground,
    )
    _record_layers(monkeypatch, layers)
    controller = SmartTopmostController(root, lambda: True, root.set_topmost)
    controller.apply()

    # When
    root.grabbed = root
    controller.apply()  # grab held -> early return
    root.grabbed = None
    controller.apply()  # top already cached -> no-op

    # Then
    assert root.topmost_values == [True]
    assert layers == ["top"]


def test_smart_topmost_freezes_in_place_while_a_menu_is_open(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given a native menu is open: it holds NO Tk grab (grab_current stays None)
    # yet the 750 ms poll still fires inside tk_popup's modal loop.
    root = _TopmostRoot()
    layers: list[str] = []
    monkeypatch.setattr(
        "codex_usage_widget.topmost.read_foreground_process",
        _codex_foreground,
    )
    _record_layers(monkeypatch, layers)
    controller = SmartTopmostController(root, lambda: True, root.set_topmost)
    controller.apply()  # -> top

    # When
    controller.suspend()  # menu opened: freeze in place, never lower
    controller.apply()  # poll during the menu
    controller.apply()  # ...every tick
    frozen_topmost = list(root.topmost_values)
    frozen_layers = list(layers)
    controller.resume()  # menu closed: reassert once to correct any drift

    # Then suspend and the polls touch Win32 zero times (widget never moves);
    # resume performs exactly one reassert of the same (top) layer.
    assert frozen_topmost == [True]
    assert frozen_layers == ["top"]
    assert root.topmost_values == [True, True]
    assert layers == ["top", "top"]
