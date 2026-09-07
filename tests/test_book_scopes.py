from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from books.models import (
    BookKind,
    ImmutableBookEvidenceError,
    PolicyRevision,
    ReconciliationBook,
    ReconciliationScope,
)
from books.scopes import (
    BookGenerationConflict,
    PolicyUnavailable,
    ScopeUnavailable,
    WorkspacePolicyRepository,
    WorkspaceScopeRepository,
)
from ingestion.models import Dataset
from reconciliation.domain import BookId, WorkspaceId, policy_revision_digest
from sources.models import BookSource, SourceRole, SourceSystem
from workspaces.models import Workspace


pytestmark = pytest.mark.django_db
NOW = datetime(2026, 9, 7, 18, tzinfo=UTC)
MATCHING = {
    "version": "demo-matching-v1",
    "assignment_floor_bp": 7000,
    "automatic_threshold_bp": 9000,
}
COMPARISON = {
    "version": "demo-comparison-v1",
    "quantity_absolute": "0",
    "timestamp_seconds": 60,
}


def create_workspace(name: str) -> Workspace:
    return Workspace.objects.create(
        session_digest=(name.encode().hex() + uuid4().hex * 2)[:64],
        created_at=NOW,
        expires_at=NOW + timedelta(days=7),
    )


def create_book_graph(
    workspace: Workspace,
    *,
    name: str = "September close",
) -> tuple[ReconciliationBook, Dataset, Dataset]:
    book = ReconciliationBook.objects.create(
        workspace=workspace,
        name=name,
        kind=BookKind.USER,
        created_at=NOW,
    )
    left_source = SourceSystem.objects.create(
        workspace=workspace,
        name=f"{name} ledger",
        adapter_key="ledger-v1",
        created_at=NOW,
    )
    right_source = SourceSystem.objects.create(
        workspace=workspace,
        name=f"{name} counterparty",
        adapter_key="counterparty-v1",
        created_at=NOW,
    )
    left_book_source = BookSource.objects.create(
        workspace=workspace,
        book=book,
        source=left_source,
        role=SourceRole.LEFT,
        identity_namespace=f"{name}-left",
        created_at=NOW,
    )
    right_book_source = BookSource.objects.create(
        workspace=workspace,
        book=book,
        source=right_source,
        role=SourceRole.RIGHT,
        identity_namespace=f"{name}-right",
        created_at=NOW,
    )
    left = Dataset.objects.create(
        workspace=workspace,
        book_source=left_book_source,
        coverage_key="2026-09",
        created_at=NOW,
    )
    right = Dataset.objects.create(
        workspace=workspace,
        book_source=right_book_source,
        coverage_key="2026-09",
        created_at=NOW,
    )
    return book, left, right


def test_scope_repository_requires_owned_book_datasets_and_roles() -> None:
    owner = create_workspace("owner")
    outsider = create_workspace("outsider")
    book, left, right = create_book_graph(owner)
    foreign_book, foreign_left, foreign_right = create_book_graph(
        outsider, name="Foreign"
    )
    repository = WorkspaceScopeRepository(WorkspaceId(owner.id))

    scope = repository.create(
        book_id=BookId(book.id),
        coverage_key=" 2026-09 ",
        left_dataset_id=left.id,
        right_dataset_id=right.id,
        created_at=NOW,
    )

    assert scope.coverage_key == "2026-09"
    assert scope.generation == 0
    assert scope.is_dirty
    assert repository.get(scope.id).id == scope.id
    assert repository.list(BookId(book.id)) == (scope,)

    invalid_pairs = (
        (right.id, left.id),
        (left.id, foreign_right.id),
        (foreign_left.id, foreign_right.id),
    )
    for left_id, right_id in invalid_pairs:
        with pytest.raises(ScopeUnavailable):
            repository.create(
                book_id=BookId(book.id),
                coverage_key=str(uuid4()),
                left_dataset_id=left_id,
                right_dataset_id=right_id,
                created_at=NOW,
            )
    with pytest.raises(ScopeUnavailable):
        repository.list(BookId(foreign_book.id))


def test_policy_revision_is_immutable_versioned_and_advances_data_generation() -> None:
    workspace = create_workspace("policy")
    book, left, right = create_book_graph(workspace)
    scope = WorkspaceScopeRepository(WorkspaceId(workspace.id)).create(
        book_id=BookId(book.id),
        coverage_key="2026-09",
        left_dataset_id=left.id,
        right_dataset_id=right.id,
        created_at=NOW,
    )
    ReconciliationScope.objects.filter(id=scope.id).update(is_dirty=False)
    repository = WorkspacePolicyRepository(WorkspaceId(workspace.id))

    first = repository.create_revision(
        book_id=BookId(book.id),
        expected_generation=0,
        matching_policy=MATCHING,
        comparison_policy=COMPARISON,
        created_at=NOW,
    )

    book.refresh_from_db()
    scope.refresh_from_db()
    assert first.revision == 1
    assert first.digest == policy_revision_digest(
        matching_policy=MATCHING,
        comparison_policy=COMPARISON,
    )
    assert book.generation == 1
    assert book.resolution_generation == 0
    assert scope.generation == 1
    assert scope.is_dirty

    same = repository.create_revision(
        book_id=BookId(book.id),
        expected_generation=1,
        matching_policy=dict(reversed(tuple(MATCHING.items()))),
        comparison_policy=dict(reversed(tuple(COMPARISON.items()))),
        created_at=NOW,
    )
    book.refresh_from_db()
    scope.refresh_from_db()
    assert same.id == first.id
    assert book.generation == 1
    assert scope.generation == 1

    second_matching = {**MATCHING, "automatic_threshold_bp": 9100}
    second = repository.create_revision(
        book_id=BookId(book.id),
        expected_generation=1,
        matching_policy=second_matching,
        comparison_policy=COMPARISON,
        created_at=NOW,
    )
    book.refresh_from_db()
    scope.refresh_from_db()
    assert second.revision == 2
    assert book.generation == 2
    assert scope.generation == 2

    with pytest.raises(BookGenerationConflict):
        repository.create_revision(
            book_id=BookId(book.id),
            expected_generation=1,
            matching_policy={**MATCHING, "automatic_threshold_bp": 9200},
            comparison_policy=COMPARISON,
            created_at=NOW,
        )
    assert PolicyRevision.objects.count() == 2

    first.matching_policy = {"changed": True}
    with pytest.raises(ImmutableBookEvidenceError):
        first.save()
    with pytest.raises(ImmutableBookEvidenceError):
        PolicyRevision.objects.filter(id=first.id).update(digest="2" * 64)
    with pytest.raises(ImmutableBookEvidenceError):
        first.delete()


def test_policy_and_scope_ids_are_workspace_scoped_without_existence_distinction() -> None:
    owner = create_workspace("scope-owner")
    outsider = create_workspace("scope-outsider")
    book, left, right = create_book_graph(owner)
    scope = WorkspaceScopeRepository(WorkspaceId(owner.id)).create(
        book_id=BookId(book.id),
        coverage_key="2026-09",
        left_dataset_id=left.id,
        right_dataset_id=right.id,
        created_at=NOW,
    )
    policy = WorkspacePolicyRepository(WorkspaceId(owner.id)).create_revision(
        book_id=BookId(book.id),
        expected_generation=0,
        matching_policy=MATCHING,
        comparison_policy=COMPARISON,
        created_at=NOW,
    )

    outsider_scopes = WorkspaceScopeRepository(WorkspaceId(outsider.id))
    outsider_policies = WorkspacePolicyRepository(WorkspaceId(outsider.id))
    for value in (scope.id, uuid4()):
        with pytest.raises(ScopeUnavailable):
            outsider_scopes.get(value)
    for value in (policy.id, uuid4()):
        with pytest.raises(PolicyUnavailable):
            outsider_policies.get(value)


def test_policy_digest_requires_nonempty_object_payloads() -> None:
    with pytest.raises(Exception, match="must not be empty"):
        policy_revision_digest(matching_policy={}, comparison_policy=COMPARISON)
    with pytest.raises(Exception, match="must be objects"):
        policy_revision_digest(  # type: ignore[arg-type]
            matching_policy=[], comparison_policy=COMPARISON
        )
