from __future__ import annotations

import shutil
import sys
import venv
from pathlib import Path

import pytest

from codex_usage_widget.discovery import discover_codex_executables
from codex_usage_widget.rpc import (
    RpcEndOfStream,
    RpcExecutableNotFound,
    RpcLaunchFailure,
    RpcMalformedResponse,
    RpcServerError,
    RpcStage,
    RpcSuccess,
    RpcTimeout,
    find_codex_executable,
    read_rate_limits,
)

_FIXTURE = Path(__file__).parent / "fixtures" / "fake_app_server.py"


def _configure_fake_server(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    scenario: str,
) -> Path:
    _ = shutil.copyfile(_FIXTURE, tmp_path / "app-server")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CODEX_EXE", sys.executable)
    monkeypatch.setenv("FAKE_APP_SERVER_SCENARIO", scenario)
    return Path(sys.executable).resolve()


@pytest.fixture(scope="session")
def relocatable_interpreter(
    tmp_path_factory: pytest.TempPathFactory,
) -> tuple[Path, str]:
    """Return a python.exe that still runs after being copied elsewhere.

    Copying ``sys.executable`` is only relocatable when the suite happens to run
    inside a virtual environment, where it is a launcher stub that reads
    ``pyvenv.cfg`` to find its real installation. Run by a plain interpreter --
    a CI runner's, for instance -- the copy finds neither its DLL nor its
    standard library. Building one throwaway venv per session yields that stub
    and its marker file for every caller, whatever runs the suite.
    """
    root = tmp_path_factory.mktemp("relocatable-venv")
    venv.EnvBuilder(with_pip=False).create(root)
    marker = (root / "pyvenv.cfg").read_text(encoding="utf-8")
    return root / "Scripts" / "python.exe", marker


def _configure_automatic_candidates(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    relocatable_interpreter: tuple[Path, str],
) -> tuple[Path, Path]:
    _ = shutil.copyfile(_FIXTURE, tmp_path / "app-server")
    path_directory = tmp_path / "path"
    path_directory.mkdir()
    blocked = path_directory / "codex.exe"
    _ = blocked.write_bytes(b"not a Windows executable")
    installed = (
        tmp_path / "local" / "OpenAI" / "Codex" / "bin" / "version" / "codex.exe"
    )
    installed.parent.mkdir(parents=True)
    interpreter, marker = relocatable_interpreter
    _ = shutil.copyfile(interpreter, installed)
    _ = (installed.parent / "pyvenv.cfg").write_text(marker, encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("CODEX_EXE", raising=False)
    monkeypatch.setenv("PATH", str(path_directory))
    monkeypatch.setenv("PATHEXT", ".EXE")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    monkeypatch.setenv("FAKE_APP_SERVER_SCENARIO", "success")
    return blocked.resolve(), installed.resolve()


def test_read_rate_limits_returns_sanitized_payload_when_notifications_interleave(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # Given
    executable = _configure_fake_server(monkeypatch, tmp_path, "success")

    # When
    result = read_rate_limits(timeout_seconds=2.0)

    # Then
    assert result == RpcSuccess(
        payload={
            "planType": "plus",
            "rateLimits": {
                "limitId": "codex",
                "primary": {
                    "usedPercent": 25,
                    "windowDurationMins": 10_080,
                    "resetsAt": 1_800_000_000,
                },
            },
            "profile": {},
        },
        executable=executable,
    )


@pytest.mark.parametrize(
    ("scenario", "timeout_seconds", "expected"),
    [
        ("eof", 2.0, RpcEndOfStream(stage=RpcStage.INITIALIZE)),
        (
            "timeout",
            0.1,
            RpcTimeout(stage=RpcStage.INITIALIZE, timeout_seconds=0.1),
        ),
        ("malformed", 2.0, RpcMalformedResponse(stage=RpcStage.INITIALIZE)),
    ],
)
def test_read_rate_limits_returns_typed_transport_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    scenario: str,
    timeout_seconds: float,
    expected: RpcEndOfStream | RpcTimeout | RpcMalformedResponse,
) -> None:
    # Given
    _ = _configure_fake_server(monkeypatch, tmp_path, scenario)

    # When
    result = read_rate_limits(timeout_seconds=timeout_seconds)

    # Then
    assert result == expected


def test_read_rate_limits_discards_sensitive_server_error_text(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # Given
    _ = _configure_fake_server(monkeypatch, tmp_path, "server_error")

    # When
    result = read_rate_limits(timeout_seconds=2.0)

    # Then
    assert result == RpcServerError(stage=RpcStage.RATE_LIMITS, code=-32_001)
    assert "private@example.com" not in repr(result)
    assert "secret-token" not in repr(result)
    assert "private-account" not in repr(result)


def test_read_rate_limits_classifies_and_redacts_account_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # Given
    _ = _configure_fake_server(monkeypatch, tmp_path, "account_error")

    # When
    result = read_rate_limits(timeout_seconds=2.0)

    # Then
    assert result == RpcServerError(stage=RpcStage.ACCOUNT, code=-32_002)
    assert "private@example.com" not in repr(result)
    assert "secret-token" not in repr(result)
    assert "private-account" not in repr(result)


def test_read_rate_limits_uses_null_params_for_parameterless_read(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # Given
    executable = _configure_fake_server(monkeypatch, tmp_path, "strict_params")

    # When
    result = read_rate_limits(timeout_seconds=2.0)

    # Then
    assert isinstance(result, RpcSuccess)
    assert result.executable == executable


def test_read_rate_limits_reports_missing_explicit_executable(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # Given
    monkeypatch.setenv("CODEX_EXE", str(tmp_path / "missing-codex.exe"))
    monkeypatch.setenv("PATH", "")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    # When
    result = read_rate_limits()

    # Then
    assert result == RpcExecutableNotFound()


def test_read_rate_limits_falls_back_when_path_candidate_cannot_launch(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    relocatable_interpreter: tuple[Path, str],
) -> None:
    # Given
    _, installed = _configure_automatic_candidates(
        monkeypatch,
        tmp_path,
        relocatable_interpreter,
    )

    # When
    result = read_rate_limits(timeout_seconds=2.0)

    # Then
    assert isinstance(result, RpcSuccess)
    assert result.executable == installed


def test_read_rate_limits_does_not_fallback_from_explicit_executable(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    relocatable_interpreter: tuple[Path, str],
) -> None:
    # Given
    blocked, _ = _configure_automatic_candidates(
        monkeypatch,
        tmp_path,
        relocatable_interpreter,
    )
    monkeypatch.setenv("CODEX_EXE", str(blocked))

    # When
    result = read_rate_limits(timeout_seconds=2.0)

    # Then
    assert result == RpcLaunchFailure()


def test_find_codex_executable_prefers_explicit_environment_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # Given
    explicit = tmp_path / "explicit.exe"
    explicit.touch()
    path_codex = tmp_path / "codex.exe"
    path_codex.touch()
    monkeypatch.setenv("CODEX_EXE", str(explicit))
    monkeypatch.setenv("PATH", str(tmp_path))

    # When
    result = find_codex_executable()

    # Then
    assert result == explicit.resolve()


def test_find_codex_executable_falls_back_to_local_app_install(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # Given
    installed = tmp_path / "OpenAI" / "Codex" / "bin" / "version" / "codex.exe"
    installed.parent.mkdir(parents=True)
    installed.touch()
    monkeypatch.delenv("CODEX_EXE", raising=False)
    monkeypatch.setenv("PATH", "")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    # When
    result = find_codex_executable()

    # Then
    assert result == installed.resolve()


def test_automatic_discovery_deprioritizes_windowsapps_alias(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # Given
    windows_apps = tmp_path / "Microsoft" / "WindowsApps"
    windows_apps.mkdir(parents=True)
    alias = windows_apps / "codex.exe"
    alias.touch()
    installed = tmp_path / "OpenAI" / "Codex" / "bin" / "version" / "codex.exe"
    installed.parent.mkdir(parents=True)
    installed.touch()
    monkeypatch.delenv("CODEX_EXE", raising=False)
    monkeypatch.setenv("PATH", str(windows_apps))
    monkeypatch.setenv("PATHEXT", ".EXE")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    # When
    candidates = discover_codex_executables()

    # Then
    assert candidates == (installed.resolve(), alias.resolve())
