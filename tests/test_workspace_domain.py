from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from uuid import UUID

import pytest

from reconciliation.domain import (
    BookId,
    DomainValidationError,
    ExpiryPolicy,
    QuotaAmounts,
    QuotaExceeded,
    QuotaPolicy,
    QuotaResource,
    WorkspaceAccessFailure,
    WorkspaceId,
    WorkspaceState,
)


def test_opaque_ids_round_trip_without_framework_types() -> None:
    value = UUID("2eec10ec-fbaf-43b9-a223-6659ac3a6610")

    assert WorkspaceId.parse(str(value)) == WorkspaceId(value)
    assert BookId.parse(str(value)) == BookId(value)
    assert str(WorkspaceId(value)) == str(value)


def test_expiry_is_exactly_seven_days_from_creation_in_utc() -> None:
    created_at = datetime(
        2026, 9, 5, 21, 45, tzinfo=timezone(timedelta(hours=5, minutes=30))
    )

    expires_at = ExpiryPolicy().expires_at(created_at)

    assert expires_at == datetime(2026, 9, 12, 16, 15, tzinfo=UTC)


@pytest.mark.parametrize("field_name", ["created_at", "expires_at", "now"])
def test_lifecycle_rejects_naive_datetimes(field_name: str) -> None:
    policy = ExpiryPolicy()
    aware = datetime(2026, 9, 5, tzinfo=UTC)
    values = {
        "state": WorkspaceState.ACTIVE,
        "expires_at": aware,
        "now": aware,
    }

    if field_name == "created_at":
        with pytest.raises(DomainValidationError, match="created_at"):
            policy.expires_at(datetime(2026, 9, 5))
        return

    values[field_name] = datetime(2026, 9, 5)
    with pytest.raises(DomainValidationError, match=field_name):
        policy.evaluate(**values)


def test_active_workspace_expires_at_inclusive_boundary() -> None:
    policy = ExpiryPolicy()
    expiry = datetime(2026, 9, 12, 16, 15, tzinfo=UTC)

    before = policy.evaluate(
        state=WorkspaceState.ACTIVE,
        expires_at=expiry,
        now=expiry - timedelta(microseconds=1),
    )
    at_boundary = policy.evaluate(
        state=WorkspaceState.ACTIVE,
        expires_at=expiry,
        now=expiry,
    )

    assert before.access_allowed is True
    assert before.failure is None
    assert at_boundary.access_allowed is False
    assert at_boundary.state is WorkspaceState.REVOKED
    assert at_boundary.failure is WorkspaceAccessFailure.EXPIRED
    assert at_boundary.requires_revocation is True


def test_activity_cannot_extend_the_persisted_expiry() -> None:
    policy = ExpiryPolicy()
    created_at = datetime(2026, 9, 5, 12, tzinfo=UTC)
    fixed_expiry = policy.expires_at(created_at)

    for active_day in range(7):
        result = policy.evaluate(
            state=WorkspaceState.ACTIVE,
            expires_at=fixed_expiry,
            now=created_at + timedelta(days=active_day, hours=23),
        )
        assert result.access_allowed is True

    expired = policy.evaluate(
        state=WorkspaceState.ACTIVE,
        expires_at=fixed_expiry,
        now=fixed_expiry,
    )
    assert expired.failure is WorkspaceAccessFailure.EXPIRED


@pytest.mark.parametrize(
    ("state", "failure"),
    [
        (WorkspaceState.REVOKED, WorkspaceAccessFailure.REVOKED),
        (WorkspaceState.DELETED, WorkspaceAccessFailure.DELETED),
    ],
)
def test_non_active_state_never_regains_access(
    state: WorkspaceState, failure: WorkspaceAccessFailure
) -> None:
    result = ExpiryPolicy().evaluate(
        state=state,
        expires_at=datetime(2030, 1, 1, tzinfo=UTC),
        now=datetime(2026, 9, 5, tzinfo=UTC),
    )

    assert result.access_allowed is False
    assert result.failure is failure
    assert result.requires_revocation is False


def test_quota_reservation_returns_new_usage_without_mutating_inputs() -> None:
    usage = QuotaAmounts(retained_bytes=90, books=2, active_jobs=1)
    requested = QuotaAmounts(retained_bytes=10, books=1, active_jobs=1)
    policy = QuotaPolicy(QuotaAmounts(retained_bytes=100, books=3, active_jobs=2))

    result = policy.reserve(usage=usage, requested=requested)

    assert result == QuotaAmounts(retained_bytes=100, books=3, active_jobs=2)
    assert usage == QuotaAmounts(retained_bytes=90, books=2, active_jobs=1)
    assert requested == QuotaAmounts(retained_bytes=10, books=1, active_jobs=1)


@pytest.mark.parametrize(
    ("usage", "requested", "expected_resource"),
    [
        (
            QuotaAmounts(retained_bytes=100),
            QuotaAmounts(retained_bytes=1),
            QuotaResource.RETAINED_BYTES,
        ),
        (QuotaAmounts(books=3), QuotaAmounts(books=1), QuotaResource.BOOKS),
        (
            QuotaAmounts(active_jobs=2),
            QuotaAmounts(active_jobs=1),
            QuotaResource.ACTIVE_JOBS,
        ),
    ],
)
def test_each_quota_reports_a_typed_failure_without_changing_usage(
    usage: QuotaAmounts,
    requested: QuotaAmounts,
    expected_resource: QuotaResource,
) -> None:
    policy = QuotaPolicy(QuotaAmounts(retained_bytes=100, books=3, active_jobs=2))

    with pytest.raises(QuotaExceeded) as captured:
        policy.reserve(usage=usage, requested=requested)

    assert captured.value.resource is expected_resource
    field_name = expected_resource.value
    assert captured.value.current == getattr(usage, field_name)
    assert captured.value.requested == getattr(requested, field_name)
    assert captured.value.limit == getattr(policy.limits, field_name)


def test_quota_property_matches_sum_less_than_or_equal_to_limit() -> None:
    limit = 8
    policy = QuotaPolicy(QuotaAmounts(limit, limit, limit))

    for current in range(limit + 1):
        for requested in range(limit + 1):
            values = QuotaAmounts(current, current, current)
            addition = QuotaAmounts(requested, requested, requested)
            if current + requested <= limit:
                assert policy.reserve(usage=values, requested=addition) == QuotaAmounts(
                    current + requested,
                    current + requested,
                    current + requested,
                )
            else:
                with pytest.raises(QuotaExceeded):
                    policy.reserve(usage=values, requested=addition)


@pytest.mark.parametrize("value", [-1, True, 1.5])
def test_quota_amounts_reject_invalid_values(value: object) -> None:
    with pytest.raises(DomainValidationError):
        QuotaAmounts(retained_bytes=value)  # type: ignore[arg-type]
