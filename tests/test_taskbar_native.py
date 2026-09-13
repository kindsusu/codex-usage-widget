# pyright: reportPrivateUsage=false
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false
from dataclasses import dataclass
from threading import Event

import pytest
from PIL import Image

import codex_usage_widget.taskbar_native as taskbar_native
from codex_usage_widget.taskbar_native import (
    NativeTaskbarHost,
    WS_CHILD,
    WS_CLIPSIBLINGS,
    WS_POPUP,
    attach_transaction,
    premultiplied_bgra,
)
from codex_usage_widget.taskbar_placement import Rect


class FakeUser32:
    def __init__(self) -> None:
        self.shown: list[int] = []
        self.posted: int = 0

    def ShowWindow(self, hwnd: int, command: int) -> int:  # noqa: N802
        del hwnd
        self.shown.append(command)
        return 1

    def GetClientRect(self, hwnd: int, rect: object) -> int:  # noqa: N802
        del hwnd
        native = rect._obj  # pyright: ignore[reportAttributeAccessIssue]
        native.left, native.top, native.right, native.bottom = 0, 0, 197, 46
        return 1

    def GetDpiForWindow(self, hwnd: int) -> int:  # noqa: N802
        del hwnd
        return 96

    def TrackMouseEvent(self, event: object) -> bool:  # noqa: N802
        del event
        return True

    def GetCursorPos(self, point: object) -> bool:  # noqa: N802
        native = point._obj  # pyright: ignore[reportAttributeAccessIssue]
        native.x, native.y = 170, 23
        return True

    def ScreenToClient(self, hwnd: int, point: object) -> bool:  # noqa: N802
        del hwnd, point
        return True

    def GetAsyncKeyState(self, key: int) -> int:  # noqa: N802
        del key
        return -32768

    def PostMessageW(  # noqa: N802
        self, hwnd: int, message: int, wparam: int, lparam: int
    ) -> bool:
        del hwnd, message, wparam, lparam
        self.posted += 1
        return True

    def SetThreadDpiAwarenessContext(self, context: object) -> object:  # noqa: N802
        return context


def _ignore_hwnd(_hwnd: int) -> None:
    pass


@dataclass
class FakeApi:
    style: int = WS_POPUP | 7
    parent: int = 0
    fail_position: bool = False
    positioned: bool = False

    def get_style(self, hwnd: int) -> int:
        del hwnd
        return self.style

    def set_style(self, hwnd: int, style: int) -> None:
        del hwnd
        self.style = style

    def get_parent(self, hwnd: int) -> int:
        del hwnd
        return self.parent

    def set_parent(self, hwnd: int, parent: int) -> None:
        del hwnd
        self.parent = parent

    def position(self, hwnd: int, parent: int, rect: Rect, origin: Rect) -> None:
        del hwnd, parent, rect, origin
        if self.fail_position:
            raise OSError
        self.positioned = True


def test_attachment_applies_verified_child_contract() -> None:
    api = FakeApi()

    attached = attach_transaction(api, 10, 20, Rect(1, 2, 101, 42), Rect(0, 0, 300, 48))

    assert attached
    assert api.parent == 20
    assert api.style & WS_CHILD
    assert api.style & WS_CLIPSIBLINGS
    assert not api.style & WS_POPUP
    assert api.positioned


def test_attachment_failure_rolls_back_parent_and_style() -> None:
    api = FakeApi(fail_position=True)
    original_style = api.style

    attached = attach_transaction(api, 10, 20, Rect(1, 2, 101, 42), Rect(0, 0, 300, 48))

    assert not attached
    assert api.parent == 0
    assert api.style == original_style


def test_stop_before_hwnd_creation_is_remembered() -> None:
    host = NativeTaskbarHost(lambda _x, _y: None, lambda _x, _y: None)

    host.stop()

    assert not host.available
    assert host.hwnd == 0


def test_provider_failure_detaches_and_next_scan_recovers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    host = NativeTaskbarHost(lambda _x, _y: None, lambda _x, _y: None)
    host._hwnd = 10
    host._attached = True
    user32 = FakeUser32()
    target = taskbar_native._Target(
        20,
        Rect(0, 100, 300, 148),
        Rect(100, 100, 258, 148),
        96,
    )
    api = FakeApi()
    monkeypatch.setattr(taskbar_native, "_user32", lambda: user32)
    monkeypatch.setattr(taskbar_native, "_Win32AttachmentApi", lambda: api)
    monkeypatch.setattr(host, "_render_layered", _ignore_hwnd)

    host._observed_target = None
    host._apply_observed_target()

    assert not host.attached

    host._observed_target = target
    host._apply_observed_target()

    assert host.attached
    assert api.parent == target.parent


def test_layered_pixels_are_premultiplied_bgra() -> None:
    image = Image.new("RGBA", (2, 1))
    image.paste((100, 50, 200, 128), (0, 0, 1, 1))
    image.paste((9, 8, 7, 1), (1, 0, 2, 1))

    pixels = premultiplied_bgra(image)

    assert pixels == bytes((100, 25, 50, 128, 0, 0, 0, 1))


def test_mouse_regions_split_usage_and_menu(monkeypatch: pytest.MonkeyPatch) -> None:
    host = NativeTaskbarHost(lambda _x, _y: None, lambda _x, _y: None)
    host._hwnd = 10
    host._attached = True
    user32 = FakeUser32()
    monkeypatch.setattr(taskbar_native, "_user32", lambda: user32)
    monkeypatch.setattr(host, "_render_layered", _ignore_hwnd)

    host._handle_mouse_move(10, 23 << 16 | 153)
    assert host._hover_region == "usage"

    host._handle_mouse_move(10, 23 << 16 | 159)
    assert host._hover_region == "menu"


def test_click_routing_uses_event_coordinates_not_stale_hover(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    host = NativeTaskbarHost(
        lambda _x, _y: calls.append("details"),
        lambda _x, _y: calls.append("menu"),
    )
    host._hwnd = 10
    host._hover_region = "menu"
    user32 = FakeUser32()
    monkeypatch.setattr(taskbar_native, "_user32", lambda: user32)

    _ = host._window_proc(10, taskbar_native.WM_LBUTTONUP, 0, 23 << 16 | 20)

    assert calls == ["details"]


def test_held_dismissal_consumes_only_its_matching_release(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    host = NativeTaskbarHost(
        lambda _x, _y: calls.append("details"),
        lambda _x, _y: calls.append("menu"),
    )
    host._hwnd = 10
    user32 = FakeUser32()
    monkeypatch.setattr(taskbar_native, "_user32", lambda: user32)

    assert host.suppress_held_menu_release()
    menu_point = 23 << 16 | 170
    _ = host._window_proc(10, taskbar_native.WM_LBUTTONUP, 0, menu_point)
    assert calls == []

    _ = host._window_proc(10, taskbar_native.WM_LBUTTONUP, 0, menu_point)
    assert calls == ["menu"]


def test_dragging_out_clears_held_release_suppression(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    host = NativeTaskbarHost(
        lambda _x, _y: None,
        lambda _x, _y: calls.append("menu"),
    )
    host._hwnd = 10
    user32 = FakeUser32()
    monkeypatch.setattr(taskbar_native, "_user32", lambda: user32)
    monkeypatch.setattr(host, "_render_layered", _ignore_hwnd)

    assert host.suppress_held_menu_release()
    _ = host._window_proc(10, taskbar_native.WM_MOUSELEAVE, 0, 0)
    _ = host._window_proc(10, taskbar_native.WM_LBUTTONUP, 0, 23 << 16 | 170)

    assert calls == ["menu"]


def test_stopped_observer_does_not_publish_scanned_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    host = NativeTaskbarHost(lambda _x, _y: None, lambda _x, _y: None)
    host._hwnd = 10
    host._generation = 2
    current_stop = Event()
    old_stop = Event()
    host._stop_requested = current_stop
    old_stop.set()
    user32 = FakeUser32()
    monkeypatch.setattr(taskbar_native, "_find_target", lambda: None)
    monkeypatch.setattr(taskbar_native, "_user32", lambda: user32)

    published = host._observe_once(10, old_stop, 1)

    assert not published
    assert user32.posted == 0


def test_observer_failure_publishes_none_then_next_scan_recovers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    host = NativeTaskbarHost(lambda _x, _y: None, lambda _x, _y: None)
    host._hwnd = 10
    host._generation = 1
    stop_event = Event()
    host._stop_requested = stop_event
    user32 = FakeUser32()
    target = taskbar_native._Target(
        20, Rect(0, 0, 300, 48), Rect(100, 1, 297, 47), 96
    )
    scans = iter((RuntimeError(), target))

    def scan() -> taskbar_native._Target:
        value = next(scans)
        if isinstance(value, Exception):
            raise value
        return value

    monkeypatch.setattr(taskbar_native, "_find_target", scan)
    monkeypatch.setattr(taskbar_native, "_user32", lambda: user32)

    assert host._observe_once(10, stop_event, 1)
    assert host._observed_target is None
    assert host._observe_once(10, stop_event, 1)
    assert host._observed_target == target
