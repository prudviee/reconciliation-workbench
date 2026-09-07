"""Stable investigation identities, immutable occurrences, and current scope views."""

from __future__ import annotations

from uuid import UUID, uuid4

from django.db import models

from reconciliation.domain import CaseKind, CaseResultKind, DecisionHealth, RecordSide, WorkspaceId


class CaseEvidenceError(RuntimeError):
    pass


class CaseOwnedQuerySet(models.QuerySet):
    def owned_by(self, workspace_id: WorkspaceId | UUID):
        value = workspace_id.value if isinstance(workspace_id, WorkspaceId) else workspace_id
        return self.filter(workspace_id=value)


class ImmutableCaseQuerySet(CaseOwnedQuerySet):
    def update(self, **kwargs):
        raise CaseEvidenceError("immutable case evidence cannot be updated")

    def delete(self):
        raise CaseEvidenceError("immutable case evidence requires retention cleanup")


class ImmutableCaseModel(models.Model):
    class Meta:
        abstract = True

    def save(self, *args, **kwargs) -> None:
        if not self._state.adding:
            raise CaseEvidenceError(f"{self.__class__.__name__} is immutable")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise CaseEvidenceError(f"{self.__class__.__name__} is immutable")


class InvestigationCase(ImmutableCaseModel):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    workspace = models.ForeignKey("workspaces.Workspace", on_delete=models.CASCADE, related_name="investigation_cases")
    book = models.ForeignKey("books.ReconciliationBook", on_delete=models.CASCADE, related_name="investigation_cases")
    kind = models.CharField(max_length=10, choices=[(item.value, item.name.title()) for item in CaseKind])
    stable_key = models.CharField(max_length=80)
    digest = models.CharField(max_length=64)
    left_logical = models.ForeignKey("ingestion.LogicalTransaction", on_delete=models.PROTECT, null=True, blank=True, related_name="pair_cases_as_left")
    right_logical = models.ForeignKey("ingestion.LogicalTransaction", on_delete=models.PROTECT, null=True, blank=True, related_name="pair_cases_as_right")
    record_logical = models.ForeignKey("ingestion.LogicalTransaction", on_delete=models.PROTECT, null=True, blank=True, related_name="unpaired_cases")
    record_side = models.CharField(max_length=5, choices=[(item.value, item.name.title()) for item in RecordSide], null=True, blank=True)
    ambiguity_left_logical_ids = models.JSONField(null=True, blank=True)
    ambiguity_right_logical_ids = models.JSONField(null=True, blank=True)
    ambiguity_scope = models.ForeignKey("books.ReconciliationScope", on_delete=models.CASCADE, null=True, blank=True, related_name="ambiguity_cases")
    policy_digest = models.CharField(max_length=64, null=True, blank=True)
    created_at = models.DateTimeField()

    objects = ImmutableCaseQuerySet.as_manager()

    class Meta:
        db_table = "investigation_case"
        constraints = [
            models.UniqueConstraint(fields=["book", "stable_key"], name="case_book_stable_key_unique"),
            models.CheckConstraint(condition=models.Q(kind__in=[item.value for item in CaseKind]), name="case_kind_valid"),
            models.CheckConstraint(
                condition=(
                    models.Q(kind=CaseKind.PAIR, left_logical__isnull=False, right_logical__isnull=False, record_logical__isnull=True, record_side__isnull=True, ambiguity_scope__isnull=True, policy_digest__isnull=True)
                    | models.Q(kind=CaseKind.UNPAIRED, left_logical__isnull=True, right_logical__isnull=True, record_logical__isnull=False, record_side__in=[item.value for item in RecordSide], ambiguity_scope__isnull=True, policy_digest__isnull=True)
                    | models.Q(kind=CaseKind.AMBIGUITY, left_logical__isnull=True, right_logical__isnull=True, record_logical__isnull=True, record_side__isnull=True, ambiguity_scope__isnull=False, policy_digest__isnull=False)
                ),
                name="case_identity_shape_valid",
            ),
        ]
        indexes = [models.Index(fields=["workspace", "book", "kind", "created_at"], name="case_workspace_book_idx")]


class CaseOccurrence(ImmutableCaseModel):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    workspace = models.ForeignKey("workspaces.Workspace", on_delete=models.CASCADE, related_name="case_occurrences")
    case = models.ForeignKey(InvestigationCase, on_delete=models.CASCADE, related_name="occurrences")
    run = models.ForeignKey("reconciliation.ReconciliationRun", on_delete=models.CASCADE, related_name="case_occurrences")
    result_kind = models.CharField(max_length=10, choices=[(item.value, item.name.title()) for item in CaseResultKind])
    pair = models.ForeignKey("reconciliation.RunPair", on_delete=models.CASCADE, null=True, blank=True, related_name="case_occurrences")
    unpaired = models.ForeignKey("reconciliation.RunUnpaired", on_delete=models.CASCADE, null=True, blank=True, related_name="case_occurrences")
    component = models.ForeignKey("reconciliation.AssignmentComponent", on_delete=models.CASCADE, null=True, blank=True, related_name="case_occurrences")
    state_snapshot = models.JSONField()
    created_at = models.DateTimeField()

    objects = ImmutableCaseQuerySet.as_manager()

    class Meta:
        db_table = "case_occurrence"
        constraints = [
            models.UniqueConstraint(fields=["case", "run"], name="case_run_occurrence_unique"),
            models.CheckConstraint(
                condition=(
                    models.Q(result_kind=CaseResultKind.PAIR, pair__isnull=False, unpaired__isnull=True, component__isnull=True)
                    | models.Q(result_kind=CaseResultKind.UNPAIRED, pair__isnull=True, unpaired__isnull=False, component__isnull=True)
                    | models.Q(result_kind=CaseResultKind.AMBIGUITY, pair__isnull=True, unpaired__isnull=True, component__isnull=False)
                ),
                name="occurrence_result_shape_valid",
            ),
        ]
        indexes = [models.Index(fields=["workspace", "case", "created_at"], name="occurrence_case_idx")]


class CaseScopeProjection(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    workspace = models.ForeignKey("workspaces.Workspace", on_delete=models.CASCADE, related_name="case_scope_projections")
    case = models.ForeignKey(InvestigationCase, on_delete=models.CASCADE, related_name="scope_projections")
    scope = models.ForeignKey("books.ReconciliationScope", on_delete=models.CASCADE, related_name="case_projections")
    current_occurrence = models.OneToOneField(CaseOccurrence, on_delete=models.CASCADE, related_name="current_projection")
    run = models.ForeignKey("reconciliation.ReconciliationRun", on_delete=models.CASCADE, related_name="case_projections")
    review_health = models.CharField(max_length=20, choices=[(item.value, item.name.title()) for item in DecisionHealth], null=True, blank=True)
    attention = models.JSONField(default=list)
    applied_data_generation = models.PositiveBigIntegerField()
    applied_resolution_generation = models.PositiveBigIntegerField()
    updated_at = models.DateTimeField()

    objects = CaseOwnedQuerySet.as_manager()

    class Meta:
        db_table = "case_scope_projection"
        constraints = [models.UniqueConstraint(fields=["case", "scope"], name="case_scope_projection_unique")]
        indexes = [models.Index(fields=["workspace", "scope", "review_health"], name="case_projection_scope_idx")]
