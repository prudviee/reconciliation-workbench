from __future__ import annotations

import hashlib
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from django.db import IntegrityError, close_old_connections, transaction

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
from jobs.models import JobAttempt, JobAttemptOutcome, JobEvidenceError, WorkItem
from jobs.services import (
    ClaimedWork,
    claim_batch,
    enqueue,
    mark_failed,
    mark_succeeded,
)
from reconciliation.domain import (
    BookId,
    ComparisonPolicy,
    DatasetMode,
    FailureCategory,
    JobKind,
    JobState,
    LeaseToken,
    MatchingPolicy,
    ReferenceSemantics,
    RetryOutcome,
    WorkspaceId,
    policy_revision_digest,
)
from reconciliation.policies import comparison_policy_to_payload, matching_policy_to_payload
from reconciliation.services import ReconciliationRunService
from sources.models import BookSource, MappingRevision, SourceContractRevision, SourceRole, SourceSystem
from workspaces.models import CleanupReason, Workspace, WorkspaceCleanupRequest


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


def _create_ingestion_attempt(workspace: Workspace, label: str) -> IngestionAttempt:
    book = ReconciliationBook.objects.create(
        workspace=workspace, name=f"{label} book", kind=BookKind.USER, created_at=NOW
    )
    source = SourceSystem.objects.create(
        workspace=workspace, name=f"{label}-left", adapter_key="left-v1", created_at=NOW
    )
    book_source = BookSource.objects.create(
        workspace=workspace,
        book=book,
        source=source,
        role=SourceRole.LEFT,
        identity_namespace=f"{label}-left",
        created_at=NOW,
    )
    mapping = MappingRevision.objects.create(
        workspace=workspace,
        source=source,
        revision=1,
        mapping={"side": "left"},
        parser_version="parser-v1",
        digest=_digest(f"mapping-{label}"),
        created_at=NOW,
    )
    contract = SourceContractRevision.objects.create(
        workspace=workspace,
        source=source,
        mapping_revision=mapping,
        revision=1,
        mode=DatasetMode.FULL_SNAPSHOT,
        timezone_name="UTC",
        identity_namespace=f"{label}-left",
        reference_semantics=ReferenceSemantics.TRUSTED_SHARED,
        contract={"side": "left"},
        digest=_digest(f"contract-{label}"),
        created_at=NOW,
    )
    dataset = Dataset.objects.create(
        workspace=workspace, book_source=book_source, coverage_key="2026-09", created_at=NOW
    )
    artifact = FileArtifact.objects.create(
        workspace=workspace,
        storage_key=f"{uuid4()}.csv",
        physical_hash=_digest(f"artifact-{label}"),
        original_filename="left.csv",
        content_type="text/csv",
        byte_size=10,
        created_at=NOW,
    )
    return IngestionAttempt.objects.create(
        workspace=workspace,
        artifact=artifact,
        dataset=dataset,
        contract_revision=contract,
        state=AttemptState.ACTIVATED,
        physical_hash=artifact.physical_hash,
        semantic_hash=_digest(f"semantic-{label}"),
        delimiter=",",
        row_count=1,
        error_count=0,
        validation=[],
        created_at=NOW,
        completed_at=NOW,
    )


def _create_reconciliation_run(workspace: Workspace, label: str):
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
    frozen = ReconciliationRunService(clock=lambda: NOW).create_run_manifest(
        WorkspaceId(workspace.id), scope.id
    )
    from reconciliation.models import ReconciliationRun

    return ReconciliationRun.objects.get(id=frozen.run_id)


def _create_cleanup_request(workspace: Workspace) -> WorkspaceCleanupRequest:
    return WorkspaceCleanupRequest.objects.create(
        workspace=workspace, reason=CleanupReason.DELETED, requested_at=NOW
    )


def test_work_item_accepts_exactly_the_target_matching_its_kind() -> None:
    workspace = _create_workspace("shape")
    attempt = _create_ingestion_attempt(workspace, "shape")

    item = WorkItem.objects.create(
        workspace=workspace,
        kind=JobKind.IMPORT_VALIDATION,
        import_attempt=attempt,
        available_at=NOW,
        max_attempts=3,
        created_at=NOW,
        updated_at=NOW,
    )

    assert item.state == JobState.READY


@pytest.mark.parametrize(
    "kwargs",
    [
        {},
        {"import_attempt_id": None, "reconciliation_run_id": None, "cleanup_request_id": None},
    ],
)
def test_work_item_rejects_a_kind_with_no_matching_target(kwargs: dict) -> None:
    workspace = _create_workspace("no-target")

    with pytest.raises(IntegrityError), transaction.atomic():
        WorkItem.objects.create(
            workspace=workspace,
            kind=JobKind.IMPORT_VALIDATION,
            available_at=NOW,
            max_attempts=3,
            created_at=NOW,
            updated_at=NOW,
            **kwargs,
        )


def test_work_item_rejects_two_targets_set_at_once() -> None:
    workspace = _create_workspace("two-targets")
    attempt = _create_ingestion_attempt(workspace, "two-targets")
    cleanup = _create_cleanup_request(workspace)

    with pytest.raises(IntegrityError), transaction.atomic():
        WorkItem.objects.create(
            workspace=workspace,
            kind=JobKind.IMPORT_VALIDATION,
            import_attempt=attempt,
            cleanup_request=cleanup,
            available_at=NOW,
            max_attempts=3,
            created_at=NOW,
            updated_at=NOW,
        )


def test_work_item_rejects_a_target_reused_by_a_second_work_item() -> None:
    workspace = _create_workspace("reuse")
    attempt = _create_ingestion_attempt(workspace, "reuse")
    WorkItem.objects.create(
        workspace=workspace,
        kind=JobKind.IMPORT_VALIDATION,
        import_attempt=attempt,
        available_at=NOW,
        max_attempts=3,
        created_at=NOW,
        updated_at=NOW,
    )

    with pytest.raises(IntegrityError), transaction.atomic():
        WorkItem.objects.create(
            workspace=workspace,
            kind=JobKind.IMPORT_VALIDATION,
            import_attempt=attempt,
            available_at=NOW,
            max_attempts=3,
            created_at=NOW,
            updated_at=NOW,
        )


def test_reconciliation_run_creation_enqueues_its_own_work_item() -> None:
    run_workspace = _create_workspace("run-shape")
    run = _create_reconciliation_run(run_workspace, "run-shape")

    item = WorkItem.objects.get(reconciliation_run=run)
    assert item.kind == JobKind.RECONCILIATION_RUN
    assert item.state == JobState.READY
    assert item.workspace_id == run_workspace.id


def test_work_item_cleanup_shape_is_accepted() -> None:
    cleanup_workspace = _create_workspace("cleanup-shape")
    cleanup = _create_cleanup_request(cleanup_workspace)
    WorkItem.objects.create(
        workspace=cleanup_workspace,
        kind=JobKind.WORKSPACE_CLEANUP,
        cleanup_request=cleanup,
        available_at=NOW,
        max_attempts=3,
        created_at=NOW,
        updated_at=NOW,
    )


def test_work_item_rejects_leased_state_without_lease_fields() -> None:
    workspace = _create_workspace("lease-shape")
    attempt = _create_ingestion_attempt(workspace, "lease-shape")

    with pytest.raises(IntegrityError), transaction.atomic():
        WorkItem.objects.create(
            workspace=workspace,
            kind=JobKind.IMPORT_VALIDATION,
            import_attempt=attempt,
            state=JobState.LEASED,
            available_at=NOW,
            max_attempts=3,
            created_at=NOW,
            updated_at=NOW,
        )


def test_claim_batch_leases_ready_items_and_records_one_attempt_each() -> None:
    workspace = _create_workspace("claim")
    first = _create_ingestion_attempt(workspace, "claim-a")
    second = _create_ingestion_attempt(workspace, "claim-b")
    for attempt in (first, second):
        WorkItem.objects.create(
            workspace=workspace,
            kind=JobKind.IMPORT_VALIDATION,
            import_attempt=attempt,
            available_at=NOW,
            max_attempts=3,
            created_at=NOW,
            updated_at=NOW,
        )

    claimed = claim_batch(
        JobKind.IMPORT_VALIDATION, now=NOW, lease_duration=timedelta(seconds=30)
    )

    assert len(claimed) == 2
    tokens = {str(work.token) for work in claimed}
    assert len(tokens) == 2
    for work in claimed:
        assert work.work_item.state == JobState.LEASED
        assert work.work_item.attempt_count == 1
        assert JobAttempt.objects.filter(token=str(work.token)).exists()


@pytest.mark.django_db(transaction=True)
def test_claim_batch_never_claims_the_same_row_twice_concurrently() -> None:
    workspace = _create_workspace("concurrent-claim")
    attempt = _create_ingestion_attempt(workspace, "concurrent-claim")
    WorkItem.objects.create(
        workspace=workspace,
        kind=JobKind.IMPORT_VALIDATION,
        import_attempt=attempt,
        available_at=NOW,
        max_attempts=3,
        created_at=NOW,
        updated_at=NOW,
    )

    def worker(_: int) -> list[ClaimedWork]:
        close_old_connections()
        try:
            return claim_batch(
                JobKind.IMPORT_VALIDATION, now=NOW, lease_duration=timedelta(seconds=30)
            )
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(worker, range(2)))

    total_claimed = sum(len(result) for result in results)
    assert total_claimed == 1


def test_claim_batch_reclaims_an_item_whose_lease_expired() -> None:
    workspace = _create_workspace("reclaim")
    attempt = _create_ingestion_attempt(workspace, "reclaim")
    WorkItem.objects.create(
        workspace=workspace,
        kind=JobKind.IMPORT_VALIDATION,
        import_attempt=attempt,
        available_at=NOW,
        max_attempts=3,
        created_at=NOW,
        updated_at=NOW,
    )
    first = claim_batch(
        JobKind.IMPORT_VALIDATION, now=NOW, lease_duration=timedelta(seconds=10)
    )
    assert len(first) == 1
    first_token = first[0].token

    still_leased = claim_batch(
        JobKind.IMPORT_VALIDATION,
        now=NOW + timedelta(seconds=5),
        lease_duration=timedelta(seconds=10),
    )
    assert still_leased == []

    reclaimed = claim_batch(
        JobKind.IMPORT_VALIDATION,
        now=NOW + timedelta(seconds=11),
        lease_duration=timedelta(seconds=10),
    )
    assert len(reclaimed) == 1
    assert str(reclaimed[0].token) != str(first_token)
    assert reclaimed[0].work_item.attempt_count == 2


def test_a_fenced_attempt_cannot_publish_success_after_reclaim() -> None:
    workspace = _create_workspace("fenced-success")
    attempt = _create_ingestion_attempt(workspace, "fenced-success")
    WorkItem.objects.create(
        workspace=workspace,
        kind=JobKind.IMPORT_VALIDATION,
        import_attempt=attempt,
        available_at=NOW,
        max_attempts=3,
        created_at=NOW,
        updated_at=NOW,
    )
    first = claim_batch(
        JobKind.IMPORT_VALIDATION, now=NOW, lease_duration=timedelta(seconds=10)
    )[0]
    second = claim_batch(
        JobKind.IMPORT_VALIDATION,
        now=NOW + timedelta(seconds=11),
        lease_duration=timedelta(seconds=10),
    )[0]

    accepted = mark_succeeded(first.token, now=NOW + timedelta(seconds=12))

    assert accepted is False
    work_item = WorkItem.objects.get(id=first.work_item.id)
    assert work_item.state == JobState.LEASED
    assert work_item.current_token == str(second.token)
    stale_attempt = JobAttempt.objects.get(token=str(first.token))
    assert stale_attempt.outcome == JobAttemptOutcome.EXPIRED


def test_mark_succeeded_completes_the_current_attempt() -> None:
    workspace = _create_workspace("success")
    attempt = _create_ingestion_attempt(workspace, "success")
    enqueue(
        WorkspaceId(workspace.id),
        JobKind.IMPORT_VALIDATION,
        max_attempts=3,
        now=NOW,
        import_attempt=attempt,
    )
    claimed = claim_batch(
        JobKind.IMPORT_VALIDATION, now=NOW, lease_duration=timedelta(seconds=10)
    )[0]

    accepted = mark_succeeded(claimed.token, now=NOW + timedelta(seconds=1))

    assert accepted is True
    work_item = WorkItem.objects.get(id=claimed.work_item.id)
    assert work_item.state == JobState.SUCCEEDED
    assert work_item.current_token is None
    assert work_item.lease_until is None
    job_attempt = JobAttempt.objects.get(token=str(claimed.token))
    assert job_attempt.outcome == JobAttemptOutcome.SUCCEEDED
    assert job_attempt.completed_at == NOW + timedelta(seconds=1)
    workspace.refresh_from_db()
    assert workspace.active_job_count == 0


def test_mark_failed_applies_the_supplied_retry_outcome() -> None:
    workspace = _create_workspace("retry")
    attempt = _create_ingestion_attempt(workspace, "retry")
    enqueue(
        WorkspaceId(workspace.id),
        JobKind.IMPORT_VALIDATION,
        max_attempts=3,
        now=NOW,
        import_attempt=attempt,
    )
    claimed = claim_batch(
        JobKind.IMPORT_VALIDATION, now=NOW, lease_duration=timedelta(seconds=10)
    )[0]
    retry_at = NOW + timedelta(seconds=5)

    accepted = mark_failed(
        claimed.token,
        outcome=RetryOutcome(state=JobState.READY, available_at=retry_at),
        failure_category=FailureCategory.TRANSIENT,
        now=NOW + timedelta(seconds=1),
    )

    assert accepted is True
    work_item = WorkItem.objects.get(id=claimed.work_item.id)
    assert work_item.state == JobState.READY
    assert work_item.available_at == retry_at
    assert work_item.current_token is None
    job_attempt = JobAttempt.objects.get(token=str(claimed.token))
    assert job_attempt.outcome == JobAttemptOutcome.FAILED
    assert job_attempt.failure_category == FailureCategory.TRANSIENT
    workspace.refresh_from_db()
    assert workspace.active_job_count == 1


def test_mark_failed_terminal_outcome_leaves_the_item_failed() -> None:
    workspace = _create_workspace("terminal")
    attempt = _create_ingestion_attempt(workspace, "terminal")
    enqueue(
        WorkspaceId(workspace.id),
        JobKind.IMPORT_VALIDATION,
        max_attempts=1,
        now=NOW,
        import_attempt=attempt,
    )
    claimed = claim_batch(
        JobKind.IMPORT_VALIDATION, now=NOW, lease_duration=timedelta(seconds=10)
    )[0]

    mark_failed(
        claimed.token,
        outcome=RetryOutcome(state=JobState.FAILED, available_at=None),
        failure_category=FailureCategory.PERMANENT,
        now=NOW + timedelta(seconds=1),
    )

    work_item = WorkItem.objects.get(id=claimed.work_item.id)
    assert work_item.state == JobState.FAILED
    workspace.refresh_from_db()
    assert workspace.active_job_count == 0


def test_job_attempt_rows_cannot_be_updated_outside_the_claim_service() -> None:
    workspace = _create_workspace("immutable")
    attempt = _create_ingestion_attempt(workspace, "immutable")
    item = WorkItem.objects.create(
        workspace=workspace,
        kind=JobKind.IMPORT_VALIDATION,
        import_attempt=attempt,
        available_at=NOW,
        max_attempts=3,
        created_at=NOW,
        updated_at=NOW,
    )
    claimed = claim_batch(
        JobKind.IMPORT_VALIDATION, now=NOW, lease_duration=timedelta(seconds=10)
    )[0]

    with pytest.raises(JobEvidenceError):
        JobAttempt.objects.filter(token=str(claimed.token)).update(token="tampered")

    with pytest.raises(JobEvidenceError):
        JobAttempt.objects.filter(token=str(claimed.token)).delete()

    job_attempt = JobAttempt.objects.get(token=str(claimed.token))
    with pytest.raises(JobEvidenceError):
        job_attempt.save()
