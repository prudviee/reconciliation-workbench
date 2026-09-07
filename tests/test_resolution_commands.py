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
from resolutions.models import ActiveDecisionClaim, Decision, DecisionRevision
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


def create_graph(label: str, *, right_count: int = 2) -> EvidenceGraph:
    workspace = create_workspace(label)
    book = ReconciliationBook.objects.create(
        workspace=workspace,
        name=f"{label} book",
        kind=BookKind.USER,
        created_at=NOW,
    )
    left_dataset, left, left_observations = create_side(
        workspace, book, label, SourceRole.LEFT, 1
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
