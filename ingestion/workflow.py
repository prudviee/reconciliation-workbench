"""Workspace-scoped preparation of reusable source contracts and datasets."""

from __future__ import annotations

from dataclasses import dataclass

from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from books.repositories import WorkspaceBookRepository
from reconciliation.domain import (
    BookId,
    SourceContract,
    WorkspaceId,
    mapping_revision_digest,
    source_contract_digest,
)
from sources.adapters import contract_to_payload
from sources.models import BookSource, MappingRevision, SourceContractRevision, SourceRole
from sources.repositories import WorkspaceSourceRepository

from .models import Dataset
from .repositories import WorkspaceIngestionRepository


@dataclass(frozen=True, slots=True)
class PreparedSource:
    book_source: BookSource
    contract_revision: SourceContractRevision
    dataset: Dataset


@dataclass(frozen=True, slots=True)
class SourcePreparationService:
    workspace_id: WorkspaceId

    def prepare(
        self,
        *,
        book_id: BookId,
        role: SourceRole,
        contract: SourceContract,
    ) -> PreparedSource:
        book = WorkspaceBookRepository(self.workspace_id).get(book_id)
        source_repository = WorkspaceSourceRepository(self.workspace_id)
        ingestion_repository = WorkspaceIngestionRepository(self.workspace_id)
        now = timezone.now()
        payload = contract_to_payload(contract)
        digest = source_contract_digest(payload)
        mapping_payload = {"bindings": payload["bindings"]}
        mapping_digest = mapping_revision_digest(mapping_payload)

        with transaction.atomic():
            existing = (
                BookSource.objects.owned_by(self.workspace_id)
                .select_for_update()
                .select_related("source")
                .filter(book=book, role=role)
                .first()
            )
            if existing is None:
                source = source_repository.create_source(
                    name="Internal ledger" if role == SourceRole.LEFT else "Counterparty",
                    adapter_key=contract.adapter_key,
                    created_at=now,
                )
                book_source = source_repository.assign_book_source(
                    book_id=book_id,
                    source_id=source.id,
                    role=role,
                    identity_namespace=contract.identity_namespace,
                    created_at=now,
                )
            else:
                book_source = existing
                source = existing.source

            reusable = (
                SourceContractRevision.objects.owned_by(self.workspace_id)
                .filter(source=source, digest=digest)
                .order_by("-revision")
                .first()
            )
            if reusable is None:
                next_mapping = (
                    MappingRevision.objects.owned_by(self.workspace_id)
                    .filter(source=source)
                    .aggregate(value=Max("revision"))["value"]
                    or 0
                ) + 1
                mapping = source_repository.create_mapping_revision(
                    source_id=source.id,
                    revision=next_mapping,
                    mapping=mapping_payload,
                    parser_version=contract.parser_version,
                    digest=mapping_digest,
                    created_at=now,
                )
                next_contract = (
                    SourceContractRevision.objects.owned_by(self.workspace_id)
                    .filter(source=source)
                    .aggregate(value=Max("revision"))["value"]
                    or 0
                ) + 1
                reusable = source_repository.create_contract_revision(
                    source_id=source.id,
                    mapping_revision_id=mapping.id,
                    revision=next_contract,
                    mode=contract.mode,
                    timezone_name=contract.timezone_name,
                    identity_namespace=contract.identity_namespace,
                    reference_semantics=contract.reference_semantics,
                    contract=payload,
                    digest=digest,
                    created_at=now,
                )

            dataset = (
                Dataset.objects.owned_by(self.workspace_id)
                .filter(book_source=book_source, coverage_key="default")
                .first()
            )
            if dataset is None:
                dataset = ingestion_repository.create_dataset(
                    book_source_id=book_source.id,
                    coverage_key="default",
                    created_at=now,
                )
        return PreparedSource(book_source, reusable, dataset)
