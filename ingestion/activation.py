"""Atomic full-snapshot and explicit-delta publication."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from django.db import transaction
from django.utils import timezone

from reconciliation.domain import (
    DatasetMode,
    IngestionOperation,
    WorkspaceId,
    observation_fingerprint,
    resolved_state_hash,
)
from sources.adapters import contract_from_payload
from workspaces.lifecycle import WorkspaceLifecycleService
from workspaces.models import Workspace
from workspaces.repositories import WorkspaceRepository, WorkspaceUnavailable
from books.models import ReconciliationBook
from books.scopes import mark_dataset_activation

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


class InvalidRestoreReason(ActivationError):
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
        restore_reason: str | None = None,
    ) -> DatasetRevision | None:
        normalized_reason = self._restore_reason(restore_reason)
        workspace = WorkspaceRepository().get(workspace_id)
        self.lifecycle_service.require_active(workspace, now=self.clock())
        with transaction.atomic():
            workspace = self._locked_workspace(workspace_id)
            self.lifecycle_service.require_active(workspace, now=self.clock())
            attempt = self._locked_attempt(workspace_id, attempt_id)
            if attempt.state != AttemptState.READY:
                raise AttemptNotReady
            self._locked_book(
                workspace_id,
                attempt.dataset.book_source.book_id,
            )
            dataset = self._locked_dataset(workspace_id, attempt.dataset_id)
            if dataset.current_revision_id != attempt.expected_base_id:
                raise StalePreview
            contract = contract_from_payload(attempt.contract_revision.contract)
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
            prepared = []
            resolved_members: dict[
                str,
                tuple[LogicalTransaction | None, TransactionObservation | None, str],
            ] = {}
            if contract.mode is DatasetMode.DELTA and attempt.expected_base_id is not None:
                base_memberships = (
                    attempt.expected_base.memberships.select_related(
                        "logical_transaction",
                        "observation",
                    )
                    .order_by("logical_transaction__source_record_key")
                )
                for membership in base_memberships:
                    resolved_members[
                        membership.logical_transaction.source_record_key
                    ] = (
                        membership.logical_transaction,
                        membership.observation,
                        membership.observation.fingerprint,
                    )
            source_keys: set[str] = set()
            for raw_row in rows:
                if raw_row.validation:
                    raise InvalidPreviewEvidence("preview contains row errors")
                preview = raw_row.canonical_preview
                if not isinstance(preview, dict) or preview.get("complete") is not True:
                    raise InvalidPreviewEvidence("preview contains incomplete canonical evidence")
                source_key = preview.get("source_record_key")
                try:
                    operation = IngestionOperation(preview.get("operation"))
                except (TypeError, ValueError) as error:
                    raise InvalidPreviewEvidence("preview contains an invalid operation") from error
                if not isinstance(source_key, str) or not source_key.strip():
                    raise InvalidPreviewEvidence("preview contains an invalid source key")
                if int(preview.get("row_number", 0)) != raw_row.row_number:
                    raise InvalidPreviewEvidence("preview row number is inconsistent")
                if source_key in source_keys:
                    raise InvalidPreviewEvidence("preview contains duplicate source keys")
                source_keys.add(source_key)

                if contract.mode is DatasetMode.FULL_SNAPSHOT:
                    if operation is not IngestionOperation.SNAPSHOT:
                        raise InvalidPreviewEvidence("full snapshot contains a delta operation")
                elif operation is IngestionOperation.SNAPSHOT:
                    raise InvalidPreviewEvidence("delta contains a snapshot operation")

                if operation is IngestionOperation.RETRACT:
                    resolved_members.pop(source_key, None)
                    prepared.append((raw_row, None, None))
                    continue
                try:
                    canonical = canonical_from_payload(preview)
                except (TypeError, ValueError) as error:
                    raise InvalidPreviewEvidence(
                        "preview contains incomplete canonical evidence"
                    ) from error
                fingerprint = observation_fingerprint(
                    contract_digest=attempt.contract_revision.digest,
                    row=canonical,
                )
                prepared.append((raw_row, canonical, fingerprint))
                resolved_members[source_key] = (None, None, fingerprint)

            proposed_state_hash = resolved_state_hash(
                (source_key, member[2])
                for source_key, member in resolved_members.items()
            )
            if (
                dataset.current_revision is not None
                and dataset.current_revision.state_hash == proposed_state_hash
            ):
                self._finish_without_revision(attempt, AttemptState.NO_CHANGE)
                return None
            historical_replay = DatasetRevision.objects.owned_by(workspace_id).filter(
                dataset=dataset,
                state_hash=proposed_state_hash,
            ).exists()
            if historical_replay and normalized_reason is None:
                self._finish_without_revision(attempt, AttemptState.REPLAYED)
                return None

            observation_rows = [
                item for item in prepared if item[1] is not None
            ]
            observation_keys = {
                canonical.source_record_key
                for _, canonical, _ in observation_rows
            }
            logicals = {
                value.source_record_key: value
                for value in LogicalTransaction.objects.owned_by(workspace_id).filter(
                    book_source=dataset.book_source,
                    source_record_key__in=observation_keys,
                )
            }
            missing_keys = observation_keys - set(logicals)
            if missing_keys:
                LogicalTransaction.objects.bulk_create(
                    [
                        LogicalTransaction(
                            workspace_id=workspace_id.value,
                            book_source=dataset.book_source,
                            source_record_key=source_key,
                            created_at=self.clock(),
                        )
                        for source_key in sorted(missing_keys)
                    ],
                    batch_size=500,
                    ignore_conflicts=True,
                )
                logicals = {
                    value.source_record_key: value
                    for value in LogicalTransaction.objects.owned_by(workspace_id).filter(
                        book_source=dataset.book_source,
                        source_record_key__in=observation_keys,
                    )
                }
            if set(logicals) != observation_keys:
                raise InvalidPreviewEvidence("logical identities could not be materialized")

            new_observations = [
                TransactionObservation(
                    workspace_id=workspace_id.value,
                    logical_transaction=logicals[canonical.source_record_key],
                    raw_row=raw_row,
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
                for raw_row, canonical, fingerprint in observation_rows
            ]
            TransactionObservation.objects.bulk_create(
                new_observations,
                batch_size=500,
            )
            newly_observed = {
                observation.logical_transaction.source_record_key: (
                    observation.logical_transaction,
                    observation,
                    observation.fingerprint,
                )
                for observation in new_observations
            }

            resolved_members.update(newly_observed)

            revision = repository.create_revision(
                dataset_id=dataset.id,
                attempt_id=attempt.id,
                parent_revision_id=attempt.expected_base_id,
                state_hash=proposed_state_hash,
                created_at=self.clock(),
            )
            repository.create_memberships(
                revision_id=revision.id,
                members=(
                    (logical.id, observation.id)
                    for logical, observation, _ in resolved_members.values()
                    if logical is not None and observation is not None
                ),
            )
            attempt.state = AttemptState.ACTIVATED
            attempt.completed_at = self.clock()
            attempt.activation_reason = normalized_reason
            attempt.save(
                update_fields=["state", "completed_at", "activation_reason"]
            )
            dataset.current_revision = revision
            dataset.save(update_fields=["current_revision"])
            mark_dataset_activation(
                workspace_id=workspace_id,
                book_id=dataset.book_source.book_id,
                dataset_id=dataset.id,
            )
            return revision

    def _finish_without_revision(
        self,
        attempt: IngestionAttempt,
        state: AttemptState,
    ) -> None:
        attempt.state = state
        attempt.completed_at = self.clock()
        attempt.save(update_fields=["state", "completed_at"])

    @staticmethod
    def _restore_reason(value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise InvalidRestoreReason("restore reason must not be blank")
        if len(normalized) > 1_000:
            raise InvalidRestoreReason("restore reason must be at most 1000 characters")
        return normalized

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

    @staticmethod
    def _locked_book(
        workspace_id: WorkspaceId,
        book_id: UUID,
    ) -> ReconciliationBook:
        try:
            return (
                ReconciliationBook.objects.owned_by(workspace_id)
                .select_for_update()
                .get(id=book_id)
            )
        except ReconciliationBook.DoesNotExist as error:
            raise IngestionResourceUnavailable from error
