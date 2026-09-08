"""Claim, complete, and fail leased background work."""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta

from django.db import models, transaction

from reconciliation.domain import (
    FailureCategory,
    JobState,
    LeaseToken,
    RetryOutcome,
)

from .models import JobAttempt, JobAttemptOutcome, WorkItem


class WorkItemUnavailable(LookupError):
    """A work item or its claimed attempt does not exist."""


@dataclass(frozen=True, slots=True)
class ClaimedWork:
    work_item: WorkItem
    token: LeaseToken


def _generate_token() -> str:
    return secrets.token_hex(32)


@transaction.atomic
def claim_batch(
    kind: str,
    *,
    now: datetime,
    lease_duration: timedelta,
    batch_size: int = 10,
) -> list[ClaimedWork]:
    """Claim up to `batch_size` ready or lease-expired items of one kind.

    `select_for_update(skip_locked=True)` is what makes this safe under
    concurrent callers without an external coordinator: a second caller's
    claim simply skips rows the first has already locked.
    """
    candidates = list(
        WorkItem.objects.select_for_update(skip_locked=True)
        .filter(kind=kind)
        .filter(
            models.Q(state=JobState.READY, available_at__lte=now)
            | models.Q(state=JobState.LEASED, lease_until__lt=now)
        )
        .order_by("available_at")[:batch_size]
    )
    claimed: list[ClaimedWork] = []
    for item in candidates:
        token = LeaseToken(_generate_token())
        lease_until = now + lease_duration
        WorkItem.objects.filter(id=item.id).update(
            state=JobState.LEASED,
            lease_until=lease_until,
            current_token=str(token),
            attempt_count=models.F("attempt_count") + 1,
            updated_at=now,
        )
        JobAttempt.objects.create(
            workspace_id=item.workspace_id,
            work_item=item,
            token=str(token),
            leased_at=now,
            lease_until=lease_until,
        )
        item.refresh_from_db()
        claimed.append(ClaimedWork(work_item=item, token=token))
    return claimed


@transaction.atomic
def mark_succeeded(token: LeaseToken, *, now: datetime) -> bool:
    """Record success. Returns False without effect if the token was fenced out."""
    try:
        attempt = JobAttempt.objects.get(token=str(token))
    except JobAttempt.DoesNotExist as error:
        raise WorkItemUnavailable from error
    work_item = WorkItem.objects.select_for_update().get(id=attempt.work_item_id)
    if work_item.current_token != str(token):
        JobAttempt.objects.filter(token=str(token)).update(
            outcome=JobAttemptOutcome.EXPIRED, completed_at=now
        )
        return False
    WorkItem.objects.filter(id=work_item.id).update(
        state=JobState.SUCCEEDED,
        lease_until=None,
        current_token=None,
        updated_at=now,
    )
    JobAttempt.objects.filter(token=str(token)).update(
        outcome=JobAttemptOutcome.SUCCEEDED, completed_at=now
    )
    return True


@transaction.atomic
def mark_failed(
    token: LeaseToken,
    *,
    outcome: RetryOutcome,
    failure_category: FailureCategory,
    now: datetime,
) -> bool:
    """Record failure and apply the caller's retry decision.

    Returns False without effect if the token was fenced out.
    """
    try:
        attempt = JobAttempt.objects.get(token=str(token))
    except JobAttempt.DoesNotExist as error:
        raise WorkItemUnavailable from error
    work_item = WorkItem.objects.select_for_update().get(id=attempt.work_item_id)
    if work_item.current_token != str(token):
        JobAttempt.objects.filter(token=str(token)).update(
            outcome=JobAttemptOutcome.EXPIRED, completed_at=now
        )
        return False
    next_available_at = (
        outcome.available_at if outcome.state is JobState.READY else work_item.available_at
    )
    WorkItem.objects.filter(id=work_item.id).update(
        state=outcome.state,
        available_at=next_available_at,
        lease_until=None,
        current_token=None,
        updated_at=now,
    )
    JobAttempt.objects.filter(token=str(token)).update(
        outcome=JobAttemptOutcome.FAILED,
        completed_at=now,
        failure_category=failure_category,
    )
    return True
