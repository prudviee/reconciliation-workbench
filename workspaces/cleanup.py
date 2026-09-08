"""Idempotent workspace purge: database rows first, then artifact bytes.

Every workspace-owned table across every app carries a direct `workspace`
ForeignKey with `on_delete=CASCADE` (verified by `test_architecture_constraints`
style inspection at the time this was written). Deleting the `Workspace` row
itself therefore purges everything it owns — books, sources, datasets,
observations, runs, decisions, cases, and the job-queue bookkeeping — in one
transaction, using Django's own dependency-graph collector rather than a
hand-maintained per-app deletion order.
"""

from __future__ import annotations

from django.db import transaction

from ingestion.models import FileArtifact
from ingestion.services import configured_artifact_store
from jobs.models import WorkItem
from jobs.services import TransientJobFailure
from reconciliation.domain import WorkspaceState

from .models import Workspace


class CleanupStateConflict(RuntimeError):
    """A workspace purge cannot proceed in its current state."""


def execute_claimed_cleanup(work_item: WorkItem, token) -> None:
    """A `jobs.services.claim_and_execute` executor for `JobKind.WORKSPACE_CLEANUP`."""
    if work_item.cleanup_request_id is None:
        raise LookupError("work item has no cleanup request target")
    try:
        purge_workspace(work_item.cleanup_request_id, attempt_token=str(token))
    except CleanupStateConflict as error:
        raise TransientJobFailure(str(error)) from error


def purge_workspace(
    workspace_id_value,
    *,
    attempt_token: str | None = None,
) -> bool:
    """Purge a revoked/deleted workspace. Returns False for an already-purged one.

    Redelivering a cleanup for a workspace that no longer exists is a
    documented no-op (`OPS-A07`) rather than an error: there is nothing left
    to verify a live reference against, and the artifact bytes for a
    genuinely already-purged workspace were already removed on the first
    successful delivery.
    """
    if not Workspace.objects.filter(id=workspace_id_value).exists():
        return False

    storage_keys = list(
        FileArtifact.objects.filter(workspace_id=workspace_id_value).values_list(
            "storage_key", flat=True
        )
    )

    with transaction.atomic():
        workspace = (
            Workspace.objects.select_for_update()
            .filter(id=workspace_id_value)
            .first()
        )
        if workspace is None:
            return False
        if workspace.state not in (WorkspaceState.REVOKED, WorkspaceState.DELETED):
            raise CleanupStateConflict(
                "workspace must be revoked or deleted before cleanup"
            )
        if attempt_token is not None:
            work_item = WorkItem.objects.select_for_update().get(
                cleanup_request_id=workspace_id_value
            )
            if work_item.current_token != attempt_token:
                raise CleanupStateConflict(
                    "a newer attempt has reclaimed this cleanup; "
                    "the fenced attempt cannot purge it"
                )
        workspace.delete()

    store = configured_artifact_store()
    for storage_key in storage_keys:
        store.delete_published(storage_key)
    return True
