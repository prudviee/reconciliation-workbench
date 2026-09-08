"""Workspace-scoped lookup and relationship validation for ingestion evidence."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from reconciliation.domain import CanonicalState, WorkspaceId
from sources.models import BookSource, SourceContractRevision

from .models import (
    AttemptState,
    Dataset,
    DatasetMembership,
    DatasetRevision,
    FileArtifact,
    IngestionAttempt,
    LogicalTransaction,
    RawRow,
    TransactionObservation,
)


class IngestionResourceUnavailable(LookupError):
    pass


@dataclass(frozen=True, slots=True)
class WorkspaceIngestionRepository:
    workspace_id: WorkspaceId

    def get_dataset(self, value: UUID) -> Dataset:
        return self._get(Dataset, value)

    def get_artifact(self, value: UUID) -> FileArtifact:
        return self._get(FileArtifact, value)

    def get_attempt(self, value: UUID) -> IngestionAttempt:
        return self._get(IngestionAttempt, value)

    def get_raw_row(self, value: UUID) -> RawRow:
        return self._get(RawRow, value)

    def get_logical_transaction(self, value: UUID) -> LogicalTransaction:
        return self._get(LogicalTransaction, value)

    def get_observation(self, value: UUID) -> TransactionObservation:
        return self._get(TransactionObservation, value)

    def get_revision(self, value: UUID) -> DatasetRevision:
        return self._get(DatasetRevision, value)

    def get_membership(self, value: int) -> DatasetMembership:
        return self._get(DatasetMembership, value)

    def list_eligible_memberships(
        self,
        revision_id: UUID,
    ) -> tuple[DatasetMembership, ...]:
        """Return the only ingestion evidence allowed into candidate generation."""
        revision = self.get_revision(revision_id)
        return tuple(
            DatasetMembership.objects.owned_by(self.workspace_id)
            .filter(
                dataset_revision=revision,
                observation__eligible_for_matching=True,
                observation__state=CanonicalState.SETTLED,
            )
            .select_related("logical_transaction", "observation")
            .order_by("logical_transaction__source_record_key")
        )

    def create_dataset(self, *, book_source_id: UUID, coverage_key: str, created_at) -> Dataset:
        try:
            book_source = BookSource.objects.owned_by(self.workspace_id).get(id=book_source_id)
        except BookSource.DoesNotExist as error:
            raise IngestionResourceUnavailable from error
        return Dataset.objects.create(
            workspace_id=self.workspace_id.value,
            book_source=book_source,
            coverage_key=coverage_key,
            created_at=created_at,
        )

    def create_artifact(
        self,
        *,
        storage_key: str,
        physical_hash: str,
        original_filename: str,
        content_type: str,
        byte_size: int,
        created_at: datetime,
    ) -> FileArtifact:
        return FileArtifact.objects.create(
            workspace_id=self.workspace_id.value,
            storage_key=storage_key,
            physical_hash=physical_hash,
            original_filename=original_filename,
            content_type=content_type,
            byte_size=byte_size,
            created_at=created_at,
        )

    def create_attempt(
        self,
        *,
        artifact_id: UUID,
        dataset_id: UUID,
        contract_revision_id: UUID,
        expected_base_id: UUID | None,
        state: AttemptState,
        physical_hash: str,
        semantic_hash: str | None,
        delimiter: str,
        row_count: int,
        error_count: int,
        created_at: datetime,
        completed_at: datetime | None,
        validation: list[dict[str, Any]] | None = None,
    ) -> IngestionAttempt:
        artifact = self.get_artifact(artifact_id)
        dataset = self.get_dataset(dataset_id)
        contract = self._get(SourceContractRevision, contract_revision_id)
        expected_base = (
            self.get_revision(expected_base_id) if expected_base_id is not None else None
        )
        if dataset.book_source.source_id != contract.source_id:
            raise IngestionResourceUnavailable
        if expected_base is not None and expected_base.dataset_id != dataset.id:
            raise IngestionResourceUnavailable
        return IngestionAttempt.objects.create(
            workspace_id=self.workspace_id.value,
            artifact=artifact,
            dataset=dataset,
            contract_revision=contract,
            expected_base=expected_base,
            state=state,
            physical_hash=physical_hash,
            semantic_hash=semantic_hash,
            delimiter=delimiter,
            row_count=row_count,
            error_count=error_count,
            validation=validation or [],
            created_at=created_at,
            completed_at=completed_at,
        )

    def complete_attempt(
        self,
        attempt_id: UUID,
        *,
        state: AttemptState,
        semantic_hash: str | None,
        row_count: int,
        error_count: int,
        completed_at: datetime,
        validation: list[dict[str, Any]] | None = None,
    ) -> IngestionAttempt:
        attempt = self.get_attempt(attempt_id)
        IngestionAttempt.objects.owned_by(self.workspace_id).filter(id=attempt.id).update(
            state=state,
            semantic_hash=semantic_hash,
            row_count=row_count,
            error_count=error_count,
            completed_at=completed_at,
            validation=validation or [],
        )
        attempt.refresh_from_db()
        return attempt

    def create_raw_row(
        self,
        *,
        attempt_id: UUID,
        row_number: int,
        raw_values: dict[str, Any] | list[dict[str, Any]],
        canonical_preview: dict[str, Any] | None,
        validation: list[dict[str, Any]],
    ) -> RawRow:
        attempt = self.get_attempt(attempt_id)
        return RawRow.objects.create(
            workspace_id=self.workspace_id.value,
            attempt=attempt,
            row_number=row_number,
            raw_values=raw_values,
            canonical_preview=canonical_preview,
            validation=validation,
        )

    def create_raw_rows(
        self,
        *,
        attempt_id: UUID,
        rows: Iterable[dict[str, Any]],
    ) -> list[RawRow]:
        attempt = self.get_attempt(attempt_id)
        values = [
            RawRow(
                workspace_id=self.workspace_id.value,
                attempt=attempt,
                row_number=row["row_number"],
                raw_values=row["raw_values"],
                canonical_preview=row["canonical_preview"],
                validation=row["validation"],
            )
            for row in rows
        ]
        return RawRow.objects.bulk_create(values, batch_size=500)

    def create_logical_transaction(
        self,
        *,
        book_source_id: UUID,
        source_record_key: str,
        created_at: datetime,
    ) -> LogicalTransaction:
        book_source = self._get(BookSource, book_source_id)
        return LogicalTransaction.objects.create(
            workspace_id=self.workspace_id.value,
            book_source=book_source,
            source_record_key=source_record_key,
            created_at=created_at,
        )

    def create_observation(
        self,
        *,
        logical_transaction_id: UUID,
        raw_row_id: UUID,
        business_reference: str | None,
        executed_at_utc: datetime,
        instrument: str,
        side: str,
        quantity: Decimal,
        unit_price: Decimal,
        gross_amount: Decimal,
        currency: str,
        state: str,
        eligible_for_matching: bool,
        provenance: dict[str, Any] | list[dict[str, Any]],
        fingerprint: str,
        created_at: datetime,
    ) -> TransactionObservation:
        logical = self.get_logical_transaction(logical_transaction_id)
        raw_row = self.get_raw_row(raw_row_id)
        if raw_row.attempt.dataset.book_source_id != logical.book_source_id:
            raise IngestionResourceUnavailable
        return TransactionObservation.objects.create(
            workspace_id=self.workspace_id.value,
            logical_transaction=logical,
            raw_row=raw_row,
            business_reference=business_reference,
            executed_at_utc=executed_at_utc,
            instrument=instrument,
            side=side,
            quantity=quantity,
            unit_price=unit_price,
            gross_amount=gross_amount,
            currency=currency,
            state=state,
            eligible_for_matching=eligible_for_matching,
            provenance=provenance,
            fingerprint=fingerprint,
            created_at=created_at,
        )

    def create_revision(
        self,
        *,
        dataset_id: UUID,
        attempt_id: UUID,
        parent_revision_id: UUID | None,
        state_hash: str,
        created_at: datetime,
    ) -> DatasetRevision:
        dataset = self.get_dataset(dataset_id)
        attempt = self.get_attempt(attempt_id)
        parent = (
            self.get_revision(parent_revision_id)
            if parent_revision_id is not None
            else None
        )
        if attempt.dataset_id != dataset.id:
            raise IngestionResourceUnavailable
        if parent is not None and parent.dataset_id != dataset.id:
            raise IngestionResourceUnavailable
        return DatasetRevision.objects.create(
            workspace_id=self.workspace_id.value,
            dataset=dataset,
            parent_revision=parent,
            attempt=attempt,
            state_hash=state_hash,
            created_at=created_at,
        )

    def create_membership(
        self,
        *,
        revision_id: UUID,
        logical_transaction_id: UUID,
        observation_id: UUID,
    ) -> DatasetMembership:
        revision = self.get_revision(revision_id)
        logical = self.get_logical_transaction(logical_transaction_id)
        observation = self.get_observation(observation_id)
        if (
            observation.logical_transaction_id != logical.id
            or revision.dataset.book_source_id != logical.book_source_id
        ):
            raise IngestionResourceUnavailable
        return DatasetMembership.objects.create(
            workspace_id=self.workspace_id.value,
            dataset_revision=revision,
            logical_transaction=logical,
            observation=observation,
        )

    def create_memberships(
        self,
        *,
        revision_id: UUID,
        members: Iterable[tuple[UUID, UUID]],
    ) -> list[DatasetMembership]:
        revision = self.get_revision(revision_id)
        member_values = tuple(members)
        logical_ids = {logical_id for logical_id, _ in member_values}
        observation_ids = {observation_id for _, observation_id in member_values}
        logicals = {
            value.id: value
            for value in LogicalTransaction.objects.owned_by(self.workspace_id).filter(
                id__in=logical_ids
            )
        }
        observations = {
            value.id: value
            for value in TransactionObservation.objects.owned_by(
                self.workspace_id
            ).filter(id__in=observation_ids)
        }
        if set(logicals) != logical_ids or set(observations) != observation_ids:
            raise IngestionResourceUnavailable
        values = []
        for logical_id, observation_id in member_values:
            logical = logicals[logical_id]
            observation = observations[observation_id]
            if (
                observation.logical_transaction_id != logical.id
                or revision.dataset.book_source_id != logical.book_source_id
            ):
                raise IngestionResourceUnavailable
            values.append(
                DatasetMembership(
                    workspace_id=self.workspace_id.value,
                    dataset_revision=revision,
                    logical_transaction=logical,
                    observation=observation,
                )
            )
        return DatasetMembership.objects.bulk_create(values, batch_size=500)

    def _get(self, model, public_id):
        try:
            return model.objects.owned_by(self.workspace_id).get(id=public_id)
        except model.DoesNotExist as error:
            raise IngestionResourceUnavailable from error
