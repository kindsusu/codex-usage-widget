from typing import final

import pytest

from codex_usage_widget.window_visibility import apply_native_window_state


@final
class _NativeRoot:
    def winfo_id(self) -> int:
        return 42


def test_native_window_state_hides_taskbar_entry_before_applying_layer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given
    calls: list[str] = []

    def hide_from_taskbar(_hwnd: int) -> bool:
        calls.append("taskbar")
        return True

    def apply_layer() -> None:
        calls.append("layer")

    monkeypatch.setattr(
        "codex_usage_widget.window_visibility.hide_from_taskbar",
        hide_from_taskbar,
    )

    # When
    apply_native_window_state(_NativeRoot(), apply_layer)

    # Then
    assert calls == ["taskbar", "layer"]
