"""Secure server-side session binding for anonymous workspaces."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime

from django.contrib.sessions.backends.base import SessionBase
from django.db import IntegrityError
from django.utils import timezone
from django.utils.crypto import salted_hmac

from reconciliation.domain import (
    ExpiryPolicy,
    WorkspaceAccess,
    WorkspaceId,
    WorkspaceState,
)

from .models import Workspace
from .repositories import WorkspaceRepository, WorkspaceUnavailable


SESSION_DIGEST_SALT = "reconciliation-workbench.workspace-session.v1"


def digest_session_key(session_key: str) -> str:
    return salted_hmac(SESSION_DIGEST_SALT, session_key, algorithm="sha256").hexdigest()


@dataclass(slots=True)
class WorkspaceSessionResolver:
    repository: WorkspaceRepository = field(default_factory=WorkspaceRepository)
    clock: Callable[[], datetime] = timezone.now
    expiry_policy: ExpiryPolicy = ExpiryPolicy()

    def resolve(self, session: SessionBase) -> WorkspaceAccess:
        existing = self._find_existing(session)
        if existing is not None:
            return self._authorize(existing)

        session.cycle_key()
        if session.session_key is None:
            raise RuntimeError("Session backend did not create a session key")
        digest = digest_session_key(session.session_key)
        now = self.clock()
        try:
            workspace = self.repository.create(
                session_digest=digest,
                created_at=now,
            )
        except IntegrityError:
            workspace = self.repository.find_by_session_digest(digest)
            if workspace is None:
                raise
        return self._authorize(workspace)

    def _find_existing(self, session: SessionBase) -> Workspace | None:
        if session.session_key is None:
            return None
        digest = digest_session_key(session.session_key)
        return self.repository.find_by_session_digest(digest)

    def _authorize(self, workspace: Workspace) -> WorkspaceAccess:
        lifecycle = self.expiry_policy.evaluate(
            state=WorkspaceState(workspace.state),
            expires_at=workspace.expires_at,
            now=self.clock(),
        )
        if not lifecycle.access_allowed:
            raise WorkspaceUnavailable
        return WorkspaceAccess(
            workspace_id=WorkspaceId(workspace.id),
            expires_at=workspace.expires_at,
        )
