# pyright: reportPrivateUsage=false, reportAttributeAccessIssue=false
from collections.abc import Callable
from typing import TYPE_CHECKING, cast, final

import pytest

import codex_usage_widget.visibility_panel as visibility_panel
from codex_usage_widget.actions import DesktopMode
from codex_usage_widget.visibility_panel import (
    VisibilityCallbacks,
    VisibilityPanel,
    _blend,
    _panel_mask,
    _visibility_note,
    place_avoiding_rect,
    visibility_panel_size,
)

if TYPE_CHECKING:
    import tkinter as tk


@final
class _Canvas:
    def cget(self, _name: str) -> str:
        return "292"


@final
class _Window:
    def __init__(self) -> None:
        self.idle: list[Callable[[], None]] = []
        self.timers: list[Callable[[], None]] = []
        self.destroyed = 0

    def after_idle(self, callback: Callable[[], None]) -> str:
        self.idle.append(callback)
        return "idle"

    def after(self, _ms: int, callback: Callable[[], None]) -> str:
        self.timers.append(callback)
        return "timer"

    def winfo_exists(self) -> bool:
        return not self.destroyed

    def focus_get(self) -> None:
        return None

    def destroy(self) -> None:
        self.destroyed += 1


def test_visibility_note_covers_every_surface_combination() -> None:
    assert _visibility_note(DesktopMode.NORMAL, True) == (
        "일반 위젯 · 작업표시줄 표시"
    )
    assert _visibility_note(DesktopMode.MINI, False) == (
        "미니 위젯 · 작업표시줄 숨김"
    )
    assert _visibility_note(DesktopMode.HIDDEN, True) == (
        "바탕화면 숨김 · 작업표시줄 표시"
    )


def test_translucent_design_tokens_are_blended_onto_card_surface() -> None:
    assert _blend("#1d2533", (255, 255, 255, 23)) == "#313945"


def test_panel_matches_reference_size_at_system_dpi() -> None:
    assert visibility_panel_size(96) == (292, 259)
    assert visibility_panel_size(144) == (438, 388)


def test_panel_edge_mask_is_binary_and_keeps_rounded_corners_clear() -> None:
    mask = _panel_mask(438, 328, 18)
    assert set(mask.tobytes()) <= {0, 255}
    assert mask.getpixel((0, 0)) == 0
    assert mask.getpixel((219, 164)) == 255


def test_only_the_three_reference_rows_are_interactive() -> None:
    panel = VisibilityPanel.__new__(VisibilityPanel)
    panel._canvas = _Canvas()

    assert panel._row_at(45) is None
    assert panel._row_at(46) == 0
    assert panel._row_at(85) == 0
    assert panel._row_at(86) == 1
    assert panel._row_at(165) == 2
    assert panel._row_at(166) == 3
    assert panel._row_at(205) == 3
    assert panel._row_at(206) is None


def test_trigger_focus_out_waits_for_native_release_toggle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    window = _Window()
    panel = VisibilityPanel.__new__(VisibilityPanel)
    panel._window = window
    panel._canvas = None
    panel._hover = None
    panel._icon = None
    panel._callbacks = VisibilityCallbacks(
        lambda: None,
        lambda: None,
        lambda: None,
        lambda: None,
        lambda _x, _y: True,
    )
    monkeypatch.setattr(visibility_panel, "_left_button_state", lambda: 0)
    monkeypatch.setattr(visibility_panel, "_cursor_position", lambda: (10, 20))

    panel._focus_out(cast("tk.Event[tk.Misc]", object()))
    window.idle.pop()()
    assert window.destroyed == 0

    panel.close()  # Native button-up toggle arrives through Runtime.
    window.timers.pop()()
    assert window.destroyed == 1


def test_desktop_panel_prefers_right_without_covering_trigger_card() -> None:
    assert place_avoiding_rect(
        (100, 200, 520, 434),
        438,
        328,
        (0, 0, 2560, 1400),
    ) == (528, 200)


def test_desktop_panel_uses_left_when_right_side_does_not_fit() -> None:
    assert place_avoiding_rect(
        (1800, 200, 2220, 434),
        438,
        328,
        (0, 0, 2560, 1400),
    ) == (1354, 200)
