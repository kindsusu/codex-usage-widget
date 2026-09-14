import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Protocol

import pytest

from codex_usage_widget.assets import PET_NAMES
from codex_usage_widget.config import (
    ConfigValidationError,
    ConfigWriteError,
    ThemeName,
    WidgetConfig,
    load_config,
    select_initial_config,
    save_config,
)
from codex_usage_widget.windows import WindowPosition


class _PetName(str):
    pass


class _RefreshSeconds(int):
    pass


class _SavedPosition(WindowPosition):
    pass


class _ConfigFactory(Protocol):
    def __call__(self) -> WidgetConfig: ...


def test_load_config_returns_reference_defaults_when_file_is_missing(
    tmp_path: Path,
) -> None:
    # Given
    path = tmp_path / "widget_config.json"

    # When
    config = load_config(path)

    # Then
    assert config == WidgetConfig()


def test_select_initial_config_rerolls_a_random_pet_only_when_missing() -> None:
    # Given
    missing = WidgetConfig(pet=None)
    selected = WidgetConfig(pet="image (10)")

    # When
    initialized, missing_changed = select_initial_config(missing)
    unchanged, selected_changed = select_initial_config(selected)

    # Then
    assert initialized.pet in PET_NAMES
    assert initialized.pet != "claudecode"
    assert missing_changed is True
    assert unchanged is selected
    assert selected_changed is False


def test_load_migrates_retired_claudecode_pet_to_a_random_remaining_pet(
    tmp_path: Path,
) -> None:
    # Given a legacy config still pinned to the retired Claude Code mascot
    path = tmp_path / "widget_config.json"
    _ = path.write_text(
        json.dumps({"pet": "claudecode"}),
        encoding="utf-8",
    )

    # When
    loaded = load_config(path)
    migrated, changed = select_initial_config(loaded)

    # Then
    assert loaded.pet is None  # claudecode is no longer a valid pool member
    assert changed is True
    assert migrated.pet in PET_NAMES
    assert migrated.pet != "claudecode"


def test_select_initial_config_canonicalizes_legacy_hidden_mini_state() -> None:
    legacy = WidgetConfig(
        pet="image (10)",
        desktop_visible=False,
        mini_mode=True,
        taskbar_visible=False,
    )

    migrated, changed = select_initial_config(legacy)

    assert changed is True
    assert migrated.desktop_visible is False
    assert migrated.mini_mode is False
    assert migrated.taskbar_visible is False
    assert migrated.pet == legacy.pet


def test_widget_config_rejects_out_of_range_values_without_echoing_them() -> None:
    # Given
    invalid_opacity = 0.1

    # When
    def construct() -> None:
        _ = WidgetConfig(opacity=invalid_opacity)

    # Then
    with pytest.raises(ConfigValidationError) as raised:
        construct()
    assert raised.value.field == "opacity"
    assert str(invalid_opacity) not in str(raised.value)


@pytest.mark.parametrize(
    ("field", "construct"),
    [
        ("opacity", lambda: WidgetConfig(opacity=True)),
        ("opacity", lambda: WidgetConfig(opacity=float("nan"))),
        ("scale", lambda: WidgetConfig(scale=float("inf"))),
        ("scale", lambda: WidgetConfig(scale=int("1" + "0" * 1000))),
        ("mini_scale", lambda: WidgetConfig(mini_scale=float("-inf"))),
        ("pet", lambda: WidgetConfig(pet=_PetName("claudecode"))),
        ("refresh_seconds", lambda: WidgetConfig(refresh_seconds=True)),
        ("refresh_seconds", lambda: WidgetConfig(refresh_seconds=_RefreshSeconds(180))),
        (
            "position",
            lambda: WidgetConfig(position=_SavedPosition(x=100, y=100)),
        ),
        (
            "position",
            lambda: WidgetConfig(position=WindowPosition(x=True, y=100)),
        ),
    ],
)
def test_widget_config_rejects_wrong_runtime_types_and_non_finite_numbers(
    field: str,
    construct: _ConfigFactory,
) -> None:
    # Given / When / Then
    with pytest.raises(ConfigValidationError) as raised:
        _ = construct()
    assert raised.value.field == field
    assert str(raised.value) == f"Invalid widget configuration field: {field}"


@pytest.mark.parametrize(
    ("expression", "field"),
    [
        ('WidgetConfig(theme="dark")', "theme"),
        ("WidgetConfig(mini_mode=1)", "mini_mode"),
        ("WidgetConfig(smart_topmost=1)", "smart_topmost"),
        ("WidgetConfig(desktop_visible=1)", "desktop_visible"),
        ("WidgetConfig(taskbar_visible=1)", "taskbar_visible"),
    ],
)
def test_widget_config_direct_construction_requires_exact_closed_types(
    expression: str,
    field: str,
) -> None:
    # Given
    program = (
        "from codex_usage_widget.config import ConfigValidationError, WidgetConfig\n"
        "try:\n"
        f"    {expression}\n"
        "except ConfigValidationError as error:\n"
        "    print(error.field)\n"
        "else:\n"
        "    raise SystemExit(2)\n"
    )

    # When
    completed = subprocess.run(
        [sys.executable, "-c", program],
        check=False,
        capture_output=True,
        text=True,
    )

    # Then
    assert completed.returncode == 0
    assert completed.stdout.strip() == field
    assert completed.stderr == ""


def test_load_config_merges_valid_fields_and_rejects_wrong_types(
    tmp_path: Path,
) -> None:
    # Given
    path = tmp_path / "widget_config.json"
    _ = path.write_text(
        json.dumps(
            {
                "theme": "dark",
                "opacity": "secret-value-must-not-escape",
                "scale": 1.5,
                "mini_mode": True,
                "smart_topmost": False,
                "desktop_visible": False,
                "taskbar_visible": True,
                "pet": "image (10)",
                "refresh_seconds": 240,
                "position": {"x": -900, "y": 140},
            }
        ),
        encoding="utf-8",
    )

    # When
    config = load_config(path)

    # Then
    assert config.theme is ThemeName.DARK
    assert config.opacity == WidgetConfig().opacity
    assert config.scale == 1.5
    assert config.mini_mode is True
    assert config.smart_topmost is False
    assert config.desktop_visible is False
    assert config.taskbar_visible is True
    assert config.pet == "image (10)"
    assert config.refresh_seconds == 240
    assert config.position == WindowPosition(x=-900, y=140)


@pytest.mark.parametrize("contents", ["{broken", "[]", '"not-an-object"'])
def test_load_config_recovers_from_corrupt_or_non_object_json(
    tmp_path: Path,
    contents: str,
) -> None:
    # Given
    path = tmp_path / "widget_config.json"
    _ = path.write_text(contents, encoding="utf-8")

    # When
    config = load_config(path)

    # Then
    assert config == WidgetConfig()


def test_save_config_uses_atomic_replace_and_only_safe_fields(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given
    path = tmp_path / "widget_config.json"
    config = WidgetConfig(
        theme=ThemeName.DARK,
        opacity=0.8,
        scale=1.3,
        mini_mode=True,
        smart_topmost=False,
        desktop_visible=False,
        taskbar_visible=False,
        pet="image (10)",
        refresh_seconds=300,
        position=WindowPosition(x=10, y=20),
    )
    replaced: list[tuple[Path, Path, bool]] = []
    real_replace = os.replace

    def record_replace(source: str | Path, target: str | Path) -> None:
        source_path = Path(source)
        target_path = Path(target)
        replaced.append((source_path, target_path, source_path.exists()))
        real_replace(source_path, target_path)

    monkeypatch.setattr("codex_usage_widget.config.os.replace", record_replace)

    # When
    save_config(path, config)

    # Then
    assert replaced == [(replaced[0][0], path, True)]
    serialized = path.read_text(encoding="utf-8").casefold()
    assert load_config(path) == config
    assert "token" not in serialized
    assert "email" not in serialized
    assert "account" not in serialized
    assert not replaced[0][0].exists()


@pytest.mark.parametrize(
    ("desktop_visible", "taskbar_visible"),
    [(True, True), (True, False), (False, True), (False, False)],
)
def test_save_and_load_round_trip_every_visibility_combination(
    tmp_path: Path,
    desktop_visible: bool,
    taskbar_visible: bool,
) -> None:
    path = tmp_path / "widget_config.json"
    config = WidgetConfig(
        desktop_visible=desktop_visible,
        taskbar_visible=taskbar_visible,
    )

    save_config(path, config)

    assert load_config(path) == config


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("desktop_visible", "false"),
        ("desktop_visible", 0),
        ("taskbar_visible", "true"),
        ("taskbar_visible", 1),
    ],
)
def test_load_visibility_fields_recover_from_invalid_types(
    tmp_path: Path,
    field: str,
    value: object,
) -> None:
    path = tmp_path / "widget_config.json"
    _ = path.write_text(json.dumps({field: value}), encoding="utf-8")

    config = load_config(path)

    assert config.desktop_visible is True
    assert config.taskbar_visible is True


def test_load_legacy_config_defaults_missing_visibility_fields(tmp_path: Path) -> None:
    path = tmp_path / "widget_config.json"
    _ = path.write_text(
        json.dumps({"mini_mode": True, "position": {"x": -12, "y": 34}}),
        encoding="utf-8",
    )

    config = load_config(path)

    assert config.desktop_visible is True
    assert config.taskbar_visible is True
    assert config.mini_mode is True
    assert config.position == WindowPosition(x=-12, y=34)


def test_save_config_wraps_parent_creation_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given
    path = tmp_path / "missing" / "widget_config.json"

    def fail_mkdir(
        _path: Path,
        mode: int = 0o777,
        parents: bool = False,
        exist_ok: bool = False,
    ) -> None:
        del mode, parents, exist_ok
        raise PermissionError

    monkeypatch.setattr(Path, "mkdir", fail_mkdir)

    # When / Then
    with pytest.raises(ConfigWriteError) as raised:
        save_config(path, WidgetConfig())
    assert raised.value.path == path


def test_save_config_cleanup_failure_never_masks_write_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given
    path = tmp_path / "widget_config.json"

    def fail_replace(_source: str | Path, _target: str | Path) -> None:
        raise PermissionError

    def fail_unlink(_path: Path, *, missing_ok: bool = False) -> None:
        del missing_ok
        raise PermissionError

    monkeypatch.setattr("codex_usage_widget.config.os.replace", fail_replace)
    monkeypatch.setattr(Path, "unlink", fail_unlink)

    # When / Then
    with pytest.raises(ConfigWriteError) as raised:
        save_config(path, WidgetConfig())
    assert raised.value.path == path
