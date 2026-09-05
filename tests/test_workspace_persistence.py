from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from uuid import uuid4

import pytest
from django.db import IntegrityError, connection, transaction

from books.models import BookKind, ReconciliationBook
from books.repositories import BookUnavailable, WorkspaceBookRepository
from reconciliation.domain import BookId, WorkspaceId, WorkspaceState
from workspaces.models import Workspace
from workspaces.repositories import WorkspaceRepository


pytestmark = pytest.mark.django_db


def create_workspace(*, digest: str, hour: int = 10) -> Workspace:
    return WorkspaceRepository().create(
        session_digest=digest,
        created_at=datetime(2026, 9, 5, hour, tzinfo=UTC),
    )


def test_workspace_creation_persists_fixed_expiry_and_zero_usage() -> None:
    workspace = create_workspace(digest="a" * 64)

    assert workspace.state == WorkspaceState.ACTIVE
    assert workspace.expires_at == workspace.created_at + timedelta(days=7)
    assert workspace.retained_bytes == 0
    assert workspace.book_count == 0
    assert workspace.active_job_count == 0


def test_workspace_creation_normalizes_lifecycle_instants_to_utc() -> None:
    created_at = datetime(
        2026, 9, 5, 15, 30, tzinfo=timezone(timedelta(hours=5, minutes=30))
    )

    workspace = WorkspaceRepository().create(
        session_digest="9" * 64,
        created_at=created_at,
    )

    assert workspace.created_at == datetime(2026, 9, 5, 10, tzinfo=UTC)
    assert workspace.expires_at == datetime(2026, 9, 12, 10, tzinfo=UTC)


def test_database_refuses_duplicate_session_digest() -> None:
    create_workspace(digest="b" * 64)

    with pytest.raises(IntegrityError), transaction.atomic():
        create_workspace(digest="b" * 64, hour=11)


def test_database_enforces_fixed_expiry_and_nonnegative_counters() -> None:
    created_at = datetime(2026, 9, 5, 10, tzinfo=UTC)

    with pytest.raises(IntegrityError), transaction.atomic():
        Workspace.objects.create(
            session_digest="c" * 64,
            state=WorkspaceState.ACTIVE,
            created_at=created_at,
            expires_at=created_at + timedelta(days=8),
        )

    with pytest.raises(IntegrityError), transaction.atomic():
        Workspace.objects.create(
            session_digest="d" * 64,
            state=WorkspaceState.ACTIVE,
            created_at=created_at,
            expires_at=created_at + timedelta(days=7),
            retained_bytes=-1,
        )


def test_book_creation_binds_owner_and_preserves_independent_books() -> None:
    owner = create_workspace(digest="e" * 64)
    repository = WorkspaceBookRepository(WorkspaceId(owner.id))
    created_at = datetime(2026, 9, 5, 12, tzinfo=UTC)

    uploaded = repository.create_user_book(name="August statements", created_at=created_at)
    demo = repository.create_demo_book(
        name="Demo: card to ledger",
        sample_template_version="2026.09-v1",
        created_at=created_at + timedelta(seconds=1),
    )

    assert uploaded.workspace_id == owner.id
    assert uploaded.kind == BookKind.USER
    assert uploaded.sample_template_version is None
    assert demo.workspace_id == owner.id
    assert demo.kind == BookKind.DEMO
    assert demo.sample_template_version == "2026.09-v1"
    assert [book.id for book in repository.list()] == [uploaded.id, demo.id]


def test_database_rejects_book_without_existing_owner() -> None:
    with pytest.raises(IntegrityError), transaction.atomic():
        ReconciliationBook.objects.create(
            workspace_id=uuid4(),
            name="Orphan",
            kind=BookKind.USER,
            created_at=datetime(2026, 9, 5, tzinfo=UTC),
        )
        connection.check_constraints(table_names=["reconciliation_book"])


@pytest.mark.parametrize(
    ("name", "kind", "sample_template_version"),
    [
        ("", BookKind.USER, None),
        ("User upload", BookKind.USER, "unexpected-template"),
        ("Demo", BookKind.DEMO, None),
    ],
)
def test_database_rejects_invalid_book_shape(
    name: str, kind: BookKind, sample_template_version: str | None
) -> None:
    owner = create_workspace(digest=uuid4().hex * 2)

    with pytest.raises(IntegrityError), transaction.atomic():
        ReconciliationBook.objects.create(
            workspace=owner,
            name=name,
            kind=kind,
            sample_template_version=sample_template_version,
            created_at=datetime(2026, 9, 5, tzinfo=UTC),
        )


def test_owner_can_read_rename_and_delete_book() -> None:
    owner = create_workspace(digest="f" * 64)
    repository = WorkspaceBookRepository(WorkspaceId(owner.id))
    book = repository.create_user_book(
        name="Original", created_at=datetime(2026, 9, 5, tzinfo=UTC)
    )
    book_id = BookId(book.id)

    assert repository.get(book_id).name == "Original"
    assert repository.rename(book_id, name="Renamed").name == "Renamed"
    repository.delete(book_id)

    with pytest.raises(BookUnavailable):
        repository.get(book_id)


@pytest.mark.parametrize("operation", ["get", "rename", "delete"])
@pytest.mark.parametrize("target", ["foreign", "random"])
def test_foreign_and_random_book_ids_have_identical_scoped_failure(
    operation: str, target: str
) -> None:
    owner = create_workspace(digest="1" * 64)
    outsider = create_workspace(digest="2" * 64, hour=11)
    owner_repository = WorkspaceBookRepository(WorkspaceId(owner.id))
    outsider_repository = WorkspaceBookRepository(WorkspaceId(outsider.id))
    book = owner_repository.create_user_book(
        name="Private book", created_at=datetime(2026, 9, 5, tzinfo=UTC)
    )
    target_id = BookId(book.id if target == "foreign" else uuid4())

    with pytest.raises(BookUnavailable):
        if operation == "get":
            outsider_repository.get(target_id)
        elif operation == "rename":
            outsider_repository.rename(target_id, name="Intrusion")
        else:
            outsider_repository.delete(target_id)

    book.refresh_from_db()
    assert book.name == "Private book"


def test_workspace_lists_and_counts_never_include_foreign_books() -> None:
    owner = create_workspace(digest="3" * 64)
    outsider = create_workspace(digest="4" * 64, hour=11)
    owner_repository = WorkspaceBookRepository(WorkspaceId(owner.id))
    outsider_repository = WorkspaceBookRepository(WorkspaceId(outsider.id))
    created_at = datetime(2026, 9, 5, tzinfo=UTC)

    private_book = owner_repository.create_user_book(
        name="Owner only", created_at=created_at
    )
    outsider_repository.create_user_book(name="Outsider only", created_at=created_at)

    assert [book.id for book in owner_repository.list()] == [private_book.id]
    assert owner_repository.count() == 1
    assert outsider_repository.count() == 1


def test_scoped_lookup_query_contains_workspace_and_public_id() -> None:
    workspace_id = WorkspaceId(uuid4())
    book_id = BookId(uuid4())
    query = str(
        ReconciliationBook.objects.owned_by(workspace_id).filter(id=book_id.value).query
    )

    assert '"reconciliation_book"."workspace_id"' in query
    assert '"reconciliation_book"."id"' in query


def test_schema_contains_ownership_and_cleanup_indexes() -> None:
    with connection.cursor() as cursor:
        constraints = connection.introspection.get_constraints(cursor, "workspace")
        book_constraints = connection.introspection.get_constraints(
            cursor, "reconciliation_book"
        )

    assert constraints["workspace_session_digest_key"]["unique"] is True
    assert constraints["workspace_state_expiry_idx"]["index"] is True
    assert constraints["workspace_fixed_expiry_7d"]["check"] is True
    assert book_constraints["book_workspace_public_idx"]["index"] is True
    ownership_foreign_keys = [
        details
        for details in book_constraints.values()
        if details["foreign_key"] == ("workspace", "id")
    ]
    assert len(ownership_foreign_keys) == 1
