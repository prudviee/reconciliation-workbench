from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from django.db import close_old_connections

from books.models import BookKind, ReconciliationBook, ReconciliationScope
from books.scopes import WorkspaceScopeRepository
from ingestion.models import (
    AttemptState,
    Dataset,
    FileArtifact,
    IngestionAttempt,
    LogicalTransaction,
    RawRow,
    TransactionObservation,
)
from reconciliation.domain import (
    BookId,
    DatasetMode,
    DecisionAction,
    DecisionAuthority,
    DecisionCommand,
    ExpectedDecisionRevision,
    RecordSide,
    ReferenceSemantics,
    ReviewConflictCode,
    WorkspaceId,
)
from reconciliation.querying import (
    ReviewCursorError,
    ReviewPageSizeError,
    ReviewQueryUnavailable,
)
from resolutions.queries import DecisionQueryService
from resolutions.models import ActiveDecisionClaim, Decision, DecisionRevision
from resolutions.models import DecisionSupersession
from resolutions.services import (
    DecisionCommandService,
    DecisionMutationConflict,
    DecisionMutationUnavailable,
    InitialDecisionActionRequired,
)
from sources.models import (
    BookSource,
    MappingRevision,
    SourceContractRevision,
    SourceRole,
    SourceSystem,
)
from workspaces.models import Workspace


NOW = datetime(2026, 9, 7, 20, tzinfo=UTC)


@dataclass(frozen=True, slots=True)
class EvidenceGraph:
    workspace: Workspace
    book: ReconciliationBook
    scope: ReconciliationScope
    left: tuple[LogicalTransaction, ...]
    right: tuple[LogicalTransaction, ...]
    left_observations: tuple[TransactionObservation, ...]
    right_observations: tuple[TransactionObservation, ...]


def create_workspace(label: str) -> Workspace:
    return Workspace.objects.create(
        session_digest=(label.encode().hex() + uuid4().hex * 2)[:64],
        created_at=NOW,
        expires_at=NOW + timedelta(days=7),
    )


def create_graph(
    label: str,
    *,
    left_count: int = 1,
    right_count: int = 2,
) -> EvidenceGraph:
    workspace = create_workspace(label)
    book = ReconciliationBook.objects.create(
        workspace=workspace,
        name=f"{label} book",
        kind=BookKind.USER,
        created_at=NOW,
    )
    left_dataset, left, left_observations = create_side(
        workspace, book, label, SourceRole.LEFT, left_count
    )
    right_dataset, right, right_observations = create_side(
        workspace, book, label, SourceRole.RIGHT, right_count
    )
    scope = WorkspaceScopeRepository(WorkspaceId(workspace.id)).create(
        book_id=BookId(book.id),
        coverage_key="2026-09",
        left_dataset_id=left_dataset.id,
        right_dataset_id=right_dataset.id,
        created_at=NOW,
    )
    ReconciliationScope.objects.filter(id=scope.id).update(is_dirty=False)
    scope.refresh_from_db()
    return EvidenceGraph(
        workspace,
        book,
        scope,
        left,
        right,
        left_observations,
        right_observations,
    )


def create_side(
    workspace: Workspace,
    book: ReconciliationBook,
    label: str,
    role: SourceRole,
    count: int,
) -> tuple[
    Dataset,
    tuple[LogicalTransaction, ...],
    tuple[TransactionObservation, ...],
]:
    suffix = role.value.lower()
    source = SourceSystem.objects.create(
        workspace=workspace,
        name=f"{label}-{suffix}",
        adapter_key=f"{suffix}-v1",
        created_at=NOW,
    )
    book_source = BookSource.objects.create(
        workspace=workspace,
        book=book,
        source=source,
        role=role,
        identity_namespace=f"{label}-{suffix}",
        created_at=NOW,
    )
    mapping = MappingRevision.objects.create(
        workspace=workspace,
        source=source,
        revision=1,
        mapping={"kind": suffix},
        parser_version="parser-v1",
        digest=("1" if role is SourceRole.LEFT else "2") * 64,
        created_at=NOW,
    )
    contract = SourceContractRevision.objects.create(
        workspace=workspace,
        source=source,
        mapping_revision=mapping,
        revision=1,
        mode=DatasetMode.FULL_SNAPSHOT,
        timezone_name="UTC",
        identity_namespace=f"{label}-{suffix}",
        reference_semantics=ReferenceSemantics.TRUSTED_SHARED,
        contract={"kind": suffix},
        digest=("3" if role is SourceRole.LEFT else "4") * 64,
        created_at=NOW,
    )
    dataset = Dataset.objects.create(
        workspace=workspace,
        book_source=book_source,
        coverage_key="2026-09",
        created_at=NOW,
    )
    artifact = FileArtifact.objects.create(
        workspace=workspace,
        storage_key=f"{uuid4()}.csv",
        physical_hash="5" * 64,
        original_filename=f"{suffix}.csv",
        content_type="text/csv",
        byte_size=1,
        created_at=NOW,
    )
    attempt = IngestionAttempt.objects.create(
        workspace=workspace,
        artifact=artifact,
        dataset=dataset,
        contract_revision=contract,
        state=AttemptState.ACTIVATED,
        physical_hash=artifact.physical_hash,
        semantic_hash="6" * 64,
        delimiter=",",
        row_count=count,
        error_count=0,
        validation=[],
        created_at=NOW,
        completed_at=NOW,
    )
    logicals = []
    observations = []
    for index in range(1, count + 1):
        raw = RawRow.objects.create(
            workspace=workspace,
            attempt=attempt,
            row_number=index,
            raw_values={"id": f"{suffix}-{index}"},
            canonical_preview={"complete": True},
            validation=[],
        )
        logical = LogicalTransaction.objects.create(
            workspace=workspace,
            book_source=book_source,
            source_record_key=f"{label}-{suffix}-{index}",
            created_at=NOW,
        )
        observation = TransactionObservation.objects.create(
            workspace=workspace,
            logical_transaction=logical,
            raw_row=raw,
            business_reference=f"REF-{index}",
            executed_at_utc=NOW,
            instrument="BTC-USD",
            side="BUY",
            quantity=Decimal("1"),
            unit_price=Decimal("100"),
            gross_amount=Decimal("100"),
            currency="USD",
            state="SETTLED",
            eligible_for_matching=True,
            provenance={},
            fingerprint=("7" if role is SourceRole.LEFT else str(7 + index)) * 64,
            created_at=NOW,
        )
        logicals.append(logical)
        observations.append(observation)
    return dataset, tuple(logicals), tuple(observations)


def command(
    graph: EvidenceGraph,
    *,
    action: DecisionAction,
    authority: DecisionAuthority,
    observations: tuple[TransactionObservation, ...],
    generation: int,
) -> DecisionCommand:
    return DecisionCommand(
        action=action,
        authority=authority,
        reason="  Reviewed against source evidence  ",
        actor="  WORKSPACE_REVIEWER  ",
        expected_resolution_generation=generation,
        reviewed_observation_ids=tuple(str(item.id) for item in observations),
    )


def target(revision: DecisionRevision) -> ExpectedDecisionRevision:
    return ExpectedDecisionRevision(str(revision.decision_id), str(revision.id))


@pytest.mark.django_db
def test_link_commits_revision_claims_generation_and_scope_dirtying_atomically() -> None:
    graph = create_graph("link")
    request = command(
        graph,
        action=DecisionAction.LINK,
        authority=DecisionAuthority.link(
            str(graph.left[0].id), str(graph.right[0].id)
        ),
        observations=(graph.left_observations[0], graph.right_observations[0]),
        generation=0,
    )

    revision = DecisionCommandService(clock=lambda: NOW).commit_initial(
        WorkspaceId(graph.workspace.id),
        book_id=BookId(graph.book.id),
        command=request,
    )

    graph.book.refresh_from_db()
    graph.scope.refresh_from_db()
    decision = Decision.objects.get(id=revision.decision_id)
    claims = list(
        ActiveDecisionClaim.objects.filter(decision_revision=revision).order_by(
            "logical_transaction_id"
        )
    )
    assert decision.current_revision_id == revision.id
    assert revision.reason == "Reviewed against source evidence"
    assert revision.actor == "WORKSPACE_REVIEWER"
    assert len(revision.reviewed_evidence_digest) == 64
    assert {item.logical_transaction_id for item in claims} == {
        graph.left[0].id,
        graph.right[0].id,
    }
    assert graph.book.generation == 0
    assert graph.book.resolution_generation == 1
    assert graph.scope.is_dirty
    assert graph.scope.generation == 1


@pytest.mark.django_db
def test_rejection_creates_no_claim_and_accept_unmatched_creates_one() -> None:
    graph = create_graph("shapes")
    service = DecisionCommandService(clock=lambda: NOW)
    rejection = service.commit_initial(
        WorkspaceId(graph.workspace.id),
        book_id=BookId(graph.book.id),
        command=command(
            graph,
            action=DecisionAction.REJECT_CANDIDATE,
            authority=DecisionAuthority.reject_candidate(
                str(graph.left[0].id), str(graph.right[0].id)
            ),
            observations=(graph.left_observations[0], graph.right_observations[0]),
            generation=0,
        ),
    )
    accepted = service.commit_initial(
        WorkspaceId(graph.workspace.id),
        book_id=BookId(graph.book.id),
        command=command(
            graph,
            action=DecisionAction.ACCEPT_UNMATCHED,
            authority=DecisionAuthority.accept_unmatched(
                str(graph.left[0].id), RecordSide.LEFT
            ),
            observations=(graph.left_observations[0],),
            generation=1,
        ),
    )

    graph.book.refresh_from_db()
    assert rejection.active_claims.count() == 0
    assert list(
        accepted.active_claims.values_list("logical_transaction_id", flat=True)
    ) == [graph.left[0].id]
    assert graph.book.resolution_generation == 2


@pytest.mark.django_db
def test_claim_conflict_reports_affected_authority_and_rolls_back() -> None:
    graph = create_graph("conflict")
    service = DecisionCommandService(clock=lambda: NOW)
    accepted = service.commit_initial(
        WorkspaceId(graph.workspace.id),
        book_id=BookId(graph.book.id),
        command=command(
            graph,
            action=DecisionAction.ACCEPT_UNMATCHED,
            authority=DecisionAuthority.accept_unmatched(
                str(graph.left[0].id), RecordSide.LEFT
            ),
            observations=(graph.left_observations[0],),
            generation=0,
        ),
    )

    with pytest.raises(DecisionMutationConflict) as captured:
        service.commit_initial(
            WorkspaceId(graph.workspace.id),
            book_id=BookId(graph.book.id),
            command=command(
                graph,
                action=DecisionAction.LINK,
                authority=DecisionAuthority.link(
                    str(graph.left[0].id), str(graph.right[0].id)
                ),
                observations=(
                    graph.left_observations[0],
                    graph.right_observations[0],
                ),
                generation=1,
            ),
        )

    graph.book.refresh_from_db()
    assert captured.value.conflict.code is ReviewConflictCode.ENDPOINT_CLAIMED
    assert captured.value.conflict.affected[0].decision_id == str(accepted.decision_id)
    assert Decision.objects.count() == 1
    assert DecisionRevision.objects.count() == 1
    assert ActiveDecisionClaim.objects.count() == 1
    assert graph.book.resolution_generation == 1


@pytest.mark.django_db
def test_stale_generation_side_and_foreign_evidence_fail_without_mutation() -> None:
    graph = create_graph("invalid")
    foreign = create_graph("foreign")
    service = DecisionCommandService(clock=lambda: NOW)
    valid_authority = DecisionAuthority.link(
        str(graph.left[0].id), str(graph.right[0].id)
    )
    valid_observations = (graph.left_observations[0], graph.right_observations[0])

    stale = command(
        graph,
        action=DecisionAction.LINK,
        authority=valid_authority,
        observations=valid_observations,
        generation=1,
    )
    with pytest.raises(DecisionMutationConflict) as captured:
        service.commit_initial(
            WorkspaceId(graph.workspace.id),
            book_id=BookId(graph.book.id),
            command=stale,
        )
    assert captured.value.conflict.code is ReviewConflictCode.STALE_GENERATION

    invalid_requests = (
        command(
            graph,
            action=DecisionAction.LINK,
            authority=DecisionAuthority.link(
                str(graph.right[0].id), str(graph.left[0].id)
            ),
            observations=valid_observations,
            generation=0,
        ),
        command(
            graph,
            action=DecisionAction.LINK,
            authority=valid_authority,
            observations=(foreign.left_observations[0], graph.right_observations[0]),
            generation=0,
        ),
        command(
            graph,
            action=DecisionAction.LINK,
            authority=DecisionAuthority.link(
                str(foreign.left[0].id), str(graph.right[0].id)
            ),
            observations=(foreign.left_observations[0], graph.right_observations[0]),
            generation=0,
        ),
    )
    for request in invalid_requests:
        with pytest.raises(DecisionMutationUnavailable):
            service.commit_initial(
                WorkspaceId(graph.workspace.id),
                book_id=BookId(graph.book.id),
                command=request,
            )

    graph.book.refresh_from_db()
    assert Decision.objects.filter(book=graph.book).count() == 0
    assert graph.book.resolution_generation == 0


@pytest.mark.django_db
def test_initial_service_rejects_lifecycle_actions_and_inactive_workspace() -> None:
    graph = create_graph("inactive")
    service = DecisionCommandService(clock=lambda: NOW)
    revoke = DecisionCommand(
        action=DecisionAction.REVOKE,
        target=ExpectedDecisionRevision(str(uuid4()), str(uuid4())),
        reason="No longer valid",
        actor="WORKSPACE_REVIEWER",
        expected_resolution_generation=0,
    )

    with pytest.raises(InitialDecisionActionRequired):
        service.commit_initial(
            WorkspaceId(graph.workspace.id),
            book_id=BookId(graph.book.id),
            command=revoke,
        )

    graph.workspace.state = "REVOKED"
    graph.workspace.revoked_at = NOW
    graph.workspace.save(update_fields=["state", "revoked_at"])
    request = command(
        graph,
        action=DecisionAction.LINK,
        authority=DecisionAuthority.link(
            str(graph.left[0].id), str(graph.right[0].id)
        ),
        observations=(graph.left_observations[0], graph.right_observations[0]),
        generation=0,
    )
    with pytest.raises(DecisionMutationUnavailable):
        service.commit_initial(
            WorkspaceId(graph.workspace.id),
            book_id=BookId(graph.book.id),
            command=request,
        )
    assert Decision.objects.count() == 0


@pytest.mark.django_db(transaction=True)
def test_two_concurrent_links_for_same_endpoint_allow_at_most_one() -> None:
    graph = create_graph("concurrent", right_count=2)
    requests = (
        command(
            graph,
            action=DecisionAction.LINK,
            authority=DecisionAuthority.link(
                str(graph.left[0].id), str(graph.right[0].id)
            ),
            observations=(graph.left_observations[0], graph.right_observations[0]),
            generation=0,
        ),
        command(
            graph,
            action=DecisionAction.LINK,
            authority=DecisionAuthority.link(
                str(graph.left[0].id), str(graph.right[1].id)
            ),
            observations=(graph.left_observations[0], graph.right_observations[1]),
            generation=0,
        ),
    )

    def save(request: DecisionCommand) -> str:
        close_old_connections()
        try:
            DecisionCommandService(clock=lambda: NOW).commit_initial(
                WorkspaceId(graph.workspace.id),
                book_id=BookId(graph.book.id),
                command=request,
            )
            return "saved"
        except DecisionMutationConflict as error:
            return error.conflict.code.value
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(save, requests))

    graph.book.refresh_from_db()
    assert results.count("saved") == 1
    assert len(results) == 2
    assert Decision.objects.count() == 1
    assert DecisionRevision.objects.count() == 1
    assert ActiveDecisionClaim.objects.count() == 2
    assert graph.book.resolution_generation == 1


@pytest.mark.django_db
def test_reaffirm_appends_baseline_and_moves_claims_without_changing_authority() -> None:
    graph = create_graph("reaffirm")
    service = DecisionCommandService(clock=lambda: NOW)
    initial = service.commit_initial(
        WorkspaceId(graph.workspace.id),
        book_id=BookId(graph.book.id),
        command=command(
            graph,
            action=DecisionAction.LINK,
            authority=DecisionAuthority.link(
                str(graph.left[0].id), str(graph.right[0].id)
            ),
            observations=(graph.left_observations[0], graph.right_observations[0]),
            generation=0,
        ),
    )
    reaffirmed = service.commit_change(
        WorkspaceId(graph.workspace.id),
        book_id=BookId(graph.book.id),
        command=DecisionCommand(
            action=DecisionAction.REAFFIRM,
            target=target(initial),
            reason="Reviewed after correction",
            actor="WORKSPACE_REVIEWER",
            expected_resolution_generation=1,
            reviewed_observation_ids=(
                str(graph.right_observations[0].id),
                str(graph.left_observations[0].id),
            ),
        ),
    )

    graph.book.refresh_from_db()
    history = list(
        DecisionRevision.objects.filter(decision_id=initial.decision_id).order_by(
            "revision"
        )
    )
    assert [item.action for item in history] == [
        DecisionAction.LINK,
        DecisionAction.REAFFIRM,
    ]
    assert reaffirmed.predecessor_id == initial.id
    assert reaffirmed.authority_kind == initial.authority_kind
    assert reaffirmed.left_logical_id == initial.left_logical_id
    assert reaffirmed.right_logical_id == initial.right_logical_id
    assert set(
        reaffirmed.active_claims.values_list("logical_transaction_id", flat=True)
    ) == {graph.left[0].id, graph.right[0].id}
    assert initial.active_claims.count() == 0
    assert graph.book.resolution_generation == 2


@pytest.mark.django_db
def test_revoke_releases_claims_but_preserves_original_revision_and_reason() -> None:
    graph = create_graph("revoke")
    service = DecisionCommandService(clock=lambda: NOW)
    initial = service.commit_initial(
        WorkspaceId(graph.workspace.id),
        book_id=BookId(graph.book.id),
        command=command(
            graph,
            action=DecisionAction.ACCEPT_UNMATCHED,
            authority=DecisionAuthority.accept_unmatched(
                str(graph.left[0].id), RecordSide.LEFT
            ),
            observations=(graph.left_observations[0],),
            generation=0,
        ),
    )
    revoked = service.commit_change(
        WorkspaceId(graph.workspace.id),
        book_id=BookId(graph.book.id),
        command=DecisionCommand(
            action=DecisionAction.REVOKE,
            target=target(initial),
            reason="Source owner withdrew the exception",
            actor="WORKSPACE_REVIEWER",
            expected_resolution_generation=1,
        ),
    )

    graph.book.refresh_from_db()
    decision = Decision.objects.get(id=initial.decision_id)
    initial.refresh_from_db()
    assert decision.current_revision_id == revoked.id
    assert revoked.predecessor_id == initial.id
    assert revoked.action == DecisionAction.REVOKE
    assert revoked.authority_kind is None
    assert ActiveDecisionClaim.objects.filter(book=graph.book).count() == 0
    assert initial.reason == "Reviewed against source evidence"
    assert revoked.reason == "Source owner withdrew the exception"
    assert graph.book.resolution_generation == 2

    with pytest.raises(DecisionMutationConflict) as captured:
        service.commit_change(
            WorkspaceId(graph.workspace.id),
            book_id=BookId(graph.book.id),
            command=DecisionCommand(
                action=DecisionAction.REVOKE,
                target=target(initial),
                reason="Duplicate revoke",
                actor="WORKSPACE_REVIEWER",
                expected_resolution_generation=2,
            ),
        )
    assert captured.value.conflict.code is ReviewConflictCode.STALE_REVISION
    assert DecisionRevision.objects.filter(decision=decision).count() == 2


@pytest.mark.django_db
def test_replacement_preview_shows_full_conflict_and_commit_supersedes_every_authority() -> None:
    graph = create_graph("replace", left_count=2)
    service = DecisionCommandService(clock=lambda: NOW)
    original = service.commit_initial(
        WorkspaceId(graph.workspace.id),
        book_id=BookId(graph.book.id),
        command=command(
            graph,
            action=DecisionAction.LINK,
            authority=DecisionAuthority.link(
                str(graph.left[0].id), str(graph.right[0].id)
            ),
            observations=(graph.left_observations[0], graph.right_observations[0]),
            generation=0,
        ),
    )
    conflicting = service.commit_initial(
        WorkspaceId(graph.workspace.id),
        book_id=BookId(graph.book.id),
        command=command(
            graph,
            action=DecisionAction.LINK,
            authority=DecisionAuthority.link(
                str(graph.left[1].id), str(graph.right[1].id)
            ),
            observations=(graph.left_observations[1], graph.right_observations[1]),
            generation=1,
        ),
    )
    authority = DecisionAuthority.link(
        str(graph.left[0].id), str(graph.right[1].id)
    )

    preview = service.preview_replacement(
        WorkspaceId(graph.workspace.id),
        book_id=BookId(graph.book.id),
        target=target(original),
        authority=authority,
    )

    assert preview.resolution_generation == 2
    assert preview.expected_conflicts == (target(conflicting),)
    assert set(preview.conflicts[0].claimed_record_ids) == {
        str(graph.left[1].id),
        str(graph.right[1].id),
    }

    replacement = service.commit_change(
        WorkspaceId(graph.workspace.id),
        book_id=BookId(graph.book.id),
        command=DecisionCommand(
            action=DecisionAction.REPLACE,
            target=target(original),
            authority=authority,
            approved_conflicts=preview.expected_conflicts,
            reason="Corrected relationship confirmed",
            actor="WORKSPACE_REVIEWER",
            expected_resolution_generation=preview.resolution_generation,
            reviewed_observation_ids=(
                str(graph.left_observations[0].id),
                str(graph.right_observations[1].id),
            ),
        ),
    )

    graph.book.refresh_from_db()
    active_claims = ActiveDecisionClaim.objects.filter(book=graph.book)
    assert set(active_claims.values_list("logical_transaction_id", flat=True)) == {
        graph.left[0].id,
        graph.right[1].id,
    }
    assert set(
        DecisionSupersession.objects.filter(
            replacement_revision=replacement
        ).values_list("superseded_revision_id", flat=True)
    ) == {original.id, conflicting.id}
    assert original.active_claims.count() == 0
    assert conflicting.active_claims.count() == 0
    assert Decision.objects.get(id=original.decision_id).current_revision_id == replacement.id
    assert Decision.objects.get(id=conflicting.decision_id).current_revision_id == conflicting.id
    assert graph.book.resolution_generation == 3

    with pytest.raises(DecisionMutationConflict) as captured:
        service.commit_change(
            WorkspaceId(graph.workspace.id),
            book_id=BookId(graph.book.id),
            command=DecisionCommand(
                action=DecisionAction.REAFFIRM,
                target=target(conflicting),
                reason="Try to revive displaced authority",
                actor="WORKSPACE_REVIEWER",
                expected_resolution_generation=3,
                reviewed_observation_ids=(str(graph.right_observations[1].id),),
            ),
        )
    assert captured.value.conflict.code is ReviewConflictCode.STALE_REVISION


@pytest.mark.django_db
def test_replacement_commit_requires_exact_preview_and_changes_nothing_on_mismatch() -> None:
    graph = create_graph("preview")
    service = DecisionCommandService(clock=lambda: NOW)
    original = service.commit_initial(
        WorkspaceId(graph.workspace.id),
        book_id=BookId(graph.book.id),
        command=command(
            graph,
            action=DecisionAction.LINK,
            authority=DecisionAuthority.link(
                str(graph.left[0].id), str(graph.right[0].id)
            ),
            observations=(graph.left_observations[0], graph.right_observations[0]),
            generation=0,
        ),
    )
    conflicting = service.commit_initial(
        WorkspaceId(graph.workspace.id),
        book_id=BookId(graph.book.id),
        command=command(
            graph,
            action=DecisionAction.ACCEPT_UNMATCHED,
            authority=DecisionAuthority.accept_unmatched(
                str(graph.right[1].id), RecordSide.RIGHT
            ),
            observations=(graph.right_observations[1],),
            generation=1,
        ),
    )
    replacement_authority = DecisionAuthority.link(
        str(graph.left[0].id), str(graph.right[1].id)
    )

    with pytest.raises(DecisionMutationConflict) as captured:
        service.commit_change(
            WorkspaceId(graph.workspace.id),
            book_id=BookId(graph.book.id),
            command=DecisionCommand(
                action=DecisionAction.REPLACE,
                target=target(original),
                authority=replacement_authority,
                approved_conflicts=(),
                reason="Attempt without approving the conflict",
                actor="WORKSPACE_REVIEWER",
                expected_resolution_generation=2,
                reviewed_observation_ids=(
                    str(graph.left_observations[0].id),
                    str(graph.right_observations[1].id),
                ),
            ),
        )

    graph.book.refresh_from_db()
    assert captured.value.conflict.code is ReviewConflictCode.CONFLICT_SET_CHANGED
    assert captured.value.conflict.affected == (target(conflicting),)
    assert graph.book.resolution_generation == 2
    assert DecisionRevision.objects.count() == 2
    assert DecisionSupersession.objects.count() == 0
    assert set(
        ActiveDecisionClaim.objects.filter(book=graph.book).values_list(
            "logical_transaction_id", flat=True
        )
    ) == {graph.left[0].id, graph.right[0].id, graph.right[1].id}


@pytest.mark.django_db
def test_preview_and_lifecycle_changes_reveal_or_mutate_nothing_cross_workspace() -> None:
    owner = create_graph("lifecycle-owner")
    outsider = create_graph("lifecycle-outsider")
    service = DecisionCommandService(clock=lambda: NOW)
    revision = service.commit_initial(
        WorkspaceId(owner.workspace.id),
        book_id=BookId(owner.book.id),
        command=command(
            owner,
            action=DecisionAction.ACCEPT_UNMATCHED,
            authority=DecisionAuthority.accept_unmatched(
                str(owner.left[0].id), RecordSide.LEFT
            ),
            observations=(owner.left_observations[0],),
            generation=0,
        ),
    )

    with pytest.raises(DecisionMutationUnavailable):
        service.preview_replacement(
            WorkspaceId(outsider.workspace.id),
            book_id=BookId(owner.book.id),
            target=target(revision),
            authority=DecisionAuthority.accept_unmatched(
                str(owner.right[0].id), RecordSide.RIGHT
            ),
        )
    with pytest.raises(DecisionMutationUnavailable):
        service.commit_change(
            WorkspaceId(outsider.workspace.id),
            book_id=BookId(owner.book.id),
            command=DecisionCommand(
                action=DecisionAction.REVOKE,
                target=target(revision),
                reason="Foreign mutation",
                actor="WORKSPACE_REVIEWER",
                expected_resolution_generation=1,
            ),
        )

    owner.book.refresh_from_db()
    assert owner.book.resolution_generation == 1
    assert DecisionRevision.objects.filter(decision_id=revision.decision_id).count() == 1
    assert revision.active_claims.count() == 1


@pytest.mark.django_db
def test_decision_query_pages_are_stable_complete_and_bounded(
    django_assert_num_queries,
) -> None:
    graph = create_graph("decision-query-pages")
    commands = DecisionCommandService(clock=lambda: NOW)
    for generation in range(5):
        commands.commit_initial(
            WorkspaceId(graph.workspace.id),
            book_id=BookId(graph.book.id),
            command=command(
                graph,
                action=DecisionAction.REJECT_CANDIDATE,
                authority=DecisionAuthority.reject_candidate(
                    str(graph.left[0].id), str(graph.right[0].id)
                ),
                observations=(
                    graph.left_observations[0],
                    graph.right_observations[0],
                ),
                generation=generation,
            ),
        )

    query = DecisionQueryService(clock=lambda: NOW)
    with django_assert_num_queries(4):
        first = query.list_decisions(
            WorkspaceId(graph.workspace.id),
            book_id=BookId(graph.book.id),
            scope_id=graph.scope.id,
            page_size=2,
        )
    assert first.next_cursor is not None

    seen = list(first.items)
    cursor = first.next_cursor
    while cursor is not None:
        page = query.list_decisions(
            WorkspaceId(graph.workspace.id),
            book_id=BookId(graph.book.id),
            scope_id=graph.scope.id,
            cursor=cursor,
            page_size=2,
        )
        seen.extend(page.items)
        cursor = page.next_cursor

    expected = list(
        Decision.objects.filter(book=graph.book).order_by("created_at", "id")
    )
    assert [item.decision_id for item in seen] == [item.id for item in expected]
    assert len({item.decision_id for item in seen}) == 5
    assert all(item.authority_active for item in seen)
    assert all(item.review_is_pending for item in seen)


@pytest.mark.django_db
def test_decision_query_history_labels_current_revision_and_bounds_queries(
    django_assert_num_queries,
) -> None:
    graph = create_graph("decision-query-history")
    commands = DecisionCommandService(clock=lambda: NOW)
    initial = commands.commit_initial(
        WorkspaceId(graph.workspace.id),
        book_id=BookId(graph.book.id),
        command=command(
            graph,
            action=DecisionAction.LINK,
            authority=DecisionAuthority.link(
                str(graph.left[0].id), str(graph.right[0].id)
            ),
            observations=(graph.left_observations[0], graph.right_observations[0]),
            generation=0,
        ),
    )
    latest = commands.commit_change(
        WorkspaceId(graph.workspace.id),
        book_id=BookId(graph.book.id),
        command=DecisionCommand(
            action=DecisionAction.REAFFIRM,
            target=target(initial),
            reason="Reviewed current evidence",
            actor="WORKSPACE_REVIEWER",
            expected_resolution_generation=1,
            reviewed_observation_ids=(
                str(graph.left_observations[0].id),
                str(graph.right_observations[0].id),
            ),
        ),
    )

    query = DecisionQueryService(clock=lambda: NOW)
    with django_assert_num_queries(5):
        history = query.get_decision_history(
            WorkspaceId(graph.workspace.id),
            book_id=BookId(graph.book.id),
            scope_id=graph.scope.id,
            decision_id=initial.decision_id,
        )

    assert history.current_revision_id == latest.id
    assert [item.timeline_label for item in history.revisions] == [
        "HISTORICAL",
        "CURRENT",
    ]
    assert [item.authority_active for item in history.revisions] == [False, True]


@pytest.mark.django_db
def test_decision_query_exposes_complete_replacement_preview() -> None:
    graph = create_graph("decision-query-preview", left_count=2)
    commands = DecisionCommandService(clock=lambda: NOW)
    original = commands.commit_initial(
        WorkspaceId(graph.workspace.id),
        book_id=BookId(graph.book.id),
        command=command(
            graph,
            action=DecisionAction.LINK,
            authority=DecisionAuthority.link(
                str(graph.left[0].id), str(graph.right[0].id)
            ),
            observations=(graph.left_observations[0], graph.right_observations[0]),
            generation=0,
        ),
    )
    conflict = commands.commit_initial(
        WorkspaceId(graph.workspace.id),
        book_id=BookId(graph.book.id),
        command=command(
            graph,
            action=DecisionAction.ACCEPT_UNMATCHED,
            authority=DecisionAuthority.accept_unmatched(
                str(graph.right[1].id), RecordSide.RIGHT
            ),
            observations=(graph.right_observations[1],),
            generation=1,
        ),
    )

    preview = DecisionQueryService(clock=lambda: NOW).preview_replacement(
        WorkspaceId(graph.workspace.id),
        book_id=BookId(graph.book.id),
        target=target(original),
        authority=DecisionAuthority.link(
            str(graph.left[0].id), str(graph.right[1].id)
        ),
    )

    assert preview.expected_conflicts == (target(conflict),)
    assert preview.resolution_generation == 2
    assert set(preview.conflicts[0].claimed_record_ids) == {
        str(graph.right[1].id)
    }


@pytest.mark.django_db
def test_decision_query_rejects_unbounded_invalid_and_cross_projection_cursors() -> None:
    graph = create_graph("decision-query-cursor")
    query = DecisionQueryService(clock=lambda: NOW)
    for size in (0, 101, True):
        with pytest.raises(ReviewPageSizeError):
            query.list_decisions(
                WorkspaceId(graph.workspace.id),
                book_id=BookId(graph.book.id),
                scope_id=graph.scope.id,
                page_size=size,
            )
    with pytest.raises(ReviewCursorError):
        query.list_decisions(
            WorkspaceId(graph.workspace.id),
            book_id=BookId(graph.book.id),
            scope_id=graph.scope.id,
            cursor="not-a-cursor",
        )


@pytest.mark.django_db
def test_decision_query_foreign_and_absent_ids_share_one_unavailable_result() -> None:
    owner = create_graph("decision-query-owner")
    outsider = create_graph("decision-query-outsider")
    revision = DecisionCommandService(clock=lambda: NOW).commit_initial(
        WorkspaceId(owner.workspace.id),
        book_id=BookId(owner.book.id),
        command=command(
            owner,
            action=DecisionAction.ACCEPT_UNMATCHED,
            authority=DecisionAuthority.accept_unmatched(
                str(owner.left[0].id), RecordSide.LEFT
            ),
            observations=(owner.left_observations[0],),
            generation=0,
        ),
    )
    query = DecisionQueryService(clock=lambda: NOW)
    probes = (
        lambda: query.list_decisions(
            WorkspaceId(outsider.workspace.id),
            book_id=BookId(owner.book.id),
            scope_id=owner.scope.id,
        ),
        lambda: query.list_decisions(
            WorkspaceId(owner.workspace.id),
            book_id=BookId(owner.book.id),
            scope_id=outsider.scope.id,
        ),
        lambda: query.get_decision_history(
            WorkspaceId(outsider.workspace.id),
            book_id=BookId(outsider.book.id),
            scope_id=outsider.scope.id,
            decision_id=revision.decision_id,
        ),
        lambda: query.get_decision_history(
            WorkspaceId(owner.workspace.id),
            book_id=BookId(owner.book.id),
            scope_id=owner.scope.id,
            decision_id=uuid4(),
        ),
    )
    for probe in probes:
        with pytest.raises(ReviewQueryUnavailable):
            probe()

@pytest.mark.django_db
def test_decision_query_covers_absent_context_and_preview_boundaries() -> None:
    owner = create_graph("decision-query-boundary-owner")
    outsider = create_graph("decision-query-boundary-outsider")
    revision = DecisionCommandService(clock=lambda: NOW).commit_initial(
        WorkspaceId(owner.workspace.id),
        book_id=BookId(owner.book.id),
        command=command(
            owner,
            action=DecisionAction.ACCEPT_UNMATCHED,
            authority=DecisionAuthority.accept_unmatched(
                str(owner.left[0].id), RecordSide.LEFT
            ),
            observations=(owner.left_observations[0],),
            generation=0,
        ),
    )
    query = DecisionQueryService(clock=lambda: NOW)
    probes = (
        lambda: query.list_decisions(
            WorkspaceId(owner.workspace.id),
            book_id=BookId(uuid4()),
            scope_id=owner.scope.id,
        ),
        lambda: query.list_decisions(
            WorkspaceId(owner.workspace.id),
            book_id=BookId(owner.book.id),
            scope_id=uuid4(),
        ),
        lambda: query.get_decision_history(
            WorkspaceId(owner.workspace.id),
            book_id=BookId(owner.book.id),
            scope_id=owner.scope.id,
            decision_id="invalid-id",
        ),
        lambda: query.preview_replacement(
            WorkspaceId(outsider.workspace.id),
            book_id=BookId(outsider.book.id),
            target=target(revision),
            authority=DecisionAuthority.accept_unmatched(
                str(outsider.left[0].id), RecordSide.LEFT
            ),
        ),
        lambda: query.preview_replacement(
            WorkspaceId(owner.workspace.id),
            book_id=BookId(owner.book.id),
            target=ExpectedDecisionRevision(str(uuid4()), str(uuid4())),
            authority=DecisionAuthority.accept_unmatched(
                str(owner.left[0].id), RecordSide.LEFT
            ),
        ),
    )
    for probe in probes:
        with pytest.raises(ReviewQueryUnavailable):
            probe()
