"""Workspace- and book-scoped reads for durable decisions."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from books.models import ReconciliationBook
from reconciliation.domain import BookId, WorkspaceId

from .models import ActiveDecisionClaim, Decision, DecisionRevision


class DecisionUnavailable(LookupError):
    """A decision resource is unavailable within the authorized book."""


@dataclass(frozen=True, slots=True)
class WorkspaceDecisionRepository:
    workspace_id: WorkspaceId

    def get(self, book_id: BookId, decision_id: UUID) -> Decision:
        self._book(book_id)
        try:
            return (
                Decision.objects.owned_by(self.workspace_id)
                .select_related("current_revision")
                .get(id=decision_id, book_id=book_id.value)
            )
        except Decision.DoesNotExist as error:
            raise DecisionUnavailable from error

    def get_revision(
        self,
        book_id: BookId,
        revision_id: UUID,
    ) -> DecisionRevision:
        self._book(book_id)
        try:
            return (
                DecisionRevision.objects.owned_by(self.workspace_id)
                .select_related("decision", "predecessor")
                .get(id=revision_id, decision__book_id=book_id.value)
            )
        except DecisionRevision.DoesNotExist as error:
            raise DecisionUnavailable from error

    def history(
        self,
        book_id: BookId,
        decision_id: UUID,
    ) -> tuple[DecisionRevision, ...]:
        decision = self.get(book_id, decision_id)
        return tuple(
            DecisionRevision.objects.owned_by(self.workspace_id)
            .filter(decision=decision)
            .select_related(
                "predecessor",
                "left_logical",
                "right_logical",
                "record_logical",
            )
            .order_by("revision", "id")
        )

    def claims(
        self,
        book_id: BookId,
    ) -> tuple[ActiveDecisionClaim, ...]:
        self._book(book_id)
        return tuple(
            ActiveDecisionClaim.objects.owned_by(self.workspace_id)
            .filter(book_id=book_id.value)
            .select_related("logical_transaction", "decision_revision")
            .order_by("logical_transaction_id", "id")
        )

    def _book(self, book_id: BookId) -> ReconciliationBook:
        try:
            return ReconciliationBook.objects.owned_by(self.workspace_id).get(
                id=book_id.value
            )
        except ReconciliationBook.DoesNotExist as error:
            raise DecisionUnavailable from error
