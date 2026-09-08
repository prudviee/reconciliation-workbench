"""Database representation of leased background work."""

from __future__ import annotations

from uuid import UUID, uuid4

from django.db import models

from reconciliation.domain import FailureCategory, JobKind, JobState, WorkspaceId
from workspaces.models import Workspace


class JobEvidenceError(RuntimeError):
    """A frozen job fact was changed through the application ORM."""


class WorkItemOwnedQuerySet(models.QuerySet):
    def owned_by(self, workspace_id: WorkspaceId | UUID) -> "WorkItemOwnedQuerySet":
        value = (
            workspace_id.value
            if isinstance(workspace_id, WorkspaceId)
            else workspace_id
        )
        return self.filter(workspace_id=value)


class WorkItem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    workspace = models.ForeignKey(
        Workspace, on_delete=models.CASCADE, related_name="work_items"
    )
    kind = models.CharField(
        max_length=20, choices=[(item.value, item.name.title()) for item in JobKind]
    )
    state = models.CharField(
        max_length=9,
        choices=[(item.value, item.name.title()) for item in JobState],
        default=JobState.READY,
    )
    import_attempt = models.OneToOneField(
        "ingestion.IngestionAttempt",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="work_item",
    )
    reconciliation_run = models.OneToOneField(
        "reconciliation.ReconciliationRun",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="work_item",
    )
    cleanup_request = models.OneToOneField(
        "workspaces.WorkspaceCleanupRequest",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="work_item",
    )
    available_at = models.DateTimeField()
    lease_until = models.DateTimeField(null=True, blank=True)
    current_token = models.CharField(max_length=64, null=True, blank=True)
    attempt_count = models.PositiveIntegerField(default=0)
    max_attempts = models.PositiveIntegerField()
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()

    objects = WorkItemOwnedQuerySet.as_manager()

    class Meta:
        db_table = "work_item"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(kind__in=[item.value for item in JobKind]),
                name="work_item_kind_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(state__in=[item.value for item in JobState]),
                name="work_item_state_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(max_attempts__gte=1),
                name="work_item_max_attempts_positive",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        kind=JobKind.IMPORT_VALIDATION,
                        import_attempt__isnull=False,
                        reconciliation_run__isnull=True,
                        cleanup_request__isnull=True,
                    )
                    | models.Q(
                        kind=JobKind.RECONCILIATION_RUN,
                        import_attempt__isnull=True,
                        reconciliation_run__isnull=False,
                        cleanup_request__isnull=True,
                    )
                    | models.Q(
                        kind=JobKind.WORKSPACE_CLEANUP,
                        import_attempt__isnull=True,
                        reconciliation_run__isnull=True,
                        cleanup_request__isnull=False,
                    )
                ),
                name="work_item_target_shape_valid",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        state=JobState.LEASED,
                        lease_until__isnull=False,
                        current_token__isnull=False,
                    )
                    | models.Q(
                        state__in=[
                            JobState.READY,
                            JobState.SUCCEEDED,
                            JobState.FAILED,
                        ],
                        lease_until__isnull=True,
                        current_token__isnull=True,
                    )
                ),
                name="work_item_lease_shape_valid",
            ),
        ]
        indexes = [
            models.Index(
                fields=["kind", "state", "available_at"], name="work_item_claim_idx"
            ),
            models.Index(
                fields=["workspace", "kind"], name="work_item_workspace_kind_idx"
            ),
        ]


class JobAttemptOutcome(models.TextChoices):
    SUCCEEDED = "SUCCEEDED", "Succeeded"
    FAILED = "FAILED", "Failed"
    EXPIRED = "EXPIRED", "Expired"


class JobAttemptQuerySet(WorkItemOwnedQuerySet):
    def update(self, **kwargs):
        frozen_fields = {"work_item", "work_item_id", "token", "leased_at", "lease_until"}
        if frozen_fields.intersection(kwargs):
            raise JobEvidenceError("a claimed attempt's grant cannot be changed")
        return super().update(**kwargs)

    def delete(self):
        raise JobEvidenceError(
            "job attempts can be removed only through retention cleanup"
        )


class JobAttempt(models.Model):
    id = models.BigAutoField(primary_key=True)
    workspace = models.ForeignKey(
        Workspace, on_delete=models.CASCADE, related_name="job_attempts"
    )
    work_item = models.ForeignKey(
        WorkItem, on_delete=models.CASCADE, related_name="attempts"
    )
    token = models.CharField(max_length=64, unique=True)
    leased_at = models.DateTimeField()
    lease_until = models.DateTimeField()
    completed_at = models.DateTimeField(null=True, blank=True)
    outcome = models.CharField(
        max_length=9, choices=JobAttemptOutcome.choices, null=True, blank=True
    )
    failure_category = models.CharField(
        max_length=9,
        choices=[(item.value, item.name.title()) for item in FailureCategory],
        null=True,
        blank=True,
    )

    objects = JobAttemptQuerySet.as_manager()

    class Meta:
        db_table = "job_attempt"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(lease_until__gt=models.F("leased_at")),
                name="job_attempt_lease_after_grant",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        outcome__isnull=True,
                        completed_at__isnull=True,
                        failure_category__isnull=True,
                    )
                    | models.Q(
                        outcome__in=[
                            JobAttemptOutcome.SUCCEEDED,
                            JobAttemptOutcome.EXPIRED,
                        ],
                        completed_at__isnull=False,
                        failure_category__isnull=True,
                    )
                    | models.Q(
                        outcome=JobAttemptOutcome.FAILED,
                        completed_at__isnull=False,
                        failure_category__isnull=False,
                    )
                ),
                name="job_attempt_outcome_shape_valid",
            ),
        ]
        indexes = [
            models.Index(
                fields=["workspace", "work_item", "leased_at"],
                name="job_attempt_work_item_idx",
            ),
        ]

    def save(self, *args, **kwargs) -> None:
        if not self._state.adding:
            raise JobEvidenceError(
                "JobAttempt transitions must use the jobs claim service"
            )
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise JobEvidenceError(
            "job attempts can be removed only through retention cleanup"
        )
