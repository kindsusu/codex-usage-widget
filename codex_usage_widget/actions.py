"""Immutable configuration actions shared by UI adapters."""

from dataclasses import dataclass, replace
from enum import StrEnum

from codex_usage_widget.assets import PET_NAMES
from codex_usage_widget.config import ThemeName, WidgetConfig


class MenuCommand(StrEnum):
    """Commands available from the mouse-driven context menu."""

    REFRESH = "refresh"
    THEME = "theme"
    MINI = "mini"
    SMART_TOPMOST = "smart_topmost"
    DESKTOP_VISIBILITY = "desktop_visibility"
    TASKBAR_VISIBILITY = "taskbar_visibility"
    HIDE = "hide"
    EXIT = "exit"


@dataclass(frozen=True, slots=True)
class MenuItemModel:
    """Display-independent context-menu item."""

    command: MenuCommand
    label: str
    checked: bool = False


def toggle_theme(config: WidgetConfig) -> WidgetConfig:
    """Return a config with the alternate surface theme."""
    theme = ThemeName.DARK if config.theme is ThemeName.LIGHT else ThemeName.LIGHT
    return replace(config, theme=theme)


def set_opacity(config: WidgetConfig, opacity: float) -> WidgetConfig:
    """Clamp opacity to the supported readable range."""
    return replace(config, opacity=max(0.3, min(1.0, opacity)))


def set_scale(config: WidgetConfig, scale: float, *, mini: bool) -> WidgetConfig:
    """Update only the scale belonging to the current layout mode."""
    if mini:
        return replace(config, mini_scale=max(0.5, min(2.0, scale)))
    return replace(config, scale=max(0.75, min(3.0, scale)))


def set_pet(config: WidgetConfig, pet: str) -> WidgetConfig:
    """Select a known pet and preserve config for unknown names."""
    return replace(config, pet=pet) if pet in PET_NAMES else config


def toggle_mini_mode(config: WidgetConfig) -> WidgetConfig:
    """Flip between full and compact battery layouts, and show the widget.

    Switching layout is a request to LOOK at the desktop widget. Without the
    second half, ticking "바탕화면 미니 모드" while the desktop surface is
    hidden only flips a checkbox: the window silently changes size behind the
    scenes and the user sees nothing happen (2026-09-14 bug report).
    """
    return replace(
        config, mini_mode=not config.mini_mode, desktop_visible=True
    )


def toggle_smart_topmost(config: WidgetConfig) -> WidgetConfig:
    """Flip foreground-sensitive z-order behavior."""
    return replace(config, smart_topmost=not config.smart_topmost)


def toggle_desktop_visibility(config: WidgetConfig) -> WidgetConfig:
    """Flip whether the regular desktop widget surface is shown."""
    return replace(config, desktop_visible=not config.desktop_visible)


def toggle_taskbar_visibility(config: WidgetConfig) -> WidgetConfig:
    """Flip whether the native taskbar usage indicator is shown."""
    return replace(config, taskbar_visible=not config.taskbar_visible)


def build_menu_model(config: WidgetConfig) -> tuple[MenuItemModel, ...]:
    """Build the menu's portable labels and checked states."""
    return (
        MenuItemModel(MenuCommand.REFRESH, "새로고침"),
        MenuItemModel(
            MenuCommand.THEME,
            "다크/라이트 전환",
            checked=config.theme is ThemeName.DARK,
        ),
        MenuItemModel(MenuCommand.MINI, "미니모드", checked=config.mini_mode),
        MenuItemModel(
            MenuCommand.SMART_TOPMOST,
            "스마트 포지션 스위칭",
            checked=config.smart_topmost,
        ),
        MenuItemModel(
            MenuCommand.DESKTOP_VISIBILITY,
            "바탕화면 위젯 표시",
            checked=config.desktop_visible,
        ),
        MenuItemModel(
            MenuCommand.TASKBAR_VISIBILITY,
            "작업표시줄 표시",
            checked=config.taskbar_visible,
        ),
        MenuItemModel(MenuCommand.HIDE, "트레이로 숨기기"),
        MenuItemModel(MenuCommand.EXIT, "종료"),
    )
