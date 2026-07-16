from datetime import UTC, datetime

import pytest

from codex_usage_widget.models import CreditStatus, UsageWindow
from codex_usage_widget.parser import JsonValue, UsagePayloadError, parse_rate_limits


FETCHED_AT = datetime(2026, 7, 16, 1, 30, tzinfo=UTC)


def test_parses_weekly_window_when_it_is_the_only_window() -> None:
    # Given
    payload: JsonValue = {
        "rateLimits": {
            "limitId": "codex",
            "primary": {
                "usedPercent": 19,
                "windowDurationMins": 10_080,
                "resetsAt": 1_784_246_400,
            },
            "secondary": None,
        }
    }

    # When
    snapshot = parse_rate_limits(payload, FETCHED_AT)

    # Then
    assert snapshot.windows == (
        UsageWindow(
            limit_id="codex",
            limit_name=None,
            used_percent=19.0,
            window_duration_mins=10_080,
            resets_at=datetime(2026, 7, 17, tzinfo=UTC),
        ),
    )


def test_parses_five_hour_and_weekly_windows_by_duration() -> None:
    # Given
    payload: JsonValue = {
        "rateLimits": {
            "limitId": "codex",
            "primary": {
                "usedPercent": 25,
                "windowDurationMins": 300,
                "resetsAt": 1_784_246_400,
            },
            "secondary": {
                "usedPercent": 18,
                "windowDurationMins": 10_080,
                "resetsAt": 1_784_332_800,
            },
        }
    }

    # When
    snapshot = parse_rate_limits(payload, FETCHED_AT)

    # Then
    assert tuple(window.window_duration_mins for window in snapshot.windows) == (
        300,
        10_080,
    )


def test_prefers_all_additional_limit_ids_over_legacy_rate_limits() -> None:
    # Given
    payload: JsonValue = {
        "rateLimits": {
            "limitId": "legacy",
            "primary": {
                "usedPercent": 99,
                "windowDurationMins": 300,
                "resetsAt": 1_784_246_400,
            },
        },
        "rateLimitsByLimitId": {
            "codex": {
                "limitName": "Codex",
                "primary": {
                    "usedPercent": 10,
                    "windowDurationMins": 300,
                    "resetsAt": 1_784_246_400,
                },
            },
            "codex_other": {
                "limitName": "Other models",
                "secondary": {
                    "usedPercent": 20,
                    "windowDurationMins": 1_440,
                    "resetsAt": 1_784_332_800,
                },
            },
        },
    }

    # When
    snapshot = parse_rate_limits(payload, FETCHED_AT)

    # Then
    assert tuple(
        (window.limit_id, window.limit_name) for window in snapshot.windows
    ) == (
        ("codex", "Codex"),
        ("codex_other", "Other models"),
    )


def test_does_not_invent_rows_for_missing_windows() -> None:
    # Given
    payload: JsonValue = {
        "rateLimitsByLimitId": {
            "codex": {"primary": None, "secondary": None},
            "empty": {},
        }
    }

    # When
    snapshot = parse_rate_limits(payload, FETCHED_AT)

    # Then
    assert snapshot.windows == ()


@pytest.mark.parametrize(
    ("raw_percent", "expected_percent"),
    [(-0.5, 0.0), (100.5, 100.0)],
)
def test_clamps_used_percent_to_displayable_range(
    raw_percent: float,
    expected_percent: float,
) -> None:
    # Given
    payload: JsonValue = {
        "rateLimits": {
            "primary": {
                "usedPercent": raw_percent,
                "windowDurationMins": 300,
                "resetsAt": 1_784_246_400,
            }
        }
    }

    # When
    snapshot = parse_rate_limits(payload, FETCHED_AT)

    # Then
    assert snapshot.windows[0].used_percent == expected_percent


def test_parses_credit_status_without_converting_balance() -> None:
    # Given
    payload: JsonValue = {
        "rateLimits": {
            "credits": {
                "hasCredits": True,
                "unlimited": False,
                "balance": "766.7600000000000000",
            }
        }
    }

    # When
    snapshot = parse_rate_limits(payload, FETCHED_AT)

    # Then
    assert snapshot.credits == CreditStatus(
        has_credits=True,
        unlimited=False,
        balance="766.7600000000000000",
    )


def test_uses_authoritative_reset_credit_count() -> None:
    # Given
    payload: JsonValue = {
        "rateLimits": {},
        "rateLimitResetCredits": {
            "availableCount": 3,
            "credits": [{"id": "only-detail-returned"}],
        },
    }

    # When
    snapshot = parse_rate_limits(payload, FETCHED_AT)

    # Then
    assert snapshot.reset_credit_count == 3


def test_ignores_unknown_fields_at_every_parsed_boundary() -> None:
    # Given
    payload: JsonValue = {
        "futureRoot": {"nested": True},
        "rateLimits": {
            "futureBucket": "ignored",
            "primary": {
                "usedPercent": 12,
                "windowDurationMins": 300,
                "resetsAt": 1_784_246_400,
                "futureWindow": [1, 2, 3],
            },
        },
    }

    # When
    snapshot = parse_rate_limits(payload, FETCHED_AT)

    # Then
    assert snapshot.windows[0].used_percent == 12.0


@pytest.mark.parametrize(
    "payload",
    [
        None,
        {"rateLimits": []},
        {"rateLimits": {"primary": {"windowDurationMins": 300, "resetsAt": 1}}},
        {
            "rateLimits": {
                "primary": {
                    "usedPercent": True,
                    "windowDurationMins": 300,
                    "resetsAt": 1,
                }
            }
        },
        {
            "rateLimits": {
                "primary": {
                    "usedPercent": 10,
                    "windowDurationMins": 0,
                    "resetsAt": 1,
                }
            }
        },
        {"rateLimits": {"credits": {"hasCredits": True, "unlimited": "no"}}},
        {"rateLimits": {}, "rateLimitResetCredits": {"availableCount": -1}},
    ],
)
def test_rejects_malformed_required_fields(payload: JsonValue) -> None:
    # Given
    malformed_payload = payload

    # When
    def parse() -> None:
        _ = parse_rate_limits(malformed_payload, FETCHED_AT)

    # Then
    with pytest.raises(UsagePayloadError):
        parse()


def test_preserves_fetch_time_on_snapshot() -> None:
    # Given
    payload: JsonValue = {"rateLimits": {}}

    # When
    snapshot = parse_rate_limits(payload, FETCHED_AT)

    # Then
    assert snapshot.fetched_at is FETCHED_AT


@pytest.mark.parametrize(
    ("raw_plan", "expected_plan"),
    [
        ("plus", "plus"),
        (" PLUS ", "plus"),
        ("pro", "pro"),
        ("Professional", "pro"),
        ("team", "team"),
        ("business", "business"),
        ("enterprise", "enterprise"),
        ("free", "free"),
        ("unknown", "unknown"),
    ],
)
def test_parses_only_normalized_safe_top_level_plan_types(
    raw_plan: str,
    expected_plan: str,
) -> None:
    # Given
    payload: JsonValue = {"planType": raw_plan, "rateLimits": {}}

    # When
    snapshot = parse_rate_limits(payload, FETCHED_AT)

    # Then
    assert snapshot.plan_type == expected_plan


@pytest.mark.parametrize(
    "payload",
    [
        {"rateLimits": {}},
        {"planType": "person@example.com", "rateLimits": {}},
        {"planType": "plus-owner-12345", "rateLimits": {}},
        {"planType": 7, "rateLimits": {}},
        {
            "planType": "person@example.com",
            "rateLimits": {"planType": "account-123"},
            "rateLimitsByLimitId": {
                "codex": {"planType": "private-team-name"},
            },
        },
    ],
)
def test_does_not_retain_missing_unknown_or_identity_plan_values(
    payload: JsonValue,
) -> None:
    # Given
    untrusted_payload = payload

    # When
    snapshot = parse_rate_limits(untrusted_payload, FETCHED_AT)

    # Then
    assert snapshot.plan_type is None


def test_parses_real_legacy_nested_plan_type_when_root_plan_is_missing() -> None:
    # Given
    payload: JsonValue = {"planType": None, "rateLimits": {"planType": "plus"}}

    # When
    snapshot = parse_rate_limits(payload, FETCHED_AT)

    # Then
    assert snapshot.plan_type == "plus"


def test_plan_type_precedence_prefers_root_then_legacy_then_first_safe_bucket() -> None:
    # Given
    payloads: tuple[JsonValue, ...] = (
        {
            "planType": "pro",
            "rateLimits": {"planType": "plus"},
            "rateLimitsByLimitId": {"codex": {"planType": "enterprise"}},
        },
        {
            "planType": "person@example.com",
            "rateLimits": {"planType": "business"},
            "rateLimitsByLimitId": {"codex": {"planType": "enterprise"}},
        },
        {
            "rateLimits": {"planType": "account-123"},
            "rateLimitsByLimitId": {
                "first": {"planType": "private-team-name"},
                "second": {"planType": "team"},
                "third": {"planType": "pro"},
            },
        },
    )

    # When
    plan_types = tuple(
        parse_rate_limits(payload, FETCHED_AT).plan_type for payload in payloads
    )

    # Then
    assert plan_types == ("pro", "business", "team")
