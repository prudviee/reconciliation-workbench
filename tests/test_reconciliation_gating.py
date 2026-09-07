from __future__ import annotations

import random
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from reconciliation.domain import (
    AssignmentComponentEvidence,
    CandidateEdge,
    CandidateEvidence,
    CandidateGenerationResult,
    CapacityLimits,
    DomainValidationError,
    FeatureEvidence,
    MatchFeature,
    MatchingPolicy,
    ProposalEvidence,
    ProposalGateReason,
    gate_assignment,
    solve_assignment,
)
from reconciliation.solvers import ScipyAssignmentSolver


def candidate(
    left_id: str,
    right_id: str,
    score_bp: int,
    *,
    coverage_sufficient: bool = True,
    contradictions: tuple[str, ...] = (),
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
                rule="Synthetic gating fixture with a fixed contribution.",
            )
        )
    assert remaining == 0
    return CandidateEvidence(
        left_id=left_id,
        right_id=right_id,
        blocking_reasons=("gating-fixture@1",),
        features=tuple(features),
        contradictions=contradictions,
        coverage_failures=() if coverage_sufficient else ("MISSING_QUANTITY",),
        coverage_sufficient=coverage_sufficient,
        complete_computation=complete,
        score_bp=score_bp,
    )


def generation(candidates: tuple[CandidateEvidence, ...]) -> CandidateGenerationResult:
    return CandidateGenerationResult(
        candidates=tuple(
            CandidateEdge(item.left_id, item.right_id, item.blocking_reasons)
            for item in candidates
        ),
        partitions=(),
        limited_record_ids=(),
        complete=True,
    )


def assign(
    candidates: tuple[CandidateEvidence, ...],
    *,
    policy: MatchingPolicy | None = None,
):
    selected_policy = policy or MatchingPolicy.initial_demo()
    return solve_assignment(
        candidates=candidates,
        generated=generation(candidates),
        policy=selected_policy,
        solver=ScipyAssignmentSolver(),
    )


def gate(
    candidates: tuple[CandidateEvidence, ...],
    *,
    policy: MatchingPolicy | None = None,
    solver=None,
):
    selected_policy = policy or MatchingPolicy.initial_demo()
    return gate_assignment(
        candidates=candidates,
        assignment=assign(candidates, policy=selected_policy),
        policy=selected_policy,
        solver=solver or ScipyAssignmentSolver(),
    )


def proposal_pairs(values) -> set[tuple[str, str]]:
    return {(item.left_id, item.right_id) for item in values}


def test_greedy_counterexample_has_large_counterfactual_gaps_and_is_accepted() -> None:
    edges = (
        candidate("L1", "R1", 9_400),
        candidate("L1", "R2", 9_200),
        candidate("L2", "R1", 9_300),
        candidate("L2", "R2", 2_000),
    )

    result = gate(edges)

    assert proposal_pairs(result.accepted_proposals) == {("L1", "R2"), ("L2", "R1")}
    assert {item.global_gap_bp for item in result.proposals} == {2_100}
    assert {item.counterfactual_objective_bp for item in result.proposals} == {2_400}


def test_four_equal_scores_have_zero_gap_and_abstain() -> None:
    edges = tuple(
        candidate(left_id, right_id, 9_400)
        for left_id in ("L1", "L2")
        for right_id in ("R1", "R2")
    )

    result = gate(edges)

    assert len(result.proposals) == 2
    assert result.accepted_proposals == ()
    assert {item.global_gap_bp for item in result.proposals} == {0}
    assert {
        item.gate_reasons for item in result.proposals
    } == {(ProposalGateReason.GLOBAL_GAP_BELOW_MINIMUM.value,)}


def test_score_and_global_gap_boundaries_are_inclusive() -> None:
    result = gate(
        (
            candidate("L1", "R1", 9_000),
            candidate("L1", "R2", 8_200),
        )
    )

    assert len(result.accepted_proposals) == 1
    assert result.accepted_proposals[0].score_bp == 9_000
    assert result.accepted_proposals[0].global_gap_bp == 800
    assert result.accepted_proposals[0].gate_reasons == ()


@pytest.mark.parametrize(
    ("edges", "reason"),
    [
        (
            (candidate("L1", "R1", 8_999),),
            ProposalGateReason.SCORE_BELOW_AUTOMATIC_THRESHOLD,
        ),
        (
            (candidate("L1", "R1", 9_000), candidate("L1", "R2", 8_201)),
            ProposalGateReason.GLOBAL_GAP_BELOW_MINIMUM,
        ),
    ],
)
def test_values_immediately_below_gate_boundaries_are_rejected(edges, reason) -> None:
    result = gate(edges)

    assert result.accepted_proposals == ()
    assert reason.value in result.proposals[0].gate_reasons


def test_evidence_and_contradiction_gates_report_all_factual_failures() -> None:
    result = gate(
        (
            candidate(
                "L1",
                "R1",
                9_500,
                coverage_sufficient=False,
                contradictions=("CURRENCY_MISMATCH",),
            ),
        )
    )

    assert result.accepted_proposals == ()
    assert result.proposals[0].gate_reasons == (
        ProposalGateReason.HARD_CONTRADICTION.value,
        ProposalGateReason.INSUFFICIENT_EVIDENCE.value,
    )


class CountingSolver:
    version = MatchingPolicy.initial_demo().solver_version

    def __init__(self) -> None:
        self.call_count = 0

    def minimize(self, costs):
        self.call_count += 1
        return ScipyAssignmentSolver().minimize(costs)


def test_rejected_strong_proposal_does_not_promote_weaker_alternative() -> None:
    edges = (
        candidate("L1", "R1", 9_500, coverage_sufficient=False),
        candidate("L1", "R2", 9_400),
    )
    solver = CountingSolver()

    result = gate(edges, solver=solver)

    assert proposal_pairs(result.proposals) == {("L1", "R1")}
    assert result.accepted_proposals == ()
    assert solver.call_count == 1


def test_single_pass_retains_only_accepted_subset_without_reassignment() -> None:
    edges = (
        candidate("L1", "R1", 9_500, coverage_sufficient=False),
        candidate("L1", "R2", 7_100),
        candidate("L2", "R1", 7_100),
        candidate("L2", "R2", 9_600),
    )
    solver = CountingSolver()

    result = gate(edges, solver=solver)

    assert proposal_pairs(result.proposals) == {("L1", "R1"), ("L2", "R2")}
    assert proposal_pairs(result.accepted_proposals) == {("L2", "R2")}
    assert solver.call_count == 2


class NeverCalledSolver:
    version = MatchingPolicy.initial_demo().solver_version

    def minimize(self, costs):
        raise AssertionError("incomplete components must not run counterfactual solves")


def test_over_limit_component_abstains_without_counterfactual_solver() -> None:
    edges = (
        candidate("L1", "R1", 9_500),
        candidate("L1", "R2", 9_400),
        candidate("L2", "R1", 9_300),
    )
    policy = replace(
        MatchingPolicy.initial_demo(),
        limits=CapacityLimits(3, 10, 250_000, 200),
    )
    assignment = assign(edges, policy=policy)

    result = gate_assignment(
        candidates=edges,
        assignment=assignment,
        policy=policy,
        solver=NeverCalledSolver(),
    )

    assert result.proposals == ()
    assert result.accepted_proposals == ()
    assert result.components[0].complete is False
    assert result.components[0].limit_reason == "COMPONENT_NODE_LIMIT"


def _brute_force_objective(
    edges: tuple[CandidateEvidence, ...],
    floor: int,
    *,
    forbidden: tuple[str, str] | None = None,
) -> int:
    by_left: dict[str, list[CandidateEvidence]] = {}
    for edge in edges:
        if edge.score_bp > floor and (edge.left_id, edge.right_id) != forbidden:
            by_left.setdefault(edge.left_id, []).append(edge)
    left_ids = sorted({item.left_id for item in edges})

    def visit(index: int, used_right: frozenset[str]) -> int:
        if index == len(left_ids):
            return 0
        best = visit(index + 1, used_right)
        for edge in by_left.get(left_ids[index], []):
            if edge.right_id not in used_right:
                best = max(
                    best,
                    edge.score_bp
                    - floor
                    + visit(index + 1, used_right | {edge.right_id}),
                )
        return best

    return visit(0, frozenset())


def test_counterfactual_gaps_match_exhaustive_oracle_on_generated_small_graphs() -> None:
    randomizer = random.Random(20260907)
    policy = MatchingPolicy.initial_demo()
    checked = 0
    for left_count in range(1, 5):
        for right_count in range(1, 5):
            for _ in range(10):
                edges = tuple(
                    candidate(f"L{left}", f"R{right}", randomizer.randint(7_001, 10_000))
                    for left in range(left_count)
                    for right in range(right_count)
                    if randomizer.random() < 0.72
                )
                if not edges:
                    continue
                result = gate(edges, policy=policy)
                for component in result.components:
                    component_edges = tuple(
                        edge
                        for edge in edges
                        if edge.left_id in component.left_ids
                        and edge.right_id in component.right_ids
                    )
                    base = _brute_force_objective(
                        component_edges, policy.assignment_floor_bp
                    )
                    assert component.optimal_utility_bp == base
                    for proposal in component.proposals:
                        forbidden = (proposal.left_id, proposal.right_id)
                        counterfactual = _brute_force_objective(
                            component_edges,
                            policy.assignment_floor_bp,
                            forbidden=forbidden,
                        )
                        assert proposal.counterfactual_objective_bp == counterfactual
                        assert proposal.global_gap_bp == base - counterfactual
                        checked += 1
    assert checked >= 100


def test_gating_is_identical_under_candidate_reordering() -> None:
    edges = (
        candidate("L1", "R1", 9_500),
        candidate("L1", "R2", 8_100),
        candidate("L2", "R1", 8_200),
        candidate("L2", "R2", 9_600),
    )

    assert gate(edges) == gate(tuple(reversed(edges)))


def test_component_contract_rejects_inconsistent_counterfactual_gap() -> None:
    proposal = ProposalEvidence("L1", "R1", 9_000, 1_100, 801, True, ())

    with pytest.raises(DomainValidationError, match="gaps"):
        AssignmentComponentEvidence(
            "component-1",
            "digest",
            MatchingPolicy.initial_demo().solver_version,
            ("L1",),
            ("R1",),
            1,
            1_900,
            True,
            None,
            (proposal,),
        )


def test_counterfactual_solver_version_is_frozen_by_policy() -> None:
    edges = (candidate("L1", "R1", 9_500),)
    policy = MatchingPolicy.initial_demo()
    mismatched = replace(policy, solver_version="another-solver")

    with pytest.raises(DomainValidationError, match="version"):
        gate_assignment(
            candidates=edges,
            assignment=assign(edges, policy=policy),
            policy=mismatched,
            solver=ScipyAssignmentSolver(),
        )
