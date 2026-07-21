# pyright: reportPrivateUsage=false
import tkinter as tk
from collections.abc import Callable
from pathlib import Path
from queue import Queue
from typing import Literal, final

import pytest

import codex_usage_widget.runtime as runtime
from codex_usage_widget.config import WidgetConfig, load_config
from codex_usage_widget.position_store import persist_window_position
from codex_usage_widget.windows import WindowPosition


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

    def winfo_id(self) -> int:
        return 42


@final
class _PollService:
    def poll(self) -> None:
        return None


@final
class _PollTray:
    available = True


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
        "codex_usage_widget.runtime.windows.acquire_single_instance",
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
    signals: Queue[Literal["show", "exit"]] = Queue()
    signals.put("show")
    monkeypatch.setattr(application, "_closing", False, raising=False)
    monkeypatch.setattr(application, "_root", root, raising=False)
    monkeypatch.setattr(application, "_service", _PollService(), raising=False)
    monkeypatch.setattr(application, "_signals", signals, raising=False)
    monkeypatch.setattr(application, "_tray", _PollTray(), raising=False)
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
