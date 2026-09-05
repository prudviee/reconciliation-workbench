"""Pure workspace lifecycle and quota contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Self
from uuid import UUID


class DomainValidationError(ValueError):
    """A domain value violates a declared invariant."""


@dataclass(frozen=True, slots=True)
class WorkspaceId:
    value: UUID

    @classmethod
    def parse(cls, value: str | UUID) -> Self:
        return cls(value if isinstance(value, UUID) else UUID(value))

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True, slots=True)
class WorkspaceAccess:
    workspace_id: WorkspaceId
    expires_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "expires_at",
            _as_utc(self.expires_at, "expires_at"),
        )


@dataclass(frozen=True, slots=True)
class BookId:
    value: UUID

    @classmethod
    def parse(cls, value: str | UUID) -> Self:
        return cls(value if isinstance(value, UUID) else UUID(value))

    def __str__(self) -> str:
        return str(self.value)


class WorkspaceState(StrEnum):
    ACTIVE = "ACTIVE"
    REVOKED = "REVOKED"
    DELETED = "DELETED"


class WorkspaceAccessFailure(StrEnum):
    EXPIRED = "EXPIRED"
    REVOKED = "REVOKED"
    DELETED = "DELETED"


@dataclass(frozen=True, slots=True)
class WorkspaceLifecycleResult:
    state: WorkspaceState
    access_allowed: bool
    failure: WorkspaceAccessFailure | None
    requires_revocation: bool = False


@dataclass(frozen=True, slots=True)
class ExpiryPolicy:
    retention: timedelta = timedelta(days=7)

    def __post_init__(self) -> None:
        if self.retention <= timedelta(0):
            raise DomainValidationError("retention must be greater than zero")

    def expires_at(self, created_at: datetime) -> datetime:
        return _as_utc(created_at, "created_at") + self.retention

    def evaluate(
        self,
        *,
        state: WorkspaceState,
        expires_at: datetime,
        now: datetime,
    ) -> WorkspaceLifecycleResult:
        expiry = _as_utc(expires_at, "expires_at")
        current = _as_utc(now, "now")

        if state is WorkspaceState.DELETED:
            return WorkspaceLifecycleResult(
                state=state,
                access_allowed=False,
                failure=WorkspaceAccessFailure.DELETED,
            )
        if state is WorkspaceState.REVOKED:
            return WorkspaceLifecycleResult(
                state=state,
                access_allowed=False,
                failure=WorkspaceAccessFailure.REVOKED,
            )
        if current >= expiry:
            return WorkspaceLifecycleResult(
                state=WorkspaceState.REVOKED,
                access_allowed=False,
                failure=WorkspaceAccessFailure.EXPIRED,
                requires_revocation=True,
            )
        return WorkspaceLifecycleResult(
            state=WorkspaceState.ACTIVE,
            access_allowed=True,
            failure=None,
        )


class QuotaResource(StrEnum):
    RETAINED_BYTES = "retained_bytes"
    BOOKS = "books"
    ACTIVE_JOBS = "active_jobs"


@dataclass(frozen=True, slots=True)
class QuotaAmounts:
    retained_bytes: int = 0
    books: int = 0
    active_jobs: int = 0

    def __post_init__(self) -> None:
        for field_name in ("retained_bytes", "books", "active_jobs"):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise DomainValidationError(
                    f"{field_name} must be a nonnegative integer"
                )

    def plus(self, other: QuotaAmounts) -> QuotaAmounts:
        return QuotaAmounts(
            retained_bytes=self.retained_bytes + other.retained_bytes,
            books=self.books + other.books,
            active_jobs=self.active_jobs + other.active_jobs,
        )


@dataclass(frozen=True, slots=True)
class QuotaExceeded(Exception):
    resource: QuotaResource
    current: int
    requested: int
    limit: int

    def __str__(self) -> str:
        return (
            f"{self.resource.value} quota exceeded: "
            f"current={self.current}, requested={self.requested}, limit={self.limit}"
        )


@dataclass(frozen=True, slots=True)
class QuotaPolicy:
    limits: QuotaAmounts

    def reserve(
        self,
        *,
        usage: QuotaAmounts,
        requested: QuotaAmounts,
    ) -> QuotaAmounts:
        resulting = usage.plus(requested)
        checks = (
            (
                QuotaResource.RETAINED_BYTES,
                usage.retained_bytes,
                requested.retained_bytes,
                resulting.retained_bytes,
                self.limits.retained_bytes,
            ),
            (
                QuotaResource.BOOKS,
                usage.books,
                requested.books,
                resulting.books,
                self.limits.books,
            ),
            (
                QuotaResource.ACTIVE_JOBS,
                usage.active_jobs,
                requested.active_jobs,
                resulting.active_jobs,
                self.limits.active_jobs,
            ),
        )
        for resource, current, addition, total, limit in checks:
            if total > limit:
                raise QuotaExceeded(
                    resource=resource,
                    current=current,
                    requested=addition,
                    limit=limit,
                )
        return resulting


def _as_utc(value: datetime, name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise DomainValidationError(f"{name} must be timezone-aware")
    return value.astimezone(UTC)
