from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from reconciliation.domain import (
    AcceptedUnmatched,
    CapacityLimits,
    CanonicalSide,
    CanonicalState,
    ComparisonPolicy,
    DecisionHealthDiagnostic,
    DecisionInputs,
    DiagnosticKind,
    DomainValidationError,
    EngineSnapshot,
    MatchRecord,
    MatchingPolicy,
    UnpairedReason,
    diagnose_accepted_unmatched,
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


def accepted(identity: str, index: int = 1) -> AcceptedUnmatched:
    return AcceptedUnmatched(f"accepted-{index}", f"revision-{index}", identity)


def run(
    left: tuple[MatchRecord, ...],
    right: tuple[MatchRecord, ...],
    *,
    decisions: DecisionInputs,
    policy: MatchingPolicy | None = None,
):
    snapshot = EngineSnapshot("left-v1", "right-v1", left, right)
    matching_policy = policy or MatchingPolicy.initial_demo()
    result = reconcile(
        snapshot=snapshot,
        matching_policy=matching_policy,
        comparison_policy=ComparisonPolicy.initial_demo(),
        decisions=decisions,
        solver=ScipyAssignmentSolver(),
    )
    return snapshot, matching_policy, result


def test_free_plausible_counterpart_is_reported_without_entering_assignment() -> None:
    snapshot, policy, result = run(
        (record("L1"),),
        (record("R1"),),
        decisions=DecisionInputs(accepted_unmatched=(accepted("L1"),)),
    )

    assert result.pairs == ()
    assert {(item.record_id, item.reason) for item in result.unpaired} == {
        ("L1", UnpairedReason.ACCEPTED_UNMATCHED),
        ("R1", UnpairedReason.NO_CANDIDATE),
    }
    assert result.candidates == ()
    assert result.components == ()
    assert result.diagnostics == (
        DecisionHealthDiagnostic(
            DiagnosticKind.ACCEPTED_UNMATCHED_CANDIDATE,
            "L1",
            "R1",
            None,
            True,
            "Candidate R1 has rule score 10000 under the current policy; the candidate is not currently paired.",
        ),
    )

    primary = replace(result, diagnostics=())
    before = (primary.pairs, primary.unpaired, primary.candidates, primary.components)
    diagnose_accepted_unmatched(
        snapshot=snapshot,
        decisions=DecisionInputs(accepted_unmatched=(accepted("L1"),)),
        matching_policy=policy,
        primary_result=primary,
    )
    assert (primary.pairs, primary.unpaired, primary.candidates, primary.components) == before


def test_allocated_plausible_counterpart_reports_current_pair_key() -> None:
    _, _, result = run(
        (
            record("L1"),
            record("L2", reference_value="T-1"),
        ),
        (record("R1", reference_value="T-1"),),
        decisions=DecisionInputs(accepted_unmatched=(accepted("L1"),)),
    )

    assert [(item.left_id, item.right_id) for item in result.pairs] == [("L2", "R1")]
    diagnostic = result.diagnostics[0]
    assert diagnostic.candidate_id == "R1"
    assert diagnostic.candidate_current_pair_id == "L2:R1"
    assert "currently paired with L2" in diagnostic.explanation
    assert all(item.left_id != "L1" for item in result.candidates)


def test_right_side_accepted_unmatched_searches_left_candidates_symmetrically() -> None:
    _, _, result = run(
        (record("L1"),),
        (record("R1"),),
        decisions=DecisionInputs(accepted_unmatched=(accepted("R1"),)),
    )

    assert result.diagnostics[0].record_id == "R1"
    assert result.diagnostics[0].candidate_id == "L1"


def test_incomplete_diagnostic_search_emits_candidates_and_explicit_warning() -> None:
    policy = replace(
        MatchingPolicy.initial_demo(),
        limits=CapacityLimits(100, 2_500, 250_000, 1),
    )
    _, _, result = run(
        (record("L1"),),
        (record("R1"), record("R2")),
        decisions=DecisionInputs(accepted_unmatched=(accepted("L1"),)),
        policy=policy,
    )

    kinds = {item.kind for item in result.diagnostics}
    assert kinds == {
        DiagnosticKind.ACCEPTED_UNMATCHED_CANDIDATE,
        DiagnosticKind.INCOMPLETE_SEARCH,
    }
    candidate_diagnostic = next(
        item
        for item in result.diagnostics
        if item.kind is DiagnosticKind.ACCEPTED_UNMATCHED_CANDIDATE
    )
    warning = next(
        item for item in result.diagnostics if item.kind is DiagnosticKind.INCOMPLETE_SEARCH
    )
    assert candidate_diagnostic.complete is False
    assert warning.complete is False
    assert warning.candidate_id is None
    assert "does not establish that no candidate exists" in warning.explanation


def test_diagnostic_run_budget_is_shared_across_accepted_decisions() -> None:
    policy = replace(
        MatchingPolicy.initial_demo(),
        limits=CapacityLimits(100, 2_500, 1, 200),
    )
    _, _, result = run(
        (
            record("L1", instrument="ASSET-1"),
            record("L2", instrument="ASSET-2"),
        ),
        (
            record("R1", instrument="ASSET-1"),
            record("R2", instrument="ASSET-2"),
        ),
        decisions=DecisionInputs(
            accepted_unmatched=(accepted("L1", 1), accepted("L2", 2))
        ),
        policy=policy,
    )

    assert any(
        item.record_id == "L2" and item.kind is DiagnosticKind.INCOMPLETE_SEARCH
        for item in result.diagnostics
    )
    assert all(item.candidate_id != "R2" for item in result.diagnostics)


def test_low_score_and_hard_contradiction_do_not_create_plausibility_alerts() -> None:
    _, _, low = run(
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
        decisions=DecisionInputs(accepted_unmatched=(accepted("L1"),)),
    )
    _, _, contradicted = run(
        (record("L2", reference_value="LEFT"),),
        (record("R2", reference_value="RIGHT"),),
        decisions=DecisionInputs(accepted_unmatched=(accepted("L2"),)),
    )

    assert low.diagnostics == ()
    assert contradicted.diagnostics == ()


def test_diagnostics_are_deterministic_under_input_and_decision_reordering() -> None:
    left = (
        record("L2", instrument="ASSET-2"),
        record("L1", instrument="ASSET-1"),
    )
    right = (
        record("R2", instrument="ASSET-2"),
        record("R1", instrument="ASSET-1"),
    )
    decisions = DecisionInputs(
        accepted_unmatched=(accepted("L2", 2), accepted("L1", 1))
    )

    first = run(left, right, decisions=decisions)[2]
    second = run(
        tuple(reversed(left)),
        tuple(reversed(right)),
        decisions=DecisionInputs(
            accepted_unmatched=tuple(reversed(decisions.accepted_unmatched))
        ),
    )[2]

    assert first == second
    assert [(item.record_id, item.candidate_id) for item in first.diagnostics] == [
        ("L1", "R1"),
        ("L2", "R2"),
    ]


def test_diagnostic_contract_rejects_missing_candidate_and_false_completeness() -> None:
    with pytest.raises(DomainValidationError, match="requires candidate_id"):
        DecisionHealthDiagnostic(
            DiagnosticKind.ACCEPTED_UNMATCHED_CANDIDATE,
            "L1",
            None,
            None,
            True,
            "Invalid candidate diagnostic.",
        )
    with pytest.raises(DomainValidationError, match="cannot be complete"):
        DecisionHealthDiagnostic(
            DiagnosticKind.INCOMPLETE_SEARCH,
            "L1",
            None,
            None,
            True,
            "Invalid completeness diagnostic.",
        )


def test_result_rejects_foreign_diagnostic_identity_or_allocation() -> None:
    _, _, result = run(
        (record("L1"),),
        (record("R1"),),
        decisions=DecisionInputs(accepted_unmatched=(accepted("L1"),)),
    )
    foreign = replace(result.diagnostics[0], candidate_id="foreign")
    stale_allocation = replace(result.diagnostics[0], candidate_current_pair_id="L9:R9")

    with pytest.raises(DomainValidationError, match="result inputs"):
        replace(result, diagnostics=(foreign,))
    with pytest.raises(DomainValidationError, match="result pairs"):
        replace(result, diagnostics=(stale_allocation,))
