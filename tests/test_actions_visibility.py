from dataclasses import replace

import pytest

from codex_usage_widget.actions import (
    DesktopMode,
    MenuCommand,
    build_menu_model,
    set_desktop_mode,
    toggle_desktop_visibility,
    toggle_taskbar_visibility,
)
from codex_usage_widget.config import WidgetConfig
from codex_usage_widget.windows import WindowPosition


@pytest.mark.parametrize(
    ("desktop_visible", "taskbar_visible"),
    [(True, True), (True, False), (False, True), (False, False)],
)
def test_visibility_toggles_preserve_other_persisted_display_settings(
    desktop_visible: bool,
    taskbar_visible: bool,
) -> None:
    config = WidgetConfig(
        mini_mode=True,
        mini_scale=1.5,
        position=WindowPosition(-900, 140),
        desktop_visible=desktop_visible,
        taskbar_visible=taskbar_visible,
    )

    desktop = toggle_desktop_visibility(config)
    taskbar = toggle_taskbar_visibility(config)

    expected_mode = DesktopMode.HIDDEN if desktop_visible else DesktopMode.NORMAL
    assert desktop == set_desktop_mode(config, expected_mode)
    assert taskbar == replace(config, taskbar_visible=not taskbar_visible)


def test_menu_visibility_rows_mirror_each_visibility_preference() -> None:
    config = WidgetConfig(desktop_visible=False, taskbar_visible=True)

    checked = {item.command: item.checked for item in build_menu_model(config)}

    assert checked[MenuCommand.DESKTOP_VISIBILITY] is False
    assert checked[MenuCommand.MINI] is False
    assert checked[MenuCommand.HIDE] is True
    assert checked[MenuCommand.TASKBAR_VISIBILITY] is True
