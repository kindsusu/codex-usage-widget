from datetime import UTC, datetime
from threading import Event

from codex_usage_widget.models import UsageSnapshot
from codex_usage_widget.service import (
    FailureKind,
    RefreshService,
    RefreshStatus,
    WorkerFetchError,
)

NOW = datetime(2026, 7, 16, 12, 0, tzinfo=UTC)
SNAPSHOT = UsageSnapshot(
    windows=(),
    credits=None,
    reset_credit_count=None,
    fetched_at=NOW,
)


def test_service_starts_in_loading_state() -> None:
    # Given / When
    service = RefreshService(lambda: SNAPSHOT)

    # Then
    assert service.state.status is RefreshStatus.LOADING
    assert service.state.snapshot is None
    assert service.state.refresh_in_flight is False


def test_success_replaces_loading_with_a_fresh_snapshot() -> None:
    # Given
    service = RefreshService(lambda: SNAPSHOT)

    # When
    started = service.request_refresh()
    changed = service.poll(timeout_seconds=1.0)

    # Then
    assert started is True
    assert changed is not None
    assert service.state.status is RefreshStatus.FRESH
    assert service.state.snapshot is SNAPSHOT
    assert service.state.failure is None


def test_failure_after_success_retains_snapshot_as_stale() -> None:
    # Given
    fetch_count = 0

    def fetch() -> UsageSnapshot:
        nonlocal fetch_count
        fetch_count += 1
        if fetch_count == 1:
            return SNAPSHOT
        raise WorkerFetchError(FailureKind.UNAVAILABLE)

    service = RefreshService(fetch)
    assert service.request_refresh() is True
    assert service.poll(timeout_seconds=1.0) is not None

    # When
    assert service.request_refresh() is True
    assert service.poll(timeout_seconds=1.0) is not None

    # Then
    assert service.state.status is RefreshStatus.STALE
    assert service.state.snapshot is SNAPSHOT
    assert service.state.failure is FailureKind.UNAVAILABLE


def test_failure_without_snapshot_is_an_error() -> None:
    # Given
    def fail() -> UsageSnapshot:
        raise WorkerFetchError(FailureKind.LOGIN_REQUIRED)

    service = RefreshService(fail)

    # When
    assert service.request_refresh() is True
    assert service.poll(timeout_seconds=1.0) is not None

    # Then
    assert service.state.status is RefreshStatus.ERROR
    assert service.state.snapshot is None
    assert service.state.failure is FailureKind.LOGIN_REQUIRED


def test_unexpected_worker_exception_becomes_static_unavailable_failure() -> None:
    # Given
    def fail_unexpectedly() -> UsageSnapshot:
        raise RuntimeError

    service = RefreshService(fail_unexpectedly)

    # When
    assert service.request_refresh() is True
    changed = service.poll(timeout_seconds=1.0)

    # Then
    assert changed is not None
    assert service.state.status is RefreshStatus.ERROR
    assert service.state.failure is FailureKind.UNAVAILABLE
    assert service.state.refresh_in_flight is False


def test_overlapping_refreshes_are_coalesced() -> None:
    # Given
    started = Event()
    release = Event()

    def fetch() -> UsageSnapshot:
        started.set()
        assert release.wait(timeout=1.0)
        return SNAPSHOT

    service = RefreshService(fetch)
    first = service.request_refresh()
    assert started.wait(timeout=1.0)

    # When
    second = service.request_refresh()
    release.set()
    assert service.poll(timeout_seconds=1.0) is not None

    # Then
    assert first is True
    assert second is False
    assert service.state.status is RefreshStatus.FRESH


def test_shutdown_ignores_a_late_worker_result() -> None:
    # Given
    started = Event()
    release = Event()

    def fetch() -> UsageSnapshot:
        started.set()
        assert release.wait(timeout=1.0)
        return SNAPSHOT

    service = RefreshService(fetch)
    assert service.request_refresh() is True
    assert started.wait(timeout=1.0)

    # When
    service.shutdown()
    release.set()
    changed = service.poll(timeout_seconds=1.0)

    # Then
    assert changed is None
    assert service.state.status is RefreshStatus.SHUTDOWN
    assert service.state.snapshot is None


def test_worker_failure_message_is_static_and_privacy_safe() -> None:
    # Given / When
    failure = WorkerFetchError(FailureKind.UNAVAILABLE)

    # Then
    assert str(failure) == "Codex 사용량을 불러올 수 없습니다."
    assert not hasattr(failure, "payload")
