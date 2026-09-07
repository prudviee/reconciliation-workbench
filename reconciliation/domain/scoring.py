"""Exact fixed-point rule scoring with complete feature evidence."""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import ROUND_HALF_EVEN, Decimal, localcontext
from enum import StrEnum

from .candidates import CandidateGenerationResult
from .reconciliation import (
    CandidateEvidence,
    FeatureEvidence,
    MatchFeature,
    MatchRecord,
    MatchingPolicy,
    NumericSimilarityPolicy,
    ReferenceContract,
    SCORE_SCALE_BP,
)
from .references import ReferencePreprocessingResult
from .workspaces import DomainValidationError


class ContradictionCode(StrEnum):
    INSTRUMENT_MISMATCH = "INSTRUMENT_MISMATCH"
    SIDE_MISMATCH = "SIDE_MISMATCH"
    CURRENCY_MISMATCH = "CURRENCY_MISMATCH"
    SHARED_REFERENCE_MISMATCH = "SHARED_REFERENCE_MISMATCH"
    SHARED_ALIAS_MISMATCH = "SHARED_ALIAS_MISMATCH"


class CoverageFailure(StrEnum):
    MISSING_INSTRUMENT = "MISSING_INSTRUMENT"
    MISSING_SIDE = "MISSING_SIDE"
    MISSING_CURRENCY = "MISSING_CURRENCY"
    MISSING_QUANTITY = "MISSING_QUANTITY"
    MISSING_TIMESTAMP = "MISSING_TIMESTAMP"
    MISSING_MONETARY_FIELD = "MISSING_MONETARY_FIELD"


def score_candidates(
    *,
    preprocessed: ReferencePreprocessingResult,
    generated: CandidateGenerationResult,
    policy: MatchingPolicy,
) -> tuple[CandidateEvidence, ...]:
    """Score every retained candidate without changing its candidate graph."""

    left_by_id = {record.observation_id: record for record in preprocessed.remaining_left}
    right_by_id = {record.observation_id: record for record in preprocessed.remaining_right}
    limited = set(generated.limited_record_ids)
    scored: list[CandidateEvidence] = []
    for candidate in generated.candidates:
        try:
            left = left_by_id[candidate.left_id]
            right = right_by_id[candidate.right_id]
        except KeyError as error:
            raise DomainValidationError(
                "candidate edge must reference records remaining after preprocessing"
            ) from error
        scored.append(
            score_candidate(
                left=left,
                right=right,
                blocking_reasons=candidate.blocking_reasons,
                complete_computation=(
                    candidate.left_id not in limited and candidate.right_id not in limited
                ),
                policy=policy,
            )
        )
    return tuple(sorted(scored, key=lambda item: (item.left_id, item.right_id)))


def score_candidate(
    *,
    left: MatchRecord,
    right: MatchRecord,
    blocking_reasons: tuple[str, ...],
    complete_computation: bool,
    policy: MatchingPolicy,
) -> CandidateEvidence:
    weights = {item.feature: item.weight_bp for item in policy.feature_weights}
    features = (
        _numeric_evidence(
            MatchFeature.QUANTITY,
            left.quantity,
            right.quantity,
            policy.quantity_similarity,
            weights[MatchFeature.QUANTITY],
        ),
        _timestamp_evidence(
            left.executed_at,
            right.executed_at,
            policy.timestamp_similarity.band,
            weights[MatchFeature.TIMESTAMP],
        ),
        _numeric_evidence(
            MatchFeature.UNIT_PRICE,
            left.unit_price,
            right.unit_price,
            policy.unit_price_similarity,
            weights[MatchFeature.UNIT_PRICE],
        ),
        _numeric_evidence(
            MatchFeature.GROSS_AMOUNT,
            left.gross_amount,
            right.gross_amount,
            policy.gross_amount_similarity,
            weights[MatchFeature.GROSS_AMOUNT],
        ),
    )
    contradictions = _contradictions(left, right, policy.reference_contract)
    coverage_failures = _coverage_failures(left, right)
    return CandidateEvidence(
        left_id=left.observation_id,
        right_id=right.observation_id,
        blocking_reasons=blocking_reasons,
        features=features,
        contradictions=tuple(item.value for item in contradictions),
        coverage_failures=tuple(item.value for item in coverage_failures),
        coverage_sufficient=not coverage_failures,
        complete_computation=complete_computation,
        score_bp=sum(item.contribution_bp for item in features),
    )


def _numeric_evidence(
    feature: MatchFeature,
    left: Decimal | None,
    right: Decimal | None,
    policy: NumericSimilarityPolicy,
    weight_bp: int,
) -> FeatureEvidence:
    if left is None or right is None:
        return FeatureEvidence(
            feature=feature,
            left_value=left,
            right_value=right,
            difference=None,
            band=policy.absolute_band,
            present=False,
            similarity_bp=0,
            weight_bp=weight_bp,
            contribution_bp=0,
            rule=(
                f"{_feature_name(feature)} is missing on one or both records; "
                "its contribution is zero and feature weights remain unchanged."
            ),
        )
    with localcontext() as context:
        context.prec = 80
        context.rounding = ROUND_HALF_EVEN
        difference = abs(right - left)
        band = max(
            policy.absolute_band,
            policy.relative_band * max(abs(left), abs(right)),
        )
        factor = _linear_similarity(difference, band)
        similarity_bp = _quantize_bp(Decimal(SCORE_SCALE_BP) * factor)
        contribution_bp = _quantize_bp(Decimal(weight_bp) * factor)
    return FeatureEvidence(
        feature=feature,
        left_value=left,
        right_value=right,
        difference=difference,
        band=band,
        present=True,
        similarity_bp=similarity_bp,
        weight_bp=weight_bp,
        contribution_bp=contribution_bp,
        rule=(
            f"{_feature_name(feature)} uses linear similarity from absolute difference "
            f"{difference} across band {band}; fixed weight {weight_bp} basis points."
        ),
    )


def _timestamp_evidence(
    left: datetime | None,
    right: datetime | None,
    band: timedelta,
    weight_bp: int,
) -> FeatureEvidence:
    if left is None or right is None:
        return FeatureEvidence(
            feature=MatchFeature.TIMESTAMP,
            left_value=left,
            right_value=right,
            difference=None,
            band=band,
            present=False,
            similarity_bp=0,
            weight_bp=weight_bp,
            contribution_bp=0,
            rule=(
                "Timestamp is missing on one or both records; its contribution is zero "
                "and feature weights remain unchanged."
            ),
        )
    difference = abs(right - left)
    with localcontext() as context:
        context.prec = 80
        context.rounding = ROUND_HALF_EVEN
        factor = _linear_similarity(_timedelta_seconds(difference), _timedelta_seconds(band))
        similarity_bp = _quantize_bp(Decimal(SCORE_SCALE_BP) * factor)
        contribution_bp = _quantize_bp(Decimal(weight_bp) * factor)
    return FeatureEvidence(
        feature=MatchFeature.TIMESTAMP,
        left_value=left,
        right_value=right,
        difference=difference,
        band=band,
        present=True,
        similarity_bp=similarity_bp,
        weight_bp=weight_bp,
        contribution_bp=contribution_bp,
        rule=(
            f"Timestamp uses linear similarity from elapsed difference {difference} "
            f"across band {band}; fixed weight {weight_bp} basis points."
        ),
    )


def _linear_similarity(difference: Decimal, band: Decimal) -> Decimal:
    if band == 0:
        return Decimal(1) if difference == 0 else Decimal(0)
    return max(Decimal(0), Decimal(1) - difference / band)


def _quantize_bp(value: Decimal) -> int:
    with localcontext() as context:
        context.prec = 80
        context.rounding = ROUND_HALF_EVEN
        return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_EVEN))


def _timedelta_seconds(value: timedelta) -> Decimal:
    with localcontext() as context:
        context.prec = 80
        return (
            Decimal(value.days * 86_400 + value.seconds)
            + Decimal(value.microseconds) / Decimal(1_000_000)
        )


def _contradictions(
    left: MatchRecord,
    right: MatchRecord,
    reference_contract: ReferenceContract,
) -> tuple[ContradictionCode, ...]:
    values: list[ContradictionCode] = []
    if left.instrument is not None and right.instrument is not None and left.instrument != right.instrument:
        values.append(ContradictionCode.INSTRUMENT_MISMATCH)
    if left.side is not None and right.side is not None and left.side is not right.side:
        values.append(ContradictionCode.SIDE_MISMATCH)
    if left.currency is not None and right.currency is not None and left.currency != right.currency:
        values.append(ContradictionCode.CURRENCY_MISMATCH)
    if reference_contract is ReferenceContract.SHARED_MUST_AGREE:
        if (
            left.reference_value is not None
            and right.reference_value is not None
            and left.reference_value != right.reference_value
        ):
            values.append(ContradictionCode.SHARED_REFERENCE_MISMATCH)
    elif (
        left.shared_reference_alias is not None
        and right.shared_reference_alias is not None
        and left.shared_reference_alias != right.shared_reference_alias
    ):
        values.append(ContradictionCode.SHARED_ALIAS_MISMATCH)
    return tuple(sorted(values, key=lambda item: item.value))


def _coverage_failures(
    left: MatchRecord,
    right: MatchRecord,
) -> tuple[CoverageFailure, ...]:
    values: list[CoverageFailure] = []
    if left.instrument is None or right.instrument is None:
        values.append(CoverageFailure.MISSING_INSTRUMENT)
    if left.side is None or right.side is None:
        values.append(CoverageFailure.MISSING_SIDE)
    if left.currency is None or right.currency is None:
        values.append(CoverageFailure.MISSING_CURRENCY)
    if left.quantity is None or right.quantity is None:
        values.append(CoverageFailure.MISSING_QUANTITY)
    if left.executed_at is None or right.executed_at is None:
        values.append(CoverageFailure.MISSING_TIMESTAMP)
    price_present = left.unit_price is not None and right.unit_price is not None
    amount_present = left.gross_amount is not None and right.gross_amount is not None
    if not price_present and not amount_present:
        values.append(CoverageFailure.MISSING_MONETARY_FIELD)
    return tuple(sorted(values, key=lambda item: item.value))


def _feature_name(feature: MatchFeature) -> str:
    return feature.value.replace("_", " ").title()
