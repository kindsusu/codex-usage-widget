"""Immutable configuration actions shared by UI adapters."""

from dataclasses import dataclass, replace
from enum import StrEnum

from codex_usage_widget.assets import PET_NAMES
from codex_usage_widget.config import ThemeName, WidgetConfig


class MenuCommand(StrEnum):
    """Commands available from the context menu and keyboard routes."""

    REFRESH = "refresh"
    THEME = "theme"
    MINI = "mini"
    SMART_TOPMOST = "smart_topmost"
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
    """Flip between full and compact battery layouts."""
    return replace(config, mini_mode=not config.mini_mode)


def toggle_smart_topmost(config: WidgetConfig) -> WidgetConfig:
    """Flip foreground-sensitive z-order behavior."""
    return replace(config, smart_topmost=not config.smart_topmost)


def build_menu_model(config: WidgetConfig) -> tuple[MenuItemModel, ...]:
    """Build the menu's portable labels and checked states."""
    return (
        MenuItemModel(MenuCommand.REFRESH, "지금 새로고침"),
        MenuItemModel(
            MenuCommand.THEME,
            "다크 테마",
            checked=config.theme is ThemeName.DARK,
        ),
        MenuItemModel(MenuCommand.MINI, "미니 모드", checked=config.mini_mode),
        MenuItemModel(
            MenuCommand.SMART_TOPMOST,
            "스마트 항상 위",
            checked=config.smart_topmost,
        ),
        MenuItemModel(MenuCommand.HIDE, "트레이로 숨기기"),
        MenuItemModel(MenuCommand.EXIT, "종료"),
    )
