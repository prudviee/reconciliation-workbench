"""Append-only reviewer decisions and mutable active endpoint claims."""

from __future__ import annotations

from uuid import UUID, uuid4

from django.db import models

from books.models import ReconciliationBook
from ingestion.models import LogicalTransaction
from reconciliation.domain import (
    DecisionAction,
    DecisionAuthorityKind,
    RecordSide,
    WorkspaceId,
)
from workspaces.models import Workspace


class ResolutionEvidenceError(RuntimeError):
    """Append-only resolution evidence was mutated through the application ORM."""


class ResolutionOwnedQuerySet(models.QuerySet):
    def owned_by(self, workspace_id: WorkspaceId | UUID):
        value = (
            workspace_id.value
            if isinstance(workspace_id, WorkspaceId)
            else workspace_id
        )
        return self.filter(workspace_id=value)


class ImmutableResolutionQuerySet(ResolutionOwnedQuerySet):
    def update(self, **kwargs):
        raise ResolutionEvidenceError("resolution evidence is append-only")

    def delete(self):
        raise ResolutionEvidenceError(
            "resolution evidence can be removed only through retention cleanup"
        )


class ImmutableResolutionModel(models.Model):
    class Meta:
        abstract = True

    def save(self, *args, **kwargs) -> None:
        if not self._state.adding:
            raise ResolutionEvidenceError(
                f"{self.__class__.__name__} is append-only"
            )
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ResolutionEvidenceError(
            f"{self.__class__.__name__} can be removed only through retention cleanup"
        )


class Decision(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    workspace = models.ForeignKey(
        Workspace,
        on_delete=models.CASCADE,
        related_name="decisions",
    )
    book = models.ForeignKey(
        ReconciliationBook,
        on_delete=models.CASCADE,
        related_name="decisions",
    )
    current_revision = models.ForeignKey(
        "DecisionRevision",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="current_for_decision",
    )
    created_at = models.DateTimeField()

    objects = ResolutionOwnedQuerySet.as_manager()

    class Meta:
        db_table = "decision"
        indexes = [
            models.Index(
                fields=["workspace", "book", "created_at", "id"],
                name="decision_workspace_book_idx",
            )
        ]


class DecisionRevision(ImmutableResolutionModel):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    workspace = models.ForeignKey(
        Workspace,
        on_delete=models.CASCADE,
        related_name="decision_revisions",
    )
    decision = models.ForeignKey(
        Decision,
        on_delete=models.CASCADE,
        related_name="revisions",
    )
    predecessor = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="successor_revisions",
    )
    revision = models.PositiveIntegerField()
    action = models.CharField(
        max_length=18,
        choices=[(item.value, item.name.title()) for item in DecisionAction],
    )
    authority_kind = models.CharField(
        max_length=18,
        choices=[
            (item.value, item.name.title()) for item in DecisionAuthorityKind
        ],
        null=True,
        blank=True,
    )
    left_logical = models.ForeignKey(
        LogicalTransaction,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="decision_revisions_as_left",
    )
    right_logical = models.ForeignKey(
        LogicalTransaction,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="decision_revisions_as_right",
    )
    record_logical = models.ForeignKey(
        LogicalTransaction,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="decision_revisions_as_single",
    )
    record_side = models.CharField(
        max_length=5,
        choices=[(item.value, item.name.title()) for item in RecordSide],
        null=True,
        blank=True,
    )
    reason = models.TextField()
    actor = models.CharField(max_length=80)
    reviewed_observation_ids = models.JSONField(default=list)
    reviewed_evidence_digest = models.CharField(max_length=64, null=True, blank=True)
    created_at = models.DateTimeField()

    objects = ImmutableResolutionQuerySet.as_manager()

    class Meta:
        db_table = "decision_revision"
        constraints = [
            models.UniqueConstraint(
                fields=["decision", "revision"],
                name="decision_revision_number_unique",
            ),
            models.UniqueConstraint(
                fields=["predecessor"],
                condition=models.Q(predecessor__isnull=False),
                name="decision_predecessor_successor_unique",
            ),
            models.CheckConstraint(
                condition=models.Q(revision__gte=1),
                name="decision_revision_positive",
            ),
            models.CheckConstraint(
                condition=~models.Q(reason=""),
                name="decision_reason_nonempty",
            ),
            models.CheckConstraint(
                condition=~models.Q(actor=""),
                name="decision_actor_nonempty",
            ),
            models.CheckConstraint(
                condition=~models.Q(left_logical=models.F("right_logical")),
                name="decision_pair_endpoints_distinct",
            ),
            models.CheckConstraint(
                condition=models.Q(action__in=[item.value for item in DecisionAction]),
                name="decision_action_valid",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        authority_kind__in=[
                            DecisionAuthorityKind.LINK.value,
                            DecisionAuthorityKind.REJECT_CANDIDATE.value,
                        ],
                        left_logical__isnull=False,
                        right_logical__isnull=False,
                        record_logical__isnull=True,
                        record_side__isnull=True,
                    )
                    | models.Q(
                        authority_kind=DecisionAuthorityKind.ACCEPT_UNMATCHED.value,
                        left_logical__isnull=True,
                        right_logical__isnull=True,
                        record_logical__isnull=False,
                        record_side__in=[item.value for item in RecordSide],
                    )
                    | models.Q(
                        action=DecisionAction.REVOKE.value,
                        authority_kind__isnull=True,
                        left_logical__isnull=True,
                        right_logical__isnull=True,
                        record_logical__isnull=True,
                        record_side__isnull=True,
                    )
                ),
                name="decision_authority_shape_valid",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        action=DecisionAction.LINK.value,
                        authority_kind=DecisionAuthorityKind.LINK.value,
                    )
                    | models.Q(
                        action=DecisionAction.ACCEPT_UNMATCHED.value,
                        authority_kind=DecisionAuthorityKind.ACCEPT_UNMATCHED.value,
                    )
                    | models.Q(
                        action=DecisionAction.REJECT_CANDIDATE.value,
                        authority_kind=DecisionAuthorityKind.REJECT_CANDIDATE.value,
                    )
                    | models.Q(
                        action__in=[
                            DecisionAction.REAFFIRM.value,
                            DecisionAction.REPLACE.value,
                        ],
                        authority_kind__in=[item.value for item in DecisionAuthorityKind],
                    )
                    | models.Q(
                        action=DecisionAction.REVOKE.value,
                        authority_kind__isnull=True,
                    )
                ),
                name="decision_action_authority_valid",
            ),
        ]
        indexes = [
            models.Index(
                fields=["workspace", "decision", "revision"],
                name="rev_workspace_decision_idx",
            ),
            models.Index(
                fields=["workspace", "authority_kind"],
                name="revision_workspace_kind_idx",
            ),
        ]


class DecisionSupersession(ImmutableResolutionModel):
    id = models.BigAutoField(primary_key=True)
    workspace = models.ForeignKey(
        Workspace,
        on_delete=models.CASCADE,
        related_name="decision_supersessions",
    )
    replacement_revision = models.ForeignKey(
        DecisionRevision,
        on_delete=models.CASCADE,
        related_name="superseded_authorities",
    )
    superseded_revision = models.ForeignKey(
        DecisionRevision,
        on_delete=models.PROTECT,
        related_name="superseded_by",
    )
    created_at = models.DateTimeField()

    objects = ImmutableResolutionQuerySet.as_manager()

    class Meta:
        db_table = "decision_supersession"
        constraints = [
            models.UniqueConstraint(
                fields=["replacement_revision", "superseded_revision"],
                name="decision_supersession_unique",
            ),
            models.CheckConstraint(
                condition=~models.Q(
                    replacement_revision=models.F("superseded_revision")
                ),
                name="decision_supersession_not_self",
            ),
        ]
        indexes = [
            models.Index(
                fields=["workspace", "superseded_revision"],
                name="supersession_workspace_idx",
            )
        ]


class ActiveDecisionClaim(models.Model):
    id = models.BigAutoField(primary_key=True)
    workspace = models.ForeignKey(
        Workspace,
        on_delete=models.CASCADE,
        related_name="active_decision_claims",
    )
    book = models.ForeignKey(
        ReconciliationBook,
        on_delete=models.CASCADE,
        related_name="active_decision_claims",
    )
    logical_transaction = models.ForeignKey(
        LogicalTransaction,
        on_delete=models.PROTECT,
        related_name="active_decision_claims",
    )
    decision_revision = models.ForeignKey(
        DecisionRevision,
        on_delete=models.CASCADE,
        related_name="active_claims",
    )

    objects = ResolutionOwnedQuerySet.as_manager()

    class Meta:
        db_table = "active_decision_claim"
        constraints = [
            models.UniqueConstraint(
                fields=["book", "logical_transaction"],
                name="active_claim_book_logical_unique",
            ),
            models.UniqueConstraint(
                fields=["decision_revision", "logical_transaction"],
                name="active_claim_revision_logical_unique",
            ),
        ]
        indexes = [
            models.Index(
                fields=["workspace", "book", "decision_revision"],
                name="claim_workspace_book_idx",
            )
        ]
