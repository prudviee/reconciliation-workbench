"""Workspace-scoped persistence operations for reconciliation books."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from django.db import transaction

from reconciliation.domain import BookId, QuotaAmounts, WorkspaceId
from workspaces.models import Workspace
from workspaces.quotas import WorkspaceQuotaService

from .models import BookKind, ReconciliationBook


class BookUnavailable(LookupError):
    """A book is unavailable within the authorized workspace."""


@dataclass(frozen=True, slots=True)
class WorkspaceBookRepository:
    workspace_id: WorkspaceId
    quota_service: WorkspaceQuotaService = field(default_factory=WorkspaceQuotaService)

    def list(self) -> tuple[ReconciliationBook, ...]:
        return tuple(
            ReconciliationBook.objects.owned_by(self.workspace_id).order_by(
                "created_at", "id"
            )
        )

    def count(self) -> int:
        return ReconciliationBook.objects.owned_by(self.workspace_id).count()

    def get(self, book_id: BookId) -> ReconciliationBook:
        try:
            return ReconciliationBook.objects.owned_by(self.workspace_id).get(
                id=book_id.value
            )
        except ReconciliationBook.DoesNotExist as error:
            raise BookUnavailable from error

    def create_user_book(
        self, *, name: str, created_at: datetime
    ) -> ReconciliationBook:
        return self._create(
            name=name,
            kind=BookKind.USER,
            sample_template_version=None,
            created_at=created_at,
        )

    def create_demo_book(
        self, *, name: str, sample_template_version: str, created_at: datetime
    ) -> ReconciliationBook:
        return self._create(
            name=name,
            kind=BookKind.DEMO,
            sample_template_version=sample_template_version,
            created_at=created_at,
        )

    def rename(self, book_id: BookId, *, name: str) -> ReconciliationBook:
        with transaction.atomic():
            updated = ReconciliationBook.objects.owned_by(self.workspace_id).filter(
                id=book_id.value
            ).update(name=name)
            if updated != 1:
                raise BookUnavailable
            return self.get(book_id)

    def delete(self, book_id: BookId) -> None:
        with transaction.atomic():
            try:
                Workspace.objects.select_for_update().get(id=self.workspace_id.value)
            except Workspace.DoesNotExist as error:
                raise BookUnavailable from error
            try:
                book = (
                    ReconciliationBook.objects.select_for_update()
                    .owned_by(self.workspace_id)
                    .get(id=book_id.value)
                )
            except ReconciliationBook.DoesNotExist as error:
                raise BookUnavailable from error
            self.quota_service.release(
                self.workspace_id,
                QuotaAmounts(books=1),
            )
            book.delete()

    def _create(
        self,
        *,
        name: str,
        kind: BookKind,
        sample_template_version: str | None,
        created_at: datetime,
    ) -> ReconciliationBook:
        with transaction.atomic():
            self.quota_service.reserve(
                self.workspace_id,
                QuotaAmounts(books=1),
            )
            return ReconciliationBook.objects.create(
                workspace_id=self.workspace_id.value,
                name=name,
                kind=kind,
                sample_template_version=sample_template_version,
                created_at=created_at,
            )
