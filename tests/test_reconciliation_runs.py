from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from django.db.models import F

from books.models import BookKind, PolicyRevision, ReconciliationBook, ReconciliationScope
from books.scopes import WorkspaceScopeRepository
from ingestion.models import (
    AttemptState,
    Dataset,
    DatasetMembership,
    DatasetRevision,
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
    MatchingPolicy,
    ComparisonPolicy,
    PairOrigin,
    RecordSide,
    ReferenceSemantics,
    WorkspaceId,
    policy_revision_digest,
)
from reconciliation.models import (
    FieldComparison,
    ReconciliationRun,
    RunEvidenceError,
    RunFreshness,
    RunInput,
    RunLifecycle,
)
from reconciliation.policies import comparison_policy_to_payload, matching_policy_to_payload
from reconciliation.services import ReconciliationRunService, RunUnavailable
from resolutions.services import DecisionCommandService
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
class RunGraph:
    workspace: Workspace
    book: ReconciliationBook
    scope: ReconciliationScope
    left: LogicalTransaction
    right: LogicalTransaction
    left_observation: TransactionObservation
    right_observation: TransactionObservation


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def create_graph(label: str, *, reference: str | None = "SHARED-1") -> RunGraph:
    workspace = Workspace.objects.create(
        session_digest=_digest(f"session-{label}-{uuid4()}"),
        created_at=NOW,
        expires_at=NOW + timedelta(days=7),
    )
    book = ReconciliationBook.objects.create(
        workspace=workspace,
        name=f"{label} book",
        kind=BookKind.USER,
        created_at=NOW,
    )
    left_dataset, left, left_observation = create_side(workspace, book, label, SourceRole.LEFT, reference)
    right_dataset, right, right_observation = create_side(workspace, book, label, SourceRole.RIGHT, reference)
    scope = WorkspaceScopeRepository(WorkspaceId(workspace.id)).create(
        book_id=BookId(book.id),
        coverage_key="2026-09",
        left_dataset_id=left_dataset.id,
        right_dataset_id=right_dataset.id,
        created_at=NOW,
    )
    matching = matching_policy_to_payload(MatchingPolicy.initial_demo())
    comparison = comparison_policy_to_payload(ComparisonPolicy.initial_demo())
    PolicyRevision.objects.create(
        workspace=workspace,
        book=book,
        revision=1,
        matching_policy=matching,
        comparison_policy=comparison,
        digest=policy_revision_digest(matching_policy=matching, comparison_policy=comparison),
        created_at=NOW,
    )
    return RunGraph(workspace, book, scope, left, right, left_observation, right_observation)


def create_side(
    workspace: Workspace,
    book: ReconciliationBook,
    label: str,
    role: SourceRole,
    reference: str | None,
) -> tuple[Dataset, LogicalTransaction, TransactionObservation]:
    side = role.value.lower()
    source = SourceSystem.objects.create(
        workspace=workspace,
        name=f"{label}-{side}",
        adapter_key=f"{side}-v1",
        created_at=NOW,
    )
    book_source = BookSource.objects.create(
        workspace=workspace,
        book=book,
        source=source,
        role=role,
        identity_namespace=f"{label}-{side}",
        created_at=NOW,
    )
    mapping = MappingRevision.objects.create(
        workspace=workspace,
        source=source,
        revision=1,
        mapping={"side": side},
        parser_version="parser-v1",
        digest=_digest(f"mapping-{label}-{side}"),
        created_at=NOW,
    )
    contract = SourceContractRevision.objects.create(
        workspace=workspace,
        source=source,
        mapping_revision=mapping,
        revision=1,
        mode=DatasetMode.FULL_SNAPSHOT,
        timezone_name="UTC",
        identity_namespace=f"{label}-{side}",
        reference_semantics=ReferenceSemantics.TRUSTED_SHARED,
        contract={"side": side},
        digest=_digest(f"contract-{label}-{side}"),
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
        physical_hash=_digest(f"artifact-{label}-{side}"),
        original_filename=f"{side}.csv",
        content_type="text/csv",
        byte_size=10,
        created_at=NOW,
    )
    attempt = IngestionAttempt.objects.create(
        workspace=workspace,
        artifact=artifact,
        dataset=dataset,
        contract_revision=contract,
        state=AttemptState.ACTIVATED,
        physical_hash=artifact.physical_hash,
        semantic_hash=_digest(f"semantic-{label}-{side}"),
        delimiter=",",
        row_count=1,
        error_count=0,
        validation=[],
        created_at=NOW,
        completed_at=NOW,
    )
    raw = RawRow.objects.create(
        workspace=workspace,
        attempt=attempt,
        row_number=1,
        raw_values={"id": f"{side}-1"},
        canonical_preview={"complete": True},
        validation=[],
    )
    logical = LogicalTransaction.objects.create(
        workspace=workspace,
        book_source=book_source,
        source_record_key=f"{label}-{side}-1",
        created_at=NOW,
    )
    observation = TransactionObservation.objects.create(
        workspace=workspace,
        logical_transaction=logical,
        raw_row=raw,
        business_reference=reference,
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
        fingerprint=_digest(f"observation-{label}-{side}"),
        created_at=NOW,
    )
    revision = DatasetRevision.objects.create(
        workspace=workspace,
        dataset=dataset,
        attempt=attempt,
        state_hash=_digest(f"state-{label}-{side}"),
        created_at=NOW,
    )
    DatasetMembership.objects.create(
        workspace=workspace,
        dataset_revision=revision,
        logical_transaction=logical,
        observation=observation,
    )
    Dataset.objects.filter(id=dataset.id).update(current_revision=revision)
    dataset.refresh_from_db()
    return dataset, logical, observation


@pytest.mark.django_db
def test_manifest_maps_active_authority_and_publishes_complete_immutable_facts() -> None:
    graph = create_graph("manual")
    decision = DecisionCommandService(clock=lambda: NOW).commit_initial(
        WorkspaceId(graph.workspace.id),
        book_id=BookId(graph.book.id),
        command=DecisionCommand(
            action=DecisionAction.LINK,
            authority=DecisionAuthority.link(str(graph.left.id), str(graph.right.id)),
            reason="Reviewed source documents",
            actor="reviewer",
            expected_resolution_generation=0,
            reviewed_observation_ids=(str(graph.left_observation.id), str(graph.right_observation.id)),
        ),
    )
    service = ReconciliationRunService(clock=lambda: NOW)
    frozen = service.create_run_manifest(WorkspaceId(graph.workspace.id), graph.scope.id)
    run = ReconciliationRun.objects.get(id=frozen.run_id)

    assert run.manifest_hash == _manifest_hash(run.manifest)
    assert run.manifest["decision_revision_ids"] == [str(decision.id)]
    assert run.manifest["left_inputs"] == [
        {
            "logical_transaction_id": str(graph.left.id),
            "observation_id": str(graph.left_observation.id),
            "observation_fingerprint": graph.left_observation.fingerprint,
        }
    ]
    computed = service.compute_run(WorkspaceId(graph.workspace.id), run.id)
    assert computed.pairs[0].origin is PairOrigin.MANUAL

    published = service.execute_and_publish_run(WorkspaceId(graph.workspace.id), run.id)
    run.refresh_from_db()
    graph.scope.refresh_from_db()
    assert published.freshness is RunFreshness.CURRENT
    assert run.lifecycle == RunLifecycle.COMPLETED
    assert graph.scope.current_run_id == run.id
    assert graph.scope.is_dirty is False
    assert run.inputs.count() == 2
    assert run.pairs.count() == 1
    assert run.unpaired.count() == 0
    assert run.pairs.get().decision_revision_id == decision.id
    assert run.pairs.get().comparisons.count() > 0
    assert run.result_counts == {
        "inputs": 2,
        "pairs": 1,
        "unpaired": 0,
        "candidates": 0,
        "components": 0,
        "diagnostics": 0,
    }
    with pytest.raises(RunEvidenceError):
        RunInput.objects.filter(run=run).update(side="RIGHT")
    with pytest.raises(RunEvidenceError):
        ReconciliationRun.objects.filter(id=run.id).update(manifest={})
    run.manifest = {}
    with pytest.raises(RunEvidenceError):
        run.save()
    with pytest.raises(RunEvidenceError):
        run.pairs.get().delete()


@pytest.mark.django_db
def test_publication_failure_rolls_back_every_fact_and_marks_failed() -> None:
    graph = create_graph("rollback", reference=None)

    def fail_after_facts(_run: ReconciliationRun) -> None:
        raise RuntimeError("injected publication failure")

    service = ReconciliationRunService(clock=lambda: NOW, publication_probe=fail_after_facts)
    frozen = service.create_run_manifest(WorkspaceId(graph.workspace.id), graph.scope.id)
    with pytest.raises(RuntimeError, match="injected publication failure"):
        service.execute_and_publish_run(WorkspaceId(graph.workspace.id), frozen.run_id)

    run = ReconciliationRun.objects.get(id=frozen.run_id)
    graph.scope.refresh_from_db()
    assert run.lifecycle == RunLifecycle.FAILED
    assert run.failure_code == "RuntimeError"
    assert run.pairs.count() == 0
    assert run.unpaired.count() == 0
    assert run.candidates.count() == 0
    assert run.components.count() == 0
    assert run.diagnostics.count() == 0
    assert FieldComparison.objects.filter(pair__run=run).count() == 0
    assert graph.scope.current_run_id is None


@pytest.mark.django_db
def test_weighted_run_persists_candidates_components_and_comparisons() -> None:
    graph = create_graph("weighted", reference=None)
    service = ReconciliationRunService(clock=lambda: NOW)
    frozen = service.create_run_manifest(WorkspaceId(graph.workspace.id), graph.scope.id)
    service.execute_and_publish_run(WorkspaceId(graph.workspace.id), frozen.run_id)

    run = ReconciliationRun.objects.get(id=frozen.run_id)
    pair = run.pairs.get()
    assert pair.origin == PairOrigin.WEIGHTED_GLOBAL
    assert pair.score_bp == 10_000
    assert run.candidates.count() == 1
    assert run.components.count() == 1
    assert run.candidates.get().component_id == run.components.get().id
    assert pair.comparisons.count() > 0


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("action", "expected_left_reason"),
    [
        (DecisionAction.ACCEPT_UNMATCHED, "ACCEPTED_UNMATCHED"),
        (DecisionAction.REJECT_CANDIDATE, "PROHIBITED"),
    ],
)
def test_non_link_authority_maps_into_frozen_engine_inputs(
    action: DecisionAction,
    expected_left_reason: str,
) -> None:
    graph = create_graph(f"authority-{action.value.lower()}")
    if action is DecisionAction.ACCEPT_UNMATCHED:
        authority = DecisionAuthority.accept_unmatched(str(graph.left.id), RecordSide.LEFT)
        reviewed = (str(graph.left_observation.id),)
    else:
        authority = DecisionAuthority.reject_candidate(str(graph.left.id), str(graph.right.id))
        reviewed = (str(graph.left_observation.id), str(graph.right_observation.id))
    DecisionCommandService(clock=lambda: NOW).commit_initial(
        WorkspaceId(graph.workspace.id),
        book_id=BookId(graph.book.id),
        command=DecisionCommand(
            action=action,
            authority=authority,
            reason="Reviewed authority",
            actor="reviewer",
            expected_resolution_generation=0,
            reviewed_observation_ids=reviewed,
        ),
    )
    service = ReconciliationRunService(clock=lambda: NOW)
    frozen = service.create_run_manifest(WorkspaceId(graph.workspace.id), graph.scope.id)
    result = service.compute_run(WorkspaceId(graph.workspace.id), frozen.run_id)

    left = next(item for item in result.unpaired if item.record_id == str(graph.left_observation.id))
    assert left.reason.value == expected_left_reason
    assert not result.pairs


@pytest.mark.django_db
def test_changed_dependency_keeps_completed_facts_stale_without_advancing_pointer() -> None:
    graph = create_graph("stale")
    service = ReconciliationRunService(clock=lambda: NOW)
    frozen = service.create_run_manifest(WorkspaceId(graph.workspace.id), graph.scope.id)
    ReconciliationScope.objects.filter(id=graph.scope.id).update(
        generation=F("generation") + 1,
        is_dirty=True,
    )

    published = service.execute_and_publish_run(WorkspaceId(graph.workspace.id), frozen.run_id)
    run = ReconciliationRun.objects.get(id=frozen.run_id)
    graph.scope.refresh_from_db()
    assert published.freshness is RunFreshness.STALE
    assert run.lifecycle == RunLifecycle.COMPLETED
    assert run.pairs.count() == 1
    assert graph.scope.current_run_id is None
    assert graph.scope.is_dirty is True


@pytest.mark.django_db
def test_manifest_is_idempotent_and_foreign_workspace_cannot_discover_run() -> None:
    graph = create_graph("owned")
    foreign = create_graph("foreign")
    service = ReconciliationRunService(clock=lambda: NOW)
    first = service.create_run_manifest(WorkspaceId(graph.workspace.id), graph.scope.id)
    second = service.create_run_manifest(WorkspaceId(graph.workspace.id), graph.scope.id)
    assert second == first
    assert ReconciliationRun.objects.filter(scope=graph.scope).count() == 1
    with pytest.raises(RunUnavailable):
        service.compute_run(WorkspaceId(foreign.workspace.id), first.run_id)
    with pytest.raises(RunUnavailable):
        service.create_run_manifest(WorkspaceId(foreign.workspace.id), graph.scope.id)


def _manifest_hash(manifest: dict) -> str:
    return hashlib.sha256(
        __import__("json").dumps(manifest, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()
    ).hexdigest()
