"""Workspace-owned source and contract revisions."""

from __future__ import annotations

from uuid import UUID, uuid4

from django.db import models

from books.models import ReconciliationBook
from reconciliation.domain import DatasetMode, ReferenceSemantics, WorkspaceId
from workspaces.models import Workspace


class ImmutableEvidenceError(RuntimeError):
    pass


class ImmutableEvidenceModel(models.Model):
    class Meta:
        abstract = True

    def save(self, *args, **kwargs) -> None:
        if not self._state.adding:
            raise ImmutableEvidenceError(
                f"{self.__class__.__name__} is immutable; append a revision"
            )
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ImmutableEvidenceError(
            f"{self.__class__.__name__} is immutable; remove it only through retention cleanup"
        )


class WorkspaceOwnedQuerySet(models.QuerySet):
    def owned_by(self, workspace_id: WorkspaceId | UUID):
        value = workspace_id.value if isinstance(workspace_id, WorkspaceId) else workspace_id
        return self.filter(workspace_id=value)


class ImmutableWorkspaceOwnedQuerySet(WorkspaceOwnedQuerySet):
    def update(self, **kwargs):
        raise ImmutableEvidenceError("immutable evidence cannot be bulk-updated")

    def delete(self):
        raise ImmutableEvidenceError(
            "immutable evidence can be removed only through retention cleanup"
        )


class SourceRole(models.TextChoices):
    LEFT = "LEFT", "Left"
    RIGHT = "RIGHT", "Right"


class SourceSystem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="sources")
    name = models.CharField(max_length=160)
    adapter_key = models.CharField(max_length=80)
    created_at = models.DateTimeField()
    objects = WorkspaceOwnedQuerySet.as_manager()

    class Meta:
        db_table = "source_system"
        indexes = [models.Index(fields=["workspace", "name"], name="source_workspace_name_idx")]
        constraints = [models.CheckConstraint(condition=~models.Q(name=""), name="source_name_nonempty")]


class BookSource(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="book_sources")
    book = models.ForeignKey(ReconciliationBook, on_delete=models.CASCADE, related_name="book_sources")
    source = models.ForeignKey(SourceSystem, on_delete=models.PROTECT, related_name="book_sources")
    role = models.CharField(max_length=5, choices=SourceRole.choices)
    identity_namespace = models.CharField(max_length=160)
    created_at = models.DateTimeField()
    objects = WorkspaceOwnedQuerySet.as_manager()

    class Meta:
        db_table = "book_source"
        constraints = [
            models.UniqueConstraint(fields=["book", "role"], name="book_source_role_unique"),
            models.CheckConstraint(condition=models.Q(role__in=SourceRole.values), name="book_source_valid_role"),
            models.CheckConstraint(condition=~models.Q(identity_namespace=""), name="book_source_namespace_nonempty"),
        ]
        indexes = [models.Index(fields=["workspace", "book"], name="book_source_workspace_idx")]


class MappingRevision(ImmutableEvidenceModel):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="mapping_revisions")
    source = models.ForeignKey(SourceSystem, on_delete=models.PROTECT, related_name="mapping_revisions")
    revision = models.PositiveIntegerField()
    mapping = models.JSONField()
    parser_version = models.CharField(max_length=40)
    digest = models.CharField(max_length=64)
    created_at = models.DateTimeField()
    objects = ImmutableWorkspaceOwnedQuerySet.as_manager()

    class Meta:
        db_table = "mapping_revision"
        constraints = [models.UniqueConstraint(fields=["source", "revision"], name="mapping_source_revision_unique")]
        indexes = [models.Index(fields=["workspace", "source"], name="mapping_workspace_source_idx")]


class SourceContractRevision(ImmutableEvidenceModel):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="contract_revisions")
    source = models.ForeignKey(SourceSystem, on_delete=models.PROTECT, related_name="contract_revisions")
    mapping_revision = models.ForeignKey(MappingRevision, on_delete=models.PROTECT, related_name="contracts")
    revision = models.PositiveIntegerField()
    mode = models.CharField(max_length=13, choices=[(item.value, item.name.title()) for item in DatasetMode])
    timezone_name = models.CharField(max_length=80, null=True, blank=True)
    identity_namespace = models.CharField(max_length=160)
    reference_semantics = models.CharField(max_length=14, choices=[(item.value, item.name.title()) for item in ReferenceSemantics])
    contract = models.JSONField()
    digest = models.CharField(max_length=64)
    created_at = models.DateTimeField()
    objects = ImmutableWorkspaceOwnedQuerySet.as_manager()

    class Meta:
        db_table = "source_contract_revision"
        constraints = [
            models.UniqueConstraint(fields=["source", "revision"], name="contract_source_revision_unique"),
            models.CheckConstraint(condition=~models.Q(identity_namespace=""), name="contract_namespace_nonempty"),
            models.CheckConstraint(condition=models.Q(mode__in=[item.value for item in DatasetMode]), name="contract_valid_mode"),
            models.CheckConstraint(condition=models.Q(reference_semantics__in=[item.value for item in ReferenceSemantics]), name="contract_valid_reference"),
        ]
        indexes = [models.Index(fields=["workspace", "source"], name="contract_workspace_source_idx")]
