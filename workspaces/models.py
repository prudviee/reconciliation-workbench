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
        ]

    def __str__(self) -> str:
        return str(self.id)
