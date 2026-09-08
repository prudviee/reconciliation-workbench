"""Synchronous workspace revocation and durable cleanup signalling."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from django.db import transaction

from django.conf import settings

from reconciliation.domain import ExpiryPolicy, JobKind, WorkspaceId, WorkspaceState

from .models import CleanupReason, Workspace, WorkspaceCleanupRequest
from .repositories import WorkspaceUnavailable


@dataclass(frozen=True, slots=True)
class WorkspaceLifecycleService:
    expiry_policy: ExpiryPolicy = ExpiryPolicy()

    def expire(self, workspace_id: WorkspaceId, *, now: datetime) -> Workspace:
        return self._revoke(
            workspace_id,
            now=now,
            final_state=WorkspaceState.REVOKED,
            reason=CleanupReason.EXPIRED,
        )

    def delete(self, workspace_id: WorkspaceId, *, now: datetime) -> Workspace:
        return self._revoke(
            workspace_id,
            now=now,
            final_state=WorkspaceState.DELETED,
            reason=CleanupReason.DELETED,
        )

    def require_active(self, workspace: Workspace, *, now: datetime) -> None:
        result = self.expiry_policy.evaluate(
            state=WorkspaceState(workspace.state),
            expires_at=workspace.expires_at,
            now=now,
        )
        if result.requires_revocation:
            self.expire(WorkspaceId(workspace.id), now=now)
        if not result.access_allowed:
            raise WorkspaceUnavailable

    def _revoke(
        self,
        workspace_id: WorkspaceId,
        *,
        now: datetime,
        final_state: WorkspaceState,
        reason: CleanupReason,
    ) -> Workspace:
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("now must be timezone-aware")
        revoked_at = now.astimezone(UTC)
        with transaction.atomic():
            try:
                workspace = Workspace.objects.select_for_update().get(
                    id=workspace_id.value
                )
            except Workspace.DoesNotExist as error:
                raise WorkspaceUnavailable from error

            if final_state is WorkspaceState.DELETED:
                if workspace.revoked_at is None:
                    workspace.revoked_at = revoked_at
                if workspace.deleted_at is None:
                    workspace.deleted_at = revoked_at
                workspace.state = WorkspaceState.DELETED
                update_fields = ["state", "revoked_at", "deleted_at"]
            elif workspace.state == WorkspaceState.ACTIVE:
                workspace.state = WorkspaceState.REVOKED
                workspace.revoked_at = revoked_at
                update_fields = ["state", "revoked_at"]
            else:
                update_fields = []

            if update_fields:
                workspace.save(update_fields=update_fields)

            cleanup, created = WorkspaceCleanupRequest.objects.get_or_create(
                workspace=workspace,
                defaults={"reason": reason, "requested_at": revoked_at},
            )
            if not created and reason == CleanupReason.DELETED:
                cleanup.reason = reason
                cleanup.save(update_fields=["reason"])

            from jobs.models import WorkItem

            WorkItem.objects.get_or_create(
                cleanup_request=cleanup,
                defaults={
                    "workspace_id": workspace_id.value,
                    "kind": JobKind.WORKSPACE_CLEANUP,
                    "max_attempts": settings.JOBS_CLEANUP_MAX_ATTEMPTS,
                    "available_at": revoked_at,
                    "created_at": revoked_at,
                    "updated_at": revoked_at,
                },
            )
            return workspace
