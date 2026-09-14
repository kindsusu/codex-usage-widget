# pyright: reportPrivateUsage=false, reportAttributeAccessIssue=false
from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from collections.abc import Callable
    import tkinter as tk

from codex_usage_widget.config import ThemeName
from codex_usage_widget.opacity_popup import (
    OpacityPopupCallbacks,
    OpacityPopupController,
)


class _Canvas:
    def delete(self, _tag: str) -> None: ...

    def create_text(self, *_args: object, **_kwargs: object) -> int:
        return 1

    def create_line(self, *_args: object, **_kwargs: object) -> int:
        return 1

    def create_oval(self, *_args: object, **_kwargs: object) -> int:
        return 1


class _Root:
    def after_idle(self, callback: Callable[[], None]) -> str:
        callback()
        return "idle"


class _Window:
    def winfo_exists(self) -> bool:
        return True

    def destroy(self) -> None: ...


def _controller() -> OpacityPopupController:
    controller = OpacityPopupController.__new__(OpacityPopupController)
    controller._canvas = cast("tk.Canvas", cast("object", _Canvas()))
    controller._theme = ThemeName.DARK
    controller._scale = 1.5
    controller._value = 0.7
    controller._dragging = False
    controller._callbacks = OpacityPopupCallbacks(
        changed=lambda _value: None,
        opened=lambda: None,
        closed=lambda: None,
        context_requested=lambda _x, _y: None,
    )
    return controller


def test_label_click_does_not_change_opacity() -> None:
    controller = _controller()
    changed: list[float] = []
    controller._callbacks = OpacityPopupCallbacks(
        changed=changed.append,
        opened=lambda: None,
        closed=lambda: None,
        context_requested=lambda _x, _y: None,
    )

    controller._press(
        cast("tk.Event[tk.Misc]", cast("object", SimpleNamespace(x=100, y=20)))
    )

    assert changed == []
    assert controller._dragging is False


def test_track_drag_keeps_gesture_and_clamps_value() -> None:
    controller = _controller()
    changed: list[float] = []
    controller._callbacks = OpacityPopupCallbacks(
        changed=changed.append,
        opened=lambda: None,
        closed=lambda: None,
        context_requested=lambda _x, _y: None,
    )

    controller._press(
        cast("tk.Event[tk.Misc]", cast("object", SimpleNamespace(x=27, y=108)))
    )
    controller._drag(
        cast("tk.Event[tk.Misc]", cast("object", SimpleNamespace(x=999, y=5)))
    )
    controller._release(
        cast("tk.Event[tk.Misc]", cast("object", SimpleNamespace()))
    )

    assert changed == [0.3, 1.0]
    assert controller._dragging is False


def test_popup_right_click_closes_before_requesting_context_menu() -> None:
    controller = _controller()
    sequence: list[object] = []
    controller._window = cast("tk.Toplevel", cast("object", _Window()))
    controller._root = cast("tk.Tk", cast("object", _Root()))
    controller._callbacks = OpacityPopupCallbacks(
        changed=lambda _value: None,
        opened=lambda: None,
        closed=lambda: sequence.append("closed"),
        context_requested=lambda x, y: sequence.append((x, y)),
    )

    controller._context_requested(
        cast(
            "tk.Event[tk.Misc]",
            cast("object", SimpleNamespace(x_root=51, y_root=73)),
        )
    )

    assert sequence == ["closed", (51, 73)]
