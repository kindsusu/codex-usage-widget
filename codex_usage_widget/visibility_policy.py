"""Resolve requested surface preferences into safe effective visibility."""

from dataclasses import dataclass
from enum import StrEnum


class VisibilityFallback(StrEnum):
    """Why the desktop is visible beyond the saved user preference."""

    TASKBAR_UNAVAILABLE = "taskbar_unavailable"
    NO_RESTORE_PATH = "no_restore_path"


@dataclass(frozen=True, slots=True)
class EffectiveVisibility:
    """Effective surfaces plus an optional temporary desktop fallback."""

    desktop: bool
    taskbar: bool
    fallback: VisibilityFallback | None = None


def resolve_visibility(
    *,
    desktop_requested: bool,
    taskbar_requested: bool,
    taskbar_attached: bool,
    tray_available: bool,
) -> EffectiveVisibility:
    """Keep one recovery surface without mutating persisted preferences."""
    taskbar = taskbar_requested and taskbar_attached
    if desktop_requested:
        return EffectiveVisibility(desktop=True, taskbar=taskbar)
    if taskbar_requested and not taskbar_attached:
        return EffectiveVisibility(
            desktop=True,
            taskbar=False,
            fallback=VisibilityFallback.TASKBAR_UNAVAILABLE,
        )
    if not taskbar_requested and not tray_available:
        return EffectiveVisibility(
            desktop=True,
            taskbar=False,
            fallback=VisibilityFallback.NO_RESTORE_PATH,
        )
    return EffectiveVisibility(desktop=False, taskbar=taskbar)
