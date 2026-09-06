"""Explainable CSV-to-canonical preview and atomic preview persistence."""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, TypeVar
from uuid import UUID

from django.db import transaction
from django.utils import timezone

from reconciliation.domain import (
    CanonicalRow,
    CanonicalSide,
    CanonicalState,
    DatasetMode,
    FieldInterpretationError,
    FieldProvenance,
    IngestionOperation,
    RawCell,
    RawCellKind,
    RowErrorCode,
    RowIssue,
    SourceContract,
    SemanticInputRow,
    SemanticValue,
    SemanticValueTag,
    canonical_datetime,
    canonical_decimal,
    mapping_revision_digest,
    WorkspaceId,
    parse_datetime_value,
    parse_decimal_value,
    parse_enum_value,
    parse_required_text,
    semantic_input_hash,
    semantic_row_from_canonical,
    source_contract_digest,
)
from sources.adapters import InvalidSourceContract, contract_from_payload
from sources.models import SourceContractRevision
from sources.repositories import WorkspaceSourceRepository
from workspaces.lifecycle import WorkspaceLifecycleService
from workspaces.repositories import WorkspaceRepository

from .artifacts import (
    IntakeLimits,
    PrivateArtifactStore,
    read_bounded_csv,
)
from .models import AttemptState, IngestionAttempt
from .repositories import (
    IngestionResourceUnavailable,
    WorkspaceIngestionRepository,
)
from .services import configured_artifact_store, configured_intake_limits


T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class InterpretedRow:
    row_number: int
    raw_values: tuple[dict[str, Any], ...]
    canonical: CanonicalRow | None
    canonical_preview: dict[str, Any] | None
    issues: tuple[RowIssue, ...]


@dataclass(frozen=True, slots=True)
class InterpretedPreview:
    header: tuple[str, ...]
    rows: tuple[InterpretedRow, ...]
    issues: tuple[RowIssue, ...]

    @property
    def error_count(self) -> int:
        return len(self.issues) + sum(len(row.issues) for row in self.rows)


@dataclass(slots=True)
class PreviewService:
    store: PrivateArtifactStore
    limits: IntakeLimits
    clock: Callable[[], datetime] = timezone.now
    lifecycle_service: WorkspaceLifecycleService = field(
        default_factory=WorkspaceLifecycleService
    )

    @classmethod
    def configured(cls) -> PreviewService:
        return cls(configured_artifact_store(), configured_intake_limits())

    def preview(
        self,
        workspace_id: WorkspaceId,
        *,
        artifact_id: UUID,
        dataset_id: UUID,
        contract_revision_id: UUID,
        delimiter: str,
    ) -> IngestionAttempt:
        workspace = WorkspaceRepository().get(workspace_id)
        self.lifecycle_service.require_active(workspace, now=self.clock())
        repository = WorkspaceIngestionRepository(workspace_id)
        artifact = repository.get_artifact(artifact_id)
        dataset = repository.get_dataset(dataset_id)
        contract_revision = WorkspaceSourceRepository(workspace_id).get_contract(
            contract_revision_id
        )
        if dataset.book_source.source_id != contract_revision.source_id:
            raise IngestionResourceUnavailable
        contract = contract_from_payload(contract_revision.contract)
        self._verify_revision_contract(contract_revision, contract)
        if contract.mode is not DatasetMode.FULL_SNAPSHOT:
            raise InvalidSourceContract("delta preview is implemented in ING-T08")

        path = self.store.resolve(artifact.storage_key)
        interpreted = interpret_csv(
            path,
            delimiter=delimiter,
            limits=self.limits,
            contract=contract,
        )
        state = AttemptState.READY if interpreted.error_count == 0 else AttemptState.REJECTED
        semantic_hash = semantic_input_hash(
            contract_digest=contract_revision.digest,
            header=interpreted.header,
            rows=(_semantic_row(row) for row in interpreted.rows),
        )
        completed_at = self.clock()
        with transaction.atomic():
            attempt = repository.create_attempt(
                artifact_id=artifact.id,
                dataset_id=dataset.id,
                contract_revision_id=contract_revision.id,
                expected_base_id=dataset.current_revision_id,
                state=state,
                physical_hash=artifact.physical_hash,
                semantic_hash=semantic_hash,
                delimiter=delimiter,
                row_count=len(interpreted.rows),
                error_count=interpreted.error_count,
                created_at=completed_at,
                completed_at=completed_at,
                validation=[issue_to_payload(issue) for issue in interpreted.issues],
            )
            repository.create_raw_rows(
                attempt_id=attempt.id,
                rows=(
                    {
                        "row_number": row.row_number,
                        "raw_values": list(row.raw_values),
                        "canonical_preview": row.canonical_preview,
                        "validation": [
                            issue_to_payload(issue) for issue in row.issues
                        ],
                    }
                    for row in interpreted.rows
                ),
            )
        return attempt

    @staticmethod
    def _verify_revision_contract(
        revision: SourceContractRevision,
        contract: SourceContract,
    ) -> None:
        if (
            revision.digest != source_contract_digest(revision.contract)
            or revision.mapping_revision.digest
            != mapping_revision_digest(revision.mapping_revision.mapping)
            or revision.mapping_revision.mapping.get("bindings")
            != revision.contract.get("bindings")
            or revision.mode != contract.mode
            or revision.timezone_name != contract.timezone_name
            or revision.identity_namespace != contract.identity_namespace
            or revision.reference_semantics != contract.reference_semantics
        ):
            raise InvalidSourceContract(
                "stored source contract metadata does not match its payload"
            )


def interpret_csv(
    path: Path,
    *,
    delimiter: str,
    limits: IntakeLimits,
    contract: SourceContract,
) -> InterpretedPreview:
    content = read_bounded_csv(path, delimiter=delimiter, limits=limits)
    header = content.scan.header
    header_issues = _header_issues(header, contract)
    rows = tuple(
        _interpret_row(
            row_number=index + 2,
            header=header,
            values=values,
            contract=contract,
            blocked=bool(header_issues),
        )
        for index, values in enumerate(content.rows)
    )
    rows = _mark_duplicate_source_keys(rows)
    return InterpretedPreview(header, rows, header_issues)


def _header_issues(
    header: tuple[str, ...],
    contract: SourceContract,
) -> tuple[RowIssue, ...]:
    issues: list[RowIssue] = []
    counts = Counter(header)
    for name, count in counts.items():
        if count > 1:
            issues.append(
                RowIssue(
                    1,
                    name or "_header",
                    RowErrorCode.DUPLICATE_HEADER,
                    name,
                    "a unique column header",
                )
            )
    required = {
        binding.source_column
        for binding in contract.bindings
        if binding.source_column is not None
    }
    required.update(
        [contract.operation_field] if contract.operation_field is not None else []
    )
    for name in sorted(required - set(header)):
        issues.append(
            RowIssue(
                1,
                name,
                RowErrorCode.MISSING_COLUMN,
                None,
                f"source column {name}",
            )
        )
    return tuple(issues)


def _interpret_row(
    *,
    row_number: int,
    header: tuple[str, ...],
    values: tuple[str, ...],
    contract: SourceContract,
    blocked: bool,
) -> InterpretedRow:
    raw_values = _raw_values(header, values, null_tokens=contract.null_tokens)
    if blocked:
        return InterpretedRow(row_number, raw_values, None, None, ())

    cells = {
        item["column"]: RawCell.from_source(
            item["original"],
            null_tokens=contract.null_tokens,
        )
        if item["kind"] != "MISSING"
        else RawCell.missing()
        for item in raw_values
        if not item["column"].startswith("__extra_")
    }
    issues: list[RowIssue] = []
    if len(values) > len(header):
        issues.append(
            RowIssue(
                row_number,
                "_row",
                RowErrorCode.UNEXPECTED_COLUMN,
                None,
                f"at most {len(header)} values",
            )
        )

    bindings = {binding.canonical_field: binding for binding in contract.bindings}
    enums = {mapping.canonical_field: mapping for mapping in contract.enum_mappings}
    parsed: dict[str, Any] = {}
    provenance: list[FieldProvenance] = []

    def parse(field: str, parser: Callable[[RawCell], T]) -> T | None:
        binding = bindings[field]
        cell = (
            RawCell.from_source(binding.constant)
            if binding.constant is not None
            else cells.get(binding.source_column, RawCell.missing())
        )
        try:
            value = parser(cell)
        except FieldInterpretationError as error:
            issues.append(error.issue)
            return None
        provenance.append(
            FieldProvenance(
                canonical_field=field,
                source_column=binding.source_column,
                raw_cell=cell,
                transformation="constant" if binding.constant is not None else "declared mapping",
            )
        )
        return value

    for field in ("source_record_key", "instrument", "currency"):
        parsed[field] = parse(
            field,
            lambda cell, field=field: parse_required_text(
                cell,
                row_number=row_number,
                field=field,
            ),
        )
    if "business_reference" in bindings:
        parsed["business_reference"] = parse(
            "business_reference",
            lambda cell: parse_required_text(
                cell,
                row_number=row_number,
                field="business_reference",
            ),
        )
    else:
        parsed["business_reference"] = None
    parsed["executed_at_utc"] = parse(
        "executed_at_utc",
        lambda cell: parse_datetime_value(
            cell,
            row_number=row_number,
            field="executed_at_utc",
            timestamp_format=contract.timestamp_format,
            timezone_name=contract.timezone_name,
            fold_policy=contract.fold_policy,
        ),
    )
    for field in ("quantity", "unit_price", "gross_amount"):
        parsed[field] = parse(
            field,
            lambda cell, field=field: parse_decimal_value(
                cell,
                row_number=row_number,
                field=field,
            ),
        )
    parsed["side"] = parse(
        "side",
        lambda cell: parse_enum_value(
            cell,
            row_number=row_number,
            field="side",
            mapping=tuple(
                (source, CanonicalSide(target))
                for source, target in enums["side"].values
            ),
        ),
    )
    parsed["state"] = parse(
        "state",
        lambda cell: parse_enum_value(
            cell,
            row_number=row_number,
            field="state",
            mapping=tuple(
                (source, CanonicalState(target))
                for source, target in enums["state"].values
            ),
        ),
    )
    canonical = None
    if not issues:
        canonical = CanonicalRow(
            row_number=row_number,
            source_record_key=parsed["source_record_key"],
            business_reference=parsed["business_reference"],
            executed_at_utc=parsed["executed_at_utc"],
            instrument=parsed["instrument"],
            side=parsed["side"],
            quantity=parsed["quantity"],
            unit_price=parsed["unit_price"],
            gross_amount=parsed["gross_amount"],
            currency=parsed["currency"],
            state=parsed["state"],
            operation=IngestionOperation.SNAPSHOT,
            provenance=tuple(provenance),
        )
    canonical_preview = (
        canonical_to_payload(canonical)
        if canonical is not None
        else partial_canonical_to_payload(row_number, parsed, provenance)
    )
    return InterpretedRow(
        row_number,
        raw_values,
        canonical,
        canonical_preview,
        tuple(issues),
    )


def _raw_values(
    header: tuple[str, ...],
    values: tuple[str, ...],
    *,
    null_tokens: tuple[str, ...],
) -> tuple[dict[str, Any], ...]:
    result: list[dict[str, Any]] = []
    for index in range(max(len(header), len(values))):
        column = header[index] if index < len(header) else f"__extra_{index - len(header) + 1}"
        cell = (
            RawCell.from_source(values[index], null_tokens=null_tokens)
            if index < len(values)
            else RawCell.missing()
        )
        result.append(
            {
                "column": column,
                "kind": cell.kind.value,
                "original": cell.original,
            }
        )
    return tuple(result)


def _mark_duplicate_source_keys(
    rows: tuple[InterpretedRow, ...],
) -> tuple[InterpretedRow, ...]:
    positions: dict[str, list[int]] = defaultdict(list)
    for index, row in enumerate(rows):
        if row.canonical_preview is not None:
            source_key = row.canonical_preview.get("source_record_key")
            if source_key:
                positions[source_key].append(index)
    duplicate_indexes = {
        index
        for indexes in positions.values()
        if len(indexes) > 1
        for index in indexes
    }
    result = []
    for index, row in enumerate(rows):
        if index not in duplicate_indexes:
            result.append(row)
            continue
        issue = RowIssue(
            row.row_number,
            "source_record_key",
            RowErrorCode.DUPLICATE_SOURCE_KEY,
            row.canonical_preview["source_record_key"],
            "a unique source record key",
        )
        preview = {**row.canonical_preview, "complete": False}
        result.append(
            InterpretedRow(
                row.row_number,
                row.raw_values,
                None,
                preview,
                row.issues + (issue,),
            )
        )
    return tuple(result)


def issue_to_payload(issue: RowIssue) -> dict[str, Any]:
    return {
        "row_number": issue.row_number,
        "field": issue.field,
        "code": issue.code.value,
        "original_value": issue.original_value,
        "expected": issue.expected,
    }


def canonical_to_payload(row: CanonicalRow) -> dict[str, Any]:
    return {
        "complete": True,
        "row_number": row.row_number,
        "source_record_key": row.source_record_key,
        "business_reference": row.business_reference,
        "executed_at_utc": canonical_datetime(row.executed_at_utc),
        "instrument": row.instrument,
        "side": row.side.value,
        "quantity": canonical_decimal(row.quantity),
        "unit_price": canonical_decimal(row.unit_price),
        "gross_amount": canonical_decimal(row.gross_amount),
        "currency": row.currency,
        "state": row.state.value,
        "eligible_for_matching": row.eligible_for_matching,
        "operation": row.operation.value,
        "provenance": [
            {
                "canonical_field": item.canonical_field,
                "source_column": item.source_column,
                "kind": item.raw_cell.kind.value,
                "original": item.raw_cell.original,
                "transformation": item.transformation,
            }
            for item in row.provenance
        ],
    }


def partial_canonical_to_payload(
    row_number: int,
    parsed: dict[str, Any],
    provenance: list[FieldProvenance],
) -> dict[str, Any]:
    payload: dict[str, Any] = {"complete": False, "row_number": row_number}
    for field, value in parsed.items():
        if value is None and field != "business_reference":
            continue
        if isinstance(value, datetime):
            payload[field] = canonical_datetime(value)
        elif isinstance(value, Decimal):
            payload[field] = canonical_decimal(value)
        elif hasattr(value, "value"):
            payload[field] = value.value
        else:
            payload[field] = value
    payload["provenance"] = [
        {
            "canonical_field": item.canonical_field,
            "source_column": item.source_column,
            "kind": item.raw_cell.kind.value,
            "original": item.raw_cell.original,
            "transformation": item.transformation,
        }
        for item in provenance
    ]
    return payload


def _semantic_row(row: InterpretedRow) -> SemanticInputRow:
    if row.canonical is not None:
        return semantic_row_from_canonical(row.canonical)

    preview = row.canonical_preview or {}
    required = {
        "source_record_key",
        "executed_at_utc",
        "instrument",
        "side",
        "quantity",
        "unit_price",
        "gross_amount",
        "currency",
        "state",
        "operation",
    }
    if required <= preview.keys():
        tags = {
            "source_record_key": SemanticValueTag.TEXT,
            "business_reference": SemanticValueTag.TEXT,
            "executed_at_utc": SemanticValueTag.DATETIME,
            "instrument": SemanticValueTag.TEXT,
            "side": SemanticValueTag.ENUM,
            "quantity": SemanticValueTag.DECIMAL,
            "unit_price": SemanticValueTag.DECIMAL,
            "gross_amount": SemanticValueTag.DECIMAL,
            "currency": SemanticValueTag.TEXT,
            "state": SemanticValueTag.ENUM,
        }
        fields = tuple(
            (
                name,
                SemanticValue(tags[name], "" if value is None else str(value)),
            )
            for name, value in preview.items()
            if name in tags
        )
        return SemanticInputRow(str(preview["operation"]), fields)

    return SemanticInputRow(
        "UNRESOLVED",
        tuple(
            (
                f"{index}:{item['column']}",
                SemanticValue.from_raw(
                    RawCellKind(item["kind"]),
                    item["original"],
                ),
            )
            for index, item in enumerate(row.raw_values)
        ),
    )
