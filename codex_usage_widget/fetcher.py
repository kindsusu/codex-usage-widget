"""Privacy-preserving boundary from app-server outcomes to widget snapshots."""

from datetime import UTC, datetime

from codex_usage_widget.models import UsageSnapshot
from codex_usage_widget.parser import UsagePayloadError, parse_rate_limits
from codex_usage_widget.rpc import (
    RpcEndOfStream,
    RpcExecutableNotFound,
    RpcLaunchFailure,
    RpcMalformedResponse,
    RpcServerError,
    RpcSuccess,
    RpcTimeout,
    read_rate_limits,
)
from codex_usage_widget.service import FailureKind, WorkerFetchError


def fetch_snapshot() -> UsageSnapshot:
    """Fetch one sanitized snapshot or raise a category-only worker error."""
    result = read_rate_limits()
    match result:
        case RpcSuccess(payload=payload):
            try:
                return parse_rate_limits(payload, datetime.now(tz=UTC))
            except UsagePayloadError:
                raise WorkerFetchError(FailureKind.INVALID_RESPONSE) from None
        case RpcServerError():
            raise WorkerFetchError(FailureKind.LOGIN_REQUIRED)
        case RpcMalformedResponse():
            raise WorkerFetchError(FailureKind.INVALID_RESPONSE)
        case (
            RpcExecutableNotFound()
            | RpcLaunchFailure()
            | RpcTimeout()
            | RpcEndOfStream()
        ):
            raise WorkerFetchError(FailureKind.UNAVAILABLE)
