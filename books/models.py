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
    generation = models.PositiveBigIntegerField(default=0)
    resolution_generation = models.PositiveBigIntegerField(default=0)
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
            models.CheckConstraint(
                condition=models.Q(generation__gte=0),
                name="book_generation_nonnegative",
            ),
            models.CheckConstraint(
                condition=models.Q(resolution_generation__gte=0),
                name="book_resolution_gen_nonnegative",
            ),
        ]

    def __str__(self) -> str:
        return self.name


class WorkspaceOwnedBookQuerySet(models.QuerySet):
    def owned_by(self, workspace_id: WorkspaceId | UUID):
        value = (
            workspace_id.value
            if isinstance(workspace_id, WorkspaceId)
            else workspace_id
        )
        return self.filter(workspace_id=value)


class ImmutableBookEvidenceError(RuntimeError):
    """An immutable book-owned revision was modified through the application ORM."""


class ImmutableBookOwnedQuerySet(WorkspaceOwnedBookQuerySet):
    def update(self, **kwargs):
        raise ImmutableBookEvidenceError("immutable policy evidence cannot be updated")

    def delete(self):
        raise ImmutableBookEvidenceError(
            "immutable policy evidence can be removed only through retention cleanup"
        )


class ReconciliationScope(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    workspace = models.ForeignKey(
        Workspace,
        on_delete=models.CASCADE,
        related_name="reconciliation_scopes",
    )
    book = models.ForeignKey(
        ReconciliationBook,
        on_delete=models.CASCADE,
        related_name="scopes",
    )
    coverage_key = models.CharField(max_length=200)
    left_dataset = models.ForeignKey(
        "ingestion.Dataset",
        on_delete=models.PROTECT,
        related_name="left_reconciliation_scopes",
    )
    right_dataset = models.ForeignKey(
        "ingestion.Dataset",
        on_delete=models.PROTECT,
        related_name="right_reconciliation_scopes",
    )
    generation = models.PositiveBigIntegerField(default=0)
    is_dirty = models.BooleanField(default=True)
    created_at = models.DateTimeField()

    objects = WorkspaceOwnedBookQuerySet.as_manager()

    class Meta:
        db_table = "reconciliation_scope"
        constraints = [
            models.UniqueConstraint(
                fields=["book", "coverage_key"],
                name="scope_book_coverage_unique",
            ),
            models.CheckConstraint(
                condition=~models.Q(coverage_key=""),
                name="scope_coverage_nonempty",
            ),
            models.CheckConstraint(
                condition=~models.Q(left_dataset=models.F("right_dataset")),
                name="scope_datasets_distinct",
            ),
            models.CheckConstraint(
                condition=models.Q(generation__gte=0),
                name="scope_generation_nonnegative",
            ),
        ]
        indexes = [
            models.Index(
                fields=["workspace", "book", "coverage_key"],
                name="scope_workspace_book_idx",
            ),
            models.Index(
                fields=["workspace", "is_dirty"],
                name="scope_workspace_dirty_idx",
            ),
        ]


class PolicyRevision(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    workspace = models.ForeignKey(
        Workspace,
        on_delete=models.CASCADE,
        related_name="policy_revisions",
    )
    book = models.ForeignKey(
        ReconciliationBook,
        on_delete=models.CASCADE,
        related_name="policy_revisions",
    )
    revision = models.PositiveIntegerField()
    matching_policy = models.JSONField()
    comparison_policy = models.JSONField()
    digest = models.CharField(max_length=64)
    created_at = models.DateTimeField()

    objects = ImmutableBookOwnedQuerySet.as_manager()

    class Meta:
        db_table = "policy_revision"
        constraints = [
            models.UniqueConstraint(
                fields=["book", "revision"],
                name="policy_book_revision_unique",
            ),
            models.UniqueConstraint(
                fields=["book", "digest"],
                name="policy_book_digest_unique",
            ),
            models.CheckConstraint(
                condition=models.Q(revision__gte=1),
                name="policy_revision_positive",
            ),
            models.CheckConstraint(
                condition=~models.Q(digest=""),
                name="policy_digest_nonempty",
            ),
        ]
        indexes = [
            models.Index(
                fields=["workspace", "book", "revision"],
                name="policy_workspace_book_idx",
            )
        ]

    def save(self, *args, **kwargs) -> None:
        if not self._state.adding:
            raise ImmutableBookEvidenceError(
                "PolicyRevision is immutable; append a revision"
            )
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ImmutableBookEvidenceError(
            "PolicyRevision can be removed only through retention cleanup"
        )
