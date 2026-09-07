"""Atomic command service for durable reviewer authority."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable
from uuid import UUID

from django.db import IntegrityError, transaction
from django.db.models import F
from django.utils import timezone

from books.models import ReconciliationBook, ReconciliationScope
from ingestion.models import LogicalTransaction, TransactionObservation
from reconciliation.domain import (
    BookId,
    DecisionAction,
    DecisionAuthority,
    DecisionAuthorityKind,
    DecisionCommand,
    ExpectedDecisionRevision,
    ReviewConflict,
    ReviewConflictCode,
    WorkspaceId,
)
from sources.models import SourceRole
from workspaces.lifecycle import WorkspaceLifecycleService
from workspaces.models import Workspace
from workspaces.repositories import WorkspaceUnavailable

from .models import ActiveDecisionClaim, Decision, DecisionRevision


INITIAL_ACTIONS = {
    DecisionAction.LINK,
    DecisionAction.ACCEPT_UNMATCHED,
    DecisionAction.REJECT_CANDIDATE,
}


class DecisionMutationUnavailable(LookupError):
    """A mutation target is unavailable in the authorized workspace/book."""


class InitialDecisionActionRequired(ValueError):
    """The initial-decision service received a lifecycle action."""


class DecisionMutationConflict(RuntimeError):
    """Optimistic concurrency or endpoint authority rejected the command."""

    def __init__(self, conflict: ReviewConflict):
        self.conflict = conflict
        super().__init__(conflict.message)


@dataclass(slots=True)
class DecisionCommandService:
    clock: Callable[[], datetime] = timezone.now
    lifecycle_service: WorkspaceLifecycleService = field(
        default_factory=WorkspaceLifecycleService
    )

    def commit_initial(
        self,
        workspace_id: WorkspaceId,
        *,
        book_id: BookId,
        command: DecisionCommand,
    ) -> DecisionRevision:
        if not isinstance(command, DecisionCommand) or command.action not in INITIAL_ACTIONS:
            raise InitialDecisionActionRequired(
                "commit_initial accepts LINK, ACCEPT_UNMATCHED, or REJECT_CANDIDATE"
            )
        assert command.authority is not None
        created_at = self.clock()
        with transaction.atomic():
            self._require_active_workspace(workspace_id, created_at)
            book = self._locked_book(workspace_id, book_id)
            if book.resolution_generation != command.expected_resolution_generation:
                raise DecisionMutationConflict(
                    ReviewConflict(
                        ReviewConflictCode.STALE_GENERATION,
                        "The review state changed; refresh before saving this decision.",
                    )
                )
            logicals = self._resolve_authority(
                workspace_id,
                book,
                command.authority,
            )
            observations = self._resolve_reviewed_observations(
                workspace_id,
                book,
                command,
                logicals,
            )
            self._reject_claim_conflicts(
                workspace_id,
                book,
                command.authority,
                logicals,
            )
            decision = Decision.objects.create(
                workspace_id=workspace_id.value,
                book=book,
                created_at=created_at,
            )
            revision = self._create_initial_revision(
                workspace_id=workspace_id,
                decision=decision,
                command=command,
                logicals=logicals,
                observations=observations,
                created_at=created_at,
            )
            Decision.objects.filter(id=decision.id).update(
                current_revision=revision
            )
            if command.authority.reserves_endpoints:
                try:
                    ActiveDecisionClaim.objects.bulk_create(
                        [
                            ActiveDecisionClaim(
                                workspace_id=workspace_id.value,
                                book=book,
                                logical_transaction=logicals[record_id],
                                decision_revision=revision,
                            )
                            for record_id in command.authority.endpoint_ids
                        ]
                    )
                except IntegrityError as error:
                    raise DecisionMutationConflict(
                        ReviewConflict(
                            ReviewConflictCode.ENDPOINT_CLAIMED,
                            "A reviewed endpoint is already reserved; refresh before saving.",
                        )
                    ) from error
            ReconciliationBook.objects.filter(id=book.id).update(
                resolution_generation=F("resolution_generation") + 1
            )
            ReconciliationScope.objects.owned_by(workspace_id).filter(
                book=book
            ).update(is_dirty=True, generation=F("generation") + 1)
            return revision

    def _require_active_workspace(
        self,
        workspace_id: WorkspaceId,
        now: datetime,
    ) -> None:
        try:
            workspace = Workspace.objects.select_for_update().get(id=workspace_id.value)
            self.lifecycle_service.require_active(workspace, now=now)
        except (Workspace.DoesNotExist, WorkspaceUnavailable) as error:
            raise DecisionMutationUnavailable from error

    @staticmethod
    def _locked_book(
        workspace_id: WorkspaceId,
        book_id: BookId,
    ) -> ReconciliationBook:
        try:
            return (
                ReconciliationBook.objects.owned_by(workspace_id)
                .select_for_update()
                .get(id=book_id.value)
            )
        except ReconciliationBook.DoesNotExist as error:
            raise DecisionMutationUnavailable from error

    @staticmethod
    def _resolve_authority(
        workspace_id: WorkspaceId,
        book: ReconciliationBook,
        authority: DecisionAuthority,
    ) -> dict[str, LogicalTransaction]:
        try:
            parsed = {record_id: UUID(record_id) for record_id in authority.endpoint_ids}
        except (TypeError, ValueError) as error:
            raise DecisionMutationUnavailable from error
        logicals = {
            str(item.id): item
            for item in LogicalTransaction.objects.owned_by(workspace_id)
            .filter(id__in=parsed.values())
            .select_related("book_source")
        }
        if set(logicals) != set(parsed):
            raise DecisionMutationUnavailable
        if any(item.book_source.book_id != book.id for item in logicals.values()):
            raise DecisionMutationUnavailable

        if authority.kind is DecisionAuthorityKind.ACCEPT_UNMATCHED:
            assert authority.record_id is not None and authority.record_side is not None
            expected_role = SourceRole(authority.record_side.value)
            if logicals[authority.record_id].book_source.role != expected_role:
                raise DecisionMutationUnavailable
        else:
            assert authority.left_id is not None and authority.right_id is not None
            if (
                logicals[authority.left_id].book_source.role != SourceRole.LEFT
                or logicals[authority.right_id].book_source.role != SourceRole.RIGHT
            ):
                raise DecisionMutationUnavailable
        return logicals

    @staticmethod
    def _resolve_reviewed_observations(
        workspace_id: WorkspaceId,
        book: ReconciliationBook,
        command: DecisionCommand,
        logicals: dict[str, LogicalTransaction],
    ) -> tuple[TransactionObservation, ...]:
        try:
            ids = [UUID(value) for value in command.reviewed_observation_ids]
        except (TypeError, ValueError) as error:
            raise DecisionMutationUnavailable from error
        observations = tuple(
            TransactionObservation.objects.owned_by(workspace_id)
            .filter(id__in=ids)
            .select_related("logical_transaction__book_source")
            .order_by("id")
        )
        if len(observations) != len(ids):
            raise DecisionMutationUnavailable
        if any(
            item.logical_transaction.book_source.book_id != book.id
            or str(item.logical_transaction_id) not in logicals
            for item in observations
        ):
            raise DecisionMutationUnavailable
        if {str(item.logical_transaction_id) for item in observations} != set(logicals):
            raise DecisionMutationUnavailable
        return observations

    @staticmethod
    def _reject_claim_conflicts(
        workspace_id: WorkspaceId,
        book: ReconciliationBook,
        authority: DecisionAuthority,
        logicals: dict[str, LogicalTransaction],
    ) -> None:
        if not authority.reserves_endpoints:
            return
        claims = tuple(
            ActiveDecisionClaim.objects.owned_by(workspace_id)
            .filter(
                book=book,
                logical_transaction_id__in=[
                    logicals[item].id for item in authority.endpoint_ids
                ],
            )
            .select_related("decision_revision__decision")
            .order_by("decision_revision__decision_id")
        )
        if not claims:
            return
        affected = tuple(
            ExpectedDecisionRevision(
                str(item.decision_revision.decision_id),
                str(item.decision_revision_id),
            )
            for item in claims
        )
        raise DecisionMutationConflict(
            ReviewConflict(
                ReviewConflictCode.ENDPOINT_CLAIMED,
                "A reviewed endpoint is already reserved; preview a replacement.",
                affected,
            )
        )

    @staticmethod
    def _create_initial_revision(
        *,
        workspace_id: WorkspaceId,
        decision: Decision,
        command: DecisionCommand,
        logicals: dict[str, LogicalTransaction],
        observations: tuple[TransactionObservation, ...],
        created_at: datetime,
    ) -> DecisionRevision:
        assert command.authority is not None
        authority = command.authority
        values: dict[str, object] = {}
        if authority.kind is DecisionAuthorityKind.ACCEPT_UNMATCHED:
            assert authority.record_id is not None and authority.record_side is not None
            values.update(
                record_logical=logicals[authority.record_id],
                record_side=authority.record_side.value,
            )
        else:
            assert authority.left_id is not None and authority.right_id is not None
            values.update(
                left_logical=logicals[authority.left_id],
                right_logical=logicals[authority.right_id],
            )
        return DecisionRevision.objects.create(
            workspace_id=workspace_id.value,
            decision=decision,
            revision=1,
            action=command.action.value,
            authority_kind=authority.kind.value,
            reason=command.reason.strip(),
            actor=command.actor.strip(),
            reviewed_observation_ids=[str(item.id) for item in observations],
            reviewed_evidence_digest=_reviewed_evidence_digest(observations),
            created_at=created_at,
            **values,
        )


def _reviewed_evidence_digest(
    observations: tuple[TransactionObservation, ...],
) -> str:
    payload = [
        {
            "logical_transaction_id": str(item.logical_transaction_id),
            "observation_id": str(item.id),
            "fingerprint": item.fingerprint,
        }
        for item in sorted(observations, key=lambda value: str(value.id))
    ]
    encoded = json.dumps(
        {
            "version": "reviewed-evidence-v1",
            "observations": payload,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
