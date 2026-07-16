from datetime import UTC, datetime

import pytest

from codex_usage_widget.parser import JsonValue, UsagePayloadError, parse_rate_limits


FETCHED_AT = datetime(2026, 7, 16, 1, 30, tzinfo=UTC)


def test_classifies_secondary_five_hour_window_by_duration() -> None:
    # Given
    payload: JsonValue = {
        "rateLimits": {
            "primary": {
                "usedPercent": 18,
                "windowDurationMins": 10_080,
                "resetsAt": 1_784_332_800,
            },
            "secondary": {
                "usedPercent": 25,
                "windowDurationMins": 300,
                "resetsAt": 1_784_246_400,
            },
        }
    }

    # When
    snapshot = parse_rate_limits(payload, FETCHED_AT)

    # Then
    assert tuple(window.window_duration_mins for window in snapshot.windows) == (
        10_080,
        300,
    )


def test_excludes_sensitive_unknown_fields_from_snapshot_representation() -> None:
    # Given
    payload: JsonValue = {
        "access_token": "secret-access-token",
        "email": "private@example.com",
        "account_id": "private-account-id",
        "rateLimits": {},
    }

    # When
    snapshot_text = repr(parse_rate_limits(payload, FETCHED_AT))

    # Then
    assert all(
        marker not in snapshot_text
        for marker in (
            "access_token",
            "secret-access-token",
            "email",
            "private@example.com",
            "account_id",
            "private-account-id",
        )
    )


def test_excludes_sensitive_fields_and_values_from_typed_error_text() -> None:
    # Given
    payload: JsonValue = {
        "access_token": "secret-access-token",
        "email": "private@example.com",
        "account_id": "private-account-id",
        "rateLimits": {
            "primary": {
                "usedPercent": "secret-access-token",
                "windowDurationMins": 300,
                "resetsAt": 1_784_246_400,
            }
        },
    }

    # When
    with pytest.raises(UsagePayloadError) as error_info:
        _ = parse_rate_limits(payload, FETCHED_AT)

    # Then
    error_text = str(error_info.value)
    assert all(
        marker not in error_text
        for marker in (
            "access_token",
            "secret-access-token",
            "email",
            "private@example.com",
            "account_id",
            "private-account-id",
        )
    )


def test_rejects_oversized_json_integer_with_typed_error() -> None:
    # Given
    payload: JsonValue = {
        "rateLimits": {
            "primary": {
                "usedPercent": 10**10_000,
                "windowDurationMins": 300,
                "resetsAt": 1_784_246_400,
            }
        }
    }

    # When
    def parse() -> None:
        _ = parse_rate_limits(payload, FETCHED_AT)

    # Then
    with pytest.raises(UsagePayloadError):
        parse()
