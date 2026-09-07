from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from reconciliation.domain import (
    CASE_KEY_VERSION,
    CaseKey,
    CaseKind,
    CaseLineageEdge,
    CaseOccurrenceDescriptor,
    CaseResultKind,
    CaseTransitionPlan,
    DecisionAction,
    DecisionAttention,
    DecisionAuthority,
    DecisionAuthorityKind,
    DecisionCommand,
    DecisionConflict,
    DecisionHealth,
    DecisionHealthEvidence,
    DecisionHealthProjection,
    DomainValidationError,
    ExpectedDecisionRevision,
    RecordSide,
    ReplacementPreview,
    ReviewConflict,
    ReviewConflictCode,
    ambiguity_case_key,
    pair_case_key,
    project_decision_health,
    unpaired_case_key,
)


POLICY_DIGEST = "1" * 64


def expected(decision: str = "D1", revision: str = "R1") -> ExpectedDecisionRevision:
    return ExpectedDecisionRevision(decision, revision)


@pytest.mark.parametrize(
    ("action", "authority", "reviewed"),
    [
        (DecisionAction.LINK, DecisionAuthority.link("L1", "R1"), ("OL1", "OR1")),
        (
            DecisionAction.ACCEPT_UNMATCHED,
            DecisionAuthority.accept_unmatched("L1", RecordSide.LEFT),
            ("OL1",),
        ),
        (
            DecisionAction.REJECT_CANDIDATE,
            DecisionAuthority.reject_candidate("L1", "R1"),
            ("OL1", "OR1"),
        ),
    ],
)
def test_initial_action_contracts_are_valid_and_canonical(
    action: DecisionAction,
    authority: DecisionAuthority,
    reviewed: tuple[str, ...],
) -> None:
    command = DecisionCommand(
        action=action,
        authority=authority,
        reason="Reviewed the source evidence",
        actor="WORKSPACE_REVIEWER",
        expected_resolution_generation=4,
        reviewed_observation_ids=tuple(reversed(reviewed)),
    )

    assert command.reviewed_observation_ids == tuple(sorted(reviewed))
    assert authority.reserves_endpoints is (
        action is not DecisionAction.REJECT_CANDIDATE
    )
    with pytest.raises(FrozenInstanceError):
        command.reason = "changed"  # type: ignore[misc]


@pytest.mark.parametrize("action", list(DecisionAction))
def test_every_action_requires_a_reason(action: DecisionAction) -> None:
    values: dict[str, object] = {
        "action": action,
        "reason": " ",
        "actor": "WORKSPACE_REVIEWER",
        "expected_resolution_generation": 0,
    }
    if action in {
        DecisionAction.LINK,
        DecisionAction.ACCEPT_UNMATCHED,
        DecisionAction.REJECT_CANDIDATE,
        DecisionAction.REPLACE,
    }:
        values["authority"] = DecisionAuthority.link("L1", "R1")
        values["reviewed_observation_ids"] = ("OL1", "OR1")
    if action in {DecisionAction.REAFFIRM, DecisionAction.REVOKE, DecisionAction.REPLACE}:
        values["target"] = expected()
    if action is DecisionAction.REAFFIRM:
        values["reviewed_observation_ids"] = ("OL1",)

    with pytest.raises(DomainValidationError, match="reason"):
        DecisionCommand(**values)  # type: ignore[arg-type]


def test_authority_shapes_and_reservation_semantics_are_explicit() -> None:
    link = DecisionAuthority.link("L1", "R1")
    accepted = DecisionAuthority.accept_unmatched("R2", RecordSide.RIGHT)
    rejected = DecisionAuthority.reject_candidate("L2", "R2")

    assert link.endpoint_ids == ("L1", "R1")
    assert accepted.endpoint_ids == ("R2",)
    assert rejected.endpoint_ids == ("L2", "R2")
    assert link.reserves_endpoints
    assert accepted.reserves_endpoints
    assert not rejected.reserves_endpoints

    with pytest.raises(DomainValidationError, match="single endpoint"):
        DecisionAuthority(
            DecisionAuthorityKind.LINK,
            left_id="L1",
            right_id="R1",
            record_id="L2",
        )
    with pytest.raises(DomainValidationError, match="pair endpoints"):
        DecisionAuthority(
            DecisionAuthorityKind.ACCEPT_UNMATCHED,
            left_id="L1",
            right_id="R1",
        )
    with pytest.raises(DomainValidationError, match="record_side"):
        DecisionAuthority.accept_unmatched("L1", "LEFT")  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("action", "authority"),
    [
        (DecisionAction.LINK, DecisionAuthority.reject_candidate("L1", "R1")),
        (
            DecisionAction.ACCEPT_UNMATCHED,
            DecisionAuthority.link("L1", "R1"),
        ),
        (
            DecisionAction.REJECT_CANDIDATE,
            DecisionAuthority.accept_unmatched("L1", RecordSide.LEFT),
        ),
    ],
)
def test_initial_actions_reject_incompatible_authority(
    action: DecisionAction, authority: DecisionAuthority
) -> None:
    with pytest.raises(DomainValidationError, match="requires"):
        DecisionCommand(
            action=action,
            authority=authority,
            reason="Because",
            actor="WORKSPACE_REVIEWER",
            expected_resolution_generation=0,
            reviewed_observation_ids=authority.endpoint_ids,
        )


def test_commands_require_reviewed_baseline_cardinality() -> None:
    with pytest.raises(DomainValidationError, match="2 reviewed"):
        DecisionCommand(
            action=DecisionAction.LINK,
            authority=DecisionAuthority.link("L1", "R1"),
            reason="Because",
            actor="WORKSPACE_REVIEWER",
            expected_resolution_generation=0,
            reviewed_observation_ids=("OL1",),
        )
    with pytest.raises(DomainValidationError, match="unique"):
        DecisionCommand(
            action=DecisionAction.LINK,
            authority=DecisionAuthority.link("L1", "R1"),
            reason="Because",
            actor="WORKSPACE_REVIEWER",
            expected_resolution_generation=0,
            reviewed_observation_ids=("O1", "O1"),
        )


def test_reaffirm_revoke_and_replace_have_distinct_shapes() -> None:
    reaffirm = DecisionCommand(
        action=DecisionAction.REAFFIRM,
        target=expected(),
        reason="Reviewed the corrected values",
        actor="WORKSPACE_REVIEWER",
        expected_resolution_generation=2,
        reviewed_observation_ids=("O2", "O1"),
    )
    revoke = DecisionCommand(
        action=DecisionAction.REVOKE,
        target=expected(),
        reason="The earlier authority no longer applies",
        actor="WORKSPACE_REVIEWER",
        expected_resolution_generation=3,
    )
    replace = DecisionCommand(
        action=DecisionAction.REPLACE,
        target=expected(),
        authority=DecisionAuthority.link("L1", "R2"),
        approved_conflicts=(expected("D3", "R3"), expected("D2", "R2")),
        reason="The source confirms a different counterpart",
        actor="WORKSPACE_REVIEWER",
        expected_resolution_generation=4,
        reviewed_observation_ids=("OL1", "OR2"),
    )

    assert reaffirm.reviewed_observation_ids == ("O1", "O2")
    assert revoke.authority is None
    assert [item.decision_id for item in replace.approved_conflicts] == ["D2", "D3"]

    with pytest.raises(DomainValidationError, match="fresh reviewed"):
        DecisionCommand(
            action=DecisionAction.REAFFIRM,
            target=expected(),
            reason="Because",
            actor="WORKSPACE_REVIEWER",
            expected_resolution_generation=0,
        )
    with pytest.raises(DomainValidationError, match="no authority"):
        DecisionCommand(
            action=DecisionAction.REVOKE,
            target=expected(),
            authority=DecisionAuthority.link("L1", "R1"),
            reason="Because",
            actor="WORKSPACE_REVIEWER",
            expected_resolution_generation=0,
        )


def test_replacement_conflicts_are_complete_canonical_expected_revisions() -> None:
    preview = ReplacementPreview(
        authority=DecisionAuthority.link("L1", "R3"),
        target=expected("D1", "R1"),
        conflicts=(
            DecisionConflict("D3", "R3", ("R3", "L7")),
            DecisionConflict("D2", "R2", ("L1",)),
        ),
        resolution_generation=8,
    )

    assert preview.expected_conflicts == (
        expected("D2", "R2"),
        expected("D3", "R3"),
    )
    assert preview.conflicts[1].claimed_record_ids == ("L7", "R3")

    with pytest.raises(DomainValidationError, match="each conflicting decision"):
        ReplacementPreview(
            authority=preview.authority,
            target=preview.target,
            conflicts=(
                DecisionConflict("D2", "R2", ("L1",)),
                DecisionConflict("D2", "R4", ("R3",)),
            ),
            resolution_generation=8,
        )


def test_expected_versions_and_conflicts_reject_ambiguous_values() -> None:
    with pytest.raises(DomainValidationError, match="nonnegative"):
        DecisionCommand(
            action=DecisionAction.REVOKE,
            target=expected(),
            reason="Because",
            actor="WORKSPACE_REVIEWER",
            expected_resolution_generation=-1,
        )
    with pytest.raises(DomainValidationError, match="each affected decision"):
        ReviewConflict(
            ReviewConflictCode.CONFLICT_SET_CHANGED,
            "The replacement preview is stale",
            (expected("D1", "R1"), expected("D1", "R2")),
        )


def test_health_is_exact_separate_vocabulary_with_canonical_attention() -> None:
    assert {item.value for item in DecisionHealth} == {
        "UNCHANGED",
        "EVIDENCE_CHANGED",
        "PARTNER_UNAVAILABLE",
        "NEW_CANDIDATE",
    }
    projection = DecisionHealthProjection(
        decision_id="D1",
        revision_id="R1",
        run_id="RUN2",
        health=DecisionHealth.EVIDENCE_CHANGED,
        attention=(
            DecisionAttention.DIAGNOSTIC_INCOMPLETE,
            DecisionAttention.COMPARISON_CHANGED,
        ),
    )

    assert projection.attention == (
        DecisionAttention.COMPARISON_CHANGED,
        DecisionAttention.DIAGNOSTIC_INCOMPLETE,
    )
    with pytest.raises(DomainValidationError, match="DecisionHealth"):
        DecisionHealthProjection("D1", "R1", "RUN2", "UNCHANGED")  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("evidence", "health", "attention"),
    [
        (
            DecisionHealthEvidence(DecisionAuthorityKind.LINK, True, False),
            DecisionHealth.UNCHANGED,
            (),
        ),
        (
            DecisionHealthEvidence(
                DecisionAuthorityKind.LINK,
                True,
                True,
                comparison_changed=True,
            ),
            DecisionHealth.EVIDENCE_CHANGED,
            (DecisionAttention.COMPARISON_CHANGED,),
        ),
        (
            DecisionHealthEvidence(DecisionAuthorityKind.LINK, False, True),
            DecisionHealth.PARTNER_UNAVAILABLE,
            (),
        ),
        (
            DecisionHealthEvidence(
                DecisionAuthorityKind.ACCEPT_UNMATCHED,
                True,
                True,
                new_candidate=True,
            ),
            DecisionHealth.NEW_CANDIDATE,
            (),
        ),
        (
            DecisionHealthEvidence(
                DecisionAuthorityKind.ACCEPT_UNMATCHED,
                True,
                False,
                diagnostic_complete=False,
            ),
            DecisionHealth.UNCHANGED,
            (DecisionAttention.DIAGNOSTIC_INCOMPLETE,),
        ),
        (
            DecisionHealthEvidence(
                DecisionAuthorityKind.REJECT_CANDIDATE,
                True,
                True,
                authoritative_reference_conflict=True,
            ),
            DecisionHealth.EVIDENCE_CHANGED,
            (DecisionAttention.AUTHORITATIVE_REFERENCE_CONFLICT,),
        ),
    ],
)
def test_health_projection_has_explicit_precedence_and_separate_attention(
    evidence: DecisionHealthEvidence,
    health: DecisionHealth,
    attention: tuple[DecisionAttention, ...],
) -> None:
    projected = project_decision_health(
        decision_id="D1",
        revision_id="R1",
        run_id="RUN1",
        evidence=evidence,
    )
    assert projected.health is health
    assert projected.attention == attention


def test_pair_and_unpaired_keys_use_stable_logical_identity_and_side() -> None:
    pair = pair_case_key(book_id="B1", left_id="L1", right_id="R1")
    same = pair_case_key(book_id="B1", left_id="L1", right_id="R1")

    assert CASE_KEY_VERSION == "stable-case-key-v1"
    assert pair == same
    assert str(pair).startswith("pair:")
    assert pair != pair_case_key(book_id="B1", left_id="L2", right_id="R1")
    assert pair != pair_case_key(book_id="B1", left_id="R1", right_id="L1")
    assert unpaired_case_key(
        book_id="B1", side=RecordSide.LEFT, record_id="X1"
    ) != unpaired_case_key(
        book_id="B1", side=RecordSide.RIGHT, record_id="X1"
    )


def test_ambiguity_key_is_order_independent_but_member_policy_and_scope_sensitive() -> None:
    key = ambiguity_case_key(
        book_id="B1",
        scope_id="S1",
        policy_digest=POLICY_DIGEST,
        left_ids=("L2", "L1"),
        right_ids=("R2", "R1"),
    )
    reordered = ambiguity_case_key(
        book_id="B1",
        scope_id="S1",
        policy_digest=POLICY_DIGEST,
        left_ids=("L1", "L2"),
        right_ids=("R1", "R2"),
    )

    assert key == reordered
    assert str(key).startswith("ambiguity:")
    assert key != ambiguity_case_key(
        book_id="B1",
        scope_id="S1",
        policy_digest=POLICY_DIGEST,
        left_ids=("L1", "L2", "L3"),
        right_ids=("R1", "R2"),
    )
    assert key != ambiguity_case_key(
        book_id="B1",
        scope_id="S2",
        policy_digest=POLICY_DIGEST,
        left_ids=("L1", "L2"),
        right_ids=("R1", "R2"),
    )
    assert key != ambiguity_case_key(
        book_id="B1",
        scope_id="S1",
        policy_digest="2" * 64,
        left_ids=("L1", "L2"),
        right_ids=("R1", "R2"),
    )

    with pytest.raises(DomainValidationError, match="unique"):
        ambiguity_case_key(
            book_id="B1",
            scope_id="S1",
            policy_digest=POLICY_DIGEST,
            left_ids=("L1", "L1"),
            right_ids=("R1",),
        )
    with pytest.raises(DomainValidationError, match="both sides"):
        ambiguity_case_key(
            book_id="B1",
            scope_id="S1",
            policy_digest=POLICY_DIGEST,
            left_ids=("L1",),
            right_ids=(),
        )


def test_case_key_vectors_are_fixed_for_cross_process_persistence() -> None:
    assert str(pair_case_key(book_id="B1", left_id="L1", right_id="R1")) == (
        "pair:3b240f5dcff6118f57187c5fb1d7c6e9fbbe3d88e42864db072d18ee1518888d"
    )
    assert str(
        unpaired_case_key(book_id="B1", side=RecordSide.LEFT, record_id="L1")
    ) == "unpaired:447604f540f372bbe760079086117d8780249f99435df2bd4049f140383d4c24"
    assert str(
        ambiguity_case_key(
            book_id="B1",
            scope_id="S1",
            policy_digest=POLICY_DIGEST,
            left_ids=("L2", "L1"),
            right_ids=("R2", "R1"),
        )
    ) == "ambiguity:67765459c8ca0f0510e045688096cb62f45d7ee34a9c8397fa4c1cb21647bfa8"


def test_occurrences_must_reference_same_kind_as_stable_case() -> None:
    pair = pair_case_key(book_id="B1", left_id="L1", right_id="R1")
    occurrence = CaseOccurrenceDescriptor(
        case_key=pair,
        run_id="RUN1",
        result_kind=CaseResultKind.PAIR,
        result_id="PAIR1",
    )
    assert occurrence.case_key == pair

    with pytest.raises(DomainValidationError, match="must match"):
        CaseOccurrenceDescriptor(
            case_key=pair,
            run_id="RUN1",
            result_kind=CaseResultKind.UNPAIRED,
            result_id="U1",
        )


def test_lineage_plan_is_canonical_many_to_many_and_rejects_self_edges() -> None:
    first = unpaired_case_key(book_id="B1", side=RecordSide.LEFT, record_id="L1")
    second = unpaired_case_key(book_id="B1", side=RecordSide.RIGHT, record_id="R1")
    pair = pair_case_key(book_id="B1", left_id="L1", right_id="R1")
    plan = CaseTransitionPlan(
        (
            CaseLineageEdge(second, pair),
            CaseLineageEdge(first, pair),
        )
    )

    assert len(plan.edges) == 2
    assert {edge.predecessor for edge in plan.edges} == {first, second}
    with pytest.raises(DomainValidationError, match="self-edge"):
        CaseLineageEdge(pair, pair)
    with pytest.raises(DomainValidationError, match="unique"):
        CaseTransitionPlan((plan.edges[0], plan.edges[0]))


def test_case_key_rejects_non_sha256_digest() -> None:
    with pytest.raises(DomainValidationError, match="SHA-256"):
        CaseKey(CaseKind.PAIR, "xyz")
