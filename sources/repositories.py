"""Workspace-scoped source persistence boundaries."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from books.models import ReconciliationBook
from reconciliation.domain import (
    BookId,
    DatasetMode,
    ReferenceSemantics,
    WorkspaceId,
)

from .models import BookSource, MappingRevision, SourceContractRevision, SourceSystem


class SourceUnavailable(LookupError):
    pass


@dataclass(frozen=True, slots=True)
class WorkspaceSourceRepository:
    workspace_id: WorkspaceId

    def create_source(
        self,
        *,
        name: str,
        adapter_key: str,
        created_at: datetime,
    ) -> SourceSystem:
        return SourceSystem.objects.create(
            workspace_id=self.workspace_id.value,
            name=name,
            adapter_key=adapter_key,
            created_at=created_at,
        )

    def get_source(self, source_id: UUID) -> SourceSystem:
        return self._get(SourceSystem, source_id)

    def get_book_source(self, book_source_id: UUID) -> BookSource:
        return self._get(BookSource, book_source_id)

    def get_mapping(self, mapping_id: UUID) -> MappingRevision:
        return self._get(MappingRevision, mapping_id)

    def get_contract(self, contract_id: UUID) -> SourceContractRevision:
        return self._get(SourceContractRevision, contract_id)

    def assign_book_source(
        self,
        *,
        book_id: BookId,
        source_id: UUID,
        role: str,
        identity_namespace: str,
        created_at,
    ) -> BookSource:
        try:
            book = ReconciliationBook.objects.owned_by(self.workspace_id).get(id=book_id.value)
            source = SourceSystem.objects.owned_by(self.workspace_id).get(id=source_id)
        except (ReconciliationBook.DoesNotExist, SourceSystem.DoesNotExist) as error:
            raise SourceUnavailable from error
        return BookSource.objects.create(
            workspace_id=self.workspace_id.value,
            book=book,
            source=source,
            role=role,
            identity_namespace=identity_namespace,
            created_at=created_at,
        )

    def create_mapping_revision(
        self,
        *,
        source_id: UUID,
        revision: int,
        mapping: dict[str, Any],
        parser_version: str,
        digest: str,
        created_at: datetime,
    ) -> MappingRevision:
        source = self.get_source(source_id)
        return MappingRevision.objects.create(
            workspace_id=self.workspace_id.value,
            source=source,
            revision=revision,
            mapping=mapping,
            parser_version=parser_version,
            digest=digest,
            created_at=created_at,
        )

    def create_contract_revision(
        self,
        *,
        source_id: UUID,
        mapping_revision_id: UUID,
        revision: int,
        mode: DatasetMode,
        timezone_name: str | None,
        identity_namespace: str,
        reference_semantics: ReferenceSemantics,
        contract: dict[str, Any],
        digest: str,
        created_at: datetime,
    ) -> SourceContractRevision:
        source = self.get_source(source_id)
        mapping_revision = self.get_mapping(mapping_revision_id)
        if mapping_revision.source_id != source.id:
            raise SourceUnavailable
        return SourceContractRevision.objects.create(
            workspace_id=self.workspace_id.value,
            source=source,
            mapping_revision=mapping_revision,
            revision=revision,
            mode=mode,
            timezone_name=timezone_name,
            identity_namespace=identity_namespace,
            reference_semantics=reference_semantics,
            contract=contract,
            digest=digest,
            created_at=created_at,
        )

    def _get(self, model, public_id: UUID):
        try:
            return model.objects.owned_by(self.workspace_id).get(id=public_id)
        except model.DoesNotExist as error:
            raise SourceUnavailable from error
