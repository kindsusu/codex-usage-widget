# pyright: reportPrivateUsage=false, reportAttributeAccessIssue=false
from typing import TYPE_CHECKING, cast, final

if TYPE_CHECKING:
    from collections.abc import Callable

import pytest

import codex_usage_widget.menus as menus
from codex_usage_widget.config import WidgetConfig


class FakeMenu:
    def __init__(self) -> None:
        self.unposted: int = 0

    def unpost(self) -> None:
        self.unposted += 1


@final
class _DeferredRoot:
    def __init__(self) -> None:
        self.idle: list[object] = []

    def after_idle(self, callback: object) -> str:
        self.idle.append(callback)
        return "idle-cleanup"


def test_repeated_trigger_unposts_active_context_menu(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller = menus.ContextMenuController.__new__(menus.ContextMenuController)
    active = FakeMenu()
    controller._active = active
    controller._native_owner = 123
    shown = False

    def record_show(*_args: object) -> None:
        nonlocal shown
        shown = True

    monkeypatch.setattr(controller, "_show", record_show)
    cancelled: list[int] = []
    monkeypatch.setattr(menus, "_cancel_native_popup", cancelled.append)

    callbacks = cast("menus.MenuCallbacks", object())
    controller.toggle(10, 20, WidgetConfig(), callbacks)

    assert active.unposted == 1
    assert cancelled == [123]
    assert not shown


def test_dismiss_is_noop_without_active_menu() -> None:
    controller = menus.ContextMenuController.__new__(menus.ContextMenuController)
    controller._active = None
    controller._native_owner = 0

    assert controller.dismiss() is False


def test_selected_command_remains_alive_until_idle_cleanup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _DeferredRoot()
    controller = menus.ContextMenuController.__new__(menus.ContextMenuController)
    controller._root = cast("object", root)
    controller._active = None
    controller._native_owner = 0
    destroyed: list[str] = []
    selected: list[str] = []
    closed: list[str] = []

    class _Popup(FakeMenu):
        def tk_popup(self, _x: int, _y: int) -> None:
            return None

        def destroy(self) -> None:
            destroyed.append("destroyed")

    popup = _Popup()
    def new_menu(
        _root: object,
        _tokens: object,
        _font: tuple[str, int],
    ) -> _Popup:
        return popup

    def populate(*_args: object) -> tuple[()]:
        return ()

    def native_owner(_root: object) -> int:
        return 0

    def finish_native(_owner: int) -> None:
        return None

    monkeypatch.setattr(menus, "_new_menu", new_menu)
    monkeypatch.setattr(menus, "_populate_context_menu", populate)
    monkeypatch.setattr(menus, "_prepare_native_popup", native_owner)
    monkeypatch.setattr(menus, "_finish_native_popup", finish_native)
    def noop() -> None:
        return None
    callbacks = menus.MenuCallbacks(
        refresh=noop,
        theme=noop,
        opacity=noop,
        desktop_normal=noop,
        desktop_mini=noop,
        desktop_hidden=noop,
        taskbar_visibility=lambda: selected.append("selected"),
        topmost=noop,
        auto_update=noop,
        exit_app=noop,
        scale=lambda _value, _mini: None,
        pet=lambda _name: None,
        menu_opened=noop,
        menu_closed=lambda: closed.append("closed"),
    )

    controller._show(10, 20, WidgetConfig(), callbacks)

    assert destroyed == []
    assert controller.active is False
    assert closed == ["closed"]
    callbacks.taskbar_visibility()
    cleanup = cast("Callable[[], None]", root.idle.pop())
    cleanup()
    assert selected == ["selected"]
    assert destroyed == ["destroyed"]
