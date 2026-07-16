"""Read Codex rate limits through a short-lived app-server process."""

from __future__ import annotations

import json
import os
import subprocess
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from io import BufferedReader, BufferedWriter
from queue import Empty, Queue
from typing import TYPE_CHECKING, Final

from codex_usage_widget.discovery import discover_codex_executables
from codex_usage_widget.protocol import RpcStage, request_for

if TYPE_CHECKING:
    from collections.abc import Callable, Generator, Mapping
    from pathlib import Path

    from codex_usage_widget.parser import JsonValue


_SENSITIVE_KEYS: Final = frozenset(
    {
        "token",
        "idtoken",
        "apikey",
        "authorization",
        "secret",
        "password",
        "accesstoken",
        "refreshtoken",
        "email",
        "accountid",
        "userid",
    },
)

__all__ = ["RpcStage"]


@dataclass(frozen=True, slots=True)
class _JsonCodec:
    loads: Callable[[str], JsonValue]


_JSON_CODEC: Final = _JsonCodec(loads=json.loads)


class _ExchangeFailure:
    pass


@dataclass(frozen=True, slots=True)
class RpcSuccess:
    """Sanitized rate-limit result and executable used for the read."""

    payload: JsonValue
    executable: Path


@dataclass(frozen=True, slots=True)
class RpcExecutableNotFound:
    """No usable Codex executable was discovered."""


@dataclass(frozen=True, slots=True)
class RpcLaunchFailure:
    """The discovered executable could not start an app-server."""


@dataclass(frozen=True, slots=True)
class RpcTimeout(_ExchangeFailure):
    """The app-server did not answer within the stage deadline."""

    stage: RpcStage
    timeout_seconds: float


@dataclass(frozen=True, slots=True)
class RpcEndOfStream(_ExchangeFailure):
    """The app-server closed stdout before returning a response."""

    stage: RpcStage


@dataclass(frozen=True, slots=True)
class RpcMalformedResponse(_ExchangeFailure):
    """The app-server emitted a response that was not valid JSON-RPC."""

    stage: RpcStage


@dataclass(frozen=True, slots=True)
class RpcServerError(_ExchangeFailure):
    """The app-server returned a redacted JSON-RPC error."""

    stage: RpcStage
    code: int | None


RpcTransportFailure = RpcTimeout | RpcEndOfStream | RpcMalformedResponse
RpcFailure = (
    RpcExecutableNotFound | RpcLaunchFailure | RpcTransportFailure | RpcServerError
)
RpcResult = RpcSuccess | RpcFailure


@dataclass(frozen=True, slots=True)
class _Response:
    payload: JsonValue


_ExchangeResult = _Response | RpcTransportFailure | RpcServerError
_CandidateResult = RpcSuccess | RpcLaunchFailure | RpcTransportFailure | RpcServerError


@dataclass(frozen=True, slots=True)
class _RunningProcess:
    process: subprocess.Popen[bytes]
    stdin: BufferedWriter
    lines: Queue[bytes | None]
    reader: threading.Thread


def find_codex_executable() -> Path | None:
    """Resolve Codex from the override, PATH, then the desktop install tree."""
    candidates = discover_codex_executables()
    return candidates[0].resolve() if candidates else None


def read_rate_limits(timeout_seconds: float = 20.0) -> RpcResult:
    """Return a sanitized rate-limit payload without exposing account identity."""
    candidates = discover_codex_executables()
    if not candidates:
        return RpcExecutableNotFound()

    for executable in candidates:
        result = _read_candidate(executable, timeout_seconds)
        match result:
            case RpcLaunchFailure():
                continue
            case RpcSuccess() | _ExchangeFailure():
                return result
    return RpcLaunchFailure()


def _read_candidate(executable: Path, timeout_seconds: float) -> _CandidateResult:
    try:
        with _app_server(executable) as running:
            initialized = _exchange(
                running,
                RpcStage.INITIALIZE,
                timeout_seconds,
            )
            match initialized:
                case _Response():
                    pass
                case _ExchangeFailure():
                    return initialized

            account = _exchange(
                running,
                RpcStage.ACCOUNT,
                timeout_seconds,
            )
            match account:
                case _Response():
                    pass
                case _ExchangeFailure():
                    return account

            response = _exchange(
                running,
                RpcStage.RATE_LIMITS,
                timeout_seconds,
            )
            match response:
                case _Response(payload=payload):
                    return RpcSuccess(payload=payload, executable=executable)
                case _ExchangeFailure():
                    return response
    except OSError:
        return RpcLaunchFailure()


@contextmanager
def _app_server(executable: Path) -> Generator[_RunningProcess]:
    process: subprocess.Popen[bytes] = subprocess.Popen(  # noqa: S603 -- trusted local executable
        [str(executable), "app-server", "--stdio"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        shell=False,
        text=False,
        creationflags=0x08000000 if os.name == "nt" else 0,  # CREATE_NO_WINDOW
    )
    match (process.stdin, process.stdout):
        case (BufferedWriter() as stdin, BufferedReader() as stdout):
            lines: Queue[bytes | None] = Queue()
            reader = threading.Thread(
                target=_read_lines,
                args=(stdout, lines),
                daemon=True,
            )
            reader.start()
            running = _RunningProcess(process, stdin, lines, reader)
        case _:
            _ = process.terminate()
            _ = process.wait(timeout=1.0)
            raise BrokenPipeError
    try:
        yield running
    finally:
        _stop_process(process)
        reader.join(timeout=1.0)


def _read_lines(stdout: BufferedReader, lines: Queue[bytes | None]) -> None:
    while line := stdout.readline():
        lines.put(line)
    lines.put(None)


def _stop_process(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is None:
        _ = process.terminate()
    try:
        _ = process.wait(timeout=0.5)
    except subprocess.TimeoutExpired:
        _ = process.kill()
        _ = process.wait(timeout=0.5)


def _exchange(
    running: _RunningProcess,
    stage: RpcStage,
    timeout_seconds: float,
) -> _ExchangeResult:
    request = request_for(stage)
    try:
        for message in request.messages:
            _ = running.stdin.write((json.dumps(message) + "\n").encode())
        running.stdin.flush()
    except OSError:
        return RpcEndOfStream(stage=stage)

    deadline = time.monotonic() + timeout_seconds
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return RpcTimeout(
                stage=stage,
                timeout_seconds=timeout_seconds,
            )
        try:
            line = running.lines.get(timeout=remaining)
        except Empty:
            return RpcTimeout(
                stage=stage,
                timeout_seconds=timeout_seconds,
            )
        if line is None:
            return RpcEndOfStream(stage=stage)
        decoded = _decode_json(line)
        if decoded is None:
            return RpcMalformedResponse(stage=stage)
        match decoded:
            case {"id": response_id} if response_id == request.request_id:
                return _parse_response(decoded, stage)
            case _:
                continue


def _decode_json(line: bytes) -> JsonValue | None:
    try:
        decoded = _JSON_CODEC.loads(line.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    return decoded


def _parse_response(
    response: Mapping[str, JsonValue],
    stage: RpcStage,
) -> _ExchangeResult:
    if "error" in response:
        match response["error"]:
            case {"code": int() as code} if not isinstance(code, bool):
                return RpcServerError(stage=stage, code=code)
            case _:
                return RpcServerError(stage=stage, code=None)
    if "result" not in response:
        return RpcMalformedResponse(stage=stage)
    return _Response(payload=_sanitize(response["result"]))


def _sanitize(value: JsonValue) -> JsonValue:
    match value:
        case dict() as mapping:
            return {
                key: _sanitize(item)
                for key, item in mapping.items()
                if key.replace("_", "").replace("-", "").casefold()
                not in _SENSITIVE_KEYS
            }
        case list() as items:
            return [_sanitize(item) for item in items]
        case None:
            return None
        case str() | int() | float():
            return value
