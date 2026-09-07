"""Read-only health diagnostics for accepted-unmatched decisions."""

from __future__ import annotations

from dataclasses import replace

from .candidates import generate_candidates
from .reconciliation import (
    DecisionHealthDiagnostic,
    DecisionInputs,
    DiagnosticKind,
    EngineResult,
    EngineSnapshot,
    MatchRecord,
    MatchingPolicy,
    PairOutcome,
    RecordSide,
)
from .references import (
    ProhibitedRelationship,
    ReferencePreprocessingResult,
)
from .scoring import score_candidates


def diagnose_accepted_unmatched(
    *,
    snapshot: EngineSnapshot,
    decisions: DecisionInputs,
    matching_policy: MatchingPolicy,
    primary_result: EngineResult,
) -> tuple[DecisionHealthDiagnostic, ...]:
    """Search for plausible new evidence without feeding reservations into assignment."""

    left_by_id = {item.observation_id: item for item in snapshot.left}
    right_by_id = {item.observation_id: item for item in snapshot.right}
    pair_by_record = {
        identity: pair
        for pair in primary_result.pairs
        for identity in (pair.left_id, pair.right_id)
    }
    prohibited = tuple(
        ProhibitedRelationship(item.left_id, item.right_id, item.decision_id, item.revision_id)
        for item in decisions.rejected_relationships
        if item.left_id in left_by_id and item.right_id in right_by_id
    )
    remaining_run_edges = matching_policy.limits.max_run_candidate_edges
    diagnostics: list[DecisionHealthDiagnostic] = []

    for accepted in decisions.accepted_unmatched:
        side, record = _accepted_record(accepted.record_id, left_by_id, right_by_id)
        if record is None or not record.eligible:
            continue
        if remaining_run_edges == 0:
            diagnostics.append(_incomplete_diagnostic(accepted.record_id, "run edge limit"))
            continue
        opposite = tuple(
            item
            for item in (snapshot.right if side is RecordSide.LEFT else snapshot.left)
            if item.eligible
        )
        diagnostic_limits = replace(
            matching_policy.limits,
            max_run_candidate_edges=remaining_run_edges,
        )
        diagnostic_policy = replace(matching_policy, limits=diagnostic_limits)
        preprocessed = _diagnostic_preprocessing(
            record=record,
            side=side,
            opposite=opposite,
            prohibited=prohibited,
        )
        generated = generate_candidates(
            preprocessed=preprocessed,
            policy=diagnostic_policy,
        )
        remaining_run_edges -= len(generated.candidates)
        candidates = score_candidates(
            preprocessed=preprocessed,
            generated=generated,
            policy=diagnostic_policy,
        )
        for candidate in candidates:
            if (
                candidate.score_bp < matching_policy.automatic_threshold_bp
                or not candidate.coverage_sufficient
                or candidate.contradictions
            ):
                continue
            candidate_id = (
                candidate.right_id if side is RecordSide.LEFT else candidate.left_id
            )
            current_pair = pair_by_record.get(candidate_id)
            diagnostics.append(
                DecisionHealthDiagnostic(
                    kind=DiagnosticKind.ACCEPTED_UNMATCHED_CANDIDATE,
                    record_id=accepted.record_id,
                    candidate_id=candidate_id,
                    candidate_current_pair_id=(
                        None if current_pair is None else _pair_key(current_pair)
                    ),
                    complete=candidate.complete_computation,
                    explanation=_candidate_explanation(
                        candidate_id=candidate_id,
                        score_bp=candidate.score_bp,
                        current_pair=current_pair,
                    ),
                )
            )
        if not generated.complete:
            diagnostics.append(
                _incomplete_diagnostic(
                    accepted.record_id,
                    "candidate enumeration limit",
                )
            )

    return tuple(
        sorted(
            diagnostics,
            key=lambda item: (
                item.record_id,
                item.candidate_id or "",
                item.kind.value,
            ),
        )
    )


def _accepted_record(
    record_id: str,
    left_by_id: dict[str, MatchRecord],
    right_by_id: dict[str, MatchRecord],
) -> tuple[RecordSide, MatchRecord | None]:
    if record_id in left_by_id:
        return RecordSide.LEFT, left_by_id[record_id]
    if record_id in right_by_id:
        return RecordSide.RIGHT, right_by_id[record_id]
    return RecordSide.LEFT, None


def _diagnostic_preprocessing(
    *,
    record: MatchRecord,
    side: RecordSide,
    opposite: tuple[MatchRecord, ...],
    prohibited: tuple[ProhibitedRelationship, ...],
) -> ReferencePreprocessingResult:
    left = (record,) if side is RecordSide.LEFT else opposite
    right = opposite if side is RecordSide.LEFT else (record,)
    left_ids = {item.observation_id for item in left}
    right_ids = {item.observation_id for item in right}
    return ReferencePreprocessingResult(
        input_left_ids=tuple(left_ids),
        input_right_ids=tuple(right_ids),
        pairs=(),
        terminal_unpaired=(),
        remaining_left=left,
        remaining_right=right,
        prohibited_relationships=tuple(
            item
            for item in prohibited
            if item.left_id in left_ids and item.right_id in right_ids
        ),
        reference_conflicts=(),
    )


def _pair_key(pair: PairOutcome) -> str:
    return f"{pair.left_id}:{pair.right_id}"


def _candidate_explanation(
    *,
    candidate_id: str,
    score_bp: int,
    current_pair: PairOutcome | None,
) -> str:
    if current_pair is None:
        allocation = "the candidate is not currently paired"
    else:
        partner = (
            current_pair.right_id
            if current_pair.left_id == candidate_id
            else current_pair.left_id
        )
        allocation = f"the candidate is currently paired with {partner}"
    return (
        f"Candidate {candidate_id} has rule score {score_bp} under the current policy; "
        f"{allocation}."
    )


def _incomplete_diagnostic(record_id: str, limit: str) -> DecisionHealthDiagnostic:
    return DecisionHealthDiagnostic(
        kind=DiagnosticKind.INCOMPLETE_SEARCH,
        record_id=record_id,
        candidate_id=None,
        candidate_current_pair_id=None,
        complete=False,
        explanation=(
            f"Decision-health search is incomplete because it reached the {limit}; "
            "absence of another diagnostic does not establish that no candidate exists."
        ),
    )
