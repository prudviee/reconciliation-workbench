from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from django.db.models import F

from books.models import BookKind, PolicyRevision, ReconciliationBook, ReconciliationScope
from books.scopes import WorkspaceScopeRepository, mark_dataset_activation
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
    DecisionHealthDiagnostic,
    DiagnosticKind,
    ExpectedDecisionRevision,
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
    CurrentDecisionHealth,
    DecisionHealthSnapshot,
    ReconciliationRun,
    RunEvidenceError,
    RunFreshness,
    RunInput,
    RunLifecycle,
)
from reconciliation.policies import comparison_policy_to_payload, matching_policy_to_payload
from reconciliation.services import ReconciliationRunService, RunUnavailable
from resolutions.models import ActiveDecisionClaim, Decision
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


def create_graph(
    label: str,
    *,
    left_reference: str | None = "SHARED-1",
    right_reference: str | None = "SHARED-1",
    right_instrument: str = "BTC-USD",
) -> RunGraph:
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
    left_dataset, left, left_observation = create_side(
        workspace, book, label, SourceRole.LEFT, left_reference, "BTC-USD"
    )
    right_dataset, right, right_observation = create_side(
        workspace, book, label, SourceRole.RIGHT, right_reference, right_instrument
    )
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
    instrument: str,
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
        instrument=instrument,
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


def replace_side_snapshot(
    graph: RunGraph,
    role: SourceRole,
    *,
    include: bool = True,
    reference: str | None = None,
    instrument: str | None = None,
    gross_amount: Decimal | None = None,
) -> TransactionObservation | None:
    logical = graph.left if role is SourceRole.LEFT else graph.right
    previous = (
        graph.left_observation if role is SourceRole.LEFT else graph.right_observation
    )
    dataset = Dataset.objects.get(
        book_source=logical.book_source,
        coverage_key=graph.scope.coverage_key,
    )
    prior_revision = dataset.current_revision
    assert prior_revision is not None
    contract = prior_revision.attempt.contract_revision
    artifact = FileArtifact.objects.create(
        workspace=graph.workspace,
        storage_key=f"{uuid4()}.csv",
        physical_hash=_digest(f"replacement-artifact-{uuid4()}"),
        original_filename=f"{role.value.lower()}-replacement.csv",
        content_type="text/csv",
        byte_size=10,
        created_at=NOW + timedelta(minutes=1),
    )
    attempt = IngestionAttempt.objects.create(
        workspace=graph.workspace,
        artifact=artifact,
        dataset=dataset,
        contract_revision=contract,
        expected_base=prior_revision,
        state=AttemptState.ACTIVATED,
        physical_hash=artifact.physical_hash,
        semantic_hash=_digest(f"replacement-semantic-{uuid4()}"),
        delimiter=",",
        row_count=1 if include else 0,
        error_count=0,
        validation=[],
        activation_reason="test correction",
        created_at=NOW + timedelta(minutes=1),
        completed_at=NOW + timedelta(minutes=1),
    )
    observation = None
    if include:
        raw = RawRow.objects.create(
            workspace=graph.workspace,
            attempt=attempt,
            row_number=1,
            raw_values={"id": logical.source_record_key},
            canonical_preview={"complete": True},
            validation=[],
        )
        selected_reference = (
            previous.business_reference if reference is None else reference
        )
        observation = TransactionObservation.objects.create(
            workspace=graph.workspace,
            logical_transaction=logical,
            raw_row=raw,
            business_reference=selected_reference,
            executed_at_utc=previous.executed_at_utc,
            instrument=instrument or previous.instrument,
            side=previous.side,
            quantity=previous.quantity,
            unit_price=previous.unit_price,
            gross_amount=gross_amount or previous.gross_amount,
            currency=previous.currency,
            state=previous.state,
            eligible_for_matching=previous.eligible_for_matching,
            provenance={},
            fingerprint=_digest(f"replacement-observation-{uuid4()}"),
            created_at=NOW + timedelta(minutes=1),
        )
    revision = DatasetRevision.objects.create(
        workspace=graph.workspace,
        dataset=dataset,
        parent_revision=prior_revision,
        attempt=attempt,
        state_hash=_digest(f"replacement-state-{uuid4()}"),
        created_at=NOW + timedelta(minutes=1),
    )
    if observation is not None:
        DatasetMembership.objects.create(
            workspace=graph.workspace,
            dataset_revision=revision,
            logical_transaction=logical,
            observation=observation,
        )
    Dataset.objects.filter(id=dataset.id).update(current_revision=revision)
    mark_dataset_activation(
        workspace_id=WorkspaceId(graph.workspace.id),
        book_id=graph.book.id,
        dataset_id=dataset.id,
    )
    return observation


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
    graph = create_graph("rollback", left_reference=None, right_reference=None)

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
def test_health_projection_rolls_back_with_failed_publication() -> None:
    graph = create_graph("health-rollback")
    DecisionCommandService(clock=lambda: NOW).commit_initial(
        WorkspaceId(graph.workspace.id),
        book_id=BookId(graph.book.id),
        command=DecisionCommand(
            action=DecisionAction.LINK,
            authority=DecisionAuthority.link(str(graph.left.id), str(graph.right.id)),
            reason="Reviewed pair",
            actor="reviewer",
            expected_resolution_generation=0,
            reviewed_observation_ids=(str(graph.left_observation.id), str(graph.right_observation.id)),
        ),
    )

    def fail_after_health(_run: ReconciliationRun) -> None:
        raise RuntimeError("health publication failure")

    runner = ReconciliationRunService(
        clock=lambda: NOW,
        publication_probe=fail_after_health,
    )
    frozen = runner.create_run_manifest(WorkspaceId(graph.workspace.id), graph.scope.id)
    with pytest.raises(RuntimeError, match="health publication failure"):
        runner.execute_and_publish_run(WorkspaceId(graph.workspace.id), frozen.run_id)

    assert not DecisionHealthSnapshot.objects.filter(run_id=frozen.run_id).exists()
    assert not CurrentDecisionHealth.objects.filter(scope=graph.scope).exists()


@pytest.mark.django_db
def test_weighted_run_persists_candidates_components_and_comparisons() -> None:
    graph = create_graph("weighted", left_reference=None, right_reference=None)
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


@pytest.mark.django_db
def test_manual_correction_preserves_authority_flags_health_and_reaffirm_resets_baseline() -> None:
    graph = create_graph("manual-health")
    commands = DecisionCommandService(clock=lambda: NOW)
    revision = commands.commit_initial(
        WorkspaceId(graph.workspace.id),
        book_id=BookId(graph.book.id),
        command=DecisionCommand(
            action=DecisionAction.LINK,
            authority=DecisionAuthority.link(str(graph.left.id), str(graph.right.id)),
            reason="Reviewed original pair",
            actor="reviewer",
            expected_resolution_generation=0,
            reviewed_observation_ids=(str(graph.left_observation.id), str(graph.right_observation.id)),
        ),
    )
    runner = ReconciliationRunService(clock=lambda: NOW)
    first = runner.create_run_manifest(WorkspaceId(graph.workspace.id), graph.scope.id)
    runner.execute_and_publish_run(WorkspaceId(graph.workspace.id), first.run_id)
    assert DecisionHealthSnapshot.objects.get(run_id=first.run_id).health == "UNCHANGED"

    corrected = replace_side_snapshot(
        graph,
        SourceRole.RIGHT,
        gross_amount=Decimal("101"),
    )
    assert corrected is not None
    second = runner.create_run_manifest(WorkspaceId(graph.workspace.id), graph.scope.id)
    runner.execute_and_publish_run(WorkspaceId(graph.workspace.id), second.run_id)
    changed = DecisionHealthSnapshot.objects.get(run_id=second.run_id)
    pair = ReconciliationRun.objects.get(id=second.run_id).pairs.get()
    assert pair.origin == PairOrigin.MANUAL
    assert pair.right_observation_id == corrected.id
    assert changed.health == "EVIDENCE_CHANGED"
    assert changed.attention == ["COMPARISON_CHANGED"]
    original_snapshot = DecisionHealthSnapshot.objects.get(run_id=first.run_id)
    assert original_snapshot.health == "UNCHANGED"
    assert original_snapshot.attention == []
    with pytest.raises(RunEvidenceError):
        DecisionHealthSnapshot.objects.filter(id=original_snapshot.id).update(
            health="EVIDENCE_CHANGED"
        )
    assert ActiveDecisionClaim.objects.filter(decision_revision=revision).count() == 2
    assert Decision.objects.get(id=revision.decision_id).current_revision_id == revision.id

    graph.book.refresh_from_db()
    reaffirmed = commands.commit_change(
        WorkspaceId(graph.workspace.id),
        book_id=BookId(graph.book.id),
        command=DecisionCommand(
            action=DecisionAction.REAFFIRM,
            target=ExpectedDecisionRevision(str(revision.decision_id), str(revision.id)),
            reason="Reviewed corrected pair",
            actor="reviewer",
            expected_resolution_generation=graph.book.resolution_generation,
            reviewed_observation_ids=(str(graph.left_observation.id), str(corrected.id)),
        ),
    )
    third = runner.create_run_manifest(WorkspaceId(graph.workspace.id), graph.scope.id)
    runner.execute_and_publish_run(WorkspaceId(graph.workspace.id), third.run_id)
    reset = DecisionHealthSnapshot.objects.get(run_id=third.run_id)
    assert reset.decision_revision_id == reaffirmed.id
    assert reset.health == "UNCHANGED"
    assert reset.attention == []


@pytest.mark.django_db
def test_accepted_unmatched_stays_reserved_when_new_candidate_appears() -> None:
    graph = create_graph("accepted-health", right_instrument="ETH-USD")
    revision = DecisionCommandService(clock=lambda: NOW).commit_initial(
        WorkspaceId(graph.workspace.id),
        book_id=BookId(graph.book.id),
        command=DecisionCommand(
            action=DecisionAction.ACCEPT_UNMATCHED,
            authority=DecisionAuthority.accept_unmatched(str(graph.left.id), RecordSide.LEFT),
            reason="No counterpart found",
            actor="reviewer",
            expected_resolution_generation=0,
            reviewed_observation_ids=(str(graph.left_observation.id),),
        ),
    )
    runner = ReconciliationRunService(clock=lambda: NOW)
    first = runner.create_run_manifest(WorkspaceId(graph.workspace.id), graph.scope.id)
    runner.execute_and_publish_run(WorkspaceId(graph.workspace.id), first.run_id)
    assert DecisionHealthSnapshot.objects.get(run_id=first.run_id).health == "UNCHANGED"

    replace_side_snapshot(graph, SourceRole.RIGHT, instrument="BTC-USD")
    second = runner.create_run_manifest(WorkspaceId(graph.workspace.id), graph.scope.id)
    result = runner.compute_run(WorkspaceId(graph.workspace.id), second.run_id)
    assert any(item.kind.value == "ACCEPTED_UNMATCHED_CANDIDATE" for item in result.diagnostics)
    runner.execute_and_publish_run(WorkspaceId(graph.workspace.id), second.run_id)
    projected = DecisionHealthSnapshot.objects.get(run_id=second.run_id)
    assert projected.health == "NEW_CANDIDATE"
    assert ReconciliationRun.objects.get(id=second.run_id).unpaired.get(
        observation_id=graph.left_observation.id
    ).reason == "ACCEPTED_UNMATCHED"
    assert ActiveDecisionClaim.objects.get(decision_revision=revision).logical_transaction_id == graph.left.id


@pytest.mark.django_db
def test_incomplete_accepted_unmatched_diagnostic_records_limit_attention() -> None:
    graph = create_graph("accepted-limit", right_instrument="ETH-USD")
    DecisionCommandService(clock=lambda: NOW).commit_initial(
        WorkspaceId(graph.workspace.id),
        book_id=BookId(graph.book.id),
        command=DecisionCommand(
            action=DecisionAction.ACCEPT_UNMATCHED,
            authority=DecisionAuthority.accept_unmatched(str(graph.left.id), RecordSide.LEFT),
            reason="No counterpart found",
            actor="reviewer",
            expected_resolution_generation=0,
            reviewed_observation_ids=(str(graph.left_observation.id),),
        ),
    )
    runner = ReconciliationRunService(clock=lambda: NOW)
    frozen = runner.create_run_manifest(WorkspaceId(graph.workspace.id), graph.scope.id)
    result = runner.compute_run(WorkspaceId(graph.workspace.id), frozen.run_id)
    limited = replace(
        result,
        diagnostics=(
            DecisionHealthDiagnostic(
                kind=DiagnosticKind.INCOMPLETE_SEARCH,
                record_id=str(graph.left_observation.id),
                candidate_id=None,
                candidate_current_pair_id=None,
                complete=False,
                explanation="Diagnostic reached its configured candidate limit.",
            ),
        ),
    )
    ReconciliationRun.objects.filter(id=frozen.run_id).update(lifecycle=RunLifecycle.RUNNING)
    runner.publish_run(WorkspaceId(graph.workspace.id), frozen.run_id, limited)

    projected = DecisionHealthSnapshot.objects.get(run_id=frozen.run_id)
    assert projected.health == "UNCHANGED"
    assert projected.attention == ["DIAGNOSTIC_INCOMPLETE"]
    assert ReconciliationRun.objects.get(id=frozen.run_id).diagnostics.get().complete is False


@pytest.mark.django_db
def test_missing_link_partner_projects_unavailable_without_releasing_claims() -> None:
    graph = create_graph("missing-health")
    revision = DecisionCommandService(clock=lambda: NOW).commit_initial(
        WorkspaceId(graph.workspace.id),
        book_id=BookId(graph.book.id),
        command=DecisionCommand(
            action=DecisionAction.LINK,
            authority=DecisionAuthority.link(str(graph.left.id), str(graph.right.id)),
            reason="Reviewed pair",
            actor="reviewer",
            expected_resolution_generation=0,
            reviewed_observation_ids=(str(graph.left_observation.id), str(graph.right_observation.id)),
        ),
    )
    replace_side_snapshot(graph, SourceRole.RIGHT, include=False)
    runner = ReconciliationRunService(clock=lambda: NOW)
    frozen = runner.create_run_manifest(WorkspaceId(graph.workspace.id), graph.scope.id)
    runner.execute_and_publish_run(WorkspaceId(graph.workspace.id), frozen.run_id)

    projected = DecisionHealthSnapshot.objects.get(run_id=frozen.run_id)
    assert projected.health == "PARTNER_UNAVAILABLE"
    assert projected.current_observation_ids == [str(graph.left_observation.id)]
    assert ActiveDecisionClaim.objects.filter(decision_revision=revision).count() == 2


@pytest.mark.django_db
def test_rejection_survives_equal_reference_correction_with_conflict_attention() -> None:
    graph = create_graph(
        "rejected-health",
        left_reference="LEFT-1",
        right_reference="RIGHT-9",
    )
    revision = DecisionCommandService(clock=lambda: NOW).commit_initial(
        WorkspaceId(graph.workspace.id),
        book_id=BookId(graph.book.id),
        command=DecisionCommand(
            action=DecisionAction.REJECT_CANDIDATE,
            authority=DecisionAuthority.reject_candidate(str(graph.left.id), str(graph.right.id)),
            reason="Not the same trade",
            actor="reviewer",
            expected_resolution_generation=0,
            reviewed_observation_ids=(str(graph.left_observation.id), str(graph.right_observation.id)),
        ),
    )
    runner = ReconciliationRunService(clock=lambda: NOW)
    first = runner.create_run_manifest(WorkspaceId(graph.workspace.id), graph.scope.id)
    runner.execute_and_publish_run(WorkspaceId(graph.workspace.id), first.run_id)
    original = DecisionHealthSnapshot.objects.get(run_id=first.run_id)
    assert original.health == "UNCHANGED"
    assert original.attention == []

    replace_side_snapshot(graph, SourceRole.RIGHT, reference="LEFT-1")
    second = runner.create_run_manifest(WorkspaceId(graph.workspace.id), graph.scope.id)
    result = runner.compute_run(WorkspaceId(graph.workspace.id), second.run_id)
    assert not result.pairs
    runner.execute_and_publish_run(WorkspaceId(graph.workspace.id), second.run_id)
    projected = DecisionHealthSnapshot.objects.get(run_id=second.run_id)
    assert projected.health == "EVIDENCE_CHANGED"
    assert projected.attention == ["AUTHORITATIVE_REFERENCE_CONFLICT"]
    assert Decision.objects.get(id=revision.decision_id).current_revision_id == revision.id
    assert CurrentDecisionHealth.objects.get(
        scope=graph.scope,
        decision_id=revision.decision_id,
    ).snapshot_id == projected.id


@pytest.mark.django_db
def test_stale_run_keeps_health_snapshot_without_replacing_current_projection() -> None:
    graph = create_graph("stale-health")
    revision = DecisionCommandService(clock=lambda: NOW).commit_initial(
        WorkspaceId(graph.workspace.id),
        book_id=BookId(graph.book.id),
        command=DecisionCommand(
            action=DecisionAction.LINK,
            authority=DecisionAuthority.link(str(graph.left.id), str(graph.right.id)),
            reason="Reviewed pair",
            actor="reviewer",
            expected_resolution_generation=0,
            reviewed_observation_ids=(str(graph.left_observation.id), str(graph.right_observation.id)),
        ),
    )
    runner = ReconciliationRunService(clock=lambda: NOW)
    frozen = runner.create_run_manifest(WorkspaceId(graph.workspace.id), graph.scope.id)
    ReconciliationScope.objects.filter(id=graph.scope.id).update(
        generation=F("generation") + 1,
        is_dirty=True,
    )
    published = runner.execute_and_publish_run(
        WorkspaceId(graph.workspace.id), frozen.run_id
    )

    assert published.freshness is RunFreshness.STALE
    assert DecisionHealthSnapshot.objects.filter(
        run_id=frozen.run_id,
        decision_revision=revision,
    ).count() == 1
    assert not CurrentDecisionHealth.objects.filter(
        scope=graph.scope,
        decision_id=revision.decision_id,
    ).exists()


def _manifest_hash(manifest: dict) -> str:
    return hashlib.sha256(
        __import__("json").dumps(manifest, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()
    ).hexdigest()
