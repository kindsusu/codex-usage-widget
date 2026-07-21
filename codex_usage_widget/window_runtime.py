# pyright: reportAny=false, reportUnknownArgumentType=false, reportUnknownMemberType=false
"""Pointer-safe Win32 foreground process discovery."""

from __future__ import annotations

import ctypes
import os
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import PureWindowsPath
from typing import TYPE_CHECKING, ClassVar, Final, Literal, Protocol, final

from codex_usage_widget.windows import (
    MonitorRect,
    WindowPosition,
    WindowSize,
    resolve_window_position,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    class _VirtualDesktopSource(Protocol):
        def winfo_vrootx(self) -> int: ...

        def winfo_vrooty(self) -> int: ...

        def winfo_vrootwidth(self) -> int: ...

        def winfo_vrootheight(self) -> int: ...

    class _DwordPointer(Protocol):
        contents: wintypes.DWORD

    class _ProcessEntryPointer(Protocol):
        contents: _ProcessEntry


_SNAP_PROCESS: Final = 0x00000002
_MAX_PATH: Final = 260
_DIRECT_CODEX_NAMES: Final = frozenset(
    {"codex.exe", "codex-desktop.exe", "codex app.exe", "openai codex.exe"},
)
_TERMINAL_NAMES: Final = frozenset(
    {"windowsterminal.exe", "powershell.exe", "pwsh.exe", "cmd.exe", "conhost.exe"},
)


@final
class _ProcessEntry(ctypes.Structure):
    _fields_: ClassVar = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.c_size_t),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", wintypes.LONG),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", wintypes.WCHAR * _MAX_PATH),
    ]


@dataclass(frozen=True, slots=True)
class _NullaryPointerFunction:
    call: Callable[[], int | None]


@dataclass(frozen=True, slots=True)
class _WindowPidFunction:
    call: Callable[[int, _DwordPointer], int]


@dataclass(frozen=True, slots=True)
class _SnapshotFunction:
    call: Callable[[int, int], int | None]


@dataclass(frozen=True, slots=True)
class _ProcessIteratorFunction:
    call: Callable[[int, _ProcessEntryPointer], int]


@dataclass(frozen=True, slots=True)
class _CloseHandleFunction:
    call: Callable[[int], int]


@dataclass(frozen=True, slots=True)
class ForegroundProcess:
    """Foreground executable and only its descendant executable names."""

    name: str | None
    related_process_names: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ProcessRecord:
    """Minimal process-tree row used by foreground classification."""

    pid: int
    parent_pid: int
    name: str


def foreground_process_from_records(
    foreground_pid: int,
    records: tuple[ProcessRecord, ...],
) -> ForegroundProcess:
    """Build a foreground context from an injected immutable process table."""
    foreground = next((row for row in records if row.pid == foreground_pid), None)
    if foreground is None:
        return ForegroundProcess(name=None, related_process_names=())
    descendants: list[str] = []
    pending = [foreground_pid]
    while pending:
        parent_pid = pending.pop()
        children = tuple(row for row in records if row.parent_pid == parent_pid)
        descendants.extend(child.name for child in children)
        pending.extend(child.pid for child in children)
    return ForegroundProcess(
        name=foreground.name,
        related_process_names=tuple(descendants),
    )


def format_window_position(x: int, y: int) -> str:
    """Format Tk coordinates with one sign per axis, including negatives."""
    return f"{x:+d}{y:+d}"


def is_codex_foreground(
    foreground_process_name: str | None,
    related_process_names: tuple[str, ...],
) -> bool:
    """Classify direct Codex windows or a terminal hosting a Codex process."""
    foreground = _normalized_name(foreground_process_name)
    if foreground in _DIRECT_CODEX_NAMES:
        return True
    return foreground in _TERMINAL_NAMES and any(
        _normalized_name(name) in _DIRECT_CODEX_NAMES for name in related_process_names
    )


def is_codex_running(records: tuple[ProcessRecord, ...]) -> bool:
    """Return whether a supported Codex executable exists in a process table."""
    return any(_normalized_name(row.name) in _DIRECT_CODEX_NAMES for row in records)


def window_layer(
    smart_enabled: bool,
    codex_running: bool,
) -> Literal["top", "bottom"]:
    """Map the live Codex process state to the widget's native window layer."""
    return "top" if smart_enabled and codex_running else "bottom"


def should_keep_topmost(
    smart_enabled: bool,
    *,
    widget_focused: bool,
    foreground: ForegroundProcess,
) -> bool:
    """Enable topmost only for widget focus or a Codex-related foreground."""
    return smart_enabled and (
        widget_focused
        or is_codex_foreground(foreground.name, foreground.related_process_names)
    )


def resolve_initial_position(
    saved: WindowPosition | None,
    desktop: _VirtualDesktopSource,
) -> WindowPosition:
    """Resolve a saved position against bounds reported by the Tk virtual root."""
    left = desktop.winfo_vrootx()
    top = desktop.winfo_vrooty()
    monitor = MonitorRect(
        left=left,
        top=top,
        right=left + desktop.winfo_vrootwidth(),
        bottom=top + desktop.winfo_vrootheight(),
    )
    return resolve_window_position(saved, WindowSize(260, 170), (monitor,))


def read_foreground_process() -> ForegroundProcess:
    """Read the foreground process tree without exposing Win32 failures."""
    if os.name != "nt":
        return ForegroundProcess(name=None, related_process_names=())
    try:
        return read_foreground_process_native()
    except (AttributeError, OSError, TypeError, ValueError):
        return ForegroundProcess(name=None, related_process_names=())


def read_codex_running() -> bool:
    """Read global Codex process presence without exposing Win32 failures."""
    if os.name != "nt":
        return False
    try:
        return is_codex_running(_read_process_records())
    except (AttributeError, OSError, TypeError, ValueError):
        return False


def read_foreground_process_native() -> ForegroundProcess:
    """Read foreground PID and descendants using pointer-sized Win32 types."""
    user32 = ctypes.CDLL("user32", use_last_error=True)
    user32.GetForegroundWindow.argtypes = []
    user32.GetForegroundWindow.restype = ctypes.c_void_p
    get_foreground = _NullaryPointerFunction(call=user32.GetForegroundWindow)
    hwnd = get_foreground.call()
    if not hwnd:
        return ForegroundProcess(name=None, related_process_names=())
    user32.GetWindowThreadProcessId.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(wintypes.DWORD),
    ]
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    get_pid = _WindowPidFunction(call=user32.GetWindowThreadProcessId)
    pid = wintypes.DWORD()
    pid_pointer = ctypes.pointer(pid)
    if get_pid.call(hwnd, pid_pointer) == 0 or pid.value == 0:
        return ForegroundProcess(name=None, related_process_names=())
    return foreground_process_from_records(pid.value, _read_process_records())


def _read_process_records() -> tuple[ProcessRecord, ...]:
    kernel32 = ctypes.CDLL("kernel32", use_last_error=True)
    kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel32.CreateToolhelp32Snapshot.restype = ctypes.c_void_p
    create_snapshot = _SnapshotFunction(call=kernel32.CreateToolhelp32Snapshot)
    handle = create_snapshot.call(_SNAP_PROCESS, 0)
    if not handle or handle == ctypes.c_void_p(-1).value:
        return ()
    kernel32.Process32FirstW.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(_ProcessEntry),
    ]
    kernel32.Process32FirstW.restype = wintypes.BOOL
    kernel32.Process32NextW.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(_ProcessEntry),
    ]
    kernel32.Process32NextW.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    kernel32.CloseHandle.restype = wintypes.BOOL
    first = _ProcessIteratorFunction(call=kernel32.Process32FirstW)
    next_entry = _ProcessIteratorFunction(call=kernel32.Process32NextW)
    close_handle = _CloseHandleFunction(call=kernel32.CloseHandle)
    entry = _ProcessEntry()
    entry.dwSize = ctypes.sizeof(_ProcessEntry)
    entry_pointer = ctypes.pointer(entry)
    records: list[ProcessRecord] = []
    try:
        available = bool(first.call(handle, entry_pointer))
        while available:
            records.append(
                ProcessRecord(
                    pid=int(entry.th32ProcessID),
                    parent_pid=int(entry.th32ParentProcessID),
                    name=str(entry.szExeFile),
                )
            )
            available = bool(next_entry.call(handle, entry_pointer))
    finally:
        _ = close_handle.call(handle)
    return tuple(records)


def _normalized_name(name: str | None) -> str:
    if name is None:
        return ""
    return PureWindowsPath(name).name.casefold()
