import ctypes
from ctypes import wintypes
from typing import Protocol, final

import pytest

import codex_usage_widget.windows as windows
from codex_usage_widget.window_runtime import (
    ForegroundProcess,
    ProcessRecord,
    foreground_process_from_records,
    format_window_position,
    is_codex_foreground,
    resolve_initial_position,
    read_foreground_process_native,
)
from codex_usage_widget.windows import (
    MonitorRect,
    WindowPosition,
    WindowSize,
    hide_from_taskbar,
    resolve_window_position,
    set_window_zorder,
    singleton_name,
)


@final
class _ZeroMutexFunction:
    argtypes: (
        list[type[ctypes.c_void_p] | type[ctypes.c_int] | type[ctypes.c_wchar_p]] | None
    ) = None
    restype: type[ctypes.c_void_p] | None = None

    def __call__(self, _security: None, _owner: int, _name: str) -> int:
        return 0


@final
class _FakeKernel32:
    def __init__(self) -> None:
        self.CreateMutexW: _ZeroMutexFunction = _ZeroMutexFunction()


@final
class _SetWindowPosFunction:
    argtypes: (
        list[type[ctypes.c_void_p] | type[ctypes.c_int] | type[ctypes.c_uint]] | None
    ) = None
    restype: type[ctypes.c_int] | None = None

    def __init__(self) -> None:
        self.received_hwnd: int = 0

    def __call__(
        self,
        hwnd: int,
        _insert_after: int,
        _x: int,
        _y: int,
        _width: int,
        _height: int,
        _flags: int,
    ) -> int:
        self.received_hwnd = hwnd
        return 0


@final
class _FakeUser32:
    def __init__(self) -> None:
        self.SetWindowPos: _SetWindowPosFunction = _SetWindowPosFunction()


class _DwordPointer(Protocol):
    contents: wintypes.DWORD


@final
class _GetForegroundWindowFunction:
    argtypes: list[type[ctypes.c_void_p]] | None = None
    restype: type[ctypes.c_void_p] | None = None

    def __call__(self) -> int:
        return 77


@final
class _GetWindowThreadProcessIdFunction:
    argtypes: list[type[ctypes.c_void_p] | type[ctypes.c_ulong]] | None = None
    restype: type[ctypes.c_ulong] | None = None

    def __init__(self) -> None:
        self.received_pointer = False

    def __call__(self, _hwnd: int, pid_pointer: _DwordPointer) -> int:
        pid_pointer.contents.value = 42
        self.received_pointer = True
        return 0


@final
class _ForegroundUser32:
    def __init__(self) -> None:
        self.GetForegroundWindow = _GetForegroundWindowFunction()
        self.GetWindowThreadProcessId = _GetWindowThreadProcessIdFunction()


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


def test_singleton_uses_codex_specific_name() -> None:
    # Given / When / Then
    assert singleton_name() == "codex-usage-widget-singleton"


def test_singleton_returns_false_when_win32_returns_a_zero_handle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given
    fake = _FakeKernel32()

    def load_kernel32(_name: str, *, use_last_error: bool = False) -> _FakeKernel32:
        del use_last_error
        return fake

    monkeypatch.setattr("codex_usage_widget.windows.os.name", "nt")
    monkeypatch.setattr("codex_usage_widget.windows.ctypes.CDLL", load_kernel32)

    # When
    acquired = windows.acquire_single_instance("test-zero-handle")

    # Then
    assert acquired is False
    assert fake.CreateMutexW.argtypes == [
        ctypes.c_void_p,
        ctypes.c_int,
        ctypes.c_wchar_p,
    ]
    assert fake.CreateMutexW.restype is ctypes.c_void_p


def test_win32_api_load_failure_returns_false(monkeypatch: pytest.MonkeyPatch) -> None:
    # Given
    def fail_load(*_args: str, **_kwargs: bool) -> None:
        raise OSError

    monkeypatch.setattr("codex_usage_widget.windows.os.name", "nt")
    monkeypatch.setattr("codex_usage_widget.windows.ctypes.CDLL", fail_load)

    # When / Then
    assert windows.acquire_single_instance("test-api-failure") is False
    assert windows.set_window_zorder(2**40, "normal") is False
    assert windows.hide_from_taskbar(2**40) is False


def test_set_window_pos_uses_pointer_sized_hwnd_without_argument_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given
    fake = _FakeUser32()
    large_hwnd = 2**40

    def load_user32(_name: str, *, use_last_error: bool = False) -> _FakeUser32:
        del use_last_error
        return fake

    monkeypatch.setattr("codex_usage_widget.windows.os.name", "nt")
    monkeypatch.setattr("codex_usage_widget.windows.ctypes.CDLL", load_user32)

    # When
    result = windows.set_window_zorder(large_hwnd, "normal")

    # Then
    assert result is False
    assert fake.SetWindowPos.received_hwnd == large_hwnd
    assert fake.SetWindowPos.argtypes is not None
    assert fake.SetWindowPos.argtypes[:2] == [ctypes.c_void_p, ctypes.c_void_p]
    assert fake.SetWindowPos.restype is ctypes.c_int


def test_foreground_pid_query_passes_the_declared_dword_pointer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given
    fake = _ForegroundUser32()

    def load_user32(_name: str, *, use_last_error: bool = False) -> _ForegroundUser32:
        del use_last_error
        return fake

    monkeypatch.setattr("codex_usage_widget.window_runtime.ctypes.CDLL", load_user32)

    # When
    context = read_foreground_process_native()

    # Then
    assert context == ForegroundProcess(name=None, related_process_names=())
    assert fake.GetWindowThreadProcessId.received_pointer is True
    assert fake.GetWindowThreadProcessId.argtypes == [
        ctypes.c_void_p,
        ctypes.POINTER(wintypes.DWORD),
    ]


@pytest.mark.parametrize("hwnd", [0, 2**40])
def test_invalid_pointer_sized_hwnds_fail_cleanly(hwnd: int) -> None:
    # Given / When / Then
    assert set_window_zorder(hwnd, "normal") is False
    assert hide_from_taskbar(hwnd) is False
