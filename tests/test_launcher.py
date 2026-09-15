import subprocess
from pathlib import Path

import pytest

from codex_usage_widget.launcher import DetachedLaunchError, launch_detached


def _widget_command(_root: Path) -> tuple[str, str]:
    return "pythonw.exe", "widget.pyw"


def _unexpected_popen(*_args: object, **_kwargs: object) -> object:
    pytest.fail("direct fallback should not run")


def _record_wmi(
    calls: list[tuple[tuple[str, ...], Path]],
    command: tuple[str, ...],
    root: Path,
) -> None:
    calls.append((command, root))


def test_launch_detached_prefers_wmi_on_windows(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[tuple[str, str], Path]] = []

    monkeypatch.setattr("codex_usage_widget.launcher.os.name", "nt")
    monkeypatch.setattr(
        "codex_usage_widget.launcher.widget_command",
        _widget_command,
    )
    monkeypatch.setattr(
        "codex_usage_widget.launcher._launch_via_wmi",
        lambda command, root: _record_wmi(calls, command, root),  # pyright: ignore[reportUnknownLambdaType, reportUnknownArgumentType]
    )
    monkeypatch.setattr(
        "codex_usage_widget.launcher.subprocess.Popen",
        _unexpected_popen,
    )

    launch_detached(tmp_path)

    assert calls == [(("pythonw.exe", "widget.pyw"), tmp_path)]


def test_launch_detached_uses_breakaway_fallback_when_wmi_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[object, dict[str, object]]] = []

    def fail_wmi(_command: tuple[str, str], _root: Path) -> None:
        raise subprocess.SubprocessError

    def record_popen(args: object, **kwargs: object) -> object:
        calls.append((args, kwargs))
        return object()

    monkeypatch.setattr("codex_usage_widget.launcher.os.name", "nt")
    monkeypatch.setattr(
        "codex_usage_widget.launcher.widget_command",
        _widget_command,
    )
    monkeypatch.setattr("codex_usage_widget.launcher._launch_via_wmi", fail_wmi)
    monkeypatch.setattr("codex_usage_widget.launcher.subprocess.Popen", record_popen)

    launch_detached(tmp_path)

    assert calls[0][0] == ("pythonw.exe", "widget.pyw")
    assert calls[0][1]["creationflags"] == (
        getattr(subprocess, "CREATE_BREAKAWAY_FROM_JOB", 0x01000000)
        | getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
        | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)
    )


def test_launch_detached_reports_when_both_windows_paths_fail(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(*_args: object, **_kwargs: object) -> None:
        raise OSError

    monkeypatch.setattr("codex_usage_widget.launcher.os.name", "nt")
    monkeypatch.setattr("codex_usage_widget.launcher._launch_via_wmi", fail)
    monkeypatch.setattr("codex_usage_widget.launcher.subprocess.Popen", fail)

    with pytest.raises(DetachedLaunchError):
        launch_detached(tmp_path)
