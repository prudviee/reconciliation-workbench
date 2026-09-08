from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from io import StringIO
from pathlib import Path
from uuid import uuid4

import pytest
from django.core.management import call_command

from books.models import BookKind, PolicyRevision, ReconciliationBook
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
from jobs.models import WorkerHeartbeat
from reconciliation.domain import (
    BookId,
    ComparisonPolicy,
    DatasetMode,
    MatchingPolicy,
    ReferenceSemantics,
    WorkspaceId,
    policy_revision_digest,
)
from reconciliation.models import ReconciliationRun, RunLifecycle
from reconciliation.policies import comparison_policy_to_payload, matching_policy_to_payload
from reconciliation.services import ReconciliationRunService
from sources.models import BookSource, MappingRevision, SourceContractRevision, SourceRole, SourceSystem
from workspaces.lifecycle import WorkspaceLifecycleService
from workspaces.models import Workspace


pytestmark = pytest.mark.django_db(transaction=True)
NOW = datetime(2026, 9, 8, tzinfo=UTC)


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _create_run_graph(label: str):
    workspace = Workspace.objects.create(
        session_digest=_digest(f"session-{label}-{uuid4()}"),
        created_at=NOW,
        expires_at=NOW + timedelta(days=7),
    )
    book = ReconciliationBook.objects.create(
        workspace=workspace, name=f"{label} book", kind=BookKind.USER, created_at=NOW
    )
    datasets = {}
    for role in (SourceRole.LEFT, SourceRole.RIGHT):
        side = role.value.lower()
        source = SourceSystem.objects.create(
            workspace=workspace, name=f"{label}-{side}", adapter_key=f"{side}-v1", created_at=NOW
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
            workspace=workspace, book_source=book_source, coverage_key="2026-09", created_at=NOW
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
            business_reference="SHARED-1",
            executed_at_utc=NOW,
            instrument="BTC-USD",
            side="BUY",
            quantity=1,
            unit_price=100,
            gross_amount=100,
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
        datasets[role] = dataset

    scope = WorkspaceScopeRepository(WorkspaceId(workspace.id)).create(
        book_id=BookId(book.id),
        coverage_key="2026-09",
        left_dataset_id=datasets[SourceRole.LEFT].id,
        right_dataset_id=datasets[SourceRole.RIGHT].id,
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
    return workspace, scope


def test_worker_once_claims_and_completes_a_pending_run() -> None:
    workspace, scope = _create_run_graph("worker")
    frozen = ReconciliationRunService(clock=lambda: NOW).create_run_manifest(
        WorkspaceId(workspace.id), scope.id
    )
    output = StringIO()

    call_command("worker", once=True, stdout=output)

    run = ReconciliationRun.objects.get(id=frozen.run_id)
    assert run.lifecycle == RunLifecycle.COMPLETED
    assert "RECONCILIATION_RUN: claimed 1, succeeded 1" in output.getvalue()


def test_worker_once_purges_a_pending_workspace_cleanup() -> None:
    workspace = Workspace.objects.create(
        session_digest=hashlib.sha256(f"cleanup-{uuid4()}".encode()).hexdigest(),
        created_at=NOW,
        expires_at=NOW + timedelta(days=7),
    )
    WorkspaceLifecycleService().delete(WorkspaceId(workspace.id), now=NOW)
    output = StringIO()

    call_command("worker", once=True, stdout=output)

    assert not Workspace.objects.filter(id=workspace.id).exists()
    assert "WORKSPACE_CLEANUP: claimed 1, succeeded 1" in output.getvalue()


def test_worker_once_writes_a_database_backed_heartbeat(monkeypatch, tmp_path: Path) -> None:
    output = StringIO()
    heartbeat_file = tmp_path / "worker-heartbeat"
    monkeypatch.setenv("WORKER_HEARTBEAT_FILE", str(heartbeat_file))

    call_command("worker", once=True, worker_id="test-worker", stdout=output)

    heartbeat = WorkerHeartbeat.objects.get(worker_id="test-worker")
    assert heartbeat.updated_at.tzinfo is not None
