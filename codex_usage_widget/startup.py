# pyright: reportAny=false, reportUnknownMemberType=false
"""Visible, privacy-safe startup diagnostics for console-free launches."""

from __future__ import annotations

import ctypes
import os
from datetime import datetime
from pathlib import Path
from typing import Final, Literal, TypeAlias

_TITLE: Final = "Codex 사용량 위젯"
_MESSAGES: Final = {
    "already_running": "이미 실행 중입니다. 트레이에서 종료한 뒤 다시 실행해 주세요.",
    "single_instance_error": (
        "위젯 실행 상태를 확인할 수 없습니다. 잠시 후 다시 시도해 주세요."
    ),
    "startup_error": "위젯을 시작하지 못했습니다. 설치 상태를 확인해 주세요.",
    "launch_error": (
        "위젯을 독립 프로세스로 시작하지 못했습니다. "
        "Windows 관리 서비스 상태를 확인한 뒤 다시 시도해 주세요."
    ),
}
_LIFECYCLE_LOG_FILENAME: Final = "lifecycle.log"
_MAX_LIFECYCLE_LOG_BYTES: Final = 64 * 1024
LifecycleEvent: TypeAlias = Literal[
    "started",
    "user_exit",
    "update_restart",
    "mainloop_return",
]


def report_startup_problem(category: str) -> None:
    """Show one finite message and record only its non-sensitive category."""
    message = _MESSAGES.get(category, _MESSAGES["startup_error"])
    _write_diagnostic(category if category in _MESSAGES else "startup_error")
    _show_message(message)


def report_lifecycle_event(
    event: LifecycleEvent | Literal["fatal"],
    error_type: type[BaseException] | None = None,
) -> None:
    """Append a bounded, privacy-safe process lifecycle marker.

    Events are a closed set. Fatal markers accept an exception *type*, never
    an exception instance or message, so RPC payloads, paths, and tokens cannot
    reach the diagnostic file.
    """
    if event == "fatal":
        name = "Exception" if error_type is None else error_type.__name__
        safe_name = name if name.isidentifier() else "Exception"
        marker = f"fatal:{safe_name}"
    else:
        marker = event
    base = os.environ.get("LOCALAPPDATA")
    if not base:
        return
    path = Path(base) / "CodexUsageWidget" / _LIFECYCLE_LOG_FILENAME
    timestamp = datetime.now().astimezone().isoformat(timespec="seconds")
    _append_bounded(path, f"{timestamp} {marker}\n".encode())


def _show_message(message: str) -> None:
    if os.name != "nt":
        return
    try:
        user32 = ctypes.WinDLL("user32")
        user32.MessageBoxW.argtypes = [
            ctypes.c_void_p,
            ctypes.c_wchar_p,
            ctypes.c_wchar_p,
            ctypes.c_uint,
        ]
        user32.MessageBoxW.restype = ctypes.c_int
        user32.MessageBoxW(None, message, _TITLE, 0x10)
    except (AttributeError, OSError, TypeError, ValueError):
        return


def _write_diagnostic(category: str) -> None:
    base = os.environ.get("LOCALAPPDATA")
    if not base:
        return
    path = Path(base) / "CodexUsageWidget" / "startup.log"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().astimezone().isoformat(timespec="seconds")
        _ = path.write_text(f"{timestamp} {category}\n", encoding="utf-8")
    except OSError:
        return


def _append_bounded(path: Path, line: bytes) -> None:
    """Append one short line while retaining only recent complete records."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        mode = "r+b" if path.exists() else "w+b"
        with path.open(mode) as log:
            _ = log.seek(0, 2)
            current_size = log.tell()
            keep_bytes = _MAX_LIFECYCLE_LOG_BYTES - len(line)
            if current_size > keep_bytes:
                read_bytes = min(current_size, max(keep_bytes, 0))
                _ = log.seek(current_size - read_bytes)
                retained = log.read(read_bytes)
                if current_size > read_bytes:
                    _, separator, retained = retained.partition(b"\n")
                    if not separator:
                        retained = b""
                _ = log.seek(0)
                _ = log.write(retained)
                _ = log.truncate()
            _ = log.seek(0, 2)
            _ = log.write(line[-_MAX_LIFECYCLE_LOG_BYTES:])
    except OSError:
        return
