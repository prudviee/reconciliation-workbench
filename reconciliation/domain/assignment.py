"""Connected components and optional-unmatched global assignment."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict, deque
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, Sequence

from .candidates import CandidateGenerationResult
from .reconciliation import CandidateEvidence, MatchingPolicy
from .workspaces import DomainValidationError


class AssignmentLimitReason(StrEnum):
    INCOMPLETE_CANDIDATE_GRAPH = "INCOMPLETE_CANDIDATE_GRAPH"
    COMPONENT_NODE_LIMIT = "COMPONENT_NODE_LIMIT"
    COMPONENT_EDGE_LIMIT = "COMPONENT_EDGE_LIMIT"


class AssignmentSolver(Protocol):
    @property
    def version(self) -> str: ...

    def minimize(
        self, costs: Sequence[Sequence[int]]
    ) -> tuple[tuple[int, int], ...]: ...


@dataclass(frozen=True, slots=True)
class SelectedAssignmentEdge:
    left_id: str
    right_id: str
    score_bp: int
    utility_bp: int

    def __post_init__(self) -> None:
        for name in ("left_id", "right_id"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise DomainValidationError(f"selected assignment {name} must be nonblank text")
        for name in ("score_bp", "utility_bp"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise DomainValidationError(f"selected assignment {name} must be a positive integer")
        if self.score_bp > 10_000 or self.utility_bp > self.score_bp:
            raise DomainValidationError("selected assignment score or utility is outside its integer scale")


@dataclass(frozen=True, slots=True)
class SolvedAssignmentComponent:
    component_id: str
    graph_digest: str
    solver_version: str
    left_ids: tuple[str, ...]
    right_ids: tuple[str, ...]
    candidate_count: int
    optimal_utility_bp: int
    complete: bool
    limit_reason: AssignmentLimitReason | None
    selected_edges: tuple[SelectedAssignmentEdge, ...]

    def __post_init__(self) -> None:
        for name in ("component_id", "graph_digest", "solver_version"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise DomainValidationError(f"assignment component {name} must be nonblank text")
        left_ids = tuple(sorted(self.left_ids))
        right_ids = tuple(sorted(self.right_ids))
        if not left_ids or not right_ids:
            raise DomainValidationError("assignment component requires records on both sides")
        if len(left_ids) != len(set(left_ids)) or len(right_ids) != len(set(right_ids)):
            raise DomainValidationError("assignment component identities must be unique")
        if (
            isinstance(self.candidate_count, bool)
            or not isinstance(self.candidate_count, int)
            or self.candidate_count <= 0
        ):
            raise DomainValidationError("assignment candidate_count must be positive")
        if (
            isinstance(self.optimal_utility_bp, bool)
            or not isinstance(self.optimal_utility_bp, int)
            or self.optimal_utility_bp < 0
        ):
            raise DomainValidationError("optimal_utility_bp must be a nonnegative integer")
        if not isinstance(self.complete, bool):
            raise DomainValidationError("assignment component complete must be boolean")
        if self.complete and self.limit_reason is not None:
            raise DomainValidationError("a complete assignment component cannot have a limit reason")
        if not self.complete and not isinstance(self.limit_reason, AssignmentLimitReason):
            raise DomainValidationError("an incomplete assignment component requires a limit reason")
        selected = tuple(sorted(self.selected_edges, key=lambda item: (item.left_id, item.right_id)))
        selected_left = [item.left_id for item in selected]
        selected_right = [item.right_id for item in selected]
        if len(selected_left) != len(set(selected_left)) or len(selected_right) != len(set(selected_right)):
            raise DomainValidationError("selected assignment edges must be one-to-one")
        if not set(selected_left).issubset(left_ids) or not set(selected_right).issubset(right_ids):
            raise DomainValidationError("selected assignment edge must belong to its component")
        if not self.complete and selected:
            raise DomainValidationError("an incomplete assignment component cannot select edges")
        if self.optimal_utility_bp != sum(item.utility_bp for item in selected):
            raise DomainValidationError("component objective must equal selected edge utilities")
        object.__setattr__(self, "left_ids", left_ids)
        object.__setattr__(self, "right_ids", right_ids)
        object.__setattr__(self, "selected_edges", selected)


@dataclass(frozen=True, slots=True)
class AssignmentSolveResult:
    components: tuple[SolvedAssignmentComponent, ...]
    selected_edges: tuple[SelectedAssignmentEdge, ...]
    source_limited_record_ids: tuple[str, ...]
    limited_record_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        components = tuple(sorted(self.components, key=lambda item: item.component_id))
        selected = tuple(sorted(self.selected_edges, key=lambda item: (item.left_id, item.right_id)))
        source_limited = tuple(sorted(self.source_limited_record_ids))
        limited = tuple(sorted(self.limited_record_ids))
        component_ids = [item.component_id for item in components]
        if len(component_ids) != len(set(component_ids)):
            raise DomainValidationError("assignment component identities must be unique")
        component_selected = tuple(edge for component in components for edge in component.selected_edges)
        if selected != tuple(sorted(component_selected, key=lambda item: (item.left_id, item.right_id))):
            raise DomainValidationError("assignment selected edges must equal component selections")
        selected_left = [item.left_id for item in selected]
        selected_right = [item.right_id for item in selected]
        if len(selected_left) != len(set(selected_left)) or len(selected_right) != len(set(selected_right)):
            raise DomainValidationError("assignment result selections must be globally one-to-one")
        if len(source_limited) != len(set(source_limited)):
            raise DomainValidationError("source limited record identities must be unique")
        expected_limited = set(source_limited) | {
            identity
            for component in components
            if not component.complete
            for identity in (*component.left_ids, *component.right_ids)
        }
        if set(limited) != expected_limited:
            raise DomainValidationError(
                "assignment limited identities must equal source and incomplete component members"
            )
        object.__setattr__(self, "components", components)
        object.__setattr__(self, "selected_edges", selected)
        object.__setattr__(self, "source_limited_record_ids", source_limited)
        object.__setattr__(self, "limited_record_ids", limited)


def solve_assignment(
    *,
    candidates: tuple[CandidateEvidence, ...],
    generated: CandidateGenerationResult,
    policy: MatchingPolicy,
    solver: AssignmentSolver,
) -> AssignmentSolveResult:
    """Solve complete above-floor components with explicit unmatched choices."""

    if solver.version != policy.solver_version:
        raise DomainValidationError("assignment solver version must match the matching policy")
    candidate_keys = [(item.left_id, item.right_id) for item in candidates]
    if len(candidate_keys) != len(set(candidate_keys)):
        raise DomainValidationError("scored assignment candidates must be unique")
    generated_keys = {(item.left_id, item.right_id) for item in generated.candidates}
    if set(candidate_keys) != generated_keys:
        raise DomainValidationError("scored candidates must exactly cover generated candidate edges")

    eligible = tuple(
        sorted(
            (item for item in candidates if item.score_bp > policy.assignment_floor_bp),
            key=lambda item: (item.left_id, item.right_id),
        )
    )
    components: list[SolvedAssignmentComponent] = []
    limited_ids = set(generated.limited_record_ids)
    for component_edges in _connected_components(eligible):
        left_ids = tuple(sorted({item.left_id for item in component_edges}))
        right_ids = tuple(sorted({item.right_id for item in component_edges}))
        component_id = _component_id(left_ids, right_ids)
        graph_digest = _graph_digest(
            component_id=component_id,
            assignment_floor_bp=policy.assignment_floor_bp,
            edges=component_edges,
        )
        limit_reason: AssignmentLimitReason | None = None
        if limited_ids.intersection((*left_ids, *right_ids)) or any(
            not item.complete_computation for item in component_edges
        ):
            limit_reason = AssignmentLimitReason.INCOMPLETE_CANDIDATE_GRAPH
        elif len(left_ids) + len(right_ids) > policy.limits.max_component_nodes:
            limit_reason = AssignmentLimitReason.COMPONENT_NODE_LIMIT
        elif len(component_edges) > policy.limits.max_component_edges:
            limit_reason = AssignmentLimitReason.COMPONENT_EDGE_LIMIT

        if limit_reason is not None:
            components.append(
                SolvedAssignmentComponent(
                    component_id,
                    graph_digest,
                    solver.version,
                    left_ids,
                    right_ids,
                    len(component_edges),
                    0,
                    False,
                    limit_reason,
                    (),
                )
            )
            continue

        selected = _solve_component(
            left_ids=left_ids,
            right_ids=right_ids,
            candidates=component_edges,
            assignment_floor_bp=policy.assignment_floor_bp,
            solver=solver,
        )
        components.append(
            SolvedAssignmentComponent(
                component_id,
                graph_digest,
                solver.version,
                left_ids,
                right_ids,
                len(component_edges),
                sum(item.utility_bp for item in selected),
                True,
                None,
                selected,
            )
        )

    selected_edges = tuple(edge for component in components for edge in component.selected_edges)
    component_limited = set(generated.limited_record_ids) | {
        identity
        for component in components
        if not component.complete
        for identity in (*component.left_ids, *component.right_ids)
    }
    return AssignmentSolveResult(
        tuple(components),
        selected_edges,
        generated.limited_record_ids,
        tuple(component_limited),
    )


def _connected_components(
    candidates: tuple[CandidateEvidence, ...],
) -> tuple[tuple[CandidateEvidence, ...], ...]:
    by_node: defaultdict[tuple[str, str], list[int]] = defaultdict(list)
    for index, candidate in enumerate(candidates):
        by_node[("L", candidate.left_id)].append(index)
        by_node[("R", candidate.right_id)].append(index)
    unvisited = set(range(len(candidates)))
    components: list[tuple[CandidateEvidence, ...]] = []
    while unvisited:
        start = min(
            unvisited,
            key=lambda index: (candidates[index].left_id, candidates[index].right_id),
        )
        queue = deque([start])
        indices: set[int] = set()
        while queue:
            index = queue.popleft()
            if index in indices:
                continue
            indices.add(index)
            unvisited.discard(index)
            edge = candidates[index]
            for node in (("L", edge.left_id), ("R", edge.right_id)):
                for connected_index in by_node[node]:
                    if connected_index not in indices:
                        queue.append(connected_index)
        components.append(tuple(candidates[index] for index in sorted(indices)))
    return tuple(
        sorted(
            components,
            key=lambda values: min((item.left_id, item.right_id) for item in values),
        )
    )


def _solve_component(
    *,
    left_ids: tuple[str, ...],
    right_ids: tuple[str, ...],
    candidates: tuple[CandidateEvidence, ...],
    assignment_floor_bp: int,
    solver: AssignmentSolver,
) -> tuple[SelectedAssignmentEdge, ...]:
    edges = {(item.left_id, item.right_id): item for item in candidates}
    forbidden_cost = len(left_ids) * 10_001 + 1
    costs: list[list[int]] = []
    for left_id in left_ids:
        row = [
            -(
                edges[(left_id, right_id)].score_bp - assignment_floor_bp
            )
            if (left_id, right_id) in edges
            else forbidden_cost
            for right_id in right_ids
        ]
        row.extend(0 for _ in left_ids)
        costs.append(row)

    selections = solver.minimize(costs)
    _validate_solver_selection(
        selections=selections,
        row_count=len(left_ids),
        column_count=len(right_ids) + len(left_ids),
    )
    selected: list[SelectedAssignmentEdge] = []
    for row_index, column_index in selections:
        if column_index >= len(right_ids):
            continue
        left_id = left_ids[row_index]
        right_id = right_ids[column_index]
        candidate = edges.get((left_id, right_id))
        if candidate is None:
            raise DomainValidationError("assignment solver selected a forbidden relationship")
        utility = candidate.score_bp - assignment_floor_bp
        if utility <= 0:
            raise DomainValidationError("assignment solver selected a nonpositive real edge")
        selected.append(SelectedAssignmentEdge(left_id, right_id, candidate.score_bp, utility))
    return tuple(sorted(selected, key=lambda item: (item.left_id, item.right_id)))


def _validate_solver_selection(
    *, selections: tuple[tuple[int, int], ...], row_count: int, column_count: int
) -> None:
    if len(selections) != row_count:
        raise DomainValidationError("assignment solver must select exactly one column per row")
    rows = [row for row, _ in selections]
    columns = [column for _, column in selections]
    if set(rows) != set(range(row_count)) or len(columns) != len(set(columns)):
        raise DomainValidationError("assignment solver returned duplicate or missing row/column selections")
    if any(column < 0 or column >= column_count for column in columns):
        raise DomainValidationError("assignment solver returned an out-of-range column")


def _component_id(left_ids: tuple[str, ...], right_ids: tuple[str, ...]) -> str:
    payload = json.dumps(
        {"left": left_ids, "right": right_ids},
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return f"component-{hashlib.sha256(payload).hexdigest()[:16]}"


def _graph_digest(
    *,
    component_id: str,
    assignment_floor_bp: int,
    edges: tuple[CandidateEvidence, ...],
) -> str:
    payload = json.dumps(
        {
            "component_id": component_id,
            "assignment_floor_bp": assignment_floor_bp,
            "edges": [
                {
                    "left_id": item.left_id,
                    "right_id": item.right_id,
                    "score_bp": item.score_bp,
                    "complete": item.complete_computation,
                }
                for item in sorted(edges, key=lambda value: (value.left_id, value.right_id))
            ],
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
