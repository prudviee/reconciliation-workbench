"""Transactional persistence for anonymous-workspace quota reservations."""

from __future__ import annotations

from dataclasses import dataclass, field

from django.conf import settings
from django.db import transaction

from reconciliation.domain import QuotaAmounts, QuotaPolicy, WorkspaceId

from .models import Workspace
from .repositories import WorkspaceUnavailable


class QuotaReleaseConflict(RuntimeError):
    """A release would make a persisted quota counter negative."""


def configured_quota_policy() -> QuotaPolicy:
    return QuotaPolicy(
        QuotaAmounts(
            retained_bytes=settings.WORKSPACE_RETAINED_BYTES_LIMIT,
            books=settings.WORKSPACE_BOOK_LIMIT,
            active_jobs=settings.WORKSPACE_ACTIVE_JOB_LIMIT,
        )
    )


@dataclass(slots=True)
class WorkspaceQuotaService:
    policy: QuotaPolicy = field(default_factory=configured_quota_policy)

    def reserve(
        self, workspace_id: WorkspaceId, requested: QuotaAmounts
    ) -> QuotaAmounts:
        with transaction.atomic():
            workspace = self._locked_workspace(workspace_id)
            resulting = self.policy.reserve(
                usage=self._usage(workspace),
                requested=requested,
            )
            self._persist(workspace, resulting)
            return resulting

    def release(
        self, workspace_id: WorkspaceId, released: QuotaAmounts
    ) -> QuotaAmounts:
        with transaction.atomic():
            workspace = self._locked_workspace(workspace_id)
            usage = self._usage(workspace)
            values = (
                usage.retained_bytes - released.retained_bytes,
                usage.books - released.books,
                usage.active_jobs - released.active_jobs,
            )
            if any(value < 0 for value in values):
                raise QuotaReleaseConflict("quota release exceeds current usage")
            resulting = QuotaAmounts(*values)
            self._persist(workspace, resulting)
            return resulting

    @staticmethod
    def _locked_workspace(workspace_id: WorkspaceId) -> Workspace:
        try:
            return Workspace.objects.select_for_update().get(id=workspace_id.value)
        except Workspace.DoesNotExist as error:
            raise WorkspaceUnavailable from error

    @staticmethod
    def _usage(workspace: Workspace) -> QuotaAmounts:
        return QuotaAmounts(
            retained_bytes=workspace.retained_bytes,
            books=workspace.book_count,
            active_jobs=workspace.active_job_count,
        )

    @staticmethod
    def _persist(workspace: Workspace, usage: QuotaAmounts) -> None:
        workspace.retained_bytes = usage.retained_bytes
        workspace.book_count = usage.books
        workspace.active_job_count = usage.active_jobs
        workspace.save(
            update_fields=["retained_bytes", "book_count", "active_job_count"]
        )
