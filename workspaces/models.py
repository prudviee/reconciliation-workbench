"""Database representation of anonymous workspaces."""

from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

from django.db import models

from reconciliation.domain import WorkspaceState


class Workspace(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    session_digest = models.CharField(max_length=64, unique=True)
    state = models.CharField(
        max_length=8,
        choices=[(state.value, state.name.title()) for state in WorkspaceState],
        default=WorkspaceState.ACTIVE,
    )
    created_at = models.DateTimeField()
    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    retained_bytes = models.BigIntegerField(default=0)
    book_count = models.PositiveIntegerField(default=0)
    active_job_count = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "workspace"
        indexes = [
            models.Index(fields=["state", "expires_at"], name="workspace_state_expiry_idx")
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(
                    expires_at=models.F("created_at") + timedelta(days=7)
                ),
                name="workspace_fixed_expiry_7d",
            ),
            models.CheckConstraint(
                condition=models.Q(state__in=[state.value for state in WorkspaceState]),
                name="workspace_valid_state",
            ),
            models.CheckConstraint(
                condition=models.Q(retained_bytes__gte=0),
                name="workspace_retained_bytes_nonnegative",
            ),
            models.CheckConstraint(
                condition=models.Q(book_count__gte=0),
                name="workspace_book_count_nonnegative",
            ),
            models.CheckConstraint(
                condition=models.Q(active_job_count__gte=0),
                name="workspace_active_jobs_nonnegative",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        state=WorkspaceState.ACTIVE,
                        revoked_at__isnull=True,
                        deleted_at__isnull=True,
                    )
                    | models.Q(
                        state=WorkspaceState.REVOKED,
                        revoked_at__isnull=False,
                        deleted_at__isnull=True,
                    )
                    | models.Q(
                        state=WorkspaceState.DELETED,
                        revoked_at__isnull=False,
                        deleted_at__isnull=False,
                    )
                ),
                name="workspace_lifecycle_timestamps",
            ),
        ]

    def __str__(self) -> str:
        return str(self.id)


class CleanupReason(models.TextChoices):
    EXPIRED = "EXPIRED", "Expired"
    DELETED = "DELETED", "Deleted"


class WorkspaceCleanupRequest(models.Model):
    workspace = models.OneToOneField(
        Workspace,
        on_delete=models.CASCADE,
        primary_key=True,
        related_name="cleanup_request",
    )
    reason = models.CharField(max_length=7, choices=CleanupReason.choices)
    requested_at = models.DateTimeField()
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "workspace_cleanup_request"
        indexes = [
            models.Index(
                fields=["requested_at"],
                name="cleanup_pending_idx",
                condition=models.Q(processed_at__isnull=True),
            )
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(reason__in=CleanupReason.values),
                name="cleanup_valid_reason",
            )
        ]
