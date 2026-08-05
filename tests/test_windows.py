from typing import final

import pytest

from codex_usage_widget.window_runtime import (
    ForegroundProcess,
    ProcessRecord,
    foreground_process_from_records,
    format_window_position,
    is_codex_foreground,
    is_codex_running,
    read_codex_running,
    resolve_initial_position,
    should_keep_topmost,
    window_layer,
)
from codex_usage_widget.windows import (
    MonitorRect,
    WindowPosition,
    WindowSize,
    resolve_window_position,
    taskbar_hidden_exstyle,
)


@final
class _VirtualDesktop:
    def winfo_vrootx(self) -> int:
        return -1920

    def winfo_vrooty(self) -> int:
        return 0

    def winfo_vrootwidth(self) -> int:
        return 3840

    def winfo_vrootheight(self) -> int:
        return 1080


def test_resolve_window_position_preserves_visible_negative_monitor_position() -> None:
    # Given
    saved = WindowPosition(x=-1500, y=120)
    size = WindowSize(width=260, height=170)
    monitors = (
        MonitorRect(left=-1920, top=0, right=0, bottom=1080),
        MonitorRect(left=0, top=0, right=1920, bottom=1080),
    )

    # When
    resolved = resolve_window_position(saved, size, monitors)

    # Then
    assert resolved == saved


def test_resolve_window_position_recovers_offscreen_to_deterministic_default() -> None:
    # Given
    saved = WindowPosition(x=9000, y=9000)
    size = WindowSize(width=260, height=170)
    monitors = (MonitorRect(left=1920, top=-200, right=3200, bottom=824),)

    # When
    resolved = resolve_window_position(saved, size, monitors)

    # Then
    assert resolved == WindowPosition(x=2020, y=-100)


def test_format_window_position_preserves_signed_negative_coordinates() -> None:
    # Given
    position = WindowPosition(x=-900, y=140)

    # When
    geometry = format_window_position(position.x, position.y)

    # Then
    assert geometry == "+-900+140"


def test_format_window_position_keeps_top_left_anchor_for_negative_axes() -> None:
    # Given: coordinates that a bare "-" sign would re-anchor to the far edges
    above_top = WindowPosition(x=100, y=-12)
    left_of_origin = WindowPosition(x=-5, y=50)

    # When
    above_top_geometry = format_window_position(above_top.x, above_top.y)
    left_geometry = format_window_position(left_of_origin.x, left_of_origin.y)

    # Then
    assert above_top_geometry == "+100+-12"
    assert left_geometry == "+-5+50"


def test_initial_position_resolves_against_tk_virtual_desktop_bounds() -> None:
    # Given
    saved = WindowPosition(x=9000, y=9000)

    # When
    resolved = resolve_initial_position(saved, _VirtualDesktop())

    # Then
    assert resolved == WindowPosition(x=-1820, y=100)


def test_taskbar_hidden_exstyle_clears_appwindow_and_sets_toolwindow() -> None:
    # Given
    ws_ex_appwindow = 0x00040000
    ws_ex_toolwindow = 0x00000080
    ws_ex_topmost = 0x00000008
    ws_ex_layered = 0x00080000  # set by -transparentcolor churn

    # When: a window currently owning a taskbar button plus unrelated bits
    result = taskbar_hidden_exstyle(ws_ex_appwindow | ws_ex_topmost | ws_ex_layered)

    # Then: APPWINDOW dropped, TOOLWINDOW added, every other bit preserved
    assert not result & ws_ex_appwindow
    assert result & ws_ex_toolwindow
    assert result & ws_ex_topmost
    assert result & ws_ex_layered
    # And the composition is idempotent across repeated attribute churn.
    assert taskbar_hidden_exstyle(result) == result


def test_codex_desktop_and_cli_are_direct_foreground_matches() -> None:
    # Given
    related: tuple[str, ...] = ()

    # When / Then
    assert is_codex_foreground("Codex.exe", related) is True
    assert is_codex_foreground("codex-desktop.exe", related) is True


def test_terminal_foreground_requires_a_related_codex_process() -> None:
    # Given
    terminal = "WindowsTerminal.exe"

    # When / Then
    assert is_codex_foreground(terminal, ("codex.exe",)) is True
    assert is_codex_foreground(terminal, ("python.exe",)) is False


def test_chatgpt_desktop_host_requires_a_related_codex_process() -> None:
    # Given
    chatgpt = "ChatGPT.exe"

    # When / Then
    assert is_codex_foreground(chatgpt, ("codex.exe",)) is True
    assert is_codex_foreground(chatgpt, ("python.exe",)) is False


def test_chatgpt_desktop_host_matches_a_full_executable_path() -> None:
    # Given
    chatgpt = r"C:\\Users\\User\\AppData\\Local\\Programs\\ChatGPT\\ChatGPT.exe"

    # When / Then
    assert is_codex_foreground(chatgpt, ("codex.exe",)) is True


def test_foreground_context_includes_only_descendants_of_the_terminal() -> None:
    # Given
    records = (
        ProcessRecord(pid=10, parent_pid=1, name="WindowsTerminal.exe"),
        ProcessRecord(pid=11, parent_pid=10, name="pwsh.exe"),
        ProcessRecord(pid=12, parent_pid=11, name="codex.exe"),
        ProcessRecord(pid=20, parent_pid=1, name="codex.exe"),
    )

    # When
    context = foreground_process_from_records(10, records)

    # Then
    assert context == ForegroundProcess(
        name="WindowsTerminal.exe",
        related_process_names=("pwsh.exe", "codex.exe"),
    )


def test_claude_names_are_never_classified_as_codex() -> None:
    # Given
    claude_names = ("claude.exe", "Claude Desktop.exe", "claude-code.exe")

    # When
    results = tuple(is_codex_foreground(name, claude_names) for name in claude_names)

    # Then
    assert results == (False, False, False)


def test_codex_running_classifies_a_global_process_record() -> None:
    # Given
    records = (
        ProcessRecord(pid=10, parent_pid=1, name="explorer.exe"),
        ProcessRecord(pid=20, parent_pid=1, name="Codex.exe"),
    )

    # When / Then
    assert is_codex_running(records) is True


def test_codex_running_ignores_claude_and_unrelated_processes() -> None:
    # Given
    records = (
        ProcessRecord(pid=10, parent_pid=1, name="Claude.exe"),
        ProcessRecord(pid=20, parent_pid=1, name="WindowsTerminal.exe"),
    )

    # When / Then
    assert is_codex_running(records) is False


@pytest.mark.parametrize(
    ("smart_enabled", "codex_running", "expected"),
    [
        (True, True, "top"),
        (True, False, "bottom"),
        (False, True, "top"),
        (False, False, "top"),
    ],
)
def test_window_layer_tracks_codex_process_presence_only_while_smart(
    smart_enabled: bool,
    codex_running: bool,
    expected: str,
) -> None:
    # Given / When / Then
    assert window_layer(smart_enabled, codex_running) == expected


@pytest.mark.parametrize(
    ("widget_focused", "foreground"),
    [
        (False, ForegroundProcess(name="explorer.exe", related_process_names=())),
        (False, ForegroundProcess(name="codex.exe", related_process_names=())),
        (True, ForegroundProcess(name="explorer.exe", related_process_names=())),
    ],
)
def test_should_keep_topmost_pins_the_widget_while_smart_is_disabled(
    widget_focused: bool,
    foreground: ForegroundProcess,
) -> None:
    # Given / When
    keep = should_keep_topmost(
        False,
        widget_focused=widget_focused,
        foreground=foreground,
    )

    # Then
    assert keep is True


def test_codex_running_reader_contains_native_snapshot_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given
    def fail_snapshot() -> tuple[ProcessRecord, ...]:
        raise OSError

    monkeypatch.setattr("codex_usage_widget.window_runtime.os.name", "nt")
    monkeypatch.setattr(
        "codex_usage_widget.window_runtime._read_process_records",
        fail_snapshot,
    )

    # When / Then
    assert read_codex_running() is False
