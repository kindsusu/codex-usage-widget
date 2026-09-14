from dataclasses import replace

import pytest

from codex_usage_widget.assets import PET_NAMES
from codex_usage_widget.config import ThemeName, WidgetConfig
from codex_usage_widget.app import (
    DesktopMode,
    MenuCommand,
    build_menu_model,
    desktop_mode,
    set_desktop_mode,
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
    # a layout switch also un-hides the desktop widget, otherwise the toggle
    # silently resizes a hidden window and the user sees nothing happen
    assert mini == replace(config, mini_mode=True, desktop_visible=True)
    assert topmost == replace(config, smart_topmost=False)


def test_mini_toggle_reveals_a_hidden_desktop_widget() -> None:
    hidden = WidgetConfig(mini_mode=True, desktop_visible=False)

    shown = toggle_mini_mode(hidden)

    assert shown.mini_mode is True
    assert shown.desktop_visible is True


@pytest.mark.parametrize(
    ("mode", "visible", "mini"),
    [
        (DesktopMode.NORMAL, True, False),
        (DesktopMode.MINI, True, True),
        (DesktopMode.HIDDEN, False, False),
    ],
)
def test_set_desktop_mode_writes_one_canonical_state(
    mode: DesktopMode, visible: bool, mini: bool
) -> None:
    config = WidgetConfig(taskbar_visible=False, desktop_visible=False, mini_mode=True)

    updated = set_desktop_mode(config, mode)

    assert updated.desktop_visible is visible
    assert updated.mini_mode is mini
    assert updated.taskbar_visible is False
    assert desktop_mode(updated) is mode


def test_menu_model_exposes_plain_korean_labels_and_checked_state() -> None:
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
    labels = {item.command: item.label for item in model}
    assert labels[MenuCommand.REFRESH] == "새로고침"
    assert labels[MenuCommand.THEME] == "다크/라이트 전환"
    assert labels[MenuCommand.DESKTOP_VISIBILITY] == "데스크톱 일반 모드"
    assert labels[MenuCommand.MINI] == "데스크톱 미니 모드"
    assert labels[MenuCommand.SMART_TOPMOST] == "스마트 포지션 스위칭"
    assert labels[MenuCommand.HIDE] == "데스크톱 숨기기"
    assert labels[MenuCommand.EXIT] == "종료"
    # No accelerator/shortcut hints remain in any label.
    assert all("Ctrl" not in item.label and "\t" not in item.label for item in model)
    assert next(item for item in model if item.command is MenuCommand.THEME).checked
    assert not next(
        item for item in model if item.command is MenuCommand.SMART_TOPMOST
    ).checked


@pytest.mark.parametrize(
    ("mini", "smart", "dark"),
    [(True, True, True), (False, False, False)],
)
def test_menu_model_checked_flags_track_every_toggle(
    mini: bool, smart: bool, dark: bool
) -> None:
    # Given
    config = WidgetConfig(
        theme=ThemeName.DARK if dark else ThemeName.LIGHT,
        mini_mode=mini,
        smart_topmost=smart,
    )

    # When
    checked = {item.command: item.checked for item in build_menu_model(config)}

    # Then each toggle row mirrors its live config field...
    assert checked[MenuCommand.DESKTOP_VISIBILITY] is (not mini)
    assert checked[MenuCommand.MINI] is mini
    assert checked[MenuCommand.SMART_TOPMOST] is smart
    assert checked[MenuCommand.THEME] is dark
    # ...and the plain command rows are never checked.
    assert checked[MenuCommand.REFRESH] is False
    assert checked[MenuCommand.HIDE] is False
    assert checked[MenuCommand.EXIT] is False
