import tkinter as tk
from pathlib import Path

import pytest

import codex_usage_widget.runtime as runtime
from codex_usage_widget.config import WidgetConfig, load_config
from codex_usage_widget.position_store import persist_window_position
from codex_usage_widget.windows import WindowPosition


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
