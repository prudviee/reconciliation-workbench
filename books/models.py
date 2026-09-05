"""Database representation of a workspace-owned reconciliation book."""

from __future__ import annotations

from uuid import UUID, uuid4

from django.db import models

from reconciliation.domain import WorkspaceId
from workspaces.models import Workspace


class BookKind(models.TextChoices):
    USER = "USER", "User"
    DEMO = "DEMO", "Demo"


class ReconciliationBookQuerySet(models.QuerySet["ReconciliationBook"]):
    def owned_by(
        self, workspace_id: WorkspaceId | UUID
    ) -> "ReconciliationBookQuerySet":
        value = (
            workspace_id.value
            if isinstance(workspace_id, WorkspaceId)
            else workspace_id
        )
        return self.filter(workspace_id=value)


class ReconciliationBook(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    workspace = models.ForeignKey(
        Workspace,
        on_delete=models.CASCADE,
        related_name="books",
    )
    name = models.CharField(max_length=160)
    kind = models.CharField(max_length=4, choices=BookKind.choices)
    sample_template_version = models.CharField(max_length=80, null=True, blank=True)
    created_at = models.DateTimeField()

    objects = ReconciliationBookQuerySet.as_manager()

    class Meta:
        db_table = "reconciliation_book"
        indexes = [
            models.Index(fields=["workspace", "id"], name="book_workspace_public_idx"),
            models.Index(fields=["workspace", "created_at"], name="book_workspace_created_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(name=""),
                name="book_name_nonempty",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(kind=BookKind.USER, sample_template_version__isnull=True)
                    | models.Q(kind=BookKind.DEMO, sample_template_version__isnull=False)
                ),
                name="book_kind_template_consistent",
            ),
        ]

    def __str__(self) -> str:
        return self.name
