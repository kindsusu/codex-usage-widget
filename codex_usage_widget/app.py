"""Public app actions and the executable entry boundary."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

from codex_usage_widget.actions import (
    DesktopMode,
    MenuCommand,
    MenuItemModel,
    build_menu_model,
    desktop_mode,
    set_desktop_mode,
    set_opacity,
    set_pet,
    set_scale,
    toggle_auto_update,
    toggle_desktop_visibility,
    toggle_mini_mode,
    toggle_smart_topmost,
    toggle_taskbar_visibility,
    toggle_theme,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

__all__ = [
    "DesktopMode",
    "MenuCommand",
    "MenuItemModel",
    "build_menu_model",
    "desktop_mode",
    "main",
    "set_desktop_mode",
    "set_opacity",
    "set_pet",
    "set_scale",
    "toggle_auto_update",
    "toggle_desktop_visibility",
    "toggle_mini_mode",
    "toggle_smart_topmost",
    "toggle_taskbar_visibility",
    "toggle_theme",
]


def main(argv: Sequence[str] | None = None) -> int:
    """Start the native widget runtime, or run the shared release gate.

    ``--selftest`` is handled before anything touches Tk, the singleton mutex,
    or the config file: the release workflow and the auto-updater both run it
    against an unpacked tree that must stay untouched.
    """
    arguments = sys.argv[1:] if argv is None else list(argv)
    if "--selftest" in arguments:
        from codex_usage_widget.selftest import run_selftest  # noqa: PLC0415

        return run_selftest()
    from codex_usage_widget.startup import report_startup_problem  # noqa: PLC0415

    try:
        from codex_usage_widget.runtime import run_widget  # noqa: PLC0415

        return run_widget()
    except Exception:  # noqa: BLE001  # noqa: BROAD_EXCEPT_OK
        report_startup_problem("startup_error")
        return 1
