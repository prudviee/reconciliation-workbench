"""Claim, complete, and fail leased background work."""

from __future__ import annotations

import logging
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from time import perf_counter

from django.db import models, transaction

from reconciliation.domain import (
    FailureCategory,
    JobState,
    LeaseToken,
    QuotaAmounts,
    RetryOutcome,
    RetryPolicy,
    WorkspaceId,
)
from workspaces.quotas import WorkspaceQuotaService

from .models import JobAttempt, JobAttemptOutcome, WorkItem

logger = logging.getLogger("reconciliation.jobs")
execution_logger = logging.getLogger("reconciliation.jobs.events")
_ONE_ACTIVE_JOB = QuotaAmounts(active_jobs=1)


class WorkItemUnavailable(LookupError):
    """A work item or its claimed attempt does not exist."""


class TransientJobFailure(RuntimeError):
    """Raised by an executor for a failure that should retry."""


@dataclass(frozen=True, slots=True)
class ClaimedWork:
    work_item: WorkItem
    token: LeaseToken


@dataclass(frozen=True, slots=True)
class ExecutionRecord:
    work_item: WorkItem
    succeeded: bool


def _generate_token() -> str:
    return secrets.token_hex(32)


def _claimable(now: datetime):
    return models.Q(state=JobState.READY, available_at__lte=now) | models.Q(
        state=JobState.LEASED, lease_until__lt=now
    )


def enqueue(
    workspace_id: WorkspaceId,
    kind: str,
    *,
    max_attempts: int,
    now: datetime,
    **target,
) -> WorkItem:
    """Create, or reuse, the one `WorkItem` for a target.

    `target` must be exactly one of `import_attempt=`, `reconciliation_run=`,
    or `cleanup_request=`, matching the model's exact-shape constraint. The
    `active_jobs` quota is reserved only when a new row is actually created —
    calling this again for the same target (e.g. an unchanged manifest) is a
    no-op that returns the existing item without reserving twice.
    """
    if len(target) != 1:
        raise ValueError("enqueue requires exactly one target keyword argument")
    existing = WorkItem.objects.filter(**target).first()
    if existing is not None:
        return existing
    WorkspaceQuotaService().reserve(workspace_id, _ONE_ACTIVE_JOB)
    return WorkItem.objects.create(
        workspace_id=workspace_id.value,
        kind=kind,
        max_attempts=max_attempts,
        available_at=now,
        created_at=now,
        updated_at=now,
        **target,
    )


def _claim_row(item: WorkItem, *, now: datetime, lease_duration: timedelta) -> ClaimedWork:
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
    return ClaimedWork(work_item=item, token=token)


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
        .filter(_claimable(now))
        .order_by("available_at")[:batch_size]
    )
    return [_claim_row(item, now=now, lease_duration=lease_duration) for item in candidates]


@transaction.atomic
def claim_one(work_item_id, *, now: datetime, lease_duration: timedelta) -> ClaimedWork | None:
    """Claim exactly one work item by id, if it is currently claimable.

    Used by a caller that just enqueued a specific item and needs to run it
    inline (the local single-process Compose path), rather than pulling
    whatever is next in the system-wide queue for that kind.
    """
    candidate = (
        WorkItem.objects.select_for_update(skip_locked=True)
        .filter(id=work_item_id)
        .filter(_claimable(now))
        .first()
    )
    if candidate is None:
        return None
    return _claim_row(candidate, now=now, lease_duration=lease_duration)


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
    WorkspaceQuotaService().release(WorkspaceId(work_item.workspace_id), _ONE_ACTIVE_JOB)
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
    if outcome.state is JobState.FAILED:
        WorkspaceQuotaService().release(WorkspaceId(work_item.workspace_id), _ONE_ACTIVE_JOB)
    return True


def claim_and_execute(
    kind: str,
    *,
    now: datetime,
    lease_duration: timedelta,
    retry_policy: RetryPolicy,
    executor: Callable[[WorkItem, LeaseToken], None],
    batch_size: int = 1,
    work_item_id=None,
) -> list[ExecutionRecord]:
    """Claim work of one kind and run `executor` on each claimed item.

    With `work_item_id`, claims exactly that item (or nothing, if it is not
    currently claimable) via `claim_one`; otherwise claims up to `batch_size`
    items system-wide via `claim_batch`. `executor` must raise
    `TransientJobFailure` for a retryable failure and let any other exception
    propagate for a permanent one; both are recorded through `mark_failed`
    using `retry_policy` and logged, but never re-raised — one item's failure
    does not stop the rest of the batch from being attempted, which matters
    for a polling worker processing many items per cycle. The caller reads
    `ExecutionRecord.succeeded` per item rather than catching exceptions.

    A successful `WORKSPACE_CLEANUP` executor deletes the workspace, which
    cascades away its own `WorkItem`/`JobAttempt` rows before this function's
    own `mark_succeeded` call can reach them; that `WorkItemUnavailable` is
    swallowed rather than reported as failure, since the executor's own
    success (no exception) already proves the outcome.
    """
    if work_item_id is not None:
        one = claim_one(work_item_id, now=now, lease_duration=lease_duration)
        claimed = [one] if one is not None else []
    else:
        claimed = claim_batch(kind, now=now, lease_duration=lease_duration, batch_size=batch_size)
    records: list[ExecutionRecord] = []
    for work in claimed:
        started = perf_counter()
        failure_category_value: str | None = None
        try:
            executor(work.work_item, work.token)
        except TransientJobFailure:
            failure_category_value = FailureCategory.TRANSIENT.value
            outcome = retry_policy.decide(
                attempt_count=work.work_item.attempt_count,
                failure_category=FailureCategory.TRANSIENT,
                now=now,
            )
            mark_failed(work.token, outcome=outcome, failure_category=FailureCategory.TRANSIENT, now=now)
            records.append(ExecutionRecord(work.work_item, succeeded=False))
        except Exception:
            failure_category_value = FailureCategory.PERMANENT.value
            logger.exception(
                "claimed_work_failed",
                extra={"kind": kind, "work_item_id": str(work.work_item.id)},
            )
            outcome = retry_policy.decide(
                attempt_count=work.work_item.attempt_count,
                failure_category=FailureCategory.PERMANENT,
                now=now,
            )
            mark_failed(work.token, outcome=outcome, failure_category=FailureCategory.PERMANENT, now=now)
            records.append(ExecutionRecord(work.work_item, succeeded=False))
        else:
            try:
                mark_succeeded(work.token, now=now)
            except WorkItemUnavailable:
                pass
            records.append(ExecutionRecord(work.work_item, succeeded=True))
        finally:
            _log_job_execution(
                kind=kind,
                work_item=work.work_item,
                duration_ms=round((perf_counter() - started) * 1000, 3),
                failure_category=failure_category_value,
            )
    return records


def _log_job_execution(
    *,
    kind: str,
    work_item: WorkItem,
    duration_ms: float,
    failure_category: str | None,
) -> None:
    from observability.logging import hash_workspace_ref, safe_event

    event = safe_event(
        {
            "event": "job_execution_completed",
            "stage": kind,
            "job_id": str(work_item.id),
            "run_id": str(work_item.reconciliation_run_id)
            if work_item.reconciliation_run_id
            else None,
            "import_id": str(work_item.import_attempt_id)
            if work_item.import_attempt_id
            else None,
            "workspace_ref": hash_workspace_ref(work_item.workspace_id),
            "duration_ms": duration_ms,
            "failure_category": failure_category,
        }
    )
    execution_logger.info("job_execution_completed", extra={"structured_event": event})
