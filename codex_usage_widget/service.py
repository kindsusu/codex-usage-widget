"""Keep refresh work off Tk while exposing immutable UI state."""

from collections.abc import Mapping
from dataclasses import dataclass, replace
from enum import StrEnum
from queue import Empty, Queue
from threading import Thread
from types import MappingProxyType
from typing import Final, Protocol, final

from codex_usage_widget.models import UsageSnapshot


class RefreshStatus(StrEnum):
    """User-visible freshness phase of the current snapshot."""

    LOADING = "loading"
    FRESH = "fresh"
    REFRESHING = "refreshing"
    STALE = "stale"
    ERROR = "error"
    SHUTDOWN = "shutdown"


class FailureKind(StrEnum):
    """Sanitized worker failures safe to display or log."""

    LOGIN_REQUIRED = "login_required"
    UNAVAILABLE = "unavailable"
    INVALID_RESPONSE = "invalid_response"


@final
class WorkerFetchError(Exception):
    """Typed worker-boundary failure that cannot retain raw payload data."""

    __slots__ = ("kind",)

    kind: FailureKind

    def __init__(self, kind: FailureKind) -> None:
        """Create an error from a finite privacy-safe category."""
        self.kind = kind
        super().__init__(failure_message(kind))


@dataclass(frozen=True, slots=True)
class WidgetState:
    """Immutable current snapshot and refresh lifecycle state."""

    snapshot: UsageSnapshot | None
    status: RefreshStatus
    refresh_in_flight: bool
    failure: FailureKind | None

    @classmethod
    def initial(cls) -> "WidgetState":
        """Create the loading state shown before the first refresh."""
        return cls(
            snapshot=None,
            status=RefreshStatus.LOADING,
            refresh_in_flight=False,
            failure=None,
        )


@dataclass(frozen=True, slots=True)
class _RefreshSuccess:
    snapshot: UsageSnapshot

    def complete(self, state: WidgetState) -> WidgetState:
        _ = state
        return WidgetState(
            snapshot=self.snapshot,
            status=RefreshStatus.FRESH,
            refresh_in_flight=False,
            failure=None,
        )


@dataclass(frozen=True, slots=True)
class _RefreshFailure:
    kind: FailureKind

    def complete(self, state: WidgetState) -> WidgetState:
        return WidgetState(
            snapshot=state.snapshot,
            status=(
                RefreshStatus.ERROR if state.snapshot is None else RefreshStatus.STALE
            ),
            refresh_in_flight=False,
            failure=self.kind,
        )


class _RefreshOutcome(Protocol):
    def complete(self, state: WidgetState) -> WidgetState: ...


class _SnapshotFetcher(Protocol):
    def __call__(self) -> UsageSnapshot: ...


@final
class RefreshService:
    """Coalesce refresh requests and deliver typed results through a queue."""

    __slots__ = ("_fetch", "_results", "_state")

    def __init__(self, fetch: _SnapshotFetcher) -> None:
        """Bind a fetch operation without starting background work."""
        self._fetch = fetch
        self._results: Queue[_RefreshOutcome] = Queue()
        self._state = WidgetState.initial()

    @property
    def state(self) -> WidgetState:
        """Return the latest immutable state."""
        return self._state

    def request_refresh(self) -> bool:
        """Start one worker or report that the request was coalesced."""
        if self._state.status is RefreshStatus.SHUTDOWN:
            return False
        if self._state.refresh_in_flight:
            return False
        status = (
            RefreshStatus.LOADING
            if self._state.snapshot is None
            else RefreshStatus.REFRESHING
        )
        self._state = replace(
            self._state,
            status=status,
            refresh_in_flight=True,
            failure=None,
        )
        Thread(target=self._run_worker, daemon=True).start()
        return True

    def poll(self, timeout_seconds: float = 0.0) -> WidgetState | None:
        """Apply one queued result and return a changed state when available."""
        try:
            outcome = (
                self._results.get_nowait()
                if timeout_seconds <= 0.0
                else self._results.get(timeout=timeout_seconds)
            )
        except Empty:
            return None
        previous = self._state
        self._state = _complete(previous, outcome)
        return None if self._state is previous else self._state

    def shutdown(self) -> None:
        """Stop accepting refreshes and suppress results from late workers."""
        self._state = replace(
            self._state,
            status=RefreshStatus.SHUTDOWN,
            refresh_in_flight=False,
            failure=None,
        )

    def _run_worker(self) -> None:
        try:
            outcome: _RefreshOutcome = _RefreshSuccess(self._fetch())
        except WorkerFetchError as error:
            outcome = _RefreshFailure(error.kind)
        except Exception:  # noqa: BLE001  # noqa: BROAD_EXCEPT_OK
            outcome = _RefreshFailure(FailureKind.UNAVAILABLE)
        self._results.put(outcome)


def failure_message(kind: FailureKind) -> str:
    """Return a static Korean action message without raw exception details."""
    return _FAILURE_MESSAGES[kind]


def _complete(state: WidgetState, outcome: _RefreshOutcome) -> WidgetState:
    if state.status is RefreshStatus.SHUTDOWN:
        return state
    return outcome.complete(state)


_FAILURE_MESSAGES: Final[Mapping[FailureKind, str]] = MappingProxyType(
    {
        FailureKind.LOGIN_REQUIRED: "Codex에 로그인한 뒤 다시 시도하세요.",
        FailureKind.UNAVAILABLE: "Codex 사용량을 불러올 수 없습니다.",
        FailureKind.INVALID_RESPONSE: "Codex 사용량 응답을 확인할 수 없습니다.",
    },
)
