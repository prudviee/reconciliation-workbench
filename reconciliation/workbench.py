"""Workspace-scoped preparation and read projections for the browser workbench."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable
from uuid import UUID

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from books.models import PolicyRevision, ReconciliationBook, ReconciliationScope
from cases.queries import CaseListItem, CaseQueryService
from ingestion.models import Dataset
from reconciliation.domain import (
    BookId,
    ComparisonPolicy,
    MatchingPolicy,
    WorkspaceId,
    policy_revision_digest,
)
from reconciliation.models import ReconciliationRun
from reconciliation.policies import comparison_policy_to_payload, matching_policy_to_payload
from reconciliation.querying import ReviewPage, ReviewQueryUnavailable
from sources.models import SourceRole
from workspaces.lifecycle import WorkspaceLifecycleService
from workspaces.models import Workspace
from workspaces.repositories import WorkspaceUnavailable


class WorkbenchUnavailable(LookupError):
    """The requested workbench resource is unavailable in this workspace."""


class WorkbenchNotReady(RuntimeError):
    def __init__(self, missing_sides: tuple[str, ...]):
        self.missing_sides = missing_sides
        super().__init__("Both source datasets must be active before reconciliation.")


@dataclass(frozen=True, slots=True)
class WorkbenchReadiness:
    ready: bool
    missing_sides: tuple[str, ...]
    left_dataset_id: UUID | None
    right_dataset_id: UUID | None
    scope_id: UUID | None
    policy_revision_id: UUID | None


@dataclass(frozen=True, slots=True)
class WorkbenchRunItem:
    run_id: UUID
    lifecycle: str
    freshness: str
    result_counts: dict | None
    created_at: datetime
    completed_at: datetime | None
    is_current: bool


@dataclass(frozen=True, slots=True)
class WorkbenchSnapshot:
    book_id: UUID
    book_name: str
    readiness: WorkbenchReadiness
    scope_is_dirty: bool
    resolution_generation: int
    current_run_id: UUID | None
    selected_run: WorkbenchRunItem | None
    runs: tuple[WorkbenchRunItem, ...]
    current_cases: ReviewPage[CaseListItem]


@dataclass(slots=True)
class WorkbenchService:
    clock: Callable[[], datetime] = timezone.now
    lifecycle_service: WorkspaceLifecycleService = field(
        default_factory=WorkspaceLifecycleService
    )

    def readiness(
        self,
        workspace_id: WorkspaceId,
        *,
        book_id: BookId,
    ) -> WorkbenchReadiness:
        book = self._book(workspace_id, book_id)
        datasets = self._active_datasets(workspace_id, book)
        missing = tuple(
            role.value
            for role in (SourceRole.LEFT, SourceRole.RIGHT)
            if role not in datasets
        )
        scope = (
            ReconciliationScope.objects.owned_by(workspace_id)
            .filter(book=book, coverage_key="default")
            .first()
        )
        policy = (
            PolicyRevision.objects.owned_by(workspace_id)
            .filter(book=book)
            .order_by("-revision", "-id")
            .first()
        )
        return WorkbenchReadiness(
            ready=not missing,
            missing_sides=missing,
            left_dataset_id=(datasets.get(SourceRole.LEFT).id if SourceRole.LEFT in datasets else None),
            right_dataset_id=(datasets.get(SourceRole.RIGHT).id if SourceRole.RIGHT in datasets else None),
            scope_id=scope.id if scope is not None else None,
            policy_revision_id=policy.id if policy is not None else None,
        )

    def ensure_run_context(
        self,
        workspace_id: WorkspaceId,
        *,
        book_id: BookId,
    ) -> ReconciliationScope:
        self._active_workspace(workspace_id)
        with transaction.atomic():
            try:
                book = (
                    ReconciliationBook.objects.owned_by(workspace_id)
                    .select_for_update()
                    .get(id=book_id.value)
                )
            except ReconciliationBook.DoesNotExist as error:
                raise WorkbenchUnavailable from error
            datasets = self._active_datasets(workspace_id, book)
            missing = tuple(
                role.value
                for role in (SourceRole.LEFT, SourceRole.RIGHT)
                if role not in datasets
            )
            if missing:
                raise WorkbenchNotReady(missing)
            scope, _created = ReconciliationScope.objects.get_or_create(
                workspace_id=workspace_id.value,
                book=book,
                coverage_key="default",
                defaults={
                    "left_dataset": datasets[SourceRole.LEFT],
                    "right_dataset": datasets[SourceRole.RIGHT],
                    "generation": 0,
                    "is_dirty": True,
                    "created_at": self.clock(),
                },
            )
            if (
                scope.left_dataset_id != datasets[SourceRole.LEFT].id
                or scope.right_dataset_id != datasets[SourceRole.RIGHT].id
            ):
                raise WorkbenchUnavailable
            policy = (
                PolicyRevision.objects.owned_by(workspace_id)
                .filter(book=book)
                .order_by("-revision", "-id")
                .first()
            )
            if policy is None:
                matching = matching_policy_to_payload(MatchingPolicy.initial_demo())
                comparison = comparison_policy_to_payload(ComparisonPolicy.initial_demo())
                PolicyRevision.objects.create(
                    workspace_id=workspace_id.value,
                    book=book,
                    revision=1,
                    matching_policy=matching,
                    comparison_policy=comparison,
                    digest=policy_revision_digest(
                        matching_policy=matching,
                        comparison_policy=comparison,
                    ),
                    created_at=self.clock(),
                )
                ReconciliationBook.objects.filter(id=book.id).update(
                    generation=F("generation") + 1
                )
                ReconciliationScope.objects.filter(id=scope.id).update(
                    generation=F("generation") + 1,
                    is_dirty=True,
                )
                scope.refresh_from_db()
            return scope

    def snapshot(
        self,
        workspace_id: WorkspaceId,
        *,
        book_id: BookId,
        selected_run_id: UUID | str | None = None,
        case_cursor: str | None = None,
        page_size: int = 50,
    ) -> WorkbenchSnapshot:
        book = self._book(workspace_id, book_id)
        state = self.readiness(workspace_id, book_id=book_id)
        empty_cases: ReviewPage[CaseListItem] = ReviewPage((), None)
        if state.scope_id is None:
            return WorkbenchSnapshot(
                book.id,
                book.name,
                state,
                True,
                book.resolution_generation,
                None,
                None,
                (),
                empty_cases,
            )
        try:
            scope = (
                ReconciliationScope.objects.owned_by(workspace_id)
                .select_related("current_run")
                .get(id=state.scope_id, book=book)
            )
        except ReconciliationScope.DoesNotExist as error:
            raise WorkbenchUnavailable from error
        runs = tuple(
            ReconciliationRun.objects.owned_by(workspace_id)
            .filter(scope=scope)
            .order_by("-created_at", "-id")[:50]
        )
        selected_id = self._optional_id(selected_run_id) or scope.current_run_id
        selected_model = None
        if selected_id is not None:
            selected_model = next((item for item in runs if item.id == selected_id), None)
            if selected_model is None:
                try:
                    selected_model = ReconciliationRun.objects.owned_by(workspace_id).get(
                        id=selected_id,
                        scope=scope,
                    )
                except ReconciliationRun.DoesNotExist as error:
                    raise WorkbenchUnavailable from error
        run_items = tuple(self._run_item(item, scope.current_run_id) for item in runs)
        current_cases = empty_cases
        if scope.current_run_id is not None:
            try:
                current_cases = CaseQueryService(
                    clock=self.clock,
                    lifecycle_service=self.lifecycle_service,
                ).list_cases(
                    workspace_id,
                    book_id=book_id,
                    scope_id=scope.id,
                    cursor=case_cursor,
                    page_size=page_size,
                )
            except ReviewQueryUnavailable as error:
                raise WorkbenchUnavailable from error
        return WorkbenchSnapshot(
            book_id=book.id,
            book_name=book.name,
            readiness=state,
            scope_is_dirty=scope.is_dirty,
            resolution_generation=book.resolution_generation,
            current_run_id=scope.current_run_id,
            selected_run=(
                self._run_item(selected_model, scope.current_run_id)
                if selected_model is not None
                else None
            ),
            runs=run_items,
            current_cases=current_cases,
        )

    def _book(self, workspace_id: WorkspaceId, book_id: BookId) -> ReconciliationBook:
        self._active_workspace(workspace_id)
        try:
            return ReconciliationBook.objects.owned_by(workspace_id).get(id=book_id.value)
        except ReconciliationBook.DoesNotExist as error:
            raise WorkbenchUnavailable from error

    def _active_workspace(self, workspace_id: WorkspaceId) -> Workspace:
        try:
            workspace = Workspace.objects.get(id=workspace_id.value)
            self.lifecycle_service.require_active(workspace, now=self.clock())
            return workspace
        except (Workspace.DoesNotExist, WorkspaceUnavailable) as error:
            raise WorkbenchUnavailable from error

    @staticmethod
    def _active_datasets(
        workspace_id: WorkspaceId,
        book: ReconciliationBook,
    ) -> dict[SourceRole, Dataset]:
        rows = (
            Dataset.objects.owned_by(workspace_id)
            .filter(
                book_source__book=book,
                coverage_key="default",
                current_revision__isnull=False,
            )
            .select_related("book_source", "current_revision")
        )
        return {SourceRole(item.book_source.role): item for item in rows}

    @staticmethod
    def _optional_id(value: UUID | str | None) -> UUID | None:
        if value is None or value == "":
            return None
        try:
            return value if isinstance(value, UUID) else UUID(value)
        except (TypeError, ValueError) as error:
            raise WorkbenchUnavailable from error

    @staticmethod
    def _run_item(run: ReconciliationRun, current_run_id: UUID | None) -> WorkbenchRunItem:
        return WorkbenchRunItem(
            run_id=run.id,
            lifecycle=run.lifecycle,
            freshness=run.freshness,
            result_counts=dict(run.result_counts) if run.result_counts is not None else None,
            created_at=run.created_at,
            completed_at=run.completed_at,
            is_current=run.id == current_run_id,
        )
