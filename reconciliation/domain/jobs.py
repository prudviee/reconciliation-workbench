"""Pure claim, lease, and retry contracts for background work."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum

from .workspaces import DomainValidationError


class JobKind(StrEnum):
    IMPORT_VALIDATION = "IMPORT_VALIDATION"
    RECONCILIATION_RUN = "RECONCILIATION_RUN"
    WORKSPACE_CLEANUP = "WORKSPACE_CLEANUP"


class JobState(StrEnum):
    READY = "READY"
    LEASED = "LEASED"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class FailureCategory(StrEnum):
    TRANSIENT = "TRANSIENT"
    PERMANENT = "PERMANENT"


@dataclass(frozen=True, slots=True)
class LeaseToken:
    value: str

    def __post_init__(self) -> None:
        if not self.value:
            raise DomainValidationError("a lease token must not be empty")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class ClaimSnapshot:
    state: JobState
    available_at: datetime
    lease_until: datetime | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "available_at", _as_utc(self.available_at, "available_at")
        )
        if self.lease_until is not None:
            object.__setattr__(
                self, "lease_until", _as_utc(self.lease_until, "lease_until")
            )
        if self.state is JobState.LEASED and self.lease_until is None:
            raise DomainValidationError("a LEASED item requires lease_until")
        if self.state is not JobState.LEASED and self.lease_until is not None:
            raise DomainValidationError("only a LEASED item may carry lease_until")


def is_claimable(snapshot: ClaimSnapshot, *, now: datetime) -> bool:
    """Evaluate the same rule the SKIP LOCKED claim query enforces in SQL."""
    current = _as_utc(now, "now")
    if snapshot.state is JobState.READY:
        return current >= snapshot.available_at
    if snapshot.state is JobState.LEASED:
        assert snapshot.lease_until is not None
        return current > snapshot.lease_until
    return False


@dataclass(frozen=True, slots=True)
class RetryOutcome:
    state: JobState
    available_at: datetime | None

    def __post_init__(self) -> None:
        if self.state not in (JobState.READY, JobState.FAILED):
            raise DomainValidationError(
                "a retry outcome state must be READY or FAILED"
            )
        if self.state is JobState.READY and self.available_at is None:
            raise DomainValidationError(
                "a READY retry outcome requires available_at"
            )
        if self.state is JobState.FAILED and self.available_at is not None:
            raise DomainValidationError(
                "a FAILED retry outcome must not carry available_at"
            )
        if self.available_at is not None:
            object.__setattr__(
                self, "available_at", _as_utc(self.available_at, "available_at")
            )


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    max_attempts: int
    backoff: timedelta = timedelta(seconds=5)

    def __post_init__(self) -> None:
        if (
            isinstance(self.max_attempts, bool)
            or not isinstance(self.max_attempts, int)
            or self.max_attempts < 1
        ):
            raise DomainValidationError("max_attempts must be a positive integer")
        if self.backoff <= timedelta(0):
            raise DomainValidationError("backoff must be greater than zero")

    def decide(
        self,
        *,
        attempt_count: int,
        failure_category: FailureCategory,
        now: datetime,
    ) -> RetryOutcome:
        if (
            isinstance(attempt_count, bool)
            or not isinstance(attempt_count, int)
            or attempt_count < 1
        ):
            raise DomainValidationError("attempt_count must be a positive integer")
        current = _as_utc(now, "now")
        if failure_category is FailureCategory.PERMANENT:
            return RetryOutcome(state=JobState.FAILED, available_at=None)
        if attempt_count >= self.max_attempts:
            return RetryOutcome(state=JobState.FAILED, available_at=None)
        delay = self.backoff * (2 ** (attempt_count - 1))
        return RetryOutcome(state=JobState.READY, available_at=current + delay)


def _as_utc(value: datetime, name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise DomainValidationError(f"{name} must be timezone-aware")
    return value.astimezone(UTC)
