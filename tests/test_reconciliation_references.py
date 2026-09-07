from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from reconciliation.domain import (
    AcceptedUnmatched,
    CanonicalSide,
    CanonicalState,
    DecisionInputs,
    DomainValidationError,
    EngineSnapshot,
    ManualLink,
    MatchRecord,
    PairOrigin,
    RecordSide,
    ReferenceContract,
    RejectedRelationship,
    ReservedIdentity,
    UnpairedReason,
    preprocess_references,
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
        "reference_value": None,
        "shared_reference_alias": None,
    }
    values.update(overrides)
    return MatchRecord(**values)  # type: ignore[arg-type]


def snapshot(
    left: tuple[MatchRecord, ...], right: tuple[MatchRecord, ...]
) -> EngineSnapshot:
    return EngineSnapshot("left-revision", "right-revision", left, right)


def preprocess(
    left: tuple[MatchRecord, ...],
    right: tuple[MatchRecord, ...],
    *,
    decisions: DecisionInputs = DecisionInputs(),
    contract: ReferenceContract = ReferenceContract.SHARED_MUST_AGREE,
):
    return preprocess_references(
        snapshot=snapshot(left, right),
        decisions=decisions,
        reference_contract=contract,
    )


def terminal_map(result) -> dict[str, UnpairedReason]:
    return {item.record_id: item.reason for item in result.terminal_unpaired}


def test_unique_trusted_shared_reference_establishes_authoritative_pair() -> None:
    result = preprocess(
        (record("L1", reference_value="T-1011"),),
        (record("R1", reference_value="T-1011", gross_amount=Decimal("201")),),
    )

    assert len(result.pairs) == 1
    assert result.pairs[0].origin is PairOrigin.AUTHORITATIVE_REFERENCE
    assert (result.pairs[0].left_id, result.pairs[0].right_id) == ("L1", "R1")
    assert result.pairs[0].comparisons == ()
    assert result.remaining_left == result.remaining_right == ()


def test_reference_pair_remains_authoritative_when_every_other_field_disagrees() -> None:
    result = preprocess(
        (record("L1", reference_value="T-1011"),),
        (
            record(
                "R1",
                reference_value="T-1011",
                instrument="ETH-USD",
                side=CanonicalSide.SELL,
                currency="EUR",
                quantity=Decimal("3"),
                gross_amount=Decimal("300"),
            ),
        ),
    )

    assert [(item.left_id, item.right_id, item.origin) for item in result.pairs] == [
        ("L1", "R1", PairOrigin.AUTHORITATIVE_REFERENCE)
    ]


def test_cancelled_records_are_explicitly_excluded_before_reference_pairing() -> None:
    result = preprocess(
        (record("L1", reference_value="T-1", state=CanonicalState.CANCELLED),),
        (record("R1", reference_value="T-1"),),
    )

    assert result.pairs == ()
    assert terminal_map(result) == {"L1": UnpairedReason.CANCELLED_EXCLUDED}
    assert tuple(item.observation_id for item in result.remaining_right) == ("R1",)


def test_manual_link_reserves_both_endpoints_and_ignores_automatic_contradictions() -> None:
    decisions = DecisionInputs(
        manual_links=(ManualLink("manual-1", "rev-1", "L1", "R1"),),
        rejected_relationships=(
            RejectedRelationship("reject-1", "rev-1", "L1", "R1"),
        ),
    )
    result = preprocess(
        (record("L1", reference_value="LEFT"),),
        (record("R1", reference_value="RIGHT", currency="EUR"),),
        decisions=decisions,
    )

    assert len(result.pairs) == 1
    assert result.pairs[0].origin is PairOrigin.MANUAL
    assert result.prohibited_relationships[0].decision_id == "reject-1"
    assert result.remaining_left == result.remaining_right == ()


def test_missing_or_cancelled_manual_counterpart_requires_attention() -> None:
    missing = preprocess(
        (record("L1"),),
        (),
        decisions=DecisionInputs(
            manual_links=(ManualLink("manual-1", "rev-1", "L1", "missing-R"),)
        ),
    )
    cancelled = preprocess(
        (record("L1"),),
        (record("R1", state=CanonicalState.CANCELLED),),
        decisions=DecisionInputs(
            manual_links=(ManualLink("manual-2", "rev-1", "L1", "R1"),)
        ),
    )

    assert terminal_map(missing) == {"L1": UnpairedReason.MANUAL_ATTENTION}
    assert terminal_map(cancelled) == {
        "L1": UnpairedReason.MANUAL_ATTENTION,
        "R1": UnpairedReason.CANCELLED_EXCLUDED,
    }


def test_accepted_unmatched_and_reserved_identities_do_not_reach_automatic_stage() -> None:
    decisions = DecisionInputs(
        accepted_unmatched=(AcceptedUnmatched("accept-1", "rev-1", "L1"),),
        reserved_identities=(ReservedIdentity("reserve-1", "rev-1", "R1"),),
    )
    result = preprocess(
        (record("L1", reference_value="T-1"),),
        (record("R1", reference_value="T-1"),),
        decisions=decisions,
    )

    assert terminal_map(result) == {
        "L1": UnpairedReason.ACCEPTED_UNMATCHED,
        "R1": UnpairedReason.REVIEWER_RESERVED,
    }
    assert result.pairs == ()
    assert result.remaining_left == result.remaining_right == ()


def test_cancelled_outcome_takes_precedence_over_accepted_unmatched_reservation() -> None:
    result = preprocess(
        (record("L1", state=CanonicalState.CANCELLED),),
        (),
        decisions=DecisionInputs(
            accepted_unmatched=(AcceptedUnmatched("accept-1", "rev-1", "L1"),)
        ),
    )

    assert terminal_map(result) == {"L1": UnpairedReason.CANCELLED_EXCLUDED}


def test_active_rejection_blocks_unique_authoritative_pair_without_reserving_identities() -> None:
    result = preprocess(
        (record("L1", reference_value="T-1"),),
        (record("R1", reference_value="T-1"),),
        decisions=DecisionInputs(
            rejected_relationships=(
                RejectedRelationship("reject-1", "rev-4", "L1", "R1"),
            )
        ),
    )

    assert result.pairs == ()
    assert result.terminal_unpaired == ()
    assert tuple(item.observation_id for item in result.remaining_left) == ("L1",)
    assert tuple(item.observation_id for item in result.remaining_right) == ("R1",)
    assert result.prohibited_relationships[0] == type(result.prohibited_relationships[0])(
        "L1", "R1", "reject-1", "rev-4"
    )


@pytest.mark.parametrize(
    ("left_refs", "right_refs"),
    [
        (("T-1", "T-1"), ("T-1",)),
        (("T-1",), ("T-1", "T-1")),
        (("T-1", "T-1"), ()),
    ],
)
def test_nonunique_trusted_reference_abstains_with_full_conflicting_members(
    left_refs: tuple[str, ...], right_refs: tuple[str, ...]
) -> None:
    left = tuple(record(f"L{index}", reference_value=value) for index, value in enumerate(left_refs, 1))
    right = tuple(record(f"R{index}", reference_value=value) for index, value in enumerate(right_refs, 1))
    result = preprocess(left, right)
    conflict_ids = tuple(sorted(record.observation_id for record in left + right))

    assert result.pairs == ()
    assert len(result.reference_conflicts) == 1
    assert result.reference_conflicts[0].left_ids == tuple(
        item.observation_id for item in left
    )
    assert result.reference_conflicts[0].right_ids == tuple(
        item.observation_id for item in right
    )
    assert all(item.reason is UnpairedReason.DUPLICATE_REFERENCE for item in result.terminal_unpaired)
    assert all(item.related_ids == conflict_ids for item in result.terminal_unpaired)


def test_duplicate_reference_only_considers_records_left_after_reviewer_reservations() -> None:
    result = preprocess(
        (
            record("L1", reference_value="T-1"),
            record("L2", reference_value="T-1"),
        ),
        (record("R1", reference_value="T-1"),),
        decisions=DecisionInputs(
            accepted_unmatched=(AcceptedUnmatched("accept-1", "rev-1", "L2"),)
        ),
    )

    assert [(item.left_id, item.right_id) for item in result.pairs] == [("L1", "R1")]
    assert terminal_map(result) == {"L2": UnpairedReason.ACCEPTED_UNMATCHED}
    assert result.reference_conflicts == ()


def test_source_local_ids_do_not_pair_without_explicit_shared_alias() -> None:
    no_alias = preprocess(
        (record("L1", reference_value="ledger-11"),),
        (record("R1", reference_value="provider-88"),),
        contract=ReferenceContract.SOURCE_LOCAL_OR_ALIAS,
    )
    alias = preprocess(
        (
            record(
                "L1", reference_value="ledger-11", shared_reference_alias="SHARED-1"
            ),
        ),
        (
            record(
                "R1", reference_value="provider-88", shared_reference_alias="SHARED-1"
            ),
        ),
        contract=ReferenceContract.SOURCE_LOCAL_OR_ALIAS,
    )

    assert no_alias.pairs == ()
    assert tuple(item.observation_id for item in no_alias.remaining_left) == ("L1",)
    assert alias.pairs[0].origin is PairOrigin.AUTHORITATIVE_REFERENCE


def test_different_shared_aliases_remain_for_weighted_evidence_and_are_not_authoritative() -> None:
    result = preprocess(
        (record("L1", shared_reference_alias="SHARED-1"),),
        (record("R1", shared_reference_alias="SHARED-2"),),
        contract=ReferenceContract.SOURCE_LOCAL_OR_ALIAS,
    )

    assert result.pairs == ()
    assert tuple(item.observation_id for item in result.remaining_left) == ("L1",)
    assert tuple(item.observation_id for item in result.remaining_right) == ("R1",)


def test_relationship_decisions_reject_endpoint_on_wrong_side() -> None:
    with pytest.raises(DomainValidationError, match="right-side record as left_id"):
        preprocess(
            (record("L1"),),
            (record("R1"),),
            decisions=DecisionInputs(
                manual_links=(ManualLink("manual-1", "rev-1", "R1", "missing"),)
            ),
        )
    with pytest.raises(DomainValidationError, match="left-side record as right_id"):
        preprocess(
            (record("L1"),),
            (record("R1"),),
            decisions=DecisionInputs(
                rejected_relationships=(
                    RejectedRelationship("reject-1", "rev-1", "missing", "L1"),
                )
            ),
        )


def test_preprocessing_is_identical_under_snapshot_and_decision_reordering() -> None:
    left = (
        record("L2", reference_value="T-2"),
        record("L1", reference_value="T-1"),
        record("L3", state=CanonicalState.CANCELLED),
    )
    right = (
        record("R2", reference_value="T-2"),
        record("R1", reference_value="T-1"),
    )
    decisions = DecisionInputs(
        rejected_relationships=(
            RejectedRelationship("reject-2", "rev-1", "L2", "R2"),
            RejectedRelationship("reject-1", "rev-1", "L1", "R1"),
        )
    )

    first = preprocess(left, right, decisions=decisions)
    second = preprocess(tuple(reversed(left)), tuple(reversed(right)), decisions=DecisionInputs(
        rejected_relationships=tuple(reversed(decisions.rejected_relationships))
    ))

    assert first == second
