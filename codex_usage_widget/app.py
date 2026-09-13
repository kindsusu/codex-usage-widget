"""Public app actions and the executable entry boundary."""

from codex_usage_widget.actions import (
    MenuCommand,
    MenuItemModel,
    build_menu_model,
    set_opacity,
    set_pet,
    set_scale,
    toggle_desktop_visibility,
    toggle_mini_mode,
    toggle_smart_topmost,
    toggle_taskbar_visibility,
    toggle_theme,
)

__all__ = [
    "MenuCommand",
    "MenuItemModel",
    "build_menu_model",
    "main",
    "set_opacity",
    "set_pet",
    "set_scale",
    "toggle_desktop_visibility",
    "toggle_mini_mode",
    "toggle_smart_topmost",
    "toggle_taskbar_visibility",
    "toggle_theme",
]


def main() -> int:
    """Start the native widget runtime."""
    from codex_usage_widget.startup import report_startup_problem  # noqa: PLC0415

    try:
        from codex_usage_widget.runtime import run_widget  # noqa: PLC0415

        return run_widget()
    except Exception:  # noqa: BLE001  # noqa: BROAD_EXCEPT_OK
        report_startup_problem("startup_error")
        return 1
