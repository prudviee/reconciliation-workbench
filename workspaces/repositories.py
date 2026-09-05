"""Persistence operations for workspaces."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from django.db import transaction

from reconciliation.domain import ExpiryPolicy, WorkspaceId, WorkspaceState

from .models import Workspace


class WorkspaceUnavailable(LookupError):
    """The requested workspace is unavailable to the caller."""


@dataclass(frozen=True, slots=True)
class WorkspaceRepository:
    expiry_policy: ExpiryPolicy = ExpiryPolicy()

    def create(self, *, session_digest: str, created_at: datetime) -> Workspace:
        expires_at = self.expiry_policy.expires_at(created_at)
        created_at_utc = created_at.astimezone(UTC)
        with transaction.atomic():
            return Workspace.objects.create(
                session_digest=session_digest,
                state=WorkspaceState.ACTIVE,
                created_at=created_at_utc,
                expires_at=expires_at,
            )

    def get(self, workspace_id: WorkspaceId) -> Workspace:
        try:
            return Workspace.objects.get(id=workspace_id.value)
        except Workspace.DoesNotExist as error:
            raise WorkspaceUnavailable from error
