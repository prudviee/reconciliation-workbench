"""Immutable ingestion evidence and materialized dataset revisions."""

from __future__ import annotations

from uuid import UUID, uuid4

from django.db import models

from reconciliation.domain import CanonicalSide, CanonicalState, WorkspaceId
from sources.models import (
    BookSource,
    ImmutableEvidenceModel,
    ImmutableWorkspaceOwnedQuerySet,
    SourceContractRevision,
    WorkspaceOwnedQuerySet,
)
from workspaces.models import Workspace


class AttemptState(models.TextChoices):
    RECEIVED = "RECEIVED", "Received"
    PARSING = "PARSING", "Parsing"
    READY = "READY", "Ready"
    REJECTED = "REJECTED", "Rejected"
    ACTIVATED = "ACTIVATED", "Activated"
    NO_CHANGE = "NO_CHANGE", "No change"
    REPLAYED = "REPLAYED", "Historical replay"


class Dataset(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="datasets")
    book_source = models.ForeignKey(BookSource, on_delete=models.CASCADE, related_name="datasets")
    coverage_key = models.CharField(max_length=200)
    current_revision = models.ForeignKey("DatasetRevision", on_delete=models.PROTECT, null=True, blank=True, related_name="current_for")
    created_at = models.DateTimeField()
    objects = WorkspaceOwnedQuerySet.as_manager()

    class Meta:
        db_table = "dataset"
        constraints = [models.UniqueConstraint(fields=["book_source", "coverage_key"], name="dataset_source_coverage_unique")]
        indexes = [models.Index(fields=["workspace", "book_source"], name="dataset_workspace_source_idx")]


class FileArtifact(ImmutableEvidenceModel):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="file_artifacts")
    storage_key = models.CharField(max_length=240, unique=True)
    physical_hash = models.CharField(max_length=64)
    original_filename = models.CharField(max_length=255)
    content_type = models.CharField(max_length=120)
    byte_size = models.BigIntegerField()
    created_at = models.DateTimeField()
    objects = ImmutableWorkspaceOwnedQuerySet.as_manager()

    class Meta:
        db_table = "file_artifact"
        constraints = [models.CheckConstraint(condition=models.Q(byte_size__gte=0), name="artifact_size_nonnegative")]
        indexes = [models.Index(fields=["workspace", "physical_hash"], name="artifact_workspace_hash_idx")]


class IngestionAttempt(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="ingestion_attempts")
    artifact = models.ForeignKey(FileArtifact, on_delete=models.PROTECT, related_name="attempts")
    dataset = models.ForeignKey(Dataset, on_delete=models.CASCADE, related_name="attempts")
    contract_revision = models.ForeignKey(SourceContractRevision, on_delete=models.PROTECT, related_name="attempts")
    expected_base = models.ForeignKey("DatasetRevision", on_delete=models.PROTECT, null=True, blank=True, related_name="dependent_attempts")
    state = models.CharField(max_length=10, choices=AttemptState.choices, default=AttemptState.RECEIVED)
    physical_hash = models.CharField(max_length=64)
    semantic_hash = models.CharField(max_length=64, null=True, blank=True)
    delimiter = models.CharField(max_length=1)
    row_count = models.PositiveIntegerField(default=0)
    error_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField()
    completed_at = models.DateTimeField(null=True, blank=True)
    objects = WorkspaceOwnedQuerySet.as_manager()

    class Meta:
        db_table = "ingestion_attempt"
        indexes = [models.Index(fields=["workspace", "dataset", "created_at"], name="attempt_workspace_dataset_idx")]
        constraints = [models.CheckConstraint(condition=models.Q(state__in=AttemptState.values), name="attempt_valid_state")]


class RawRow(ImmutableEvidenceModel):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="raw_rows")
    attempt = models.ForeignKey(IngestionAttempt, on_delete=models.CASCADE, related_name="raw_rows")
    row_number = models.PositiveIntegerField()
    raw_values = models.JSONField()
    canonical_preview = models.JSONField(null=True, blank=True)
    validation = models.JSONField(default=list)
    objects = ImmutableWorkspaceOwnedQuerySet.as_manager()

    class Meta:
        db_table = "raw_row"
        constraints = [
            models.UniqueConstraint(fields=["attempt", "row_number"], name="raw_row_attempt_number_unique"),
            models.CheckConstraint(condition=models.Q(row_number__gte=1), name="raw_row_number_positive"),
        ]


class LogicalTransaction(ImmutableEvidenceModel):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="logical_transactions")
    book_source = models.ForeignKey(BookSource, on_delete=models.PROTECT, related_name="logical_transactions")
    source_record_key = models.CharField(max_length=240)
    created_at = models.DateTimeField()
    objects = ImmutableWorkspaceOwnedQuerySet.as_manager()

    class Meta:
        db_table = "logical_transaction"
        constraints = [
            models.UniqueConstraint(fields=["book_source", "source_record_key"], name="logical_source_key_unique"),
            models.CheckConstraint(condition=~models.Q(source_record_key=""), name="logical_source_key_nonempty"),
        ]


class TransactionObservation(ImmutableEvidenceModel):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="transaction_observations")
    logical_transaction = models.ForeignKey(LogicalTransaction, on_delete=models.PROTECT, related_name="observations")
    raw_row = models.ForeignKey(RawRow, on_delete=models.PROTECT, related_name="observations")
    business_reference = models.CharField(max_length=240, null=True, blank=True)
    executed_at_utc = models.DateTimeField()
    instrument = models.CharField(max_length=120)
    side = models.CharField(max_length=4, choices=[(item.value, item.name.title()) for item in CanonicalSide])
    quantity = models.DecimalField(max_digits=38, decimal_places=12)
    unit_price = models.DecimalField(max_digits=38, decimal_places=12)
    gross_amount = models.DecimalField(max_digits=38, decimal_places=12)
    currency = models.CharField(max_length=12)
    state = models.CharField(max_length=9, choices=[(item.value, item.name.title()) for item in CanonicalState])
    eligible_for_matching = models.BooleanField()
    provenance = models.JSONField()
    fingerprint = models.CharField(max_length=64)
    created_at = models.DateTimeField()
    objects = ImmutableWorkspaceOwnedQuerySet.as_manager()

    class Meta:
        db_table = "transaction_observation"
        indexes = [
            models.Index(fields=["workspace", "logical_transaction"], name="obs_ws_logical_idx"),
            models.Index(fields=["workspace", "instrument", "side", "currency", "executed_at_utc"], name="observation_candidate_idx"),
        ]
        constraints = [
            models.CheckConstraint(condition=models.Q(side__in=[item.value for item in CanonicalSide]), name="observation_valid_side"),
            models.CheckConstraint(condition=models.Q(state__in=[item.value for item in CanonicalState]), name="observation_valid_state"),
            models.CheckConstraint(
                condition=(
                    models.Q(state=CanonicalState.CANCELLED, eligible_for_matching=False)
                    | models.Q(state=CanonicalState.SETTLED, eligible_for_matching=True)
                ),
                name="observation_state_eligibility",
            ),
        ]


class DatasetRevision(ImmutableEvidenceModel):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="dataset_revisions")
    dataset = models.ForeignKey(Dataset, on_delete=models.CASCADE, related_name="revisions")
    parent_revision = models.ForeignKey("self", on_delete=models.PROTECT, null=True, blank=True, related_name="children")
    attempt = models.OneToOneField(IngestionAttempt, on_delete=models.PROTECT, related_name="activated_revision")
    state_hash = models.CharField(max_length=64)
    created_at = models.DateTimeField()
    objects = ImmutableWorkspaceOwnedQuerySet.as_manager()

    class Meta:
        db_table = "dataset_revision"
        indexes = [models.Index(fields=["workspace", "dataset", "created_at"], name="revision_workspace_dataset_idx")]


class DatasetMembership(ImmutableEvidenceModel):
    id = models.BigAutoField(primary_key=True)
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="dataset_memberships")
    dataset_revision = models.ForeignKey(DatasetRevision, on_delete=models.CASCADE, related_name="memberships")
    logical_transaction = models.ForeignKey(LogicalTransaction, on_delete=models.PROTECT, related_name="memberships")
    observation = models.ForeignKey(TransactionObservation, on_delete=models.PROTECT, related_name="memberships")
    objects = ImmutableWorkspaceOwnedQuerySet.as_manager()

    class Meta:
        db_table = "dataset_membership"
        constraints = [models.UniqueConstraint(fields=["dataset_revision", "logical_transaction"], name="membership_revision_logical_unique")]
        indexes = [models.Index(fields=["workspace", "dataset_revision"], name="membership_ws_revision_idx")]
