from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Barrier

import pytest
from django.db import IntegrityError, close_old_connections, transaction
from django.test import override_settings

from books.models import ReconciliationBook
from books.repositories import BookUnavailable, WorkspaceBookRepository
from reconciliation.domain import (
    BookId,
    QuotaAmounts,
    QuotaExceeded,
    QuotaPolicy,
    QuotaResource,
    WorkspaceId,
)
from workspaces.models import Workspace
from workspaces.quotas import WorkspaceQuotaService, configured_quota_policy
from workspaces.repositories import WorkspaceRepository


def create_workspace() -> Workspace:
    return WorkspaceRepository().create(
        session_digest="a" * 64,
        created_at=datetime(2026, 9, 5, tzinfo=UTC),
    )


def requested_amount(resource: QuotaResource, value: int = 1) -> QuotaAmounts:
    return QuotaAmounts(**{resource.value: value})


@override_settings(
    WORKSPACE_RETAINED_BYTES_LIMIT=123,
    WORKSPACE_BOOK_LIMIT=4,
    WORKSPACE_ACTIVE_JOB_LIMIT=5,
)
def test_quota_limits_are_configuration_driven() -> None:
    assert configured_quota_policy().limits == QuotaAmounts(123, 4, 5)


@pytest.mark.django_db
def test_reservations_update_each_persisted_counter() -> None:
    workspace = create_workspace()
    service = WorkspaceQuotaService(
        QuotaPolicy(QuotaAmounts(retained_bytes=100, books=10, active_jobs=2))
    )

    resulting = service.reserve(
        WorkspaceId(workspace.id),
        QuotaAmounts(retained_bytes=25, books=2, active_jobs=1),
    )

    workspace.refresh_from_db()
    assert resulting == QuotaAmounts(retained_bytes=25, books=2, active_jobs=1)
    assert workspace.retained_bytes == 25
    assert workspace.book_count == 2
    assert workspace.active_job_count == 1


@pytest.mark.django_db
@pytest.mark.parametrize(
    "resource",
    [
        QuotaResource.RETAINED_BYTES,
        QuotaResource.BOOKS,
        QuotaResource.ACTIVE_JOBS,
    ],
)
def test_at_limit_refusal_preserves_all_persisted_counters(
    resource: QuotaResource,
) -> None:
    workspace = create_workspace()
    service = WorkspaceQuotaService(QuotaPolicy(QuotaAmounts(1, 1, 1)))
    workspace_id = WorkspaceId(workspace.id)
    service.reserve(workspace_id, requested_amount(resource))
    workspace.refresh_from_db()
    before = (
        workspace.retained_bytes,
        workspace.book_count,
        workspace.active_job_count,
    )

    with pytest.raises(QuotaExceeded) as captured:
        service.reserve(workspace_id, requested_amount(resource))

    workspace.refresh_from_db()
    assert captured.value.resource is resource
    assert captured.value.current == 1
    assert captured.value.requested == 1
    assert captured.value.limit == 1
    assert str(captured.value) == (
        f"{resource.value} quota exceeded: current=1, requested=1, limit=1"
    )
    assert (
        workspace.retained_bytes,
        workspace.book_count,
        workspace.active_job_count,
    ) == before


@pytest.mark.django_db
def test_book_and_counter_commit_and_release_together() -> None:
    workspace = create_workspace()
    service = WorkspaceQuotaService(QuotaPolicy(QuotaAmounts(100, 1, 2)))
    repository = WorkspaceBookRepository(WorkspaceId(workspace.id), service)
    created_at = datetime(2026, 9, 5, tzinfo=UTC)

    first = repository.create_user_book(name="First", created_at=created_at)
    with pytest.raises(QuotaExceeded) as captured:
        repository.create_user_book(name="Second", created_at=created_at)

    workspace.refresh_from_db()
    assert captured.value.resource is QuotaResource.BOOKS
    assert workspace.book_count == 1
    assert list(ReconciliationBook.objects.values_list("id", flat=True)) == [first.id]

    repository.delete(BookId(first.id))
    workspace.refresh_from_db()
    assert workspace.book_count == 0
    assert ReconciliationBook.objects.count() == 0


@pytest.mark.django_db
def test_missing_delete_preserves_existing_book_and_counter() -> None:
    workspace = create_workspace()
    repository = WorkspaceBookRepository(WorkspaceId(workspace.id))
    existing = repository.create_user_book(
        name="Existing",
        created_at=datetime(2026, 9, 5, tzinfo=UTC),
    )

    with pytest.raises(BookUnavailable):
        repository.delete(BookId.parse("1cf76754-8a30-4396-9864-076c285d5534"))

    workspace.refresh_from_db()
    assert workspace.book_count == 1
    assert ReconciliationBook.objects.get().id == existing.id


@pytest.mark.django_db
def test_failed_book_insert_rolls_back_quota_reservation() -> None:
    workspace = create_workspace()
    repository = WorkspaceBookRepository(WorkspaceId(workspace.id))

    with pytest.raises(IntegrityError), transaction.atomic():
        repository.create_user_book(
            name="",
            created_at=datetime(2026, 9, 5, tzinfo=UTC),
        )

    workspace.refresh_from_db()
    assert workspace.book_count == 0
    assert ReconciliationBook.objects.count() == 0


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(
    "resource",
    [
        QuotaResource.RETAINED_BYTES,
        QuotaResource.BOOKS,
        QuotaResource.ACTIVE_JOBS,
    ],
)
def test_concurrent_reservations_never_exceed_capacity(
    resource: QuotaResource,
) -> None:
    workspace = create_workspace()
    workspace_id = WorkspaceId(workspace.id)
    workers = 6
    capacity = 2
    barrier = Barrier(workers)
    policy = QuotaPolicy(QuotaAmounts(capacity, capacity, capacity))

    def attempt_reservation() -> str:
        close_old_connections()
        try:
            barrier.wait(timeout=10)
            WorkspaceQuotaService(policy).reserve(
                workspace_id,
                requested_amount(resource),
            )
            return "reserved"
        except QuotaExceeded as error:
            assert error.resource is resource
            return "refused"
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=workers) as executor:
        outcomes = list(executor.map(lambda _: attempt_reservation(), range(workers)))

    workspace.refresh_from_db()
    persisted = {
        QuotaResource.RETAINED_BYTES: workspace.retained_bytes,
        QuotaResource.BOOKS: workspace.book_count,
        QuotaResource.ACTIVE_JOBS: workspace.active_job_count,
    }
    assert outcomes.count("reserved") == capacity
    assert outcomes.count("refused") == workers - capacity
    assert persisted[resource] == capacity
