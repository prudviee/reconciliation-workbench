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
    ReplacementPreview,
    DecisionConflict,
    ReviewConflict,
    ReviewConflictCode,
    WorkspaceId,
)
from sources.models import SourceRole
from workspaces.lifecycle import WorkspaceLifecycleService
from workspaces.models import Workspace
from workspaces.repositories import WorkspaceUnavailable

from .models import (
    ActiveDecisionClaim,
    Decision,
    DecisionRevision,
    DecisionSupersession,
)


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

    def preview_replacement(
        self,
        workspace_id: WorkspaceId,
        *,
        book_id: BookId,
        target: ExpectedDecisionRevision,
        authority: DecisionAuthority,
    ) -> ReplacementPreview:
        now = self.clock()
        self._require_active_workspace_read(workspace_id, now)
        book = self._book(workspace_id, book_id)
        target_revision = self._current_revision(
            workspace_id,
            book,
            target,
        )
        logicals = self._resolve_authority(workspace_id, book, authority)
        conflicts = self._claim_conflicts(
            workspace_id,
            book,
            authority,
            logicals,
            excluding_decision_id=target_revision.decision_id,
        )
        return ReplacementPreview(
            authority=authority,
            target=target,
            conflicts=conflicts,
            resolution_generation=book.resolution_generation,
        )

    def commit_change(
        self,
        workspace_id: WorkspaceId,
        *,
        book_id: BookId,
        command: DecisionCommand,
    ) -> DecisionRevision:
        if not isinstance(command, DecisionCommand) or command.action not in {
            DecisionAction.REAFFIRM,
            DecisionAction.REVOKE,
            DecisionAction.REPLACE,
        }:
            raise InitialDecisionActionRequired(
                "commit_change accepts REAFFIRM, REVOKE, or REPLACE"
            )
        assert command.target is not None
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
            current = self._current_revision(
                workspace_id,
                book,
                command.target,
                lock=True,
            )
            inherited = self._authority_from_revision(current)
            logicals: dict[str, LogicalTransaction] = {}
            observations: tuple[TransactionObservation, ...] = ()
            authority: DecisionAuthority | None = None
            conflicts: tuple[DecisionConflict, ...] = ()
            if command.action is DecisionAction.REAFFIRM:
                authority = inherited
                logicals = self._resolve_authority(workspace_id, book, authority)
                observations = self._resolve_reviewed_observations(
                    workspace_id,
                    book,
                    command,
                    logicals,
                )
            elif command.action is DecisionAction.REPLACE:
                assert command.authority is not None
                authority = command.authority
                logicals = self._resolve_authority(workspace_id, book, authority)
                observations = self._resolve_reviewed_observations(
                    workspace_id,
                    book,
                    command,
                    logicals,
                )
                conflicts = self._claim_conflicts(
                    workspace_id,
                    book,
                    authority,
                    logicals,
                    excluding_decision_id=current.decision_id,
                )
                actual = tuple(
                    ExpectedDecisionRevision(item.decision_id, item.revision_id)
                    for item in conflicts
                )
                if actual != command.approved_conflicts:
                    raise DecisionMutationConflict(
                        ReviewConflict(
                            ReviewConflictCode.CONFLICT_SET_CHANGED,
                            "The affected decisions changed; preview the replacement again.",
                            actual,
                        )
                    )

            revision = self._create_lifecycle_revision(
                workspace_id=workspace_id,
                current=current,
                command=command,
                authority=authority,
                logicals=logicals,
                observations=observations,
                created_at=created_at,
            )

            if command.action is DecisionAction.REAFFIRM:
                ActiveDecisionClaim.objects.owned_by(workspace_id).filter(
                    book=book,
                    decision_revision=current,
                ).update(decision_revision=revision)
            elif command.action is DecisionAction.REVOKE:
                ActiveDecisionClaim.objects.owned_by(workspace_id).filter(
                    book=book,
                    decision_revision=current,
                ).delete()
            else:
                superseded_ids = [current.id] + [
                    UUID(item.revision_id) for item in conflicts
                ]
                DecisionSupersession.objects.bulk_create(
                    [
                        DecisionSupersession(
                            workspace_id=workspace_id.value,
                            replacement_revision=revision,
                            superseded_revision_id=revision_id,
                            created_at=created_at,
                        )
                        for revision_id in superseded_ids
                    ]
                )
                ActiveDecisionClaim.objects.owned_by(workspace_id).filter(
                    book=book,
                    decision_revision_id__in=superseded_ids,
                ).delete()
                assert authority is not None
                if authority.reserves_endpoints:
                    try:
                        ActiveDecisionClaim.objects.bulk_create(
                            [
                                ActiveDecisionClaim(
                                    workspace_id=workspace_id.value,
                                    book=book,
                                    logical_transaction=logicals[record_id],
                                    decision_revision=revision,
                                )
                                for record_id in authority.endpoint_ids
                            ]
                        )
                    except IntegrityError as error:
                        raise DecisionMutationConflict(
                            ReviewConflict(
                                ReviewConflictCode.ENDPOINT_CLAIMED,
                                "A reviewed endpoint is already reserved; preview again.",
                            )
                        ) from error

            Decision.objects.filter(id=current.decision_id).update(
                current_revision=revision
            )
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

    def _require_active_workspace_read(
        self,
        workspace_id: WorkspaceId,
        now: datetime,
    ) -> None:
        try:
            workspace = Workspace.objects.get(id=workspace_id.value)
            self.lifecycle_service.require_active(workspace, now=now)
        except (Workspace.DoesNotExist, WorkspaceUnavailable) as error:
            raise DecisionMutationUnavailable from error

    @staticmethod
    def _book(
        workspace_id: WorkspaceId,
        book_id: BookId,
    ) -> ReconciliationBook:
        try:
            return ReconciliationBook.objects.owned_by(workspace_id).get(
                id=book_id.value
            )
        except ReconciliationBook.DoesNotExist as error:
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
    def _current_revision(
        workspace_id: WorkspaceId,
        book: ReconciliationBook,
        target: ExpectedDecisionRevision,
        *,
        lock: bool = False,
    ) -> DecisionRevision:
        try:
            decision_id = UUID(target.decision_id)
            revision_id = UUID(target.revision_id)
        except (TypeError, ValueError) as error:
            raise DecisionMutationUnavailable from error
        queryset = Decision.objects.owned_by(workspace_id).filter(book=book)
        try:
            if lock:
                decision = queryset.select_for_update().get(id=decision_id)
                current = (
                    DecisionRevision.objects.owned_by(workspace_id)
                    .select_related("decision")
                    .get(id=decision.current_revision_id)
                    if decision.current_revision_id is not None
                    else None
                )
            else:
                decision = queryset.select_related("current_revision").get(id=decision_id)
                current = decision.current_revision
        except Decision.DoesNotExist as error:
            raise DecisionMutationUnavailable from error
        except DecisionRevision.DoesNotExist as error:
            raise DecisionMutationUnavailable from error
        if current is None or current.id != revision_id:
            affected = ()
            if current is not None:
                affected = (
                    ExpectedDecisionRevision(str(decision.id), str(current.id)),
                )
            raise DecisionMutationConflict(
                ReviewConflict(
                    ReviewConflictCode.STALE_REVISION,
                    "The decision revision changed; refresh before saving.",
                    affected,
                )
            )
        if current.action == DecisionAction.REVOKE.value or current.superseded_by.exists():
            raise DecisionMutationConflict(
                ReviewConflict(
                    ReviewConflictCode.STALE_REVISION,
                    "The decision is no longer active; refresh before saving.",
                )
            )
        return current

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
        conflicts = DecisionCommandService._claim_conflicts(
            workspace_id,
            book,
            authority,
            logicals,
        )
        if not conflicts:
            return
        affected = tuple(
            ExpectedDecisionRevision(item.decision_id, item.revision_id)
            for item in conflicts
        )
        raise DecisionMutationConflict(
            ReviewConflict(
                ReviewConflictCode.ENDPOINT_CLAIMED,
                "A reviewed endpoint is already reserved; preview a replacement.",
                affected,
            )
        )

    @staticmethod
    def _claim_conflicts(
        workspace_id: WorkspaceId,
        book: ReconciliationBook,
        authority: DecisionAuthority,
        logicals: dict[str, LogicalTransaction],
        *,
        excluding_decision_id: UUID | None = None,
    ) -> tuple[DecisionConflict, ...]:
        if not authority.reserves_endpoints:
            return ()
        claims_query = (
            ActiveDecisionClaim.objects.owned_by(workspace_id)
            .filter(
                book=book,
                logical_transaction_id__in=[
                    logicals[item].id for item in authority.endpoint_ids
                ],
            )
            .select_related("decision_revision__decision")
        )
        if excluding_decision_id is not None:
            claims_query = claims_query.exclude(
                decision_revision__decision_id=excluding_decision_id
            )
        overlapping = tuple(claims_query.order_by("decision_revision__decision_id"))
        revision_ids = {item.decision_revision_id for item in overlapping}
        if not revision_ids:
            return ()
        all_claims = ActiveDecisionClaim.objects.owned_by(workspace_id).filter(
            book=book,
            decision_revision_id__in=revision_ids,
        ).order_by("decision_revision__decision_id", "logical_transaction_id")
        grouped: dict[UUID, list[str]] = {}
        revisions: dict[UUID, DecisionRevision] = {}
        for item in all_claims.select_related("decision_revision__decision"):
            grouped.setdefault(item.decision_revision_id, []).append(
                str(item.logical_transaction_id)
            )
            revisions[item.decision_revision_id] = item.decision_revision
        return tuple(
            sorted(
                (
                    DecisionConflict(
                        decision_id=str(revisions[revision_id].decision_id),
                        revision_id=str(revision_id),
                        claimed_record_ids=tuple(grouped[revision_id]),
                    )
                    for revision_id in revision_ids
                ),
                key=lambda item: (item.decision_id, item.revision_id),
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

    @staticmethod
    def _create_lifecycle_revision(
        *,
        workspace_id: WorkspaceId,
        current: DecisionRevision,
        command: DecisionCommand,
        authority: DecisionAuthority | None,
        logicals: dict[str, LogicalTransaction],
        observations: tuple[TransactionObservation, ...],
        created_at: datetime,
    ) -> DecisionRevision:
        values: dict[str, object] = {}
        if authority is not None:
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
            decision=current.decision,
            predecessor=current,
            revision=current.revision + 1,
            action=command.action.value,
            authority_kind=authority.kind.value if authority is not None else None,
            reason=command.reason.strip(),
            actor=command.actor.strip(),
            reviewed_observation_ids=[str(item.id) for item in observations],
            reviewed_evidence_digest=(
                _reviewed_evidence_digest(observations) if observations else None
            ),
            created_at=created_at,
            **values,
        )

    @staticmethod
    def _authority_from_revision(revision: DecisionRevision) -> DecisionAuthority:
        kind = DecisionAuthorityKind(revision.authority_kind)
        if kind is DecisionAuthorityKind.ACCEPT_UNMATCHED:
            assert revision.record_logical_id is not None and revision.record_side is not None
            from reconciliation.domain import RecordSide

            return DecisionAuthority.accept_unmatched(
                str(revision.record_logical_id),
                RecordSide(revision.record_side),
            )
        assert revision.left_logical_id is not None and revision.right_logical_id is not None
        if kind is DecisionAuthorityKind.LINK:
            return DecisionAuthority.link(
                str(revision.left_logical_id), str(revision.right_logical_id)
            )
        return DecisionAuthority.reject_candidate(
            str(revision.left_logical_id), str(revision.right_logical_id)
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
