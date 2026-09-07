from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from reconciliation.domain import (
    BlockingPassPolicy,
    CandidateLimitReason,
    CandidateGenerationResult,
    CanonicalSide,
    CanonicalState,
    CapacityLimits,
    DecisionInputs,
    DomainValidationError,
    EngineSnapshot,
    MatchRecord,
    MatchingPolicy,
    ReferenceContract,
    RejectedRelationship,
    generate_candidates,
    preprocess_references,
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
        "quantity": Decimal("2"),
        "executed_at": BASE_TIME,
        "unit_price": Decimal("100"),
        "gross_amount": Decimal("200"),
        "reference_value": None,
        "shared_reference_alias": None,
    }
    values.update(overrides)
    return MatchRecord(**values)  # type: ignore[arg-type]


def generate(
    left: tuple[MatchRecord, ...],
    right: tuple[MatchRecord, ...],
    *,
    policy: MatchingPolicy | None = None,
    decisions: DecisionInputs = DecisionInputs(),
):
    selected_policy = policy or MatchingPolicy.initial_demo()
    preprocessed = preprocess_references(
        snapshot=EngineSnapshot("left-v1", "right-v1", left, right),
        decisions=decisions,
        reference_contract=selected_policy.reference_contract,
    )
    return generate_candidates(preprocessed=preprocessed, policy=selected_policy)


def edge_map(result) -> dict[tuple[str, str], tuple[str, ...]]:
    return {
        (item.left_id, item.right_id): item.blocking_reasons
        for item in result.candidates
    }


def test_general_pass_requires_compatible_fields_and_inclusive_24_hour_window() -> None:
    result = generate(
        (record("L1"),),
        (
            record("R-boundary", executed_at=BASE_TIME + timedelta(hours=24)),
            record("R-after", executed_at=BASE_TIME + timedelta(hours=24, microseconds=1)),
            record("R-instrument", instrument="ETH-USD"),
            record("R-side", side=CanonicalSide.SELL),
            record("R-currency", currency="EUR"),
        ),
    )

    assert edge_map(result) == {
        ("L1", "R-boundary"): ("general-compatible-24h@1",)
    }
    assert result.complete is True


def test_multiple_versioned_passes_are_unioned_and_reasons_are_deduplicated() -> None:
    passes = (
        BlockingPassPolicy("general-1h", "1", timedelta(hours=1)),
        BlockingPassPolicy(
            "shared-alias-48h",
            "2",
            timedelta(hours=48),
            require_instrument=False,
            require_side=False,
            require_currency=False,
            use_shared_alias=True,
        ),
    )
    policy = replace(MatchingPolicy.initial_demo(), blocking_passes=passes)
    result = generate(
        (
            record("L1", shared_reference_alias="A"),
            record("L2", shared_reference_alias="B", executed_at=BASE_TIME + timedelta(hours=3)),
        ),
        (
            record("R1", shared_reference_alias="A"),
            record("R2", shared_reference_alias="B"),
        ),
        policy=policy,
    )

    assert edge_map(result) == {
        ("L1", "R1"): ("general-1h@1", "shared-alias-48h@2"),
        ("L1", "R2"): ("general-1h@1",),
        ("L2", "R2"): ("shared-alias-48h@2",),
    }


def test_active_rejected_relationship_never_enters_candidate_union() -> None:
    result = generate(
        (record("L1"), record("L2")),
        (record("R1"),),
        decisions=DecisionInputs(
            rejected_relationships=(
                RejectedRelationship("reject-1", "rev-1", "L1", "R1"),
            )
        ),
    )

    assert edge_map(result) == {("L2", "R1"): ("general-compatible-24h@1",)}


def test_missing_required_blocking_value_or_timestamp_produces_no_candidate_without_truncation() -> None:
    result = generate(
        (
            record("L-instrument", instrument=None),
            record("L-side", side=None),
            record("L-currency", currency=None),
            record("L-time", executed_at=None),
        ),
        (record("R1"),),
    )

    assert result.candidates == ()
    assert result.partitions == ()
    assert result.complete is True
    assert result.limited_record_ids == ()


def test_explicit_alias_pass_without_time_window_can_surface_sparse_candidate() -> None:
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
    result = generate(
        (record("L1", executed_at=None, shared_reference_alias="A"),),
        (record("R1", executed_at=None, shared_reference_alias="A"),),
        policy=policy,
    )

    assert edge_map(result) == {
        ("L1", "R1"): ("alias-without-time@1",)
    }
    assert result.complete is True


def test_per_record_limit_is_inclusive_then_marks_entire_partition_incomplete() -> None:
    limits = CapacityLimits(
        max_component_nodes=100,
        max_component_edges=2_500,
        max_run_candidate_edges=250_000,
        max_candidates_per_record=2,
    )
    policy = replace(MatchingPolicy.initial_demo(), limits=limits)
    exact = generate(
        (record("L1"),),
        (record("R1"), record("R2")),
        policy=policy,
    )
    exceeded = generate(
        (record("L1"),),
        (record("R1"), record("R2"), record("R3")),
        policy=policy,
    )

    assert len(exact.candidates) == 2
    assert exact.complete is True
    assert len(exceeded.candidates) == 2
    assert exceeded.complete is False
    assert exceeded.partitions[0].limit_reason is CandidateLimitReason.PER_RECORD_LIMIT
    assert exceeded.limited_record_ids == ("L1", "R1", "R2", "R3")


def test_run_edge_limit_allows_exact_boundary_and_withholds_later_partitions() -> None:
    limits = CapacityLimits(
        max_component_nodes=100,
        max_component_edges=2_500,
        max_run_candidate_edges=2,
        max_candidates_per_record=200,
    )
    policy = replace(MatchingPolicy.initial_demo(), limits=limits)
    exact = generate(
        (record("L1", instrument="A"), record("L2", instrument="B")),
        (record("R1", instrument="A"), record("R2", instrument="B")),
        policy=policy,
    )
    exceeded = generate(
        (
            record("L1", instrument="A"),
            record("L2", instrument="B"),
            record("L3", instrument="C"),
        ),
        (
            record("R1", instrument="A"),
            record("R2", instrument="B"),
            record("R3", instrument="C"),
        ),
        policy=policy,
    )

    assert len(exact.candidates) == 2 and exact.complete is True
    assert len(exceeded.candidates) == 2 and exceeded.complete is False
    limited = [item for item in exceeded.partitions if not item.complete]
    assert len(limited) == 1
    assert limited[0].limit_reason is CandidateLimitReason.RUN_EDGE_LIMIT
    assert set(exceeded.limited_record_ids) == {"L3", "R3"}


def test_incompleteness_propagates_across_overlapping_pass_partitions() -> None:
    passes = (
        BlockingPassPolicy(
            "a-alias",
            "1",
            timedelta(hours=1),
            require_instrument=False,
            require_side=False,
            require_currency=False,
            use_shared_alias=True,
        ),
        BlockingPassPolicy("z-dense", "1", timedelta(hours=1)),
    )
    policy = replace(
        MatchingPolicy.initial_demo(),
        blocking_passes=passes,
        limits=CapacityLimits(
            max_component_nodes=100,
            max_component_edges=2_500,
            max_run_candidate_edges=250_000,
            max_candidates_per_record=1,
        ),
        reference_contract=ReferenceContract.SHARED_MUST_AGREE,
    )
    result = generate(
        (
            record("L1", instrument="A", shared_reference_alias="X"),
        ),
        (
            record("R1", instrument="A", shared_reference_alias="Y"),
            record("R2", instrument="A", shared_reference_alias="Z"),
            record("R3", instrument="B", shared_reference_alias="X"),
        ),
        policy=policy,
    )

    assert result.complete is False
    assert set(result.limited_record_ids) == {"L1", "R1", "R2", "R3"}
    reasons = {item.blocking_pass: item.limit_reason for item in result.partitions}
    assert reasons["z-dense@1"] is CandidateLimitReason.PER_RECORD_LIMIT
    assert reasons["a-alias@1"] is CandidateLimitReason.CONNECTED_TO_INCOMPLETE_PARTITION


def test_candidate_generation_is_identical_under_input_and_pass_reordering() -> None:
    passes = (
        BlockingPassPolicy("general", "1", timedelta(hours=24)),
        BlockingPassPolicy(
            "alias",
            "1",
            timedelta(hours=48),
            require_instrument=False,
            require_side=False,
            require_currency=False,
            use_shared_alias=True,
        ),
    )
    first_policy = replace(MatchingPolicy.initial_demo(), blocking_passes=passes)
    second_policy = replace(MatchingPolicy.initial_demo(), blocking_passes=tuple(reversed(passes)))
    left = (
        record("L2", shared_reference_alias="B"),
        record("L1", shared_reference_alias="A"),
    )
    right = (
        record("R2", shared_reference_alias="B"),
        record("R1", shared_reference_alias="A"),
    )

    first = generate(left, right, policy=first_policy)
    second = generate(tuple(reversed(left)), tuple(reversed(right)), policy=second_policy)

    assert first == second


def test_search_window_is_independent_from_similarity_and_comparison_tolerances() -> None:
    policy = MatchingPolicy.initial_demo()
    result = generate(
        (record("L1"),),
        (record("R1", executed_at=BASE_TIME + timedelta(minutes=30)),),
        policy=policy,
    )

    assert len(result.candidates) == 1
    assert policy.blocking_passes[0].time_window == timedelta(hours=24)
    assert policy.timestamp_similarity.band == timedelta(minutes=10)
    # Comparison policy is a separate contract and is never accepted by this function.
    assert "comparison" not in generate_candidates.__annotations__


def test_candidate_result_rejects_integer_used_as_completeness_flag() -> None:
    with pytest.raises(DomainValidationError, match="complete must be boolean"):
        CandidateGenerationResult((), (), (), 1)  # type: ignore[arg-type]
