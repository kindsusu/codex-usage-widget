from dataclasses import replace

from codex_usage_widget.assets import PET_NAMES
from codex_usage_widget.config import ThemeName, WidgetConfig
from codex_usage_widget.app import (
    MenuCommand,
    build_menu_model,
    set_opacity,
    set_pet,
    set_scale,
    toggle_mini_mode,
    toggle_smart_topmost,
    toggle_theme,
)


def test_toggle_theme_when_light_selects_dark() -> None:
    # Given
    config = WidgetConfig(theme=ThemeName.LIGHT)

    # When
    updated = toggle_theme(config)

    # Then
    assert updated.theme is ThemeName.DARK


def test_set_opacity_when_below_supported_range_clamps_to_thirty_percent() -> None:
    # Given
    config = WidgetConfig()

    # When
    updated = set_opacity(config, 0.1)

    # Then
    assert updated.opacity == 0.3


def test_set_scale_when_mini_uses_mini_scale_only() -> None:
    # Given
    config = WidgetConfig(scale=1.0, mini_scale=1.0)

    # When
    updated = set_scale(config, 1.5, mini=True)

    # Then
    assert updated == replace(config, mini_scale=1.5)


def test_set_pet_when_name_is_known_updates_selection() -> None:
    # Given
    config = WidgetConfig()

    # When
    updated = set_pet(config, PET_NAMES[-1])

    # Then
    assert updated.pet == PET_NAMES[-1]


def test_toggle_commands_when_invoked_flip_only_their_fields() -> None:
    # Given
    config = WidgetConfig(mini_mode=False, smart_topmost=True)

    # When
    mini = toggle_mini_mode(config)
    topmost = toggle_smart_topmost(config)

    # Then
    assert mini == replace(config, mini_mode=True)
    assert topmost == replace(config, smart_topmost=False)


def test_menu_model_when_built_exposes_keyboard_equivalent_core_actions() -> None:
    # Given
    config = WidgetConfig(theme=ThemeName.DARK, smart_topmost=False)

    # When
    model = build_menu_model(config)

    # Then
    commands = {item.command for item in model}
    assert commands >= {
        MenuCommand.REFRESH,
        MenuCommand.THEME,
        MenuCommand.MINI,
        MenuCommand.SMART_TOPMOST,
        MenuCommand.HIDE,
        MenuCommand.EXIT,
    }
    assert next(item for item in model if item.command is MenuCommand.THEME).checked
    assert not next(
        item for item in model if item.command is MenuCommand.SMART_TOPMOST
    ).checked
