from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from books.models import BookKind, ReconciliationBook
from ingestion.artifacts import IntakeLimits
from ingestion.models import AttemptState, IngestionAttempt, RawRow
from ingestion.preview import ImportStateConflict, PreviewService, execute_claimed_import
from ingestion.repositories import WorkspaceIngestionRepository
from ingestion.services import ArtifactIntakeService, configured_artifact_store
from jobs.models import WorkItem
from jobs.services import TransientJobFailure, claim_and_execute, enqueue
from reconciliation.domain import (
    BookId,
    JobKind,
    JobState,
    RetryPolicy,
    WorkspaceId,
    mapping_revision_digest,
    source_contract_digest,
)
from sources.adapters import contract_to_payload, ledger_contract
from sources.models import SourceRole
from sources.repositories import WorkspaceSourceRepository
from workspaces.models import Workspace


pytestmark = pytest.mark.django_db
NOW = datetime(2026, 9, 8, tzinfo=UTC)
LIMITS = IntakeLimits(10_000, 100, 20, 1_000)
LEDGER_HEADER = "trade_id,traded_at,instrument,side,quantity,price,gross_amount,state\n"
LEDGER_ROW = "T-1001,2026-09-01T09:15:00Z,BTC-USD,BUY,0.5,62000,31000,SETTLED\n"


@pytest.fixture(autouse=True)
def _local_artifact_root(settings, tmp_path: Path) -> None:
    """Point the configured store at this test's tmp_path.

    `execute_claimed_import` always resolves `PreviewService.configured()`
    (matching production, which has exactly one configured backend), so the
    artifact must be published under the same root the executor will read
    from, not a store the test constructs separately.
    """
    settings.INGESTION_PRIVATE_ROOT = tmp_path


def _create_workspace(label: str) -> Workspace:
    return Workspace.objects.create(
        session_digest=(label * 8)[:64].ljust(64, "0"),
        created_at=NOW,
        expires_at=NOW + timedelta(days=7),
    )


def _prepare(tmp_path: Path, workspace: Workspace) -> dict[str, object]:
    book = ReconciliationBook.objects.create(
        workspace=workspace, name="wiring book", kind=BookKind.USER, created_at=NOW
    )
    source_repository = WorkspaceSourceRepository(WorkspaceId(workspace.id))
    ingestion_repository = WorkspaceIngestionRepository(WorkspaceId(workspace.id))
    contract = ledger_contract()
    source = source_repository.create_source(
        name="ledger source", adapter_key=contract.adapter_key, created_at=NOW
    )
    book_source = source_repository.assign_book_source(
        book_id=BookId(book.id),
        source_id=source.id,
        role=SourceRole.LEFT,
        identity_namespace=contract.identity_namespace,
        created_at=NOW,
    )
    contract_payload = contract_to_payload(contract)
    mapping = source_repository.create_mapping_revision(
        source_id=source.id,
        revision=1,
        mapping={"bindings": contract_payload["bindings"]},
        parser_version=contract.parser_version,
        digest=mapping_revision_digest({"bindings": contract_payload["bindings"]}),
        created_at=NOW,
    )
    contract_revision = source_repository.create_contract_revision(
        source_id=source.id,
        mapping_revision_id=mapping.id,
        revision=1,
        mode=contract.mode,
        timezone_name=contract.timezone_name,
        identity_namespace=contract.identity_namespace,
        reference_semantics=contract.reference_semantics,
        contract=contract_payload,
        digest=source_contract_digest(contract_payload),
        created_at=NOW,
    )
    dataset = ingestion_repository.create_dataset(
        book_source_id=book_source.id, coverage_key="2026-09", created_at=NOW
    )
    intake = ArtifactIntakeService(limits=LIMITS, clock=lambda: NOW)
    artifact = intake.ingest(
        WorkspaceId(workspace.id),
        original_filename="ledger.csv",
        content_type="text/csv",
        delimiter=",",
        chunks=[(LEDGER_HEADER + LEDGER_ROW).encode()],
    )
    return {
        "preview_service": PreviewService(
            configured_artifact_store(), LIMITS, clock=lambda: NOW
        ),
        "artifact": artifact,
        "dataset": dataset,
        "contract": contract_revision,
    }


def _retry_policy() -> RetryPolicy:
    return RetryPolicy(max_attempts=3, backoff=timedelta(seconds=5))


def test_claim_and_execute_completes_a_freshly_enqueued_import_and_releases_quota(
    tmp_path: Path,
) -> None:
    workspace = _create_workspace("wiring")
    graph = _prepare(tmp_path, workspace)
    shell = graph["preview_service"].create_shell(
        WorkspaceId(workspace.id),
        artifact_id=graph["artifact"].id,
        dataset_id=graph["dataset"].id,
        contract_revision_id=graph["contract"].id,
        delimiter=",",
    )
    work_item = enqueue(
        WorkspaceId(workspace.id),
        JobKind.IMPORT_VALIDATION,
        max_attempts=3,
        now=NOW,
        import_attempt=shell,
    )
    workspace.refresh_from_db()
    assert workspace.active_job_count == 1

    records = claim_and_execute(
        JobKind.IMPORT_VALIDATION,
        now=NOW,
        lease_duration=timedelta(seconds=60),
        retry_policy=_retry_policy(),
        executor=execute_claimed_import,
        work_item_id=work_item.id,
    )

    assert len(records) == 1
    assert records[0].succeeded is True
    attempt = IngestionAttempt.objects.get(id=shell.id)
    assert attempt.state == AttemptState.READY
    assert attempt.row_count == 1
    assert RawRow.objects.filter(attempt=attempt).count() == 1
    workspace.refresh_from_db()
    assert workspace.active_job_count == 0


def test_a_work_item_pointed_at_another_workspaces_attempt_fails_before_reading_bytes(
    tmp_path: Path,
) -> None:
    owner_workspace = _create_workspace("owner")
    graph = _prepare(tmp_path, owner_workspace)
    shell = graph["preview_service"].create_shell(
        WorkspaceId(owner_workspace.id),
        artifact_id=graph["artifact"].id,
        dataset_id=graph["dataset"].id,
        contract_revision_id=graph["contract"].id,
        delimiter=",",
    )
    work_item = enqueue(
        WorkspaceId(owner_workspace.id),
        JobKind.IMPORT_VALIDATION,
        max_attempts=3,
        now=NOW,
        import_attempt=shell,
    )
    intruder_workspace = _create_workspace("intruder")
    WorkItem.objects.filter(id=work_item.id).update(workspace_id=intruder_workspace.id)

    work_item = WorkItem.objects.get(id=work_item.id)
    with pytest.raises(Exception):
        execute_claimed_import(work_item, "forged-token")

    attempt = IngestionAttempt.objects.get(id=shell.id)
    assert attempt.state == AttemptState.RECEIVED
    assert attempt.row_count == 0


def test_a_fenced_attempt_cannot_complete_after_reclaim(tmp_path: Path) -> None:
    workspace = _create_workspace("fenced")
    graph = _prepare(tmp_path, workspace)
    shell = graph["preview_service"].create_shell(
        WorkspaceId(workspace.id),
        artifact_id=graph["artifact"].id,
        dataset_id=graph["dataset"].id,
        contract_revision_id=graph["contract"].id,
        delimiter=",",
    )
    work_item = enqueue(
        WorkspaceId(workspace.id),
        JobKind.IMPORT_VALIDATION,
        max_attempts=3,
        now=NOW,
        import_attempt=shell,
    )

    from jobs.services import claim_one

    first = claim_one(work_item.id, now=NOW, lease_duration=timedelta(seconds=10))
    second = claim_one(
        work_item.id,
        now=NOW + timedelta(seconds=11),
        lease_duration=timedelta(seconds=10),
    )
    assert second is not None

    with pytest.raises(ImportStateConflict):
        graph["preview_service"].complete(
            WorkspaceId(workspace.id), shell.id, attempt_token=str(first.token)
        )

    attempt = IngestionAttempt.objects.get(id=shell.id)
    assert attempt.state == AttemptState.RECEIVED

    completed = graph["preview_service"].complete(
        WorkspaceId(workspace.id), shell.id, attempt_token=str(second.token)
    )
    assert completed.state == AttemptState.READY


def test_claim_and_execute_retries_a_transient_import_failure(tmp_path: Path) -> None:
    workspace = _create_workspace("transient")
    graph = _prepare(tmp_path, workspace)
    shell = graph["preview_service"].create_shell(
        WorkspaceId(workspace.id),
        artifact_id=graph["artifact"].id,
        dataset_id=graph["dataset"].id,
        contract_revision_id=graph["contract"].id,
        delimiter=",",
    )
    work_item = enqueue(
        WorkspaceId(workspace.id),
        JobKind.IMPORT_VALIDATION,
        max_attempts=3,
        now=NOW,
        import_attempt=shell,
    )
    calls = {"count": 0}

    def flaky_executor(item, token) -> None:
        calls["count"] += 1
        if calls["count"] == 1:
            raise TransientJobFailure("simulated lock timeout")
        execute_claimed_import(item, token)

    first_pass = claim_and_execute(
        JobKind.IMPORT_VALIDATION,
        now=NOW,
        lease_duration=timedelta(seconds=60),
        retry_policy=_retry_policy(),
        executor=flaky_executor,
        work_item_id=work_item.id,
    )
    assert first_pass[0].succeeded is False
    refreshed = WorkItem.objects.get(id=work_item.id)
    assert refreshed.state == JobState.READY

    second_pass = claim_and_execute(
        JobKind.IMPORT_VALIDATION,
        now=NOW + timedelta(seconds=5),
        lease_duration=timedelta(seconds=60),
        retry_policy=_retry_policy(),
        executor=flaky_executor,
        work_item_id=work_item.id,
    )
    assert second_pass[0].succeeded is True
    attempt = IngestionAttempt.objects.get(id=shell.id)
    assert attempt.state == AttemptState.READY
