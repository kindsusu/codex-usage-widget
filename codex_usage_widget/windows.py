# pyright: reportAny=false, reportUnknownMemberType=false
"""Import-safe pure geometry and guarded Windows integration helpers."""

from __future__ import annotations

import ctypes
import os
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Final, Literal

if TYPE_CHECKING:
    from collections.abc import Callable


@dataclass(frozen=True, slots=True)
class WindowPosition:
    """Top-left window coordinates in physical pixels."""

    x: int
    y: int


@dataclass(frozen=True, slots=True)
class WindowSize:
    """Window dimensions in physical pixels."""

    width: int
    height: int


@dataclass(frozen=True, slots=True)
class MonitorRect:
    """One monitor's virtual-desktop bounds."""

    left: int
    top: int
    right: int
    bottom: int


_SINGLETON_NAME: Final = "codex-usage-widget-singleton"
_RESTORE_EVENT_NAME: Final = "Local\\codex-usage-widget-restore-v1"
_MIN_VISIBLE_AREA: Final = 800
_ERROR_ALREADY_EXISTS: Final = 183
_EVENT_MODIFY_STATE: Final = 0x0002
_WAIT_OBJECT_0: Final = 0
_FALSE: Final = 0
_GA_ROOT: Final = 2
_SWP_ZORDER_FLAGS: Final = 0x13
_SWP_FRAME_CHANGED_FLAGS: Final = 0x37
_GWL_EXSTYLE: Final = -20
_WS_EX_TOOLWINDOW: Final = 0x00000080
_WS_EX_APPWINDOW: Final = 0x00040000
_singleton_handles: Final[list[int]] = []
_restore_event_handles: Final[list[int]] = []


class SingleInstanceStatus(StrEnum):
    """Result of attempting to become the widget's primary instance."""

    ACQUIRED = "acquired"
    ALREADY_RUNNING = "already_running"
    UNAVAILABLE = "unavailable"


def taskbar_hidden_exstyle(exstyle: int) -> int:
    """Compose the extended style that keeps a window off the taskbar.

    Clears WS_EX_APPWINDOW and sets WS_EX_TOOLWINDOW while preserving every
    other bit. Idempotent, so repeated calls after attribute churn are safe.
    """
    return (exstyle & ~_WS_EX_APPWINDOW) | _WS_EX_TOOLWINDOW


@dataclass(frozen=True, slots=True)
class _UnaryIntFunction:
    call: Callable[[int], int]


@dataclass(frozen=True, slots=True)
class _NullaryIntFunction:
    call: Callable[[], int]


@dataclass(frozen=True, slots=True)
class _CreateMutexFunction:
    call: Callable[[None, int, str], int | None]


@dataclass(frozen=True, slots=True)
class _CloseHandleFunction:
    call: Callable[[int], int]


@dataclass(frozen=True, slots=True)
class _SetWindowPosFunction:
    call: Callable[[int, int, int, int, int, int, int], int]


@dataclass(frozen=True, slots=True)
class _GetAncestorFunction:
    call: Callable[[int, int], int | None]


@dataclass(frozen=True, slots=True)
class _GetWindowLongFunction:
    call: Callable[[int, int], int]


@dataclass(frozen=True, slots=True)
class _SetWindowLongFunction:
    call: Callable[[int, int, int], int]


def singleton_name() -> str:
    """Return the stable Windows named-mutex identifier."""
    return _SINGLETON_NAME


def resolve_window_position(
    saved: WindowPosition | None,
    size: WindowSize,
    monitors: tuple[MonitorRect, ...],
) -> WindowPosition:
    """Keep visible positions and recover invalid ones deterministically."""
    if saved is not None and any(
        _visible_area(saved, size, monitor) >= _MIN_VISIBLE_AREA for monitor in monitors
    ):
        return saved
    if not monitors:
        return WindowPosition(x=100, y=100)
    first = monitors[0]
    max_x = max(first.left, first.right - size.width)
    max_y = max(first.top, first.bottom - size.height)
    return WindowPosition(
        x=min(first.left + 100, max_x),
        y=min(first.top + 100, max_y),
    )


def enable_dpi_awareness() -> bool:
    """Enable native Windows DPI rendering before Tk creates its root."""
    if os.name != "nt":
        return False
    try:
        shcore = ctypes.CDLL("shcore")
        shcore.SetProcessDpiAwareness.argtypes = [ctypes.c_int]
        shcore.SetProcessDpiAwareness.restype = ctypes.c_long
        set_awareness = _UnaryIntFunction(call=shcore.SetProcessDpiAwareness)
        result = set_awareness.call(1)
    except (AttributeError, OSError):
        try:
            user32 = ctypes.CDLL("user32")
            user32.SetProcessDPIAware.argtypes = []
            user32.SetProcessDPIAware.restype = ctypes.c_int
            set_aware = _NullaryIntFunction(call=user32.SetProcessDPIAware)
        except (AttributeError, OSError):
            return False
        else:
            return bool(set_aware.call())
    else:
        return result in (0, -2147024891)


def acquire_single_instance_status(
    name: str = _SINGLETON_NAME,
) -> SingleInstanceStatus:
    """Acquire the process mutex while preserving duplicate/error identity."""
    if os.name != "nt":
        return SingleInstanceStatus.ACQUIRED
    try:
        kernel32 = ctypes.CDLL("kernel32", use_last_error=True)
        kernel32.CreateMutexW.argtypes = [
            ctypes.c_void_p,
            ctypes.c_int,
            ctypes.c_wchar_p,
        ]
        kernel32.CreateMutexW.restype = ctypes.c_void_p
        create_mutex = _CreateMutexFunction(call=kernel32.CreateMutexW)
        handle = create_mutex.call(None, _FALSE, name)
    except (AttributeError, OSError, TypeError, ValueError):
        return SingleInstanceStatus.UNAVAILABLE
    if not handle:
        return SingleInstanceStatus.UNAVAILABLE
    handle_number = int(handle)
    if ctypes.get_last_error() == _ERROR_ALREADY_EXISTS:
        kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        kernel32.CloseHandle.restype = ctypes.c_int
        close_handle = _CloseHandleFunction(call=kernel32.CloseHandle)
        _ = close_handle.call(handle_number)
        return SingleInstanceStatus.ALREADY_RUNNING
    _singleton_handles.append(handle_number)
    return SingleInstanceStatus.ACQUIRED


def acquire_single_instance(name: str = _SINGLETON_NAME) -> bool:
    """Compatibility wrapper returning whether this process became primary."""
    return acquire_single_instance_status(name) is SingleInstanceStatus.ACQUIRED


def create_restore_event(name: str = _RESTORE_EVENT_NAME) -> bool:
    """Create the primary instance's auto-reset desktop-restore event."""
    if os.name != "nt":
        return True
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateEventW.argtypes = [
            ctypes.c_void_p,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_wchar_p,
        ]
        kernel32.CreateEventW.restype = ctypes.c_void_p
        handle = kernel32.CreateEventW(None, 0, 0, name)
    except (AttributeError, OSError, TypeError, ValueError):
        return False
    if not handle:
        return False
    _restore_event_handles.append(int(handle))
    return True


def request_existing_instance_restore(name: str = _RESTORE_EVENT_NAME) -> bool:
    """Signal a compatible running instance to restore its desktop surface."""
    if os.name != "nt":
        return False
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenEventW.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_wchar_p]
        kernel32.OpenEventW.restype = ctypes.c_void_p
        kernel32.SetEvent.argtypes = [ctypes.c_void_p]
        kernel32.SetEvent.restype = ctypes.c_int
        kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        kernel32.CloseHandle.restype = ctypes.c_int
        handle = kernel32.OpenEventW(_EVENT_MODIFY_STATE, 0, name)
        if not handle:
            return False
        try:
            return bool(kernel32.SetEvent(handle))
        finally:
            _ = kernel32.CloseHandle(handle)
    except (AttributeError, OSError, TypeError, ValueError):
        return False


def consume_restore_request() -> bool:
    """Consume one pending restore request without blocking Tk."""
    if os.name != "nt" or not _restore_event_handles:
        return False
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        kernel32.WaitForSingleObject.restype = ctypes.c_ulong
        result = kernel32.WaitForSingleObject(_restore_event_handles[-1], 0)
    except (AttributeError, OSError, TypeError, ValueError):
        return False
    else:
        return result == _WAIT_OBJECT_0


def release_single_instance() -> None:
    """Release the held singleton mutex if this process owns one."""
    if os.name != "nt":
        return
    _close_restore_events()
    if not _singleton_handles:
        return
    handle = _singleton_handles.pop()
    try:
        kernel32 = ctypes.CDLL("kernel32")
        kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        kernel32.CloseHandle.restype = ctypes.c_int
        close_handle = _CloseHandleFunction(call=kernel32.CloseHandle)
        _ = close_handle.call(handle)
    except (AttributeError, OSError):
        return


def _close_restore_events() -> None:
    while _restore_event_handles:
        handle = _restore_event_handles.pop()
        try:
            kernel32 = ctypes.WinDLL("kernel32")
            kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
            kernel32.CloseHandle.restype = ctypes.c_int
            _ = kernel32.CloseHandle(handle)
        except (AttributeError, OSError, TypeError, ValueError):
            continue


def set_window_zorder(hwnd: int, mode: Literal["top", "normal", "bottom"]) -> bool:
    """Set a Tk window's Win32 z-order without moving or activating it."""
    if os.name != "nt":
        return False
    targets: Final = {"top": -1, "normal": -2, "bottom": 1}
    try:
        user32 = ctypes.CDLL("user32", use_last_error=True)
        user32.GetAncestor.argtypes = [ctypes.c_void_p, ctypes.c_uint]
        user32.GetAncestor.restype = ctypes.c_void_p
        get_ancestor = _GetAncestorFunction(call=user32.GetAncestor)
        root = get_ancestor.call(hwnd, _GA_ROOT)
        if not root:
            return False
        user32.SetWindowPos.argtypes = [
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_uint,
        ]
        user32.SetWindowPos.restype = ctypes.c_int
        set_window_pos = _SetWindowPosFunction(call=user32.SetWindowPos)
        return bool(
            set_window_pos.call(
                int(root),
                targets[mode],
                0,
                0,
                0,
                0,
                _SWP_ZORDER_FLAGS,
            ),
        )
    except (AttributeError, OSError):
        return False


def hide_from_taskbar(hwnd: int) -> bool:
    """Apply tool-window style so an override-redirect Tk window stays hidden."""
    if os.name != "nt":
        return False
    try:
        user32 = ctypes.CDLL("user32", use_last_error=True)
        user32.GetAncestor.argtypes = [ctypes.c_void_p, ctypes.c_uint]
        user32.GetAncestor.restype = ctypes.c_void_p
        get_ancestor = _GetAncestorFunction(call=user32.GetAncestor)
        root = get_ancestor.call(hwnd, _GA_ROOT)
        if not root:
            return False
        root_number = int(root)
        if ctypes.sizeof(ctypes.c_void_p) == 8:
            get_raw = user32.GetWindowLongPtrW
            set_raw = user32.SetWindowLongPtrW
        else:
            get_raw = user32.GetWindowLongW
            set_raw = user32.SetWindowLongW
        get_raw.argtypes = [ctypes.c_void_p, ctypes.c_int]
        get_raw.restype = ctypes.c_ssize_t
        set_raw.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_ssize_t]
        set_raw.restype = ctypes.c_ssize_t
        get_window_long = _GetWindowLongFunction(call=get_raw)
        set_window_long = _SetWindowLongFunction(call=set_raw)
        _ = ctypes.set_last_error(0)
        style = get_window_long.call(root_number, _GWL_EXSTYLE)
        if style == 0 and ctypes.get_last_error() != 0:
            return False
        new_style = taskbar_hidden_exstyle(style)
        _ = ctypes.set_last_error(0)
        previous_style = set_window_long.call(root_number, _GWL_EXSTYLE, new_style)
        if previous_style == 0 and ctypes.get_last_error() != 0:
            return False
        user32.SetWindowPos.argtypes = [
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_uint,
        ]
        user32.SetWindowPos.restype = ctypes.c_int
        set_window_pos = _SetWindowPosFunction(call=user32.SetWindowPos)
        return bool(
            set_window_pos.call(
                root_number,
                0,
                0,
                0,
                0,
                0,
                _SWP_FRAME_CHANGED_FLAGS,
            ),
        )
    except (AttributeError, OSError, TypeError, ValueError):
        return False


def _visible_area(
    position: WindowPosition,
    size: WindowSize,
    monitor: MonitorRect,
) -> int:
    width = max(
        0,
        min(position.x + size.width, monitor.right) - max(position.x, monitor.left),
    )
    height = max(
        0,
        min(position.y + size.height, monitor.bottom) - max(position.y, monitor.top),
    )
    return width * height
