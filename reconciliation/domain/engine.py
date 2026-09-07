"""Pure orchestration for a complete deterministic reconciliation result."""

from __future__ import annotations

import hashlib
import json
from dataclasses import fields, is_dataclass, replace
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Any

from .assignment import AssignmentSolver, solve_assignment
from .candidates import generate_candidates
from .comparison import compare_pair_fields
from .gating import gate_assignment
from .diagnostics import diagnose_accepted_unmatched
from .hashing import canonical_datetime, canonical_decimal
from .reconciliation import (
    CandidateEvidence,
    ComparisonPolicy,
    DecisionInputs,
    EngineResult,
    EngineSnapshot,
    MatchRecord,
    MatchingPolicy,
    PairOrigin,
    PairOutcome,
    RecordSide,
    UnpairedOutcome,
    UnpairedReason,
)
from .references import ReferencePreprocessingResult, preprocess_references
from .scoring import score_candidates


def reconcile(
    *,
    snapshot: EngineSnapshot,
    matching_policy: MatchingPolicy,
    comparison_policy: ComparisonPolicy,
    decisions: DecisionInputs,
    solver: AssignmentSolver,
) -> EngineResult:
    """Run every selection stage and return one terminal outcome per input record."""

    preprocessed = preprocess_references(
        snapshot=snapshot,
        decisions=decisions,
        reference_contract=matching_policy.reference_contract,
    )
    generated = generate_candidates(preprocessed=preprocessed, policy=matching_policy)
    candidates = score_candidates(
        preprocessed=preprocessed,
        generated=generated,
        policy=matching_policy,
    )
    assignment = solve_assignment(
        candidates=candidates,
        generated=generated,
        policy=matching_policy,
        solver=solver,
    )
    gated = gate_assignment(
        candidates=candidates,
        assignment=assignment,
        policy=matching_policy,
        solver=solver,
    )

    left_by_id = {item.observation_id: item for item in snapshot.left}
    right_by_id = {item.observation_id: item for item in snapshot.right}
    pairs = [
        _compare_pair(
            pair=pair,
            left=left_by_id[pair.left_id],
            right=right_by_id[pair.right_id],
            matching_policy=matching_policy,
            comparison_policy=comparison_policy,
        )
        for pair in preprocessed.pairs
    ]
    for proposal in gated.accepted_proposals:
        pairs.append(
            _compare_pair(
                pair=PairOutcome(
                    proposal.left_id,
                    proposal.right_id,
                    PairOrigin.WEIGHTED_GLOBAL,
                    score_bp=proposal.score_bp,
                    global_gap_bp=proposal.global_gap_bp,
                ),
                left=left_by_id[proposal.left_id],
                right=right_by_id[proposal.right_id],
                matching_policy=matching_policy,
                comparison_policy=comparison_policy,
            )
        )

    paired_ids = {
        identity
        for pair in pairs
        for identity in (pair.left_id, pair.right_id)
    }
    unpaired = list(preprocessed.terminal_unpaired)
    for side, records in (
        (RecordSide.LEFT, preprocessed.remaining_left),
        (RecordSide.RIGHT, preprocessed.remaining_right),
    ):
        for record in records:
            if record.observation_id in paired_ids:
                continue
            unpaired.append(
                _automatic_unpaired(
                    record=record,
                    side=side,
                    candidates=candidates,
                    preprocessed=preprocessed,
                    limited_ids=frozenset(assignment.limited_record_ids),
                    assignment_floor_bp=matching_policy.assignment_floor_bp,
                )
            )

    primary_result = EngineResult(
        left_revision_id=snapshot.left_revision_id,
        right_revision_id=snapshot.right_revision_id,
        matching_policy_version=matching_policy.policy_version,
        comparison_policy_version=comparison_policy.policy_version,
        engine_version=matching_policy.engine_version,
        solver_version=matching_policy.solver_version,
        input_left_ids=snapshot.input_left_ids,
        input_right_ids=snapshot.input_right_ids,
        pairs=tuple(pairs),
        unpaired=tuple(unpaired),
        candidates=candidates,
        components=gated.components,
    )
    diagnostics = diagnose_accepted_unmatched(
        snapshot=snapshot,
        decisions=decisions,
        matching_policy=matching_policy,
        primary_result=primary_result,
    )
    return replace(primary_result, diagnostics=diagnostics)


def candidate_graph_digest(candidates: tuple[CandidateEvidence, ...]) -> str:
    """Return a canonical digest of the complete scored candidate evidence."""

    ordered = tuple(sorted(candidates, key=lambda item: (item.left_id, item.right_id)))
    return _digest({"kind": "candidate-graph-v1", "candidates": ordered})


def canonical_result_json(result: EngineResult) -> str:
    """Serialize an engine result without lossy decimal or timestamp conversion."""

    return json.dumps(
        _canonical_value(result),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def engine_result_digest(result: EngineResult) -> str:
    """Return a canonical digest suitable for reproducibility and publication checks."""

    return hashlib.sha256(canonical_result_json(result).encode("utf-8")).hexdigest()


def _compare_pair(
    *,
    pair: PairOutcome,
    left: MatchRecord,
    right: MatchRecord,
    matching_policy: MatchingPolicy,
    comparison_policy: ComparisonPolicy,
) -> PairOutcome:
    return PairOutcome(
        left_id=pair.left_id,
        right_id=pair.right_id,
        origin=pair.origin,
        score_bp=pair.score_bp,
        global_gap_bp=pair.global_gap_bp,
        comparisons=compare_pair_fields(
            left=left,
            right=right,
            origin=pair.origin,
            policy=comparison_policy,
            reference_contract=matching_policy.reference_contract,
        ),
    )


def _automatic_unpaired(
    *,
    record: MatchRecord,
    side: RecordSide,
    candidates: tuple[CandidateEvidence, ...],
    preprocessed: ReferencePreprocessingResult,
    limited_ids: frozenset[str],
    assignment_floor_bp: int,
) -> UnpairedOutcome:
    identity = record.observation_id
    related_candidates = tuple(
        item
        for item in candidates
        if (item.left_id if side is RecordSide.LEFT else item.right_id) == identity
    )
    prohibited_counterparts = tuple(
        item.right_id if side is RecordSide.LEFT else item.left_id
        for item in preprocessed.prohibited_relationships
        if (item.left_id if side is RecordSide.LEFT else item.right_id) == identity
    )
    candidate_counterparts = tuple(
        item.right_id if side is RecordSide.LEFT else item.left_id
        for item in related_candidates
    )
    related_ids = tuple(sorted(set((*candidate_counterparts, *prohibited_counterparts))))

    if identity in limited_ids:
        return UnpairedOutcome(
            identity,
            side,
            UnpairedReason.COMPUTATION_LIMITED,
            "Candidate enumeration or assignment was incomplete for this record, so automatic matching was withheld.",
            related_ids,
        )
    if not related_candidates:
        if prohibited_counterparts:
            return UnpairedOutcome(
                identity,
                side,
                UnpairedReason.PROHIBITED,
                "The available relationship for this record was prohibited by an active reviewer decision.",
                related_ids,
            )
        return UnpairedOutcome(
            identity,
            side,
            UnpairedReason.NO_CANDIDATE,
            "No candidate was found in the complete configured search.",
        )
    if all(item.contradictions for item in related_candidates):
        return UnpairedOutcome(
            identity,
            side,
            UnpairedReason.PROHIBITED,
            "Every retained candidate for this record contains a hard contradiction.",
            related_ids,
        )
    if all(item.score_bp <= assignment_floor_bp for item in related_candidates):
        return UnpairedOutcome(
            identity,
            side,
            UnpairedReason.BELOW_ASSIGNMENT_FLOOR,
            "Every candidate rule score was at or below the assignment floor.",
            related_ids,
        )
    return UnpairedOutcome(
        identity,
        side,
        UnpairedReason.AMBIGUOUS,
        "No proposal for this record passed every automatic acceptance gate.",
        related_ids,
    )


def _digest(value: Any) -> str:
    payload = json.dumps(
        _canonical_value(value),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _canonical_value(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: _canonical_value(getattr(value, field.name))
            for field in fields(value)
        }
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Decimal):
        return {"decimal": canonical_decimal(value)}
    if isinstance(value, datetime):
        return {"datetime": canonical_datetime(value)}
    if isinstance(value, timedelta):
        microseconds = (
            value.days * 86_400_000_000
            + value.seconds * 1_000_000
            + value.microseconds
        )
        return {"timedelta_microseconds": microseconds}
    if isinstance(value, tuple):
        return [_canonical_value(item) for item in value]
    if isinstance(value, dict):
        if any(not isinstance(key, str) for key in value):
            raise TypeError("canonical result mappings require string keys")
        return {key: _canonical_value(item) for key, item in sorted(value.items())}
    if value is None or isinstance(value, (bool, int, str)):
        return value
    raise TypeError(f"unsupported canonical result value: {type(value).__name__}")
