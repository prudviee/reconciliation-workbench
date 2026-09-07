from __future__ import annotations

import itertools
import subprocess
import sys
import textwrap
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from reconciliation.domain import (
    CapacityLimits,
    CanonicalSide,
    CanonicalState,
    ComparisonPolicy,
    ComparisonStatus,
    DecisionInputs,
    DomainValidationError,
    EngineSnapshot,
    FeatureWeight,
    ManualLink,
    MatchFeature,
    MatchRecord,
    MatchingPolicy,
    NumericSimilarityPolicy,
    PairOrigin,
    RecordSide,
    RejectedRelationship,
    TimestampSimilarityPolicy,
    UnpairedReason,
    candidate_graph_digest,
    canonical_result_json,
    engine_result_digest,
    reconcile,
)
from reconciliation.solvers import ScipyAssignmentSolver


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


def run(
    left: tuple[MatchRecord, ...],
    right: tuple[MatchRecord, ...],
    *,
    matching_policy: MatchingPolicy | None = None,
    comparison_policy: ComparisonPolicy | None = None,
    decisions: DecisionInputs = DecisionInputs(),
):
    return reconcile(
        snapshot=EngineSnapshot("left-revision", "right-revision", left, right),
        matching_policy=matching_policy or MatchingPolicy.initial_demo(),
        comparison_policy=comparison_policy or ComparisonPolicy.initial_demo(),
        decisions=decisions,
        solver=ScipyAssignmentSolver(),
    )


def pair_edges(result) -> set[tuple[str, str]]:
    return {(item.left_id, item.right_id) for item in result.pairs}


def unpaired_reasons(result) -> dict[str, UnpairedReason]:
    return {item.record_id: item.reason for item in result.unpaired}


def test_end_to_end_weighted_pair_has_comparisons_and_complete_evidence() -> None:
    result = run((record("L1"),), (record("R1"),))

    assert pair_edges(result) == {("L1", "R1")}
    assert result.pairs[0].origin is PairOrigin.WEIGHTED_GLOBAL
    assert result.pairs[0].score_bp == 10_000
    assert result.pairs[0].global_gap_bp == 3_000
    assert len(result.pairs[0].comparisons) == 9
    assert result.unpaired == ()
    assert len(result.candidates) == 1
    assert len(result.components) == 1
    assert result.components[0].proposals[0].accepted is True

    with pytest.raises(DomainValidationError, match="weighted-global"):
        replace(result, components=())
    foreign_candidate = replace(result.candidates[0], left_id="foreign-left")
    with pytest.raises(DomainValidationError, match="result inputs"):
        replace(result, candidates=(foreign_candidate,))


def test_manual_and_authoritative_pairs_keep_identity_and_expose_comparisons() -> None:
    result = run(
        (
            record("L1", reference_value="LEFT"),
            record("L2", reference_value="T-1011", gross_amount=Decimal("34000")),
        ),
        (
            record("R1", reference_value="RIGHT", currency="EUR"),
            record("R2", reference_value="T-1011", gross_amount=Decimal("34170")),
        ),
        decisions=DecisionInputs(
            manual_links=(ManualLink("manual-1", "revision-1", "L1", "R1"),)
        ),
    )

    assert [(item.left_id, item.right_id, item.origin) for item in result.pairs] == [
        ("L1", "R1", PairOrigin.MANUAL),
        ("L2", "R2", PairOrigin.AUTHORITATIVE_REFERENCE),
    ]
    manual = {item.field: item for item in result.pairs[0].comparisons}
    authoritative = {item.field: item for item in result.pairs[1].comparisons}
    assert manual["currency"].status is ComparisonStatus.DISCREPANT
    assert manual["gross_amount"].status is ComparisonStatus.NOT_COMPARABLE
    assert authoritative["gross_amount"].status is ComparisonStatus.DISCREPANT
    assert authoritative["gross_amount"].signed_difference == Decimal("170")


def test_equal_optimum_abstains_and_classifies_every_record_ambiguous() -> None:
    result = run(
        (record("L1"), record("L2")),
        (record("R1"), record("R2")),
    )

    assert result.pairs == ()
    assert set(unpaired_reasons(result)) == {"L1", "L2", "R1", "R2"}
    assert set(unpaired_reasons(result).values()) == {UnpairedReason.AMBIGUOUS}
    assert all(
        proposal.global_gap_bp == 0 and not proposal.accepted
        for proposal in result.components[0].proposals
    )


def test_below_floor_and_no_candidate_have_distinct_terminal_reasons() -> None:
    below = run(
        (record("L1", quantity=Decimal("1"), unit_price=Decimal("1"), gross_amount=Decimal("1")),),
        (
            record(
                "R1",
                quantity=Decimal("100"),
                executed_at=BASE_TIME + timedelta(hours=1),
                unit_price=Decimal("100"),
                gross_amount=Decimal("100"),
            ),
        ),
    )
    absent = run((record("L2", instrument="BTC"),), (record("R2", instrument="ETH"),))

    assert set(unpaired_reasons(below).values()) == {UnpairedReason.BELOW_ASSIGNMENT_FLOOR}
    assert set(unpaired_reasons(absent).values()) == {UnpairedReason.NO_CANDIDATE}


def test_active_rejection_and_component_limit_have_explicit_terminal_reasons() -> None:
    rejected = run(
        (record("L1"),),
        (record("R1"),),
        decisions=DecisionInputs(
            rejected_relationships=(
                RejectedRelationship("reject-1", "revision-1", "L1", "R1"),
            )
        ),
    )
    policy = replace(
        MatchingPolicy.initial_demo(),
        limits=CapacityLimits(1, 2_500, 250_000, 200),
    )
    limited = run((record("L2"),), (record("R2"),), matching_policy=policy)

    assert set(unpaired_reasons(rejected).values()) == {UnpairedReason.PROHIBITED}
    assert set(unpaired_reasons(limited).values()) == {UnpairedReason.COMPUTATION_LIMITED}
    assert limited.components[0].complete is False


def test_global_assignment_stage_is_preserved_by_orchestration() -> None:
    policy = replace(
        MatchingPolicy.initial_demo(),
        feature_weights=(
            FeatureWeight(MatchFeature.QUANTITY, 10_000),
            FeatureWeight(MatchFeature.TIMESTAMP, 0),
            FeatureWeight(MatchFeature.UNIT_PRICE, 0),
            FeatureWeight(MatchFeature.GROSS_AMOUNT, 0),
        ),
        quantity_similarity=NumericSimilarityPolicy(Decimal("20"), Decimal("0")),
        timestamp_similarity=TimestampSimilarityPolicy(timedelta(0)),
        automatic_threshold_bp=8_500,
        minimum_global_gap_bp=400,
    )
    result = run(
        (
            record("L1", quantity=Decimal("10")),
            record("L2", quantity=Decimal("12")),
        ),
        (
            record("R1", quantity=Decimal("10.5")),
            record("R2", quantity=Decimal("9")),
        ),
        matching_policy=policy,
    )

    assert pair_edges(result) == {("L1", "R2"), ("L2", "R1")}
    assert {(item.left_id, item.right_id): item.score_bp for item in result.pairs} == {
        ("L1", "R2"): 9_500,
        ("L2", "R1"): 9_250,
    }


def test_every_input_has_exactly_one_terminal_outcome() -> None:
    result = run(
        (
            record("L1", reference_value="T-1"),
            record("L2", instrument="LEFT-ONLY"),
            record("L3", state=CanonicalState.CANCELLED),
        ),
        (
            record("R1", reference_value="T-1"),
            record("R2", instrument="RIGHT-ONLY"),
        ),
    )

    terminal = [
        *(item.left_id for item in result.pairs),
        *(item.right_id for item in result.pairs),
        *(item.record_id for item in result.unpaired),
    ]
    assert sorted(terminal) == ["L1", "L2", "L3", "R1", "R2"]
    assert len(terminal) == len(set(terminal))

    with pytest.raises(DomainValidationError):
        replace(result, unpaired=result.unpaired[:-1])
    with pytest.raises(DomainValidationError):
        replace(result, unpaired=(*result.unpaired, result.unpaired[0]))


def test_576_input_permutations_produce_the_same_canonical_result() -> None:
    left = tuple(
        record(f"L{index}", instrument=f"ASSET-{index}") for index in range(4)
    )
    right = tuple(
        record(f"R{index}", instrument=f"ASSET-{index}") for index in range(4)
    )
    expected = run(left, right)
    checked = 0
    for left_order in itertools.permutations(left):
        for right_order in itertools.permutations(right):
            assert run(left_order, right_order) == expected
            checked += 1
    assert checked == 576


def test_candidate_and_result_digests_are_canonical_and_type_preserving() -> None:
    left = (
        record("L1", instrument="ASSET-1", quantity=Decimal("2.0")),
        record("L2", instrument="ASSET-2", quantity=Decimal("3")),
    )
    right = (
        record("R1", instrument="ASSET-1", quantity=Decimal("2.00")),
        record("R2", instrument="ASSET-2", quantity=Decimal("3")),
    )
    first = run(left, right)
    second = run(tuple(reversed(left)), tuple(reversed(right)))

    assert candidate_graph_digest(first.candidates) == candidate_graph_digest(
        tuple(reversed(first.candidates))
    )
    assert engine_result_digest(first) == engine_result_digest(second)
    assert len(engine_result_digest(first)) == 64
    payload = canonical_result_json(first)
    assert '"decimal":"2"' in payload
    assert '"datetime":"2026-09-07T12:00:00.000000Z"' in payload


def test_reconcile_runs_in_subprocess_with_framework_and_runtime_io_blocked() -> None:
    project_root = Path(__file__).resolve().parents[1]
    script = textwrap.dedent(
        """
        import builtins
        import socket
        import time
        from datetime import UTC, datetime
        from decimal import Decimal
        from reconciliation.domain import (
            CanonicalSide, CanonicalState, ComparisonPolicy, DecisionInputs,
            EngineSnapshot, MatchRecord, MatchingPolicy, engine_result_digest, reconcile,
        )

        class Solver:
            version = MatchingPolicy.initial_demo().solver_version
            def minimize(self, costs):
                return tuple(
                    (row_index, min(range(len(row)), key=lambda column: (row[column], column)))
                    for row_index, row in enumerate(costs)
                )

        def record(identity):
            return MatchRecord(
                identity, f"logical-{identity}", f"source-{identity}",
                CanonicalState.SETTLED, "BTC-USD", CanonicalSide.BUY, "USD",
                Decimal("2"), datetime(2026, 9, 7, 12, tzinfo=UTC),
                Decimal("100"), Decimal("200"), None, None,
            )

        original_import = builtins.__import__
        def guarded_import(name, *args, **kwargs):
            if name == "django" or name.startswith("django."):
                raise AssertionError("framework access is forbidden")
            return original_import(name, *args, **kwargs)
        builtins.__import__ = guarded_import
        builtins.open = lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("filesystem access is forbidden"))
        socket.socket = lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("network access is forbidden"))
        time.time = lambda: (_ for _ in ()).throw(AssertionError("clock access is forbidden"))

        result = reconcile(
            snapshot=EngineSnapshot("left-v1", "right-v1", (record("L1"),), (record("R1"),)),
            matching_policy=MatchingPolicy.initial_demo(),
            comparison_policy=ComparisonPolicy.initial_demo(),
            decisions=DecisionInputs(),
            solver=Solver(),
        )
        print(engine_result_digest(result))
        """
    )

    first = subprocess.run(
        [sys.executable, "-c", script],
        cwd=project_root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    second = subprocess.run(
        [sys.executable, "-c", script],
        cwd=project_root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    assert first == second
    assert first == "5978c24d74750144676ddad50046e8b1de753623af55154742450fa9f0acc4de"
