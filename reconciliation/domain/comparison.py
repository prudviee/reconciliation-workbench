"""Exact field comparison for already-established transaction pairs."""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

from .ingestion import CanonicalState
from .reconciliation import (
    ComparisonPolicy,
    ComparisonStatus,
    DecimalTolerance,
    FieldComparison,
    MatchRecord,
    PairOrigin,
    ReferenceContract,
)


def compare_pair_fields(
    *,
    left: MatchRecord,
    right: MatchRecord,
    origin: PairOrigin,
    policy: ComparisonPolicy,
    reference_contract: ReferenceContract,
) -> tuple[FieldComparison, ...]:
    """Compare a paired record set without reconsidering whether it should be paired."""

    currencies_equal = (
        left.currency is not None
        and right.currency is not None
        and left.currency == right.currency
    )
    comparisons = (
        _reference_comparison(left, right, origin, reference_contract),
        _categorical("instrument", "Instrument", left.instrument, right.instrument),
        _categorical(
            "side",
            "Side",
            None if left.side is None else left.side.value,
            None if right.side is None else right.side.value,
        ),
        _decimal_comparison(
            "quantity",
            "Quantity",
            left.quantity,
            right.quantity,
            policy.quantity_tolerance,
        ),
        _timestamp_comparison(left.executed_at, right.executed_at, policy.timestamp_tolerance),
        _monetary_comparison(
            "unit_price",
            "Unit price",
            left.unit_price,
            right.unit_price,
            policy.unit_price_tolerance,
            left.currency,
            right.currency,
            currencies_equal,
        ),
        _monetary_comparison(
            "gross_amount",
            "Gross amount",
            left.gross_amount,
            right.gross_amount,
            policy.gross_amount_tolerance,
            left.currency,
            right.currency,
            currencies_equal,
        ),
        _categorical("currency", "Currency", left.currency, right.currency),
        _state_comparison(left.state, right.state, policy),
    )
    return tuple(sorted(comparisons, key=lambda item: item.field))


def _reference_comparison(
    left: MatchRecord,
    right: MatchRecord,
    origin: PairOrigin,
    contract: ReferenceContract,
) -> FieldComparison:
    if contract is ReferenceContract.SHARED_MUST_AGREE:
        left_value = left.reference_value
        right_value = right.reference_value
        kind = "Shared reference"
    else:
        left_value = left.shared_reference_alias
        right_value = right.shared_reference_alias
        kind = "Shared reference alias"
    role = origin.value.replace("_", " ").lower()
    if left_value is None or right_value is None:
        return FieldComparison(
            "reference",
            ComparisonStatus.MISSING,
            left_value,
            right_value,
            None,
            None,
            f"{kind} is missing on one or both records; the pair origin is {role}.",
        )
    if left_value == right_value:
        return FieldComparison(
            "reference",
            ComparisonStatus.EXACT,
            left_value,
            right_value,
            None,
            None,
            f"{kind} is exactly equal at {left_value}; the pair origin is {role}.",
        )
    return FieldComparison(
        "reference",
        ComparisonStatus.DISCREPANT,
        left_value,
        right_value,
        None,
        None,
        f"{kind} differs: left is {left_value} and right is {right_value}; the pair origin is {role}.",
    )


def _categorical(
    field: str,
    label: str,
    left: str | None,
    right: str | None,
) -> FieldComparison:
    if left is None or right is None:
        return FieldComparison(
            field,
            ComparisonStatus.MISSING,
            left,
            right,
            None,
            None,
            f"{label} is missing on one or both records; no comparison was calculated.",
        )
    if left == right:
        return FieldComparison(
            field,
            ComparisonStatus.EXACT,
            left,
            right,
            None,
            None,
            f"{label} is exactly equal at {left}.",
        )
    return FieldComparison(
        field,
        ComparisonStatus.DISCREPANT,
        left,
        right,
        None,
        None,
        f"{label} differs: left is {left} and right is {right}.",
    )


def _decimal_comparison(
    field: str,
    label: str,
    left: Decimal | None,
    right: Decimal | None,
    tolerance: DecimalTolerance,
) -> FieldComparison:
    if left is None or right is None:
        return FieldComparison(
            field,
            ComparisonStatus.MISSING,
            left,
            right,
            None,
            None,
            f"{label} is missing on one or both records; no difference was calculated.",
        )
    signed_difference = right - left
    allowed = max(
        tolerance.absolute,
        tolerance.relative * max(abs(left), abs(right)),
    )
    if signed_difference == 0:
        status = ComparisonStatus.EXACT
        explanation = f"{label} is exactly equal at {left}."
    elif abs(signed_difference) <= allowed:
        status = ComparisonStatus.WITHIN_TOLERANCE
        explanation = (
            f"{label} differs by {signed_difference}; the allowed difference is {allowed}."
        )
    else:
        status = ComparisonStatus.DISCREPANT
        explanation = (
            f"{label} differs by {signed_difference}; the allowed difference is {allowed}."
        )
    return FieldComparison(
        field,
        status,
        left,
        right,
        signed_difference,
        allowed,
        explanation,
    )


def _timestamp_comparison(
    left: datetime | None,
    right: datetime | None,
    tolerance: timedelta,
) -> FieldComparison:
    if left is None or right is None:
        return FieldComparison(
            "timestamp",
            ComparisonStatus.MISSING,
            left,
            right,
            None,
            None,
            "Timestamp is missing on one or both records; no elapsed difference was calculated.",
        )
    signed_difference = right - left
    if signed_difference == timedelta(0):
        status = ComparisonStatus.EXACT
        explanation = f"Timestamp is exactly equal at {left.isoformat()}."
    elif abs(signed_difference) <= tolerance:
        status = ComparisonStatus.WITHIN_TOLERANCE
        explanation = (
            f"Timestamp differs by {_duration_text(signed_difference)}; "
            f"the allowed elapsed difference is {_duration_text(tolerance)}."
        )
    else:
        status = ComparisonStatus.DISCREPANT
        explanation = (
            f"Timestamp differs by {_duration_text(signed_difference)}; "
            f"the allowed elapsed difference is {_duration_text(tolerance)}."
        )
    return FieldComparison(
        "timestamp",
        status,
        left,
        right,
        signed_difference,
        tolerance,
        explanation,
    )


def _monetary_comparison(
    field: str,
    label: str,
    left: Decimal | None,
    right: Decimal | None,
    tolerance: DecimalTolerance,
    left_currency: str | None,
    right_currency: str | None,
    currencies_equal: bool,
) -> FieldComparison:
    if (
        left_currency is not None
        and right_currency is not None
        and not currencies_equal
    ):
        return FieldComparison(
            field,
            ComparisonStatus.NOT_COMPARABLE,
            left,
            right,
            None,
            None,
            f"{label} is not comparable because currencies differ: left is {left_currency} and right is {right_currency}.",
        )
    if left_currency is None or right_currency is None:
        return FieldComparison(
            field,
            ComparisonStatus.NOT_COMPARABLE,
            left,
            right,
            None,
            None,
            f"{label} is not comparable because currency is missing on one or both records.",
        )
    return _decimal_comparison(field, label, left, right, tolerance)


def _duration_text(value: timedelta) -> str:
    microseconds = (
        value.days * 86_400_000_000
        + value.seconds * 1_000_000
        + value.microseconds
    )
    seconds = Decimal(microseconds) / Decimal(1_000_000)
    return f"{format(seconds, 'f')} seconds"


def _state_comparison(
    left: CanonicalState,
    right: CanonicalState,
    policy: ComparisonPolicy,
) -> FieldComparison:
    left_value = left.value
    right_value = right.value
    if left is right:
        return FieldComparison(
            "state",
            ComparisonStatus.EXACT,
            left_value,
            right_value,
            None,
            None,
            f"State is exactly equal at {left_value}.",
        )
    compatible = (left, right) in policy.compatible_state_pairs
    status = ComparisonStatus.WITHIN_TOLERANCE if compatible else ComparisonStatus.DISCREPANT
    qualifier = "compatible" if compatible else "not compatible"
    return FieldComparison(
        "state",
        status,
        left_value,
        right_value,
        None,
        None,
        f"State differs: left is {left_value} and right is {right_value}; the policy marks this pair {qualifier}.",
    )
