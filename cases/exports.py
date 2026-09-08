"""Workspace-scoped case exports with explicit view semantics."""

from __future__ import annotations

import csv
import io
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Iterable
from uuid import UUID

from django.db.models import Q, QuerySet

from reconciliation.domain import BookId, WorkspaceId
from reconciliation.models import ReconciliationRun
from reconciliation.querying import ReviewQueryUnavailable

from .models import CaseOccurrence, CaseScopeProjection
from .queries import CaseQueryService


EXPORT_FIELDS = (
    "export_view",
    "run_id",
    "run_freshness",
    "run_created_at_utc",
    "case_id",
    "case_kind",
    "result_kind",
    "left_reference",
    "left_executed_at_utc",
    "left_quantity",
    "left_unit_price",
    "left_gross_amount",
    "left_currency",
    "right_reference",
    "right_executed_at_utc",
    "right_quantity",
    "right_unit_price",
    "right_gross_amount",
    "right_currency",
    "pair_origin",
    "review_health",
    "review_attention",
    "review_state_as_of_utc",
)


@dataclass(frozen=True, slots=True)
class CaseExportRow:
    export_view: str
    run_id: str
    run_freshness: str
    run_created_at_utc: str
    case_id: str
    case_kind: str
    result_kind: str
    left_reference: str
    left_executed_at_utc: str
    left_quantity: str
    left_unit_price: str
    left_gross_amount: str
    left_currency: str
    right_reference: str
    right_executed_at_utc: str
    right_quantity: str
    right_unit_price: str
    right_gross_amount: str
    right_currency: str
    pair_origin: str
    review_health: str
    review_attention: str
    review_state_as_of_utc: str


@dataclass(frozen=True, slots=True)
class CaseExportDocument:
    view: str
    timezone: str
    decimal_encoding: str
    run_id: str
    rows: tuple[CaseExportRow, ...]

    def json_payload(self) -> dict:
        return {
            "view": self.view,
            "timezone": self.timezone,
            "decimal_encoding": self.decimal_encoding,
            "run_id": self.run_id,
            "total": len(self.rows),
            "rows": [asdict(item) for item in self.rows],
        }

    def csv_text(self) -> str:
        stream = io.StringIO(newline="")
        writer = csv.DictWriter(stream, fieldnames=EXPORT_FIELDS, lineterminator="\r\n")
        writer.writeheader()
        for row in self.rows:
            writer.writerow(
                {key: formula_safe_csv_cell(value) for key, value in asdict(row).items()}
            )
        return stream.getvalue()


def formula_safe_csv_cell(value: object) -> str:
    text = "" if value is None else str(value)
    if text.startswith(("=", "+", "-", "@", "\t", "\r")):
        return f"'{text}"
    return text


class CaseExportService:
    def build(
        self,
        workspace_id: WorkspaceId,
        *,
        book_id: BookId,
        scope_id: UUID | str,
        view: str,
        run_id: UUID | str | None = None,
        search: str | None = None,
        kind: str | None = None,
        review: str | None = None,
        sort: str = "oldest",
    ) -> CaseExportDocument:
        _book, scope = CaseQueryService()._context(workspace_id, book_id, scope_id)
        search_value, kind_value, review_value, sort_value = (
            CaseQueryService._case_filters(
                search=search,
                kind=kind,
                review=review,
                sort=sort,
            )
        )
        if view == "current_review":
            if scope.current_run_id is None:
                raise ReviewQueryUnavailable
            projections = self._current_projections(
                workspace_id,
                scope,
                search=search_value,
                kind=kind_value,
                review=review_value,
                sort=sort_value,
            )
            rows = tuple(
                self._row(
                    item.current_occurrence,
                    export_view=view,
                    review_health=item.review_health or "UNREVIEWED",
                    review_attention=", ".join(item.attention),
                    review_state_as_of=item.updated_at,
                )
                for item in projections
            )
            resolved_run_id = str(scope.current_run_id or "")
        elif view == "run_facts":
            if review_value:
                raise ReviewQueryUnavailable
            run = self._run(workspace_id, scope.id, run_id)
            occurrences = self._run_occurrences(
                workspace_id,
                run,
                search=search_value,
                kind=kind_value,
                sort=sort_value,
            )
            rows = tuple(
                self._row(
                    item,
                    export_view=view,
                    review_health="",
                    review_attention="",
                    review_state_as_of=None,
                )
                for item in occurrences
            )
            resolved_run_id = str(run.id)
        else:
            raise ReviewQueryUnavailable
        return CaseExportDocument(
            view=view,
            timezone="UTC (+00:00)",
            decimal_encoding="canonical decimal strings",
            run_id=resolved_run_id,
            rows=rows,
        )

    @staticmethod
    def _current_projections(
        workspace_id: WorkspaceId,
        scope,
        *,
        search: str,
        kind: str,
        review: str,
        sort: str,
    ) -> QuerySet:
        queryset = CaseScopeProjection.objects.owned_by(workspace_id).filter(scope=scope)
        queryset = _filter_cases(queryset, search=search, kind=kind)
        if review == "UNREVIEWED":
            queryset = queryset.filter(review_health__isnull=True)
        elif review:
            queryset = queryset.filter(review_health=review)
        return queryset.select_related(*_projection_relations()).order_by(
            "-case__created_at" if sort == "newest" else "case__created_at",
            "-case_id" if sort == "newest" else "case_id",
        )

    @staticmethod
    def _run_occurrences(
        workspace_id: WorkspaceId,
        run: ReconciliationRun,
        *,
        search: str,
        kind: str,
        sort: str,
    ) -> QuerySet:
        queryset = CaseOccurrence.objects.owned_by(workspace_id).filter(run=run)
        queryset = _filter_cases(queryset, search=search, kind=kind)
        return queryset.select_related(*_occurrence_relations()).order_by(
            "-case__created_at" if sort == "newest" else "case__created_at",
            "-case_id" if sort == "newest" else "case_id",
        )

    @staticmethod
    def _run(
        workspace_id: WorkspaceId,
        scope_id: UUID,
        run_id: UUID | str | None,
    ) -> ReconciliationRun:
        try:
            public_id = run_id if isinstance(run_id, UUID) else UUID(str(run_id))
            return ReconciliationRun.objects.owned_by(workspace_id).get(
                id=public_id,
                scope_id=scope_id,
                lifecycle="COMPLETED",
            )
        except (TypeError, ValueError, ReconciliationRun.DoesNotExist) as error:
            raise ReviewQueryUnavailable from error

    @staticmethod
    def _row(
        occurrence: CaseOccurrence,
        *,
        export_view: str,
        review_health: str,
        review_attention: str,
        review_state_as_of: datetime | None,
    ) -> CaseExportRow:
        left = right = None
        pair_origin = ""
        if occurrence.pair_id:
            left = occurrence.pair.left_observation
            right = occurrence.pair.right_observation
            pair_origin = occurrence.pair.origin
        elif occurrence.unpaired_id:
            if occurrence.unpaired.side == "LEFT":
                left = occurrence.unpaired.observation
            else:
                right = occurrence.unpaired.observation
        left_values = _observation_values(left)
        right_values = _observation_values(right)
        return CaseExportRow(
            export_view=export_view,
            run_id=str(occurrence.run_id),
            run_freshness=occurrence.run.freshness,
            run_created_at_utc=_utc(occurrence.run.created_at),
            case_id=str(occurrence.case_id),
            case_kind=occurrence.case.kind,
            result_kind=occurrence.result_kind,
            left_reference=left_values[0],
            left_executed_at_utc=left_values[1],
            left_quantity=left_values[2],
            left_unit_price=left_values[3],
            left_gross_amount=left_values[4],
            left_currency=left_values[5],
            right_reference=right_values[0],
            right_executed_at_utc=right_values[1],
            right_quantity=right_values[2],
            right_unit_price=right_values[3],
            right_gross_amount=right_values[4],
            right_currency=right_values[5],
            pair_origin=pair_origin,
            review_health=review_health,
            review_attention=review_attention,
            review_state_as_of_utc=(
                _utc(review_state_as_of) if review_state_as_of is not None else ""
            ),
        )


def _filter_cases(queryset: QuerySet, *, search: str, kind: str) -> QuerySet:
    if search:
        queryset = queryset.filter(
            Q(case__stable_key__icontains=search)
            | Q(case__left_logical__source_record_key__icontains=search)
            | Q(case__right_logical__source_record_key__icontains=search)
            | Q(case__record_logical__source_record_key__icontains=search)
        )
    if kind:
        queryset = queryset.filter(case__kind=kind)
    return queryset


def _projection_relations() -> Iterable[str]:
    return (
        "case",
        "current_occurrence__run",
        "current_occurrence__pair__left_observation__logical_transaction",
        "current_occurrence__pair__right_observation__logical_transaction",
        "current_occurrence__unpaired__observation__logical_transaction",
    )


def _occurrence_relations() -> Iterable[str]:
    return (
        "case",
        "run",
        "pair__left_observation__logical_transaction",
        "pair__right_observation__logical_transaction",
        "unpaired__observation__logical_transaction",
    )


def _observation_values(observation) -> tuple[str, str, str, str, str, str]:
    if observation is None:
        return "", "", "", "", "", ""
    return (
        observation.logical_transaction.source_record_key,
        _utc(observation.executed_at_utc),
        str(observation.quantity),
        str(observation.unit_price),
        str(observation.gross_amount),
        observation.currency,
    )


def _utc(value: datetime) -> str:
    return value.astimezone(UTC).isoformat()
