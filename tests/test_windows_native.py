import ctypes
from ctypes import wintypes
from typing import Protocol, final

import pytest

import codex_usage_widget.windows as windows
from codex_usage_widget.window_runtime import (
    ForegroundProcess,
    read_foreground_process_native,
)
from codex_usage_widget.windows import (
    hide_from_taskbar,
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
        self.received_hwnd = 0
        self.received_flags = 0

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
        self.received_flags = _flags
        return 1


@final
class _GetAncestorFunction:
    argtypes: list[type[ctypes.c_void_p] | type[ctypes.c_uint]] | None = None
    restype: type[ctypes.c_void_p] | None = None
    root_hwnd = 99

    def __init__(self) -> None:
        self.received_hwnd = 0

    def __call__(self, hwnd: int, _flags: int) -> int:
        self.received_hwnd = hwnd
        return self.root_hwnd


@final
class _GetWindowLongPtrFunction:
    argtypes: list[type[ctypes.c_void_p] | type[ctypes.c_int]] | None = None
    restype: type[ctypes.c_ssize_t] | None = None

    def __call__(self, _hwnd: int, _index: int) -> int:
        return 0x00040000


@final
class _SetWindowLongPtrFunction:
    argtypes: list[type[ctypes.c_void_p] | type[ctypes.c_int]] | None = None
    restype: type[ctypes.c_ssize_t] | None = None

    def __init__(self) -> None:
        self.received_hwnd = 0
        self.received_style = 0

    def __call__(self, hwnd: int, _index: int, style: int) -> int:
        self.received_hwnd = hwnd
        self.received_style = style
        return 0x00040000


@final
class _FakeUser32:
    def __init__(self) -> None:
        self.GetAncestor = _GetAncestorFunction()
        self.SetWindowPos: _SetWindowPosFunction = _SetWindowPosFunction()
        self.GetWindowLongPtrW = _GetWindowLongPtrFunction()
        self.SetWindowLongPtrW = _SetWindowLongPtrFunction()


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


def test_set_window_pos_targets_the_pointer_sized_root_wrapper(
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
    assert result is True
    assert fake.GetAncestor.received_hwnd == large_hwnd
    assert fake.SetWindowPos.received_hwnd == fake.GetAncestor.root_hwnd
    assert fake.SetWindowPos.argtypes is not None
    assert fake.SetWindowPos.argtypes[:2] == [ctypes.c_void_p, ctypes.c_void_p]
    assert fake.SetWindowPos.restype is ctypes.c_int


def test_hide_from_taskbar_styles_root_wrapper_and_refreshes_shell(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given
    fake = _FakeUser32()

    def load_user32(_name: str, *, use_last_error: bool = False) -> _FakeUser32:
        del use_last_error
        return fake

    monkeypatch.setattr("codex_usage_widget.windows.os.name", "nt")
    monkeypatch.setattr("codex_usage_widget.windows.ctypes.CDLL", load_user32)

    # When
    result = hide_from_taskbar(42)

    # Then
    assert result is True
    assert fake.GetAncestor.received_hwnd == 42
    assert fake.SetWindowLongPtrW.received_hwnd == fake.GetAncestor.root_hwnd
    assert fake.SetWindowLongPtrW.received_style & 0x00000080
    assert not fake.SetWindowLongPtrW.received_style & 0x00040000
    assert fake.SetWindowPos.received_hwnd == fake.GetAncestor.root_hwnd
    assert fake.SetWindowPos.received_flags & 0x20


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
