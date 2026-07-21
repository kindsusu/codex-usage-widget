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
    window_layer,
)
from codex_usage_widget.windows import (
    MonitorRect,
    WindowPosition,
    WindowSize,
    resolve_window_position,
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
    assert geometry == "-900+140"


def test_initial_position_resolves_against_tk_virtual_desktop_bounds() -> None:
    # Given
    saved = WindowPosition(x=9000, y=9000)

    # When
    resolved = resolve_initial_position(saved, _VirtualDesktop())

    # Then
    assert resolved == WindowPosition(x=-1820, y=100)


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
        (False, True, "bottom"),
        (False, False, "bottom"),
    ],
)
def test_window_layer_tracks_codex_process_presence(
    smart_enabled: bool,
    codex_running: bool,
    expected: str,
) -> None:
    # Given / When / Then
    assert window_layer(smart_enabled, codex_running) == expected


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
