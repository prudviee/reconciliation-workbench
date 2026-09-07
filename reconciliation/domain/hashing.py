"""Versioned deterministic digests for ingestion and materialized state."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any, Iterable

from .ingestion import CanonicalRow, RawCellKind
from .workspaces import DomainValidationError


HASH_SCHEME_VERSION = "reconciliation-sha256-v1"


class SemanticValueTag(StrEnum):
    TEXT = "TEXT"
    DECIMAL = "DECIMAL"
    DATETIME = "DATETIME"
    ENUM = "ENUM"
    MISSING = "MISSING"
    NULL = "NULL"
    EMPTY = "EMPTY"
    RAW = "RAW"


@dataclass(frozen=True, slots=True)
class SemanticValue:
    tag: SemanticValueTag
    value: str | None

    def __post_init__(self) -> None:
        if self.tag is SemanticValueTag.MISSING:
            if self.value is not None:
                raise DomainValidationError("a missing semantic value has no payload")
        elif not isinstance(self.value, str):
            raise DomainValidationError("a semantic value payload must be text")
        if self.tag is SemanticValueTag.EMPTY and self.value != "":
            raise DomainValidationError("an empty semantic value must preserve empty text")

    @classmethod
    def from_raw(cls, kind: RawCellKind, value: str | None) -> SemanticValue:
        tags = {
            RawCellKind.MISSING: SemanticValueTag.MISSING,
            RawCellKind.NULL: SemanticValueTag.NULL,
            RawCellKind.EMPTY: SemanticValueTag.EMPTY,
            RawCellKind.VALUE: SemanticValueTag.RAW,
        }
        return cls(tags[kind], value)


@dataclass(frozen=True, slots=True)
class SemanticInputRow:
    operation: str
    fields: tuple[tuple[str, SemanticValue], ...]

    def __post_init__(self) -> None:
        if not self.operation.strip():
            raise DomainValidationError("semantic row operation must not be blank")
        names = [name for name, _ in self.fields]
        if any(not name.strip() for name in names) or len(names) != len(set(names)):
            raise DomainValidationError(
                "semantic row field names must be nonempty and unique"
            )


def physical_artifact_hash(chunks: Iterable[bytes]) -> str:
    digest = hashlib.sha256()
    for chunk in chunks:
        if not isinstance(chunk, bytes):
            raise DomainValidationError("physical hash chunks must be bytes")
        digest.update(chunk)
    return digest.hexdigest()


def mapping_revision_digest(mapping: dict[str, Any]) -> str:
    return _digest("mapping-revision", mapping)


def source_contract_digest(contract: dict[str, Any]) -> str:
    return _digest("source-contract", contract)


def policy_revision_digest(
    *,
    matching_policy: dict[str, Any],
    comparison_policy: dict[str, Any],
) -> str:
    if not isinstance(matching_policy, dict) or not isinstance(
        comparison_policy, dict
    ):
        raise DomainValidationError("policy payloads must be objects")
    if not matching_policy or not comparison_policy:
        raise DomainValidationError("policy payloads must not be empty")
    return _digest(
        "policy-revision",
        {
            "matching_policy": matching_policy,
            "comparison_policy": comparison_policy,
        },
    )


def semantic_input_hash(
    *,
    contract_digest: str,
    header: Iterable[str],
    rows: Iterable[SemanticInputRow],
) -> str:
    _validate_digest(contract_digest, "contract_digest")
    metadata = {
        "contract_digest": contract_digest,
        "header": sorted(header),
    }
    records = [
        _canonical_json(
            {
                "operation": row.operation,
                "fields": [
                    {
                        "name": name,
                        "tag": value.tag.value,
                        "value": value.value,
                    }
                    for name, value in sorted(row.fields)
                ],
            }
        )
        for row in rows
    ]
    return _record_digest("semantic-input", metadata, records)


def semantic_row_from_canonical(row: CanonicalRow) -> SemanticInputRow:
    fields = (
        (
            "source_record_key",
            SemanticValue(SemanticValueTag.TEXT, row.source_record_key),
        ),
        (
            "business_reference",
            SemanticValue(SemanticValueTag.TEXT, row.business_reference or ""),
        ),
        (
            "executed_at_utc",
            SemanticValue(
                SemanticValueTag.DATETIME,
                canonical_datetime(row.executed_at_utc),
            ),
        ),
        ("instrument", SemanticValue(SemanticValueTag.TEXT, row.instrument)),
        ("side", SemanticValue(SemanticValueTag.ENUM, row.side.value)),
        (
            "quantity",
            SemanticValue(
                SemanticValueTag.DECIMAL,
                canonical_decimal(row.quantity),
            ),
        ),
        (
            "unit_price",
            SemanticValue(
                SemanticValueTag.DECIMAL,
                canonical_decimal(row.unit_price),
            ),
        ),
        (
            "gross_amount",
            SemanticValue(
                SemanticValueTag.DECIMAL,
                canonical_decimal(row.gross_amount),
            ),
        ),
        ("currency", SemanticValue(SemanticValueTag.TEXT, row.currency)),
        ("state", SemanticValue(SemanticValueTag.ENUM, row.state.value)),
    )
    return SemanticInputRow(row.operation.value, fields)


def observation_fingerprint(*, contract_digest: str, row: CanonicalRow) -> str:
    _validate_digest(contract_digest, "contract_digest")
    semantic = semantic_row_from_canonical(row)
    payload = {
        "contract_digest": contract_digest,
        "operation": semantic.operation,
        "fields": [
            {"name": name, "tag": value.tag.value, "value": value.value}
            for name, value in sorted(semantic.fields)
        ],
        "provenance": [
            {
                "canonical_field": item.canonical_field,
                "source_column": item.source_column,
                "source_kind": item.raw_cell.kind.value,
                "transformation": item.transformation,
            }
            for item in sorted(
                row.provenance,
                key=lambda value: value.canonical_field,
            )
        ],
    }
    return _digest("observation", payload)


def resolved_state_hash(members: Iterable[tuple[str, str]]) -> str:
    records = []
    identities: set[str] = set()
    for identity, fingerprint in members:
        if not identity.strip() or identity in identities:
            raise DomainValidationError(
                "resolved state identities must be nonempty and unique"
            )
        _validate_digest(fingerprint, "observation fingerprint")
        identities.add(identity)
        records.append(
            _canonical_json(
                {
                    "identity": identity,
                    "observation_fingerprint": fingerprint,
                }
            )
        )
    return _record_digest("resolved-state", {}, records)


def canonical_decimal(value: Decimal) -> str:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise DomainValidationError("canonical decimal requires a finite Decimal")
    if value == 0:
        return "0"
    return format(value.normalize(), "f")


def canonical_datetime(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise DomainValidationError("canonical datetime must be timezone-aware")
    utc = value.astimezone(UTC)
    return utc.isoformat(timespec="microseconds").replace("+00:00", "Z")


def _record_digest(
    kind: str,
    metadata: dict[str, Any],
    records: Iterable[bytes],
) -> str:
    digest = hashlib.sha256()
    envelope = {
        "version": HASH_SCHEME_VERSION,
        "kind": kind,
        "metadata": metadata,
    }
    digest.update(_length_prefix(_canonical_json(envelope)))
    for record in sorted(records):
        digest.update(_length_prefix(record))
    return digest.hexdigest()


def _digest(kind: str, payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        _canonical_json(
            {
                "version": HASH_SCHEME_VERSION,
                "kind": kind,
                "payload": payload,
            }
        )
    ).hexdigest()


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _length_prefix(value: bytes) -> bytes:
    return len(value).to_bytes(8, "big") + value


def _validate_digest(value: str, name: str) -> None:
    if len(value) != 64:
        raise DomainValidationError(f"{name} must be a lowercase SHA-256 digest")
    try:
        bytes.fromhex(value)
    except ValueError:
        raise DomainValidationError(
            f"{name} must be a lowercase SHA-256 digest"
        ) from None
    if value != value.lower():
        raise DomainValidationError(f"{name} must be a lowercase SHA-256 digest")
