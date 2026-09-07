from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from django.db import IntegrityError, connection, transaction

from books.models import BookKind, ReconciliationBook
from ingestion.models import LogicalTransaction
from reconciliation.domain import (
    BookId,
    DecisionAction,
    DecisionAuthorityKind,
    RecordSide,
    WorkspaceId,
)
from resolutions.models import (
    ActiveDecisionClaim,
    Decision,
    DecisionRevision,
    DecisionSupersession,
    ResolutionEvidenceError,
)
from resolutions.repositories import DecisionUnavailable, WorkspaceDecisionRepository
from sources.models import BookSource, SourceRole, SourceSystem
from workspaces.models import Workspace


pytestmark = pytest.mark.django_db
NOW = datetime(2026, 9, 7, 19, tzinfo=UTC)


def create_workspace(label: str) -> Workspace:
    return Workspace.objects.create(
        session_digest=(label.encode().hex() + uuid4().hex * 2)[:64],
        created_at=NOW,
        expires_at=NOW + timedelta(days=7),
    )


def create_book_with_logicals(
    workspace: Workspace,
    label: str,
) -> tuple[ReconciliationBook, LogicalTransaction, LogicalTransaction, LogicalTransaction]:
    book = ReconciliationBook.objects.create(
        workspace=workspace,
        name=f"{label} book",
        kind=BookKind.USER,
        created_at=NOW,
    )
    left_source = SourceSystem.objects.create(
        workspace=workspace,
        name=f"{label} ledger",
        adapter_key="ledger-v1",
        created_at=NOW,
    )
    right_source = SourceSystem.objects.create(
        workspace=workspace,
        name=f"{label} counterparty",
        adapter_key="counterparty-v1",
        created_at=NOW,
    )
    left_book_source = BookSource.objects.create(
        workspace=workspace,
        book=book,
        source=left_source,
        role=SourceRole.LEFT,
        identity_namespace=f"{label}-left",
        created_at=NOW,
    )
    right_book_source = BookSource.objects.create(
        workspace=workspace,
        book=book,
        source=right_source,
        role=SourceRole.RIGHT,
        identity_namespace=f"{label}-right",
        created_at=NOW,
    )
    left = LogicalTransaction.objects.create(
        workspace=workspace,
        book_source=left_book_source,
        source_record_key=f"{label}-L1",
        created_at=NOW,
    )
    right1 = LogicalTransaction.objects.create(
        workspace=workspace,
        book_source=right_book_source,
        source_record_key=f"{label}-R1",
        created_at=NOW,
    )
    right2 = LogicalTransaction.objects.create(
        workspace=workspace,
        book_source=right_book_source,
        source_record_key=f"{label}-R2",
        created_at=NOW,
    )
    return book, left, right1, right2


def create_decision(workspace: Workspace, book: ReconciliationBook) -> Decision:
    return Decision.objects.create(workspace=workspace, book=book, created_at=NOW)


def link_revision(
    decision: Decision,
    left: LogicalTransaction,
    right: LogicalTransaction,
    *,
    revision: int = 1,
    predecessor: DecisionRevision | None = None,
    action: DecisionAction = DecisionAction.LINK,
    reason: str = "The source records identify the same transaction",
) -> DecisionRevision:
    return DecisionRevision.objects.create(
        workspace=decision.workspace,
        decision=decision,
        predecessor=predecessor,
        revision=revision,
        action=action,
        authority_kind=DecisionAuthorityKind.LINK,
        left_logical=left,
        right_logical=right,
        reason=reason,
        actor="WORKSPACE_REVIEWER",
        reviewed_observation_ids=[f"O-{left.id}", f"O-{right.id}"],
        reviewed_evidence_digest="1" * 64,
        created_at=NOW,
    )


def test_decision_history_is_append_only_and_preserves_reasons() -> None:
    workspace = create_workspace("history")
    book, left, right1, right2 = create_book_with_logicals(workspace, "history")
    decision = create_decision(workspace, book)
    initial = link_revision(
        decision,
        left,
        right1,
        reason="Initial operations evidence",
    )
    replacement = link_revision(
        decision,
        left,
        right2,
        revision=2,
        predecessor=initial,
        action=DecisionAction.REPLACE,
        reason="Corrected counterparty identity",
    )
    Decision.objects.filter(id=decision.id).update(current_revision=replacement)

    history = WorkspaceDecisionRepository(WorkspaceId(workspace.id)).history(
        BookId(book.id), decision.id
    )

    assert [(item.action, item.reason) for item in history] == [
        (DecisionAction.LINK, "Initial operations evidence"),
        (DecisionAction.REPLACE, "Corrected counterparty identity"),
    ]
    assert history[1].predecessor_id == history[0].id
    initial.reason = "rewritten"
    with pytest.raises(ResolutionEvidenceError):
        initial.save()
    with pytest.raises(ResolutionEvidenceError):
        DecisionRevision.objects.filter(id=initial.id).update(reason="rewritten")
    with pytest.raises(ResolutionEvidenceError):
        initial.delete()


def test_predecessor_chain_cannot_branch() -> None:
    workspace = create_workspace("chain")
    book, left, right1, right2 = create_book_with_logicals(workspace, "chain")
    decision = create_decision(workspace, book)
    initial = link_revision(decision, left, right1)
    link_revision(
        decision,
        left,
        right2,
        revision=2,
        predecessor=initial,
        action=DecisionAction.REPLACE,
    )

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            link_revision(
                decision,
                left,
                right1,
                revision=3,
                predecessor=initial,
                action=DecisionAction.REAFFIRM,
            )


def test_database_authority_shape_and_action_constraints_reject_invalid_rows() -> None:
    workspace = create_workspace("shape")
    book, left, right1, _ = create_book_with_logicals(workspace, "shape")
    invalid = (
        {
            "action": DecisionAction.LINK,
            "authority_kind": DecisionAuthorityKind.LINK,
            "left_logical": left,
        },
        {
            "action": DecisionAction.LINK,
            "authority_kind": DecisionAuthorityKind.REJECT_CANDIDATE,
            "left_logical": left,
            "right_logical": right1,
        },
        {
            "action": DecisionAction.REVOKE,
            "authority_kind": DecisionAuthorityKind.LINK,
            "left_logical": left,
            "right_logical": right1,
        },
        {
            "action": DecisionAction.LINK,
            "authority_kind": DecisionAuthorityKind.LINK,
            "left_logical": left,
            "right_logical": left,
        },
    )
    for index, overrides in enumerate(invalid, start=1):
        decision = create_decision(workspace, book)
        values = {
            "workspace": workspace,
            "decision": decision,
            "revision": 1,
            "reason": f"Invalid fixture {index}",
            "actor": "WORKSPACE_REVIEWER",
            "reviewed_observation_ids": [],
            "created_at": NOW,
            **overrides,
        }
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                DecisionRevision.objects.create(**values)

    for field in ("reason", "actor"):
        decision = create_decision(workspace, book)
        values = {
            "workspace": workspace,
            "decision": decision,
            "revision": 1,
            "action": DecisionAction.LINK,
            "authority_kind": DecisionAuthorityKind.LINK,
            "left_logical": left,
            "right_logical": right1,
            "reason": "Reason",
            "actor": "WORKSPACE_REVIEWER",
            "reviewed_observation_ids": [],
            "created_at": NOW,
        }
        values[field] = ""
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                DecisionRevision.objects.create(**values)


def test_active_claim_database_uniqueness_prevents_endpoint_reuse_in_book() -> None:
    workspace = create_workspace("claims")
    book, left, right1, right2 = create_book_with_logicals(workspace, "claims")
    first_decision = create_decision(workspace, book)
    first_revision = link_revision(first_decision, left, right1)
    ActiveDecisionClaim.objects.bulk_create(
        [
            ActiveDecisionClaim(
                workspace=workspace,
                book=book,
                logical_transaction=left,
                decision_revision=first_revision,
            ),
            ActiveDecisionClaim(
                workspace=workspace,
                book=book,
                logical_transaction=right1,
                decision_revision=first_revision,
            ),
        ]
    )
    second_decision = create_decision(workspace, book)
    second_revision = DecisionRevision.objects.create(
        workspace=workspace,
        decision=second_decision,
        revision=1,
        action=DecisionAction.ACCEPT_UNMATCHED,
        authority_kind=DecisionAuthorityKind.ACCEPT_UNMATCHED,
        record_logical=right1,
        record_side=RecordSide.RIGHT,
        reason="No counterpart is expected",
        actor="WORKSPACE_REVIEWER",
        reviewed_observation_ids=[f"O-{right1.id}"],
        reviewed_evidence_digest="2" * 64,
        created_at=NOW,
    )

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            ActiveDecisionClaim.objects.create(
                workspace=workspace,
                book=book,
                logical_transaction=right1,
                decision_revision=second_revision,
            )

    rejection = DecisionRevision.objects.create(
        workspace=workspace,
        decision=create_decision(workspace, book),
        revision=1,
        action=DecisionAction.REJECT_CANDIDATE,
        authority_kind=DecisionAuthorityKind.REJECT_CANDIDATE,
        left_logical=left,
        right_logical=right2,
        reason="This relationship is contradicted by source evidence",
        actor="WORKSPACE_REVIEWER",
        reviewed_observation_ids=[f"O-{left.id}", f"O-{right2.id}"],
        reviewed_evidence_digest="3" * 64,
        created_at=NOW,
    )
    assert rejection.active_claims.count() == 0
    assert ActiveDecisionClaim.objects.count() == 2


def test_replacement_can_preserve_every_superseded_authority() -> None:
    workspace = create_workspace("supersession")
    book, left, right1, right2 = create_book_with_logicals(
        workspace, "supersession"
    )
    replacing_decision = create_decision(workspace, book)
    initial = link_revision(replacing_decision, left, right1)
    replacement = link_revision(
        replacing_decision,
        left,
        right2,
        revision=2,
        predecessor=initial,
        action=DecisionAction.REPLACE,
    )
    conflicting_decision = create_decision(workspace, book)
    conflict = DecisionRevision.objects.create(
        workspace=workspace,
        decision=conflicting_decision,
        revision=1,
        action=DecisionAction.ACCEPT_UNMATCHED,
        authority_kind=DecisionAuthorityKind.ACCEPT_UNMATCHED,
        record_logical=right2,
        record_side=RecordSide.RIGHT,
        reason="Earlier unmatched authority",
        actor="WORKSPACE_REVIEWER",
        reviewed_observation_ids=[f"O-{right2.id}"],
        reviewed_evidence_digest="2" * 64,
        created_at=NOW,
    )
    edges = DecisionSupersession.objects.bulk_create(
        [
            DecisionSupersession(
                workspace=workspace,
                replacement_revision=replacement,
                superseded_revision=initial,
                created_at=NOW,
            ),
            DecisionSupersession(
                workspace=workspace,
                replacement_revision=replacement,
                superseded_revision=conflict,
                created_at=NOW,
            ),
        ]
    )

    assert {item.superseded_revision_id for item in edges} == {
        initial.id,
        conflict.id,
    }
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            DecisionSupersession.objects.create(
                workspace=workspace,
                replacement_revision=replacement,
                superseded_revision=replacement,
                created_at=NOW,
            )
    with pytest.raises(ResolutionEvidenceError):
        edges[0].delete()


def test_repository_constrains_decision_revision_history_and_claims_to_book() -> None:
    owner = create_workspace("repo-owner")
    outsider = create_workspace("repo-outsider")
    owner_book, left, right1, _ = create_book_with_logicals(owner, "repo-owner")
    second_book, _, _, _ = create_book_with_logicals(owner, "repo-second")
    decision = create_decision(owner, owner_book)
    revision = link_revision(decision, left, right1)
    Decision.objects.filter(id=decision.id).update(current_revision=revision)
    ActiveDecisionClaim.objects.create(
        workspace=owner,
        book=owner_book,
        logical_transaction=left,
        decision_revision=revision,
    )
    repository = WorkspaceDecisionRepository(WorkspaceId(owner.id))

    assert repository.get(BookId(owner_book.id), decision.id).id == decision.id
    assert repository.get_revision(BookId(owner_book.id), revision.id).id == revision.id
    assert len(repository.claims(BookId(owner_book.id))) == 1

    for book_id, workspace_id in (
        (BookId(second_book.id), WorkspaceId(owner.id)),
        (BookId(owner_book.id), WorkspaceId(outsider.id)),
    ):
        scoped = WorkspaceDecisionRepository(workspace_id)
        with pytest.raises(DecisionUnavailable):
            scoped.get(book_id, decision.id)
        with pytest.raises(DecisionUnavailable):
            scoped.get_revision(book_id, revision.id)
        with pytest.raises(DecisionUnavailable):
            scoped.history(book_id, decision.id)


def test_resolution_schema_has_required_named_constraints() -> None:
    expected = {
        "decision_revision": {
            "decision_revision_number_unique",
            "decision_predecessor_successor_unique",
            "decision_authority_shape_valid",
            "decision_action_authority_valid",
            "decision_pair_endpoints_distinct",
        },
        "active_decision_claim": {
            "active_claim_book_logical_unique",
            "active_claim_revision_logical_unique",
        },
        "decision_supersession": {
            "decision_supersession_unique",
            "decision_supersession_not_self",
        },
    }
    with connection.cursor() as cursor:
        for table, names in expected.items():
            actual = connection.introspection.get_constraints(cursor, table)
            assert names <= set(actual)
