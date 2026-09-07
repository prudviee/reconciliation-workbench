"""Workspace-scoped reconciliation scope, policy, and generation services."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from django.db import transaction
from django.db.models import F, Max, Q

from ingestion.models import Dataset
from reconciliation.domain import (
    BookId,
    WorkspaceId,
    policy_revision_digest,
)
from sources.models import SourceRole

from .models import PolicyRevision, ReconciliationBook, ReconciliationScope


class ScopeUnavailable(LookupError):
    """A scope or one of its parents is unavailable in the workspace."""


class PolicyUnavailable(LookupError):
    """A policy revision is unavailable in the workspace."""


class BookGenerationConflict(RuntimeError):
    """A caller based a policy change on an obsolete book generation."""


@dataclass(frozen=True, slots=True)
class WorkspaceScopeRepository:
    workspace_id: WorkspaceId

    def list(self, book_id: BookId) -> tuple[ReconciliationScope, ...]:
        self._book(book_id)
        return tuple(
            ReconciliationScope.objects.owned_by(self.workspace_id)
            .filter(book_id=book_id.value)
            .order_by("coverage_key", "id")
        )

    def get(self, scope_id: UUID) -> ReconciliationScope:
        try:
            return (
                ReconciliationScope.objects.owned_by(self.workspace_id)
                .select_related("book", "left_dataset", "right_dataset")
                .get(id=scope_id)
            )
        except ReconciliationScope.DoesNotExist as error:
            raise ScopeUnavailable from error

    def create(
        self,
        *,
        book_id: BookId,
        coverage_key: str,
        left_dataset_id: UUID,
        right_dataset_id: UUID,
        created_at: datetime,
    ) -> ReconciliationScope:
        if not isinstance(coverage_key, str) or not coverage_key.strip():
            raise ScopeUnavailable
        with transaction.atomic():
            book = self._book(book_id, lock=True)
            datasets = {
                item.id: item
                for item in Dataset.objects.owned_by(self.workspace_id)
                .filter(id__in=(left_dataset_id, right_dataset_id))
                .select_related("book_source")
            }
            if set(datasets) != {left_dataset_id, right_dataset_id}:
                raise ScopeUnavailable
            left = datasets[left_dataset_id]
            right = datasets[right_dataset_id]
            if (
                left.book_source.book_id != book.id
                or right.book_source.book_id != book.id
                or left.book_source.role != SourceRole.LEFT
                or right.book_source.role != SourceRole.RIGHT
            ):
                raise ScopeUnavailable
            return ReconciliationScope.objects.create(
                workspace_id=self.workspace_id.value,
                book=book,
                coverage_key=coverage_key.strip(),
                left_dataset=left,
                right_dataset=right,
                generation=0,
                is_dirty=True,
                created_at=created_at,
            )

    def _book(
        self, book_id: BookId, *, lock: bool = False
    ) -> ReconciliationBook:
        queryset = ReconciliationBook.objects.owned_by(self.workspace_id)
        if lock:
            queryset = queryset.select_for_update()
        try:
            return queryset.get(id=book_id.value)
        except ReconciliationBook.DoesNotExist as error:
            raise ScopeUnavailable from error


@dataclass(frozen=True, slots=True)
class WorkspacePolicyRepository:
    workspace_id: WorkspaceId

    def list(self, book_id: BookId) -> tuple[PolicyRevision, ...]:
        self._book(book_id)
        return tuple(
            PolicyRevision.objects.owned_by(self.workspace_id)
            .filter(book_id=book_id.value)
            .order_by("revision", "id")
        )

    def get(self, policy_id: UUID) -> PolicyRevision:
        try:
            return PolicyRevision.objects.owned_by(self.workspace_id).get(id=policy_id)
        except PolicyRevision.DoesNotExist as error:
            raise PolicyUnavailable from error

    def create_revision(
        self,
        *,
        book_id: BookId,
        expected_generation: int,
        matching_policy: dict[str, Any],
        comparison_policy: dict[str, Any],
        created_at: datetime,
    ) -> PolicyRevision:
        if (
            isinstance(expected_generation, bool)
            or not isinstance(expected_generation, int)
            or expected_generation < 0
        ):
            raise BookGenerationConflict
        digest = policy_revision_digest(
            matching_policy=matching_policy,
            comparison_policy=comparison_policy,
        )
        with transaction.atomic():
            book = self._book(book_id, lock=True)
            if book.generation != expected_generation:
                raise BookGenerationConflict
            existing = (
                PolicyRevision.objects.owned_by(self.workspace_id)
                .filter(book=book, digest=digest)
                .first()
            )
            if existing is not None:
                return existing
            latest = (
                PolicyRevision.objects.owned_by(self.workspace_id)
                .filter(book=book)
                .aggregate(value=Max("revision"))["value"]
                or 0
            )
            policy = PolicyRevision.objects.create(
                workspace_id=self.workspace_id.value,
                book=book,
                revision=latest + 1,
                matching_policy=matching_policy,
                comparison_policy=comparison_policy,
                digest=digest,
                created_at=created_at,
            )
            ReconciliationBook.objects.filter(id=book.id).update(
                generation=F("generation") + 1
            )
            ReconciliationScope.objects.owned_by(self.workspace_id).filter(
                book=book
            ).update(is_dirty=True, generation=F("generation") + 1)
            return policy

    def _book(
        self, book_id: BookId, *, lock: bool = False
    ) -> ReconciliationBook:
        queryset = ReconciliationBook.objects.owned_by(self.workspace_id)
        if lock:
            queryset = queryset.select_for_update()
        try:
            return queryset.get(id=book_id.value)
        except ReconciliationBook.DoesNotExist as error:
            raise PolicyUnavailable from error


def mark_dataset_activation(
    *,
    workspace_id: WorkspaceId,
    book_id: UUID,
    dataset_id: UUID,
) -> None:
    """Advance data generation and dirty only scopes that consume this dataset."""
    updated = (
        ReconciliationBook.objects.owned_by(workspace_id)
        .filter(id=book_id)
        .update(generation=F("generation") + 1)
    )
    if updated != 1:
        raise ScopeUnavailable
    ReconciliationScope.objects.owned_by(workspace_id).filter(
        Q(left_dataset_id=dataset_id) | Q(right_dataset_id=dataset_id)
    ).update(is_dirty=True, generation=F("generation") + 1)
