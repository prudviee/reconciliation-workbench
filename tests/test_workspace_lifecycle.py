from __future__ import annotations

from datetime import UTC, datetime, timedelta
from io import StringIO

import pytest
from django.conf import settings
from django.core.management import CommandError, call_command
from django.db import IntegrityError, connection, transaction
from django.test import Client

from books.models import ReconciliationBook
from books.repositories import WorkspaceBookRepository
from reconciliation.domain import BookId, WorkspaceId, WorkspaceState
from workspaces.guards import WorkspaceBoundaryGuard
from workspaces.lifecycle import WorkspaceLifecycleService
from workspaces.models import CleanupReason, Workspace, WorkspaceCleanupRequest
from workspaces.repositories import WorkspaceUnavailable
from workspaces.sessions import digest_session_key


pytestmark = pytest.mark.django_db


def workspace_for(client: Client) -> Workspace:
    session_key = client.session.session_key
    assert session_key is not None
    return Workspace.objects.get(session_digest=digest_session_key(session_key))


def test_delete_confirmation_and_post_revoke_before_cleanup() -> None:
    client = Client(enforce_csrf_checks=True)
    client.get("/")
    workspace = workspace_for(client)
    WorkspaceBookRepository(WorkspaceId(workspace.id)).create_user_book(
        name="Private evidence",
        created_at=datetime(2026, 9, 5, tzinfo=UTC),
    )

    confirmation = client.get("/workspace/delete")
    token = client.cookies[settings.CSRF_COOKIE_NAME].value
    deleted = client.post(
        "/workspace/delete/confirm",
        HTTP_X_CSRFTOKEN=token,
        follow=True,
    )

    workspace.refresh_from_db()
    cleanup = WorkspaceCleanupRequest.objects.get(workspace=workspace)
    assert confirmation.status_code == 200
    assert "This cannot be recovered" in confirmation.content.decode()
    assert deleted.status_code == 200
    assert "Workspace access revoked" in deleted.content.decode()
    assert workspace.state == WorkspaceState.DELETED
    assert workspace.revoked_at is not None
    assert workspace.deleted_at is not None
    assert workspace.revoked_at <= workspace.deleted_at
    assert cleanup.reason == CleanupReason.DELETED
    assert cleanup.processed_at is None
    assert ReconciliationBook.objects.filter(workspace=workspace).exists()

    replacement_page = client.get("/")
    replacement = workspace_for(client)
    assert replacement_page.status_code == 200
    assert replacement.id != workspace.id
    assert replacement.state == WorkspaceState.ACTIVE


def test_delete_without_csrf_does_not_revoke() -> None:
    client = Client(enforce_csrf_checks=True)
    client.get("/")
    workspace = workspace_for(client)

    response = client.post("/workspace/delete/confirm")

    workspace.refresh_from_db()
    assert response.status_code == 403
    assert workspace.state == WorkspaceState.ACTIVE
    assert not WorkspaceCleanupRequest.objects.exists()


def test_deleted_session_cannot_read_mutate_or_create_work() -> None:
    owner = Client()
    owner.get("/")
    workspace = workspace_for(owner)
    repository = WorkspaceBookRepository(WorkspaceId(workspace.id))
    book = repository.create_user_book(
        name="Before deletion",
        created_at=datetime(2026, 9, 5, tzinfo=UTC),
    )
    old_session_key = owner.session.session_key
    assert old_session_key is not None
    WorkspaceLifecycleService().delete(
        WorkspaceId(workspace.id),
        now=datetime(2026, 9, 6, tzinfo=UTC),
    )

    def stale_client() -> Client:
        client = Client()
        client.cookies[settings.SESSION_COOKIE_NAME] = old_session_key
        return client

    read = stale_client().get(f"/books/{book.id}")
    mutation = stale_client().post(
        f"/books/{book.id}/rename", {"name": "Changed"}
    )
    create = stale_client().post("/books/demo")

    assert read.status_code == 302
    assert mutation.status_code == 302
    assert create.status_code == 302
    assert read.headers["Location"] == "/workspace/unavailable"
    assert mutation.headers["Location"] == "/workspace/unavailable"
    assert create.headers["Location"] == "/workspace/unavailable"
    book.refresh_from_db()
    assert book.name == "Before deletion"
    with pytest.raises(WorkspaceUnavailable):
        WorkspaceBookRepository(WorkspaceId(workspace.id)).create_user_book(
            name="Direct bypass",
            created_at=datetime(2026, 9, 6, tzinfo=UTC),
        )


def test_expiry_revokes_on_next_web_boundary_without_extending_deadline() -> None:
    client = Client()
    client.get("/")
    workspace = workspace_for(client)
    original_expiry = workspace.expires_at
    expired_creation = datetime.now(tz=UTC) - timedelta(days=7, seconds=1)
    Workspace.objects.filter(id=workspace.id).update(
        created_at=expired_creation,
        expires_at=expired_creation + timedelta(days=7),
    )

    response = client.get("/")

    workspace.refresh_from_db()
    assert response.status_code == 302
    assert response.headers["Location"] == "/workspace/unavailable"
    assert workspace.state == WorkspaceState.REVOKED
    assert workspace.expires_at == expired_creation + timedelta(days=7)
    assert workspace.expires_at != original_expiry
    cleanup = WorkspaceCleanupRequest.objects.get(workspace=workspace)
    assert cleanup.reason == CleanupReason.EXPIRED


def test_normal_activity_never_moves_persisted_expiry() -> None:
    client = Client()
    client.get("/")
    workspace = workspace_for(client)
    fixed_expiry = workspace.expires_at

    for _ in range(5):
        assert client.get("/").status_code == 200

    workspace.refresh_from_db()
    assert workspace.expires_at == fixed_expiry


def test_database_rejects_inconsistent_lifecycle_timestamps() -> None:
    client = Client()
    client.get("/")
    workspace = workspace_for(client)

    with pytest.raises(IntegrityError), transaction.atomic():
        Workspace.objects.filter(id=workspace.id).update(
            state=WorkspaceState.DELETED,
            revoked_at=None,
            deleted_at=None,
        )


def test_cleanup_schema_has_pending_index_and_reason_constraint() -> None:
    with connection.cursor() as cursor:
        constraints = connection.introspection.get_constraints(
            cursor, "workspace_cleanup_request"
        )

    assert constraints["cleanup_pending_idx"]["index"] is True
    assert constraints["cleanup_valid_reason"]["check"] is True


def test_revocation_is_idempotent_and_delete_upgrades_cleanup_reason() -> None:
    client = Client()
    client.get("/")
    workspace = workspace_for(client)
    service = WorkspaceLifecycleService()
    first_time = datetime(2026, 9, 12, tzinfo=UTC)

    first = service.expire(WorkspaceId(workspace.id), now=first_time)
    second = service.expire(
        WorkspaceId(workspace.id), now=first_time + timedelta(hours=1)
    )
    deleted = service.delete(
        WorkspaceId(workspace.id), now=first_time + timedelta(hours=2)
    )

    cleanup = WorkspaceCleanupRequest.objects.get(workspace=workspace)
    assert first.revoked_at == first_time
    assert second.revoked_at == first_time
    assert deleted.state == WorkspaceState.DELETED
    assert WorkspaceCleanupRequest.objects.filter(workspace=workspace).count() == 1
    assert cleanup.reason == CleanupReason.DELETED
    assert cleanup.requested_at == first_time


@pytest.mark.django_db(transaction=True)
def test_worker_guard_accepts_active_and_refuses_revoked_workspace() -> None:
    client = Client()
    client.get("/")
    workspace = workspace_for(client)
    output = StringIO()

    call_command("worker", once=True, workspace_id=str(workspace.id), stdout=output)
    WorkspaceLifecycleService().delete(
        WorkspaceId(workspace.id), now=datetime(2026, 9, 6, tzinfo=UTC)
    )

    assert output.getvalue().strip() == "worker heartbeat ready"
    with pytest.raises(CommandError, match="workspace unavailable"):
        call_command("worker", once=True, workspace_id=str(workspace.id))
    with pytest.raises(WorkspaceUnavailable):
        WorkspaceBoundaryGuard().require_active(
            WorkspaceId(workspace.id), now=datetime(2026, 9, 6, tzinfo=UTC)
        )
