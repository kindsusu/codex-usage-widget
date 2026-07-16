from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from codex_usage_widget.rpc import RpcSuccess, read_rate_limits

if TYPE_CHECKING:
    from codex_usage_widget.parser import JsonValue

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


def _run_strict_fake_server(account_request: JsonValue) -> str:
    messages: tuple[JsonValue, ...] = (
        {"id": 1, "method": "initialize"},
        {"method": "initialized"},
        account_request,
        {"id": 3, "method": "account/rateLimits/read", "params": None},
    )
    completed = subprocess.run(  # noqa: S603 -- trusted test interpreter
        [sys.executable, str(_FIXTURE), "--scenario", "strict_params"],
        input="".join(f"{json.dumps(message)}\n" for message in messages),
        capture_output=True,
        check=True,
        text=True,
    )
    return completed.stdout.splitlines()[-1]


def test_read_rate_limits_removes_exact_nested_sensitive_keys(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # Given
    executable = _configure_fake_server(monkeypatch, tmp_path, "nested_sensitive")

    # When
    result = read_rate_limits(timeout_seconds=2.0)

    # Then
    assert result == RpcSuccess(
        payload={
            "usage": {
                "tokenCount": 321,
                "auth": {
                    "resetCreditCount": 4,
                    "identity": {"windowId": "weekly"},
                },
            },
        },
        executable=executable,
    )
    rendered = repr(result)
    for sensitive_value in (
        "generic-token-value",
        "identity-token-value",
        "api-key-value",
        "authorization-value",
        "secret-value",
        "password-value",
        "access-token-value",
        "refresh-token-value",
        "nested@example.com",
        "account-id-value",
        "user-id-value",
    ):
        assert sensitive_value not in rendered


@pytest.mark.parametrize(
    "account_request",
    [
        {
            "id": 2,
            "method": "account/read",
            "params": {"refreshToken": True},
        },
        {"id": 2, "method": "account/read"},
    ],
    ids=["refresh-enabled", "params-missing"],
)
def test_strict_fake_rejects_invalid_account_read_params(
    account_request: JsonValue,
) -> None:
    # Given
    expected = json.dumps({"id": 3, "error": {"code": -32_600}})

    # When
    response = _run_strict_fake_server(account_request)

    # Then
    assert response == expected
