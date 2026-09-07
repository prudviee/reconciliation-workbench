from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from reconciliation.domain import (
    CanonicalSide,
    CanonicalState,
    ComparisonPolicy,
    ComparisonStatus,
    DecimalTolerance,
    DomainValidationError,
    FieldComparison,
    MatchRecord,
    PairOrigin,
    PairOutcome,
    ReferenceContract,
    compare_pair_fields,
)


def record(
    observation_id: str,
    *,
    state: CanonicalState = CanonicalState.SETTLED,
    instrument: str | None = "AAPL",
    side: CanonicalSide | None = CanonicalSide.BUY,
    currency: str | None = "USD",
    quantity: Decimal | None = Decimal("10"),
    executed_at: datetime | None = datetime(2026, 9, 7, 12, tzinfo=UTC),
    unit_price: Decimal | None = Decimal("100"),
    gross_amount: Decimal | None = Decimal("1000"),
    reference_value: str | None = "T-1011",
    shared_reference_alias: str | None = "SHARED-1011",
) -> MatchRecord:
    return MatchRecord(
        observation_id=observation_id,
        logical_transaction_id=f"logical-{observation_id}",
        source_record_key=f"source-{observation_id}",
        state=state,
        instrument=instrument,
        side=side,
        currency=currency,
        quantity=quantity,
        executed_at=executed_at,
        unit_price=unit_price,
        gross_amount=gross_amount,
        reference_value=reference_value,
        shared_reference_alias=shared_reference_alias,
    )


def compare(
    left: MatchRecord,
    right: MatchRecord,
    *,
    origin: PairOrigin = PairOrigin.WEIGHTED_GLOBAL,
    policy: ComparisonPolicy | None = None,
    contract: ReferenceContract = ReferenceContract.SHARED_MUST_AGREE,
):
    return compare_pair_fields(
        left=left,
        right=right,
        origin=origin,
        policy=policy or ComparisonPolicy.initial_demo(),
        reference_contract=contract,
    )


def by_field(comparisons):
    return {item.field: item for item in comparisons}


def test_exact_pair_produces_a_complete_canonical_field_ledger() -> None:
    comparisons = compare(record("L1"), record("R1"))

    assert tuple(item.field for item in comparisons) == (
        "currency",
        "gross_amount",
        "instrument",
        "quantity",
        "reference",
        "side",
        "state",
        "timestamp",
        "unit_price",
    )
    assert {item.status for item in comparisons} == {ComparisonStatus.EXACT}


def test_initial_demo_policy_uses_documented_comparison_boundaries() -> None:
    policy = ComparisonPolicy.initial_demo()

    assert policy.quantity_tolerance.absolute == Decimal("0.00000001")
    assert policy.unit_price_tolerance.absolute == Decimal("0.01")
    assert policy.gross_amount_tolerance.absolute == Decimal("0.05")
    assert policy.timestamp_tolerance == timedelta(seconds=60)


@pytest.mark.parametrize(
    ("field", "boundary_value", "beyond_value", "allowed"),
    [
        ("quantity", Decimal("10.00000001"), Decimal("10.000000011"), Decimal("0.00000001")),
        ("unit_price", Decimal("100.01"), Decimal("100.0100001"), Decimal("0.01")),
        ("gross_amount", Decimal("1000.05"), Decimal("1000.050001"), Decimal("0.05")),
    ],
)
def test_decimal_tolerances_are_inclusive_and_exact(
    field: str,
    boundary_value: Decimal,
    beyond_value: Decimal,
    allowed: Decimal,
) -> None:
    baseline = record("L1")
    boundary = by_field(compare(baseline, record("R1", **{field: boundary_value})))[field]
    beyond = by_field(compare(baseline, record("R1", **{field: beyond_value})))[field]

    assert boundary.status is ComparisonStatus.WITHIN_TOLERANCE
    assert boundary.allowed_difference == allowed
    assert beyond.status is ComparisonStatus.DISCREPANT
    assert beyond.allowed_difference == allowed


def test_timestamp_tolerance_is_inclusive_and_uses_elapsed_instants() -> None:
    left = record("L1", executed_at=datetime(2026, 9, 7, 12, tzinfo=UTC))
    boundary = record("R1", executed_at=datetime(2026, 9, 7, 12, 1, tzinfo=UTC))
    beyond = record(
        "R2",
        executed_at=datetime(2026, 9, 7, 12, 1, tzinfo=UTC) + timedelta(microseconds=1),
    )
    same_instant = record(
        "R3",
        executed_at=datetime(
            2026,
            9,
            7,
            17,
            30,
            tzinfo=timezone(timedelta(hours=5, minutes=30)),
        ),
    )

    assert by_field(compare(left, boundary))["timestamp"].status is ComparisonStatus.WITHIN_TOLERANCE
    boundary_result = by_field(compare(left, boundary))["timestamp"]
    assert boundary_result.explanation == (
        "Timestamp differs by 60 seconds; the allowed elapsed difference is 60 seconds."
    )
    assert by_field(compare(left, beyond))["timestamp"].status is ComparisonStatus.DISCREPANT
    equivalent = by_field(compare(left, same_instant))["timestamp"]
    assert equivalent.status is ComparisonStatus.EXACT
    assert equivalent.signed_difference == timedelta(0)


def test_relative_decimal_tolerance_uses_the_larger_absolute_value() -> None:
    policy = replace(
        ComparisonPolicy.initial_demo(),
        quantity_tolerance=DecimalTolerance(Decimal("0"), Decimal("0.01")),
    )

    result = by_field(
        compare(
            record("L1", quantity=Decimal("100")),
            record("R1", quantity=Decimal("101")),
            policy=policy,
        )
    )["quantity"]

    assert result.status is ComparisonStatus.WITHIN_TOLERANCE
    assert result.signed_difference == Decimal("1")
    assert result.allowed_difference == Decimal("1.01")


def test_signed_decimal_difference_preserves_direction() -> None:
    result = by_field(
        compare(
            record("L1", gross_amount=Decimal("1000")),
            record("R1", gross_amount=Decimal("999.98")),
        )
    )["gross_amount"]

    assert result.signed_difference == Decimal("-0.02")
    assert result.status is ComparisonStatus.WITHIN_TOLERANCE


def test_different_currencies_refuse_monetary_subtraction() -> None:
    result = by_field(compare(record("L1"), record("R1", currency="EUR")))

    assert result["currency"].status is ComparisonStatus.DISCREPANT
    for field in ("unit_price", "gross_amount"):
        assert result[field].status is ComparisonStatus.NOT_COMPARABLE
        assert result[field].signed_difference is None
        assert result[field].allowed_difference is None
        assert "currencies differ" in result[field].explanation


def test_missing_currency_or_value_is_explicit() -> None:
    result = by_field(
        compare(
            record("L1", quantity=None),
            record("R1", currency=None, quantity=Decimal("10")),
        )
    )

    assert result["quantity"].status is ComparisonStatus.MISSING
    assert result["currency"].status is ComparisonStatus.MISSING
    assert result["gross_amount"].status is ComparisonStatus.NOT_COMPARABLE


def test_authoritative_reference_pair_preserves_amount_discrepancy() -> None:
    comparisons = compare(
        record("L1", gross_amount=Decimal("34000"), reference_value="T-1011"),
        record("R1", gross_amount=Decimal("34170"), reference_value="T-1011"),
        origin=PairOrigin.AUTHORITATIVE_REFERENCE,
    )
    pair = PairOutcome(
        "L1",
        "R1",
        PairOrigin.AUTHORITATIVE_REFERENCE,
        comparisons=comparisons,
    )
    result = by_field(pair.comparisons)

    assert result["reference"].status is ComparisonStatus.EXACT
    assert "authoritative reference" in result["reference"].explanation
    assert result["gross_amount"].status is ComparisonStatus.DISCREPANT
    assert result["gross_amount"].signed_difference == Decimal("170")


def test_source_local_references_compare_shared_aliases() -> None:
    result = by_field(
        compare(
            record("L1", reference_value="LEFT-7", shared_reference_alias="S-7"),
            record("R1", reference_value="RIGHT-99", shared_reference_alias="S-7"),
            contract=ReferenceContract.SOURCE_LOCAL_OR_ALIAS,
        )
    )["reference"]

    assert result.status is ComparisonStatus.EXACT
    assert result.left_value == "S-7"
    assert result.right_value == "S-7"


def test_state_compatibility_is_versioned_and_distinct_from_equality() -> None:
    policy = replace(
        ComparisonPolicy.initial_demo(),
        compatible_state_pairs=((CanonicalState.SETTLED, CanonicalState.CANCELLED),),
    )

    result = by_field(
        compare(
            record("L1", state=CanonicalState.SETTLED),
            record("R1", state=CanonicalState.CANCELLED),
            policy=policy,
        )
    )["state"]

    assert result.status is ComparisonStatus.WITHIN_TOLERANCE
    assert "policy marks this pair compatible" in result.explanation


def test_incompatible_state_and_categorical_difference_are_discrepant() -> None:
    result = by_field(
        compare(
            record("L1", instrument="AAPL", side=CanonicalSide.BUY),
            record(
                "R1",
                state=CanonicalState.CANCELLED,
                instrument="MSFT",
                side=CanonicalSide.SELL,
            ),
        )
    )

    assert result["state"].status is ComparisonStatus.DISCREPANT
    assert result["instrument"].status is ComparisonStatus.DISCREPANT
    assert result["side"].status is ComparisonStatus.DISCREPANT


def test_explanations_only_state_observed_values_rules_and_pair_origin() -> None:
    comparisons = compare(
        record("L1", gross_amount=Decimal("34000")),
        record("R1", gross_amount=Decimal("34170")),
        origin=PairOrigin.MANUAL,
    )
    text = " ".join(item.explanation.lower() for item in comparisons)

    for unsupported in ("fee", "fraud", "intent", "settlement delay"):
        assert unsupported not in text
    assert "differs by 170" in text
    assert "pair origin is manual" in text


def test_comparison_is_identical_when_called_repeatedly() -> None:
    left = record("L1", unit_price=Decimal("99.995"))
    right = record("R1", unit_price=Decimal("100.004"))

    assert compare(left, right) == compare(left, right)


@pytest.mark.parametrize(
    ("signed", "allowed"),
    [
        (Decimal("1"), None),
        (Decimal("1"), timedelta(seconds=1)),
        (Decimal("1"), Decimal("-0.01")),
    ],
)
def test_field_comparison_rejects_incoherent_difference_evidence(signed, allowed) -> None:
    with pytest.raises(DomainValidationError):
        FieldComparison(
            "quantity",
            ComparisonStatus.DISCREPANT,
            Decimal("1"),
            Decimal("2"),
            signed,
            allowed,
            "Synthetic invalid comparison evidence.",
        )


def test_not_comparable_field_cannot_claim_a_calculated_difference() -> None:
    with pytest.raises(DomainValidationError, match="not-comparable"):
        FieldComparison(
            "gross_amount",
            ComparisonStatus.NOT_COMPARABLE,
            Decimal("1"),
            Decimal("2"),
            Decimal("1"),
            Decimal("0.05"),
            "Synthetic invalid comparison evidence.",
        )
