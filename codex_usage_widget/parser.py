"""Parse untrusted Codex app-server rate-limit payloads."""

from collections.abc import Mapping
from datetime import UTC, datetime
from math import isfinite
from typing import Final, TypeAlias, final

from codex_usage_widget.models import CreditStatus, UsageSnapshot, UsageWindow

JsonValue: TypeAlias = (
    str | int | float | bool | list["JsonValue"] | dict[str, "JsonValue"] | None
)
JsonPath: TypeAlias = tuple[str | int, ...]
JsonObject: TypeAlias = Mapping[str, JsonValue]
_SAFE_PLAN_TYPES: Final = frozenset(
    {"plus", "pro", "team", "business", "enterprise", "free", "unknown"}
)
_PLAN_TYPE_MAX_LENGTH: Final = 16


@final
class UsagePayloadError(Exception):
    """A typed description of malformed data at the app-server boundary."""

    __slots__ = ("actual", "expected", "path")

    path: JsonPath
    expected: str
    actual: str

    def __init__(self, *, path: JsonPath, expected: str, actual: str) -> None:
        self.path = path
        self.expected = expected
        self.actual = actual
        location = "$" + "".join(
            f"[{part}]" if isinstance(part, int) else f".{part}" for part in self.path
        )
        super().__init__(f"{location}: expected {self.expected}, got {self.actual}")


def parse_rate_limits(payload: JsonValue, fetched_at: datetime) -> UsageSnapshot:
    """Parse an ``account/rateLimits/read`` result into an immutable snapshot."""
    root = _expect_object(payload, ())
    buckets = _select_buckets(root)
    windows = tuple(
        window
        for limit_id, bucket, path in buckets
        for window in _parse_bucket_windows(limit_id, bucket, path)
    )
    credits = _parse_credits(buckets)
    reset_credit_count = _parse_reset_credit_count(root)
    plan_type = _parse_plan_type(root, buckets)
    return UsageSnapshot(
        windows=windows,
        credits=credits,
        reset_credit_count=reset_credit_count,
        fetched_at=fetched_at,
        plan_type=plan_type,
    )


def _select_buckets(
    root: JsonObject,
) -> tuple[tuple[str, JsonObject, JsonPath], ...]:
    by_id_value = root.get("rateLimitsByLimitId")
    if by_id_value is not None:
        by_id = _expect_object(by_id_value, ("rateLimitsByLimitId",))
        return tuple(
            (
                limit_id,
                _expect_object(bucket, ("rateLimitsByLimitId", limit_id)),
                ("rateLimitsByLimitId", limit_id),
            )
            for limit_id, bucket in by_id.items()
        )

    if "rateLimits" not in root:
        raise _error((), "rateLimits or rateLimitsByLimitId", dict(root))
    path = ("rateLimits",)
    bucket = _expect_object(root["rateLimits"], path)
    return ((_parse_legacy_limit_id(bucket, path), bucket, path),)


def _parse_legacy_limit_id(bucket: JsonObject, path: JsonPath) -> str:
    value = bucket.get("limitId")
    if value is None:
        return "codex"
    return _expect_string(value, (*path, "limitId"))


def _parse_bucket_windows(
    limit_id: str,
    bucket: JsonObject,
    path: JsonPath,
) -> tuple[UsageWindow, ...]:
    limit_name = _optional_string(bucket.get("limitName"), (*path, "limitName"))
    windows: list[UsageWindow] = []
    for window_key in ("primary", "secondary"):
        value = bucket.get(window_key)
        if value is not None:
            windows.append(
                _parse_window(
                    value,
                    limit_id,
                    limit_name,
                    (*path, window_key),
                )
            )
    return tuple(windows)


def _parse_window(
    value: JsonValue,
    limit_id: str,
    limit_name: str | None,
    path: JsonPath,
) -> UsageWindow:
    window = _expect_object(value, path)
    used_percent = _expect_number(window.get("usedPercent"), (*path, "usedPercent"))
    duration = _expect_positive_int(
        window.get("windowDurationMins"),
        (*path, "windowDurationMins"),
    )
    resets_at = _expect_timestamp(window.get("resetsAt"), (*path, "resetsAt"))
    return UsageWindow(
        limit_id=limit_id,
        limit_name=limit_name,
        used_percent=min(100.0, max(0.0, used_percent)),
        window_duration_mins=duration,
        resets_at=resets_at,
    )


def _parse_credits(
    buckets: tuple[tuple[str, JsonObject, JsonPath], ...],
) -> CreditStatus | None:
    for _, bucket, path in buckets:
        value = bucket.get("credits")
        if value is not None:
            credits = _expect_object(value, (*path, "credits"))
            return CreditStatus(
                has_credits=_expect_bool(
                    credits.get("hasCredits"),
                    (*path, "credits", "hasCredits"),
                ),
                unlimited=_expect_bool(
                    credits.get("unlimited"),
                    (*path, "credits", "unlimited"),
                ),
                balance=_optional_string(
                    credits.get("balance"),
                    (*path, "credits", "balance"),
                ),
            )
    return None


def _parse_reset_credit_count(root: JsonObject) -> int | None:
    value = root.get("rateLimitResetCredits")
    if value is None:
        return None
    path = ("rateLimitResetCredits",)
    reset_credits = _expect_object(value, path)
    count = _expect_nonnegative_int(
        reset_credits.get("availableCount"),
        (*path, "availableCount"),
    )
    return count


def _parse_plan_type(
    root: JsonObject,
    buckets: tuple[tuple[str, JsonObject, JsonPath], ...],
) -> str | None:
    candidates: list[JsonValue] = [root.get("planType")]
    match root.get("rateLimits"):
        case dict() as legacy:
            candidates.append(legacy.get("planType"))
        case _:
            pass
    candidates.extend(bucket.get("planType") for _, bucket, _ in buckets)
    for value in candidates:
        match value:
            case str() as text:
                normalized = text.strip().casefold()
            case _:
                continue
        if len(normalized) > _PLAN_TYPE_MAX_LENGTH:
            continue
        if normalized == "professional":
            return "pro"
        if normalized in _SAFE_PLAN_TYPES:
            return normalized
    return None


def _expect_object(value: JsonValue, path: JsonPath) -> JsonObject:
    match value:
        case dict() as mapping:
            return mapping
        case _:
            raise _error(path, "JSON object", value)


def _expect_string(value: JsonValue, path: JsonPath) -> str:
    match value:
        case str() as text:
            return text
        case _:
            raise _error(path, "string", value)


def _optional_string(value: JsonValue, path: JsonPath) -> str | None:
    if value is None:
        return None
    return _expect_string(value, path)


def _expect_bool(value: JsonValue, path: JsonPath) -> bool:
    match value:
        case bool() as flag:
            return flag
        case _:
            raise _error(path, "boolean", value)


def _expect_number(value: JsonValue, path: JsonPath) -> float:
    match value:
        case bool():
            raise _error(path, "finite number", value)
        case int() | float():
            try:
                number = float(value)
            except OverflowError:
                raise _error(path, "finite number", value) from None
            if isfinite(number):
                return number
            raise _error(path, "finite number", value)
        case _:
            raise _error(path, "finite number", value)


def _expect_positive_int(value: JsonValue, path: JsonPath) -> int:
    result = _expect_nonnegative_int(value, path)
    if result == 0:
        raise _error(path, "positive integer", value)
    return result


def _expect_nonnegative_int(value: JsonValue, path: JsonPath) -> int:
    match value:
        case bool():
            raise _error(path, "nonnegative integer", value)
        case int() as integer if integer >= 0:
            return integer
        case _:
            raise _error(path, "nonnegative integer", value)


def _expect_timestamp(value: JsonValue, path: JsonPath) -> datetime:
    timestamp = _expect_nonnegative_int(value, path)
    try:
        return datetime.fromtimestamp(timestamp, tz=UTC)
    except (OSError, OverflowError, ValueError):
        raise _error(path, "valid Unix timestamp", value) from None


def _error(path: JsonPath, expected: str, value: JsonValue) -> UsagePayloadError:
    return UsagePayloadError(path=path, expected=expected, actual=type(value).__name__)
