"""Bounded workspace/book/scope case projections for the review workbench."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable
from uuid import UUID

from django.db.models import Exists, OuterRef, Q
from django.utils import timezone

from books.models import ReconciliationBook, ReconciliationScope
from reconciliation.domain import BookId, WorkspaceId
from reconciliation.querying import (
    ReviewFilterError,
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
from reconciliation.models import CandidateEvidence


_CASE_CURSOR = "review-cases-v1"
_CASE_KINDS = frozenset({"PAIR", "UNPAIRED", "AMBIGUITY"})
_REVIEW_HEALTH = frozenset(
    {"UNCHANGED", "EVIDENCE_CHANGED", "PARTNER_UNAVAILABLE", "NEW_CANDIDATE"}
)
_CASE_SORTS = frozenset({"oldest", "newest"})


@dataclass(frozen=True, slots=True)
class CaseEvidenceRecord:
    side: str
    observation_id: UUID
    logical_transaction_id: UUID
    source_record_key: str
    row_number: int
    raw_values: tuple[dict, ...]
    canonical_values: dict
    provenance: tuple[dict, ...]


@dataclass(frozen=True, slots=True)
class CaseEvidenceDetail:
    case_id: UUID
    kind: str
    stable_key: str
    occurrence: CaseOccurrenceItem
    current_review: CurrentCaseReview | None
    history: CaseHistory
    lineage: CaseLineageDetail
    left: CaseEvidenceRecord | None
    right: CaseEvidenceRecord | None
    comparisons: tuple[dict, ...]
    candidates: tuple[dict, ...]
    link_options: tuple[dict, ...]
    allocation: dict | None
    run_metadata: dict

    @property
    def records(self) -> tuple[CaseEvidenceRecord, ...]:
        return tuple(item for item in (self.left, self.right) if item is not None)

    @property
    def display_label(self) -> str:
        if self.left is not None and self.right is not None:
            return f"{self.left.source_record_key} ↔ {self.right.source_record_key}"
        record = self.left or self.right
        if record is not None:
            return f"{record.source_record_key} · {record.side.lower()}"
        return "Ambiguous candidate set"


@dataclass(frozen=True, slots=True)
class CaseListItem:
    case_id: UUID
    kind: str
    stable_key: str
    display_label: str
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
        search: str | None = None,
        kind: str | None = None,
        review: str | None = None,
        sort: str = "oldest",
    ) -> ReviewPage[CaseListItem]:
        size = bounded_page_size(page_size)
        search_value, kind_value, review_value, sort_value = self._case_filters(
            search=search,
            kind=kind,
            review=review,
            sort=sort,
        )
        cursor_namespace = self._cursor_namespace(
            search_value, kind_value, review_value, sort_value
        )
        position = decode_review_cursor(cursor_namespace, cursor)
        _book, scope = self._context(workspace_id, book_id, scope_id)
        queryset = (
            CaseScopeProjection.objects.owned_by(workspace_id)
            .filter(scope=scope)
            .select_related(
                "case",
                "case__left_logical",
                "case__right_logical",
                "case__record_logical",
                "current_occurrence",
                "run",
            )
        )
        if search_value:
            queryset = queryset.filter(
                Q(case__stable_key__icontains=search_value)
                | Q(case__left_logical__source_record_key__icontains=search_value)
                | Q(case__right_logical__source_record_key__icontains=search_value)
                | Q(case__record_logical__source_record_key__icontains=search_value)
            )
        if kind_value:
            queryset = queryset.filter(case__kind=kind_value)
        if review_value == "UNREVIEWED":
            queryset = queryset.filter(review_health__isnull=True)
        elif review_value:
            queryset = queryset.filter(review_health=review_value)
        total = queryset.count()
        descending = sort_value == "newest"
        queryset = queryset.order_by(
            "-case__created_at" if descending else "case__created_at",
            "-case_id" if descending else "case_id",
        )
        if position is not None:
            if descending:
                queryset = queryset.filter(
                    Q(case__created_at__lt=position.created_at)
                    | Q(
                        case__created_at=position.created_at,
                        case_id__lt=position.public_id,
                    )
                )
            else:
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
                display_label=self._case_label(row.case),
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
                cursor_namespace,
                created_at=last.created_at,
                public_id=last.id,
            )
        return ReviewPage(items=items, next_cursor=next_cursor, total=total)

    @staticmethod
    def _case_filters(
        *,
        search: str | None,
        kind: str | None,
        review: str | None,
        sort: str,
    ) -> tuple[str, str, str, str]:
        search_value = (search or "").strip()
        kind_value = (kind or "").strip().upper()
        review_value = (review or "").strip().upper()
        sort_value = (sort or "oldest").strip().lower()
        if len(search_value) > 120:
            raise ReviewFilterError("search must be at most 120 characters")
        if kind_value and kind_value not in _CASE_KINDS:
            raise ReviewFilterError("case kind is unsupported")
        if review_value and review_value not in _REVIEW_HEALTH | {"UNREVIEWED"}:
            raise ReviewFilterError("review status is unsupported")
        if sort_value not in _CASE_SORTS:
            raise ReviewFilterError("case sort is unsupported")
        return search_value, kind_value, review_value, sort_value

    @staticmethod
    def _cursor_namespace(search: str, kind: str, review: str, sort: str) -> str:
        payload = json.dumps(
            {"q": search, "kind": kind, "review": review, "sort": sort},
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
        digest = hashlib.sha256(payload).hexdigest()[:16]
        return f"{_CASE_CURSOR}:{digest}"

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

    def get_case_evidence(
        self,
        workspace_id: WorkspaceId,
        *,
        book_id: BookId,
        scope_id: UUID | str,
        case_id: UUID | str,
    ) -> CaseEvidenceDetail:
        book, scope = self._context(workspace_id, book_id, scope_id)
        case = self._case(workspace_id, book, scope, case_id)
        projection = (
            CaseScopeProjection.objects.owned_by(workspace_id)
            .filter(scope=scope, case=case)
            .select_related("current_occurrence__run")
            .first()
        )
        if projection is None:
            raise ReviewQueryUnavailable
        occurrence = self._occurrence_with_evidence(
            workspace_id, book, scope, projection.current_occurrence_id
        )
        history = self.get_case_history(
            workspace_id, book_id=book_id, scope_id=scope.id, case_id=case.id
        )
        lineage = self.get_case_lineage(
            workspace_id, book_id=book_id, scope_id=scope.id, case_id=case.id
        )
        current_review = self.get_current_review(
            workspace_id, book_id=book_id, scope_id=scope.id, case_id=case.id
        )
        current_occurrence = (
            CaseOccurrence.objects.owned_by(workspace_id)
            .filter(id=projection.current_occurrence_id)
            .select_related(
                "run__policy_revision",
                "pair__left_observation__logical_transaction",
                "pair__right_observation__logical_transaction",
                "pair__left_observation__raw_row",
                "pair__right_observation__raw_row",
                "unpaired__observation__logical_transaction",
                "unpaired__observation__raw_row",
                "component",
            )
            .get()
        )
        left = right = None
        comparisons: tuple[dict, ...] = ()
        candidates: tuple[dict, ...] = ()
        if current_occurrence.pair_id:
            pair = current_occurrence.pair
            left = self._record("LEFT", pair.left_observation)
            right = self._record("RIGHT", pair.right_observation)
            comparisons = tuple(
                {
                    "field": item.field,
                    "status": item.status,
                    "left_value": item.left_value,
                    "right_value": item.right_value,
                    "signed_difference": item.signed_difference,
                    "allowed_difference": item.allowed_difference,
                    "explanation": item.explanation,
                }
                for item in pair.comparisons.all().order_by("field")
            )
        elif current_occurrence.unpaired_id:
            item = current_occurrence.unpaired
            record = self._record(item.side, item.observation)
            if item.side == "LEFT":
                left = record
            else:
                right = record
        elif current_occurrence.component_id:
            candidates = tuple(
                {
                    "score_bp": item.score_bp,
                    "score_label": item.score_label,
                    "blocking_reasons": tuple(item.blocking_reasons),
                    "contradictions": tuple(item.contradictions),
                    "coverage_failures": tuple(item.coverage_failures),
                    "complete_computation": item.complete_computation,
                    "left_observation_id": item.left_observation_id,
                    "right_observation_id": item.right_observation_id,
                }
                for item in CandidateEvidence.objects.owned_by(workspace_id)
                .filter(component_id=current_occurrence.component_id)
                .order_by("-score_bp", "id")
            )
        link_options: tuple[dict, ...] = ()
        if (left is None) != (right is None):
            own_observation_id = (left or right).observation_id
            options = CandidateEvidence.objects.owned_by(workspace_id).filter(
                run=current_occurrence.run
            ).filter(
                Q(left_observation_id=own_observation_id)
                | Q(right_observation_id=own_observation_id)
            ).select_related(
                "left_observation__logical_transaction",
                "right_observation__logical_transaction",
                "left_observation__raw_row",
                "right_observation__raw_row",
            ).order_by("-score_bp", "id")
            link_options = tuple(
                {
                    "partner_observation_id": (
                        item.right_observation_id
                        if item.left_observation_id == own_observation_id
                        else item.left_observation_id
                    ),
                    "left_observation_id": item.left_observation_id,
                    "right_observation_id": item.right_observation_id,
                    "partner_logical_id": (
                        item.right_observation.logical_transaction_id
                        if item.left_observation_id == own_observation_id
                        else item.left_observation.logical_transaction_id
                    ),
                    "partner_source_record_key": (
                        item.right_observation.logical_transaction.source_record_key
                        if item.left_observation_id == own_observation_id
                        else item.left_observation.logical_transaction.source_record_key
                    ),
                    "partner_record": self._record(
                        "RIGHT" if item.left_observation_id == own_observation_id else "LEFT",
                        item.right_observation
                        if item.left_observation_id == own_observation_id
                        else item.left_observation,
                    ),
                    "score_bp": item.score_bp,
                    "score_label": item.score_label,
                    "blocking_reasons": tuple(item.blocking_reasons),
                }
                for item in options
            )
        allocation = self._allocation_evidence(
            workspace_id,
            current_occurrence,
        )
        policy = current_occurrence.run.policy_revision
        return CaseEvidenceDetail(
            case_id=case.id,
            kind=case.kind,
            stable_key=case.stable_key,
            occurrence=occurrence,
            current_review=current_review,
            history=history,
            lineage=lineage,
            left=left,
            right=right,
            comparisons=comparisons,
            candidates=candidates,
            link_options=link_options,
            allocation=allocation,
            run_metadata={
                "run_id": current_occurrence.run_id,
                "created_at": current_occurrence.run.created_at,
                "data_generation": current_occurrence.run.data_generation,
                "resolution_generation": current_occurrence.run.resolution_generation,
                "engine_version": current_occurrence.run.engine_version,
                "solver_version": current_occurrence.run.solver_version,
                "policy_digest": policy.digest,
                "matching_policy_version": policy.matching_policy.get("policy_version"),
                "comparison_policy_version": policy.comparison_policy.get("policy_version"),
            },
        )

    @staticmethod
    def _allocation_evidence(
        workspace_id: WorkspaceId,
        occurrence: CaseOccurrence,
    ) -> dict | None:
        component_id = occurrence.component_id
        if component_id is None:
            related = CandidateEvidence.objects.owned_by(workspace_id).filter(
                run=occurrence.run,
                component__isnull=False,
            )
            if occurrence.pair_id:
                related = related.filter(
                    left_observation_id=occurrence.pair.left_observation_id,
                    right_observation_id=occurrence.pair.right_observation_id,
                )
            elif occurrence.unpaired_id:
                observation_id = occurrence.unpaired.observation_id
                related = related.filter(
                    Q(left_observation_id=observation_id)
                    | Q(right_observation_id=observation_id)
                )
            component_id = related.values_list("component_id", flat=True).first()
        if component_id is None:
            return None
        candidates = tuple(
            CandidateEvidence.objects.owned_by(workspace_id)
            .filter(run=occurrence.run, component_id=component_id)
            .select_related(
                "component",
                "left_observation__logical_transaction",
                "right_observation__logical_transaction",
            )
            .order_by("-score_bp", "left_observation_id", "right_observation_id")
        )
        if not candidates:
            return None
        component = candidates[0].component
        proposals = {
            (item["left_id"], item["right_id"]): item
            for item in component.proposals or ()
        }
        rows = []
        for candidate in candidates:
            proposal = proposals.get(
                (str(candidate.left_observation_id), str(candidate.right_observation_id))
            )
            rows.append(
                {
                    "left_reference": candidate.left_observation.logical_transaction.source_record_key,
                    "right_reference": candidate.right_observation.logical_transaction.source_record_key,
                    "score_bp": candidate.score_bp,
                    "score_label": candidate.score_label,
                    "blocking_reasons": tuple(candidate.blocking_reasons),
                    "features": tuple(
                        {
                            "name": item["feature"].replace("_", " ").title(),
                            "left_value": CaseQueryService._semantic_label(
                                item.get("left_value")
                            ),
                            "right_value": CaseQueryService._semantic_label(
                                item.get("right_value")
                            ),
                            "difference": CaseQueryService._semantic_label(
                                item.get("difference")
                            ),
                            "similarity_bp": item["similarity_bp"],
                            "weight_bp": item["weight_bp"],
                            "contribution_bp": item["contribution_bp"],
                            "rule": item["rule"],
                        }
                        for item in candidate.features
                    ),
                    "contradictions": tuple(candidate.contradictions),
                    "coverage_failures": tuple(candidate.coverage_failures),
                    "selected": proposal is not None,
                    "accepted": proposal["accepted"] if proposal is not None else False,
                    "counterfactual_objective_bp": (
                        proposal["counterfactual_objective_bp"]
                        if proposal is not None
                        else None
                    ),
                    "global_gap_bp": (
                        proposal["global_gap_bp"] if proposal is not None else None
                    ),
                    "gate_reasons": (
                        tuple(proposal["gate_reasons"])
                        if proposal is not None
                        else ()
                    ),
                }
            )
        return {
            "component_id": component.id,
            "candidate_count": component.candidate_count,
            "optimal_utility_bp": component.optimal_utility_bp,
            "complete": component.complete,
            "limit_reason": component.limit_reason,
            "graph_digest": component.graph_digest,
            "solver_version": component.solver_version,
            "candidates": tuple(rows),
        }

    @staticmethod
    def _semantic_label(value: object) -> str:
        if value is None:
            return "—"
        if isinstance(value, dict) and len(value) == 1:
            key, payload = next(iter(value.items()))
            if key == "timedelta_microseconds":
                return f"{payload} µs"
            return str(payload)
        return str(value)

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
    def _record(side: str, observation) -> CaseEvidenceRecord:
        canonical = {
            "business_reference": observation.business_reference,
            "executed_at_utc": observation.executed_at_utc.isoformat(),
            "instrument": observation.instrument,
            "side": observation.side,
            "quantity": str(observation.quantity),
            "unit_price": str(observation.unit_price),
            "gross_amount": str(observation.gross_amount),
            "currency": observation.currency,
            "state": observation.state,
        }
        return CaseEvidenceRecord(
            side=side,
            observation_id=observation.id,
            logical_transaction_id=observation.logical_transaction_id,
            source_record_key=observation.logical_transaction.source_record_key,
            row_number=observation.raw_row.row_number,
            raw_values=tuple(observation.raw_row.raw_values or ()),
            canonical_values=canonical,
            provenance=tuple(observation.provenance or ()),
        )

    def _occurrence_with_evidence(self, workspace_id, book, scope, occurrence_id):
        current = CaseScopeProjection.objects.owned_by(workspace_id).filter(
            scope=scope, current_occurrence_id=OuterRef("pk")
        )
        try:
            occurrence = (
                CaseOccurrence.objects.owned_by(workspace_id)
                .filter(case__book=book, run__scope=scope)
                .select_related("run")
                .annotate(is_current=Exists(current))
                .get(id=occurrence_id)
            )
            return self._occurrence_item(occurrence)
        except CaseOccurrence.DoesNotExist as error:
            raise ReviewQueryUnavailable from error

    @staticmethod
    def _case_label(case: InvestigationCase) -> str:
        if case.kind == "PAIR":
            return (
                f"{case.left_logical.source_record_key} ↔ "
                f"{case.right_logical.source_record_key}"
            )
        if case.kind == "UNPAIRED":
            return f"{case.record_logical.source_record_key} · {case.record_side.lower()}"
        left_count = len(case.ambiguity_left_logical_ids or ())
        right_count = len(case.ambiguity_right_logical_ids or ())
        return f"Ambiguous set · {left_count} left / {right_count} right"

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
