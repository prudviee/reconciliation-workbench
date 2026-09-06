"""Reusable authorization guard for worker and service boundaries."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from reconciliation.domain import WorkspaceAccess, WorkspaceId

from .lifecycle import WorkspaceLifecycleService
from .repositories import WorkspaceRepository


@dataclass(slots=True)
class WorkspaceBoundaryGuard:
    repository: WorkspaceRepository = field(default_factory=WorkspaceRepository)
    lifecycle_service: WorkspaceLifecycleService = field(
        default_factory=WorkspaceLifecycleService
    )

    def require_active(
        self, workspace_id: WorkspaceId, *, now: datetime
    ) -> WorkspaceAccess:
        workspace = self.repository.get(workspace_id)
        self.lifecycle_service.require_active(workspace, now=now)
        return WorkspaceAccess(workspace_id=workspace_id, expires_at=workspace.expires_at)
