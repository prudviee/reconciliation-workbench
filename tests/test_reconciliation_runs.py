from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from django.db.models import F

from books.models import BookKind, PolicyRevision, ReconciliationBook, ReconciliationScope
from books.scopes import WorkspacePolicyRepository, WorkspaceScopeRepository, mark_dataset_activation
from cases.models import CaseEvidenceError, CaseLineage, CaseOccurrence, CaseScopeProjection, InvestigationCase
from cases.queries import CaseQueryService
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
from reconciliation.querying import ReviewPageSizeError, ReviewQueryUnavailable
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
from resolutions.queries import DecisionQueryService
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
    assert not CaseOccurrence.objects.filter(run=run).exists()
    assert not CaseScopeProjection.objects.filter(scope=graph.scope).exists()


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


@pytest.mark.django_db
def test_pair_case_reuses_logical_identity_across_corrected_observations() -> None:
    graph = create_graph("stable-pair", left_reference=None, right_reference=None)
    runner = ReconciliationRunService(clock=lambda: NOW)
    first = runner.create_run_manifest(WorkspaceId(graph.workspace.id), graph.scope.id)
    runner.execute_and_publish_run(WorkspaceId(graph.workspace.id), first.run_id)
    first_occurrence = CaseOccurrence.objects.get(run_id=first.run_id, result_kind="PAIR")
    first_snapshot = dict(first_occurrence.state_snapshot)

    corrected = replace_side_snapshot(graph, SourceRole.RIGHT, gross_amount=Decimal("100.10"))
    second = runner.create_run_manifest(WorkspaceId(graph.workspace.id), graph.scope.id)
    runner.execute_and_publish_run(WorkspaceId(graph.workspace.id), second.run_id)
    second_occurrence = CaseOccurrence.objects.get(run_id=second.run_id, result_kind="PAIR")

    assert corrected is not None
    assert second_occurrence.case_id == first_occurrence.case_id
    assert InvestigationCase.objects.filter(book=graph.book, kind="PAIR").count() == 1
    assert first_occurrence.case.occurrences.count() == 2
    assert first_occurrence.state_snapshot == first_snapshot
    projection = CaseScopeProjection.objects.get(case=first_occurrence.case, scope=graph.scope)
    assert projection.current_occurrence_id == second_occurrence.id
    assert projection.run_id == second.run_id
    with pytest.raises(CaseEvidenceError):
        CaseOccurrence.objects.filter(id=first_occurrence.id).update(state_snapshot={})


@pytest.mark.django_db
def test_unpaired_case_reuses_identity_and_carries_current_review_health() -> None:
    graph = create_graph("stable-unpaired", right_instrument="ETH-USD")
    decision = DecisionCommandService(clock=lambda: NOW).commit_initial(
        WorkspaceId(graph.workspace.id),
        book_id=BookId(graph.book.id),
        command=DecisionCommand(
            action=DecisionAction.ACCEPT_UNMATCHED,
            authority=DecisionAuthority.accept_unmatched(str(graph.left.id), RecordSide.LEFT),
            reason="No counterpart",
            actor="reviewer",
            expected_resolution_generation=0,
            reviewed_observation_ids=(str(graph.left_observation.id),),
        ),
    )
    runner = ReconciliationRunService(clock=lambda: NOW)
    first = runner.create_run_manifest(WorkspaceId(graph.workspace.id), graph.scope.id)
    runner.execute_and_publish_run(WorkspaceId(graph.workspace.id), first.run_id)
    first_occurrence = CaseOccurrence.objects.get(
        run_id=first.run_id,
        unpaired__logical_transaction=graph.left,
    )

    corrected = replace_side_snapshot(graph, SourceRole.LEFT, gross_amount=Decimal("101"))
    second = runner.create_run_manifest(WorkspaceId(graph.workspace.id), graph.scope.id)
    runner.execute_and_publish_run(WorkspaceId(graph.workspace.id), second.run_id)
    second_occurrence = CaseOccurrence.objects.get(
        run_id=second.run_id,
        unpaired__logical_transaction=graph.left,
    )
    projection = CaseScopeProjection.objects.get(case=first_occurrence.case, scope=graph.scope)

    assert corrected is not None
    assert first_occurrence.case_id == second_occurrence.case_id
    assert projection.current_occurrence_id == second_occurrence.id
    assert projection.review_health == "EVIDENCE_CHANGED"
    assert CurrentDecisionHealth.objects.get(decision_id=decision.decision_id).health == "EVIDENCE_CHANGED"


@pytest.mark.django_db
def test_same_stable_case_keeps_independent_current_projection_per_scope() -> None:
    graph = create_graph("multi-scope")
    second_scope = WorkspaceScopeRepository(WorkspaceId(graph.workspace.id)).create(
        book_id=BookId(graph.book.id),
        coverage_key="2026-10",
        left_dataset_id=graph.scope.left_dataset_id,
        right_dataset_id=graph.scope.right_dataset_id,
        created_at=NOW,
    )
    runner = ReconciliationRunService(clock=lambda: NOW)
    first = runner.create_run_manifest(WorkspaceId(graph.workspace.id), graph.scope.id)
    second = runner.create_run_manifest(WorkspaceId(graph.workspace.id), second_scope.id)
    runner.execute_and_publish_run(WorkspaceId(graph.workspace.id), first.run_id)
    runner.execute_and_publish_run(WorkspaceId(graph.workspace.id), second.run_id)

    pair_case = InvestigationCase.objects.get(book=graph.book, kind="PAIR")
    projections = CaseScopeProjection.objects.filter(case=pair_case).order_by("scope_id")
    assert projections.count() == 2
    assert {item.scope_id for item in projections} == {graph.scope.id, second_scope.id}
    assert {item.run_id for item in projections} == {first.run_id, second.run_id}


@pytest.mark.django_db
def test_ambiguity_case_uses_complete_logical_members_and_reuses_unchanged_membership() -> None:
    graph = create_graph("stable-ambiguity", left_reference=None, right_reference=None)
    replace_side_snapshot(graph, SourceRole.RIGHT, gross_amount=Decimal("200"))
    runner = ReconciliationRunService(clock=lambda: NOW)
    first = runner.create_run_manifest(WorkspaceId(graph.workspace.id), graph.scope.id)
    first_result = runner.compute_run(WorkspaceId(graph.workspace.id), first.run_id)
    assert {item.reason.value for item in first_result.unpaired} == {"AMBIGUOUS"}
    runner.execute_and_publish_run(WorkspaceId(graph.workspace.id), first.run_id)
    first_occurrence = CaseOccurrence.objects.get(run_id=first.run_id, result_kind="AMBIGUITY")

    replace_side_snapshot(graph, SourceRole.RIGHT, gross_amount=Decimal("201"))
    second = runner.create_run_manifest(WorkspaceId(graph.workspace.id), graph.scope.id)
    runner.execute_and_publish_run(WorkspaceId(graph.workspace.id), second.run_id)
    second_occurrence = CaseOccurrence.objects.get(run_id=second.run_id, result_kind="AMBIGUITY")
    ambiguity = InvestigationCase.objects.get(id=first_occurrence.case_id)

    assert second_occurrence.case_id == first_occurrence.case_id
    assert ambiguity.ambiguity_left_logical_ids == [str(graph.left.id)]
    assert ambiguity.ambiguity_right_logical_ids == [str(graph.right.id)]
    assert ambiguity.occurrences.count() == 2

    graph.book.refresh_from_db()
    revised_matching = matching_policy_to_payload(
        MatchingPolicy.initial_demo(policy_version="demo-matching-v2")
    )
    revised_comparison = comparison_policy_to_payload(ComparisonPolicy.initial_demo())
    WorkspacePolicyRepository(WorkspaceId(graph.workspace.id)).create_revision(
        book_id=BookId(graph.book.id),
        expected_generation=graph.book.generation,
        matching_policy=revised_matching,
        comparison_policy=revised_comparison,
        created_at=NOW + timedelta(minutes=2),
    )
    third = runner.create_run_manifest(WorkspaceId(graph.workspace.id), graph.scope.id)
    runner.execute_and_publish_run(WorkspaceId(graph.workspace.id), third.run_id)
    third_occurrence = CaseOccurrence.objects.get(run_id=third.run_id, result_kind="AMBIGUITY")

    assert third_occurrence.case_id != first_occurrence.case_id
    assert InvestigationCase.objects.filter(book=graph.book, kind="AMBIGUITY").count() == 2


@pytest.mark.django_db
def test_pair_split_and_merge_preserve_every_predecessor_and_successor() -> None:
    graph = create_graph("lineage")
    runner = ReconciliationRunService(clock=lambda: NOW)
    first = runner.create_run_manifest(WorkspaceId(graph.workspace.id), graph.scope.id)
    runner.execute_and_publish_run(WorkspaceId(graph.workspace.id), first.run_id)
    pair_case = CaseOccurrence.objects.get(run_id=first.run_id, result_kind="PAIR").case

    replace_side_snapshot(graph, SourceRole.RIGHT, reference="DIFFERENT")
    second = runner.create_run_manifest(WorkspaceId(graph.workspace.id), graph.scope.id)
    runner.execute_and_publish_run(WorkspaceId(graph.workspace.id), second.run_id)
    unpaired_cases = {
        item.case for item in CaseOccurrence.objects.filter(run_id=second.run_id, result_kind="UNPAIRED")
    }
    split_edges = CaseLineage.objects.filter(caused_by_run_id=second.run_id)
    assert {item.successor for item in split_edges} == unpaired_cases
    assert {item.predecessor for item in split_edges} == {pair_case}

    replace_side_snapshot(graph, SourceRole.RIGHT, reference="SHARED-1")
    third = runner.create_run_manifest(WorkspaceId(graph.workspace.id), graph.scope.id)
    runner.execute_and_publish_run(WorkspaceId(graph.workspace.id), third.run_id)
    merged_pair = CaseOccurrence.objects.get(run_id=third.run_id, result_kind="PAIR").case
    merge_edges = CaseLineage.objects.filter(caused_by_run_id=third.run_id)
    assert merged_pair == pair_case
    assert {item.predecessor for item in merge_edges} == unpaired_cases
    assert {item.successor for item in merge_edges} == {pair_case}
    with pytest.raises(CaseEvidenceError):
        merge_edges.update(transition_kind="changed")


def _manifest_hash(manifest: dict) -> str:
    return hashlib.sha256(
        __import__("json").dumps(manifest, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()
    ).hexdigest()


@pytest.mark.django_db
def test_case_query_pages_are_stable_complete_and_bounded(
    django_assert_num_queries,
) -> None:
    graph = create_graph(
        "case-query-pages",
        left_reference=None,
        right_reference=None,
        right_instrument="ETH-USD",
    )
    runner = ReconciliationRunService(clock=lambda: NOW)
    frozen = runner.create_run_manifest(WorkspaceId(graph.workspace.id), graph.scope.id)
    runner.execute_and_publish_run(WorkspaceId(graph.workspace.id), frozen.run_id)

    query = CaseQueryService(clock=lambda: NOW)
    with django_assert_num_queries(4):
        first = query.list_cases(
            WorkspaceId(graph.workspace.id),
            book_id=BookId(graph.book.id),
            scope_id=graph.scope.id,
            page_size=1,
        )
    assert first.next_cursor is not None
    second = query.list_cases(
        WorkspaceId(graph.workspace.id),
        book_id=BookId(graph.book.id),
        scope_id=graph.scope.id,
        cursor=first.next_cursor,
        page_size=1,
    )
    assert second.next_cursor is None

    seen = first.items + second.items
    expected = list(
        CaseScopeProjection.objects.filter(scope=graph.scope).order_by(
            "case__created_at", "case_id"
        )
    )
    assert [item.case_id for item in seen] == [item.case_id for item in expected]
    assert len({item.case_id for item in seen}) == 2
    with pytest.raises(ReviewPageSizeError):
        query.list_cases(
            WorkspaceId(graph.workspace.id),
            book_id=BookId(graph.book.id),
            scope_id=graph.scope.id,
            page_size=101,
        )


@pytest.mark.django_db
def test_case_query_history_occurrence_and_current_review_are_explicit(
    django_assert_num_queries,
) -> None:
    graph = create_graph("case-query-history", left_reference=None, right_reference=None)
    runner = ReconciliationRunService(clock=lambda: NOW)
    first = runner.create_run_manifest(WorkspaceId(graph.workspace.id), graph.scope.id)
    runner.execute_and_publish_run(WorkspaceId(graph.workspace.id), first.run_id)
    corrected = replace_side_snapshot(
        graph,
        SourceRole.RIGHT,
        gross_amount=Decimal("100.10"),
    )
    assert corrected is not None
    second = runner.create_run_manifest(WorkspaceId(graph.workspace.id), graph.scope.id)
    runner.execute_and_publish_run(WorkspaceId(graph.workspace.id), second.run_id)
    case = CaseOccurrence.objects.get(run_id=first.run_id, result_kind="PAIR").case

    query = CaseQueryService(clock=lambda: NOW)
    with django_assert_num_queries(5):
        history = query.get_case_history(
            WorkspaceId(graph.workspace.id),
            book_id=BookId(graph.book.id),
            scope_id=graph.scope.id,
            case_id=case.id,
        )
    assert sorted(item.timeline_label for item in history.occurrences) == [
        "CURRENT",
        "HISTORICAL",
    ]
    current_occurrence = next(
        item for item in history.occurrences if item.timeline_label == "CURRENT"
    )
    with django_assert_num_queries(4):
        occurrence = query.get_case_occurrence(
            WorkspaceId(graph.workspace.id),
            book_id=BookId(graph.book.id),
            scope_id=graph.scope.id,
            occurrence_id=current_occurrence.occurrence_id,
        )
    assert occurrence.timeline_label == "CURRENT"
    assert occurrence.run_id == second.run_id
    with django_assert_num_queries(5):
        current_review = query.get_current_review(
            WorkspaceId(graph.workspace.id),
            book_id=BookId(graph.book.id),
            scope_id=graph.scope.id,
            case_id=case.id,
        )
    assert current_review is not None
    assert current_review.occurrence_id == current_occurrence.occurrence_id


@pytest.mark.django_db
def test_case_query_returns_complete_bidirectional_lineage(
    django_assert_num_queries,
) -> None:
    graph = create_graph("case-query-lineage")
    runner = ReconciliationRunService(clock=lambda: NOW)
    first = runner.create_run_manifest(WorkspaceId(graph.workspace.id), graph.scope.id)
    runner.execute_and_publish_run(WorkspaceId(graph.workspace.id), first.run_id)
    pair_case = CaseOccurrence.objects.get(run_id=first.run_id, result_kind="PAIR").case

    replace_side_snapshot(graph, SourceRole.RIGHT, reference="DIFFERENT")
    second = runner.create_run_manifest(WorkspaceId(graph.workspace.id), graph.scope.id)
    runner.execute_and_publish_run(WorkspaceId(graph.workspace.id), second.run_id)
    unpaired_case = CaseOccurrence.objects.filter(
        run_id=second.run_id,
        result_kind="UNPAIRED",
    ).first().case

    query = CaseQueryService(clock=lambda: NOW)
    with django_assert_num_queries(5):
        outgoing = query.get_case_lineage(
            WorkspaceId(graph.workspace.id),
            book_id=BookId(graph.book.id),
            scope_id=graph.scope.id,
            case_id=pair_case.id,
        )
    assert len(outgoing.edges) == 2
    assert {item.direction for item in outgoing.edges} == {"SUCCESSOR"}
    incoming = query.get_case_lineage(
        WorkspaceId(graph.workspace.id),
        book_id=BookId(graph.book.id),
        scope_id=graph.scope.id,
        case_id=unpaired_case.id,
    )
    assert [(item.direction, item.related_case_id) for item in incoming.edges] == [
        ("PREDECESSOR", pair_case.id)
    ]


@pytest.mark.django_db
def test_case_query_foreign_and_absent_ids_share_one_unavailable_result() -> None:
    owner = create_graph("case-query-owner")
    outsider = create_graph("case-query-outsider")
    runner = ReconciliationRunService(clock=lambda: NOW)
    frozen = runner.create_run_manifest(WorkspaceId(owner.workspace.id), owner.scope.id)
    runner.execute_and_publish_run(WorkspaceId(owner.workspace.id), frozen.run_id)
    occurrence = CaseOccurrence.objects.get(run_id=frozen.run_id)
    query = CaseQueryService(clock=lambda: NOW)
    probes = (
        lambda: query.list_cases(
            WorkspaceId(outsider.workspace.id),
            book_id=BookId(owner.book.id),
            scope_id=owner.scope.id,
        ),
        lambda: query.list_cases(
            WorkspaceId(owner.workspace.id),
            book_id=BookId(owner.book.id),
            scope_id=outsider.scope.id,
        ),
        lambda: query.get_case_history(
            WorkspaceId(outsider.workspace.id),
            book_id=BookId(outsider.book.id),
            scope_id=outsider.scope.id,
            case_id=occurrence.case_id,
        ),
        lambda: query.get_case_history(
            WorkspaceId(owner.workspace.id),
            book_id=BookId(owner.book.id),
            scope_id=owner.scope.id,
            case_id=uuid4(),
        ),
        lambda: query.get_case_occurrence(
            WorkspaceId(owner.workspace.id),
            book_id=BookId(owner.book.id),
            scope_id=owner.scope.id,
            occurrence_id=uuid4(),
        ),
    )
    for probe in probes:
        with pytest.raises(ReviewQueryUnavailable):
            probe()

@pytest.mark.django_db
def test_case_query_applies_unavailable_boundary_to_every_detail_projection() -> None:
    owner = create_graph("case-query-boundary-owner")
    outsider = create_graph("case-query-boundary-outsider")
    runner = ReconciliationRunService(clock=lambda: NOW)
    frozen = runner.create_run_manifest(WorkspaceId(owner.workspace.id), owner.scope.id)
    runner.execute_and_publish_run(WorkspaceId(owner.workspace.id), frozen.run_id)
    occurrence = CaseOccurrence.objects.get(run_id=frozen.run_id)
    query = CaseQueryService(clock=lambda: NOW)
    foreign_probes = (
        lambda: query.get_case_history(
            WorkspaceId(outsider.workspace.id),
            book_id=BookId(outsider.book.id),
            scope_id=outsider.scope.id,
            case_id=occurrence.case_id,
        ),
        lambda: query.get_case_occurrence(
            WorkspaceId(outsider.workspace.id),
            book_id=BookId(outsider.book.id),
            scope_id=outsider.scope.id,
            occurrence_id=occurrence.id,
        ),
        lambda: query.get_current_review(
            WorkspaceId(outsider.workspace.id),
            book_id=BookId(outsider.book.id),
            scope_id=outsider.scope.id,
            case_id=occurrence.case_id,
        ),
        lambda: query.get_case_lineage(
            WorkspaceId(outsider.workspace.id),
            book_id=BookId(outsider.book.id),
            scope_id=outsider.scope.id,
            case_id=occurrence.case_id,
        ),
    )
    absent_probes = (
        lambda: query.get_case_history(
            WorkspaceId(owner.workspace.id),
            book_id=BookId(owner.book.id),
            scope_id=owner.scope.id,
            case_id=uuid4(),
        ),
        lambda: query.get_case_occurrence(
            WorkspaceId(owner.workspace.id),
            book_id=BookId(owner.book.id),
            scope_id=owner.scope.id,
            occurrence_id=uuid4(),
        ),
        lambda: query.get_current_review(
            WorkspaceId(owner.workspace.id),
            book_id=BookId(owner.book.id),
            scope_id=owner.scope.id,
            case_id=uuid4(),
        ),
        lambda: query.get_case_lineage(
            WorkspaceId(owner.workspace.id),
            book_id=BookId(owner.book.id),
            scope_id=owner.scope.id,
            case_id=uuid4(),
        ),
    )
    for probe in foreign_probes + absent_probes:
        with pytest.raises(ReviewQueryUnavailable):
            probe()
@pytest.mark.django_db
def test_review_acceptance_corpus_preserves_run_one_through_decision_correction_and_rerun() -> None:
    graph = create_graph("review-acceptance-corpus")
    runner = ReconciliationRunService(clock=lambda: NOW)
    first = runner.create_run_manifest(WorkspaceId(graph.workspace.id), graph.scope.id)
    runner.execute_and_publish_run(WorkspaceId(graph.workspace.id), first.run_id)
    first_run = ReconciliationRun.objects.get(id=first.run_id)
    first_pair = first_run.pairs.get()
    first_occurrence = CaseOccurrence.objects.get(run=first_run, result_kind="PAIR")
    immutable_snapshot = {
        "counts": dict(first_run.result_counts),
        "pair": (
            first_pair.id,
            first_pair.origin,
            first_pair.left_observation_id,
            first_pair.right_observation_id,
            first_pair.decision_revision_id,
        ),
        "comparisons": tuple(
            first_pair.comparisons.order_by("field").values_list(
                "field",
                "status",
                "left_value",
                "right_value",
                "signed_difference",
                "allowed_difference",
            )
        ),
        "occurrence": dict(first_occurrence.state_snapshot),
    }

    decision = DecisionCommandService(clock=lambda: NOW).commit_initial(
        WorkspaceId(graph.workspace.id),
        book_id=BookId(graph.book.id),
        command=DecisionCommand(
            action=DecisionAction.LINK,
            authority=DecisionAuthority.link(str(graph.left.id), str(graph.right.id)),
            reason="Confirmed the economic relationship",
            actor="reviewer",
            expected_resolution_generation=0,
            reviewed_observation_ids=(
                str(graph.left_observation.id),
                str(graph.right_observation.id),
            ),
        ),
    )
    pending = DecisionQueryService(clock=lambda: NOW).list_decisions(
        WorkspaceId(graph.workspace.id),
        book_id=BookId(graph.book.id),
        scope_id=graph.scope.id,
    )
    assert [(item.decision_id, item.review_is_pending) for item in pending.items] == [
        (decision.decision_id, True)
    ]

    corrected = replace_side_snapshot(
        graph,
        SourceRole.RIGHT,
        gross_amount=Decimal("101.00"),
    )
    assert corrected is not None
    second = runner.create_run_manifest(WorkspaceId(graph.workspace.id), graph.scope.id)
    runner.execute_and_publish_run(WorkspaceId(graph.workspace.id), second.run_id)

    second_run = ReconciliationRun.objects.get(id=second.run_id)
    second_pair = second_run.pairs.get()
    health = DecisionHealthSnapshot.objects.get(run=second_run, decision_revision=decision)
    case_history = CaseQueryService(clock=lambda: NOW).get_case_history(
        WorkspaceId(graph.workspace.id),
        book_id=BookId(graph.book.id),
        scope_id=graph.scope.id,
        case_id=first_occurrence.case_id,
    )
    assert second_pair.origin == PairOrigin.MANUAL
    assert second_pair.right_observation_id == corrected.id
    assert health.health == "EVIDENCE_CHANGED"
    assert health.attention == ["COMPARISON_CHANGED"]
    assert sorted(item.timeline_label for item in case_history.occurrences) == [
        "CURRENT",
        "HISTORICAL",
    ]

    first_run.refresh_from_db()
    first_pair.refresh_from_db()
    first_occurrence.refresh_from_db()
    assert dict(first_run.result_counts) == immutable_snapshot["counts"]
    assert (
        first_pair.id,
        first_pair.origin,
        first_pair.left_observation_id,
        first_pair.right_observation_id,
        first_pair.decision_revision_id,
    ) == immutable_snapshot["pair"]
    assert tuple(
        first_pair.comparisons.order_by("field").values_list(
            "field",
            "status",
            "left_value",
            "right_value",
            "signed_difference",
            "allowed_difference",
        )
    ) == immutable_snapshot["comparisons"]
    assert first_occurrence.state_snapshot == immutable_snapshot["occurrence"]
