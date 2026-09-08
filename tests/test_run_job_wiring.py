from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest

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
from jobs.models import JobState, WorkItem
from jobs.services import (
    TransientJobFailure,
    claim_and_execute,
)
from reconciliation.domain import (
    BookId,
    ComparisonPolicy,
    DatasetMode,
    FailureCategory,
    JobKind,
    MatchingPolicy,
    ReferenceSemantics,
    RetryPolicy,
    WorkspaceId,
    policy_revision_digest,
)
from reconciliation.models import ReconciliationRun, RunLifecycle
from reconciliation.policies import comparison_policy_to_payload, matching_policy_to_payload
from reconciliation.services import RunUnavailable, execute_claimed_run
from reconciliation.services import ReconciliationRunService
from sources.models import BookSource, MappingRevision, SourceContractRevision, SourceRole, SourceSystem
from workspaces.models import Workspace


pytestmark = pytest.mark.django_db

NOW = datetime(2026, 9, 8, tzinfo=UTC)


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _create_workspace(label: str) -> Workspace:
    return Workspace.objects.create(
        session_digest=_digest(f"session-{label}-{uuid4()}"),
        created_at=NOW,
        expires_at=NOW + timedelta(days=7),
    )


def _create_graph(workspace: Workspace, label: str):
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
    return scope


def _retry_policy() -> RetryPolicy:
    return RetryPolicy(max_attempts=3, backoff=timedelta(seconds=5))


def test_claim_and_execute_completes_a_freshly_enqueued_run_and_releases_quota() -> None:
    workspace = _create_workspace("wiring")
    scope = _create_graph(workspace, "wiring")
    frozen = ReconciliationRunService(clock=lambda: NOW).create_run_manifest(
        WorkspaceId(workspace.id), scope.id
    )
    workspace.refresh_from_db()
    assert workspace.active_job_count == 1

    records = claim_and_execute(
        JobKind.RECONCILIATION_RUN,
        now=NOW,
        lease_duration=timedelta(seconds=60),
        retry_policy=_retry_policy(),
        executor=execute_claimed_run,
        work_item_id=frozen.work_item_id,
    )

    assert len(records) == 1
    assert records[0].succeeded is True
    run = ReconciliationRun.objects.get(id=frozen.run_id)
    assert run.lifecycle == RunLifecycle.COMPLETED
    assert run.current_attempt_token is None
    workspace.refresh_from_db()
    assert workspace.active_job_count == 0


def test_repeated_manifest_freeze_reuses_the_work_item_without_double_reserving() -> None:
    workspace = _create_workspace("dedup")
    scope = _create_graph(workspace, "dedup")
    service = ReconciliationRunService(clock=lambda: NOW)

    first = service.create_run_manifest(WorkspaceId(workspace.id), scope.id)
    second = service.create_run_manifest(WorkspaceId(workspace.id), scope.id)

    assert first.run_id == second.run_id
    assert first.work_item_id == second.work_item_id
    assert WorkItem.objects.filter(reconciliation_run_id=first.run_id).count() == 1
    workspace.refresh_from_db()
    assert workspace.active_job_count == 1


def test_a_work_item_pointed_at_another_workspaces_run_fails_before_any_financial_read() -> None:
    owner_workspace = _create_workspace("owner")
    scope = _create_graph(owner_workspace, "owner")
    frozen = ReconciliationRunService(clock=lambda: NOW).create_run_manifest(
        WorkspaceId(owner_workspace.id), scope.id
    )
    intruder_workspace = _create_workspace("intruder")
    WorkItem.objects.filter(id=frozen.work_item_id).update(
        workspace_id=intruder_workspace.id
    )

    work_item = WorkItem.objects.get(id=frozen.work_item_id)
    with pytest.raises(RunUnavailable):
        execute_claimed_run(work_item, "forged-token")

    run = ReconciliationRun.objects.get(id=frozen.run_id)
    assert run.lifecycle == RunLifecycle.FROZEN
    assert run.current_attempt_token is None


def test_claim_and_execute_retries_a_transient_executor_failure() -> None:
    workspace = _create_workspace("transient")
    scope = _create_graph(workspace, "transient")
    frozen = ReconciliationRunService(clock=lambda: NOW).create_run_manifest(
        WorkspaceId(workspace.id), scope.id
    )
    calls = {"count": 0}

    def flaky_executor(work_item, token) -> None:
        calls["count"] += 1
        if calls["count"] == 1:
            raise TransientJobFailure("simulated lock timeout")
        execute_claimed_run(work_item, token)

    first_pass = claim_and_execute(
        JobKind.RECONCILIATION_RUN,
        now=NOW,
        lease_duration=timedelta(seconds=60),
        retry_policy=_retry_policy(),
        executor=flaky_executor,
        work_item_id=frozen.work_item_id,
    )
    assert first_pass[0].succeeded is False
    work_item = WorkItem.objects.get(id=frozen.work_item_id)
    assert work_item.state == JobState.READY
    assert work_item.available_at == NOW + timedelta(seconds=5)

    second_pass = claim_and_execute(
        JobKind.RECONCILIATION_RUN,
        now=NOW + timedelta(seconds=5),
        lease_duration=timedelta(seconds=60),
        retry_policy=_retry_policy(),
        executor=flaky_executor,
        work_item_id=frozen.work_item_id,
    )
    assert second_pass[0].succeeded is True
    run = ReconciliationRun.objects.get(id=frozen.run_id)
    assert run.lifecycle == RunLifecycle.COMPLETED
