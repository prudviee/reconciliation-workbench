from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest

from books.models import BookKind, ReconciliationBook
from ingestion.artifacts import IntakeLimits
from ingestion.models import FileArtifact
from ingestion.services import ArtifactIntakeService, configured_artifact_store
from jobs.models import WorkItem
from jobs.services import claim_and_execute, claim_one
from reconciliation.domain import JobKind, JobState, RetryPolicy, WorkspaceId, WorkspaceState
from workspaces.cleanup import CleanupStateConflict, execute_claimed_cleanup, purge_workspace
from workspaces.lifecycle import WorkspaceLifecycleService
from workspaces.models import Workspace, WorkspaceCleanupRequest


pytestmark = pytest.mark.django_db
NOW = datetime(2026, 9, 8, tzinfo=UTC)
LIMITS = IntakeLimits(10_000, 100, 20, 1_000)


@pytest.fixture(autouse=True)
def _local_artifact_root(settings, tmp_path: Path) -> None:
    settings.INGESTION_PRIVATE_ROOT = tmp_path


def _create_workspace(label: str) -> Workspace:
    return Workspace.objects.create(
        session_digest=hashlib.sha256(f"{label}-{uuid4()}".encode()).hexdigest(),
        created_at=NOW,
        expires_at=NOW + timedelta(days=7),
    )


def _upload_artifact(workspace: Workspace, label: str) -> FileArtifact:
    intake = ArtifactIntakeService(limits=LIMITS, clock=lambda: NOW)
    return intake.ingest(
        WorkspaceId(workspace.id),
        original_filename=f"{label}.csv",
        content_type="text/csv",
        delimiter=",",
        chunks=[b"a,b\n1,2\n"],
    )


def _retry_policy() -> RetryPolicy:
    return RetryPolicy(max_attempts=3, backoff=timedelta(seconds=5))


def test_deleting_a_workspace_enqueues_exactly_one_cleanup_work_item() -> None:
    workspace = _create_workspace("enqueue")

    WorkspaceLifecycleService().delete(WorkspaceId(workspace.id), now=NOW)

    cleanup = WorkspaceCleanupRequest.objects.get(workspace_id=workspace.id)
    item = WorkItem.objects.get(cleanup_request=cleanup)
    assert item.kind == JobKind.WORKSPACE_CLEANUP
    assert item.state == JobState.READY

    again = WorkspaceLifecycleService().delete(WorkspaceId(workspace.id), now=NOW)
    assert again.id == workspace.id
    assert WorkItem.objects.filter(cleanup_request=cleanup).count() == 1


def test_purge_removes_every_owned_row_and_the_artifact_bytes(tmp_path: Path) -> None:
    workspace = _create_workspace("purge")
    ReconciliationBook.objects.create(
        workspace=workspace, name="doomed book", kind=BookKind.USER, created_at=NOW
    )
    artifact = _upload_artifact(workspace, "purge")
    store = configured_artifact_store()
    bytes_path = store.resolve(artifact.storage_key)
    assert bytes_path.exists()

    WorkspaceLifecycleService().delete(WorkspaceId(workspace.id), now=NOW)
    purged = purge_workspace(workspace.id)

    assert purged is True
    assert not Workspace.objects.filter(id=workspace.id).exists()
    assert not ReconciliationBook.objects.filter(workspace_id=workspace.id).exists()
    assert not FileArtifact.objects.filter(workspace_id=workspace.id).exists()
    assert not bytes_path.exists()


def test_purge_leaves_other_workspaces_completely_untouched() -> None:
    victim = _create_workspace("victim")
    survivor = _create_workspace("survivor")
    ReconciliationBook.objects.create(
        workspace=survivor, name="safe book", kind=BookKind.USER, created_at=NOW
    )
    survivor_artifact = _upload_artifact(survivor, "survivor")
    store = configured_artifact_store()
    survivor_bytes = store.resolve(survivor_artifact.storage_key)

    WorkspaceLifecycleService().delete(WorkspaceId(victim.id), now=NOW)
    purge_workspace(victim.id)

    assert Workspace.objects.filter(id=survivor.id).exists()
    assert ReconciliationBook.objects.filter(workspace_id=survivor.id).exists()
    assert survivor_bytes.exists()


def test_redelivering_a_completed_cleanup_is_a_no_op() -> None:
    workspace = _create_workspace("redeliver")
    WorkspaceLifecycleService().delete(WorkspaceId(workspace.id), now=NOW)

    first = purge_workspace(workspace.id)
    second = purge_workspace(workspace.id)

    assert first is True
    assert second is False


def test_purge_refuses_a_workspace_that_is_still_active() -> None:
    workspace = _create_workspace("still-active")

    with pytest.raises(CleanupStateConflict):
        purge_workspace(workspace.id)

    assert Workspace.objects.filter(id=workspace.id, state=WorkspaceState.ACTIVE).exists()


def test_claim_and_execute_purges_through_the_job_queue() -> None:
    workspace = _create_workspace("claimed")
    artifact = _upload_artifact(workspace, "claimed")
    store = configured_artifact_store()
    bytes_path = store.resolve(artifact.storage_key)

    WorkspaceLifecycleService().delete(WorkspaceId(workspace.id), now=NOW)
    cleanup = WorkspaceCleanupRequest.objects.get(workspace_id=workspace.id)
    work_item = WorkItem.objects.get(cleanup_request=cleanup)

    records = claim_and_execute(
        JobKind.WORKSPACE_CLEANUP,
        now=NOW,
        lease_duration=timedelta(seconds=60),
        retry_policy=_retry_policy(),
        executor=execute_claimed_cleanup,
        work_item_id=work_item.id,
    )

    assert len(records) == 1
    assert records[0].succeeded is True
    assert not Workspace.objects.filter(id=workspace.id).exists()
    assert not bytes_path.exists()


def test_a_fenced_cleanup_attempt_cannot_purge_after_reclaim() -> None:
    workspace = _create_workspace("fenced-cleanup")
    WorkspaceLifecycleService().delete(WorkspaceId(workspace.id), now=NOW)
    cleanup = WorkspaceCleanupRequest.objects.get(workspace_id=workspace.id)
    work_item = WorkItem.objects.get(cleanup_request=cleanup)

    first = claim_one(work_item.id, now=NOW, lease_duration=timedelta(seconds=10))
    second = claim_one(
        work_item.id,
        now=NOW + timedelta(seconds=11),
        lease_duration=timedelta(seconds=10),
    )
    assert second is not None

    with pytest.raises(CleanupStateConflict):
        purge_workspace(workspace.id, attempt_token=str(first.token))

    assert Workspace.objects.filter(id=workspace.id).exists()

    purged = purge_workspace(workspace.id, attempt_token=str(second.token))
    assert purged is True
