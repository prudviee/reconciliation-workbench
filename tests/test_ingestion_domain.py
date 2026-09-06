from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from reconciliation.domain import (
    CanonicalRow,
    CanonicalSide,
    CanonicalState,
    DatasetMode,
    DateFoldPolicy,
    DomainValidationError,
    EnumMapping,
    FieldBinding,
    FieldInterpretationError,
    FieldProvenance,
    IngestionOperation,
    RawCell,
    RawCellKind,
    ReferenceSemantics,
    RowErrorCode,
    SourceContract,
    parse_datetime_value,
    parse_decimal_value,
    parse_enum_value,
    parse_required_text,
)


def issue_from(callable_value) -> object:
    with pytest.raises(FieldInterpretationError) as captured:
        callable_value()
    return captured.value.issue


def minimal_contract(**overrides: object) -> SourceContract:
    values: dict[str, object] = {
        "adapter_key": "ledger-v1",
        "parser_version": "1",
        "mode": DatasetMode.FULL_SNAPSHOT,
        "identity_namespace": "ledger-trade",
        "reference_semantics": ReferenceSemantics.TRUSTED_SHARED,
        "timestamp_format": "ISO8601",
        "timezone_name": None,
        "bindings": (
            FieldBinding("source_record_key", source_column="trade_id"),
            FieldBinding("currency", constant="USD"),
        ),
        "enum_mappings": (
            EnumMapping("side", (("BUY", "BUY"), ("SELL", "SELL"))),
        ),
    }
    values.update(overrides)
    return SourceContract(**values)  # type: ignore[arg-type]


def test_raw_cell_tags_preserve_missing_null_empty_and_value() -> None:
    cells = (
        RawCell.missing(),
        RawCell.from_source("NULL", null_tokens=("NULL",)),
        RawCell.from_source(""),
        RawCell.from_source(" 100.00 "),
    )

    assert [cell.kind for cell in cells] == [
        RawCellKind.MISSING,
        RawCellKind.NULL,
        RawCellKind.EMPTY,
        RawCellKind.VALUE,
    ]
    assert [cell.semantic_value() for cell in cells] == [
        ("MISSING", None),
        ("NULL", "NULL"),
        ("EMPTY", ""),
        ("VALUE", " 100.00 "),
    ]


@pytest.mark.parametrize(
    ("cell", "code"),
    [
        (RawCell.missing(), RowErrorCode.MISSING_FIELD),
        (RawCell.from_source("NULL", null_tokens=("NULL",)), RowErrorCode.NULL_REQUIRED),
        (RawCell.from_source(""), RowErrorCode.EMPTY_REQUIRED),
        (RawCell.from_source("   "), RowErrorCode.EMPTY_REQUIRED),
    ],
)
def test_required_text_reports_tagged_failure_with_row_and_original(
    cell: RawCell, code: RowErrorCode
) -> None:
    issue = issue_from(
        lambda: parse_required_text(cell, row_number=7, field="trade_id")
    )

    assert issue.code is code
    assert issue.row_number == 7
    assert issue.field == "trade_id"
    assert issue.original_value == cell.original


def test_required_text_trims_only_when_declared() -> None:
    cell = RawCell.from_source(" BTC-USD ")

    assert parse_required_text(cell, row_number=1, field="instrument") == "BTC-USD"
    assert (
        parse_required_text(
            cell, row_number=1, field="instrument", trim=False
        )
        == " BTC-USD "
    )


@pytest.mark.parametrize(
    "source",
    [
        "99999999999999999999999999.999999999999",
        "0.000000000001",
        "-31000.00",
        "1E+25",
    ],
)
def test_decimal_parser_accepts_numeric_38_12_boundaries(source: str) -> None:
    parsed = parse_decimal_value(
        RawCell.from_source(source), row_number=2, field="gross_amount"
    )

    assert parsed == Decimal(source)


@pytest.mark.parametrize(
    ("source", "code"),
    [
        ("NaN", RowErrorCode.NON_FINITE_DECIMAL),
        ("Infinity", RowErrorCode.NON_FINITE_DECIMAL),
        ("not-money", RowErrorCode.INVALID_DECIMAL),
        ("1.0000000000001", RowErrorCode.UNSUPPORTED_PRECISION),
        ("999999999999999999999999999.000000000000", RowErrorCode.UNSUPPORTED_PRECISION),
        ("1E+38", RowErrorCode.UNSUPPORTED_PRECISION),
    ],
)
def test_decimal_parser_refuses_invalid_nonfinite_or_overprecision(
    source: str, code: RowErrorCode
) -> None:
    issue = issue_from(
        lambda: parse_decimal_value(
            RawCell.from_source(source), row_number=3, field="gross_amount"
        )
    )

    assert issue.code is code
    assert issue.original_value == source
    assert "38 total digits" in issue.expected if code is RowErrorCode.UNSUPPORTED_PRECISION else True


def test_iso_datetime_with_offset_normalizes_to_utc() -> None:
    parsed = parse_datetime_value(
        RawCell.from_source("2026-09-06T12:30:00+05:30"),
        row_number=1,
        field="traded_at",
        timestamp_format="ISO8601",
        timezone_name=None,
    )

    assert parsed == datetime(2026, 9, 6, 7, 0, tzinfo=UTC)


def test_naive_datetime_requires_and_uses_explicit_timezone() -> None:
    cell = RawCell.from_source("2025-07-01 09:15:00")

    missing = issue_from(
        lambda: parse_datetime_value(
            cell,
            row_number=2,
            field="executed_at",
            timestamp_format="%Y-%m-%d %H:%M:%S",
            timezone_name=None,
        )
    )
    parsed = parse_datetime_value(
        cell,
        row_number=2,
        field="executed_at",
        timestamp_format="%Y-%m-%d %H:%M:%S",
        timezone_name="UTC",
    )

    assert missing.code is RowErrorCode.MISSING_TIMEZONE
    assert parsed == datetime(2025, 7, 1, 9, 15, tzinfo=UTC)


def test_ambiguous_local_datetime_rejects_without_explicit_fold() -> None:
    cell = RawCell.from_source("2026-11-01 01:30:00")
    arguments = {
        "row_number": 9,
        "field": "executed_at",
        "timestamp_format": "%Y-%m-%d %H:%M:%S",
        "timezone_name": "America/New_York",
    }

    issue = issue_from(lambda: parse_datetime_value(cell, **arguments))
    earlier = parse_datetime_value(
        cell, **arguments, fold_policy=DateFoldPolicy.EARLIER
    )
    later = parse_datetime_value(cell, **arguments, fold_policy=DateFoldPolicy.LATER)

    assert issue.code is RowErrorCode.AMBIGUOUS_DATETIME
    assert earlier == datetime(2026, 11, 1, 5, 30, tzinfo=UTC)
    assert later == datetime(2026, 11, 1, 6, 30, tzinfo=UTC)


def test_nonexistent_local_datetime_is_rejected() -> None:
    issue = issue_from(
        lambda: parse_datetime_value(
            RawCell.from_source("2026-03-08 02:30:00"),
            row_number=4,
            field="executed_at",
            timestamp_format="%Y-%m-%d %H:%M:%S",
            timezone_name="America/New_York",
        )
    )

    assert issue.code is RowErrorCode.NONEXISTENT_DATETIME


def test_enum_mapping_is_explicit_and_unknown_value_is_preserved() -> None:
    mapping = (("B", CanonicalSide.BUY), ("S", CanonicalSide.SELL))

    assert (
        parse_enum_value(
            RawCell.from_source("B"), row_number=1, field="direction", mapping=mapping
        )
        is CanonicalSide.BUY
    )
    issue = issue_from(
        lambda: parse_enum_value(
            RawCell.from_source("BUY"),
            row_number=5,
            field="direction",
            mapping=mapping,
        )
    )
    assert issue.code is RowErrorCode.UNKNOWN_ENUM
    assert issue.original_value == "BUY"
    assert issue.expected == "one of: B, S"


def test_contract_is_immutable_and_requires_explicit_delta_operations() -> None:
    contract = minimal_contract()

    with pytest.raises(FrozenInstanceError):
        contract.mode = DatasetMode.DELTA  # type: ignore[misc]
    with pytest.raises(DomainValidationError, match="delta contract requires"):
        minimal_contract(mode=DatasetMode.DELTA)

    delta = minimal_contract(
        mode=DatasetMode.DELTA,
        operation_field="operation",
        operation_mapping=(
            ("UPSERT", IngestionOperation.UPSERT),
            ("CANCEL", IngestionOperation.CANCEL),
            ("RETRACT", IngestionOperation.RETRACT),
        ),
    )
    assert delta.mode is DatasetMode.DELTA


def test_full_snapshot_refuses_delta_mapping_and_contract_validates_timezone() -> None:
    with pytest.raises(DomainValidationError, match="full snapshot"):
        minimal_contract(
            operation_field="operation",
            operation_mapping=(("UPSERT", IngestionOperation.UPSERT),),
        )
    with pytest.raises(DomainValidationError, match="IANA"):
        minimal_contract(timezone_name="Mars/Olympus_Mons")


def test_delta_contract_requires_all_three_explicit_operation_meanings() -> None:
    with pytest.raises(DomainValidationError, match="distinguish"):
        minimal_contract(
            mode=DatasetMode.DELTA,
            operation_field="operation",
            operation_mapping=(("UPSERT", IngestionOperation.UPSERT),),
        )


def test_contract_refuses_ambiguous_null_and_enum_tokens() -> None:
    with pytest.raises(DomainValidationError, match="null tokens"):
        minimal_contract(null_tokens=("",))
    with pytest.raises(DomainValidationError, match="enum source"):
        minimal_contract(enum_mappings=(EnumMapping("side", ((" ", "BUY"),)),))
    with pytest.raises(DomainValidationError, match="canonical values"):
        minimal_contract(enum_mappings=(EnumMapping("side", (("B", " "),)),))
    with pytest.raises(DomainValidationError, match="IANA"):
        minimal_contract(timezone_name=" ")
    with pytest.raises(DomainValidationError, match="operation source"):
        minimal_contract(
            mode=DatasetMode.DELTA,
            operation_field="operation",
            operation_mapping=(
                (" ", IngestionOperation.UPSERT),
                ("CANCEL", IngestionOperation.CANCEL),
                ("RETRACT", IngestionOperation.RETRACT),
            ),
        )


def canonical_row(*, state: CanonicalState, operation: IngestionOperation) -> CanonicalRow:
    return CanonicalRow(
        row_number=6,
        source_record_key="T-1018",
        business_reference="T-1018",
        executed_at_utc=datetime(2025, 7, 6, 15, tzinfo=UTC),
        instrument="SOL-USD",
        side=CanonicalSide.BUY,
        quantity=Decimal("100.00"),
        unit_price=Decimal("149.00"),
        gross_amount=Decimal("14900.00"),
        currency="USD",
        state=state,
        operation=operation,
        provenance=(
            FieldProvenance(
                canonical_field="state",
                source_column="state",
                raw_cell=RawCell.from_source(state.value),
                transformation="exact enum mapping",
            ),
        ),
    )


def test_cancelled_rows_are_immutable_evidence_but_ineligible_for_matching() -> None:
    settled = canonical_row(
        state=CanonicalState.SETTLED,
        operation=IngestionOperation.SNAPSHOT,
    )
    cancelled = canonical_row(
        state=CanonicalState.CANCELLED,
        operation=IngestionOperation.SNAPSHOT,
    )

    assert settled.eligible_for_matching is True
    assert cancelled.eligible_for_matching is False
    with pytest.raises(FrozenInstanceError):
        cancelled.state = CanonicalState.SETTLED  # type: ignore[misc]


def test_cancel_operation_requires_cancelled_state_and_retract_has_no_observation() -> None:
    with pytest.raises(DomainValidationError, match="requires cancelled state"):
        canonical_row(
            state=CanonicalState.SETTLED,
            operation=IngestionOperation.CANCEL,
        )
    with pytest.raises(DomainValidationError, match="does not create"):
        canonical_row(
            state=CanonicalState.CANCELLED,
            operation=IngestionOperation.RETRACT,
        )


def test_provenance_projection_is_read_only() -> None:
    row = canonical_row(
        state=CanonicalState.SETTLED,
        operation=IngestionOperation.SNAPSHOT,
    )
    projection = row.provenance_by_field

    assert projection["state"].raw_cell.original == "SETTLED"
    with pytest.raises(TypeError):
        projection["state"] = projection["state"]  # type: ignore[index]


def test_canonical_row_refuses_duplicate_provenance_fields() -> None:
    item = FieldProvenance(
        canonical_field="state",
        source_column="state",
        raw_cell=RawCell.from_source("SETTLED"),
        transformation="exact enum mapping",
    )
    row = canonical_row(
        state=CanonicalState.SETTLED,
        operation=IngestionOperation.SNAPSHOT,
    )

    with pytest.raises(DomainValidationError, match="provenance fields"):
        CanonicalRow(
            row_number=row.row_number,
            source_record_key=row.source_record_key,
            business_reference=row.business_reference,
            executed_at_utc=row.executed_at_utc,
            instrument=row.instrument,
            side=row.side,
            quantity=row.quantity,
            unit_price=row.unit_price,
            gross_amount=row.gross_amount,
            currency=row.currency,
            state=row.state,
            operation=row.operation,
            provenance=(item, item),
        )
