# pyright: reportPrivateUsage=false
import tkinter as tk
from collections.abc import Callable
from pathlib import Path
from queue import Queue
from threading import Event
from typing import final

import pytest

import codex_usage_widget.runtime as runtime
from codex_usage_widget.config import WidgetConfig, load_config
from codex_usage_widget.position_store import persist_window_position
from codex_usage_widget.windows import WindowPosition
from codex_usage_widget.windows import SingleInstanceStatus


@final
class _PollRoot:
    def __init__(self) -> None:
        self.deiconified = 0

    def after(self, _ms: int, _callback: Callable[[], None]) -> str:
        return "poll-timer"

    def deiconify(self) -> None:
        self.deiconified += 1

    def lift(self) -> None:
        return None

    def state(self) -> str:
        return "normal"

    def withdraw(self) -> None:
        return None

    def winfo_id(self) -> int:
        return 42

    def attributes(self, _name: str, _value: float) -> None:
        return None


@final
class _PollService:
    def poll(self) -> None:
        return None


@final
class _PollTray:
    available = True

    def __init__(self) -> None:
        self.menu_refreshes = 0

    def set_status(self, _status: str | None) -> None:
        return None

    def refresh_menu(self) -> None:
        self.menu_refreshes += 1


@final
class _PollTaskbar:
    attached = True

    def __init__(self) -> None:
        self.attached: bool = True
        self.visibility: list[bool] = []

    def set_visible(self, _visible: bool) -> None:
        self.visibility.append(_visible)

    def suppress_held_menu_release(self) -> bool:
        return False


@final
class _PollTopmost:
    def __init__(self) -> None:
        self.applied = 0

    def apply(self) -> None:
        self.applied += 1


def test_run_widget_releases_singleton_when_tk_initialization_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given
    released = False

    def fail_tk() -> tk.Tk:
        raise tk.TclError

    def record_release() -> None:
        nonlocal released
        released = True

    monkeypatch.setattr(
        "codex_usage_widget.runtime.windows.acquire_single_instance_status",
        lambda: SingleInstanceStatus.ACQUIRED,
    )
    monkeypatch.setattr(
        "codex_usage_widget.runtime.windows.create_restore_event",
        lambda: True,
    )
    monkeypatch.setattr("codex_usage_widget.runtime.tk.Tk", fail_tk)
    monkeypatch.setattr(
        "codex_usage_widget.runtime.windows.release_single_instance",
        record_release,
    )

    # When / Then
    with pytest.raises(tk.TclError):
        _ = runtime.run_widget()
    assert released is True


def test_duplicate_launch_requests_existing_instance_restore(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requested = 0

    def request_restore() -> bool:
        nonlocal requested
        requested += 1
        return True

    monkeypatch.setattr(
        "codex_usage_widget.runtime.windows.acquire_single_instance_status",
        lambda: SingleInstanceStatus.ALREADY_RUNNING,
    )
    monkeypatch.setattr(
        "codex_usage_widget.runtime.windows.request_existing_instance_restore",
        request_restore,
    )

    assert runtime.run_widget() == 0
    assert requested == 1


def test_legacy_duplicate_shows_clear_message_when_restore_event_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    categories: list[str] = []
    monkeypatch.setattr(
        "codex_usage_widget.runtime.windows.acquire_single_instance_status",
        lambda: SingleInstanceStatus.ALREADY_RUNNING,
    )
    monkeypatch.setattr(
        "codex_usage_widget.runtime.windows.request_existing_instance_restore",
        lambda: False,
    )
    monkeypatch.setattr(runtime, "report_startup_problem", categories.append)

    assert runtime.run_widget() == 0
    assert categories == ["already_running"]


def test_drag_end_persists_position_without_rebuilding_the_surface(
    tmp_path: Path,
) -> None:
    # Given: a saved widget configuration and a new native window position.
    config_path = tmp_path / "widget_config.json"
    expected = WidgetConfig(position=WindowPosition(321, -45))

    # When: runtime position persistence runs independently from rendering.
    updated = persist_window_position(
        config_path,
        WidgetConfig(),
        WindowPosition(321, -45),
    )

    # Then: the returned and stored configurations match the new position.
    assert load_config(config_path) == updated == expected


def test_tray_show_reapplies_taskbar_style_and_window_layer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given
    application = runtime.WidgetApplication.__new__(runtime.WidgetApplication)
    root = _PollRoot()
    topmost = _PollTopmost()
    signals: Queue[runtime.Signal] = Queue()
    signals.put(("show", 0, 0))
    monkeypatch.setattr(application, "_closing", False, raising=False)
    monkeypatch.setattr(application, "_root", root, raising=False)
    monkeypatch.setattr(application, "_service", _PollService(), raising=False)
    monkeypatch.setattr(application, "_signals", signals, raising=False)
    monkeypatch.setattr(application, "_tray", _PollTray(), raising=False)
    monkeypatch.setattr(application, "_taskbar", _PollTaskbar(), raising=False)
    monkeypatch.setattr(application, "_config", WidgetConfig(), raising=False)
    monkeypatch.setattr(application, "_effective_visibility", None, raising=False)
    monkeypatch.setattr(application, "_topmost", topmost, raising=False)
    hidden_handles: list[int] = []

    def record_hidden_handle(hwnd: int) -> bool:
        hidden_handles.append(hwnd)
        return True

    monkeypatch.setattr(
        "codex_usage_widget.window_visibility.hide_from_taskbar",
        record_hidden_handle,
    )

    # When
    application._poll()

    # Then
    assert root.deiconified == 1
    assert hidden_handles == [42]
    assert topmost.applied == 1


@pytest.mark.parametrize(
    ("attached", "expected_desktop"),
    [(True, False), (False, True)],
)
def test_taskbar_only_preference_uses_temporary_desktop_fallback(
    monkeypatch: pytest.MonkeyPatch,
    attached: bool,
    expected_desktop: bool,
) -> None:
    application = runtime.WidgetApplication.__new__(runtime.WidgetApplication)
    root = _PollRoot()
    taskbar = _PollTaskbar()
    taskbar.attached = attached
    config = WidgetConfig(desktop_visible=False, taskbar_visible=True, mini_mode=True)
    monkeypatch.setattr(application, "_root", root, raising=False)
    monkeypatch.setattr(application, "_taskbar", taskbar, raising=False)
    monkeypatch.setattr(application, "_tray", _PollTray(), raising=False)
    monkeypatch.setattr(application, "_topmost", _PollTopmost(), raising=False)
    monkeypatch.setattr(application, "_config", config, raising=False)
    monkeypatch.setattr(application, "_effective_visibility", None, raising=False)

    application._apply_visibility()

    effective = application._effective_visibility
    assert effective is not None
    assert effective.desktop is expected_desktop
    assert application._config is config
    assert application._config.mini_mode is True
    assert taskbar.visibility == [True]


def test_saved_config_refreshes_tray_menu_after_state_is_applied(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    application = runtime.WidgetApplication.__new__(runtime.WidgetApplication)
    tray = _PollTray()
    current = WidgetConfig(desktop_visible=True)
    updated = WidgetConfig(desktop_visible=False)
    monkeypatch.setattr(application, "_config", current, raising=False)
    monkeypatch.setattr(
        application,
        "_config_path",
        tmp_path / "config.json",
        raising=False,
    )
    monkeypatch.setattr(application, "_root", _PollRoot(), raising=False)
    monkeypatch.setattr(application, "_topmost", _PollTopmost(), raising=False)
    monkeypatch.setattr(application, "_tray", tray, raising=False)
    monkeypatch.setattr(application, "_render", lambda: None)
    monkeypatch.setattr(application, "_apply_visibility", lambda: None)

    application._save_and_render(updated)

    assert application._config is updated
    assert load_config(tmp_path / "config.json") == updated
    assert tray.menu_refreshes == 1


def test_poll_reschedules_before_modal_menu_dispatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    application = runtime.WidgetApplication.__new__(runtime.WidgetApplication)
    root = _PollRoot()
    signals: Queue[runtime.Signal] = Queue()
    signals.put(("menu", 10, 20))
    sequence: list[str] = []
    monkeypatch.setattr(application, "_closing", False, raising=False)
    monkeypatch.setattr(application, "_root", root, raising=False)
    monkeypatch.setattr(application, "_service", _PollService(), raising=False)
    monkeypatch.setattr(application, "_signals", signals, raising=False)
    monkeypatch.setattr(application, "_apply_visibility", lambda: None)
    def record_after(_ms: int, _callback: Callable[[], None]) -> None:
        sequence.append("after")

    def record_signal(_signal: runtime.Signal) -> bool:
        sequence.append("menu")
        return False

    monkeypatch.setattr(root, "after", record_after)
    monkeypatch.setattr(
        application,
        "_handle_signal",
        record_signal,
    )

    application._poll()

    assert sequence == ["after", "menu"]


def test_poll_does_not_touch_destroyed_root_after_modal_exit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    application = runtime.WidgetApplication.__new__(runtime.WidgetApplication)
    root = _PollRoot()
    signals: Queue[runtime.Signal] = Queue()
    signals.put(("menu", 10, 20))
    visibility_calls = 0

    def close_from_menu(_signal: runtime.Signal) -> bool:
        application._closing = True
        return False

    def apply_visibility() -> None:
        nonlocal visibility_calls
        visibility_calls += 1

    monkeypatch.setattr(application, "_closing", False, raising=False)
    monkeypatch.setattr(application, "_root", root, raising=False)
    monkeypatch.setattr(application, "_service", _PollService(), raising=False)
    monkeypatch.setattr(application, "_signals", signals, raising=False)
    monkeypatch.setattr(application, "_handle_signal", close_from_menu)
    monkeypatch.setattr(application, "_apply_visibility", apply_visibility)

    application._poll()

    assert visibility_calls == 0


def test_taskbar_menu_click_snapshots_open_state_before_tk_dispatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    application = runtime.WidgetApplication.__new__(runtime.WidgetApplication)
    signals: Queue[runtime.Signal] = Queue()
    menu_open = Event()
    monkeypatch.setattr(application, "_signals", signals, raising=False)
    monkeypatch.setattr(application, "_taskbar_menu_open", menu_open, raising=False)

    application._queue_taskbar_menu(10, 20)
    menu_open.set()
    application._queue_taskbar_menu(30, 40)
    menu_open.clear()

    assert signals.get_nowait() == ("menu", 10, 20)
    assert signals.get_nowait() == ("menu_close", 30, 40)
