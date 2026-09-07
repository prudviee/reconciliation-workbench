"""Single-pass automatic-acceptance gates for assignment proposals."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .assignment import (
    AssignmentSolveResult,
    AssignmentSolver,
    assignment_graph_digest,
    solve_component,
)
from .reconciliation import (
    AssignmentComponentEvidence,
    CandidateEvidence,
    MatchingPolicy,
    ProposalEvidence,
)
from .workspaces import DomainValidationError


class ProposalGateReason(StrEnum):
    """Stable factual reasons why an assignment proposal was withheld."""

    SCORE_BELOW_AUTOMATIC_THRESHOLD = "SCORE_BELOW_AUTOMATIC_THRESHOLD"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    HARD_CONTRADICTION = "HARD_CONTRADICTION"
    INCOMPLETE_COMPUTATION = "INCOMPLETE_COMPUTATION"
    GLOBAL_GAP_BELOW_MINIMUM = "GLOBAL_GAP_BELOW_MINIMUM"


@dataclass(frozen=True, slots=True)
class GatedAssignmentResult:
    """Auditable component evidence and its immutable accepted subset."""

    components: tuple[AssignmentComponentEvidence, ...]
    proposals: tuple[ProposalEvidence, ...]
    accepted_proposals: tuple[ProposalEvidence, ...]

    def __post_init__(self) -> None:
        components = tuple(sorted(self.components, key=lambda item: item.component_id))
        proposals = tuple(sorted(self.proposals, key=lambda item: (item.left_id, item.right_id)))
        accepted = tuple(
            sorted(self.accepted_proposals, key=lambda item: (item.left_id, item.right_id))
        )
        component_ids = [item.component_id for item in components]
        if len(component_ids) != len(set(component_ids)):
            raise DomainValidationError("gated assignment component identities must be unique")
        component_proposals = tuple(
            proposal for component in components for proposal in component.proposals
        )
        if proposals != tuple(
            sorted(component_proposals, key=lambda item: (item.left_id, item.right_id))
        ):
            raise DomainValidationError(
                "gated proposals must exactly equal the component proposal evidence"
            )
        expected_accepted = tuple(item for item in proposals if item.accepted)
        if accepted != expected_accepted:
            raise DomainValidationError(
                "accepted proposals must exactly equal the accepted flagged subset"
            )
        left_ids = [item.left_id for item in accepted]
        right_ids = [item.right_id for item in accepted]
        if len(left_ids) != len(set(left_ids)) or len(right_ids) != len(set(right_ids)):
            raise DomainValidationError("accepted proposals must be one-to-one")
        object.__setattr__(self, "components", components)
        object.__setattr__(self, "proposals", proposals)
        object.__setattr__(self, "accepted_proposals", accepted)


def gate_assignment(
    *,
    candidates: tuple[CandidateEvidence, ...],
    assignment: AssignmentSolveResult,
    policy: MatchingPolicy,
    solver: AssignmentSolver,
) -> GatedAssignmentResult:
    """Evaluate every base proposal once without mutating or re-solving the accepted subset."""

    if solver.version != policy.solver_version:
        raise DomainValidationError("counterfactual solver version must match the matching policy")
    candidate_by_edge = {(item.left_id, item.right_id): item for item in candidates}
    if len(candidate_by_edge) != len(candidates):
        raise DomainValidationError("counterfactual candidates must be unique")
    eligible_edges = {
        edge for edge, item in candidate_by_edge.items()
        if item.score_bp > policy.assignment_floor_bp
    }

    components: list[AssignmentComponentEvidence] = []
    assigned_component_edges: set[tuple[str, str]] = set()
    for component in assignment.components:
        if component.solver_version != policy.solver_version:
            raise DomainValidationError(
                "assignment component solver version must match the matching policy"
            )
        component_candidates = tuple(
            sorted(
                (
                    item
                    for item in candidates
                    if item.left_id in component.left_ids
                    and item.right_id in component.right_ids
                    and item.score_bp > policy.assignment_floor_bp
                ),
                key=lambda item: (item.left_id, item.right_id),
            )
        )
        if len(component_candidates) != component.candidate_count:
            raise DomainValidationError(
                "assignment component candidate count must match the eligible candidate graph"
            )
        component_edges = {
            (item.left_id, item.right_id) for item in component_candidates
        }
        if assigned_component_edges.intersection(component_edges):
            raise DomainValidationError("eligible candidate edges cannot span assignment components")
        assigned_component_edges.update(component_edges)
        expected_digest = assignment_graph_digest(
            component_id=component.component_id,
            assignment_floor_bp=policy.assignment_floor_bp,
            edges=component_candidates,
        )
        if component.graph_digest != expected_digest:
            raise DomainValidationError(
                "assignment component graph digest must match the eligible candidate graph"
            )

        proposals: list[ProposalEvidence] = []
        if component.complete:
            for selected in component.selected_edges:
                edge_key = (selected.left_id, selected.right_id)
                candidate = candidate_by_edge.get(edge_key)
                if candidate is None:
                    raise DomainValidationError(
                        "assignment proposal must reference a scored candidate"
                    )
                if (
                    selected.score_bp != candidate.score_bp
                    or selected.utility_bp
                    != candidate.score_bp - policy.assignment_floor_bp
                ):
                    raise DomainValidationError(
                        "assignment proposal score and utility must match its candidate evidence"
                    )
                counterfactual = solve_component(
                    left_ids=component.left_ids,
                    right_ids=component.right_ids,
                    candidates=component_candidates,
                    assignment_floor_bp=policy.assignment_floor_bp,
                    solver=solver,
                    forbidden_edges=frozenset({edge_key}),
                )
                counterfactual_objective = sum(item.utility_bp for item in counterfactual)
                global_gap = component.optimal_utility_bp - counterfactual_objective
                if global_gap < 0:
                    raise DomainValidationError(
                        "counterfactual objective cannot exceed the base optimal objective"
                    )
                reasons = _gate_reasons(
                    candidate=candidate,
                    global_gap_bp=global_gap,
                    policy=policy,
                )
                proposals.append(
                    ProposalEvidence(
                        left_id=selected.left_id,
                        right_id=selected.right_id,
                        score_bp=selected.score_bp,
                        counterfactual_objective_bp=counterfactual_objective,
                        global_gap_bp=global_gap,
                        accepted=not reasons,
                        gate_reasons=tuple(reason.value for reason in reasons),
                    )
                )

        components.append(
            AssignmentComponentEvidence(
                component_id=component.component_id,
                graph_digest=component.graph_digest,
                solver_version=component.solver_version,
                left_ids=component.left_ids,
                right_ids=component.right_ids,
                candidate_count=component.candidate_count,
                optimal_utility_bp=component.optimal_utility_bp,
                complete=component.complete,
                limit_reason=(
                    None if component.limit_reason is None else component.limit_reason.value
                ),
                proposals=tuple(proposals),
            )
        )

    if assigned_component_edges != eligible_edges:
        raise DomainValidationError(
            "assignment components must exactly partition the eligible candidate graph"
        )
    all_proposals = tuple(proposal for component in components for proposal in component.proposals)
    return GatedAssignmentResult(
        components=tuple(components),
        proposals=all_proposals,
        accepted_proposals=tuple(item for item in all_proposals if item.accepted),
    )


def _gate_reasons(
    *,
    candidate: CandidateEvidence,
    global_gap_bp: int,
    policy: MatchingPolicy,
) -> tuple[ProposalGateReason, ...]:
    reasons: list[ProposalGateReason] = []
    if candidate.score_bp < policy.automatic_threshold_bp:
        reasons.append(ProposalGateReason.SCORE_BELOW_AUTOMATIC_THRESHOLD)
    if not candidate.coverage_sufficient:
        reasons.append(ProposalGateReason.INSUFFICIENT_EVIDENCE)
    if candidate.contradictions:
        reasons.append(ProposalGateReason.HARD_CONTRADICTION)
    if not candidate.complete_computation:
        reasons.append(ProposalGateReason.INCOMPLETE_COMPUTATION)
    if global_gap_bp < policy.minimum_global_gap_bp:
        reasons.append(ProposalGateReason.GLOBAL_GAP_BELOW_MINIMUM)
    return tuple(reasons)
