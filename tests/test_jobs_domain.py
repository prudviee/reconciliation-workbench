from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from reconciliation.domain import (
    ClaimSnapshot,
    DomainValidationError,
    FailureCategory,
    JobState,
    LeaseToken,
    RetryPolicy,
    is_claimable,
)


def test_lease_token_rejects_empty_value() -> None:
    with pytest.raises(DomainValidationError):
        LeaseToken("")

    assert str(LeaseToken("abc123")) == "abc123"


def test_claim_snapshot_shape_matches_state() -> None:
    now = datetime(2026, 9, 8, tzinfo=UTC)

    with pytest.raises(DomainValidationError, match="LEASED"):
        ClaimSnapshot(state=JobState.LEASED, available_at=now, lease_until=None)

    with pytest.raises(DomainValidationError, match="LEASED"):
        ClaimSnapshot(state=JobState.READY, available_at=now, lease_until=now)


@pytest.mark.parametrize(
    "state,offset,expected",
    [
        (JobState.READY, timedelta(microseconds=-1), False),
        (JobState.READY, timedelta(0), True),
        (JobState.READY, timedelta(microseconds=1), True),
        (JobState.LEASED, timedelta(microseconds=-1), False),
        (JobState.LEASED, timedelta(0), False),
        (JobState.LEASED, timedelta(microseconds=1), True),
    ],
)
def test_is_claimable_matches_the_sql_where_clause_boundary(
    state: JobState, offset: timedelta, expected: bool
) -> None:
    reference = datetime(2026, 9, 8, 12, 0, tzinfo=UTC)
    if state is JobState.READY:
        snapshot = ClaimSnapshot(state=state, available_at=reference)
    else:
        snapshot = ClaimSnapshot(
            state=state, available_at=reference, lease_until=reference
        )

    assert is_claimable(snapshot, now=reference + offset) is expected


@pytest.mark.parametrize("state", [JobState.SUCCEEDED, JobState.FAILED])
def test_terminal_states_are_never_claimable(state: JobState) -> None:
    reference = datetime(2026, 9, 8, tzinfo=UTC)
    snapshot = ClaimSnapshot(state=state, available_at=reference)

    assert is_claimable(snapshot, now=reference + timedelta(days=365)) is False


def test_permanent_failure_terminates_on_first_attempt() -> None:
    policy = RetryPolicy(max_attempts=3, backoff=timedelta(seconds=5))
    now = datetime(2026, 9, 8, tzinfo=UTC)

    outcome = policy.decide(
        attempt_count=1, failure_category=FailureCategory.PERMANENT, now=now
    )

    assert outcome.state is JobState.FAILED
    assert outcome.available_at is None


def test_transient_failure_retries_with_exponential_backoff_until_the_limit() -> None:
    policy = RetryPolicy(max_attempts=3, backoff=timedelta(seconds=5))
    now = datetime(2026, 9, 8, tzinfo=UTC)

    first = policy.decide(
        attempt_count=1, failure_category=FailureCategory.TRANSIENT, now=now
    )
    second = policy.decide(
        attempt_count=2, failure_category=FailureCategory.TRANSIENT, now=now
    )
    third = policy.decide(
        attempt_count=3, failure_category=FailureCategory.TRANSIENT, now=now
    )

    assert first.state is JobState.READY
    assert first.available_at == now + timedelta(seconds=5)
    assert second.state is JobState.READY
    assert second.available_at == now + timedelta(seconds=10)
    assert third.state is JobState.FAILED
    assert third.available_at is None


@pytest.mark.parametrize(
    "kwargs",
    [
        {"max_attempts": 0},
        {"max_attempts": -1},
        {"max_attempts": True},
        {"backoff": timedelta(0)},
        {"backoff": timedelta(seconds=-1)},
    ],
)
def test_retry_policy_rejects_invalid_configuration(kwargs: dict) -> None:
    base = {"max_attempts": 3, "backoff": timedelta(seconds=5)}
    with pytest.raises(DomainValidationError):
        RetryPolicy(**{**base, **kwargs})


def test_retry_decide_rejects_non_positive_attempt_count() -> None:
    policy = RetryPolicy(max_attempts=3)
    now = datetime(2026, 9, 8, tzinfo=UTC)

    with pytest.raises(DomainValidationError):
        policy.decide(
            attempt_count=0, failure_category=FailureCategory.TRANSIENT, now=now
        )


@pytest.mark.parametrize("field_name", ["available_at", "lease_until", "now"])
def test_naive_datetimes_are_rejected(field_name: str) -> None:
    aware = datetime(2026, 9, 8, tzinfo=UTC)
    naive = datetime(2026, 9, 8)

    if field_name == "available_at":
        with pytest.raises(DomainValidationError, match="available_at"):
            ClaimSnapshot(state=JobState.READY, available_at=naive)
        return
    if field_name == "lease_until":
        with pytest.raises(DomainValidationError, match="lease_until"):
            ClaimSnapshot(state=JobState.LEASED, available_at=aware, lease_until=naive)
        return

    snapshot = ClaimSnapshot(state=JobState.READY, available_at=aware)
    with pytest.raises(DomainValidationError, match="now"):
        is_claimable(snapshot, now=naive)
