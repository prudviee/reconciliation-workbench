"""Frozen manifests and immutable reconciliation result evidence."""

from __future__ import annotations

from uuid import UUID, uuid4

from django.db import models

from reconciliation.domain import (
    ComparisonStatus,
    DiagnosticKind,
    PairOrigin,
    RecordSide,
    UnpairedReason,
    WorkspaceId,
)


class RunEvidenceError(RuntimeError):
    pass


class RunOwnedQuerySet(models.QuerySet):
    def owned_by(self, workspace_id: WorkspaceId | UUID):
        value = workspace_id.value if isinstance(workspace_id, WorkspaceId) else workspace_id
        return self.filter(workspace_id=value)

    def update(self, **kwargs):
        frozen_fields = {
            "workspace",
            "workspace_id",
            "scope",
            "scope_id",
            "left_revision",
            "left_revision_id",
            "right_revision",
            "right_revision_id",
            "policy_revision",
            "policy_revision_id",
            "manifest",
            "manifest_hash",
            "data_generation",
            "resolution_generation",
            "scope_generation",
            "engine_version",
            "solver_version",
            "created_at",
        }
        if frozen_fields.intersection(kwargs):
            raise RunEvidenceError("a frozen run manifest cannot be changed")
        return super().update(**kwargs)

    def delete(self):
        raise RunEvidenceError("runs can be removed only through retention cleanup")


class ImmutableRunQuerySet(RunOwnedQuerySet):
    def update(self, **kwargs):
        raise RunEvidenceError("immutable run evidence cannot be bulk-updated")

    def delete(self):
        raise RunEvidenceError("immutable run evidence can be removed only through retention cleanup")


class ImmutableRunModel(models.Model):
    class Meta:
        abstract = True

    def save(self, *args, **kwargs) -> None:
        if not self._state.adding:
            raise RunEvidenceError(f"{self.__class__.__name__} is immutable")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise RunEvidenceError(f"{self.__class__.__name__} is immutable")


class RunLifecycle(models.TextChoices):
    FROZEN = "FROZEN", "Frozen"
    RUNNING = "RUNNING", "Running"
    COMPLETED = "COMPLETED", "Completed"
    FAILED = "FAILED", "Failed"


class RunFreshness(models.TextChoices):
    PENDING = "PENDING", "Pending"
    CURRENT = "CURRENT", "Current"
    STALE = "STALE", "Stale"


class ReconciliationRun(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    workspace = models.ForeignKey("workspaces.Workspace", on_delete=models.CASCADE, related_name="reconciliation_runs")
    scope = models.ForeignKey("books.ReconciliationScope", on_delete=models.CASCADE, related_name="runs")
    left_revision = models.ForeignKey("ingestion.DatasetRevision", on_delete=models.PROTECT, related_name="runs_as_left")
    right_revision = models.ForeignKey("ingestion.DatasetRevision", on_delete=models.PROTECT, related_name="runs_as_right")
    policy_revision = models.ForeignKey("books.PolicyRevision", on_delete=models.PROTECT, related_name="runs")
    manifest = models.JSONField()
    manifest_hash = models.CharField(max_length=64)
    data_generation = models.PositiveBigIntegerField()
    resolution_generation = models.PositiveBigIntegerField()
    scope_generation = models.PositiveBigIntegerField()
    engine_version = models.CharField(max_length=80)
    solver_version = models.CharField(max_length=100)
    lifecycle = models.CharField(max_length=10, choices=RunLifecycle.choices, default=RunLifecycle.FROZEN)
    freshness = models.CharField(max_length=8, choices=RunFreshness.choices, default=RunFreshness.PENDING)
    result_digest = models.CharField(max_length=64, null=True, blank=True)
    result_counts = models.JSONField(null=True, blank=True)
    failure_code = models.CharField(max_length=80, null=True, blank=True)
    created_at = models.DateTimeField()
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    objects = RunOwnedQuerySet.as_manager()

    class Meta:
        db_table = "reconciliation_run"
        constraints = [
            models.UniqueConstraint(fields=["scope", "manifest_hash"], name="run_scope_manifest_unique"),
            models.CheckConstraint(condition=models.Q(lifecycle__in=RunLifecycle.values), name="run_lifecycle_valid"),
            models.CheckConstraint(condition=models.Q(freshness__in=RunFreshness.values), name="run_freshness_valid"),
            models.CheckConstraint(condition=~models.Q(left_revision=models.F("right_revision")), name="run_revisions_distinct"),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        lifecycle=RunLifecycle.COMPLETED,
                        freshness__in=[RunFreshness.CURRENT, RunFreshness.STALE],
                        result_digest__isnull=False,
                        result_counts__isnull=False,
                        completed_at__isnull=False,
                        failure_code__isnull=True,
                    )
                    | models.Q(
                        lifecycle__in=[RunLifecycle.FROZEN, RunLifecycle.RUNNING],
                        freshness=RunFreshness.PENDING,
                        result_digest__isnull=True,
                        result_counts__isnull=True,
                        completed_at__isnull=True,
                        failure_code__isnull=True,
                    )
                    | models.Q(
                        lifecycle=RunLifecycle.FAILED,
                        freshness=RunFreshness.PENDING,
                        result_digest__isnull=True,
                        result_counts__isnull=True,
                        completed_at__isnull=True,
                        failure_code__isnull=False,
                    )
                ),
                name="run_state_shape_valid",
            ),
        ]
        indexes = [
            models.Index(fields=["workspace", "scope", "created_at"], name="run_workspace_scope_idx"),
            models.Index(fields=["workspace", "lifecycle"], name="run_workspace_state_idx"),
        ]

    def save(self, *args, **kwargs) -> None:
        if not self._state.adding:
            raise RunEvidenceError("run transitions must use the reconciliation service")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise RunEvidenceError("runs can be removed only through retention cleanup")


class RunInput(ImmutableRunModel):
    id = models.BigAutoField(primary_key=True)
    workspace = models.ForeignKey("workspaces.Workspace", on_delete=models.CASCADE, related_name="run_inputs")
    run = models.ForeignKey(ReconciliationRun, on_delete=models.CASCADE, related_name="inputs")
    side = models.CharField(max_length=5, choices=[(item.value, item.name.title()) for item in RecordSide])
    logical_transaction = models.ForeignKey("ingestion.LogicalTransaction", on_delete=models.PROTECT, related_name="run_inputs")
    observation = models.ForeignKey("ingestion.TransactionObservation", on_delete=models.PROTECT, related_name="run_inputs")

    objects = ImmutableRunQuerySet.as_manager()

    class Meta:
        db_table = "run_input"
        constraints = [
            models.UniqueConstraint(fields=["run", "logical_transaction"], name="run_input_logical_unique"),
            models.UniqueConstraint(fields=["run", "observation"], name="run_input_observation_unique"),
            models.CheckConstraint(condition=models.Q(side__in=[item.value for item in RecordSide]), name="run_input_side_valid"),
        ]


class RunDecisionInput(ImmutableRunModel):
    id = models.BigAutoField(primary_key=True)
    workspace = models.ForeignKey("workspaces.Workspace", on_delete=models.CASCADE, related_name="run_decision_inputs")
    run = models.ForeignKey(ReconciliationRun, on_delete=models.CASCADE, related_name="decision_inputs")
    decision_revision = models.ForeignKey("resolutions.DecisionRevision", on_delete=models.PROTECT, related_name="run_inputs")

    objects = ImmutableRunQuerySet.as_manager()

    class Meta:
        db_table = "run_decision_input"
        constraints = [models.UniqueConstraint(fields=["run", "decision_revision"], name="run_decision_input_unique")]


class AssignmentComponent(ImmutableRunModel):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    workspace = models.ForeignKey("workspaces.Workspace", on_delete=models.CASCADE, related_name="assignment_components")
    run = models.ForeignKey(ReconciliationRun, on_delete=models.CASCADE, related_name="components")
    component_key = models.CharField(max_length=64)
    graph_digest = models.CharField(max_length=64)
    solver_version = models.CharField(max_length=100)
    left_observation_ids = models.JSONField()
    right_observation_ids = models.JSONField()
    candidate_count = models.PositiveIntegerField()
    optimal_utility_bp = models.PositiveIntegerField()
    complete = models.BooleanField()
    limit_reason = models.CharField(max_length=80, null=True, blank=True)
    proposals = models.JSONField()

    objects = ImmutableRunQuerySet.as_manager()

    class Meta:
        db_table = "assignment_component"
        constraints = [
            models.UniqueConstraint(fields=["run", "component_key"], name="run_component_key_unique"),
            models.CheckConstraint(
                condition=(
                    models.Q(complete=True, limit_reason__isnull=True)
                    | models.Q(complete=False, limit_reason__isnull=False)
                ),
                name="component_limit_shape_valid",
            ),
        ]


class CandidateEvidence(ImmutableRunModel):
    id = models.BigAutoField(primary_key=True)
    workspace = models.ForeignKey("workspaces.Workspace", on_delete=models.CASCADE, related_name="candidate_evidence")
    run = models.ForeignKey(ReconciliationRun, on_delete=models.CASCADE, related_name="candidates")
    left_observation = models.ForeignKey("ingestion.TransactionObservation", on_delete=models.PROTECT, related_name="candidate_evidence_as_left")
    right_observation = models.ForeignKey("ingestion.TransactionObservation", on_delete=models.PROTECT, related_name="candidate_evidence_as_right")
    component = models.ForeignKey(AssignmentComponent, on_delete=models.PROTECT, null=True, blank=True, related_name="candidates")
    blocking_reasons = models.JSONField()
    features = models.JSONField()
    contradictions = models.JSONField()
    coverage_failures = models.JSONField()
    coverage_sufficient = models.BooleanField()
    complete_computation = models.BooleanField()
    score_bp = models.PositiveIntegerField()
    score_label = models.CharField(max_length=40)

    objects = ImmutableRunQuerySet.as_manager()

    class Meta:
        db_table = "candidate_evidence"
        constraints = [models.UniqueConstraint(fields=["run", "left_observation", "right_observation"], name="run_candidate_edge_unique")]


class RunPair(ImmutableRunModel):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    workspace = models.ForeignKey("workspaces.Workspace", on_delete=models.CASCADE, related_name="run_pairs")
    run = models.ForeignKey(ReconciliationRun, on_delete=models.CASCADE, related_name="pairs")
    left_observation = models.ForeignKey("ingestion.TransactionObservation", on_delete=models.PROTECT, related_name="run_pairs_as_left")
    right_observation = models.ForeignKey("ingestion.TransactionObservation", on_delete=models.PROTECT, related_name="run_pairs_as_right")
    left_logical = models.ForeignKey("ingestion.LogicalTransaction", on_delete=models.PROTECT, related_name="run_pairs_as_left")
    right_logical = models.ForeignKey("ingestion.LogicalTransaction", on_delete=models.PROTECT, related_name="run_pairs_as_right")
    origin = models.CharField(max_length=24, choices=[(item.value, item.name.title()) for item in PairOrigin])
    decision_revision = models.ForeignKey("resolutions.DecisionRevision", on_delete=models.PROTECT, null=True, blank=True, related_name="run_pairs")
    reference_value = models.CharField(max_length=240, null=True, blank=True)
    score_bp = models.PositiveIntegerField(null=True, blank=True)
    global_gap_bp = models.PositiveIntegerField(null=True, blank=True)
    explanation = models.TextField()

    objects = ImmutableRunQuerySet.as_manager()

    class Meta:
        db_table = "run_pair"
        constraints = [
            models.UniqueConstraint(fields=["run", "left_observation"], name="run_pair_left_unique"),
            models.UniqueConstraint(fields=["run", "right_observation"], name="run_pair_right_unique"),
            models.CheckConstraint(condition=models.Q(origin__in=[item.value for item in PairOrigin]), name="run_pair_origin_valid"),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        origin=PairOrigin.WEIGHTED_GLOBAL,
                        score_bp__isnull=False,
                        global_gap_bp__isnull=False,
                    )
                    | models.Q(
                        origin__in=[PairOrigin.MANUAL, PairOrigin.AUTHORITATIVE_REFERENCE],
                        score_bp__isnull=True,
                        global_gap_bp__isnull=True,
                    )
                ),
                name="run_pair_score_shape_valid",
            ),
        ]


class FieldComparison(ImmutableRunModel):
    id = models.BigAutoField(primary_key=True)
    workspace = models.ForeignKey("workspaces.Workspace", on_delete=models.CASCADE, related_name="field_comparisons")
    pair = models.ForeignKey(RunPair, on_delete=models.CASCADE, related_name="comparisons")
    field = models.CharField(max_length=80)
    status = models.CharField(max_length=20, choices=[(item.value, item.name.title()) for item in ComparisonStatus])
    left_value = models.JSONField(null=True)
    right_value = models.JSONField(null=True)
    signed_difference = models.JSONField(null=True)
    allowed_difference = models.JSONField(null=True)
    explanation = models.TextField()

    objects = ImmutableRunQuerySet.as_manager()

    class Meta:
        db_table = "field_comparison"
        constraints = [models.UniqueConstraint(fields=["pair", "field"], name="pair_comparison_field_unique")]


class RunUnpaired(ImmutableRunModel):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    workspace = models.ForeignKey("workspaces.Workspace", on_delete=models.CASCADE, related_name="run_unpaired")
    run = models.ForeignKey(ReconciliationRun, on_delete=models.CASCADE, related_name="unpaired")
    observation = models.ForeignKey("ingestion.TransactionObservation", on_delete=models.PROTECT, related_name="run_unpaired")
    logical_transaction = models.ForeignKey("ingestion.LogicalTransaction", on_delete=models.PROTECT, related_name="run_unpaired")
    side = models.CharField(max_length=5, choices=[(item.value, item.name.title()) for item in RecordSide])
    reason = models.CharField(max_length=32, choices=[(item.value, item.name.title()) for item in UnpairedReason])
    explanation = models.TextField()
    related_observation_ids = models.JSONField()

    objects = ImmutableRunQuerySet.as_manager()

    class Meta:
        db_table = "run_unpaired"
        constraints = [
            models.UniqueConstraint(fields=["run", "observation"], name="run_unpaired_observation_unique"),
            models.CheckConstraint(condition=models.Q(side__in=[item.value for item in RecordSide]), name="run_unpaired_side_valid"),
            models.CheckConstraint(condition=models.Q(reason__in=[item.value for item in UnpairedReason]), name="run_unpaired_reason_valid"),
        ]


class RunDiagnostic(ImmutableRunModel):
    id = models.BigAutoField(primary_key=True)
    workspace = models.ForeignKey("workspaces.Workspace", on_delete=models.CASCADE, related_name="run_diagnostics")
    run = models.ForeignKey(ReconciliationRun, on_delete=models.CASCADE, related_name="diagnostics")
    decision_revision = models.ForeignKey("resolutions.DecisionRevision", on_delete=models.PROTECT, null=True, blank=True, related_name="run_diagnostics")
    kind = models.CharField(max_length=32, choices=[(item.value, item.name.title()) for item in DiagnosticKind])
    record_observation = models.ForeignKey("ingestion.TransactionObservation", on_delete=models.PROTECT, related_name="diagnostics_as_record")
    candidate_observation = models.ForeignKey("ingestion.TransactionObservation", on_delete=models.PROTECT, null=True, blank=True, related_name="diagnostics_as_candidate")
    candidate_current_pair_observation = models.ForeignKey("ingestion.TransactionObservation", on_delete=models.PROTECT, null=True, blank=True, related_name="diagnostics_as_allocation")
    complete = models.BooleanField()
    explanation = models.TextField()

    objects = ImmutableRunQuerySet.as_manager()

    class Meta:
        db_table = "run_diagnostic"
        constraints = [
            models.UniqueConstraint(fields=["run", "record_observation", "candidate_observation", "kind"], name="run_diagnostic_unique"),
            models.CheckConstraint(condition=models.Q(kind__in=[item.value for item in DiagnosticKind]), name="run_diagnostic_kind_valid"),
        ]
