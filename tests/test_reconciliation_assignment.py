from __future__ import annotations

import random
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from reconciliation.domain import (
    AssignmentLimitReason,
    CandidateEdge,
    CandidateEvidence,
    CandidateGenerationResult,
    CandidateLimitReason,
    CandidatePartitionEvidence,
    CapacityLimits,
    DomainValidationError,
    FeatureEvidence,
    MatchFeature,
    MatchingPolicy,
    solve_assignment,
)
from reconciliation.solvers import ScipyAssignmentSolver


def candidate(
    left_id: str,
    right_id: str,
    score_bp: int,
    *,
    complete: bool = True,
) -> CandidateEvidence:
    weights = {
        MatchFeature.QUANTITY: 3_500,
        MatchFeature.TIMESTAMP: 2_500,
        MatchFeature.UNIT_PRICE: 1_500,
        MatchFeature.GROSS_AMOUNT: 2_500,
    }
    remaining = score_bp
    features = []
    for name, weight in weights.items():
        contribution = min(weight, remaining)
        remaining -= contribution
        if name is MatchFeature.TIMESTAMP:
            left_value = right_value = datetime(2026, 9, 7, tzinfo=UTC)
            difference = timedelta(0)
            band = timedelta(minutes=10)
        else:
            left_value = right_value = Decimal("1")
            difference = Decimal("0")
            band = Decimal("1")
        features.append(
            FeatureEvidence(
                feature=name,
                left_value=left_value,
                right_value=right_value,
                difference=difference,
                band=band,
                present=True,
                similarity_bp=10_000 if contribution == weight else 0,
                weight_bp=weight,
                contribution_bp=contribution,
                rule="Synthetic assignment fixture with a fixed contribution.",
            )
        )
    assert remaining == 0
    return CandidateEvidence(
        left_id=left_id,
        right_id=right_id,
        blocking_reasons=("assignment-fixture@1",),
        features=tuple(features),
        contradictions=(),
        coverage_failures=(),
        coverage_sufficient=True,
        complete_computation=complete,
        score_bp=score_bp,
    )


def generation(
    candidates: tuple[CandidateEvidence, ...],
    *,
    limited_ids: tuple[str, ...] = (),
) -> CandidateGenerationResult:
    raw = tuple(
        CandidateEdge(item.left_id, item.right_id, item.blocking_reasons)
        for item in candidates
    )
    if limited_ids:
        left_ids = tuple(sorted(value for value in limited_ids if value.startswith("L")))
        right_ids = tuple(sorted(value for value in limited_ids if value.startswith("R")))
        partitions = (
            CandidatePartitionEvidence(
                "partition-limited",
                "assignment-fixture@1",
                left_ids,
                right_ids,
                len(raw),
                False,
                CandidateLimitReason.PER_RECORD_LIMIT,
            ),
        )
    else:
        partitions = ()
    return CandidateGenerationResult(raw, partitions, limited_ids, not limited_ids)


def solve(
    candidates: tuple[CandidateEvidence, ...],
    *,
    policy: MatchingPolicy | None = None,
    limited_ids: tuple[str, ...] = (),
):
    selected_policy = policy or MatchingPolicy.initial_demo()
    return solve_assignment(
        candidates=candidates,
        generated=generation(candidates, limited_ids=limited_ids),
        policy=selected_policy,
        solver=ScipyAssignmentSolver(),
    )


def selected_pairs(result) -> set[tuple[str, str]]:
    return {(item.left_id, item.right_id) for item in result.selected_edges}


def test_global_assignment_beats_greedy_counterexample() -> None:
    result = solve(
        (
            candidate("L1", "R1", 9_400),
            candidate("L1", "R2", 9_200),
            candidate("L2", "R1", 9_300),
            candidate("L2", "R2", 2_000),
        )
    )

    assert selected_pairs(result) == {("L1", "R2"), ("L2", "R1")}
    assert result.components[0].optimal_utility_bp == 4_500


def test_edges_at_or_below_floor_select_unmatched_options() -> None:
    result = solve(
        (
            candidate("L1", "R1", 7_000),
            candidate("L2", "R2", 6_999),
        )
    )

    assert result.selected_edges == ()
    assert result.components == ()


def test_rectangular_problem_allows_unmatched_records_on_either_side() -> None:
    result = solve(
        (
            candidate("L1", "R1", 9_500),
            candidate("L1", "R2", 8_000),
            candidate("L2", "R1", 8_100),
            candidate("L2", "R3", 9_600),
        )
    )

    assert selected_pairs(result) == {("L1", "R1"), ("L2", "R3")}
    assert result.components[0].right_ids == ("R1", "R2", "R3")


class CapturingSolver:
    version = MatchingPolicy.initial_demo().solver_version

    def __init__(self) -> None:
        self.costs = ()

    def minimize(self, costs):
        self.costs = tuple(tuple(row) for row in costs)
        return ScipyAssignmentSolver().minimize(costs)


def test_sparse_component_uses_positive_forbidden_cells_and_zero_dummy_columns() -> None:
    edges = (
        candidate("L1", "R1", 9_500),
        candidate("L1", "R2", 9_200),
        candidate("L2", "R2", 9_600),
    )
    solver = CapturingSolver()
    result = solve_assignment(
        candidates=edges,
        generated=generation(edges),
        policy=MatchingPolicy.initial_demo(),
        solver=solver,
    )

    assert selected_pairs(result) == {("L1", "R1"), ("L2", "R2")}
    assert len(result.components) == 1
    assert solver.costs == (
        (-2_500, -2_200, 0, 0),
        (20_003, -2_600, 0, 0),
    )


def test_more_left_records_than_right_records_uses_a_dummy_unmatched_choice() -> None:
    result = solve(
        (
            candidate("L1", "R1", 9_500),
            candidate("L2", "R1", 9_000),
        )
    )

    assert selected_pairs(result) == {("L1", "R1")}
    assert result.components[0].left_ids == ("L1", "L2")
    assert result.components[0].optimal_utility_bp == 2_500


def test_disconnected_candidate_graph_solves_independent_components() -> None:
    result = solve(
        (
            candidate("L1", "R1", 9_100),
            candidate("L2", "R2", 9_200),
            candidate("L3", "R3", 9_300),
        )
    )

    assert len(result.components) == 3
    assert selected_pairs(result) == {("L1", "R1"), ("L2", "R2"), ("L3", "R3")}


class NeverCalledSolver:
    version = MatchingPolicy.initial_demo().solver_version

    def minimize(self, costs):
        raise AssertionError("limited component must not reach the solver")


@pytest.mark.parametrize(
    ("limits", "reason"),
    [
        (CapacityLimits(3, 10, 250_000, 200), AssignmentLimitReason.COMPONENT_NODE_LIMIT),
        (CapacityLimits(100, 2, 250_000, 200), AssignmentLimitReason.COMPONENT_EDGE_LIMIT),
    ],
)
def test_component_limit_excess_abstains_without_invoking_solver(
    limits: CapacityLimits,
    reason: AssignmentLimitReason,
) -> None:
    edges = (
        candidate("L1", "R1", 9_000),
        candidate("L1", "R2", 9_100),
        candidate("L2", "R1", 9_200),
    )
    policy = replace(MatchingPolicy.initial_demo(), limits=limits)
    result = solve_assignment(
        candidates=edges,
        generated=generation(edges),
        policy=policy,
        solver=NeverCalledSolver(),
    )

    assert result.selected_edges == ()
    assert result.components[0].complete is False
    assert result.components[0].limit_reason is reason
    assert set(result.limited_record_ids) == {"L1", "L2", "R1", "R2"}


def test_exact_component_node_and_edge_limits_are_solved() -> None:
    edges = (
        candidate("L1", "R1", 9_000),
        candidate("L1", "R2", 9_100),
        candidate("L2", "R1", 9_200),
    )
    policy = replace(
        MatchingPolicy.initial_demo(),
        limits=CapacityLimits(4, 3, 250_000, 200),
    )
    result = solve(edges, policy=policy)

    assert result.components[0].complete is True
    assert result.components[0].candidate_count == 3
    assert result.selected_edges


def test_incomplete_candidate_partition_abstains_before_solver() -> None:
    edges = (
        candidate("L1", "R1", 9_500, complete=False),
        candidate("L1", "R2", 9_400, complete=False),
    )
    policy = MatchingPolicy.initial_demo()
    result = solve_assignment(
        candidates=edges,
        generated=generation(edges, limited_ids=("L1", "R1", "R2")),
        policy=policy,
        solver=NeverCalledSolver(),
    )

    assert result.selected_edges == ()
    assert result.components[0].limit_reason is AssignmentLimitReason.INCOMPLETE_CANDIDATE_GRAPH


def test_generated_limit_without_above_floor_edge_is_still_propagated() -> None:
    edges = (candidate("L1", "R1", 6_000, complete=False),)
    result = solve(edges, limited_ids=("L1", "R1"))

    assert result.components == ()
    assert result.limited_record_ids == ("L1", "R1")


def test_solver_version_is_frozen_by_matching_policy() -> None:
    policy = replace(MatchingPolicy.initial_demo(), solver_version="different-solver")

    with pytest.raises(DomainValidationError, match="version"):
        solve((candidate("L1", "R1", 9_000),), policy=policy)


class BrokenSolver:
    version = MatchingPolicy.initial_demo().solver_version

    def minimize(self, costs):
        return ((0, 0), (0, 1))


def test_malformed_solver_output_is_rejected() -> None:
    edges = (
        candidate("L1", "R1", 9_500),
        candidate("L2", "R2", 9_500),
        candidate("L1", "R2", 9_100),
    )

    with pytest.raises(DomainValidationError, match="duplicate or missing"):
        solve_assignment(
            candidates=edges,
            generated=generation(edges),
            policy=MatchingPolicy.initial_demo(),
            solver=BrokenSolver(),
        )


@pytest.mark.parametrize("matrix", [((1, 2), (3,)), ((True, 1),)])
def test_scipy_adapter_rejects_ragged_or_noninteger_costs(matrix) -> None:
    with pytest.raises(DomainValidationError):
        ScipyAssignmentSolver().minimize(matrix)


def test_assignment_is_identical_under_candidate_reordering() -> None:
    edges = (
        candidate("L2", "R1", 9_300),
        candidate("L1", "R2", 9_200),
        candidate("L1", "R1", 9_400),
    )

    assert solve(edges) == solve(tuple(reversed(edges)))


def _brute_force_objective(
    edges: tuple[CandidateEvidence, ...], floor: int
) -> int:
    by_left: dict[str, list[CandidateEvidence]] = {}
    for edge in edges:
        if edge.score_bp > floor:
            by_left.setdefault(edge.left_id, []).append(edge)
    left_ids = sorted(by_left)

    def visit(index: int, used_right: frozenset[str]) -> int:
        if index == len(left_ids):
            return 0
        best = visit(index + 1, used_right)
        for edge in by_left[left_ids[index]]:
            if edge.right_id not in used_right:
                best = max(
                    best,
                    edge.score_bp - floor + visit(index + 1, used_right | {edge.right_id}),
                )
        return best

    return visit(0, frozenset())


def test_scipy_solver_objective_matches_exhaustive_oracle_on_generated_small_graphs() -> None:
    randomizer = random.Random(20260907)
    policy = MatchingPolicy.initial_demo()
    checked = 0
    for left_count in range(1, 5):
        for right_count in range(1, 5):
            for _ in range(15):
                edges = tuple(
                    candidate(f"L{left}", f"R{right}", randomizer.randint(6_500, 10_000))
                    for left in range(left_count)
                    for right in range(right_count)
                    if randomizer.random() < 0.7
                )
                if not edges:
                    continue
                result = solve(edges, policy=policy)
                actual = sum(item.optimal_utility_bp for item in result.components)
                assert actual == _brute_force_objective(edges, policy.assignment_floor_bp)
                checked += 1
    assert checked >= 200
