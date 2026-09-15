"""Typed widget configuration with safe recovery and atomic persistence."""

from __future__ import annotations

import json
import os
import random
import tempfile
from contextlib import suppress
from dataclasses import dataclass, replace
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Final, TypeAlias, TypedDict, final

from codex_usage_widget.assets import PET_NAMES
from codex_usage_widget.windows import WindowPosition

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

ConfigJson: TypeAlias = (
    str | int | float | bool | list["ConfigJson"] | dict[str, "ConfigJson"] | None
)
_MIN_OPACITY: Final = 0.3
_MIN_SCALE: Final = 0.75
_MAX_SCALE: Final = 3.0
_MIN_MINI_SCALE: Final = 0.5
_MAX_MINI_SCALE: Final = 2.0
_MIN_REFRESH_SECONDS: Final = 30
_MAX_REFRESH_SECONDS: Final = 3600
_DEFAULT_POSITION: Final = WindowPosition(x=100, y=100)


class ThemeName(StrEnum):
    """Supported widget color themes."""

    LIGHT = "light"
    DARK = "dark"


# SHARED STRIP CONTRACT -- keep identical in the Claude widget (widget.pyw).
# Where the taskbar strip lives: which taskbar window hosts it, and which end
# of that taskbar it groups with.
class TaskbarZone(StrEnum):
    """Which end of the host taskbar the strip groups with."""

    LEFT = "left"
    RIGHT = "right"


class TaskbarHost(StrEnum):
    """Which taskbar window hosts the strip."""

    PRIMARY = "primary"
    SECONDARY = "secondary"


_MAX_DEVICE_NAME: Final = 64


@dataclass(frozen=True, slots=True)
class WidgetConfig:
    """Validated persisted settings used by the Tk application."""

    theme: ThemeName = ThemeName.LIGHT
    opacity: float = 0.95
    scale: float = 1.0
    mini_mode: bool = False
    mini_scale: float = 1.0
    smart_topmost: bool = True
    desktop_visible: bool = True
    taskbar_visible: bool = True
    auto_update: bool = True
    pet: str | None = None
    refresh_seconds: int = 180
    position: WindowPosition | None = _DEFAULT_POSITION
    taskbar_zone: TaskbarZone = TaskbarZone.LEFT
    taskbar_host: TaskbarHost = TaskbarHost.PRIMARY
    # ``GetMonitorInfoW`` szDevice of the secondary taskbar's monitor, as in
    # the ``DISPLAY2`` device path. Empty for the primary taskbar.
    taskbar_host_monitor: str = ""

    def __post_init__(self) -> None:
        """Reject invalid direct construction before settings reach the UI."""
        checks = (
            ("theme", type(self.theme) is ThemeName),
            ("opacity", _valid_float(self.opacity, _MIN_OPACITY, 1.0)),
            ("scale", _valid_float(self.scale, _MIN_SCALE, _MAX_SCALE)),
            (
                "mini_scale",
                _valid_float(self.mini_scale, _MIN_MINI_SCALE, _MAX_MINI_SCALE),
            ),
            ("mini_mode", type(self.mini_mode) is bool),
            ("smart_topmost", type(self.smart_topmost) is bool),
            ("desktop_visible", type(self.desktop_visible) is bool),
            ("taskbar_visible", type(self.taskbar_visible) is bool),
            ("auto_update", type(self.auto_update) is bool),
            (
                "pet",
                self.pet is None or (type(self.pet) is str and self.pet in PET_NAMES),
            ),
            (
                "refresh_seconds",
                type(self.refresh_seconds) is int
                and _MIN_REFRESH_SECONDS
                <= self.refresh_seconds
                <= _MAX_REFRESH_SECONDS,
            ),
            ("position", _valid_position(self.position)),
            ("taskbar_zone", type(self.taskbar_zone) is TaskbarZone),
            ("taskbar_host", type(self.taskbar_host) is TaskbarHost),
            (
                "taskbar_host_monitor",
                type(self.taskbar_host_monitor) is str
                and len(self.taskbar_host_monitor) <= _MAX_DEVICE_NAME,
            ),
        )
        invalid = next((field for field, valid in checks if not valid), None)
        if invalid is not None:
            raise ConfigValidationError(field=invalid)


@final
class ConfigValidationError(Exception):
    """Configuration contains a rejected field without retaining its value."""

    def __init__(self, *, field: str) -> None:
        """Identify only the rejected field so sensitive values cannot escape."""
        self.field = field
        super().__init__(f"Invalid widget configuration field: {field}")


@final
class ConfigWriteError(Exception):
    """Atomic configuration persistence failed for the target path."""

    def __init__(self, path: Path) -> None:
        """Capture the failed path without retaining attempted file content."""
        self.path = path
        super().__init__(f"Could not save widget configuration: {path}")


class _PositionData(TypedDict):
    x: int
    y: int


class _ConfigData(TypedDict):
    theme: str
    opacity: float
    scale: float
    mini_mode: bool
    mini_scale: float
    smart_topmost: bool
    desktop_visible: bool
    taskbar_visible: bool
    auto_update: bool
    pet: str | None
    refresh_seconds: int
    position: _PositionData | None
    taskbar_zone: str
    taskbar_host: str
    taskbar_host_monitor: str


@dataclass(frozen=True, slots=True)
class _JsonCodec:
    loads: Callable[[str], ConfigJson]


_JSON_CODEC: Final = _JsonCodec(loads=json.loads)


def load_config(path: Path) -> WidgetConfig:
    """Load known fields while recovering silently from unsafe file data."""
    try:
        decoded = _JSON_CODEC.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return WidgetConfig()
    match decoded:
        case dict() as values:
            return _parse_config(values)
        case _:
            return WidgetConfig()


def select_initial_config(config: WidgetConfig) -> tuple[WidgetConfig, bool]:
    """Canonicalize legacy display flags and assign a pet when unset.

    Configs whose pet is no longer in the pool -- notably the retired
    ``claudecode`` mascot, which loads back as ``None`` -- are treated as unset
    and rerolled to a random remaining pet so the new choice is persisted.
    """
    changed = config.pet not in PET_NAMES or (
        not config.desktop_visible and config.mini_mode
    )
    if not changed:
        return config, False
    # Older releases retained ``mini_mode`` while hidden.  The current UI has
    # one exclusive desktop state, so hidden is persisted as (False, False).
    config = replace(
        config,
        mini_mode=config.mini_mode if config.desktop_visible else False,
    )
    if config.pet in PET_NAMES:
        return config, True
    # Cosmetic mascot pick only -- no security relevance to the randomness.
    return replace(config, pet=random.choice(PET_NAMES)), True  # noqa: S311


def save_config(path: Path, config: WidgetConfig) -> None:
    """Persist safe fields by replacing the destination atomically."""
    temporary_path: Path | None = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            json.dump(_to_data(config), temporary, ensure_ascii=False, indent=2)
            _ = temporary.write("\n")
            _ = temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_path, path)  # noqa: PTH105 -- atomic OS boundary
    except OSError:
        if temporary_path is not None:
            with suppress(OSError):
                temporary_path.unlink(missing_ok=True)
        raise ConfigWriteError(path) from None


def _valid_float(value: float, low: float, high: float) -> bool:
    return type(value) in (int, float) and low <= value <= high


def _valid_position(position: WindowPosition | None) -> bool:
    if position is None:
        return True
    return (
        type(position) is WindowPosition
        and type(position.x) is int
        and type(position.y) is int
    )


def _parse_config(values: Mapping[str, ConfigJson]) -> WidgetConfig:
    defaults = WidgetConfig()
    return WidgetConfig(
        theme=_theme(values.get("theme"), defaults.theme),
        opacity=_bounded_float(
            values.get("opacity"),
            defaults.opacity,
            _MIN_OPACITY,
            1.0,
        ),
        scale=_bounded_float(
            values.get("scale"),
            defaults.scale,
            _MIN_SCALE,
            _MAX_SCALE,
        ),
        mini_mode=_boolean(values.get("mini_mode"), default=defaults.mini_mode),
        mini_scale=_bounded_float(
            values.get("mini_scale"),
            defaults.mini_scale,
            _MIN_MINI_SCALE,
            _MAX_MINI_SCALE,
        ),
        smart_topmost=_boolean(
            values.get("smart_topmost"),
            default=defaults.smart_topmost,
        ),
        desktop_visible=_boolean(
            values.get("desktop_visible"),
            default=defaults.desktop_visible,
        ),
        taskbar_visible=_boolean(
            values.get("taskbar_visible"),
            default=defaults.taskbar_visible,
        ),
        auto_update=_boolean(
            values.get("auto_update"),
            default=defaults.auto_update,
        ),
        pet=_pet(values.get("pet"), defaults.pet),
        refresh_seconds=_bounded_int(
            values.get("refresh_seconds"),
            defaults.refresh_seconds,
            _MIN_REFRESH_SECONDS,
            _MAX_REFRESH_SECONDS,
        ),
        position=_position(values.get("position"), defaults.position),
        taskbar_zone=_zone(values.get("taskbar_zone"), defaults.taskbar_zone),
        taskbar_host=_host(values.get("taskbar_host"), defaults.taskbar_host),
        taskbar_host_monitor=_device_name(
            values.get("taskbar_host_monitor"),
            defaults.taskbar_host_monitor,
        ),
    )


def _zone(value: ConfigJson, default: TaskbarZone) -> TaskbarZone:
    match value:
        case "left":
            return TaskbarZone.LEFT
        case "right":
            return TaskbarZone.RIGHT
        case _:
            return default


def _host(value: ConfigJson, default: TaskbarHost) -> TaskbarHost:
    match value:
        case "primary":
            return TaskbarHost.PRIMARY
        case "secondary":
            return TaskbarHost.SECONDARY
        case _:
            return default


def _device_name(value: ConfigJson, default: str) -> str:
    match value:
        case str() as name if len(name) <= _MAX_DEVICE_NAME:
            return name
        case _:
            return default


def _theme(value: ConfigJson, default: ThemeName) -> ThemeName:
    match value:
        case "light":
            return ThemeName.LIGHT
        case "dark":
            return ThemeName.DARK
        case _:
            return default


def _boolean(value: ConfigJson, *, default: bool) -> bool:
    match value:
        case bool() as flag:
            return flag
        case _:
            return default


def _bounded_float(value: ConfigJson, default: float, low: float, high: float) -> float:
    match value:
        case bool():
            return default
        case int() | float() as number if low <= number <= high:
            return float(number)
        case _:
            return default


def _bounded_int(value: ConfigJson, default: int, low: int, high: int) -> int:
    match value:
        case bool():
            return default
        case int() as number if low <= number <= high:
            return number
        case _:
            return default


def _pet(value: ConfigJson, default: str | None) -> str | None:
    match value:
        case str() as name if name in PET_NAMES:
            return name
        case None:
            return None
        case _:
            return default


def _position(
    value: ConfigJson,
    default: WindowPosition | None,
) -> WindowPosition | None:
    match value:
        case None:
            return None
        case {"x": int() as x, "y": int() as y} if type(x) is int and type(y) is int:
            return WindowPosition(x=x, y=y)
        case _:
            return default


def _to_data(config: WidgetConfig) -> _ConfigData:
    position = config.position
    position_data: _PositionData | None = (
        None if position is None else {"x": position.x, "y": position.y}
    )
    return {
        "theme": config.theme.value,
        "opacity": config.opacity,
        "scale": config.scale,
        "mini_mode": config.mini_mode,
        "mini_scale": config.mini_scale,
        "smart_topmost": config.smart_topmost,
        "desktop_visible": config.desktop_visible,
        "taskbar_visible": config.taskbar_visible,
        "auto_update": config.auto_update,
        "pet": config.pet,
        "refresh_seconds": config.refresh_seconds,
        "position": position_data,
        "taskbar_zone": config.taskbar_zone.value,
        "taskbar_host": config.taskbar_host.value,
        "taskbar_host_monitor": config.taskbar_host_monitor,
    }
