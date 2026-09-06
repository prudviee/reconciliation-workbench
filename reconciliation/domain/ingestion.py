"""Pure source-contract and canonical ingestion values."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from types import MappingProxyType
from typing import Never, TypeVar
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .workspaces import DomainValidationError


MAX_NUMERIC_PRECISION = 38
MAX_NUMERIC_SCALE = 12


class DatasetMode(StrEnum):
    FULL_SNAPSHOT = "FULL_SNAPSHOT"
    DELTA = "DELTA"


class IngestionOperation(StrEnum):
    SNAPSHOT = "SNAPSHOT"
    UPSERT = "UPSERT"
    CANCEL = "CANCEL"
    RETRACT = "RETRACT"


class ReferenceSemantics(StrEnum):
    TRUSTED_SHARED = "TRUSTED_SHARED"
    SECONDARY = "SECONDARY"
    NONE = "NONE"


class RawCellKind(StrEnum):
    MISSING = "MISSING"
    NULL = "NULL"
    EMPTY = "EMPTY"
    VALUE = "VALUE"


class CanonicalSide(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


class CanonicalState(StrEnum):
    SETTLED = "SETTLED"
    CANCELLED = "CANCELLED"


class DateFoldPolicy(StrEnum):
    REJECT = "REJECT"
    EARLIER = "EARLIER"
    LATER = "LATER"


class RowErrorCode(StrEnum):
    MISSING_COLUMN = "MISSING_COLUMN"
    DUPLICATE_HEADER = "DUPLICATE_HEADER"
    UNEXPECTED_COLUMN = "UNEXPECTED_COLUMN"
    MISSING_FIELD = "MISSING_FIELD"
    NULL_REQUIRED = "NULL_REQUIRED"
    EMPTY_REQUIRED = "EMPTY_REQUIRED"
    UNKNOWN_ENUM = "UNKNOWN_ENUM"
    INVALID_DECIMAL = "INVALID_DECIMAL"
    NON_FINITE_DECIMAL = "NON_FINITE_DECIMAL"
    UNSUPPORTED_PRECISION = "UNSUPPORTED_PRECISION"
    INVALID_DATETIME = "INVALID_DATETIME"
    MISSING_TIMEZONE = "MISSING_TIMEZONE"
    AMBIGUOUS_DATETIME = "AMBIGUOUS_DATETIME"
    NONEXISTENT_DATETIME = "NONEXISTENT_DATETIME"
    DUPLICATE_SOURCE_KEY = "DUPLICATE_SOURCE_KEY"
    INVALID_OPERATION = "INVALID_OPERATION"


@dataclass(frozen=True, slots=True)
class RawCell:
    kind: RawCellKind
    original: str | None

    def __post_init__(self) -> None:
        if self.kind is RawCellKind.MISSING and self.original is not None:
            raise DomainValidationError("a missing cell cannot contain a value")
        if self.kind is RawCellKind.EMPTY and self.original != "":
            raise DomainValidationError("an empty cell must preserve an empty string")
        if self.kind in {RawCellKind.NULL, RawCellKind.VALUE} and not isinstance(self.original, str):
            raise DomainValidationError(
                f"a {self.kind.value.lower()} cell must preserve source text"
            )
        if self.kind is RawCellKind.NULL and self.original == "":
            raise DomainValidationError("a null cell token must not be empty")

    @classmethod
    def missing(cls) -> RawCell:
        return cls(RawCellKind.MISSING, None)

    @classmethod
    def from_source(
        cls,
        value: str,
        *,
        null_tokens: tuple[str, ...] = (),
    ) -> RawCell:
        if value == "":
            return cls(RawCellKind.EMPTY, value)
        if value in null_tokens:
            return cls(RawCellKind.NULL, value)
        return cls(RawCellKind.VALUE, value)

    def semantic_value(self) -> tuple[str, str | None]:
        return (self.kind.value, self.original)


@dataclass(frozen=True, slots=True)
class RowIssue:
    row_number: int
    field: str
    code: RowErrorCode
    original_value: str | None
    expected: str

    def __post_init__(self) -> None:
        if (
            isinstance(self.row_number, bool)
            or not isinstance(self.row_number, int)
            or self.row_number < 1
        ):
            raise DomainValidationError("row_number must be a positive integer")
        if not self.field.strip():
            raise DomainValidationError("field must not be blank")
        if not self.expected.strip():
            raise DomainValidationError("expected must not be blank")


@dataclass(frozen=True, slots=True)
class FieldInterpretationError(ValueError):
    issue: RowIssue

    def __str__(self) -> str:
        return f"row {self.issue.row_number} {self.issue.field}: {self.issue.code.value}"


@dataclass(frozen=True, slots=True)
class FieldBinding:
    canonical_field: str
    source_column: str | None = None
    constant: str | None = None

    def __post_init__(self) -> None:
        if not self.canonical_field.strip():
            raise DomainValidationError("canonical_field must not be blank")
        if (self.source_column is None) == (self.constant is None):
            raise DomainValidationError(
                "a field binding requires exactly one source column or constant"
            )
        if self.source_column is not None and not self.source_column.strip():
            raise DomainValidationError("source_column must not be blank")


@dataclass(frozen=True, slots=True)
class EnumMapping:
    canonical_field: str
    values: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        if not self.canonical_field.strip():
            raise DomainValidationError("canonical_field must not be blank")
        source_values = [source for source, _ in self.values]
        if (
            not self.values
            or any(not source.strip() for source in source_values)
            or len(source_values) != len(set(source_values))
        ):
            raise DomainValidationError("enum source values must be nonempty and unique")
        if any(not canonical.strip() for _, canonical in self.values):
            raise DomainValidationError("enum canonical values must not be blank")


@dataclass(frozen=True, slots=True)
class SourceContract:
    adapter_key: str
    parser_version: str
    mode: DatasetMode
    identity_namespace: str
    reference_semantics: ReferenceSemantics
    timestamp_format: str
    timezone_name: str | None
    bindings: tuple[FieldBinding, ...]
    enum_mappings: tuple[EnumMapping, ...] = ()
    null_tokens: tuple[str, ...] = ()
    operation_field: str | None = None
    operation_mapping: tuple[tuple[str, IngestionOperation], ...] = ()
    fold_policy: DateFoldPolicy = DateFoldPolicy.REJECT

    def __post_init__(self) -> None:
        for name in (
            "adapter_key",
            "parser_version",
            "identity_namespace",
            "timestamp_format",
        ):
            if not getattr(self, name).strip():
                raise DomainValidationError(f"{name} must not be blank")

        canonical_fields = [binding.canonical_field for binding in self.bindings]
        if not self.bindings or len(canonical_fields) != len(set(canonical_fields)):
            raise DomainValidationError(
                "contract bindings must be nonempty and canonical fields unique"
            )
        enum_fields = [mapping.canonical_field for mapping in self.enum_mappings]
        if len(enum_fields) != len(set(enum_fields)):
            raise DomainValidationError("enum mappings must target unique fields")
        if (
            any(token == "" for token in self.null_tokens)
            or len(self.null_tokens) != len(set(self.null_tokens))
        ):
            raise DomainValidationError("null tokens must be nonempty and unique")

        if self.timezone_name is not None:
            if not self.timezone_name.strip():
                raise DomainValidationError(
                    "timezone_name must be None or a valid IANA zone"
                )
            try:
                ZoneInfo(self.timezone_name)
            except ZoneInfoNotFoundError as error:
                raise DomainValidationError("timezone_name must be a valid IANA zone") from error

        operation_values = [source for source, _ in self.operation_mapping]
        if (
            any(not source.strip() for source in operation_values)
            or len(operation_values) != len(set(operation_values))
        ):
            raise DomainValidationError(
                "operation source values must be nonempty and unique"
            )
        if self.mode is DatasetMode.FULL_SNAPSHOT:
            if self.operation_field is not None or self.operation_mapping:
                raise DomainValidationError(
                    "a full snapshot cannot declare delta operation mapping"
                )
        elif (
            not self.operation_field
            or not self.operation_field.strip()
            or not self.operation_mapping
        ):
            raise DomainValidationError(
                "a delta contract requires an operation field and mapping"
            )
        if self.mode is DatasetMode.DELTA and any(
            operation is IngestionOperation.SNAPSHOT
            for _, operation in self.operation_mapping
        ):
            raise DomainValidationError("a delta operation cannot map to SNAPSHOT")
        if self.mode is DatasetMode.DELTA and {
            operation for _, operation in self.operation_mapping
        } != {
            IngestionOperation.UPSERT,
            IngestionOperation.CANCEL,
            IngestionOperation.RETRACT,
        }:
            raise DomainValidationError(
                "a delta contract must distinguish upsert, cancel, and retract"
            )


@dataclass(frozen=True, slots=True)
class FieldProvenance:
    canonical_field: str
    source_column: str | None
    raw_cell: RawCell
    transformation: str

    def __post_init__(self) -> None:
        if not self.canonical_field.strip() or not self.transformation.strip():
            raise DomainValidationError(
                "provenance field and transformation must not be blank"
            )


@dataclass(frozen=True, slots=True)
class CanonicalRow:
    row_number: int
    source_record_key: str
    business_reference: str | None
    executed_at_utc: datetime
    instrument: str
    side: CanonicalSide
    quantity: Decimal
    unit_price: Decimal
    gross_amount: Decimal
    currency: str
    state: CanonicalState
    operation: IngestionOperation
    provenance: tuple[FieldProvenance, ...]

    def __post_init__(self) -> None:
        if (
            isinstance(self.row_number, bool)
            or not isinstance(self.row_number, int)
            or self.row_number < 1
        ):
            raise DomainValidationError("row_number must be a positive integer")
        for name in ("source_record_key", "instrument", "currency"):
            if not getattr(self, name).strip():
                raise DomainValidationError(f"{name} must not be blank")
        if self.business_reference is not None and not self.business_reference.strip():
            raise DomainValidationError("business_reference must be nonblank or None")
        if self.executed_at_utc.tzinfo is None or self.executed_at_utc.utcoffset() is None:
            raise DomainValidationError("executed_at_utc must be timezone-aware")
        object.__setattr__(self, "executed_at_utc", self.executed_at_utc.astimezone(UTC))
        for name in ("quantity", "unit_price", "gross_amount"):
            validate_numeric_value(getattr(self, name), name=name)
        if self.operation is IngestionOperation.RETRACT:
            raise DomainValidationError("a retraction does not create a canonical observation")
        if (
            self.operation is IngestionOperation.CANCEL
            and self.state is not CanonicalState.CANCELLED
        ):
            raise DomainValidationError("a cancellation operation requires cancelled state")
        provenance_fields = [item.canonical_field for item in self.provenance]
        if len(provenance_fields) != len(set(provenance_fields)):
            raise DomainValidationError("provenance fields must be unique")

    @property
    def eligible_for_matching(self) -> bool:
        return self.state is not CanonicalState.CANCELLED

    @property
    def provenance_by_field(self) -> MappingProxyType[str, FieldProvenance]:
        return MappingProxyType(
            {item.canonical_field: item for item in self.provenance}
        )


T = TypeVar("T", bound=StrEnum)


def parse_required_text(
    cell: RawCell,
    *,
    row_number: int,
    field: str,
    trim: bool = True,
) -> str:
    value = _required_source_value(cell, row_number=row_number, field=field)
    parsed = value.strip() if trim else value
    if parsed == "":
        _raise_issue(
            row_number,
            field,
            RowErrorCode.EMPTY_REQUIRED,
            cell,
            "a nonempty text value",
        )
    return parsed


def parse_decimal_value(
    cell: RawCell,
    *,
    row_number: int,
    field: str,
) -> Decimal:
    source = _required_source_value(cell, row_number=row_number, field=field)
    try:
        value = Decimal(source.strip())
    except InvalidOperation:
        _raise_issue(
            row_number,
            field,
            RowErrorCode.INVALID_DECIMAL,
            cell,
            "a base-10 decimal",
        )
    if not value.is_finite():
        _raise_issue(
            row_number,
            field,
            RowErrorCode.NON_FINITE_DECIMAL,
            cell,
            "a finite decimal",
        )
    try:
        validate_numeric_value(value, name=field)
    except DomainValidationError:
        _raise_issue(
            row_number,
            field,
            RowErrorCode.UNSUPPORTED_PRECISION,
            cell,
            "at most 38 total digits and 12 fractional digits",
        )
    return value


def validate_numeric_value(value: Decimal, *, name: str) -> None:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise DomainValidationError(f"{name} must be a finite Decimal")
    sign, digits, exponent = value.as_tuple()
    del sign
    scale = max(-exponent, 0)
    integer_digits = max(len(digits) + exponent, 0)
    precision = integer_digits + scale
    if scale > MAX_NUMERIC_SCALE or precision > MAX_NUMERIC_PRECISION:
        raise DomainValidationError(
            f"{name} exceeds NUMERIC({MAX_NUMERIC_PRECISION},{MAX_NUMERIC_SCALE})"
        )


def parse_enum_value(
    cell: RawCell,
    *,
    row_number: int,
    field: str,
    mapping: tuple[tuple[str, T], ...],
) -> T:
    source = _required_source_value(cell, row_number=row_number, field=field)
    values = dict(mapping)
    try:
        return values[source.strip()]
    except KeyError:
        _raise_issue(
            row_number,
            field,
            RowErrorCode.UNKNOWN_ENUM,
            cell,
            "one of: " + ", ".join(sorted(values)),
        )


def parse_datetime_value(
    cell: RawCell,
    *,
    row_number: int,
    field: str,
    timestamp_format: str,
    timezone_name: str | None,
    fold_policy: DateFoldPolicy = DateFoldPolicy.REJECT,
) -> datetime:
    source = _required_source_value(cell, row_number=row_number, field=field).strip()
    try:
        if timestamp_format == "ISO8601":
            parsed = datetime.fromisoformat(source.replace("Z", "+00:00"))
        else:
            parsed = datetime.strptime(source, timestamp_format)
    except ValueError:
        _raise_issue(
            row_number,
            field,
            RowErrorCode.INVALID_DATETIME,
            cell,
            f"datetime format {timestamp_format}",
        )

    if parsed.tzinfo is not None and parsed.utcoffset() is not None:
        return parsed.astimezone(UTC)
    if not timezone_name:
        _raise_issue(
            row_number,
            field,
            RowErrorCode.MISSING_TIMEZONE,
            cell,
            "an explicit timezone for a timestamp without an offset",
        )
    try:
        zone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        raise DomainValidationError("timezone_name must be a valid IANA zone") from None

    candidates = tuple(
        candidate
        for fold in (0, 1)
        if _round_trips(parsed, candidate := parsed.replace(tzinfo=zone, fold=fold), zone)
    )
    distinct = {candidate.astimezone(UTC) for candidate in candidates}
    if not distinct:
        _raise_issue(
            row_number,
            field,
            RowErrorCode.NONEXISTENT_DATETIME,
            cell,
            f"an existing local time in {timezone_name}",
        )
    if len(distinct) > 1:
        if fold_policy is DateFoldPolicy.REJECT:
            _raise_issue(
                row_number,
                field,
                RowErrorCode.AMBIGUOUS_DATETIME,
                cell,
                f"an unambiguous local time in {timezone_name} or an explicit fold",
            )
        ordered = sorted(distinct)
        return ordered[0] if fold_policy is DateFoldPolicy.EARLIER else ordered[-1]
    return distinct.pop()


def _round_trips(naive: datetime, aware: datetime, zone: ZoneInfo) -> bool:
    return aware.astimezone(UTC).astimezone(zone).replace(tzinfo=None) == naive


def _required_source_value(
    cell: RawCell,
    *,
    row_number: int,
    field: str,
) -> str:
    failures = {
        RawCellKind.MISSING: (
            RowErrorCode.MISSING_FIELD,
            "a present required field",
        ),
        RawCellKind.NULL: (RowErrorCode.NULL_REQUIRED, "a non-null value"),
        RawCellKind.EMPTY: (RowErrorCode.EMPTY_REQUIRED, "a nonempty value"),
    }
    if cell.kind in failures:
        code, expected = failures[cell.kind]
        _raise_issue(row_number, field, code, cell, expected)
    assert cell.original is not None
    return cell.original


def _raise_issue(
    row_number: int,
    field: str,
    code: RowErrorCode,
    cell: RawCell,
    expected: str,
) -> Never:
    raise FieldInterpretationError(
        RowIssue(
            row_number=row_number,
            field=field,
            code=code,
            original_value=cell.original,
            expected=expected,
        )
    )
