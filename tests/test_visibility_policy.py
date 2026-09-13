import pytest

from codex_usage_widget.visibility_policy import (
    EffectiveVisibility,
    VisibilityFallback,
    resolve_visibility,
)


@pytest.mark.parametrize(
    ("desktop", "taskbar", "expected"),
    [
        (True, True, EffectiveVisibility(desktop=True, taskbar=True)),
        (True, False, EffectiveVisibility(desktop=True, taskbar=False)),
        (False, True, EffectiveVisibility(desktop=False, taskbar=True)),
        (False, False, EffectiveVisibility(desktop=False, taskbar=False)),
    ],
)
def test_all_requested_visibility_combinations_when_restore_paths_are_healthy(
    desktop: bool,
    taskbar: bool,
    expected: EffectiveVisibility,
) -> None:
    assert (
        resolve_visibility(
            desktop_requested=desktop,
            taskbar_requested=taskbar,
            taskbar_attached=True,
            tray_available=True,
        )
        == expected
    )


def test_taskbar_attachment_failure_temporarily_restores_desktop() -> None:
    resolved = resolve_visibility(
        desktop_requested=False,
        taskbar_requested=True,
        taskbar_attached=False,
        tray_available=True,
    )

    assert resolved == EffectiveVisibility(
        desktop=True,
        taskbar=False,
        fallback=VisibilityFallback.TASKBAR_UNAVAILABLE,
    )


def test_no_tray_or_visible_surface_forces_safe_desktop_restore() -> None:
    resolved = resolve_visibility(
        desktop_requested=False,
        taskbar_requested=False,
        taskbar_attached=False,
        tray_available=False,
    )

    assert resolved.fallback is VisibilityFallback.NO_RESTORE_PATH
    assert resolved.desktop is True
