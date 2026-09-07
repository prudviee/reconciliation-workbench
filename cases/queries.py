"""Bounded workspace/book/scope case projections for the review workbench."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable
from uuid import UUID

from django.db.models import Exists, OuterRef, Q
from django.utils import timezone

from books.models import ReconciliationBook, ReconciliationScope
from reconciliation.domain import BookId, WorkspaceId
from reconciliation.querying import (
    ReviewPage,
    ReviewQueryUnavailable,
    bounded_page_size,
    decode_review_cursor,
    encode_review_cursor,
)
from workspaces.lifecycle import WorkspaceLifecycleService
from workspaces.models import Workspace
from workspaces.repositories import WorkspaceUnavailable

from .models import (
    CaseLineage,
    CaseOccurrence,
    CaseScopeProjection,
    InvestigationCase,
)


_CASE_CURSOR = "review-cases-v1"


@dataclass(frozen=True, slots=True)
class CaseListItem:
    case_id: UUID
    kind: str
    stable_key: str
    occurrence_id: UUID
    run_id: UUID
    result_kind: str
    review_health: str | None
    attention: tuple[str, ...]
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class CaseOccurrenceItem:
    occurrence_id: UUID
    run_id: UUID
    run_freshness: str
    result_kind: str
    pair_id: UUID | None
    unpaired_id: UUID | None
    component_id: UUID | None
    state_snapshot: dict
    created_at: datetime
    timeline_label: str


@dataclass(frozen=True, slots=True)
class CaseHistory:
    case_id: UUID
    kind: str
    stable_key: str
    occurrences: tuple[CaseOccurrenceItem, ...]


@dataclass(frozen=True, slots=True)
class CurrentCaseReview:
    case_id: UUID
    occurrence_id: UUID
    run_id: UUID
    review_health: str | None
    attention: tuple[str, ...]
    applied_data_generation: int
    applied_resolution_generation: int
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class CaseLineageEdgeItem:
    edge_id: UUID
    direction: str
    related_case_id: UUID
    related_case_kind: str
    related_stable_key: str
    caused_by_run_id: UUID
    transition_kind: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class CaseLineageDetail:
    case_id: UUID
    edges: tuple[CaseLineageEdgeItem, ...]


@dataclass(slots=True)
class CaseQueryService:
    clock: Callable[[], datetime] = timezone.now
    lifecycle_service: WorkspaceLifecycleService = field(
        default_factory=WorkspaceLifecycleService
    )

    def list_cases(
        self,
        workspace_id: WorkspaceId,
        *,
        book_id: BookId,
        scope_id: UUID | str,
        cursor: str | None = None,
        page_size: int = 50,
    ) -> ReviewPage[CaseListItem]:
        size = bounded_page_size(page_size)
        position = decode_review_cursor(_CASE_CURSOR, cursor)
        _book, scope = self._context(workspace_id, book_id, scope_id)
        queryset = (
            CaseScopeProjection.objects.owned_by(workspace_id)
            .filter(scope=scope)
            .select_related("case", "current_occurrence", "run")
            .order_by("case__created_at", "case_id")
        )
        if position is not None:
            queryset = queryset.filter(
                Q(case__created_at__gt=position.created_at)
                | Q(
                    case__created_at=position.created_at,
                    case_id__gt=position.public_id,
                )
            )
        rows = list(queryset[: size + 1])
        page_rows = rows[:size]
        items = tuple(
            CaseListItem(
                case_id=row.case_id,
                kind=row.case.kind,
                stable_key=row.case.stable_key,
                occurrence_id=row.current_occurrence_id,
                run_id=row.run_id,
                result_kind=row.current_occurrence.result_kind,
                review_health=row.review_health,
                attention=tuple(row.attention),
                created_at=row.case.created_at,
                updated_at=row.updated_at,
            )
            for row in page_rows
        )
        next_cursor = None
        if len(rows) > size and page_rows:
            last = page_rows[-1].case
            next_cursor = encode_review_cursor(
                _CASE_CURSOR,
                created_at=last.created_at,
                public_id=last.id,
            )
        return ReviewPage(items=items, next_cursor=next_cursor)

    def get_case_history(
        self,
        workspace_id: WorkspaceId,
        *,
        book_id: BookId,
        scope_id: UUID | str,
        case_id: UUID | str,
    ) -> CaseHistory:
        book, scope = self._context(workspace_id, book_id, scope_id)
        case = self._case(workspace_id, book, scope, case_id)
        current = CaseScopeProjection.objects.owned_by(workspace_id).filter(
            scope=scope,
            current_occurrence_id=OuterRef("pk"),
        )
        occurrences = tuple(
            CaseOccurrence.objects.owned_by(workspace_id)
            .filter(case=case, run__scope=scope)
            .select_related("run")
            .annotate(is_current=Exists(current))
            .order_by("run__created_at", "id")
        )
        return CaseHistory(
            case_id=case.id,
            kind=case.kind,
            stable_key=case.stable_key,
            occurrences=tuple(self._occurrence_item(item) for item in occurrences),
        )

    def get_case_occurrence(
        self,
        workspace_id: WorkspaceId,
        *,
        book_id: BookId,
        scope_id: UUID | str,
        occurrence_id: UUID | str,
    ) -> CaseOccurrenceItem:
        book, scope = self._context(workspace_id, book_id, scope_id)
        public_id = self._public_id(occurrence_id)
        current = CaseScopeProjection.objects.owned_by(workspace_id).filter(
            scope=scope,
            current_occurrence_id=OuterRef("pk"),
        )
        try:
            occurrence = (
                CaseOccurrence.objects.owned_by(workspace_id)
                .filter(case__book=book, run__scope=scope)
                .select_related("run")
                .annotate(is_current=Exists(current))
                .get(id=public_id)
            )
        except CaseOccurrence.DoesNotExist as error:
            raise ReviewQueryUnavailable from error
        return self._occurrence_item(occurrence)

    def get_current_review(
        self,
        workspace_id: WorkspaceId,
        *,
        book_id: BookId,
        scope_id: UUID | str,
        case_id: UUID | str,
    ) -> CurrentCaseReview | None:
        book, scope = self._context(workspace_id, book_id, scope_id)
        case = self._case(workspace_id, book, scope, case_id)
        projection = (
            CaseScopeProjection.objects.owned_by(workspace_id)
            .filter(scope=scope, case=case)
            .first()
        )
        if projection is None:
            return None
        return CurrentCaseReview(
            case_id=case.id,
            occurrence_id=projection.current_occurrence_id,
            run_id=projection.run_id,
            review_health=projection.review_health,
            attention=tuple(projection.attention),
            applied_data_generation=projection.applied_data_generation,
            applied_resolution_generation=projection.applied_resolution_generation,
            updated_at=projection.updated_at,
        )

    def get_case_lineage(
        self,
        workspace_id: WorkspaceId,
        *,
        book_id: BookId,
        scope_id: UUID | str,
        case_id: UUID | str,
    ) -> CaseLineageDetail:
        book, scope = self._context(workspace_id, book_id, scope_id)
        case = self._case(workspace_id, book, scope, case_id)
        edges = tuple(
            CaseLineage.objects.owned_by(workspace_id)
            .filter(scope=scope)
            .filter(Q(predecessor=case) | Q(successor=case))
            .select_related("predecessor", "successor", "caused_by_run")
            .order_by("created_at", "id")
        )
        return CaseLineageDetail(
            case_id=case.id,
            edges=tuple(self._lineage_item(case, edge) for edge in edges),
        )

    def _context(
        self,
        workspace_id: WorkspaceId,
        book_id: BookId,
        scope_id: UUID | str,
    ) -> tuple[ReconciliationBook, ReconciliationScope]:
        try:
            workspace = Workspace.objects.get(id=workspace_id.value)
            self.lifecycle_service.require_active(workspace, now=self.clock())
            book = ReconciliationBook.objects.owned_by(workspace_id).get(
                id=book_id.value
            )
            scope = ReconciliationScope.objects.owned_by(workspace_id).get(
                id=self._public_id(scope_id),
                book=book,
            )
        except (
            Workspace.DoesNotExist,
            WorkspaceUnavailable,
            ReconciliationBook.DoesNotExist,
            ReconciliationScope.DoesNotExist,
        ) as error:
            raise ReviewQueryUnavailable from error
        return book, scope

    @staticmethod
    def _case(
        workspace_id: WorkspaceId,
        book: ReconciliationBook,
        scope: ReconciliationScope,
        case_id: UUID | str,
    ) -> InvestigationCase:
        public_id = CaseQueryService._public_id(case_id)
        try:
            return (
                InvestigationCase.objects.owned_by(workspace_id)
                .filter(book=book, occurrences__run__scope=scope)
                .distinct()
                .get(id=public_id)
            )
        except InvestigationCase.DoesNotExist as error:
            raise ReviewQueryUnavailable from error

    @staticmethod
    def _public_id(value: UUID | str) -> UUID:
        try:
            return value if isinstance(value, UUID) else UUID(value)
        except (TypeError, ValueError) as error:
            raise ReviewQueryUnavailable from error

    @staticmethod
    def _occurrence_item(occurrence: CaseOccurrence) -> CaseOccurrenceItem:
        return CaseOccurrenceItem(
            occurrence_id=occurrence.id,
            run_id=occurrence.run_id,
            run_freshness=occurrence.run.freshness,
            result_kind=occurrence.result_kind,
            pair_id=occurrence.pair_id,
            unpaired_id=occurrence.unpaired_id,
            component_id=occurrence.component_id,
            state_snapshot=dict(occurrence.state_snapshot),
            created_at=occurrence.created_at,
            timeline_label="CURRENT" if occurrence.is_current else "HISTORICAL",
        )

    @staticmethod
    def _lineage_item(
        case: InvestigationCase,
        edge: CaseLineage,
    ) -> CaseLineageEdgeItem:
        outgoing = edge.predecessor_id == case.id
        related = edge.successor if outgoing else edge.predecessor
        return CaseLineageEdgeItem(
            edge_id=edge.id,
            direction="SUCCESSOR" if outgoing else "PREDECESSOR",
            related_case_id=related.id,
            related_case_kind=related.kind,
            related_stable_key=related.stable_key,
            caused_by_run_id=edge.caused_by_run_id,
            transition_kind=edge.transition_kind,
            created_at=edge.created_at,
        )
