from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import ROUND_DOWN, Decimal, localcontext

import pytest

from reconciliation.domain import (
    BlockingPassPolicy,
    CandidateEdge,
    CandidateGenerationResult,
    CanonicalSide,
    CanonicalState,
    ContradictionCode,
    CoverageFailure,
    DecisionInputs,
    DomainValidationError,
    EngineSnapshot,
    FeatureWeight,
    MatchFeature,
    MatchRecord,
    MatchingPolicy,
    NumericSimilarityPolicy,
    ReferenceContract,
    generate_candidates,
    preprocess_references,
    score_candidate,
    score_candidates,
)


BASE_TIME = datetime(2026, 9, 7, 12, tzinfo=UTC)


def record(identity: str, **overrides: object) -> MatchRecord:
    values: dict[str, object] = {
        "observation_id": identity,
        "logical_transaction_id": f"logical-{identity}",
        "source_record_key": f"source-{identity}",
        "state": CanonicalState.SETTLED,
        "instrument": "BTC-USD",
        "side": CanonicalSide.BUY,
        "currency": "USD",
        "quantity": Decimal("100"),
        "executed_at": BASE_TIME,
        "unit_price": Decimal("10"),
        "gross_amount": Decimal("1000"),
        "reference_value": None,
        "shared_reference_alias": None,
    }
    values.update(overrides)
    return MatchRecord(**values)  # type: ignore[arg-type]


def score(left: MatchRecord, right: MatchRecord, *, policy: MatchingPolicy | None = None):
    return score_candidate(
        left=left,
        right=right,
        blocking_reasons=("test-pass@1",),
        complete_computation=True,
        policy=policy or MatchingPolicy.initial_demo(),
    )


def feature(result, name: MatchFeature):
    return next(item for item in result.features if item.feature is name)


def test_exact_candidate_has_full_rule_score_and_complete_feature_ledger() -> None:
    result = score(record("L1"), record("R1"))

    assert result.score_bp == 10_000
    assert result.score_label == "Rule score"
    assert result.coverage_sufficient is True
    assert result.coverage_failures == ()
    assert result.contradictions == ()
    assert {item.feature: item.contribution_bp for item in result.features} == {
        MatchFeature.QUANTITY: 3_500,
        MatchFeature.TIMESTAMP: 2_500,
        MatchFeature.UNIT_PRICE: 1_500,
        MatchFeature.GROSS_AMOUNT: 2_500,
    }
    assert all(item.present and item.similarity_bp == 10_000 for item in result.features)


def test_numeric_and_timestamp_similarity_use_exact_linear_bands() -> None:
    base = MatchingPolicy.initial_demo()
    policy = replace(
        base,
        quantity_similarity=NumericSimilarityPolicy(Decimal("10"), Decimal("0")),
        unit_price_similarity=NumericSimilarityPolicy(Decimal("4"), Decimal("0")),
        gross_amount_similarity=NumericSimilarityPolicy(Decimal("100"), Decimal("0")),
    )
    result = score(
        record("L1"),
        record(
            "R1",
            quantity=Decimal("102"),
            executed_at=BASE_TIME + timedelta(minutes=5),
            unit_price=Decimal("11"),
            gross_amount=Decimal("1025"),
        ),
        policy=policy,
    )

    assert (feature(result, MatchFeature.QUANTITY).similarity_bp, feature(result, MatchFeature.QUANTITY).contribution_bp) == (8_000, 2_800)
    assert (feature(result, MatchFeature.TIMESTAMP).similarity_bp, feature(result, MatchFeature.TIMESTAMP).contribution_bp) == (5_000, 1_250)
    assert (feature(result, MatchFeature.UNIT_PRICE).similarity_bp, feature(result, MatchFeature.UNIT_PRICE).contribution_bp) == (7_500, 1_125)
    assert (feature(result, MatchFeature.GROSS_AMOUNT).similarity_bp, feature(result, MatchFeature.GROSS_AMOUNT).contribution_bp) == (7_500, 1_875)
    assert result.score_bp == 7_050


def test_relative_band_uses_larger_absolute_value_and_similarity_stops_at_zero() -> None:
    policy = replace(
        MatchingPolicy.initial_demo(),
        quantity_similarity=NumericSimilarityPolicy(Decimal("0.5"), Decimal("0.01")),
    )
    within = score(record("L1"), record("R1", quantity=Decimal("101")), policy=policy)
    beyond = score(record("L1"), record("R1", quantity=Decimal("103")), policy=policy)

    quantity = feature(within, MatchFeature.QUANTITY)
    assert quantity.band == Decimal("1.01")
    assert quantity.difference == Decimal("1")
    assert quantity.similarity_bp == 99
    assert feature(beyond, MatchFeature.QUANTITY).similarity_bp == 0
    assert feature(beyond, MatchFeature.QUANTITY).contribution_bp == 0


def test_zero_band_means_equal_is_full_and_any_difference_is_zero() -> None:
    policy = replace(
        MatchingPolicy.initial_demo(),
        quantity_similarity=NumericSimilarityPolicy(Decimal("0"), Decimal("0")),
    )

    assert feature(score(record("L1"), record("R1"), policy=policy), MatchFeature.QUANTITY).similarity_bp == 10_000
    assert feature(score(record("L1"), record("R1", quantity=Decimal("100.0001")), policy=policy), MatchFeature.QUANTITY).similarity_bp == 0


def test_missing_feature_contributes_zero_without_weight_renormalization() -> None:
    result = score(record("L1"), record("R1", quantity=None))
    quantity = feature(result, MatchFeature.QUANTITY)

    assert quantity.present is False
    assert quantity.similarity_bp == quantity.contribution_bp == 0
    assert quantity.weight_bp == 3_500
    assert result.score_bp == 6_500
    assert result.coverage_sufficient is False
    assert result.coverage_failures == (CoverageFailure.MISSING_QUANTITY.value,)
    assert "weights remain unchanged" in quantity.rule


def test_hard_gate_requires_core_fields_and_at_least_one_paired_monetary_field() -> None:
    result = score(
        record("L1", unit_price=None, gross_amount=None),
        record(
            "R1",
            instrument=None,
            side=None,
            currency=None,
            quantity=None,
            executed_at=None,
            unit_price=Decimal("10"),
            gross_amount=None,
        ),
    )

    assert result.coverage_sufficient is False
    assert set(result.coverage_failures) == {
        CoverageFailure.MISSING_INSTRUMENT.value,
        CoverageFailure.MISSING_SIDE.value,
        CoverageFailure.MISSING_CURRENCY.value,
        CoverageFailure.MISSING_QUANTITY.value,
        CoverageFailure.MISSING_TIMESTAMP.value,
        CoverageFailure.MISSING_MONETARY_FIELD.value,
    }


def test_one_complete_monetary_feature_satisfies_monetary_coverage_floor() -> None:
    result = score(
        record("L1", unit_price=None),
        record("R1", unit_price=None),
    )

    assert result.coverage_sufficient is True
    assert result.coverage_failures == ()
    assert feature(result, MatchFeature.UNIT_PRICE).contribution_bp == 0
    assert result.score_bp == 8_500


def test_present_instrument_side_and_currency_mismatches_are_hard_contradictions() -> None:
    result = score(
        record("L1"),
        record("R1", instrument="ETH-USD", side=CanonicalSide.SELL, currency="EUR"),
    )

    assert result.coverage_sufficient is True
    assert set(result.contradictions) == {
        ContradictionCode.INSTRUMENT_MISMATCH.value,
        ContradictionCode.SIDE_MISMATCH.value,
        ContradictionCode.CURRENCY_MISMATCH.value,
    }


def test_shared_reference_contract_prohibits_unequal_present_references_only() -> None:
    unequal = score(
        record("L1", reference_value="T-1"),
        record("R1", reference_value="T-2"),
    )
    missing = score(
        record("L1", reference_value="T-1"),
        record("R1", reference_value=None),
    )

    assert unequal.contradictions == (ContradictionCode.SHARED_REFERENCE_MISMATCH.value,)
    assert missing.contradictions == ()


def test_source_local_reference_differences_are_allowed_but_mapped_alias_conflicts_are_not() -> None:
    policy = replace(
        MatchingPolicy.initial_demo(),
        reference_contract=ReferenceContract.SOURCE_LOCAL_OR_ALIAS,
    )
    local_only = score(
        record("L1", reference_value="ledger-1"),
        record("R1", reference_value="provider-9"),
        policy=policy,
    )
    alias_conflict = score(
        record("L1", reference_value="ledger-1", shared_reference_alias="A"),
        record("R1", reference_value="provider-9", shared_reference_alias="B"),
        policy=policy,
    )

    assert local_only.contradictions == ()
    assert alias_conflict.contradictions == (ContradictionCode.SHARED_ALIAS_MISMATCH.value,)


@pytest.mark.parametrize(
    ("quantity_weight", "expected"),
    [(1, 0), (3, 2)],
)
def test_contributions_use_decimal_round_half_even(
    quantity_weight: int, expected: int
) -> None:
    policy = MatchingPolicy.initial_demo()
    weights = tuple(
        FeatureWeight(
            item.feature,
            quantity_weight
            if item.feature is MatchFeature.QUANTITY
            else item.weight_bp
            + (3_500 - quantity_weight if item.feature is MatchFeature.TIMESTAMP else 0),
        )
        for item in policy.feature_weights
    )
    policy = replace(
        policy,
        feature_weights=weights,
        quantity_similarity=NumericSimilarityPolicy(Decimal("2"), Decimal("0")),
    )

    result = score(record("L1", quantity=Decimal("0")), record("R1", quantity=Decimal("1")), policy=policy)

    assert feature(result, MatchFeature.QUANTITY).contribution_bp == expected


def test_exact_ninety_percent_similarity_produces_threshold_scale_score() -> None:
    policy = replace(
        MatchingPolicy.initial_demo(),
        quantity_similarity=NumericSimilarityPolicy(Decimal("10"), Decimal("0")),
        unit_price_similarity=NumericSimilarityPolicy(Decimal("10"), Decimal("0")),
        gross_amount_similarity=NumericSimilarityPolicy(Decimal("10"), Decimal("0")),
    )
    result = score(
        record("L1", quantity=Decimal("0"), unit_price=Decimal("0"), gross_amount=Decimal("0")),
        record(
            "R1",
            quantity=Decimal("1"),
            executed_at=BASE_TIME + timedelta(minutes=1),
            unit_price=Decimal("1"),
            gross_amount=Decimal("1"),
        ),
        policy=policy,
    )

    assert result.score_bp == 9_000


def test_generated_partition_limit_marks_candidate_computation_incomplete() -> None:
    policy = replace(
        MatchingPolicy.initial_demo(),
        limits=replace(MatchingPolicy.initial_demo().limits, max_candidates_per_record=1),
    )
    preprocessed = preprocess_references(
        snapshot=EngineSnapshot(
            "left-v1",
            "right-v1",
            (record("L1"),),
            (record("R1"), record("R2")),
        ),
        decisions=DecisionInputs(),
        reference_contract=policy.reference_contract,
    )
    generated = generate_candidates(preprocessed=preprocessed, policy=policy)
    results = score_candidates(preprocessed=preprocessed, generated=generated, policy=policy)

    assert len(results) == 1
    assert results[0].complete_computation is False


def test_sparse_alias_candidate_is_retained_as_evidence_but_fails_coverage() -> None:
    policy = replace(
        MatchingPolicy.initial_demo(),
        blocking_passes=(
            BlockingPassPolicy(
                "alias-without-time",
                "1",
                None,
                require_instrument=False,
                require_side=False,
                require_currency=False,
                use_shared_alias=True,
            ),
        ),
    )
    preprocessed = preprocess_references(
        snapshot=EngineSnapshot(
            "left-v1",
            "right-v1",
            (record("L1", executed_at=None, shared_reference_alias="A"),),
            (record("R1", executed_at=None, shared_reference_alias="A"),),
        ),
        decisions=DecisionInputs(),
        reference_contract=policy.reference_contract,
    )
    generated = generate_candidates(preprocessed=preprocessed, policy=policy)
    results = score_candidates(preprocessed=preprocessed, generated=generated, policy=policy)

    assert len(results) == 1
    assert results[0].coverage_sufficient is False
    assert results[0].coverage_failures == (CoverageFailure.MISSING_TIMESTAMP.value,)
    assert feature(results[0], MatchFeature.TIMESTAMP).contribution_bp == 0


def test_decimal_context_cannot_change_fixed_point_score() -> None:
    policy = replace(
        MatchingPolicy.initial_demo(),
        quantity_similarity=NumericSimilarityPolicy(Decimal("1.01"), Decimal("0")),
    )
    expected = score(record("L1"), record("R1", quantity=Decimal("101")), policy=policy)

    with localcontext() as context:
        context.prec = 3
        context.rounding = ROUND_DOWN
        constrained = score(
            record("L1"), record("R1", quantity=Decimal("101")), policy=policy
        )

    assert constrained == expected


def test_scoring_rejects_candidate_edge_outside_remaining_inputs() -> None:
    preprocessed = preprocess_references(
        snapshot=EngineSnapshot("left-v1", "right-v1", (record("L1"),), (record("R1"),)),
        decisions=DecisionInputs(),
        reference_contract=ReferenceContract.SHARED_MUST_AGREE,
    )
    generated = CandidateGenerationResult(
        candidates=(CandidateEdge("missing", "R1", ("test@1",)),),
        partitions=(),
        limited_record_ids=(),
        complete=True,
    )

    with pytest.raises(DomainValidationError, match="remaining after preprocessing"):
        score_candidates(preprocessed=preprocessed, generated=generated, policy=MatchingPolicy.initial_demo())


def test_evidence_language_is_factual_and_never_claims_unsupported_causes() -> None:
    result = score(record("L1"), record("R1", quantity=None))
    rendered = " ".join(
        [result.score_label, *result.contradictions, *result.coverage_failures]
        + [item.rule for item in result.features]
    ).lower()

    assert result.score_label == "Rule score"
    assert all(word not in rendered for word in ("probability", "fee", "fraud", "intent"))


def test_scoring_is_identical_for_reordered_candidate_input() -> None:
    preprocessed = preprocess_references(
        snapshot=EngineSnapshot(
            "left-v1",
            "right-v1",
            (record("L2"), record("L1")),
            (record("R2"), record("R1")),
        ),
        decisions=DecisionInputs(),
        reference_contract=ReferenceContract.SHARED_MUST_AGREE,
    )
    generated = generate_candidates(
        preprocessed=preprocessed, policy=MatchingPolicy.initial_demo()
    )
    reversed_generated = replace(generated, candidates=tuple(reversed(generated.candidates)))

    assert score_candidates(
        preprocessed=preprocessed,
        generated=generated,
        policy=MatchingPolicy.initial_demo(),
    ) == score_candidates(
        preprocessed=preprocessed,
        generated=reversed_generated,
        policy=MatchingPolicy.initial_demo(),
    )
