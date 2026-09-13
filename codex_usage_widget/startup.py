# pyright: reportAny=false, reportUnknownMemberType=false
"""Visible, privacy-safe startup diagnostics for console-free launches."""

from __future__ import annotations

import ctypes
import os
from datetime import datetime
from pathlib import Path
from typing import Final

_TITLE: Final = "Codex 사용량 위젯"
_MESSAGES: Final = {
    "already_running": "이미 실행 중입니다. 트레이에서 종료한 뒤 다시 실행해 주세요.",
    "single_instance_error": (
        "위젯 실행 상태를 확인할 수 없습니다. 잠시 후 다시 시도해 주세요."
    ),
    "startup_error": "위젯을 시작하지 못했습니다. 설치 상태를 확인해 주세요.",
}


def report_startup_problem(category: str) -> None:
    """Show one finite message and record only its non-sensitive category."""
    message = _MESSAGES.get(category, _MESSAGES["startup_error"])
    _write_diagnostic(category if category in _MESSAGES else "startup_error")
    _show_message(message)


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
