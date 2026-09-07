from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from reconciliation.domain import (
    INITIAL_ASSIGNMENT_FLOOR_BP,
    INITIAL_AUTOMATIC_THRESHOLD_BP,
    INITIAL_GLOBAL_GAP_BP,
    AcceptedUnmatched,
    CapacityLimits,
    ComparisonPolicy,
    DecisionInputs,
    DomainValidationError,
    EngineResult,
    EngineSnapshot,
    FeatureWeight,
    ManualLink,
    MatchFeature,
    MatchRecord,
    MatchingPolicy,
    PairOrigin,
    PairOutcome,
    RecordSide,
    ReservedIdentity,
    UnpairedOutcome,
    UnpairedReason,
    CanonicalSide,
    CanonicalState,
)


def record(identity: str, **overrides: object) -> MatchRecord:
    values: dict[str, object] = {
        "observation_id": identity,
        "logical_transaction_id": f"logical-{identity}",
        "source_record_key": f"source-{identity}",
        "state": CanonicalState.SETTLED,
        "instrument": "BTC-USD",
        "side": CanonicalSide.BUY,
        "currency": "USD",
        "quantity": Decimal("2"),
        "executed_at": datetime(2026, 9, 7, 12, tzinfo=UTC),
        "unit_price": Decimal("100"),
        "gross_amount": Decimal("200"),
        "reference_value": "T-1011",
    }
    values.update(overrides)
    return MatchRecord(**values)  # type: ignore[arg-type]


def unpaired(identity: str, side: RecordSide) -> UnpairedOutcome:
    return UnpairedOutcome(
        record_id=identity,
        side=side,
        reason=UnpairedReason.NO_CANDIDATE,
        explanation="No candidate was found in the complete search window.",
    )


def result(**overrides: object) -> EngineResult:
    values: dict[str, object] = {
        "left_revision_id": "left-revision-1",
        "right_revision_id": "right-revision-1",
        "matching_policy_version": "demo-matching-v1",
        "comparison_policy_version": "demo-comparison-v1",
        "engine_version": "reconciliation-engine-v1",
        "solver_version": "solver-v1",
        "input_left_ids": ("L1",),
        "input_right_ids": ("R1",),
        "pairs": (),
        "unpaired": (unpaired("L1", RecordSide.LEFT), unpaired("R1", RecordSide.RIGHT)),
    }
    values.update(overrides)
    return EngineResult(**values)  # type: ignore[arg-type]


def test_snapshot_is_immutable_canonical_and_normalizes_aware_times_to_utc() -> None:
    plus_five_thirty = timezone(timedelta(hours=5, minutes=30))
    later = record("L2")
    earlier = record(
        "L1",
        executed_at=datetime(2026, 9, 7, 17, 30, tzinfo=plus_five_thirty),
    )

    snapshot = EngineSnapshot("left-v1", "right-v1", (later, earlier), (record("R1"),))

    assert snapshot.input_left_ids == ("L1", "L2")
    assert snapshot.left[0].executed_at == datetime(2026, 9, 7, 12, tzinfo=UTC)
    with pytest.raises(FrozenInstanceError):
        snapshot.left_revision_id = "changed"  # type: ignore[misc]


@pytest.mark.parametrize(
    "overrides",
    [
        {"observation_id": " "},
        {"quantity": Decimal("NaN")},
        {"gross_amount": Decimal("Infinity")},
        {"unit_price": Decimal("-1")},
        {"executed_at": datetime(2026, 9, 7, 12)},
        {"currency": ""},
    ],
)
def test_match_record_rejects_invalid_identity_decimal_time_or_optional_text(
    overrides: dict[str, object],
) -> None:
    with pytest.raises(DomainValidationError):
        record("L1", **overrides)


def test_contracts_reject_untyped_enum_and_boolean_values() -> None:
    with pytest.raises(DomainValidationError, match="CanonicalState"):
        record("L1", state="SETTLED")
    with pytest.raises(DomainValidationError, match="CanonicalSide"):
        record("L1", side="BUY")
    policy = MatchingPolicy.initial_demo()
    bad_pass = policy.blocking_passes[0]
    with pytest.raises(DomainValidationError, match="boolean"):
        type(bad_pass)(
            pass_id=bad_pass.pass_id,
            version=bad_pass.version,
            time_window=bad_pass.time_window,
            require_instrument=1,  # type: ignore[arg-type]
        )


def test_cancelled_record_remains_evidence_but_is_not_eligible() -> None:
    cancelled = record("L1", state=CanonicalState.CANCELLED)

    assert cancelled.eligible is False
    assert record("L2").eligible is True


def test_snapshot_rejects_duplicate_or_cross_side_observation_identity() -> None:
    with pytest.raises(DomainValidationError, match="left observation"):
        EngineSnapshot("left-v1", "right-v1", (record("same"), record("same")), ())
    with pytest.raises(DomainValidationError, match="across sides"):
        EngineSnapshot("left-v1", "right-v1", (record("same"),), (record("same"),))


def test_initial_demo_policy_uses_documented_integer_scale_and_separate_windows() -> None:
    matching = MatchingPolicy.initial_demo()
    comparison = ComparisonPolicy.initial_demo()

    assert {item.feature: item.weight_bp for item in matching.feature_weights} == {
        MatchFeature.QUANTITY: 3_500,
        MatchFeature.TIMESTAMP: 2_500,
        MatchFeature.UNIT_PRICE: 1_500,
        MatchFeature.GROSS_AMOUNT: 2_500,
    }
    assert matching.assignment_floor_bp == INITIAL_ASSIGNMENT_FLOOR_BP == 7_000
    assert matching.automatic_threshold_bp == INITIAL_AUTOMATIC_THRESHOLD_BP == 9_000
    assert matching.minimum_global_gap_bp == INITIAL_GLOBAL_GAP_BP == 800
    assert matching.blocking_passes[0].time_window == timedelta(hours=24)
    assert matching.timestamp_similarity.band == timedelta(minutes=10)
    assert comparison.timestamp_tolerance == timedelta(seconds=60)
    assert matching.limits == CapacityLimits(100, 2_500, 250_000, 200)


def test_matching_policy_requires_complete_unique_weights_totalling_score_scale() -> None:
    policy = MatchingPolicy.initial_demo()
    missing = tuple(item for item in policy.feature_weights if item.feature is not MatchFeature.GROSS_AMOUNT)
    duplicate = policy.feature_weights + (FeatureWeight(MatchFeature.QUANTITY, 0),)
    wrong_total = tuple(
        FeatureWeight(item.feature, item.weight_bp - (1 if item.feature is MatchFeature.QUANTITY else 0))
        for item in policy.feature_weights
    )

    for weights in (missing, duplicate, wrong_total):
        with pytest.raises(DomainValidationError):
            MatchingPolicy(
                policy_version=policy.policy_version,
                engine_version=policy.engine_version,
                solver_version=policy.solver_version,
                reference_contract=policy.reference_contract,
                blocking_passes=policy.blocking_passes,
                feature_weights=weights,
                quantity_similarity=policy.quantity_similarity,
                timestamp_similarity=policy.timestamp_similarity,
                unit_price_similarity=policy.unit_price_similarity,
                gross_amount_similarity=policy.gross_amount_similarity,
            )


@pytest.mark.parametrize(
    "field,value",
    [
        ("assignment_floor_bp", -1),
        ("assignment_floor_bp", 10_001),
        ("automatic_threshold_bp", 6_999),
        ("minimum_global_gap_bp", 9_001),
    ],
)
def test_matching_policy_rejects_invalid_threshold_boundaries(field: str, value: int) -> None:
    policy = MatchingPolicy.initial_demo()
    values = {
        "policy_version": policy.policy_version,
        "engine_version": policy.engine_version,
        "solver_version": policy.solver_version,
        "reference_contract": policy.reference_contract,
        "blocking_passes": policy.blocking_passes,
        "feature_weights": policy.feature_weights,
        "quantity_similarity": policy.quantity_similarity,
        "timestamp_similarity": policy.timestamp_similarity,
        "unit_price_similarity": policy.unit_price_similarity,
        "gross_amount_similarity": policy.gross_amount_similarity,
        "assignment_floor_bp": policy.assignment_floor_bp,
        "automatic_threshold_bp": policy.automatic_threshold_bp,
        "minimum_global_gap_bp": policy.minimum_global_gap_bp,
    }
    values[field] = value

    with pytest.raises(DomainValidationError):
        MatchingPolicy(**values)  # type: ignore[arg-type]


def test_capacity_limits_accept_exact_contract_and_reject_zero_or_boolean() -> None:
    assert CapacityLimits().max_run_candidate_edges == 250_000
    with pytest.raises(DomainValidationError):
        CapacityLimits(max_component_nodes=0)
    with pytest.raises(DomainValidationError):
        CapacityLimits(max_candidates_per_record=True)  # type: ignore[arg-type]


def test_decisions_are_canonical_and_conflicting_reservations_are_rejected() -> None:
    decisions = DecisionInputs(
        accepted_unmatched=(AcceptedUnmatched("D2", "2", "L2"),),
        manual_links=(
            ManualLink("D1", "1", "L3", "R3"),
            ManualLink("D0", "1", "L1", "R1"),
        ),
    )

    assert tuple(item.left_id for item in decisions.manual_links) == ("L1", "L3")
    with pytest.raises(DomainValidationError, match="manually linked and singly reserved"):
        DecisionInputs(
            manual_links=(ManualLink("D1", "1", "L1", "R1"),),
            reserved_identities=(ReservedIdentity("D2", "1", "L1"),),
        )
    with pytest.raises(DomainValidationError, match="manual-link left"):
        DecisionInputs(
            manual_links=(
                ManualLink("D1", "1", "L1", "R1"),
                ManualLink("D2", "1", "L1", "R2"),
            )
        )


def test_weighted_pair_requires_rule_score_and_global_gap() -> None:
    with pytest.raises(DomainValidationError, match="require score"):
        PairOutcome("L1", "R1", PairOrigin.WEIGHTED_GLOBAL)
    with pytest.raises(DomainValidationError, match="do not carry"):
        PairOutcome("L1", "R1", PairOrigin.MANUAL, score_bp=9_500)
    assert PairOutcome(
        "L1", "R1", PairOrigin.WEIGHTED_GLOBAL, score_bp=9_000, global_gap_bp=800
    ).score_bp == 9_000


def test_result_canonicalizes_order_and_accepts_exact_terminal_coverage() -> None:
    built = result(
        input_left_ids=("L2", "L1"),
        input_right_ids=("R2", "R1"),
        pairs=(PairOutcome("L2", "R2", PairOrigin.AUTHORITATIVE_REFERENCE),),
        unpaired=(unpaired("R1", RecordSide.RIGHT), unpaired("L1", RecordSide.LEFT)),
    )

    assert built.input_left_ids == ("L1", "L2")
    assert built.input_right_ids == ("R1", "R2")
    assert tuple(item.record_id for item in built.unpaired) == ("L1", "R1")


@pytest.mark.parametrize(
    "changes",
    [
        {"unpaired": (unpaired("L1", RecordSide.LEFT),)},
        {
            "pairs": (PairOutcome("L1", "R1", PairOrigin.MANUAL),),
            "unpaired": (unpaired("L1", RecordSide.LEFT),),
        },
        {"unpaired": (unpaired("L1", RecordSide.RIGHT), unpaired("R1", RecordSide.RIGHT))},
        {
            "input_left_ids": ("L1", "L2"),
            "unpaired": (
                unpaired("L1", RecordSide.LEFT),
                unpaired("L1", RecordSide.LEFT),
                unpaired("R1", RecordSide.RIGHT),
            ),
        },
    ],
)
def test_result_rejects_missing_duplicate_wrong_side_or_double_terminal_outcomes(
    changes: dict[str, object],
) -> None:
    with pytest.raises(DomainValidationError):
        result(**changes)


def test_result_is_identical_for_different_input_and_outcome_order() -> None:
    first = result(
        input_left_ids=("L2", "L1"),
        input_right_ids=("R2", "R1"),
        pairs=(),
        unpaired=(
            unpaired("R2", RecordSide.RIGHT),
            unpaired("L2", RecordSide.LEFT),
            unpaired("R1", RecordSide.RIGHT),
            unpaired("L1", RecordSide.LEFT),
        ),
    )
    second = result(
        input_left_ids=("L1", "L2"),
        input_right_ids=("R1", "R2"),
        pairs=(),
        unpaired=(
            unpaired("L1", RecordSide.LEFT),
            unpaired("R1", RecordSide.RIGHT),
            unpaired("L2", RecordSide.LEFT),
            unpaired("R2", RecordSide.RIGHT),
        ),
    )

    assert first == second
