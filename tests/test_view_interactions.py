# pyright: reportPrivateUsage=false
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, cast, final

from codex_usage_widget.desktop_render import DesktopHitRegions, HitRegion
from codex_usage_widget.view import ViewActions, WidgetView

if TYPE_CHECKING:
    import tkinter as tk


@dataclass
class _Event:
    x: int
    y: int
    x_root: int = 0
    y_root: int = 0


@final
class _Canvas:
    def __init__(self) -> None:
        self.focused: bool = False

    def focus_set(self) -> None:
        self.focused = True


def _event(x: int, y: int, *, x_root: int = 0, y_root: int = 0) -> tk.Event[tk.Misc]:
    return cast("tk.Event[tk.Misc]", cast("object", _Event(x, y, x_root, y_root)))


def _view(calls: list[tuple[str, int, int]]) -> WidgetView:
    view = object.__new__(WidgetView)
    view._regions = DesktopHitRegions(
        brand=HitRegion(10, 10, 40, 40),
        mode=HitRegion(100, 10, 170, 45),
    )
    view._canvas = cast("tk.Canvas", cast("object", _Canvas()))
    view._pressed_region = None
    view._actions = ViewActions(
        theme=lambda: None,
        opacity=lambda: None,
        mini=lambda: calls.append(("mode", 0, 0)),
        hide=lambda: None,
        refresh=lambda: None,
        menu=lambda _x, _y: None,
        visibility=lambda x, y: calls.append(("brand", x, y)),
    )
    return view


def test_body_drag_release_over_button_propagates_without_command() -> None:
    calls: list[tuple[str, int, int]] = []
    view = _view(calls)

    press_result = view._press(_event(60, 80))
    release_result = view._release(_event(120, 25))

    assert press_result is None
    assert release_result is None
    assert calls == []


def test_same_mode_button_press_and_release_invokes_once() -> None:
    calls: list[tuple[str, int, int]] = []
    view = _view(calls)

    press_result = view._press(_event(120, 25))
    release_result = view._release(_event(130, 30))

    assert press_result == "break"
    assert release_result == "break"
    assert calls == [("mode", 0, 0)]


def test_brand_click_forwards_release_screen_coordinates() -> None:
    calls: list[tuple[str, int, int]] = []
    view = _view(calls)

    assert view._press(_event(20, 20)) == "break"
    assert view._release(_event(25, 25, x_root=-120, y_root=480)) == "break"

    assert calls == [("brand", -120, 480)]


def test_button_press_released_on_different_region_is_cancelled() -> None:
    calls: list[tuple[str, int, int]] = []
    view = _view(calls)

    assert view._press(_event(20, 20)) == "break"
    assert view._release(_event(120, 25)) == "break"
    assert calls == []


def test_button_press_released_outside_controls_is_cancelled() -> None:
    calls: list[tuple[str, int, int]] = []
    view = _view(calls)

    assert view._press(_event(120, 25)) == "break"
    assert view._release(_event(60, 80)) == "break"
    assert calls == []
