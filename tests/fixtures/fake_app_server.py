from __future__ import annotations

import json
import os
import re
import sys
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

JsonValue = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]

_WEEK_MINUTES: Final = 10_080


@dataclass(frozen=True, slots=True)
class _JsonCodec:
    loads: Callable[[str], JsonValue]


_JSON_CODEC: Final = _JsonCodec(loads=json.loads)


def _write(payload: JsonValue) -> None:
    _ = os.write(1, (json.dumps(payload) + "\n").encode())


def _success_result() -> JsonValue:
    return {
        "planType": "plus",
        "rateLimits": {
            "limitId": "codex",
            "primary": {
                "usedPercent": 25,
                "windowDurationMins": _WEEK_MINUTES,
                "resetsAt": 1_800_000_000,
            },
        },
        "access_token": "secret-token",
        "profile": {"email": "private@example.com"},
        "accountId": "private-account",
    }


def _nested_sensitive_result() -> JsonValue:
    return {
        "usage": {
            "token": "generic-token-value",
            "idToken": "identity-token-value",
            "tokenCount": 321,
            "auth": {
                "api_key": "api-key-value",
                "authorization": "authorization-value",
                "secret": "secret-value",
                "password": "password-value",
                "resetCreditCount": 4,
                "identity": {
                    "access_token": "access-token-value",
                    "refresh-token": "refresh-token-value",
                    "email": "nested@example.com",
                    "account-id": "account-id-value",
                    "user_id": "user-id-value",
                    "windowId": "weekly",
                },
            },
        },
    }


def _result_for_scenario(scenario: str) -> JsonValue:
    return (
        _nested_sensitive_result()
        if scenario == "nested_sensitive"
        else _success_result()
    )


def _scenario_from_args(args: Sequence[str]) -> str:
    for index, argument in enumerate(args):
        if argument == "--scenario" and index + 1 < len(args):
            return args[index + 1]
    return os.environ.get("FAKE_APP_SERVER_SCENARIO", "success")


def _request_parts(line: str) -> tuple[int, str]:
    request_id_match = re.search(r'"id"\s*:\s*(\d+)', line)
    method_match = re.search(r'"method"\s*:\s*"([^"]+)"', line)
    if method_match is None:
        return 0, "malformed"
    request_id = int(request_id_match.group(1)) if request_id_match else 0
    return request_id, method_match.group(1)


def _has_strict_account_params(line: str) -> bool:
    try:
        request = _JSON_CODEC.loads(line)
    except json.JSONDecodeError:
        return False
    match request:
        case {"params": dict() as params}:
            return params == {"refreshToken": False}
        case _:
            return False


def _handle_account_read(
    request_id: int,
    scenario: str,
    *,
    client_initialized: bool,
) -> bool:
    if scenario == "account_error":
        _write(
            {
                "id": request_id,
                "error": {
                    "code": -32_002,
                    "message": "private@example.com secret-token private-account",
                },
            },
        )
        return False
    _write({"id": request_id, "result": {"type": "chatgpt"}})
    return client_initialized


def main() -> int:
    scenario = _scenario_from_args(tuple(sys.argv[1:]))
    client_initialized = False
    account_loaded = False
    for line in sys.stdin:
        request_id, method = _request_parts(line)

        if method == "initialized":
            client_initialized = True
            continue

        if scenario == "timeout":
            time.sleep(10)
            continue
        if scenario == "malformed":
            _ = os.write(1, b"{not-json\n")
            continue
        if scenario == "eof":
            return 0

        _write({"method": "account/updated", "params": {"kind": "notification"}})
        if method == "initialize":
            _write({"id": request_id, "result": {"server": "fake"}})
            continue
        if method == "account/read":
            account_ready = client_initialized and (
                scenario != "strict_params" or _has_strict_account_params(line)
            )
            account_loaded = _handle_account_read(
                request_id,
                scenario,
                client_initialized=account_ready,
            )
            continue
        if scenario == "server_error":
            _write(
                {
                    "id": request_id,
                    "error": {
                        "code": -32_001,
                        "message": "private@example.com secret-token private-account",
                    },
                },
            )
            continue
        if (
            scenario == "strict_params"
            and method == "account/rateLimits/read"
            and (
                not client_initialized
                or not account_loaded
                or re.search(r'"params"\s*:\s*null', line) is None
            )
        ):
            _write({"id": request_id, "error": {"code": -32_600}})
            continue
        _write({"id": request_id, "result": _result_for_scenario(scenario)})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
