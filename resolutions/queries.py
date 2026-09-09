"""Bounded workspace/book/scope decision read projections for the workbench."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable
from uuid import UUID

from django.db.models import Exists, OuterRef, Q, Subquery
from django.utils import timezone

from books.models import ReconciliationBook, ReconciliationScope
from reconciliation.domain import (
    BookId,
    DecisionAuthority,
    ExpectedDecisionRevision,
    ReplacementPreview,
    WorkspaceId,
)
from reconciliation.models import CurrentDecisionHealth, RunInput
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

from .models import Decision, DecisionRevision, DecisionSupersession
from .services import DecisionCommandService, DecisionMutationUnavailable


_DECISION_CURSOR = "review-decisions-v1"


@dataclass(frozen=True, slots=True)
class DecisionListItem:
    decision_id: UUID
    current_revision_id: UUID
    revision: int
    action: str
    authority_kind: str | None
    left_logical_id: UUID | None
    right_logical_id: UUID | None
    record_logical_id: UUID | None
    record_side: str | None
    left_reference: str | None
    right_reference: str | None
    record_reference: str | None
    reason: str
    actor: str
    created_at: datetime
    authority_active: bool
    review_health: str | None
    attention: tuple[str, ...]
    health_run_id: UUID | None
    review_is_pending: bool

    @property
    def action_label(self) -> str:
        return self.action.replace("_", " ").lower()


@dataclass(frozen=True, slots=True)
class DecisionRevisionItem:
    revision_id: UUID
    revision: int
    action: str
    authority_kind: str | None
    left_logical_id: UUID | None
    right_logical_id: UUID | None
    record_logical_id: UUID | None
    record_side: str | None
    left_reference: str | None
    right_reference: str | None
    record_reference: str | None
    reason: str
    actor: str
    reviewed_observation_ids: tuple[str, ...]
    predecessor_revision_id: UUID | None
    created_at: datetime
    timeline_label: str
    authority_active: bool

    @property
    def action_label(self) -> str:
        return self.action.replace("_", " ").lower()


@dataclass(frozen=True, slots=True)
class DecisionHistory:
    decision_id: UUID
    current_revision_id: UUID
    resolution_generation: int
    revisions: tuple[DecisionRevisionItem, ...]


@dataclass(frozen=True, slots=True)
class DecisionRecordOption:
    logical_id: UUID
    observation_id: UUID
    side: str
    reference: str
    executed_at_utc: datetime
    instrument: str
    quantity: str
    gross_amount: str
    currency: str


@dataclass(slots=True)
class DecisionQueryService:
    clock: Callable[[], datetime] = timezone.now
    lifecycle_service: WorkspaceLifecycleService = field(
        default_factory=WorkspaceLifecycleService
    )

    def list_decisions(
        self,
        workspace_id: WorkspaceId,
        *,
        book_id: BookId,
        scope_id: UUID | str,
        cursor: str | None = None,
        page_size: int = 50,
    ) -> ReviewPage[DecisionListItem]:
        size = bounded_page_size(page_size)
        position = decode_review_cursor(_DECISION_CURSOR, cursor)
        book, scope = self._context(workspace_id, book_id, scope_id)
        health = CurrentDecisionHealth.objects.owned_by(workspace_id).filter(
            scope=scope,
            decision_id=OuterRef("pk"),
        )
        superseded = DecisionSupersession.objects.owned_by(workspace_id).filter(
            superseded_revision_id=OuterRef("current_revision_id")
        )
        queryset = (
            Decision.objects.owned_by(workspace_id)
            .filter(book=book, current_revision__isnull=False)
            .select_related(
                "current_revision",
                "current_revision__left_logical",
                "current_revision__right_logical",
                "current_revision__record_logical",
            )
            .annotate(
                current_is_superseded=Exists(superseded),
                projected_health=Subquery(health.values("health")[:1]),
                projected_attention=Subquery(health.values("attention")[:1]),
                projected_run_id=Subquery(health.values("run_id")[:1]),
                projected_resolution_generation=Subquery(
                    health.values("applied_resolution_generation")[:1]
                ),
            )
            .order_by("created_at", "id")
        )
        if position is not None:
            queryset = queryset.filter(
                Q(created_at__gt=position.created_at)
                | Q(created_at=position.created_at, id__gt=position.public_id)
            )
        rows = list(queryset[: size + 1])
        page_rows = rows[:size]
        items = tuple(self._list_item(row, book, scope) for row in page_rows)
        next_cursor = None
        if len(rows) > size and page_rows:
            last = page_rows[-1]
            next_cursor = encode_review_cursor(
                _DECISION_CURSOR,
                created_at=last.created_at,
                public_id=last.id,
            )
        return ReviewPage(items=items, next_cursor=next_cursor)

    def list_for_records(
        self,
        workspace_id: WorkspaceId,
        *,
        book_id: BookId,
        scope_id: UUID | str,
        record_ids: tuple[UUID, ...],
    ) -> tuple[DecisionListItem, ...]:
        if not record_ids:
            return ()
        book, scope = self._context(workspace_id, book_id, scope_id)
        health = CurrentDecisionHealth.objects.owned_by(workspace_id).filter(
            scope=scope,
            decision_id=OuterRef("pk"),
        )
        superseded = DecisionSupersession.objects.owned_by(workspace_id).filter(
            superseded_revision_id=OuterRef("current_revision_id")
        )
        queryset = (
            Decision.objects.owned_by(workspace_id)
            .filter(
                book=book,
            )
            .filter(
                Q(revisions__left_logical_id__in=record_ids)
                | Q(revisions__right_logical_id__in=record_ids)
                | Q(revisions__record_logical_id__in=record_ids)
            )
            .select_related(
                "current_revision",
                "current_revision__left_logical",
                "current_revision__right_logical",
                "current_revision__record_logical",
            )
            .annotate(
                current_is_superseded=Exists(superseded),
                projected_health=Subquery(health.values("health")[:1]),
                projected_attention=Subquery(health.values("attention")[:1]),
                projected_run_id=Subquery(health.values("run_id")[:1]),
                projected_resolution_generation=Subquery(
                    health.values("applied_resolution_generation")[:1]
                ),
            )
            .distinct()
            .order_by("created_at", "id")
        )
        return tuple(self._list_item(item, book, scope) for item in queryset)

    def get_decision_history(
        self,
        workspace_id: WorkspaceId,
        *,
        book_id: BookId,
        scope_id: UUID | str,
        decision_id: UUID | str,
    ) -> DecisionHistory:
        book, _scope = self._context(workspace_id, book_id, scope_id)
        public_id = self._public_id(decision_id)
        try:
            decision = (
                Decision.objects.owned_by(workspace_id)
                .filter(book=book)
                .get(id=public_id, current_revision__isnull=False)
            )
        except Decision.DoesNotExist as error:
            raise ReviewQueryUnavailable from error
        superseded = DecisionSupersession.objects.owned_by(workspace_id).filter(
            superseded_revision_id=OuterRef("pk")
        )
        revisions = tuple(
            DecisionRevision.objects.owned_by(workspace_id)
            .filter(decision=decision)
            .select_related("left_logical", "right_logical", "record_logical")
            .annotate(is_superseded=Exists(superseded))
            .order_by("revision", "id")
        )
        return DecisionHistory(
            decision_id=decision.id,
            current_revision_id=decision.current_revision_id,
            resolution_generation=book.resolution_generation,
            revisions=tuple(
                DecisionRevisionItem(
                    revision_id=item.id,
                    revision=item.revision,
                    action=item.action,
                    authority_kind=item.authority_kind,
                    left_logical_id=item.left_logical_id,
                    right_logical_id=item.right_logical_id,
                    record_logical_id=item.record_logical_id,
                    record_side=item.record_side,
                    left_reference=(
                        item.left_logical.source_record_key
                        if item.left_logical is not None
                        else None
                    ),
                    right_reference=(
                        item.right_logical.source_record_key
                        if item.right_logical is not None
                        else None
                    ),
                    record_reference=(
                        item.record_logical.source_record_key
                        if item.record_logical is not None
                        else None
                    ),
                    reason=item.reason,
                    actor=item.actor,
                    reviewed_observation_ids=tuple(item.reviewed_observation_ids),
                    predecessor_revision_id=item.predecessor_id,
                    created_at=item.created_at,
                    timeline_label=(
                        "CURRENT"
                        if item.id == decision.current_revision_id
                        else "HISTORICAL"
                    ),
                    authority_active=(
                        item.id == decision.current_revision_id
                        and item.action != "REVOKE"
                        and not item.is_superseded
                    ),
                )
                for item in revisions
            ),
        )

    def list_replacement_records(
        self,
        workspace_id: WorkspaceId,
        *,
        book_id: BookId,
        scope_id: UUID | str,
    ) -> tuple[DecisionRecordOption, ...]:
        book, scope = self._context(workspace_id, book_id, scope_id)
        if scope.current_run_id is None:
            return ()
        rows = (
            RunInput.objects.owned_by(workspace_id)
            .filter(run_id=scope.current_run_id, run__scope=scope, run__scope__book=book)
            .select_related("logical_transaction", "observation")
            .order_by("side", "logical_transaction__source_record_key", "id")[:200]
        )
        return tuple(
            DecisionRecordOption(
                logical_id=item.logical_transaction_id,
                observation_id=item.observation_id,
                side=item.side,
                reference=item.logical_transaction.source_record_key,
                executed_at_utc=item.observation.executed_at_utc,
                instrument=item.observation.instrument,
                quantity=str(item.observation.quantity),
                gross_amount=str(item.observation.gross_amount),
                currency=item.observation.currency,
            )
            for item in rows
        )

    def preview_replacement(
        self,
        workspace_id: WorkspaceId,
        *,
        book_id: BookId,
        target: ExpectedDecisionRevision,
        authority: DecisionAuthority,
    ) -> ReplacementPreview:
        try:
            return DecisionCommandService(
                clock=self.clock,
                lifecycle_service=self.lifecycle_service,
            ).preview_replacement(
                workspace_id,
                book_id=book_id,
                target=target,
                authority=authority,
            )
        except DecisionMutationUnavailable as error:
            raise ReviewQueryUnavailable from error

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
    def _public_id(value: UUID | str) -> UUID:
        try:
            return value if isinstance(value, UUID) else UUID(value)
        except (TypeError, ValueError) as error:
            raise ReviewQueryUnavailable from error

    @staticmethod
    def _list_item(
        decision: Decision,
        book: ReconciliationBook,
        scope: ReconciliationScope,
    ) -> DecisionListItem:
        revision = decision.current_revision
        assert revision is not None
        active = revision.action != "REVOKE" and not decision.current_is_superseded
        applied_generation = decision.projected_resolution_generation
        pending = scope.is_dirty or applied_generation != book.resolution_generation
        return DecisionListItem(
            decision_id=decision.id,
            current_revision_id=revision.id,
            revision=revision.revision,
            action=revision.action,
            authority_kind=revision.authority_kind,
            left_logical_id=revision.left_logical_id,
            right_logical_id=revision.right_logical_id,
            record_logical_id=revision.record_logical_id,
            record_side=revision.record_side,
            left_reference=(
                revision.left_logical.source_record_key
                if revision.left_logical is not None
                else None
            ),
            right_reference=(
                revision.right_logical.source_record_key
                if revision.right_logical is not None
                else None
            ),
            record_reference=(
                revision.record_logical.source_record_key
                if revision.record_logical is not None
                else None
            ),
            reason=revision.reason,
            actor=revision.actor,
            created_at=decision.created_at,
            authority_active=active,
            review_health=decision.projected_health,
            attention=tuple(decision.projected_attention or ()),
            health_run_id=decision.projected_run_id,
            review_is_pending=pending,
        )
