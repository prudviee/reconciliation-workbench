"""Atomic full-snapshot publication from retained preview evidence."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from django.db import transaction
from django.utils import timezone

from reconciliation.domain import (
    DatasetMode,
    WorkspaceId,
    observation_fingerprint,
    resolved_state_hash,
)
from sources.adapters import contract_from_payload
from workspaces.lifecycle import WorkspaceLifecycleService
from workspaces.models import Workspace
from workspaces.repositories import WorkspaceRepository, WorkspaceUnavailable

from .models import (
    AttemptState,
    Dataset,
    DatasetRevision,
    IngestionAttempt,
    LogicalTransaction,
    RawRow,
    TransactionObservation,
)
from .preview import canonical_from_payload
from .repositories import (
    IngestionResourceUnavailable,
    WorkspaceIngestionRepository,
)


class ActivationError(RuntimeError):
    pass


class AttemptNotReady(ActivationError):
    pass


class StalePreview(ActivationError):
    pass


class InvalidPreviewEvidence(ActivationError):
    pass


@dataclass(slots=True)
class FullSnapshotActivationService:
    clock: Callable[[], datetime] = timezone.now
    lifecycle_service: WorkspaceLifecycleService = field(
        default_factory=WorkspaceLifecycleService
    )

    def activate(
        self,
        workspace_id: WorkspaceId,
        *,
        attempt_id: UUID,
    ) -> DatasetRevision:
        workspace = WorkspaceRepository().get(workspace_id)
        self.lifecycle_service.require_active(workspace, now=self.clock())
        with transaction.atomic():
            workspace = self._locked_workspace(workspace_id)
            self.lifecycle_service.require_active(workspace, now=self.clock())
            attempt = self._locked_attempt(workspace_id, attempt_id)
            if attempt.state != AttemptState.READY:
                raise AttemptNotReady
            dataset = self._locked_dataset(workspace_id, attempt.dataset_id)
            if dataset.current_revision_id != attempt.expected_base_id:
                raise StalePreview
            contract = contract_from_payload(attempt.contract_revision.contract)
            if contract.mode is not DatasetMode.FULL_SNAPSHOT:
                raise InvalidPreviewEvidence("attempt is not a full snapshot")

            rows = list(
                RawRow.objects.owned_by(workspace_id)
                .filter(attempt=attempt)
                .order_by("row_number")
            )
            if (
                len(rows) != attempt.row_count
                or attempt.error_count != 0
                or attempt.validation
            ):
                raise InvalidPreviewEvidence("preview row counts are inconsistent")

            repository = WorkspaceIngestionRepository(workspace_id)
            members: list[tuple[LogicalTransaction, TransactionObservation]] = []
            state_members: list[tuple[str, str]] = []
            source_keys: set[str] = set()
            for raw_row in rows:
                if raw_row.validation:
                    raise InvalidPreviewEvidence("preview contains row errors")
                try:
                    canonical = canonical_from_payload(raw_row.canonical_preview)
                except (TypeError, ValueError) as error:
                    raise InvalidPreviewEvidence(
                        "preview contains incomplete canonical evidence"
                    ) from error
                if canonical.row_number != raw_row.row_number:
                    raise InvalidPreviewEvidence("preview row number is inconsistent")
                if canonical.source_record_key in source_keys:
                    raise InvalidPreviewEvidence("preview contains duplicate source keys")
                source_keys.add(canonical.source_record_key)
                logical, _ = LogicalTransaction.objects.get_or_create(
                    workspace_id=workspace_id.value,
                    book_source=dataset.book_source,
                    source_record_key=canonical.source_record_key,
                    defaults={"created_at": self.clock()},
                )
                fingerprint = observation_fingerprint(
                    contract_digest=attempt.contract_revision.digest,
                    row=canonical,
                )
                observation = repository.create_observation(
                    logical_transaction_id=logical.id,
                    raw_row_id=raw_row.id,
                    business_reference=canonical.business_reference,
                    executed_at_utc=canonical.executed_at_utc,
                    instrument=canonical.instrument,
                    side=canonical.side,
                    quantity=canonical.quantity,
                    unit_price=canonical.unit_price,
                    gross_amount=canonical.gross_amount,
                    currency=canonical.currency,
                    state=canonical.state,
                    eligible_for_matching=canonical.eligible_for_matching,
                    provenance=raw_row.canonical_preview["provenance"],
                    fingerprint=fingerprint,
                    created_at=self.clock(),
                )
                members.append((logical, observation))
                state_members.append((canonical.source_record_key, fingerprint))

            revision = repository.create_revision(
                dataset_id=dataset.id,
                attempt_id=attempt.id,
                parent_revision_id=attempt.expected_base_id,
                state_hash=resolved_state_hash(state_members),
                created_at=self.clock(),
            )
            repository.create_memberships(
                revision_id=revision.id,
                members=(
                    (logical.id, observation.id)
                    for logical, observation in members
                ),
            )
            attempt.state = AttemptState.ACTIVATED
            attempt.completed_at = self.clock()
            attempt.save(update_fields=["state", "completed_at"])
            dataset.current_revision = revision
            dataset.save(update_fields=["current_revision"])
            return revision

    @staticmethod
    def _locked_workspace(workspace_id: WorkspaceId) -> Workspace:
        try:
            return Workspace.objects.select_for_update().get(id=workspace_id.value)
        except Workspace.DoesNotExist as error:
            raise WorkspaceUnavailable from error

    @staticmethod
    def _locked_attempt(
        workspace_id: WorkspaceId,
        attempt_id: UUID,
    ) -> IngestionAttempt:
        try:
            return (
                IngestionAttempt.objects.owned_by(workspace_id)
                .select_for_update()
                .select_related(
                    "contract_revision",
                    "dataset__book_source",
                )
                .get(id=attempt_id)
            )
        except IngestionAttempt.DoesNotExist as error:
            raise IngestionResourceUnavailable from error

    @staticmethod
    def _locked_dataset(
        workspace_id: WorkspaceId,
        dataset_id: UUID,
    ) -> Dataset:
        try:
            return (
                Dataset.objects.owned_by(workspace_id)
                .select_for_update()
                .select_related("book_source")
                .get(id=dataset_id)
            )
        except Dataset.DoesNotExist as error:
            raise IngestionResourceUnavailable from error
