from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from reconciliation.domain import (
    CanonicalRow,
    CanonicalSide,
    CanonicalState,
    DomainValidationError,
    FieldProvenance,
    IngestionOperation,
    RawCell,
    RawCellKind,
    SemanticInputRow,
    SemanticValue,
    SemanticValueTag,
    canonical_datetime,
    canonical_decimal,
    mapping_revision_digest,
    observation_fingerprint,
    physical_artifact_hash,
    resolved_state_hash,
    semantic_input_hash,
    semantic_row_from_canonical,
    source_contract_digest,
)


CONTRACT_DIGEST = "a" * 64


def canonical_row(
    *,
    reference: str = "T-1001",
    quantity: Decimal = Decimal("0.500"),
    executed_at: datetime = datetime(2025, 7, 1, 9, 15, tzinfo=UTC),
    quantity_original: str = "0.500",
) -> CanonicalRow:
    values = {
        "source_record_key": reference,
        "business_reference": reference,
        "executed_at_utc": executed_at.isoformat(),
        "instrument": "BTC-USD",
        "side": "BUY",
        "quantity": quantity_original,
        "unit_price": "62000",
        "gross_amount": "31000",
        "currency": "USD",
        "state": "SETTLED",
    }
    provenance = tuple(
        FieldProvenance(
            canonical_field=field,
            source_column=field,
            raw_cell=RawCell.from_source(value),
            transformation="declared mapping",
        )
        for field, value in values.items()
    )
    return CanonicalRow(
        row_number=2,
        source_record_key=reference,
        business_reference=reference,
        executed_at_utc=executed_at,
        instrument="BTC-USD",
        side=CanonicalSide.BUY,
        quantity=quantity,
        unit_price=Decimal("62000.00"),
        gross_amount=Decimal("31000.0"),
        currency="USD",
        state=CanonicalState.SETTLED,
        operation=IngestionOperation.SNAPSHOT,
        provenance=provenance,
    )


def test_physical_hash_tracks_exact_bytes_across_chunk_boundaries() -> None:
    payload = b"id,amount\n1,10.00\n"

    whole = physical_artifact_hash((payload,))
    chunked = physical_artifact_hash((payload[:3], payload[3:11], payload[11:]))
    changed = physical_artifact_hash((payload.replace(b"10.00", b"10.0"),))

    assert whole == chunked
    assert whole != changed


def test_mapping_and_contract_digests_ignore_json_key_order_but_track_meaning() -> None:
    first_mapping = {"source": "trade_id", "canonical": "source_record_key"}
    reordered_mapping = {"canonical": "source_record_key", "source": "trade_id"}
    snapshot = {"mode": "FULL_SNAPSHOT", "mapping": first_mapping}
    delta = {"mode": "DELTA", "mapping": first_mapping}

    assert mapping_revision_digest(first_mapping) == mapping_revision_digest(
        reordered_mapping
    )
    assert source_contract_digest(snapshot) != source_contract_digest(delta)


def test_canonical_decimal_and_datetime_remove_format_only_differences() -> None:
    assert canonical_decimal(Decimal("0.5000")) == "0.5"
    assert canonical_decimal(Decimal("-0.000")) == "0"
    assert canonical_decimal(Decimal("1E+3")) == "1000"
    assert canonical_datetime(datetime(2025, 7, 1, 14, 45, tzinfo=timezone(timedelta(hours=5, minutes=30)))) == "2025-07-01T09:15:00.000000Z"


def test_semantic_hash_ignores_row_order_and_valid_number_time_formatting() -> None:
    first = canonical_row()
    reformatted = canonical_row(
        quantity=Decimal("0.5"),
        quantity_original="0.5",
        executed_at=datetime(
            2025,
            7,
            1,
            14,
            45,
            tzinfo=timezone(timedelta(hours=5, minutes=30)),
        ),
    )
    second = canonical_row(reference="T-1002", quantity=Decimal("2"))

    left = semantic_input_hash(
        contract_digest=CONTRACT_DIGEST,
        header=("trade_id", "quantity"),
        rows=(semantic_row_from_canonical(first), semantic_row_from_canonical(second)),
    )
    right = semantic_input_hash(
        contract_digest=CONTRACT_DIGEST,
        header=("quantity", "trade_id"),
        rows=(semantic_row_from_canonical(second), semantic_row_from_canonical(reformatted)),
    )

    assert left == right


def test_semantic_hash_preserves_duplicate_multiplicity() -> None:
    row = semantic_row_from_canonical(canonical_row())

    once = semantic_input_hash(
        contract_digest=CONTRACT_DIGEST,
        header=("id",),
        rows=(row,),
    )
    twice = semantic_input_hash(
        contract_digest=CONTRACT_DIGEST,
        header=("id",),
        rows=(row, row),
    )

    assert once != twice


@pytest.mark.parametrize(
    ("kind", "value"),
    [
        (RawCellKind.MISSING, None),
        (RawCellKind.NULL, "NULL"),
        (RawCellKind.EMPTY, ""),
        (RawCellKind.VALUE, "NULL"),
    ],
)
def test_raw_semantic_tags_produce_distinct_hashes(
    kind: RawCellKind,
    value: str | None,
) -> None:
    row = SemanticInputRow(
        "UNRESOLVED",
        (("amount", SemanticValue.from_raw(kind, value)),),
    )
    digest = semantic_input_hash(
        contract_digest=CONTRACT_DIGEST,
        header=("amount",),
        rows=(row,),
    )
    assert len(digest) == 64


def test_all_raw_semantic_tags_have_different_digests() -> None:
    digests = {
        semantic_input_hash(
            contract_digest=CONTRACT_DIGEST,
            header=("amount",),
            rows=(
                SemanticInputRow(
                    "UNRESOLVED",
                    (("amount", SemanticValue.from_raw(kind, value)),),
                ),
            ),
        )
        for kind, value in (
            (RawCellKind.MISSING, None),
            (RawCellKind.NULL, "NULL"),
            (RawCellKind.EMPTY, ""),
            (RawCellKind.VALUE, "NULL"),
        )
    }

    assert len(digests) == 4


def test_observation_fingerprint_ignores_raw_format_but_tracks_meaning() -> None:
    formatted = canonical_row()
    equivalent = canonical_row(
        quantity=Decimal("0.5"),
        quantity_original="0.5",
    )
    changed = replace(equivalent, gross_amount=Decimal("31001"))

    first = observation_fingerprint(
        contract_digest=CONTRACT_DIGEST,
        row=formatted,
    )
    second = observation_fingerprint(
        contract_digest=CONTRACT_DIGEST,
        row=equivalent,
    )
    third = observation_fingerprint(
        contract_digest=CONTRACT_DIGEST,
        row=changed,
    )

    assert first == second
    assert first != third


def test_resolved_state_hash_is_order_independent_and_base_sensitive() -> None:
    first = observation_fingerprint(
        contract_digest=CONTRACT_DIGEST,
        row=canonical_row(reference="T-1"),
    )
    second = observation_fingerprint(
        contract_digest=CONTRACT_DIGEST,
        row=canonical_row(reference="T-2"),
    )

    state = resolved_state_hash((("T-1", first), ("T-2", second)))
    reordered = resolved_state_hash((("T-2", second), ("T-1", first)))
    different_base = resolved_state_hash((("T-1", first),))

    assert state == reordered
    assert state != different_base


def test_resolved_state_rejects_duplicate_identity_and_bad_digest() -> None:
    fingerprint = "b" * 64

    with pytest.raises(DomainValidationError, match="unique"):
        resolved_state_hash((("T-1", fingerprint), ("T-1", fingerprint)))
    with pytest.raises(DomainValidationError, match="SHA-256"):
        resolved_state_hash((("T-1", "not-a-digest"),))


def test_hash_contract_has_stable_golden_values() -> None:
    row = canonical_row()
    semantic = semantic_input_hash(
        contract_digest=CONTRACT_DIGEST,
        header=("trade_id", "quantity"),
        rows=(semantic_row_from_canonical(row),),
    )
    observation = observation_fingerprint(
        contract_digest=CONTRACT_DIGEST,
        row=row,
    )
    state = resolved_state_hash((("T-1001", observation),))

    assert semantic == "3ceac65693a9f46f90eecdd956cfff6ca02a91932bec9d3f9f87d48237b571b3"
    assert observation == "18125062a6cb7d378510306613dadeefac0aa96d18e2d1d3ebcaff683fbce382"
    assert state == "c2fd36a7fc1f073cead1ba1b84f40edbac092ef3a1b946461bd4f38792271408"
